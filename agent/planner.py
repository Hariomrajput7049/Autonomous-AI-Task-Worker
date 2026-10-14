"""
Planner module for the Autonomous AI Task Worker.
Handles:
1. Goal Understanding: Restating the goal, identifying missing entities and ambiguities.
2. Initial Plan Generation: 3 to 6 structured, actionable steps.
3. Plan Adaptation: Dynamically updating the plan based on new tool observations.
"""

from typing import List, Dict, Any, Optional
import json

from agent.llm import call_llm, LLMResponse

PLANNER_SYSTEM_PROMPT = """You are the Senior Planning Engine for an Autonomous AI Task Worker.
Given a user task and company operating rules, your job is to:
1. Restate the high-level goal clearly.
2. Identify any missing information or potential ambiguities.
3. Formulate an initial, concrete execution plan of 3 to 6 actionable steps.

Output strictly valid JSON with this format:
{
  "understood_goal": "<Restated goal in 1-2 clear sentences>",
  "missing_info": ["<List any missing items, or empty list if none>"],
  "initial_plan": [
    "Step 1: Discover documents in invoices folder",
    "Step 2: Read target invoice and extract vendor, amount, and due date",
    "Step 3: Authenticate with company ERP API to acquire bearer token",
    "Step 4: Check for duplicates or register invoice",
    "Step 5: Independently verify created record"
  ]
}
"""

def generate_initial_plan(task: str, company_rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Decomposes a user task into an initial 3-6 step plan.
    """
    messages = [
        {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
        {"role": "user", "content": f"User Task: {task}\nCompany Rules: {json.dumps(company_rules, indent=2)}"}
    ]

    try:
        resp = call_llm(messages, tools=None)
        # Attempt to parse json from content
        raw = resp.content or "{}"
        # Strip potential markdown code blocks
        if "```json" in raw:
            raw = raw.split("```json")[1].split("```")[0].strip()
        elif "```" in raw:
            raw = raw.split("```")[1].split("```")[0].strip()
        plan_data = json.loads(raw)
        return plan_data
    except Exception:
        # Fallback deterministic structured plan
        return {
            "understood_goal": f"Execute the requested operation: {task}",
            "missing_info": [],
            "initial_plan": [
                "Step 1: Discover available documents in repository",
                "Step 2: Read target invoice and extract required fields",
                "Step 3: Authenticate with corporate API to acquire access token",
                "Step 4: Check for duplicates and create invoice record",
                "Step 5: Independently query the API to verify record integrity"
            ]
        }


def format_plan_for_prompt(plan_steps: List[str], current_step_index: int = 0) -> str:
    """Formats current execution plan into readable checklist for the agent context."""
    formatted = []
    for idx, step in enumerate(plan_steps):
        status = "[DONE]" if idx < current_step_index else ("[CURRENT]" if idx == current_step_index else "[TODO]")
        formatted.append(f"{status} {step}")
    return "\n".join(formatted)
