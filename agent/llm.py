"""
Unified LLM interface for the Autonomous AI Task Worker.

Exposes one public function:
    call_llm(messages, tools, temperature) -> LLMResponse

Supported providers (selected via LLM_PROVIDER env var):
    mock      - Deterministic offline provider (no API key needed)
    gemini    - Google Gemini via google-genai SDK
    openai    - OpenAI GPT via openai SDK
    anthropic - Anthropic Claude via anthropic SDK

Invoice data baked into mock (matches data/invoices/ files):
    Acme Cloud Solutions    -> $14,250.00  due 2026-11-15  (normal)
    Apex Office Supplies    -> $ 6,050.00  due 2026-11-05  (normal)
    Nexus Logistics Inc     -> $ 8,400.00  due 2026-11-25  (normal)
    Quantum Data Labs       -> $78,500.00  due 2026-10-31  (requires approval > $50k)
    Skyline Telecom         -> $ 4,350.00  due 2026-09-15  (OVERDUE)
"""

import os
import json
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional


# ──────────────────────────────────────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ToolCall:
    """Represents a single tool invocation requested by the LLM."""
    id: str
    name: str
    arguments: Dict[str, Any]


@dataclass
class LLMResponse:
    """Represents the LLM's response: optional text + zero or more tool calls."""
    content: Optional[str]
    tool_calls: List[ToolCall] = field(default_factory=list)


# ──────────────────────────────────────────────────────────────────────────────
# Known invoice data (mirrors data/invoices/*.txt)
# ──────────────────────────────────────────────────────────────────────────────

# Each entry: vendor_key -> dict with file name, vendor name, amount, due_date
_INVOICE_DB = {
    "acme": {
        "file":     "data/invoices/invoice_acme_cloud_oct2026.txt",
        "vendor":   "Acme Cloud Solutions",
        "amount":   14250.00,
        "due_date": "2026-11-15",
        "overdue":  False,
    },
    "apex": {
        "file":     "data/invoices/invoice_apex_office_oct2026.txt",
        "vendor":   "Apex Office Supplies",
        "amount":   6050.00,
        "due_date": "2026-11-05",
        "overdue":  False,
    },
    "nexus": {
        "file":     "data/invoices/invoice_nexus_logistics_nov2026.txt",
        "vendor":   "Nexus Logistics Inc",
        "amount":   8400.00,
        "due_date": "2026-11-25",
        "overdue":  False,
    },
    "quantum": {
        "file":     "data/invoices/invoice_quantum_data_sep2026.txt",
        "vendor":   "Quantum Data Labs",
        "amount":   78500.00,
        "due_date": "2026-10-31",
        "overdue":  False,
    },
    "skyline": {
        "file":     "data/invoices/invoice_skyline_telecom_aug2026.txt",
        "vendor":   "Skyline Telecom",
        "amount":   4350.00,
        "due_date": "2026-09-15",
        "overdue":  True,
    },
}

# Vendor listing string (used as final answer for list-vendor queries)
_VENDOR_LIST_TEXT = (
    "Task complete. Here are all vendors registered in the internal ERP system:\n"
    "  1. Acme Cloud Solutions      (Cloud Hosting)     - ID: 1\n"
    "  2. Apex Office Supplies      (Office Equipment)  - ID: 3\n"
    "  3. Nexus Logistics Inc       (Supply Chain)      - ID: 2\n"
    "  4. Quantum Data Labs         (Data Science)      - ID: 4\n"
    "  5. Skyline Telecom           (Telecommunications)- ID: 5"
)


def _mk_login() -> ToolCall:
    """Helper: return a login ToolCall."""
    return ToolCall(
        id="login",
        name="api_request",
        arguments={
            "method": "POST",
            "path": "/auth/login",
            "json_body": {"username": "admin", "password": "secret_token_pass"}
        }
    )


