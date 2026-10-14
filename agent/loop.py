"""
Autonomous AI Task Worker - Core Execution Loop (ReAct).
Flow:
Goal -> Understand -> Plan -> Execute -> Observe -> Adapt -> Verify -> Complete
"""

import os
import uuid
import json
import time
from typing import Dict, Any, Optional

import agent.llm as llm_module
from agent.llm import LLMResponse, ToolCall
from agent.memory import AgentState, load_company_context
from agent.planner import generate_initial_plan, format_plan_for_prompt
from agent.guardrails import (
    check_step_limit, detect_repeated_action, check_action_approval_required, MAX_STEP_LIMIT
)
from agent.logger import AuditLogger
from tools.registry import TOOL_SCHEMAS, execute_tool_call
from tools.human import ask_human

SYSTEM_PROMPT_TEMPLATE = """You are an Autonomous AI Task Worker.
Your objective is to independently complete the user's task using available tools.

Operational Instructions:
1. THINK before acting: State your thought, current step, and reasoning.
2. RECOGNIZE ERRORS:
   - If HTTP 422: The payload violated validation (e.g. date format must be strict YYYY-MM-DD). Fix the field and retry.
   - If HTTP 401: Your token expired or is missing. Re-login at /auth/login and retry with new token.
   - If HTTP 429: You were rate limited. Check Retry-After and pause before retrying.
   - If HTTP 409: Duplicate record detected. Do NOT blindly retry; inspect or inform the user.
3. VERIFICATION IS MANDATORY:
   - Never declare task completion until you execute an independent GET /invoices/{{id}} check and verify that the stored amount and due date match the source invoice.
4. COMPANY CONTEXT & APPROVALS:
{company_rules}

Current State:
{state_summary}

Plan:
{plan_status}
"""

def extract_facts_from_observation(state: AgentState, tool_name: str, args: Dict[str, Any], observation: str):
    """Heuristic updates to working memory to keep facts fresh and compact."""
    # Auth token capture
    if tool_name == "api_request" and "/auth/login" in args.get("path", ""):
        if "access_token" in observation:
            try:
                # Extract token from json body in observation
                body_part = observation.split("Body:")[1].strip()
                data = json.loads(body_part)
                token = data.get("access_token")
                if token:
                    state.update_fact("auth_token", token)
            except Exception:
                pass

    # Created invoice ID capture
    if tool_name == "api_request" and args.get("method") == "POST" and "/invoices" in args.get("path", ""):
        if "HTTP 201" in observation:
            try:
                body_part = observation.split("Body:")[1].strip()
                data = json.loads(body_part)
                inv_id = data.get("id")
                if inv_id:
                    state.update_fact("created_invoice_id", inv_id)
            except Exception:
                pass

    # Read file capture
    if tool_name == "read_file":
        filepath = args.get("filepath")
        if filepath:
            state.update_fact("invoice_file", filepath)


