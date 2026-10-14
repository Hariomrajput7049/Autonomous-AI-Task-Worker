"""
Command-Line Interface for the Autonomous AI Task Worker.
Usage:
    python run_worker.py --task "Find the latest invoice from Acme Cloud Solutions, extract amount and due date, enter it into our internal system, and tell me once it is done."
    python run_worker.py --task "List all vendors registered in the company system"
    python run_worker.py --task "How many invoices are in the system?"
"""

import argparse
import sys
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Auto-start mock ERP server in background (same as evals do)
# This means you never need a separate terminal for the server
from tools.test_tools import start_background_api
print("[SETUP] Starting mock ERP server in background...")
start_background_api()
print("[SETUP] Mock ERP server ready at http://127.0.0.1:8000")

from agent.loop import run_agent_worker

def main():
    parser = argparse.ArgumentParser(description="Autonomous AI Task Worker CLI")
    parser.add_argument(
        "--task",
        type=str,
        default="Find the latest invoice from Acme Cloud Solutions, extract the amount and due date, enter it into our internal system, and tell me once it is done.",
        help="Natural language task prompt for the worker"
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=15,
        help="Maximum allowed execution steps"
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Automatically approve actions exceeding policy thresholds (for headless runs)"
    )

    args = parser.parse_args()

    print("======================================================================")
    print("           AUTONOMOUS AI TASK WORKER - RUNNER")
    print("======================================================================")
    print(f"Task: {args.task}")
    print(f"Provider: {os.getenv('LLM_PROVIDER', 'mock')}")
    print("======================================================================\n")

    result = run_agent_worker(
        task=args.task,
        max_steps=args.max_steps,
        auto_approve=args.auto_approve
    )

    print("\n" + "=" * 70)
    print("                    FINAL OUTCOME SUMMARY")
    print("=" * 70)
    print(f"Status:      {result['status']}")
    print(f"Steps Taken: {result['steps']}")
    print(f"Run ID:      {result['run_id']}")
    print(f"Summary:     {result['summary']}")
    print(f"Evidence:    {result['evidence']}")
    print("=" * 70)

if __name__ == "__main__":
    main()
