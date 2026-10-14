"""
Independent unit test suite for tools.
Runs without needing any LLM API key, verifying tool execution and registry dispatch.
"""

import os
from tools.files import list_files, read_file
from tools.human import ask_human, set_mock_human_response
from tools.api import api_request
from tools.registry import execute_tool_call, TOOL_SCHEMAS, TOOL_DISPATCH
import uvicorn
import threading
import time

def start_background_api():
    from mock_app.main import app
    config = uvicorn.Config(app=app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    time.sleep(1.5) # Wait for server startup
    return server

def run_tools_test():
    print("=" * 60)
    print("RUNNING TOOLS INDEPENDENT TEST SUITE")
    print("=" * 60)

    # 1. Test File Tools
    print("\n[1] Testing list_files()...")
    res_files = execute_tool_call("list_files", {"directory": "data/invoices"})
    print(res_files)
    assert "invoice_acme_cloud_oct2026.txt" in res_files, "Expected invoice file in listing"

    print("\n[2] Testing read_file()...")
    res_content = execute_tool_call("read_file", {"filepath": "data/invoices/invoice_acme_cloud_oct2026.txt"})
    print(f"Read {len(res_content)} characters. Snippet:\n{res_content[:150]}...")
    assert "Acme Cloud Solutions" in res_content
    assert "14,250.00" in res_content

    # 2. Test Human Tool
    print("\n[3] Testing ask_human() with mock hook...")
    set_mock_human_response(lambda q: "Approved by manager.")
    res_human = execute_tool_call("ask_human", {"question": "Approve $78,500?"})
    print(res_human)
    assert "Approved by manager" in res_human

    # 3. Test API Tool with live local background server
    print("\n[4] Starting background mock server to test api_request()...")
    start_background_api()

    print("[5] Testing api_request /auth/login...")
    auth_resp = execute_tool_call("api_request", {
        "method": "POST",
        "path": "/auth/login",
        "json_body": {"username": "admin", "password": "secret_token_pass"}
    })
    print(auth_resp)
    assert "HTTP 200" in auth_resp
    assert "access_token" in auth_resp

    import json
    lines = auth_resp.split("\n", 1)[1].replace("Body: ", "").strip()
    token = json.loads(lines)["access_token"]

    print("\n[6] Testing api_request /vendors with token...")
    vendors_resp = execute_tool_call("api_request", {
        "method": "GET",
        "path": "/vendors",
        "token": token
    })
    print(vendors_resp)
    assert "HTTP 200" in vendors_resp
    assert "Acme Cloud Solutions" in vendors_resp

    print("\n[7] Verifying Schema registry completeness...")
    assert len(TOOL_SCHEMAS) == len(TOOL_DISPATCH), f"Mismatch between schemas ({len(TOOL_SCHEMAS)}) and dispatchers ({len(TOOL_DISPATCH)})"
    print(f" -> All {len(TOOL_SCHEMAS)} tools registered and synchronized.")

    print("\n>>> ALL TOOLS TESTS PASSED SUCCESSFULLY! <<<")

if __name__ == "__main__":
    run_tools_test()
