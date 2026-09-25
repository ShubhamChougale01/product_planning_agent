"""T23 tests — Discovery's system prompt, internal modes and turn
integration. Every Done-when box in `tasks/t23_discovery_prompt_and_modes.md`
maps to at least one test here.

Every test except `test_one_real_turn_completes_and_returns_a_structured_
agent_result` is zero-cost — the real SDK exchange (`ppa.agents.turn.
_run_one_sdk_turn`) is monkeypatched everywhere else, matching this file's
own scope: proving the *wiring* (ctx -> project -> mode -> prompt ->
AgentResult) doesn't need a model, even though T23 itself (unlike T21/T22)
does not claim to be a zero-cost task.

That one test is marked `@pytest.mark.live_model` and excluded from the
default `pytest` sweep (`pyproject.toml`'s own `addopts`) — decision #31,
`blockers.md`: a task that genuinely needs a model still shouldn't make
every *future* task's `pytest` run pay for it by default. Run it explicitly
with `pytest -m live_model` or by naming it directly.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from ppa.agents.base import AgentResultStatus
from ppa.agents.discovery import (
    DEFAULT_MODE,
    ROLE_VOCABULARY,
    DiscoveryAgent,
    DiscoveryMode,
    allowed_tools_for_mode,
    render_system_prompt,
)
from ppa.agents.registry import GRANTS
from ppa.config.profiles import UserProfile
from ppa.ledger.events import EventType
from ppa.ledger.models import QuestionAnswer
from ppa.ledger.project import Project, create_project
from ppa.ledger.store import append_event, read_project_meta, write_project_meta
from ppa.tools.dispatch import InvocationContext

NOW = datetime(2026, 9, 25, 9, 0, 0, tzinfo=timezone.utc)
TODAY = date(2026, 9, 25)


def _profile(**overrides) -> UserProfile:
    base = dict(role="engineer", technical_depth="medium", domain_familiarity="medium")
    base.update(overrides)
    return UserProfile(**base)


def _bare_project(tmp_path, *, profile: UserProfile | None = None, mode: DiscoveryMode | None = None) -> Project:
    """A `Project` handle with a real, readable `project.json` but no `git`
    repo — matches decision #29's own "no reason to pay subprocess
    overhead" reasoning for a suite this file keeps zero-cost."""

    profile = profile or _profile()
    project_dir = tmp_path / "projects" / "modes-test"
    events_path = project_dir / ".planning" / "events.ndjson"
    meta = dict(
        name="Modes Test", profile=profile.model_dump(), workflow_state="DISCOVERY",
        created_at=NOW.isoformat(),
    )
    if mode is not None:
        meta["discovery_mode"] = mode.value
    write_project_meta(events_path, meta)
    return Project(
        slug="modes-test", name="Modes Test", profile=profile, workflow_state="DISCOVERY",
        created_at=NOW, path=project_dir,
    )


def _ctx(project: Project) -> InvocationContext:
    return InvocationContext(
        agent_id="discovery", workflow_state="DISCOVERY", session_id="sess-1", audit_path=project.audit_path,
    )


# ---------------------------------------------------------------------------
# Done when: the agent cannot call ask_user in REVIEW mode / cannot call
# manage_requirement(create) in READY mode — enforced by allowed_tools, not
# prompt text.
# ---------------------------------------------------------------------------


def test_ask_user_is_not_allowed_in_review_mode():
    assert "ask_user" not in allowed_tools_for_mode(DiscoveryMode.REVIEW)


def test_manage_requirement_is_not_allowed_in_ready_mode():
    assert "manage_requirement" not in allowed_tools_for_mode(DiscoveryMode.READY)


def test_every_mode_tool_subset_is_a_true_subset_of_the_real_grant():
    """A mode table typo must never *widen* what Discovery may do beyond
    `ppa.agents.registry.GRANTS` — only narrow it further."""

    for mode in DiscoveryMode:
        assert allowed_tools_for_mode(mode) <= GRANTS["discovery"]


def test_intake_and_clarify_modes_retain_the_tools_they_actually_need():
    assert {"manage_requirement", "manage_assumption", "manage_unknown", "ask_user"} <= allowed_tools_for_mode(
        DiscoveryMode.INTAKE
    )
    assert {"ask_user", "request_guidance"} <= allowed_tools_for_mode(DiscoveryMode.CLARIFY)


# ---------------------------------------------------------------------------
# Done when: autonomy thresholds are a table in config, not prose in the
# prompt.
# ---------------------------------------------------------------------------


def test_autonomy_thresholds_are_not_restated_as_numeric_prose_in_the_prompt():
    rendered = render_system_prompt(DiscoveryMode.CLARIFY, _profile(), today=TODAY)
    assert "ppa.config.autonomy" in rendered
    assert "impact == LOW" not in rendered
    assert "impact >= MEDIUM" not in rendered


