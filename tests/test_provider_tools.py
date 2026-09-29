"""The Anthropic provider speaks the loop's OpenAI shape on both sides.

No network: the translation functions are pure, and the response side is
exercised with a stand-in client. If either direction drifts, a cross-model
run would silently measure a different conversation than the DeepSeek run.
"""

import json
import types

import pytest

import provider as provider_mod


@pytest.fixture
def prov(monkeypatch):
    """An AnthropicProvider whose SDK client is a stub; no key, no network."""
    fake_sdk = types.SimpleNamespace(
        Anthropic=lambda **kw: types.SimpleNamespace(messages=None),
        BadRequestError=Exception,
    )
    monkeypatch.setitem(__import__("sys").modules, "anthropic", fake_sdk)
    return provider_mod.AnthropicProvider("claude-haiku-4-5", 8192, {"temperature": 0.0})


OPENAI_TOOLS = [
    {"type": "function", "function": {
        "name": "get_order", "description": "Fetch one order by id.",
        "parameters": {"type": "object", "properties": {"order_id": {"type": "string"}},
                       "required": ["order_id"]}}},
    {"type": "function", "function": {"name": "submit", "description": "Finish.",
                                      "parameters": {"type": "object", "properties": {}}}},
]


def test_tools_translate_to_input_schema(prov):
    out = prov.to_anthropic_tools(OPENAI_TOOLS)
    assert out[0] == {"name": "get_order", "description": "Fetch one order by id.",
                      "input_schema": OPENAI_TOOLS[0]["function"]["parameters"]}
    assert [t["name"] for t in out] == ["get_order", "submit"]


def test_history_translates_and_merges_tool_results(prov):
    history = [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "do the task"},
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": "get_order", "arguments": '{"order_id": "O01"}'}},
            {"id": "c2", "type": "function", "function": {"name": "get_order", "arguments": '{"order_id": "O02"}'}},
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": '{"id": "O01"}'},
        {"role": "tool", "tool_call_id": "c2", "content": '{"id": "O02"}'},
    ]
    system, msgs = prov.to_anthropic_messages(history)
    assert system == "SYS"
    assert msgs[0] == {"role": "user", "content": "do the task"}
    assert msgs[1]["role"] == "assistant"
    assert [b["type"] for b in msgs[1]["content"]] == ["tool_use", "tool_use"]
    assert msgs[1]["content"][0] == {"type": "tool_use", "id": "c1", "name": "get_order",
                                     "input": {"order_id": "O01"}}
    # both results in ONE user turn, in order
    assert msgs[2]["role"] == "user"
    assert [b["tool_use_id"] for b in msgs[2]["content"]] == ["c1", "c2"]
    assert msgs[2]["content"][0]["type"] == "tool_result"


def test_a_kept_raw_turn_is_replayed_verbatim(prov):
    raw = [{"type": "thinking", "thinking": "hmm", "signature": "sig"},
           {"type": "tool_use", "id": "c9", "name": "submit", "input": {"answer": 1}}]
    prov._raw_turns["c9"] = raw
    history = [{"role": "system", "content": "S"}, {"role": "user", "content": "u"},
               {"role": "assistant", "content": "", "tool_calls": [
                   {"id": "c9", "type": "function", "function": {"name": "submit", "arguments": '{"answer": 1}'}}]}]
    _, msgs = prov.to_anthropic_messages(history)
    assert msgs[1]["content"] is raw


class _Block:
    def __init__(self, **kw):
        self.__dict__.update(kw)

    def model_dump(self, exclude_none=True):
        return dict(self.__dict__)


def test_response_translates_back_and_accounts_cache(prov):
    response = types.SimpleNamespace(
        content=[_Block(type="text", text="ok"),
                 _Block(type="tool_use", id="t1", name="get_order", input={"order_id": "O01"})],
        usage=types.SimpleNamespace(input_tokens=100, output_tokens=20,
                                    cache_read_input_tokens=400, cache_creation_input_tokens=50),
        model="claude-haiku-4-5-20251001", stop_reason="tool_use",
    )
    captured = {}

    def create(**kwargs):
        captured.update(kwargs)
        return response

    prov.client = types.SimpleNamespace(messages=types.SimpleNamespace(create=create))
    msg, acct = prov.chat_tools([{"role": "system", "content": "S"}, {"role": "user", "content": "u"}],
                                OPENAI_TOOLS)
    assert msg.content == "ok"
    assert msg.tool_calls[0].function.name == "get_order"
    assert json.loads(msg.tool_calls[0].function.arguments) == {"order_id": "O01"}
    assert acct.input_tokens == 550 and acct.cache_hit_tokens == 400
    assert acct.cache_miss_tokens == 150 and acct.cache_write_tokens == 50
    assert acct.model == "claude-haiku-4-5-20251001" and not acct.truncated
    assert captured["system"] == "S" and captured["tools"][0]["name"] == "get_order"
    assert captured["cache_control"] == {"type": "ephemeral"}
    assert "thinking" not in captured
    # the raw turn is kept for replay under the first tool-call id
    assert prov._raw_turns["t1"][1]["name"] == "get_order"


def test_thinking_budget_is_sent_only_when_configured(prov):
    prov.thinking_budget = 2048
    captured = {}
    prov.client = types.SimpleNamespace(messages=types.SimpleNamespace(
        create=lambda **kw: (captured.update(kw) or types.SimpleNamespace(
            content=[], usage=types.SimpleNamespace(input_tokens=1, output_tokens=1,
                                                    cache_read_input_tokens=0, cache_creation_input_tokens=0),
            model="m", stop_reason="end_turn"))))
    prov.chat_tools([{"role": "user", "content": "u"}], [])
    assert captured["thinking"] == {"type": "enabled", "budget_tokens": 2048}


def test_cache_write_premium_is_added_only_when_a_write_rate_exists():
    import config as config_mod
    base = dict(provider="anthropic", base_url=None, api_key_env=None, model="m", temperature=0.0,
                max_tokens=10, runs_per_cell=1, modes=("clean",), inject_modes=(), seed=1,
                pricing_tier="standard", price_in_miss_per_mtok=1.0, price_in_hit_per_mtok=0.1,
                price_out_per_mtok=5.0, grading_timeout_s=1, baseline_pass_at_1_min=0,
                baseline_pass_at_1_max=1, max_verdict_parse_failure_rate=0, max_truncation_rate=0)
    no_write = config_mod.Config(**base)
    with_write = config_mod.Config(**base, price_in_write_per_mtok=1.25)
    # 1000 input of which 400 cached and 100 written; 10 output
    assert no_write.cost_usd(1000, 10, 400, 100) == pytest.approx((600 * 1.0 + 400 * 0.1 + 10 * 5.0) / 1e6)
    assert with_write.cost_usd(1000, 10, 400, 100) == pytest.approx(
        (600 * 1.0 + 400 * 0.1 + 10 * 5.0 + 100 * 0.25) / 1e6)
    assert "input_cache_write_per_mtok" in with_write.pricing_rates()
    assert "input_cache_write_per_mtok" not in no_write.pricing_rates()


def test_openai_compat_provider_records_its_own_name(monkeypatch):
    fake_openai = types.SimpleNamespace(OpenAI=lambda **kw: object())
    monkeypatch.setitem(__import__("sys").modules, "openai", fake_openai)
    p = provider_mod.OpenAICompatProvider("gemini", "gemini-x", 100, {}, "https://x/", "k")
    assert p.name == "gemini"
    assert provider_mod.DeepSeekProvider.name == "deepseek"
