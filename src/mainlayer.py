"""
Mainlayer billing client.

Mainlayer is the pay-per-call billing layer for AI APIs.
Base URL: https://api.mainlayer.fr
Auth:     Authorization: Bearer <api_key>

This module provides:
- `verify_payment`  — check that an inbound request has a valid Mainlayer
                      payment token and that the correct amount was charged.
- `record_usage`    — notify Mainlayer that a call was successfully served
                      (used for metering / analytics).

In development mode (MAINLAYER_DEV_MODE=true) all calls are no-ops so the
API can be exercised without a live Mainlayer account.
"""
import logging
import os
from typing import Optional

import httpx
from fastapi import HTTPException, Request, status

logger = logging.getLogger(__name__)

MAINLAYER_BASE_URL = os.getenv("MAINLAYER_BASE_URL", "https://api.mainlayer.fr")
MAINLAYER_API_KEY = os.getenv("MAINLAYER_API_KEY", "")
DEV_MODE = os.getenv("MAINLAYER_DEV_MODE", "false").lower() == "true"

# Endpoint prices in USD
PRICES: dict[str, float] = {
    "/summarize": 0.002,
    "/summarize/batch": 0.0015,
    "/summarize/url": 0.003,
}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_payment_token(request: Request) -> Optional[str]:
    """Extract the Mainlayer payment token from the request headers."""
    return request.headers.get("X-Mainlayer-Token") or request.headers.get("x-mainlayer-token")


async def _call_mainlayer(method: str, path: str, payload: dict) -> dict:
    """Make an authenticated call to the Mainlayer API."""
    if not MAINLAYER_API_KEY:
        raise RuntimeError("MAINLAYER_API_KEY is not configured")

    url = f"{MAINLAYER_BASE_URL}{path}"
    headers = {
        "Authorization": f"Bearer {MAINLAYER_API_KEY}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.request(method, url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def verify_payment(request: Request, endpoint: str) -> None:
    """
    Verify that the caller has a valid Mainlayer payment token authorising
    payment for *endpoint*.

    Raises HTTP 402 if payment is required but not present or invalid.
    Raises HTTP 500 if the Mainlayer API is unreachable (dev mode bypasses).
    """
    if DEV_MODE:
        logger.debug("DEV_MODE: skipping Mainlayer payment verification for %s", endpoint)
        return

    token = _get_payment_token(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "payment_required",
                "message": (
                    "A valid Mainlayer payment token is required. "
                    "Obtain one at https://mainlayer.fr and pass it in the "
                    "X-Mainlayer-Token header."
                ),
                "price_usd": PRICES.get(endpoint, 0.0),
                "docs": "https://docs.mainlayer.fr/quickstart",
            },
        )

    price = PRICES.get(endpoint, 0.0)
    try:
        result = await _call_mainlayer(
            "POST",
            "/v1/verify",
            {
                "token": token,
                "endpoint": endpoint,
                "amount_usd": price,
            },
        )
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 402:
            raise HTTPException(
                status_code=status.HTTP_402_PAYMENT_REQUIRED,
                detail={
                    "error": "payment_rejected",
                    "message": "Mainlayer rejected the payment token.",
                    "price_usd": price,
                },
            ) from exc
        logger.error("Mainlayer verification error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing service temporarily unavailable. Please retry.",
        ) from exc
    except Exception as exc:
        logger.error("Unexpected Mainlayer error: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing service temporarily unavailable. Please retry.",
        ) from exc

    if not result.get("valid"):
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail={
                "error": "payment_invalid",
                "message": result.get("message", "Payment token is not valid."),
                "price_usd": price,
            },
        )


async def record_usage(
    endpoint: str,
    token: Optional[str],
    metadata: Optional[dict] = None,
) -> None:
    """
    Record a successful API call with Mainlayer for metering.

    Errors are logged but not re-raised — the caller already received their
    response and usage recording is best-effort.
    """
    if DEV_MODE:
        logger.debug("DEV_MODE: skipping Mainlayer usage recording for %s", endpoint)
        return

    if not token:
        return

    payload: dict = {
        "token": token,
        "endpoint": endpoint,
        "amount_usd": PRICES.get(endpoint, 0.0),
    }
    if metadata:
        payload["metadata"] = metadata

    try:
        await _call_mainlayer("POST", "/v1/usage", payload)
    except Exception as exc:
        logger.warning("Failed to record Mainlayer usage for %s: %s", endpoint, exc)