def _mk_get(path: str, tc_id: str = "get") -> ToolCall:
    """Helper: return a GET ToolCall (token injected automatically by loop.py)."""
    return ToolCall(id=tc_id, name="api_request", arguments={"method": "GET", "path": path})


def _mk_post_invoice(vendor: str, amount: float, due_date: str, tc_id: str = "post") -> ToolCall:
    """Helper: return a POST /invoices ToolCall."""
    return ToolCall(
        id=tc_id,
        name="api_request",
        arguments={
            "method": "POST",
            "path": "/invoices",
            "json_body": {
                "vendor": vendor,
                "amount": amount,
                "due_date": due_date,
                "currency": "USD"
            }
        }
    )


# ──────────────────────────────────────────────────────────────────────────────
# Task type detector
# ──────────────────────────────────────────────────────────────────────────────

def _detect_task(first_user_msg: str) -> str:
    """
    Classifies the user's task into one of several canonical types.
    Returns a string tag used by the mock router.

    Priority order (highest to lowest):
      1. Vendor list query
      2. Invoice count
      3. Overdue check
      4. Total / sum (generic — all vendors)
      5. Total / sum for a specific vendor
      6. Full invoice processing for a specific vendor
      7. Amount-based detection
      8. Default: Acme Cloud happy path
    """
    msg = first_user_msg.lower()

    # 1. Vendor listing (no invoice context)
    if ("list" in msg or "show" in msg or "what" in msg or "which" in msg) and "vendor" in msg and "invoice" not in msg:
        return "list_vendors"
    # Also catch "registered vendors", "all vendors" without invoice
    if "vendor" in msg and "invoice" not in msg and "total" not in msg and "sum" not in msg:
        return "list_vendors"

    # 2. Invoice count
    if "how many" in msg and "invoice" in msg:
        return "count_invoices"
    if "count" in msg and "invoice" in msg:
        return "count_invoices"

    # 3. Overdue invoices
    if "overdue" in msg:
        return "list_overdue"

    # 4. Grand total across ALL vendors
    #    Phrases like: "total of all invoices", "total of all invoices from all vendors", "sum of all invoices"
    if ("total" in msg or "sum" in msg) and "invoice" in msg:
        # Check if a specific vendor is named (not "all vendors")
        named_vendor_key = None
        for key, inv in _INVOICE_DB.items():
            if _vendor_in_msg(inv["vendor"], msg):
                named_vendor_key = key
                break

        # "all vendors" or no specific vendor => grand total
        if named_vendor_key is None or "all vendor" in msg:
            return "total_all_invoices"
        else:
            return f"vendor_total_{named_vendor_key}"

    # 5. Specific vendor invoice processing (find + extract + submit)
    for key, inv in _INVOICE_DB.items():
        if _vendor_in_msg(inv["vendor"], msg):
            return f"process_{key}"

    # 6. Amount-based detection (e.g. "process the $78,500 invoice")
    for key, inv in _INVOICE_DB.items():
        amount_str = str(int(inv["amount"]))
        if amount_str in msg.replace(",", ""):
            return f"process_{key}"

    # 7. Default: Acme Cloud happy path (the main demo task shown in the README)
    return "process_acme"


def _vendor_in_msg(vendor_name: str, msg: str) -> bool:
    """Check if any word fragment of the vendor name appears in msg."""
    parts = vendor_name.lower().split()
    # Match if at least 2 distinctive words appear, or the first word + one more
    matches = sum(1 for p in parts if p in msg and len(p) > 3)
    return matches >= 1


# ──────────────────────────────────────────────────────────────────────────────
# Individual task handlers (each returns an LLMResponse for a given step)
# ──────────────────────────────────────────────────────────────────────────────

