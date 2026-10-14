"""
Memory and State Management for the Autonomous AI Task Worker.
Maintains:
- Structured `facts` (extracted vendor, amount, due date, auth token, created invoice id)
- Compact conversation history (prunes large tool outputs so context does not blow up)
- Company context loading from data/company_context.json
"""

import os
import json
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional

@dataclass
class AgentState:
    task: str
    run_id: str
    company_context: Dict[str, Any] = field(default_factory=dict)
    
    # Structured working memory
    facts: Dict[str, Any] = field(default_factory=lambda: {
        "vendor": None,
        "amount": None,
        "due_date": None,
        "currency": "USD",
        "invoice_file": None,
        "auth_token": None,
        "created_invoice_id": None,
        "verified": False,
    })
    
    plan: List[str] = field(default_factory=list)
    step_count: int = 0
    max_steps: int = 15
    retries_used: int = 0
    
    # Audit log of actions
    history: List[Dict[str, Any]] = field(default_factory=list)
    messages: List[Dict[str, Any]] = field(default_factory=list)

    def record_step(self, thought: str, action: str, observation: str):
        self.step_count += 1
        record = {
            "step": self.step_count,
            "thought": thought,
            "action": action,
            "observation": observation[:500] # store compact summary
        }
        self.history.append(record)

    def update_fact(self, key: str, value: Any):
        self.facts[key] = value

    def to_summary(self) -> str:
        """Returns a concise summary of current facts for LLM state priming."""
        return (
            f"Facts Known: "
            f"Vendor={self.facts.get('vendor')}, "
            f"Amount={self.facts.get('amount')}, "
            f"Due Date={self.facts.get('due_date')}, "
            f"File={self.facts.get('invoice_file')}, "
            f"Invoice ID={self.facts.get('created_invoice_id')}, "
            f"Verified={self.facts.get('verified')}"
        )


def load_company_context(filepath: str = "data/company_context.json") -> Dict[str, Any]:
    """Loads operational guidelines and approval thresholds."""
    if not os.path.exists(filepath):
        return {}
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Warning: could not load company context from {filepath}: {e}")
        return {}