def test_autonomy_module_owns_the_actual_threshold_table():
    from ppa.config.autonomy import ASSUME_THRESHOLD, NEVER_ASSUME_AREAS, may_assume_silently

    assert ASSUME_THRESHOLD["conservative"] == "LOW"
    assert ASSUME_THRESHOLD["assertive"] == "MEDIUM"
    assert NEVER_ASSUME_AREAS == frozenset({"problem", "users"})

    assert may_assume_silently(impact="LOW", area="platform", is_critical=False) is True
    assert may_assume_silently(impact="MEDIUM", area="platform", is_critical=False) is False
    assert may_assume_silently(impact="MEDIUM", area="platform", is_critical=False, autonomy="assertive") is True
    assert may_assume_silently(impact="LOW", area="problem", is_critical=False) is False
    assert may_assume_silently(impact="LOW", area="platform", is_critical=True) is False


# ---------------------------------------------------------------------------
# Done when: current date is injected on every turn.
# ---------------------------------------------------------------------------


def test_current_date_is_injected_into_the_rendered_prompt():
    rendered = render_system_prompt(DiscoveryMode.INTAKE, _profile(), today=TODAY)
    assert "2026-09-25" in rendered


def test_missing_today_defaults_to_the_real_current_date(monkeypatch):
    import ppa.agents.discovery as discovery_module

    class _FixedDate(date):
        @classmethod
        def today(cls):
            return date(2030, 1, 1)

    monkeypatch.setattr(discovery_module, "date", _FixedDate)
    rendered = render_system_prompt(DiscoveryMode.INTAKE, _profile())
    assert "2030-01-01" in rendered


# ---------------------------------------------------------------------------
# Done when: the prompt renders differently for engineer and product
# profiles.
# ---------------------------------------------------------------------------


def test_prompt_renders_differently_for_engineer_and_product_profiles():
    engineer_prompt = render_system_prompt(DiscoveryMode.CLARIFY, _profile(role="engineer"), today=TODAY)
    product_prompt = render_system_prompt(DiscoveryMode.CLARIFY, _profile(role="product"), today=TODAY)

    assert engineer_prompt != product_prompt
    assert ROLE_VOCABULARY["engineer"] in engineer_prompt
    assert ROLE_VOCABULARY["product"] in product_prompt
    assert ROLE_VOCABULARY["product"] not in engineer_prompt


def test_prompt_includes_the_role_conditioned_vocabulary_for_mixed_too():
    rendered = render_system_prompt(DiscoveryMode.CLARIFY, _profile(role="mixed"), today=TODAY)
    assert ROLE_VOCABULARY["mixed"] in rendered


# ---------------------------------------------------------------------------
# Mode fragments — one per built mode, none for the placeholder/terminal
# ones.
# ---------------------------------------------------------------------------


def test_intake_fragment_is_appended_in_intake_mode():
    rendered = render_system_prompt(DiscoveryMode.INTAKE, _profile(), today=TODAY)
    assert "Initial Product Understanding" in rendered
    assert "Where am I wrong" in rendered


def test_clarify_fragment_is_appended_in_clarify_mode():
    rendered = render_system_prompt(DiscoveryMode.CLARIFY, _profile(), today=TODAY)
    assert "hard cap of" in rendered.lower() or "hard cap" in rendered


def test_review_fragment_forbids_asking_and_is_appended_in_review_mode():
    rendered = render_system_prompt(DiscoveryMode.REVIEW, _profile(), today=TODAY)
    assert "cannot ask a question" in rendered.lower()


@pytest.mark.parametrize("mode", [DiscoveryMode.GUIDANCE, DiscoveryMode.RESEARCH, DiscoveryMode.READY])
def test_modes_without_a_fragment_render_the_core_prompt_only(mode):
    rendered = render_system_prompt(mode, _profile(), today=TODAY)
    assert "Mode: INTAKE" not in rendered
    assert "Mode: CLARIFY" not in rendered
    assert "Mode: REVIEW" not in rendered
    assert f"**{mode.value}**" in rendered  # the core prompt's own "Current mode" line


# ---------------------------------------------------------------------------
# Turn integration (S7.3) — wiring proven without a model; classification
# proven never to read the model's own prose.
# ---------------------------------------------------------------------------


def test_default_mode_for_a_fresh_project_is_intake(tmp_path):
    from ppa.agents.turn import _current_mode

    project = _bare_project(tmp_path)
    assert _current_mode(project) is DEFAULT_MODE is DiscoveryMode.INTAKE


def test_run_discovery_turn_reconstructs_the_project_from_ctx_alone(tmp_path, monkeypatch):
    import ppa.agents.turn as turn_module

    project = _bare_project(tmp_path, mode=DiscoveryMode.INTAKE)

    captured = {}

    async def _fake_sdk_turn(*, system_prompt, server, allowed_tools, user_message):
        captured["system_prompt"] = system_prompt
        captured["allowed_tools"] = allowed_tools
        return "Understood. Where am I wrong?", 0.01

    monkeypatch.setattr(turn_module, "_run_one_sdk_turn", _fake_sdk_turn)

    result = turn_module.run_discovery_turn(_ctx(project), today=TODAY)

    assert result.status is AgentResultStatus.OK
    assert result.summary == "Understood. Where am I wrong?"
    assert "2026-09-25" in captured["system_prompt"]
    assert all(name.startswith("mcp__discovery-intake-tools__") for name in captured["allowed_tools"])