def _handle_list_vendors(h: str) -> LLMResponse:
    """List all vendors: login -> GET /vendors -> summarize."""
    if "access_token" not in h:
        return LLMResponse(
            content="I need to authenticate before querying the vendor directory.",
            tool_calls=[_mk_login()]
        )
    if "/vendors" not in h:
        return LLMResponse(
            content="Authenticated. Now fetching all registered vendors from the ERP system.",
            tool_calls=[_mk_get("/vendors", "get_vendors")]
        )
    # Final answer
    return LLMResponse(content=_VENDOR_LIST_TEXT, tool_calls=[])


def _handle_count_invoices(h: str) -> LLMResponse:
    """Count invoices: login -> GET /invoices -> report count."""
    if "access_token" not in h:
        return LLMResponse(
            content="Authenticating to access invoice records.",
            tool_calls=[_mk_login()]
        )
    if "/invoices" not in h or "http 200" not in h:
        return LLMResponse(
            content="Authenticated. Fetching all invoices to determine the total count.",
            tool_calls=[_mk_get("/invoices", "get_invoices")]
        )
    return LLMResponse(
        content=(
            "Task complete. Retrieved all invoice records from the ERP system. "
            "There are currently 5 vendors with invoices in the system. "
            "The full list is displayed in the API response above."
        ),
        tool_calls=[]
    )


def _handle_list_overdue(h: str) -> LLMResponse:
    """List overdue invoices: login -> GET /invoices -> filter and report."""
    if "access_token" not in h:
        return LLMResponse(
            content="Authenticating with the ERP system to retrieve invoice records.",
            tool_calls=[_mk_login()]
        )
    if "/invoices" not in h or "http 200" not in h:
        return LLMResponse(
            content="Authenticated. Fetching all invoices to identify overdue entries.",
            tool_calls=[_mk_get("/invoices", "get_invoices")]
        )
    return LLMResponse(
        content=(
            "Task complete. After reviewing all invoice records, I found the following OVERDUE invoice:\n"
            "  - Vendor: Skyline Telecom\n"
            "    Amount: $4,350.00\n"
            "    Due Date: 2026-09-15 (OVERDUE - past due date)\n"
            "    File: invoice_skyline_telecom_aug2026.txt\n\n"
            "All other invoices (Acme, Apex, Nexus, Quantum) have future due dates."
        ),
        tool_calls=[]
    )


def _handle_total_all_invoices(h: str) -> LLMResponse:
    """Sum of all invoices: login -> GET /invoices -> compute total."""
    if "access_token" not in h:
        return LLMResponse(
            content="Authenticating to fetch all invoice records for summation.",
            tool_calls=[_mk_login()]
        )
    if "/invoices" not in h or "http 200" not in h:
        return LLMResponse(
            content="Authenticated. Retrieving all invoices to compute the grand total.",
            tool_calls=[_mk_get("/invoices", "get_invoices")]
        )
    # 14250 + 6050 + 8400 + 78500 + 4350 = 111550
    return LLMResponse(
        content=(
            "Task complete. Grand total of all invoices in the ERP system:\n"
            "  Acme Cloud Solutions   : $14,250.00\n"
            "  Apex Office Supplies   : $ 6,050.00\n"
            "  Nexus Logistics Inc    : $ 8,400.00\n"
            "  Quantum Data Labs      : $78,500.00\n"
            "  Skyline Telecom        : $ 4,350.00\n"
            "  ---------------------------------\n"
            "  GRAND TOTAL            : $111,550.00"
        ),
        tool_calls=[]
    )


def _handle_vendor_total(key: str, h: str) -> LLMResponse:
    """Total for a specific vendor: login -> GET /invoices -> filter -> report."""
    inv = _INVOICE_DB[key]
    if "access_token" not in h:
        return LLMResponse(
            content=f"Authenticating to access invoice records for {inv['vendor']}.",
            tool_calls=[_mk_login()]
        )
    if "/invoices" not in h or "http 200" not in h:
        return LLMResponse(
            content=f"Authenticated. Fetching all invoices to compute total for {inv['vendor']}.",
            tool_calls=[_mk_get("/invoices", "get_invoices")]
        )
    return LLMResponse(
        content=(
            f"Task complete. Total invoices for {inv['vendor']}:\n"
            f"  File     : {inv['file']}\n"
            f"  Amount   : ${inv['amount']:,.2f} USD\n"
            f"  Due Date : {inv['due_date']}\n"
            f"  Grand Total for {inv['vendor']}: ${inv['amount']:,.2f}"
        ),
        tool_calls=[]
    )


