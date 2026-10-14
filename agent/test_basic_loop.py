"""
Verification script for Phase 3: Tests the baseline tool-calling loop end-to-end.
"""

import os
from agent.loop import run_single_cycle

def test_basic_cycle():
    print("=" * 60)
    print("TESTING PHASE 3: BASIC AGENT TOOL-CALLING CYCLE")
    print("=" * 60)

    # Use mock provider so test runs offline deterministically
    os.environ["LLM_PROVIDER"] = "mock"

    task = "List the files in data/invoices so we can find Acme Cloud invoice."
    result = run_single_cycle(task)

    assert result["status"] == "success"
    assert result["step_count"] >= 1
    assert len(result["actions"]) > 0
    assert result["actions"][0]["tool"] == "list_files"
    assert "invoice_acme_cloud_oct2026.txt" in result["actions"][0]["observation"]

    print("\n>>> PHASE 3 BASIC AGENT LOOP VERIFICATION PASSED! <<<")

if __name__ == "__main__":
    test_basic_cycle()
