"""OpenAI-compatible provider — token-field auto-swap (Phase A7+).

Newer OpenAI models (gpt-5*, o1, o3, ...) reject ``max_tokens`` and
require ``max_completion_tokens``. Older models + most compats are
the other way round. The provider should detect the parameter
mismatch and swap+retry once, caching the working field on the
instance so subsequent calls skip the round-trip.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

from kpi_studio.providers.llm.base import (
    LlmMessage, LlmProviderError, LlmTool,
)
from kpi_studio.providers.llm.openai_compatible import OpenAICompatibleProvider


class _FakePostHarness:
    """Replaces the provider's ``_post`` so we can assert on the body
    field that was sent and steer the response per call."""

    def __init__(self, *, fail_on_field: str | None = None):
        # When set, calls that include this body field will raise the
        # mirror-image OpenAI error. ``None`` = always succeed.
        self.fail_on_field = fail_on_field
        self.bodies: list[dict] = []

    def __call__(self, body: dict):
        # Snapshot the body before potentially mutating on the next call.
        self.bodies.append({**body})
        if self.fail_on_field and self.fail_on_field in body:
            other = (
                "max_completion_tokens"
                if self.fail_on_field == "max_tokens"
                else "max_tokens"
            )
            raise LlmProviderError(
                f"openai: 400 Bad Request: Unsupported parameter: "
                f"'{self.fail_on_field}' is not supported with this model. "
                f"Use '{other}' instead."
            )
        # Minimal "happy" payload for both complete + complete_with_tools.
        return {
            "choices": [{"message": {"content": "ok", "role": "assistant"}}],
            "model": body.get("model", "stub"),
            "usage": {"total_tokens": 5},
        }, 7


class DefaultsByProviderName(unittest.TestCase):
    def test_openai_defaults_to_max_completion_tokens(self):
        p = OpenAICompatibleProvider(api_key="k", model="m", name="openai")
        self.assertEqual(p._max_tokens_field, "max_completion_tokens")

    def test_compat_providers_default_to_max_tokens(self):
        for name in ("cerebras", "ollama_cloud", "custom"):
            p = OpenAICompatibleProvider(api_key="k", model="m", name=name)
            self.assertEqual(
                p._max_tokens_field, "max_tokens",
                f"name={name!r} should default to legacy field",
            )

    def test_explicit_override_wins(self):
        p = OpenAICompatibleProvider(
            api_key="k", model="m", name="openai",
            max_tokens_field="max_tokens",
        )
        self.assertEqual(p._max_tokens_field, "max_tokens")


class SwapBehaviour(unittest.TestCase):
    def test_swap_when_first_field_rejected(self):
        """OpenAI rejects ``max_tokens`` → swap to ``max_completion_tokens`` + retry."""
        p = OpenAICompatibleProvider(
            api_key="k", model="m", name="cerebras",  # defaults to max_tokens
        )
        harness = _FakePostHarness(fail_on_field="max_tokens")
        with patch.object(p, "_post", side_effect=harness):
            r = p.complete([LlmMessage(role="user", content="hi")], max_tokens=128)

        # Two calls: first with max_tokens (rejected), second with the swap.
        self.assertEqual(len(harness.bodies), 2)
        self.assertIn("max_tokens", harness.bodies[0])
        self.assertIn("max_completion_tokens", harness.bodies[1])
        self.assertNotIn("max_tokens", harness.bodies[1])
        # The swap is cached for next time.
        self.assertEqual(p._max_tokens_field, "max_completion_tokens")
        self.assertEqual(r.text, "ok")

    def test_swap_other_direction(self):
        """Compat that doesn't know ``max_completion_tokens`` → swap back."""
        p = OpenAICompatibleProvider(
            api_key="k", model="m", name="openai",  # defaults to max_completion_tokens
        )
        harness = _FakePostHarness(fail_on_field="max_completion_tokens")
        with patch.object(p, "_post", side_effect=harness):
            r = p.complete([LlmMessage(role="user", content="hi")], max_tokens=128)

        self.assertIn("max_completion_tokens", harness.bodies[0])
        self.assertIn("max_tokens", harness.bodies[1])
        self.assertEqual(p._max_tokens_field, "max_tokens")
        self.assertEqual(r.text, "ok")

    def test_no_swap_on_unrelated_error(self):
        """Errors unrelated to token-field naming should NOT trigger a swap."""
        p = OpenAICompatibleProvider(api_key="k", model="m", name="openai")

        def _post(body):
            raise LlmProviderError("openai: 401 Unauthorized")

        with patch.object(p, "_post", side_effect=_post):
            with self.assertRaises(LlmProviderError) as cm:
                p.complete([LlmMessage(role="user", content="hi")], max_tokens=128)
        self.assertIn("Unauthorized", str(cm.exception))
        # Field unchanged.
        self.assertEqual(p._max_tokens_field, "max_completion_tokens")

    def test_subsequent_calls_skip_the_round_trip(self):
        """After the first swap, subsequent calls send only the right field."""
        p = OpenAICompatibleProvider(api_key="k", model="m", name="cerebras")
        harness = _FakePostHarness(fail_on_field="max_tokens")
        with patch.object(p, "_post", side_effect=harness):
            p.complete([LlmMessage(role="user", content="hi")], max_tokens=128)
            p.complete([LlmMessage(role="user", content="hi again")], max_tokens=128)

        # First call: 2 round trips (failed + retry). Second call: 1.
        self.assertEqual(len(harness.bodies), 3)
        self.assertIn("max_completion_tokens", harness.bodies[2])
        self.assertNotIn("max_tokens", harness.bodies[2])

    def test_swap_also_works_for_complete_with_tools(self):
        p = OpenAICompatibleProvider(api_key="k", model="m", name="cerebras")
        harness = _FakePostHarness(fail_on_field="max_tokens")
        tools = [LlmTool(name="t", description="d", parameters={"type": "object"})]
        with patch.object(p, "_post", side_effect=harness):
            r = p.complete_with_tools(
                [LlmMessage(role="user", content="hi")],
                tools, max_tokens=64,
            )
        self.assertEqual(len(harness.bodies), 2)
        self.assertIn("max_tokens", harness.bodies[0])
        self.assertIn("max_completion_tokens", harness.bodies[1])
        self.assertEqual(r.content, "ok")


if __name__ == "__main__":
    unittest.main()
