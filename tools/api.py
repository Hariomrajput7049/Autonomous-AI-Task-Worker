"""
API client tool for interacting with the internal mock ERP system.
Uses httpx to execute requests and returns trimmed, informative status and body.
Never dumps huge raw responses into the agent context.
"""

import os
import json
from typing import Optional, Dict, Any, Union
import httpx

API_BASE_URL = os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
MAX_BODY_CHARS = 1500

def api_request(
    method: str,
    path: str,
    json_body: Optional[Union[Dict[str, Any], str]] = None,
    token: Optional[str] = None,
    headers: Optional[Dict[str, str]] = None
) -> str:
    """
    Executes an HTTP request against the internal API.
    
    Args:
        method: HTTP method (GET, POST, PATCH, DELETE)
        path: Relative endpoint path (e.g. '/invoices', '/auth/login')
        json_body: Optional JSON dictionary or JSON string to send
        token: Optional Bearer authentication token
        headers: Optional custom headers
    
    Returns:
        A concise formatted summary of status code and response payload.
    """
    url = f"{API_BASE_URL.rstrip('/')}/{path.lstrip('/')}"
    req_headers = {"Content-Type": "application/json"}
    
    if token:
        req_headers["Authorization"] = f"Bearer {token}"
    if headers:
        req_headers.update(headers)

    parsed_body = None
    if json_body:
        if isinstance(json_body, str):
            try:
                parsed_body = json.loads(json_body)
            except json.JSONDecodeError:
                return f"Error: json_body is invalid JSON string: '{json_body}'"
        else:
            parsed_body = json_body

    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.request(
                method=method.upper(),
                url=url,
                json=parsed_body,
                headers=req_headers
            )
            
            # Format concise output
            status = resp.status_code
            try:
                resp_json = resp.json()
                body_str = json.dumps(resp_json, indent=2)
            except Exception:
                body_str = resp.text

            if len(body_str) > MAX_BODY_CHARS:
                body_str = body_str[:MAX_BODY_CHARS] + "\n...[TRUNCATED]"

            # Include retry header if present on 429
            retry_after = resp.headers.get("Retry-After")
            retry_info = f" [Retry-After: {retry_after}s]" if retry_after else ""

            return f"HTTP {status}{retry_info}\nBody: {body_str}"

    except httpx.ConnectError:
        return f"HTTP Connection Error: Could not connect to API server at {url}. Ensure mock_app is running."
    except httpx.TimeoutException:
        return f"HTTP Timeout Error: Request to {url} timed out."
    except Exception as e:
        return f"HTTP Error ({type(e).__name__}): {str(e)}"
