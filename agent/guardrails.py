"""
Guardrails, Safety Rules, and Loop Detection.
Enforces:
1. Step limits (prevents infinite execution runs).
2. Loop detection (catches repeated identical tool calls with identical arguments).
3. Company policy approval triggers:
   - Invoice amount > $50,000 threshold
   - Destructive calls (DELETE, PATCH)
4. Secrets redaction in audit logs.
"""

from typing import List, Dict, Any, Tuple
import re

MAX_STEP_LIMIT = 15
MAX_REPEATED_ACTIONS = 2

class GuardrailViolation(Exception):
    """Raised when a hard safety guardrail is breached."""
    pass


def check_step_limit(current_step: int, max_steps: int = MAX_STEP_LIMIT) -> bool:
    """Returns True if within limit, False if exceeded."""
    return current_step < max_steps


def detect_repeated_action(history: List[Dict[str, Any]], new_action: str) -> bool:
    """
    Detects if the agent is stuck in an infinite loop making the exact same tool call repeatedly.
    """
    if len(history) < MAX_REPEATED_ACTIONS:
        return False

    recent_actions = [h.get("action") for h in history[-MAX_REPEATED_ACTIONS:]]
    if all(a == new_action for a in recent_actions):
        return True
    return False


def check_action_approval_required(
    tool_name: str,
    tool_args: Dict[str, Any],
    company_rules: Dict[str, Any]
) -> Tuple[bool, str]:
    """
    Checks if an action violates policy thresholds and requires human approval before proceeding.
    Returns: (requires_approval: bool, reason: str)
    """
    policy = company_rules.get("accounts_payable_policy", {})
    threshold = policy.get("human_approval_threshold", 50000.0)

    # 1. Check API tool calls
    if tool_name == "api_request":
        method = tool_args.get("method", "").upper()
        path = tool_args.get("path", "")
        body = tool_args.get("json_body", {})

        # Destructive action check (DELETE or PATCH)
        if method in ("DELETE", "PATCH"):
            return True, f"Policy requires explicit human approval for destructive operations ({method} {path})."

        # Creation amount threshold check
        if method == "POST" and "/invoices" in path:
            if isinstance(body, dict):
                amount = body.get("amount", 0.0)
                try:
                    amount_val = float(amount)
                    if amount_val > threshold:
                        return True, f"Invoice amount ${amount_val:,.2f} exceeds policy approval threshold of ${threshold:,.2f}."
                except (ValueError, TypeError):
                    pass

    return False, ""


def redact_secrets(text: str) -> str:
    """
    Redacts sensitive secrets such as JWT tokens and passwords from logs.
    """
    if not isinstance(text, str):
        return str(text)

    # Redact JWT tokens (ey...)
    redacted = re.sub(r'eyJ[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+\.[a-zA-Z0-9_-]+', '[REDACTED_JWT_TOKEN]', text)
    # Redact secret passwords
    redacted = re.sub(r'("password":\s*")[^"]+(")', r'\1[REDACTED_PASSWORD]\2', redacted)
    redacted = re.sub(r"('password':\s*')[^']+(')", r"\1[REDACTED_PASSWORD]\2", redacted)
    return redacted
