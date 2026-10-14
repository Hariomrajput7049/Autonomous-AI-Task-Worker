"""
Configurable failure injection middleware / hook for testing resilience.
Controlled by environment variable `FAILURE_MODE` or dynamically via headers.

Supported failure modes:
- "none" / None: Normal operation
- "500": Occasional internal server error (simulated transient crash)
- "503": Service temporarily unavailable
- "401_expired": Rejects token as expired on first attempt, prompting re-authentication
- "429_rate_limit": Triggers HTTP 429 Too Many Requests with Retry-After header
- "slow_timeout": Delays response by N seconds to trigger client-side read timeout
"""

import os
import time
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse

# State counters for simulating transient (recoverable) failures
_STATE = {
    "expired_token_tested": False,
    "rate_limit_hits": 0,
    "server_error_hits": 0,
}

def reset_failure_state():
    """Resets the transient state counters (useful between eval runs)."""
    _STATE["expired_token_tested"] = False
    _STATE["rate_limit_hits"] = 0
    _STATE["server_error_hits"] = 0


async def check_injected_failures(request: Request, current_user_token: Optional[str] = None):
    """
    Checks if a simulated failure should be triggered based on:
    1. Environment variable FAILURE_MODE
    2. Dynamic header X-Failure-Mode (for individual test cases)
    """
    mode = request.headers.get("X-Failure-Mode", os.getenv("FAILURE_MODE", "none")).lower()

    if mode == "none" or not mode:
        return

    # 1. Simulated 500 Internal Server Error (Transient: fails once, then succeeds on retry)
    if mode == "500_transient":
        if _STATE["server_error_hits"] < 1:
            _STATE["server_error_hits"] += 1
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail={"error": "DatabaseConnectionTimeout", "message": "Internal transient database timeout. Please retry."}
            )

    elif mode == "500":
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={"error": "InternalServerError", "message": "Persistent internal system failure."}
        )

    # 2. Simulated 503 Service Unavailable
    elif mode == "503":
        if _STATE["server_error_hits"] < 1:
            _STATE["server_error_hits"] += 1
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail={"error": "ServiceUnavailable", "message": "Downstream ERP service temporarily unavailable."}
            )

    # 3. Simulated 429 Rate Limit (Agent should parse Retry-After header and wait)
    elif mode == "429":
        if _STATE["rate_limit_hits"] < 1:
            _STATE["rate_limit_hits"] += 1
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"error": "RateLimitExceeded", "message": "Too many requests. Please throttle your queries."},
                headers={"Retry-After": "2"}
            )

    # 4. Simulated 401 Expired Token (Only triggers once on authenticated routes, forcing re-login)
    elif mode == "401_expired" and request.url.path != "/auth/login":
        if not _STATE["expired_token_tested"]:
            _STATE["expired_token_tested"] = True
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={"error": "TokenExpired", "message": "Bearer token has expired. Please re-authenticate at /auth/login."}
            )

    # 5. Simulated Timeout
    elif mode == "slow_timeout":
        time.sleep(3.5)
