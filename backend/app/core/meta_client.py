"""Single Meta Model API client — reachability probe with model-listed verification.

Only this module talks to Meta. It never reads global settings (callers pass
explicit params) and never imports app.core.config (cycle avoidance — the
health router wires settings to these params).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import httpx

logger = logging.getLogger(__name__)

META_API_BASE_URL = "https://api.meta.ai/v1"
DEFAULT_META_MODEL = "muse-spark-1.3"
META_PROBE_TIMEOUT_S = 10.0
MAX_ERROR_CHARS = 200
CHAT_TIMEOUT_S = 120.0
QA_MAX_TOKENS = 4096
QA_TEMPERATURE = 0.0


class MetaAPIError(Exception):
    """A Meta chat-completion call failed (→ HTTP 502 at the router)."""

    def __init__(self, status_code: int | None, detail: str) -> None:
        self.status_code = status_code
        self.detail = detail
        super().__init__(str(self))

    def __str__(self) -> str:
        status = self.status_code if self.status_code is not None else "request failed"
        return f"Meta API chat completion failed: HTTP {status}: {self.detail}"


@dataclass
class ProbeResult:
    ok: bool
    error: str | None
    status_code: int | None


async def check_meta_reachability(
    api_key: str,
    model: str = DEFAULT_META_MODEL,
    *,
    base_url: str = META_API_BASE_URL,
    timeout_s: float = META_PROBE_TIMEOUT_S,
    client: httpx.AsyncClient | None = None,
) -> ProbeResult:
    """Probe Meta reachability and verify `model` is listed — no inference call.

    GETs `{base_url}/models` with Bearer auth, then checks the OpenAI-shaped
    `{"data": [{"id": ...}]}` body for `model`. Returns ok=False with a cause
    on any failure; never raises for remote conditions and never includes the
    key in errors or logs.
    """
    url = base_url.rstrip("/") + "/models"
    headers = {"Authorization": f"Bearer {api_key}"}
    owned_client = client is None
    http = client if client is not None else httpx.AsyncClient(timeout=timeout_s)
    try:
        try:
            response = await http.get(url, headers=headers)
        except httpx.TimeoutException:
            error = f"timed out after {timeout_s}s"
            logger.warning("meta probe failed: status=%s detail=%s", None, error)
            return ProbeResult(ok=False, error=error, status_code=None)
        except httpx.ConnectError as exc:
            error = f"connection failed: {exc}"
            logger.warning("meta probe failed: status=%s detail=%s", None, error)
            return ProbeResult(ok=False, error=error, status_code=None)
        except httpx.HTTPError as exc:
            error = str(exc)[:MAX_ERROR_CHARS]
            logger.warning("meta probe failed: status=%s detail=%s", None, error)
            return ProbeResult(ok=False, error=error, status_code=None)

        if response.status_code != 200:
            body = response.text[:MAX_ERROR_CHARS]
            error = f"Meta API models probe: HTTP {response.status_code}: {body}"
            logger.warning("meta probe failed: status=%s detail=%s", response.status_code, error)
            return ProbeResult(ok=False, error=error, status_code=response.status_code)

        try:
            payload = response.json()
        except ValueError:
            payload = None
        data = payload.get("data") if isinstance(payload, dict) else None
        if not isinstance(data, list):
            body = response.text[:MAX_ERROR_CHARS]
            error = f"unexpected /models response body: {body}"
            logger.warning("meta probe failed: status=%s detail=%s", 200, error)
            return ProbeResult(ok=False, error=error, status_code=200)

        listed = [e.get("id") for e in data if isinstance(e, dict)]
        if model not in listed:
            error = f"model {model} not listed by Meta API ({len(listed)} models returned)"
            logger.warning("meta probe failed: status=%s detail=%s", 200, error)
            return ProbeResult(ok=False, error=error, status_code=200)

        return ProbeResult(ok=True, error=None, status_code=200)
    finally:
        if owned_client:
            await http.aclose()


async def chat_completion(
    *,
    api_key: str,
    model: str = DEFAULT_META_MODEL,
    messages: list[dict[str, str]],
    max_tokens: int = QA_MAX_TOKENS,
    temperature: float = QA_TEMPERATURE,
    base_url: str = META_API_BASE_URL,
    timeout_s: float = CHAT_TIMEOUT_S,
    client: httpx.AsyncClient | None = None,
) -> str:
    """Run one OpenAI-shaped chat completion; return the content string.

    POSTs ``{base_url}/chat/completions`` with JSON ``response_format``.
    Raises ``MetaAPIError`` on every remote failure (transport, non-200,
    bad JSON, missing/empty choices); the key never appears in errors.
    """
    url = base_url.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    body = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature,
        "response_format": {"type": "json_object"},
    }
    owned_client = client is None
    http = client if client is not None else httpx.AsyncClient(timeout=timeout_s)
    try:
        try:
            response = await http.post(url, headers=headers, json=body)
        except httpx.TimeoutException:
            error = f"timed out after {timeout_s}s"
            logger.warning("meta chat failed: status=%s detail=%s", None, error)
            raise MetaAPIError(None, error) from None
        except httpx.HTTPError as exc:
            error = str(exc)[:MAX_ERROR_CHARS]
            logger.warning("meta chat failed: status=%s detail=%s", None, error)
            raise MetaAPIError(None, error) from None

        if response.status_code != 200:
            error = f"HTTP {response.status_code}: {response.text[:MAX_ERROR_CHARS]}"
            logger.warning("meta chat failed: status=%s detail=%s", response.status_code, error)
            raise MetaAPIError(response.status_code, error) from None

        try:
            payload = response.json()
        except ValueError:
            payload = None
        choices = payload.get("choices") if isinstance(payload, dict) else None
        content = None
        if isinstance(choices, list) and choices:
            message = choices[0].get("message") if isinstance(choices[0], dict) else None
            content = message.get("content") if isinstance(message, dict) else None
        if not isinstance(content, str) or not content:
            body_text = response.text[:MAX_ERROR_CHARS]
            error = f"unexpected chat response body: {body_text}"
            logger.warning("meta chat failed: status=%s detail=%s", 200, error)
            raise MetaAPIError(200, error) from None
        return content
    finally:
        if owned_client:
            await http.aclose()
