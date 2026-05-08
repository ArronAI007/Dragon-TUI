"""Structured error types + httpx-to-friendly mapping.

All user-facing exceptions should subclass TUIError so the app
can render a clean message instead of a raw stack trace.
"""

from __future__ import annotations


# ── Exception hierarchy ────────────────────────────────

class TUIError(Exception):
    """Base for all user-facing errors in the TUI."""
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


class APIError(TUIError):
    """API returned a non-2xx status."""


class RateLimitError(APIError):
    """HTTP 429 — too many requests."""


class AuthError(APIError):
    """HTTP 401 / 403 — bad or expired key."""


class ServerError(APIError):
    """HTTP 5xx — upstream outage."""


class NetworkError(TUIError):
    """Connection refused / DNS failure / no internet."""


class StreamInterrupted(TUIError):
    """SSE stream broke mid-response."""


class TimeoutError(TUIError):
    """Request exceeded the timeout."""


class ContentFilterError(APIError):
    """Response blocked by content filter."""


# ── Classifier ──────────────────────────────────────────

def classify(exc: Exception) -> TUIError:
    """Convert a raw exception into a user-friendly TUIError.

    Handles httpx errors, JSON decode errors, and generic exceptions.
    """
    import httpx

    # Already a TUIError — pass through
    if isinstance(exc, TUIError):
        return exc

    # ── httpx errors ────────────────────────────────
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        body = ""
        try:
            body = exc.response.text[:300]
        except Exception:
            pass

        if status == 429:
            return RateLimitError(
                "Rate limited — please wait a moment and try again.",
                retryable=True,
            )
        if status in (401, 403):
            return AuthError(
                f"Authentication failed (HTTP {status}). Check your API key."
            )
        if status == 402:
            return APIError(
                "Insufficient balance. Please top up your account.",
                retryable=False,
            )
        if 500 <= status < 600:
            return ServerError(
                f"API server error (HTTP {status}). Try again shortly.",
                retryable=True,
            )
        if status == 400:
            # Try to extract message from response body
            detail = _extract_detail(body)
            return APIError(
                f"Bad request (HTTP 400){': ' + detail if detail else ''}.",
                retryable=False,
            )
        return APIError(f"API error (HTTP {status})", retryable=(status >= 500))

    if isinstance(exc, httpx.ConnectError):
        return NetworkError(
            "Cannot connect to API. Check your network or base URL.",
            retryable=True,
        )
    if isinstance(exc, httpx.ReadError):
        return NetworkError(
            "Connection lost while reading response.",
            retryable=True,
        )
    if isinstance(exc, httpx.TimeoutException):
        return TimeoutError(
            "Request timed out. The model may be overloaded — try again.",
            retryable=True,
        )
    if isinstance(exc, httpx.RemoteProtocolError):
        return StreamInterrupted(
            "Response stream was interrupted. Try again.",
            retryable=True,
        )

    # ── Generic ─────────────────────────────────────
    msg = str(exc) or type(exc).__name__
    return TUIError(f"Unexpected error: {msg}", retryable=False)


def _extract_detail(body: str) -> str:
    """Try to pull a readable message from an error response body."""
    import json
    try:
        data = json.loads(body)
        if isinstance(data, dict):
            return data.get("error", {}).get("message", "")
    except Exception:
        pass
    return body[:120]
