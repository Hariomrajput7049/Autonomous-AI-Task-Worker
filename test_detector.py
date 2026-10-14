"""Quick unit test for _detect_task()"""
import sys, os
sys.path.insert(0, '.')
os.environ['LLM_PROVIDER'] = 'mock'
from agent.llm import _detect_task

tests = [
    ("List all vendors registered in the internal system.", "list_vendors"),
    ("Show me all registered vendors.", "list_vendors"),
    ("Which vendors do we have?", "list_vendors"),
    ("How many invoices are in the system?", "count_invoices"),
    ("Count all invoices in the system.", "count_invoices"),
    ("List all overdue invoices.", "list_overdue"),
    ("Show me overdue invoices.", "list_overdue"),
    ("What is the total of all invoices from all vendors?", "total_all_invoices"),
    ("Total of all invoices", "total_all_invoices"),
    ("Give me the sum of all invoices", "total_all_invoices"),
    ("Total of all invoices from Acme Cloud Solutions", "vendor_total_acme"),
    ("Total of invoices from Nexus Logistics Inc", "vendor_total_nexus"),
    ("Find the latest invoice from Acme Cloud Solutions, extract amount and due date, enter it into system.", "process_acme"),
    ("Find the latest invoice from Nexus Logistics Inc.", "process_nexus"),
    ("Find the latest invoice from Quantum Data Labs.", "process_quantum"),
    ("Find the latest invoice from Apex Office Supplies.", "process_apex"),
    ("Find the latest invoice from Skyline Telecom.", "process_skyline"),
]

passed = 0
for msg, expected in tests:
    result = _detect_task(msg)
    status = "PASS" if result == expected else "FAIL"
    if status == "PASS":
        passed += 1
    print(f"[{status}] \"{msg[:60]}\"")
    if status == "FAIL":
        print(f"       got={result}  expected={expected}")

print(f"\nScore: {passed}/{len(tests)} passed")
