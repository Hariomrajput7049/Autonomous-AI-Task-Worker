"""
Test script for Phase 4: Full Multi-Step ReAct Loop, Planning, Guardrails & Logging.
"""

import os
import glob
from agent.loop import run_agent_worker
from agent.llm import LLMResponse, ToolCall
import agent.llm as llm_module
from tools.human import set_mock_human_response
from tools.test_tools import start_background_api

def test_full_loop_phase4():
    print("=" * 60)
    print("TESTING PHASE 4: FULL AGENT LOOP & AUDIT LOGGING")
    print("=" * 60)

    # 1. Start Background API
    start_background_api()

    # 2. Configure deterministic mock LLM sequence simulating the complete invoice entry task
    call_counter = {"val": 0}
    
    def deterministic_agent_llm(messages, tools=None, temperature=0.0):
        c = call_counter["val"]
        call_counter["val"] += 1
        
        # Turn 0: List files
        if c == 0:
            return LLMResponse(
                content="I need to inspect the invoice files available.",
                tool_calls=[ToolCall(id="c0", name="list_files", arguments={"directory": "data/invoices"})]
            )
        # Turn 1: Read Acme invoice
        elif c == 1:
            return LLMResponse(
                content="I will read the Acme invoice to extract vendor, amount, and due date.",
                tool_calls=[ToolCall(id="c1", name="read_file", arguments={"filepath": "data/invoices/invoice_acme_cloud_oct2026.txt"})]
            )
        # Turn 2: Authenticate with ERP API
        elif c == 2:
            return LLMResponse(
                content="Extracted Acme Cloud Solutions: $14,250 due 2026-11-15. Now authenticating with ERP.",
                tool_calls=[ToolCall(id="c2", name="api_request", arguments={
                    "method": "POST",
                    "path": "/auth/login",
                    "json_body": {"username": "admin", "password": "secret_token_pass"}
                })]
            )
        # Turn 3: Create Invoice in ERP
        elif c == 3:
            return LLMResponse(
                content="Authentication succeeded. Submitting invoice record into ERP system.",
                tool_calls=[ToolCall(id="c3", name="api_request", arguments={
                    "method": "POST",
                    "path": "/invoices",
                    "json_body": {
                        "vendor": "Acme Cloud Solutions",
                        "amount": 14250.0,
                        "due_date": "2026-11-15",
                        "currency": "USD"
                    }
                })]
            )
        # Turn 4: Mandatory Independent Verification
        elif c == 4:
            return LLMResponse(
                content="Invoice created. Now independently executing GET /invoices/1 to verify record integrity.",
                tool_calls=[ToolCall(id="c4", name="api_request", arguments={
                    "method": "GET",
                    "path": "/invoices/1"
                })]
            )
        # Turn 5: Final completion summary
        else:
            return LLMResponse(
                content="Successfully processed Acme Cloud invoice ACS-2026-9810 ($14,250 due 2026-11-15). Created record ID 1 and verified.",
                tool_calls=[]
            )

    # Monkey patch call_llm for Phase 4 deterministic test
    llm_module.call_llm = deterministic_agent_llm

    task = "Find the latest invoice from Acme Cloud Solutions, extract amount and due date, enter it into our internal system, and tell me once it is done."
    result = run_agent_worker(task=task, auto_approve=True)

    print("\n--- AGENT RESULT SUMMARY ---")
    print(f"Status: {result['status']}")
    print(f"Steps:  {result['steps']}")
    print(f"Summary: {result['summary']}")
    print(f"Evidence: {result['evidence']}")

    assert result["status"] == "COMPLETED"
    assert result["evidence"]["facts"]["verified"] is True
    assert result["evidence"]["facts"]["created_invoice_id"] == 1

    # Verify audit log was created on disk
    log_files = glob.glob(f"logs/{result['run_id']}.jsonl")
    assert len(log_files) == 1, f"Expected audit log file for run {result['run_id']}"
    print(f"\nAudit Log verified at: {log_files[0]}")

    with open(log_files[0], "r", encoding="utf-8") as f:
        log_lines = f.readlines()
        print(f"Audit log contains {len(log_lines)} entries.")
        # Ensure passwords and tokens are redacted
        raw_log_text = "".join(log_lines)
        assert "secret_token_pass" not in raw_log_text, "Password was not redacted in audit log!"
        assert "[REDACTED_PASSWORD]" in raw_log_text or "[REDACTED_JWT_TOKEN]" in raw_log_text

    print("\n>>> PHASE 4 FULL REACT LOOP & AUDIT LOGGING VERIFIED! <<<")

if __name__ == "__main__":
    test_full_loop_phase4()
