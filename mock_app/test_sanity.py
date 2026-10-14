"""
Quick sanity check for the mock_app before launching uvicorn.
Validates database initialization, tables, and mock endpoints using FastAPI TestClient.
"""
from fastapi.testclient import TestClient
from mock_app.main import app

def run_sanity_check():
    client = TestClient(app)
    
    # 1. Test Login
    print("[1] Testing /auth/login...")
    login_resp = client.post("/auth/login", json={"username": "admin", "password": "secret_token_pass"})
    assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
    token = login_resp.json()["access_token"]
    print(" -> Auth successful. Token received.")
    
    headers = {"Authorization": f"Bearer {token}"}
    
    # 2. Test Vendors
    print("[2] Testing /vendors...")
    vendors_resp = client.get("/vendors", headers=headers)
    assert vendors_resp.status_code == 200, f"Vendors failed: {vendors_resp.text}"
    vendors = vendors_resp.json()
    assert len(vendors) >= 5, f"Expected 5 initial vendors, got {len(vendors)}"
    print(f" -> Found {len(vendors)} vendors: {[v['name'] for v in vendors]}")
    
    # 3. Test Strict Date Validation (422 error check)
    print("[3] Testing 422 error rejection on bad date format...")
    bad_payload = {
        "vendor": "Acme Cloud Solutions",
        "amount": 1000.0,
        "due_date": "15-11-2026", # Invalid! Needs YYYY-MM-DD
        "currency": "USD"
    }
    bad_resp = client.post("/invoices", json=bad_payload, headers=headers)
    assert bad_resp.status_code == 422, f"Expected 422, got {bad_resp.status_code}: {bad_resp.text}"
    print(" -> Successfully rejected invalid date with HTTP 422.")
    
    # 4. Test Valid Invoice Creation
    print("[4] Testing valid POST /invoices...")
    good_payload = {
        "vendor": "Acme Cloud Solutions",
        "amount": 14250.0,
        "due_date": "2026-11-15",
        "currency": "USD"
    }
    good_resp = client.post("/invoices", json=good_payload, headers=headers)
    assert good_resp.status_code == 201, f"Expected 201, got {good_resp.status_code}: {good_resp.text}"
    created_id = good_resp.json()["id"]
    print(f" -> Created invoice ID {created_id}.")
    
    # 5. Test Duplicate Detection (409 Conflict check)
    print("[5] Testing duplicate invoice rejection (HTTP 409)...")
    dup_resp = client.post("/invoices", json=good_payload, headers=headers)
    assert dup_resp.status_code == 409, f"Expected 409, got {dup_resp.status_code}: {dup_resp.text}"
    print(" -> Successfully detected duplicate and returned HTTP 409.")
    
    # 6. Test GET by ID (Verification endpoint)
    print("[6] Testing GET /invoices/{id}...")
    verify_resp = client.get(f"/invoices/{created_id}", headers=headers)
    assert verify_resp.status_code == 200, f"Verification GET failed: {verify_resp.text}"
    assert verify_resp.json()["amount"] == 14250.0
    print(" -> Successfully verified created record.")
    
    # Clean up
    client.post("/system/reset")
    print("\n>>> ALL PHASE 1 SANITY CHECKS PASSED! <<<")

if __name__ == "__main__":
    run_sanity_check()
