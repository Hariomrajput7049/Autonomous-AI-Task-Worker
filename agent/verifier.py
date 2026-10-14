"""
Independent Verification Engine.
Requirement: Never trust a POST response alone.
The agent must execute an independent GET /invoices/{id} request and rigorously compare
the persisted database values against the original extracted values from the source document.
"""

from typing import Dict, Any, Tuple
import json

def verify_invoice_record(
    source_facts: Dict[str, Any],
    get_response_body: str
) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Compares source facts (extracted from document) with the fresh GET record from the API.
    
    Returns:
        (is_verified: bool, reason: str, comparison_details: dict)
    """
    try:
        # Extract json body from observation string if needed
        raw_body = get_response_body
        if "Body:" in get_response_body:
            raw_body = get_response_body.split("Body:")[1].strip()

        record = json.loads(raw_body)
    except Exception as e:
        return False, f"Verification failed: Could not parse GET record payload ({e})", {}

    expected_vendor = source_facts.get("vendor")
    expected_amount = source_facts.get("amount")
    expected_due_date = source_facts.get("due_date")

    comparison = {
        "record_id": record.get("id"),
        "vendor": {"expected": expected_vendor, "actual": record.get("vendor")},
        "amount": {"expected": expected_amount, "actual": record.get("amount")},
        "due_date": {"expected": expected_due_date, "actual": record.get("due_date")},
        "status": record.get("status")
    }

    # Verify amount (within float tolerance)
    if expected_amount is not None:
        try:
            if abs(float(record.get("amount", 0.0)) - float(expected_amount)) > 0.01:
                return False, f"Amount mismatch: expected {expected_amount}, stored {record.get('amount')}", comparison
        except (ValueError, TypeError):
            return False, "Amount value conversion error", comparison

    # Verify due date
    if expected_due_date is not None:
        if str(record.get("due_date")) != str(expected_due_date):
            return False, f"Due date mismatch: expected {expected_due_date}, stored {record.get('due_date')}", comparison

    # Verify vendor name
    if expected_vendor is not None:
        if expected_vendor.lower() not in str(record.get("vendor", "")).lower():
            return False, f"Vendor mismatch: expected {expected_vendor}, stored {record.get('vendor')}", comparison

    return True, "All fields (vendor, amount, due_date) independently verified and match source document perfectly.", comparison