def _handle_process_invoice(key: str, h: str) -> LLMResponse:
    """
    Full invoice processing workflow for a given vendor:
    list_files -> read_file -> login -> POST /invoices -> GET /invoices/{id} -> done
    """
    inv = _INVOICE_DB[key]
    filename = inv["file"].split("/")[-1]  # e.g. invoice_acme_cloud_oct2026.txt

    # Step 1: List files (only if we haven't seen the directory listing yet)
    if "data/invoices" not in h:
        return LLMResponse(
            content="I will start by listing all invoice files in the repository to locate the target invoice.",
            tool_calls=[ToolCall(id="list", name="list_files", arguments={"directory": "data/invoices"})]
        )

    # Step 2: Read the specific file (if we see the directory but not the file contents)
    if filename not in h:
        return LLMResponse(
            content=f"Found the invoice file. Reading {filename} to extract the amount and due date.",
            tool_calls=[ToolCall(id="read", name="read_file", arguments={"filepath": inv["file"]})]
        )

    # Step 3: Authenticate (file is read, but no token yet)
    if "access_token" not in h:
        return LLMResponse(
            content=(
                f"Extracted from {filename}:\n"
                f"  Vendor   : {inv['vendor']}\n"
                f"  Amount   : ${inv['amount']:,.2f} USD\n"
                f"  Due Date : {inv['due_date']}\n\n"
                "Now authenticating with the ERP API to submit this invoice."
            ),
            tool_calls=[_mk_login()]
        )

    # Step 4: POST the invoice (if authenticated but not created yet)
    if "http 201" not in h and "http 409" not in h:
        return LLMResponse(
            content=(
                f"Authenticated successfully. Submitting invoice to the ERP system:\n"
                f"  Vendor   : {inv['vendor']}\n"
                f"  Amount   : ${inv['amount']:,.2f}\n"
                f"  Due Date : {inv['due_date']}"
            ),
            tool_calls=[_mk_post_invoice(inv["vendor"], inv["amount"], inv["due_date"], "post_inv")]
        )

    # Step 5: Independent verification GET
    if "/invoices/1" not in h and "/invoices/2" not in h and "/invoices/3" not in h:
        return LLMResponse(
            content=(
                "Invoice record created successfully. "
                "Running mandatory independent verification (GET /invoices/{id}) "
                "to confirm data integrity."
            ),
            tool_calls=[_mk_get("/invoices/1", "verify")]
        )

    # Step 6: All done
    status = "OVERDUE" if inv["overdue"] else "PENDING"
    return LLMResponse(
        content=(
            f"Task complete. The {inv['vendor']} invoice has been:\n"
            f"  1. Located  : {inv['file']}\n"
            f"  2. Extracted: Amount = ${inv['amount']:,.2f}, Due Date = {inv['due_date']}\n"
            f"  3. Submitted: POST /invoices -> HTTP 201 Created\n"
            f"  4. Verified : GET /invoices/1 -> Amount and due date confirmed in system\n"
            f"  Status: {status}"
        ),
        tool_calls=[]
    )


# ──────────────────────────────────────────────────────────────────────────────
# Main mock provider
# ──────────────────────────────────────────────────────────────────────────────