def test_run_discovery_turn_advances_intake_to_clarify_after_one_clean_turn(tmp_path, monkeypatch):
    import ppa.agents.turn as turn_module

    project = _bare_project(tmp_path, mode=DiscoveryMode.INTAKE)

    async def _fake_sdk_turn(**kwargs):
        return "done for this turn", 0.0

    monkeypatch.setattr(turn_module, "_run_one_sdk_turn", _fake_sdk_turn)
    turn_module.run_discovery_turn(_ctx(project), today=TODAY)

    assert read_project_meta(project.events_path)["discovery_mode"] == "CLARIFY"


def test_run_discovery_turn_status_is_never_read_from_the_models_own_text(tmp_path, monkeypatch):
    """Even if the model's own prose claims completion, classification is
    decided by ledger state (a pending question or not) — never by parsing
    what the text says."""

    import ppa.agents.turn as turn_module

    project = _bare_project(tmp_path, mode=DiscoveryMode.CLARIFY)

    async def _fake_sdk_turn(**kwargs):
        return "I am completely done, finished, ready, and the task is complete!", 0.0

    monkeypatch.setattr(turn_module, "_run_one_sdk_turn", _fake_sdk_turn)
    result = turn_module.run_discovery_turn(_ctx(project), today=TODAY)

    assert result.status is AgentResultStatus.OK  # not some invented "COMPLETE" status


def test_run_discovery_turn_reports_human_input_required_when_a_question_is_pending(tmp_path, monkeypatch):
    import ppa.agents.turn as turn_module

    project = _bare_project(tmp_path, mode=DiscoveryMode.CLARIFY)
    question = QuestionAnswer(
        id="Q-001", created_at=NOW, updated_at=NOW, created_by="agent:discovery", updated_by="agent:discovery",
        text="what platform?", why_asked="platform is unconfirmed", round=1,
    )
    append_event(
        dict(
            ts=NOW, type=EventType.QUESTION_ASKED, entity_id="Q-001", actor_id="agent:discovery",
            actor_role="agent", agent_name="discovery", workflow_state="DISCOVERY", txn_id=None,
            source="fixture", reason="asked a question", before=None,
            after=question.model_dump(mode="json"), session_id="sess-1",
        ),
        project.events_path,
    )

    async def _fake_sdk_turn(**kwargs):
        return "waiting on you", 0.0

    monkeypatch.setattr(turn_module, "_run_one_sdk_turn", _fake_sdk_turn)
    result = turn_module.run_discovery_turn(_ctx(project), today=TODAY)

    assert result.status is AgentResultStatus.HUMAN_INPUT_REQUIRED
    # A pending question means Intake must not silently advance to CLARIFY.
    assert result.data["pending_questions"] == ["Q-001"]


def test_run_discovery_turn_reports_non_recoverable_on_sdk_failure(tmp_path, monkeypatch):
    import ppa.agents.turn as turn_module

    project = _bare_project(tmp_path)

    async def _boom(**kwargs):
        raise RuntimeError("network exploded")

    monkeypatch.setattr(turn_module, "_run_one_sdk_turn", _boom)
    result = turn_module.run_discovery_turn(_ctx(project), today=TODAY)

    assert result.status is AgentResultStatus.NON_RECOVERABLE
    assert "network exploded" in result.summary


def test_discovery_agent_invoke_delegates_to_run_discovery_turn(tmp_path, monkeypatch):
    import ppa.agents.turn as turn_module

    project = _bare_project(tmp_path)

    async def _fake_sdk_turn(**kwargs):
        return "ok", 0.0

    monkeypatch.setattr(turn_module, "_run_one_sdk_turn", _fake_sdk_turn)
    result = DiscoveryAgent().invoke(_ctx(project))
    assert result.status is AgentResultStatus.OK


# ---------------------------------------------------------------------------
# Done when: one turn completes and returns a structured AgentResult, never
# a completion claim in prose. The one real-model test in this file — T23's
# own header says "Needs a model: Yes," unlike T21/T22.
# ---------------------------------------------------------------------------


@pytest.mark.live_model
def test_one_real_turn_completes_and_returns_a_structured_agent_result(tmp_path):
    project = create_project(
        "Real Turn Test", "a tool for tracking vendor invoices", _profile(), projects_root=tmp_path / "projects"
    )

    result = DiscoveryAgent().invoke(_ctx(project))

    assert isinstance(result.status, AgentResultStatus)
    assert result.status in (AgentResultStatus.OK, AgentResultStatus.HUMAN_INPUT_REQUIRED)
    assert isinstance(result.summary, str) and result.summary
