"""T33 zero-cost tests — fixture structure and persona determinism. No
model call anywhere in this file; the live, multi-round proofs
(`tests/eval/test_matrix.py`) are marked `live_model` separately.
"""

from __future__ import annotations

from ppa.config.profiles import UserProfile
from tests.eval.harness import FIXTURES_DIR, load_fixture, load_fixtures
from tests.eval.personas import PERSONAS

_REQUIRED_AXES = {"detail", "market", "system", "author", "ownership"}
_AXIS_ENDPOINTS = {
    "detail": {"vague", "detailed"},
    "market": {"b2b", "consumer"},
    "system": {"greenfield", "legacy"},
    "author": {"engineer", "product"},
    "ownership": {"internal", "client"},
}


def _sample_question(**overrides) -> dict:
    base = dict(
        id="Q-001", version=1, created_at="2026-09-29T00:00:00+00:00", updated_at="2026-09-29T00:00:00+00:00",
        created_by="agent:discovery", updated_by="agent:discovery", history=[],
        status="PENDING", text="Which payment processor should we integrate?",
        why_asked="determines the integration scope", target_areas=["scope_in"],
        round=1, suggested_options=["Stripe", "Braintree"], recommended_default="Stripe",
        answer_kind=None, dont_know_kind=None, answer_text=None, answered_at=None,
    )
    base.update(overrides)
    return base


# ---------------------------------------------------------------------------
# Done when: ten fixtures, covering every axis listed above.
# ---------------------------------------------------------------------------


def test_exactly_ten_fixtures_exist():
    fixtures = load_fixtures()
    assert len(fixtures) == 10


def test_every_fixture_loads_a_valid_seed_and_profile():
    for fixture in load_fixtures():
        assert fixture.seed_requirement.strip()
        assert isinstance(fixture.profile, UserProfile)
        assert _REQUIRED_AXES <= set(fixture.axes)


def test_every_axis_has_both_endpoints_represented_across_the_set():
    fixtures = load_fixtures()
    for axis, endpoints in _AXIS_ENDPOINTS.items():
        seen = {fixture.axes[axis] for fixture in fixtures}
        assert endpoints <= seen, f"axis {axis!r} is missing an endpoint: saw {seen}, need {endpoints}"


def test_fixture_names_are_unique_and_match_their_filenames():
    fixtures = load_fixtures()
    names = [f.name for f in fixtures]
    assert len(names) == len(set(names))
    for path in FIXTURES_DIR.glob("*.yaml"):
        assert load_fixture(path.stem).name == path.stem


def test_at_least_two_fixtures_are_flagged_as_adversarial_candidates():
    # Structural intent only — whether they actually break the agent is
    # proven empirically in tests/eval/test_matrix.py (live_model).
    adversarial = [f for f in load_fixtures() if f.adversarial]
    assert len(adversarial) >= 2


# ---------------------------------------------------------------------------
# Done when: six personas, each able to complete a session unattended
# (registration + shape here; the live completion proof is in
# test_matrix.py).
# ---------------------------------------------------------------------------


def test_six_personas_are_registered():
    expected = {"knows_their_stuff", "vague", "always_idk", "contradicts_self", "impatient", "defers_to_client"}
    assert set(PERSONAS) == expected


def test_every_persona_answer_matches_the_ask_user_answer_contract():
    valid_kinds = {"answered", "dont_know", "decide_later", "not_relevant"}
    for factory in PERSONAS.values():
        persona = factory()
        answer = persona.answer(_sample_question(), round_number=1)
        assert answer["answer_kind"] in valid_kinds
        if answer["answer_kind"] in ("answered", "not_relevant"):
            assert (answer.get("answer_text") or "").strip(), f"{persona.name} produced an empty answer_text"


# ---------------------------------------------------------------------------
# Done when: persona responses are deterministic and reproducible across
# runs.
# ---------------------------------------------------------------------------


def test_persona_responses_are_deterministic_given_the_same_question_sequence():
    questions = [
        _sample_question(id="Q-001", target_areas=["scope_in"], round=1),
        _sample_question(id="Q-002", target_areas=["success"], round=2, text="How will we measure success?", suggested_options=[], recommended_default=None),
        _sample_question(id="Q-003", target_areas=["scope_in"], round=4, text="Confirming scope_in again — same as before?"),
        _sample_question(id="Q-004", target_areas=["nfr"], round=4, text="What uptime is required?", suggested_options=["99.9%", "99.99%"]),
    ]

    for name, factory in PERSONAS.items():
        persona_a = factory()
        first_run = [persona_a.answer(q, round_number=q["round"]) for q in questions]

        persona_b = factory()
        second_run = [persona_b.answer(q, round_number=q["round"]) for q in questions]

        assert first_run == second_run, f"{name} was not deterministic across two fresh instances"
