"""ModelProvider seam — the config/env precedence and the credential rules."""

from __future__ import annotations

import pytest

from ppa.providers.model import MODEL_TIERS, ModelConfig, ModelProvider


def test_defaults_to_subscription_auth():
    """No API key is the whole point of the zero-cost path (docs/decisions/auth.md)."""
    provider = ModelProvider()
    assert provider.cfg.auth_source == "subscription"
    assert provider.model == MODEL_TIERS["primary"]


def test_subscription_auth_resolves_no_credential():
    assert ModelProvider()._credential() is None


def test_unknown_tier_fails_at_construction_not_mid_conversation():
    with pytest.raises(ValueError, match="Unknown model tier"):
        ModelProvider(ModelConfig(tier="enormous"))


def test_override_beats_tier():
    cfg = ModelConfig(tier="cheap", model_override="some-pinned-model")
    assert ModelProvider(cfg).model == "some-pinned-model"


def test_env_overrides_file(tmp_path, monkeypatch):
    cfg_file = tmp_path / "model.yaml"
    cfg_file.write_text("tier: cheap\nmax_turns: 5\n", encoding="utf-8")

    assert ModelProvider.from_config(cfg_file).model == MODEL_TIERS["cheap"]

    monkeypatch.setenv("PPA_MODEL_TIER", "deep")
    monkeypatch.setenv("PPA_MAX_TURNS", "99")
    provider = ModelProvider.from_config(cfg_file)
    assert provider.model == MODEL_TIERS["deep"]
    assert provider.cfg.max_turns == 99


def test_missing_config_file_falls_back_to_defaults(tmp_path):
    provider = ModelProvider.from_config(tmp_path / "absent.yaml")
    assert provider.model == MODEL_TIERS["primary"]


def test_api_key_auth_reads_env_at_call_time(monkeypatch):
    cfg = ModelConfig(auth_source="api_key", api_key_env="PPA_TEST_KEY")
    provider = ModelProvider(cfg)

    with pytest.raises(RuntimeError, match="no credential was found"):
        provider._credential()

    monkeypatch.setenv("PPA_TEST_KEY", "value-set-after-construction")
    assert provider._credential() == "value-set-after-construction"


def test_credential_is_never_stored_on_the_instance(monkeypatch):
    monkeypatch.setenv("PPA_TEST_KEY", "super-secret-value")
    provider = ModelProvider(ModelConfig(auth_source="api_key", api_key_env="PPA_TEST_KEY"))
    provider._credential()

    haystack = repr(provider.__dict__) + repr(provider) + repr(provider.describe())
    assert "super-secret-value" not in haystack


def test_describe_is_safe_to_log(monkeypatch):
    monkeypatch.setenv("PPA_TEST_KEY", "super-secret-value")
    described = ModelProvider(
        ModelConfig(auth_source="api_key", api_key_env="PPA_TEST_KEY")
    ).describe()
    assert described["credential_source"] == "$PPA_TEST_KEY"
    assert "super-secret-value" not in str(described)


def test_options_carry_the_grant_and_the_model():
    provider = ModelProvider()
    options = provider.options(system_prompt="you are a test", allowed_tools=["read_planning_state"])
    assert options.model == provider.model
    assert options.allowed_tools == ["read_planning_state"]