def run_agent_worker(
    task: str,
    max_steps: int = MAX_STEP_LIMIT,
    auto_approve: bool = False
) -> Dict[str, Any]:
    """
    Runs the autonomous task worker end-to-end.
    """
    run_id = f"run_{str(uuid.uuid4())[:8]}"
    state = AgentState(
        task=task,
        run_id=run_id,
        company_context=load_company_context(),
        max_steps=max_steps
    )
    logger = AuditLogger(run_id=run_id)

    print("\n" + "=" * 70)
    print(f">> [AGENT START] Run ID: {run_id}")
    print(f">> Goal: {task}")
    print("=" * 70)

    # 1. UNDERSTAND & PLAN
    print("[PLANNER] Decomposing task and building execution plan...")
    plan_info = generate_initial_plan(task, state.company_context)
    state.plan = plan_info.get("initial_plan", [])
    print(f"[PLANNER] Goal: {plan_info.get('understood_goal')}")
    print(f"[PLANNER] Steps:\n{format_plan_for_prompt(state.plan)}")

    # Initialize message history
    formatted_system = SYSTEM_PROMPT_TEMPLATE.format(
        company_rules=json.dumps(state.company_context, indent=2),
        state_summary=state.to_summary(),
        plan_status=format_plan_for_prompt(state.plan, 0)
    )
    state.messages.append({"role": "system", "content": formatted_system})
    state.messages.append({"role": "user", "content": f"Task: {task}"})

    # 2. REACT LOOP
    current_plan_idx = 0
    while check_step_limit(state.step_count, state.max_steps):
        state.step_count += 1
        print(f"\n--- [STEP {state.step_count}/{state.max_steps}] ---")

        # Refresh state in system prompt periodically
        state.messages[0]["content"] = SYSTEM_PROMPT_TEMPLATE.format(
            company_rules=json.dumps(state.company_context, indent=2),
            state_summary=state.to_summary(),
            plan_status=format_plan_for_prompt(state.plan, current_plan_idx)
        )

        # Call LLM
        response: LLMResponse = llm_module.call_llm(state.messages, tools=TOOL_SCHEMAS)
        thought = response.content or "(Executing tool call)"
        print(f"[THOUGHT] {thought.strip()}")

        # If LLM decides it is completely finished without tool calls
        if not response.tool_calls:
            print("[FINISH] Agent concluded task.")
            summary = thought
            evidence = {
                "facts": state.facts,
                "steps_taken": state.step_count,
                "retries": state.retries_used
            }
            logger.log_completion(summary, evidence)
            return {
                "status": "COMPLETED" if state.facts.get("verified") else "FINISHED_UNVERIFIED",
                "summary": summary,
                "run_id": run_id,
                "steps": state.step_count,
                "evidence": evidence
            }

        # Execute Tool Calls
        for tc in response.tool_calls:
            action_signature = f"{tc.name}({json.dumps(tc.arguments)})"

            # 3. GUARDRAIL CHECKS
            # Loop detection
            if detect_repeated_action(state.history, action_signature):
                print(f"[ALERT: GUARDRAIL] Loop detected: Agent attempted identical failing action twice. Breaking loop.")
                observation = "Error: Repeated action loop detected. You must change your parameters or query alternative sources."
                state.record_step(thought, action_signature, observation)
                logger.log_step(state.step_count, thought, action_signature, observation, state.facts)
                state.messages.append({"role": "user", "content": f"System Alert: {observation}"})
                break

            # Policy Approval check
            requires_approval, reason = check_action_approval_required(
                tc.name, tc.arguments, state.company_context
            )
            if requires_approval and not auto_approve:
                print(f"[APPROVAL REQUIRED] {reason}")
                approval_response = ask_human(f"Approval request for action {action_signature}: {reason}. Proceed? (approve/reject)")
                if "approve" not in approval_response.lower():
                    observation = f"Action cancelled: Human operator declined approval. Reason: {reason}"
                    state.record_step(thought, action_signature, observation)
                    logger.log_step(state.step_count, thought, action_signature, observation, state.facts)
                    state.messages.append({"role": "user", "content": f"Observation: {observation}"})
                    break

            # Automatically inject token if agent has it but omitted it
            if tc.name == "api_request" and state.facts.get("auth_token"):
                if not tc.arguments.get("token") and tc.arguments.get("path") != "/auth/login":
                    tc.arguments["token"] = state.facts["auth_token"]

            # 4. EXECUTE TOOL
            print(f"[ACTION] {tc.name} -> {tc.arguments}")
            observation = execute_tool_call(tc.name, tc.arguments)
            print(f"[OBSERVATION]\n{observation}\n")

            # 5. RESILIENCE & FAILURE RECOVERY
            # 5a. HTTP 401: Token expired or rejected -> Automatically re-authenticate and retry
            if "HTTP 401" in observation and tc.name == "api_request" and tc.arguments.get("path") != "/auth/login":
                print("[RECOVERY] Detected HTTP 401 Unauthorized / Token Expired. Automatically re-authenticating...")
                state.retries_used += 1
                auth_resp = execute_tool_call("api_request", {
                    "method": "POST",
                    "path": "/auth/login",
                    "json_body": {"username": "admin", "password": "secret_token_pass"}
                })
                extract_facts_from_observation(state, "api_request", {"path": "/auth/login"}, auth_resp)
                if state.facts.get("auth_token"):
                    print("[RECOVERY] Re-authentication successful. Retrying original request with new token...")
                    tc.arguments["token"] = state.facts["auth_token"]
                    observation = execute_tool_call(tc.name, tc.arguments)
                    print(f"[OBSERVATION (RETRY)]\n{observation}\n")

            # 5b. HTTP 429: Rate limited -> Parse Retry-After, apply backoff and retry (max 3)
            elif "HTTP 429" in observation and tc.name == "api_request":
                retry_wait = 2.0
                if "Retry-After:" in observation:
                    try:
                        part = observation.split("Retry-After:")[1].split("s]")[0].strip()
                        retry_wait = float(part)
                    except Exception:
                        retry_wait = 2.0
                print(f"[RECOVERY] Detected HTTP 429 Rate Limit. Backing off for {retry_wait}s...")
                state.retries_used += 1
                time.sleep(retry_wait)
                observation = execute_tool_call(tc.name, tc.arguments)
                print(f"[OBSERVATION (RETRY)]\n{observation}\n")

            # 5c. HTTP 500 / 503 / Timeout: Transient backend error -> Exponential backoff retry
            elif ("HTTP 500" in observation or "HTTP 503" in observation or "HTTP Timeout" in observation) and tc.name == "api_request":
                print("[RECOVERY] Detected transient server/network error. Backing off and retrying...")
                state.retries_used += 1
                time.sleep(1.5)
                observation = execute_tool_call(tc.name, tc.arguments)
                print(f"[OBSERVATION (RETRY)]\n{observation}\n")

            # 5d. HTTP 422: Validation Error -> Inject explicit instruction to LLM to fix payload
            elif "HTTP 422" in observation:
                print("[RECOVERY] Detected HTTP 422 Unprocessable Entity. Guiding agent to fix payload format.")
                state.retries_used += 1

            # 5e. HTTP 409: Duplicate Conflict
            elif "HTTP 409" in observation:
                print("[ALERT] Duplicate entry detected (HTTP 409). Recording conflict.")

            # Update working memory
            extract_facts_from_observation(state, tc.name, tc.arguments, observation)

            # Record step and audit log
            state.record_step(thought, action_signature, observation)
            logger.log_step(state.step_count, thought, action_signature, observation, state.facts)

            # Append to message history for ReAct continuity
            state.messages.append({
                "role": "assistant",
                "content": f"Thought: {thought}\nAction: {action_signature}"
            })
            state.messages.append({
                "role": "user",
                "content": f"Observation: {observation}"
            })

            # Check if this was an independent verification check
            if tc.name == "api_request" and tc.arguments.get("method") == "GET" and "/invoices/" in tc.arguments.get("path", ""):
                from agent.verifier import verify_invoice_record
                is_valid, verify_msg, details = verify_invoice_record(state.facts, observation)
                if is_valid:
                    print(f"[VERIFIER SUCCESS] {verify_msg}")
                    state.update_fact("verified", True)
                    current_plan_idx = len(state.plan)
                else:
                    print(f"[VERIFIER NOTICE] {verify_msg}")

            # Advance plan pointer
            if current_plan_idx < len(state.plan) - 1:
                current_plan_idx += 1

    # If step limit hit
    failure_msg = f"Task terminated: Exceeded maximum step limit ({state.max_steps})."
    print(f"\n[FAILED] {failure_msg}")
    logger.log_completion(failure_msg, {"facts": state.facts, "steps": state.step_count})
    return {
        "status": "FAILED_STEP_LIMIT",
        "summary": failure_msg,
        "run_id": run_id,
        "steps": state.step_count,
        "evidence": {"facts": state.facts}
    }
