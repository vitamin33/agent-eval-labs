"""P3.1 — config is the single source of truth, and validates itself."""

import textwrap

import pytest

import config as config_mod


def test_loads_default_config():
    cfg = config_mod.load()
    assert cfg.model
    assert cfg.provider in ("anthropic", "deepseek")
    assert cfg.runs_per_cell >= 1
    assert set(cfg.modes) == {"baseline", "self_verify"}
    assert cfg.price_in_miss_per_mtok > 0 and cfg.price_out_per_mtok > 0


def test_cost_formula():
    cfg = config_mod.load()
    # 1M uncached input + 1M output == the two headline prices, summed.
    cost = cfg.cost_usd(1_000_000, 1_000_000)
    assert cost == pytest.approx(cfg.price_in_miss_per_mtok + cfg.price_out_per_mtok)
    assert cfg.cost_usd(0, 0) == 0.0


def test_cached_input_is_cheaper_than_uncached():
    """Self-verify resends the generation prompt, so this changes H2's ratio."""
    cfg = config_mod.load()
    uncached = cfg.cost_usd(1_000_000, 0, 0)
    cached = cfg.cost_usd(1_000_000, 0, 1_000_000)
    assert cached < uncached
    assert cached == pytest.approx(cfg.price_in_hit_per_mtok)


def test_cache_hits_cannot_exceed_the_prompt():
    """A provider reporting more cache hits than prompt tokens must not
    produce a negative cost."""
    cfg = config_mod.load()
    assert cfg.cost_usd(100, 0, 10_000) >= 0


def _write(tmp_path, body: str):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent(body))
    return p


BASE = """
    provider: deepseek
    model: {model}
    temperature: {temperature}
    temperature_unsupported_models: [claude-opus-5, claude-sonnet-5]
    max_tokens: 512
    runs_per_cell: 5
    modes: [baseline, self_verify]
    seed: 1
    pricing:
      tier: peak
      peak:
        input_cache_miss_per_mtok: 1.0
        input_cache_hit_per_mtok: 0.1
        output_per_mtok: 5.0
"""


def test_rejects_temperature_on_a_model_that_would_400(tmp_path):
    """The check that pays for itself: fail at startup, not 40 paid calls in."""
    path = _write(tmp_path, BASE.format(model="claude-opus-5", temperature="0.0"))
    with pytest.raises(config_mod.ConfigError, match="rejects the `temperature`"):
        config_mod.load(path)


def test_allows_such_a_model_when_temperature_is_null(tmp_path):
    path = _write(tmp_path, BASE.format(model="claude-opus-5", temperature="null"))
    cfg = config_mod.load(path)
    assert cfg.sampling_params() == {}
    assert cfg.supports_temperature is False


def test_sampling_params_included_when_supported(tmp_path):
    path = _write(tmp_path, BASE.format(model="claude-haiku-4-5", temperature="0.0"))
    assert config_mod.load(path).sampling_params() == {"temperature": 0.0}


def test_rejects_unknown_mode_set(tmp_path):
    path = _write(tmp_path, BASE.format(model="claude-haiku-4-5", temperature="0.0").replace(
        "modes: [baseline, self_verify]", "modes: [baseline]"
    ))
    with pytest.raises(config_mod.ConfigError, match="modes must be"):
        config_mod.load(path)


def test_missing_file_is_an_error(tmp_path):
    with pytest.raises(config_mod.ConfigError, match="not found"):
        config_mod.load(tmp_path / "nope.yaml")


def test_rejects_an_unknown_provider(tmp_path):
    body = BASE.format(model="deepseek-v4-flash", temperature="0.0").replace(
        "provider: deepseek", "provider: mistral"
    )
    with pytest.raises(config_mod.ConfigError, match="unknown provider"):
        config_mod.load(_write(tmp_path, body))


def test_rejects_a_pricing_tier_with_no_rate_table(tmp_path):
    body = BASE.format(model="deepseek-v4-flash", temperature="0.0").replace(
        "tier: peak", "tier: off_peak"
    )
    with pytest.raises(config_mod.ConfigError, match="no rate table"):
        config_mod.load(_write(tmp_path, body))


def test_dotenv_does_not_override_an_exported_variable(tmp_path, monkeypatch):
    monkeypatch.setenv("AELABS_TEST_KEY", "from-environment")
    env = tmp_path / ".env"
    env.write_text("AELABS_TEST_KEY=from-file\nAELABS_OTHER=set-by-file\n")
    config_mod.load_dotenv(env)
    import os

    assert os.environ["AELABS_TEST_KEY"] == "from-environment"
    assert os.environ["AELABS_OTHER"] == "set-by-file"


def test_dotenv_is_a_noop_when_absent(tmp_path):
    config_mod.load_dotenv(tmp_path / "nope.env")  # must not raise
