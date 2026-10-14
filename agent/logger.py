"""
JSONL Audit Logger for recording end-to-end agent trajectories.
Every step records: timestamp, step number, thought, tool action, observation, and state facts.
All sensitive secrets (bearer tokens, passwords) are automatically redacted.
"""

import os
import json
from datetime import datetime
from typing import Dict, Any

from agent.guardrails import redact_secrets

class AuditLogger:
    def __init__(self, run_id: str, log_dir: str = "logs"):
        self.run_id = run_id
        self.log_dir = log_dir
        os.makedirs(self.log_dir, exist_ok=True)
        self.filepath = os.path.join(self.log_dir, f"{run_id}.jsonl")

    def log_step(
        self,
        step: int,
        thought: str,
        action: str,
        observation: str,
        facts: Dict[str, Any]
    ):
        """Appends a redacted step entry to the run log."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "run_id": self.run_id,
            "step": step,
            "thought": redact_secrets(thought),
            "action": redact_secrets(action),
            "observation": redact_secrets(observation[:500]),
            "facts": {k: redact_secrets(str(v)) if v else None for k, v in facts.items()}
        }
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")

    def log_completion(self, summary: str, evidence: Dict[str, Any]):
        """Logs the final completion entry."""
        entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "run_id": self.run_id,
            "event": "TASK_COMPLETE",
            "summary": redact_secrets(summary),
            "evidence": {k: redact_secrets(str(v)) for k, v in evidence.items()}
        }
        with open(self.filepath, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry) + "\n")