def _mock_provider(messages: List[Dict[str, Any]]) -> LLMResponse:
    """
    Deterministic mock LLM provider for offline demos and automated tests.

    How it works:
      1. Reads the FIRST user message to classify the task type once.
      2. Reads the FULL conversation history to determine which step we are on.
      3. Returns the correct next action (tool call or final text answer).

    This means the agent loop drives execution naturally — no hard-coded step
    counters. The mock simply asks 'what has already happened?' and picks the
    right next action.
    """
    if not messages:
        return LLMResponse(content="No task provided.", tool_calls=[])

    # Compact history string for step detection (lowercase for matching)
    full_history = " ".join(
        str(m.get("content", "")) for m in messages
    ).lower()

    # Find the first USER message (skip the system prompt which also contains context words)
    first_user_msg = ""
    for m in messages:
        if m.get("role") == "user":
            first_user_msg = m.get("content", "").lower()
            break

    # Detect which task type this is
    task_type = _detect_task(first_user_msg)

    # Route to the correct handler
    if task_type == "list_vendors":
        return _handle_list_vendors(full_history)

    elif task_type == "count_invoices":
        return _handle_count_invoices(full_history)

    elif task_type == "list_overdue":
        return _handle_list_overdue(full_history)

    elif task_type == "total_all_invoices":
        return _handle_total_all_invoices(full_history)

    elif task_type.startswith("vendor_total_"):
        key = task_type.replace("vendor_total_", "")
        return _handle_vendor_total(key, full_history)

    elif task_type.startswith("process_"):
        key = task_type.replace("process_", "")
        if key in _INVOICE_DB:
            return _handle_process_invoice(key, full_history)

    # Absolute fallback: default Acme happy path
    return _handle_process_invoice("acme", full_history)


# ──────────────────────────────────────────────────────────────────────────────
# Gemini helper
# ──────────────────────────────────────────────────────────────────────────────

def _convert_tools_for_gemini(tools: List[Dict[str, Any]]) -> List[Dict]:
    """Converts OpenAI-style tool schemas into Gemini function_declarations format."""
    declarations = []
    for t in tools:
        fn = t.get("function", {})
        declarations.append({
            "name": fn.get("name"),
            "description": fn.get("description", ""),
            "parameters": fn.get("parameters", {"type": "object", "properties": {}})
        })
    return declarations


# ──────────────────────────────────────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────────────────────────────────────

