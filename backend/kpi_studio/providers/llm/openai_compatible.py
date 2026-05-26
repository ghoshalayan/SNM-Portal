"""OpenAI-compatible Chat Completions provider.

Works with:
  * **OpenAI** (default base_url ``https://api.openai.com/v1``)
  * **Cerebras** (``https://api.cerebras.ai/v1``)
  * **Ollama Cloud** (``https://ollama.com/v1``)
  * Anything else exposing ``/chat/completions`` with bearer-token auth.

httpx is already a project dep (used by tests + the host's HTTP client),
so this stays SDK-free.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Optional, Sequence

import httpx

from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProvider, LlmProviderError, LlmResult,
    LlmTool, LlmToolCall, LlmToolResult,
)

log = logging.getLogger(__name__)


class OpenAICompatibleProvider(LlmProvider):
    """OpenAI Chat Completions over HTTP. Synchronous; one request per call."""

    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 60.0,
        # ``name`` is purely for audit logs / debugging — defaults to the host.
        name: str = "openai",
        # Which JSON field to send the output cap under. OpenAI's newer
        # models (gpt-5*, o1, o3, ...) reject ``max_tokens`` and require
        # ``max_completion_tokens``; older models + most OpenAI-compat
        # providers (Cerebras, Ollama Cloud) still expect ``max_tokens``.
        # When ``None`` we infer from ``name`` and auto-swap on error.
        max_tokens_field: str | None = None,
        # Provider-specific extra HTTP headers (T-901). OpenRouter
        # recommends ``HTTP-Referer`` + ``X-Title`` for analytics +
        # better rate-limit fairness; other compats may have their own.
        # Empty / None = send no extras (current behaviour for OpenAI /
        # Cerebras / Ollama).
        extra_headers: Optional[dict[str, str]] = None,
        # Call-log identity metadata (2026-05-25). Passed when the
        # provider is built from a ``KpiLlmProviderConfig`` row; the
        # logger stamps these on every audit row so admins can filter
        # by provider config in the UI. ``None`` when built from env.
        provider_config_id: Optional[int] = None,
        provider_label: Optional[str] = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key is required")
        if not model:
            raise ValueError("model is required")
        self._api_key = api_key
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout_seconds
        self.name = name
        # Default: assume the modern field for OpenAI itself, the legacy
        # field for everything else. The retry logic in _post_with_token_swap
        # auto-corrects per provider runtime if we guess wrong.
        if max_tokens_field is None:
            max_tokens_field = (
                "max_completion_tokens" if name == "openai" else "max_tokens"
            )
        self._max_tokens_field = max_tokens_field
        self._extra_headers = dict(extra_headers) if extra_headers else {}
        self._provider_config_id = provider_config_id
        self._provider_label = provider_label

    def complete(
        self,
        messages: Sequence[LlmMessage],
        *,
        json_mode: bool = False,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> LlmResult:
        body: dict = {
            "model": self._model,
            "messages": [_serialize_message(m) for m in messages],
            "temperature": temperature,
        }
        if max_tokens is not None:
            body[self._max_tokens_field] = max_tokens
        if json_mode:
            # OpenAI / many compats accept response_format. Providers that don't
            # support it typically ignore the field — the user prompt should
            # also instruct "respond with JSON only" as a belt-and-braces.
            body["response_format"] = {"type": "json_object"}

        data, latency_ms = self._post_with_token_swap(body)

        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmProviderError(
                f"{self.name}: missing 'choices[0].message.content' in response"
            ) from exc

        if not isinstance(content, str):
            content = str(content)

        return LlmResult(
            text=content.strip(),
            model=data.get("model") or self._model,
            latency_ms=latency_ms,
            usage=data.get("usage") or {},
        )

    def complete_with_tools(
        self,
        messages: Sequence[LlmMessage],
        tools: Sequence[LlmTool],
        *,
        max_tokens: int | None = None,
        temperature: float = 0.2,
    ) -> LlmToolResult:
        body: dict = {
            "model": self._model,
            "messages": [_serialize_message(m) for m in messages],
            "temperature": temperature,
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    },
                }
                for t in tools
            ],
            "tool_choice": "auto",
        }
        if max_tokens is not None:
            body[self._max_tokens_field] = max_tokens

        data, latency_ms = self._post_with_token_swap(body)

        try:
            choice = data["choices"][0]
            message = choice["message"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LlmProviderError(
                f"{self.name}: missing 'choices[0].message' in response"
            ) from exc

        # Tool calls — when present, the orchestrator runs them and feeds
        # the results back. The raw assistant message must be preserved
        # verbatim so OpenAI can match tool_call_id on subsequent calls.
        raw_tool_calls = message.get("tool_calls") or []
        tool_calls: list[LlmToolCall] = []
        for tc in raw_tool_calls:
            try:
                fn = tc.get("function") or {}
                args_raw = fn.get("arguments") or "{}"
                args = json.loads(args_raw) if isinstance(args_raw, str) else (args_raw or {})
                tool_calls.append(LlmToolCall(
                    id=tc.get("id") or "",
                    name=fn.get("name") or "",
                    arguments=args if isinstance(args, dict) else {},
                ))
            except json.JSONDecodeError:
                # Model produced malformed JSON for arguments — preserve
                # the raw string under a sentinel key so the orchestrator
                # can surface a "model returned bad arguments" error.
                tool_calls.append(LlmToolCall(
                    id=tc.get("id") or "",
                    name=(tc.get("function") or {}).get("name") or "",
                    arguments={"__raw__": args_raw},
                ))

        content = message.get("content") or ""
        if not isinstance(content, str):
            content = str(content)

        return LlmToolResult(
            tool_calls=tool_calls,
            content=content.strip(),
            raw_assistant_message=message,
            model=data.get("model") or self._model,
            latency_ms=latency_ms,
            usage=data.get("usage") or {},
        )

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _post_with_token_swap(self, body: dict) -> tuple[dict, int]:
        """Wrap ``_post`` with a one-shot retry that swaps between
        ``max_tokens`` and ``max_completion_tokens`` when the provider
        complains about which field it accepts.

        Caches the working field on the instance so subsequent calls
        skip the round-trip cost.
        """
        try:
            return self._post(body)
        except LlmProviderError as exc:
            current = self._max_tokens_field
            other = (
                "max_completion_tokens" if current == "max_tokens" else "max_tokens"
            )
            # Only attempt the swap when:
            #   - the body actually carries a token-cap field, and
            #   - the error message references the *other* one as the fix.
            # OpenAI's exact wording: "Use 'max_completion_tokens' instead."
            # Cerebras-style providers tend to say "max_completion_tokens"
            # is unrecognised and to use "max_tokens".
            msg = str(exc)
            if current in body and other in msg:
                body[other] = body.pop(current)
                self._max_tokens_field = other
                return self._post(body)
            raise

    def _post(self, body: dict) -> tuple[dict, int]:
        """Shared POST → (parsed-json, latency_ms). Raises LlmProviderError
        on non-2xx, malformed JSON, or transport failure.

        Every round-trip is recorded to kpi_llm_call_log via call_logger.
        Failures are recorded too — admin can inspect them in the
        "Call log" tab without re-running the failing flow."""
        from datetime import datetime, timezone
        url = f"{self._base_url}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            **self._extra_headers,
        }
        started_at = datetime.now(timezone.utc)
        started = time.perf_counter()

        # Mine the model from the request body — accurate per-call even
        # when the same provider instance gets re-used for different
        # models (which shouldn't happen today but the call-log should
        # reflect what was actually sent).
        request_model = (body.get("model") if isinstance(body, dict) else None) \
            or self._model

        def _record(*, succeeded: bool, status: Optional[int],
                    response_body: Any, error: Optional[str]) -> None:
            # Lazy import — call_logger pulls in deps which lazy-resolve
            # the host's session factory; importing at module-load time
            # creates an import cycle during tests.
            from kpi_studio.services import call_logger
            call_logger.record(
                provider_kind=self.name,
                provider_label=self._provider_label,
                provider_config_id=self._provider_config_id,
                base_url=self._base_url,
                model=request_model,
                request_method="POST",
                request_path="/chat/completions",
                request_body=body,
                request_headers=headers,
                response_status=status,
                response_body=response_body,
                succeeded=succeeded,
                error=error,
                latency_ms=int((time.perf_counter() - started) * 1000),
                started_at=started_at,
            )

        try:
            with httpx.Client(timeout=self._timeout) as client:
                resp = client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            _record(succeeded=False, status=None, response_body=None,
                    error=f"{type(exc).__name__}: request timed out")
            raise LlmProviderError(f"{self.name}: request timed out") from exc
        except httpx.HTTPError as exc:
            _record(succeeded=False, status=None, response_body=None,
                    error=f"{type(exc).__name__}: {exc}")
            raise LlmProviderError(f"{self.name}: HTTP error: {exc}") from exc
        latency_ms = int((time.perf_counter() - started) * 1000)

        if resp.status_code >= 400:
            snippet = (resp.text or "")[:400]
            _record(
                succeeded=False,
                status=resp.status_code,
                response_body=resp.text,
                error=f"{resp.status_code} {resp.reason_phrase}: {snippet}",
            )
            raise LlmProviderError(
                f"{self.name}: {resp.status_code} {resp.reason_phrase}: {snippet}"
            )

        try:
            parsed = resp.json()
        except json.JSONDecodeError as exc:
            _record(
                succeeded=False,
                status=resp.status_code,
                response_body=resp.text,
                error="response was not JSON",
            )
            raise LlmProviderError(f"{self.name}: response was not JSON") from exc

        _record(
            succeeded=True,
            status=resp.status_code,
            response_body=parsed,
            error=None,
        )
        return parsed, latency_ms


def _serialize_message(m: LlmMessage) -> dict:
    """Turn an ``LlmMessage`` into the OpenAI wire shape.

    Three cases:
      * Plain text turn (system / user / assistant) → ``{role, content}``
      * Assistant turn that called tools → ``{role, content, tool_calls}``
      * Tool result reply → ``{role: "tool", tool_call_id, content}``

    The assistant-turn-with-tools case is built from the *raw* OpenAI
    message that ``complete_with_tools`` returned, not from this helper —
    callers append it directly. We still handle the shape here for
    completeness in case a caller hand-builds one.
    """
    out: dict = {"role": m.role, "content": m.content}
    if m.tool_calls:
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {
                    "name": tc.name,
                    "arguments": json.dumps(tc.arguments),
                },
            }
            for tc in m.tool_calls
        ]
    if m.tool_call_id is not None:
        out["tool_call_id"] = m.tool_call_id
    return out
