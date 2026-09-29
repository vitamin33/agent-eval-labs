"""Load experiment 3's config.yaml into experiment 1's `Config` dataclass.

Experiment 1's loader validates its own matrix (`modes` must be baseline and
self_verify), so it cannot read this file. The dataclass itself is reusable:
provider construction, pricing and `cost_usd` are shared code, and sharing
them is what keeps the cost numbers of the three experiments comparable.
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
for _p in (HERE, HERE.parent / "verifier-gap"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

from config import Config, ConfigError  # noqa: E402

DEFAULT_CONFIG = HERE / "config.yaml"
MODES = ("clean", "inject", "inject_tool", "inject_enforced")
# Stage 3 adds one arm on DeepSeek only: the enforced wrapper WITHOUT the
# prompt line that names the checkpoint as authoritative.
ALL_MODES = MODES + ("inject_wrapped",)


def load(path: str | Path = DEFAULT_CONFIG) -> Config:
    path = Path(path)
    if not path.exists():
        raise ConfigError(f"config not found: {path}")
    raw_bytes = path.read_bytes()
    data = yaml.safe_load(raw_bytes) or {}

    required = ["provider", "model", "max_tokens", "modes", "stage_runs", "seed", "pricing"]
    missing = [k for k in required if k not in data]
    if missing:
        raise ConfigError(f"config missing required keys: {missing}")
    modes = tuple(data["modes"])
    unknown = [m for m in modes if m not in ALL_MODES]
    if unknown or not modes:
        raise ConfigError(f"modes must be a non-empty subset of {list(ALL_MODES)}, got {list(modes)}")
    provider = data["provider"]
    if provider not in ("anthropic", "deepseek", "gemini", "openai_compat"):
        raise ConfigError(f"unknown provider {provider!r}")
    if provider != "anthropic" and not data.get("base_url"):
        raise ConfigError(f"provider {provider!r} needs a base_url")

    pricing = data["pricing"]
    tier = pricing.get("tier", "peak")
    if tier not in pricing:
        raise ConfigError(f"pricing tier {tier!r} has no rate table in config")
    rates = pricing[tier]
    for key in ("input_cache_miss_per_mtok", "input_cache_hit_per_mtok", "output_per_mtok"):
        if key not in rates:
            raise ConfigError(f"pricing.{tier} is missing {key}")

    thr = data.get("thresholds", {})
    return Config(
        provider=provider,
        base_url=data.get("base_url"),
        api_key_env=data.get("api_key_env"),
        model=data["model"],
        temperature=data.get("temperature"),
        max_tokens=int(data["max_tokens"]),
        runs_per_cell=int(max(int(v) for v in data["stage_runs"].values())),
        modes=modes,
        inject_modes=(),
        seed=int(data["seed"]),
        pricing_tier=tier,
        price_in_miss_per_mtok=float(rates["input_cache_miss_per_mtok"]),
        price_in_hit_per_mtok=float(rates["input_cache_hit_per_mtok"]),
        price_out_per_mtok=float(rates["output_per_mtok"]),
        grading_timeout_s=10,
        baseline_pass_at_1_min=0.0,
        baseline_pass_at_1_max=1.0,
        max_verdict_parse_failure_rate=0.0,
        max_truncation_rate=float(thr.get("max_truncation_rate", 0.02)),
        temperature_unsupported_models=tuple(data.get("temperature_unsupported_models", [])),
        price_in_write_per_mtok=(float(rates["input_cache_write_per_mtok"])
                                 if "input_cache_write_per_mtok" in rates else None),
        thinking_budget=(int(data["thinking_budget"]) if data.get("thinking_budget") else None),
        raw=data,
        path=str(path),
        sha256=hashlib.sha256(raw_bytes).hexdigest(),
    )


def stage_runs(cfg: Config) -> dict[int, int]:
    return {int(k): int(v) for k, v in cfg.raw["stage_runs"].items()}


def step_cap(cfg: Config) -> int:
    return int(cfg.raw.get("step_cap", 12))


def thresholds(cfg: Config) -> dict[str, float]:
    thr = cfg.raw.get("thresholds", {})
    return {
        "max_truncation_rate": float(thr.get("max_truncation_rate", 0.02)),
        "max_step_cap_rate": float(thr.get("max_step_cap_rate", 0.10)),
        "clean_pass_rate_min": float(thr.get("clean_pass_rate_min", 0.70)),
    }


def tag(cfg: Config) -> str:
    """Short name for result files: config `tag`, else the model id."""
    return str(cfg.raw.get("tag") or cfg.model).replace("/", "-")