def call_llm(
    messages: List[Dict[str, Any]],
    tools: Optional[List[Dict[str, Any]]] = None,
    temperature: float = 0.0
) -> LLMResponse:
    """
    Unified LLM call. Provider is selected via the LLM_PROVIDER environment variable.

    Args:
        messages    : Conversation history in OpenAI chat format
                      [{"role": "system"|"user"|"assistant", "content": "..."}]
        tools       : Optional list of tool schemas in OpenAI function-calling format
        temperature : Sampling temperature (0.0 = deterministic/greedy)

    Returns:
        LLMResponse with .content (text) and .tool_calls (list of ToolCall)

    Raises:
        ValueError  : If required API key is missing
        RuntimeError: If the API call itself fails
    """
    provider = os.getenv("LLM_PROVIDER", "mock").lower()

    # ------------------------------------------------------------------
    # MOCK PROVIDER — deterministic, no network, works offline
    # ------------------------------------------------------------------
    if provider == "mock":
        return _mock_provider(messages)

    # ------------------------------------------------------------------
    # OPENAI PROVIDER
    # ------------------------------------------------------------------
    elif provider == "openai":
        from openai import OpenAI

        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise ValueError(
                "OPENAI_API_KEY is not set. "
                "Add it to your .env file or export it in your shell."
            )
        client = OpenAI(api_key=api_key)

        kwargs: Dict[str, Any] = {
            "model": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
            "messages": messages,
            "temperature": temperature,
        }
        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        completion = client.chat.completions.create(**kwargs)
        choice = completion.choices[0].message

        parsed_tool_calls: List[ToolCall] = []
        if choice.tool_calls:
            for tc in choice.tool_calls:
                try:
                    args = json.loads(tc.function.arguments)
                except (json.JSONDecodeError, ValueError):
                    args = {"raw": tc.function.arguments}
                parsed_tool_calls.append(
                    ToolCall(id=tc.id, name=tc.function.name, arguments=args)
                )

        return LLMResponse(content=choice.content, tool_calls=parsed_tool_calls)

    # ------------------------------------------------------------------
    # GEMINI PROVIDER
    # ------------------------------------------------------------------
    elif provider == "gemini":
        try:
            from google import genai
            from google.genai import types

            api_key = os.getenv("GEMINI_API_KEY")
            if not api_key:
                raise ValueError(
                    "GEMINI_API_KEY is not set. "
                    "Get one at https://ai.google.dev and add it to your .env file."
                )
            client = genai.Client(api_key=api_key)

            # Separate system instruction from chat turns
            system_instruction: Optional[str] = None
            chat_contents: List[Dict] = []
            for m in messages:
                role = m.get("role", "")
                content = m.get("content", "")
                if role == "system":
                    system_instruction = content
                elif role in ("user", "human"):
                    chat_contents.append({"role": "user", "parts": [{"text": content}]})
                elif role in ("assistant", "model"):
                    chat_contents.append({"role": "model", "parts": [{"text": content}]})

            # Build config
            config = types.GenerateContentConfig(
                temperature=temperature,
                system_instruction=system_instruction,
            )
            if tools:
                config.tools = [{"function_declarations": _convert_tools_for_gemini(tools)}]

            response = client.models.generate_content(
                model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
                contents=chat_contents,
                config=config,
            )

            parsed_tool_calls = []
            content_text = ""
            for part in response.candidates[0].content.parts:
                if hasattr(part, "function_call") and part.function_call:
                    fc = part.function_call
                    parsed_tool_calls.append(ToolCall(
                        id=f"call_{fc.name}",
                        name=fc.name,
                        arguments=dict(fc.args) if fc.args else {}
                    ))
                elif hasattr(part, "text") and part.text:
                    content_text += part.text

            return LLMResponse(content=content_text, tool_calls=parsed_tool_calls)

        except Exception as e:
            raise RuntimeError(f"Gemini API invocation error: {str(e)}")

    # ------------------------------------------------------------------
    # ANTHROPIC PROVIDER
    # ------------------------------------------------------------------
    elif provider == "anthropic":
        import anthropic

        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. "
                "Add it to your .env file or export it in your shell."
            )
        client = anthropic.Anthropic(api_key=api_key)

        # Convert tools to Anthropic format
        anthropic_tools = []
        if tools:
            for t in tools:
                fn = t.get("function", {})
                anthropic_tools.append({
                    "name": fn.get("name"),
                    "description": fn.get("description", ""),
                    "input_schema": fn.get("parameters", {"type": "object", "properties": {}})
                })

        # Separate system message from conversation turns
        system_text = ""
        user_messages: List[Dict] = []
        for m in messages:
            if m.get("role") == "system":
                system_text += m["content"] + "\n"
            else:
                user_messages.append({"role": m["role"], "content": m["content"]})

        resp = client.messages.create(
            model=os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022"),
            system=system_text.strip(),
            messages=user_messages,
            tools=anthropic_tools,
            temperature=temperature,
            max_tokens=2048,
        )

        parsed_tool_calls = []
        content_text = ""
        for block in resp.content:
            if block.type == "tool_use":
                parsed_tool_calls.append(ToolCall(
                    id=block.id,
                    name=block.name,
                    arguments=block.input
                ))
            elif block.type == "text":
                content_text += block.text

        return LLMResponse(content=content_text, tool_calls=parsed_tool_calls)

    # ------------------------------------------------------------------
    # UNKNOWN PROVIDER
    # ------------------------------------------------------------------
    else:
        raise ValueError(
            f"Unsupported LLM_PROVIDER: '{provider}'. "
            "Choose from: mock, gemini, openai, anthropic"
        )
