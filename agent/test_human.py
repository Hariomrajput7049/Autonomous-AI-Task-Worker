"""
Verification suite for Phase 7: Human-in-the-Loop & Policy Guardrails.
Tests:
1. High-Value Approval (> $50,000) - Quantum Data Labs ($78,500) approved.
2. High-Value Approval - Rejected by Human -> Action safely halted.
3. Destructive Action Approval - PATCH / DELETE operations.
"""

import os
import json
from agent.loop import run_agent_worker
from agent.llm import LLMResponse, ToolCall
import agent.llm as llm_module
from tools.human import set_mock_human_response
from tools.test_tools import start_background_api
from tools.registry import execute_tool_call

def test_high_value_approved():
    print("\n--- [TEST 1] High-Value Approval ($78,500 > $50,000) -> Approved ---")
    execute_tool_call("api_request", {"method": "POST", "path": "/system/reset"})

    # Simulate human operator approving the action
    approval_counter = {"asked": 0}
    def mock_human(question: str) -> str:
        approval_counter["asked"] += 1
        print(f" -> Human received approval request: '{question}'")
        return "approve"

    set_mock_human_response(mock_human)

    call_seq = {"turn": 0}
    def mock_llm_high_val(messages, tools=None, temperature=0.0):
        t = call_seq["turn"]
        call_seq["turn"] += 1
        if t == 0:
            return LLMResponse(
                content="Authenticating with ERP.",
                tool_calls=[ToolCall(id="t0", name="api_request", arguments={
                    "method": "POST", "path": "/auth/login", "json_body": {"username": "admin", "password": "secret_token_pass"}
                })]
            )
        elif t == 1:
            # Submitting high value invoice ($78,500 > threshold of $50,000)
            return LLMResponse(
                content="Submitting Quantum Data Labs invoice for $78,500.",
                tool_calls=[ToolCall(id="t1", name="api_request", arguments={
                    "method": "POST", "path": "/invoices", "json_body": {
                        "vendor": "Quantum Data Labs", "amount": 78500.0, "due_date": "2026-10-31", "currency": "USD"
                    }
                })]
            )
        elif t == 2:
            return LLMResponse(
                content="Verifying created record via independent GET /invoices/1.",
                tool_calls=[ToolCall(id="t2", name="api_request", arguments={"method": "GET", "path": "/invoices/1"})]
            )
        else:
            return LLMResponse(content="Task completed: High value invoice approved and submitted.", tool_calls=[])

    llm_module.call_llm = mock_llm_high_val
    result = run_agent_worker("Process Quantum Data Labs invoice", auto_approve=False)

    assert approval_counter["asked"] >= 1, "Expected human operator to be asked for approval"
    assert result["status"] == "COMPLETED"
    print(" -> High value invoice successfully approved and created.")


def test_high_value_rejected():
    print("\n--- [TEST 2] High-Value Approval ($78,500) -> Rejected by Human ---")
    execute_tool_call("api_request", {"method": "POST", "path": "/system/reset"})

    # Simulate human operator rejecting the action
    def mock_human_reject(question: str) -> str:
        print(f" -> Human received approval request: '{question}' and typed: reject")
        return "reject"

    set_mock_human_response(mock_human_reject)

    call_seq = {"turn": 0}
    def mock_llm_rejected(messages, tools=None, temperature=0.0):
        t = call_seq["turn"]
        call_seq["turn"] += 1
        if t == 0:
            return LLMResponse(
                content="Authenticating with ERP.",
                tool_calls=[ToolCall(id="t0", name="api_request", arguments={
                    "method": "POST", "path": "/auth/login", "json_body": {"username": "admin", "password": "secret_token_pass"}
                })]
            )
        elif t == 1:
            return LLMResponse(
                content="Attempting submission of $78,500 invoice.",
                tool_calls=[ToolCall(id="t1", name="api_request", arguments={
                    "method": "POST", "path": "/invoices", "json_body": {
                        "vendor": "Quantum Data Labs", "amount": 78500.0, "due_date": "2026-10-31", "currency": "USD"
                    }
                })]
            )
        else:
            return LLMResponse(content="Operator rejected the submission. Task halted gracefully.", tool_calls=[])

    llm_module.call_llm = mock_llm_rejected
    result = run_agent_worker("Process Quantum Data Labs invoice", auto_approve=False)

    assert result["status"] == "FINISHED_UNVERIFIED"
    print(" -> High-value submission was safely halted upon human rejection.")


def test_destructive_action_approval():
    print("\n--- [TEST 3] Destructive Action (DELETE /invoices/1) -> Approval Required ---")
    execute_tool_call("api_request", {"method": "POST", "path": "/system/reset"})

    asked_counter = {"val": 0}
    def mock_human_delete(question: str) -> str:
        asked_counter["val"] += 1
        return "approve"

    set_mock_human_response(mock_human_delete)

    call_seq = {"turn": 0}
    def mock_llm_delete(messages, tools=None, temperature=0.0):
        t = call_seq["turn"]
        call_seq["turn"] += 1
        if t == 0:
            return LLMResponse(
                content="Authenticating with ERP.",
                tool_calls=[ToolCall(id="t0", name="api_request", arguments={
                    "method": "POST", "path": "/auth/login", "json_body": {"username": "admin", "password": "secret_token_pass"}
                })]
            )
        elif t == 1:
            return LLMResponse(
                content="Attempting to delete invoice 1.",
                tool_calls=[ToolCall(id="t1", name="api_request", arguments={
                    "method": "DELETE", "path": "/invoices/1"
                })]
            )
        else:
            return LLMResponse(content="Deletion concluded.", tool_calls=[])

    llm_module.call_llm = mock_llm_delete
    run_agent_worker("Delete invoice 1", auto_approve=False)
    assert asked_counter["val"] >= 1, "Expected human approval before DELETE"
    print(" -> Destructive DELETE triggered human approval guardrail.")


def run_all_human_tests():
    start_background_api()
    test_high_value_approved()
    test_high_value_rejected()
    test_destructive_action_approval()
    print("\n>>> ALL PHASE 7 HUMAN APPROVAL & GUARDRAIL TESTS PASSED! <<<")

if __name__ == "__main__":
    run_all_human_tests()
