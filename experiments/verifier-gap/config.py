"""Typed loader for config.yaml.

The loader validates the model/parameter combination up front. Discovering
that a model rejects `temperature` halfway through a paid 150-call run is an
avoidable failure, so it is turned into a startup error.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

HERE = Path(__file__).resolve().parent
DEFAULT_CONFIG = HERE / "config.yaml"


class ConfigError(ValueError):
    """Raised when config.yaml is internally inconsistent or unusable."""


@dataclass(frozen=True)
class Config:
    model: str
    temperature: float | None
    max_tokens: int
    runs_per_cell: int
    modes: tuple[str, ...]
    seed: int
    price_in_per_mtok: float
    price_out_per_mtok: float
    grading_timeout_s: int
    baseline_pass_at_1_min: float
    baseline_pass_at_1_max: float
    max_verdict_parse_failure_rate: float
    temperature_unsupported_models: tuple[str, ...] = ()
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def supports_temperature(self) -> bool:
        return self.model not in self.temperature_unsupported_models

    def cost_usd(self, input_tokens: int, output_tokens: int) -> float:
        """Cost of one call, in USD."""
        return (
            input_tokens * self.price_in_per_mtok
            + output_tokens * self.price_out_per_mtok
        ) / 1_000_000

    def sampling_params(self) -> dict[str, Any]:
        """Sampling params to send, omitting any the model would reject."""
        if self.temperature is None or not self.supports_temperature:
            return {}
        return {"temperature": self.temperature}


def load(path: str | Path = DEFAULT_CONFIG) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}

    required = ["model", "max_tokens", "runs_per_cell", "modes", "seed", "pricing"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ConfigError(f"config missing required keys: {missing}")

    unsupported = tuple(data.get("temperature_unsupported_models", []))
    model = data["model"]
    temperature = data.get("temperature")

    # The check that pays for itself: fail before spending money.
    if temperature is not None and model in unsupported:
        raise ConfigError(
            f"model {model!r} rejects the `temperature` parameter with HTTP 400, "
            f"but config sets temperature={temperature}. Either pick a model that "
            f"accepts it or set `temperature: null` and record that sampling was "
            f"left at the API default."
        )

    modes = tuple(data["modes"])
    if set(modes) != {"baseline", "self_verify"}:
        raise ConfigError(f"modes must be exactly [baseline, self_verify], got {list(modes)}")
    if int(data["runs_per_cell"]) < 1:
        raise ConfigError("runs_per_cell must be >= 1")

    cal = data.get("calibration", {})
    thr = data.get("thresholds", {})
    return Config(
        model=model,
        temperature=temperature,
        max_tokens=int(data["max_tokens"]),
        runs_per_cell=int(data["runs_per_cell"]),
        modes=modes,
        seed=int(data["seed"]),
        price_in_per_mtok=float(data["pricing"]["input_per_mtok"]),
        price_out_per_mtok=float(data["pricing"]["output_per_mtok"]),
        grading_timeout_s=int(data.get("grading", {}).get("timeout_seconds", 10)),
        baseline_pass_at_1_min=float(cal.get("baseline_pass_at_1_min", 0.50)),
        baseline_pass_at_1_max=float(cal.get("baseline_pass_at_1_max", 0.70)),
        max_verdict_parse_failure_rate=float(thr.get("max_verdict_parse_failure_rate", 0.02)),
        temperature_unsupported_models=unsupported,
        raw=data,
    )
