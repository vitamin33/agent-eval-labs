"""Model access, behind one interface with two implementations.

`AnthropicProvider` calls the real API. `MockProvider` produces seeded,
deterministic responses so the whole 100-record matrix can run offline.

Dry-run output is SYNTHETIC. Records carry `provider: "mock"` and gate G4
refuses to accept them as experimental results.
"""

from __future__ import annotations

import hashlib
import json
import random
import time
from dataclasses import dataclass, field
from typing import Any

VERDICT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["correct", "wrong"]},
        "confidence": {"type": "integer", "minimum": 0, "maximum": 100},
        "revised": {"type": ["string", "null"]},
    },
    "required": ["verdict", "confidence", "revised"],
    "additionalProperties": False,
}


@dataclass
class CallResult:
    text: str
    input_tokens: int
    output_tokens: int
    model: str
    latency_s: float
    stop_reason: str | None = None
    structured: bool = False
    error: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)


class AnthropicProvider:
    """Direct Anthropic SDK. No agent framework, no orchestrator."""

    name = "anthropic"

    def __init__(self, model: str, max_tokens: int, sampling: dict[str, Any]):
        import anthropic  # imported here so dry-run works without the package

        self._anthropic = anthropic
        self.client = anthropic.Anthropic()
        self.model = model
        self.max_tokens = max_tokens
        self.sampling = sampling

    def complete(
        self,
        system: str,
        messages: list[dict],
        *,
        schema: dict | None = None,
        trace: dict | None = None,
    ) -> CallResult:
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": messages,
            **self.sampling,
        }
        structured = False
        if schema is not None:
            kwargs["output_config"] = {"format": {"type": "json_schema", "schema": schema}}
            structured = True

        t0 = time.perf_counter()
        try:
            response = self.client.messages.create(**kwargs)
        except self._anthropic.BadRequestError as exc:
            # Structured output may be unavailable for this model. Fall back to
            # a plain call and let the tolerant parser handle the text; the
            # record keeps `structured=False` so the difference stays visible.
            if schema is None:
                raise
            kwargs.pop("output_config")
            structured = False
            t0 = time.perf_counter()
            response = self.client.messages.create(**kwargs)
        latency = time.perf_counter() - t0

        text = "".join(b.text for b in response.content if b.type == "text")
        return CallResult(
            text=text,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
            latency_s=latency,
            stop_reason=response.stop_reason,
            structured=structured,
        )


# --------------------------------------------------------------------------- #
# mock
# --------------------------------------------------------------------------- #

_FENCE_STYLES = [
    "```python\n{code}\n```",
    "```\n{code}\n```",
    "Here is the implementation:\n\n```python\n{code}\n```\n\nThis handles the edge cases.",
    "{code}",
]
_SQL_FENCE_STYLES = [
    "```sql\n{code}\n```",
    "```\n{code}\n```",
    "The query:\n\n```sql\n{code}\n```",
]
_REFUSALS = [
    "I can't help with that request.",
    "I'm unable to complete this task as specified.",
]


class MockProvider:
    """Seeded, offline responses. Same seed in, byte-identical records out."""

    name = "mock"

    # Response mix, chosen so dry-run baseline pass@1 lands near the 50-70%
    # calibration window and there are enough wrong answers to verify.
    P_CORRECT = 0.60
    P_SILENT_FAILURE = 0.32
    # remainder: refusal / unusable

    # Verifier behaviour: approves nearly everything, which is the phenomenon
    # under test. These are assumptions baked into the mock, not findings.
    P_APPROVE_GIVEN_CORRECT = 0.92
    P_APPROVE_GIVEN_WRONG = 0.45

    def __init__(self, model: str, max_tokens: int, sampling: dict, seed: int, tasks: dict):
        self.model = model
        self.max_tokens = max_tokens
        self.sampling = sampling
        self.seed = seed
        self.tasks = tasks

    def _rng(self, trace: dict) -> random.Random:
        key = "|".join(
            str(trace.get(k, "")) for k in ("task_id", "mode", "run_index", "stage")
        )
        digest = hashlib.sha256(f"{self.seed}|{key}".encode()).hexdigest()
        return random.Random(int(digest[:16], 16))

    @staticmethod
    def _tokens(text: str) -> int:
        # Deterministic stand-in for real usage numbers.
        return max(1, len(text) // 4)

    def complete(
        self,
        system: str,
        messages: list[dict],
        *,
        schema: dict | None = None,
        trace: dict | None = None,
    ) -> CallResult:
        trace = trace or {}
        rng = self._rng(trace)
        task = self.tasks[trace["task_id"]]

        if trace.get("stage") == "verification":
            text = self._verification(rng, trace)
        else:
            text = self._generation(rng, task)

        prompt_chars = len(system) + sum(len(str(m["content"])) for m in messages)
        return CallResult(
            text=text,
            input_tokens=self._tokens("x" * prompt_chars),
            output_tokens=self._tokens(text),
            model=f"{self.model}-mock",
            latency_s=0.0,
            stop_reason="end_turn",
            structured=schema is not None,
        )

    def _generation(self, rng: random.Random, task: dict) -> str:
        roll = rng.random()
        if roll < self.P_CORRECT:
            code = task["reference"].strip()
        elif roll < self.P_CORRECT + self.P_SILENT_FAILURE:
            code = task["silent_failure"].strip()
        else:
            return rng.choice(_REFUSALS)
        styles = _SQL_FENCE_STYLES if task["kind"] == "sql" else _FENCE_STYLES
        return rng.choice(styles).format(code=code)

    def _verification(self, rng: random.Random, trace: dict) -> str:
        # The mock verifier is told whether the answer was actually right; a real
        # verifier is not. This exists to exercise the pipeline, not to predict it.
        truth_correct = bool(trace.get("truth_correct"))
        p = self.P_APPROVE_GIVEN_CORRECT if truth_correct else self.P_APPROVE_GIVEN_WRONG
        says_correct = rng.random() < p
        if says_correct:
            confidence = rng.randint(78, 99)
            return json.dumps({"verdict": "correct", "confidence": confidence, "revised": None})
        confidence = rng.randint(40, 88)
        return json.dumps(
            {
                "verdict": "wrong",
                "confidence": confidence,
                "revised": trace.get("revision_code") or None,
            }
        )


def build_provider(cfg, *, dry_run: bool, tasks: dict):
    if dry_run:
        return MockProvider(
            cfg.model, cfg.max_tokens, cfg.sampling_params(), cfg.seed, tasks
        )
    return AnthropicProvider(cfg.model, cfg.max_tokens, cfg.sampling_params())
