"""T31 tests — `parse_answer`, the terminal input parser added to
`ppa/render/question_card.py` alongside T17's own rendering functions.
"""

from __future__ import annotations

from ppa.render.question_card import parse_answer, render_answer_summary, render_question_card


def test_plain_text_is_recorded_as_answered_verbatim():
    assert parse_answer("Stripe") == {"answer_kind": "answered", "answer_text": "Stripe"}


def test_idk_variants_parse_as_dont_know():
    for phrase in ("idk", "I don't know", "IDK", "  not sure  "):
        assert parse_answer(phrase) == {"answer_kind": "dont_know"}


def test_decide_later_variants_parse_as_decide_later():
    for phrase in ("decide later", "later", "Later"):
        assert parse_answer(phrase) == {"answer_kind": "decide_later"}


def test_not_relevant_prefix_captures_the_reason():
    result = parse_answer("not relevant: this is a v2 concern")
    assert result == {"answer_kind": "not_relevant", "answer_text": "this is a v2 concern"}


def test_answer_containing_the_word_later_is_not_misread():
    # A whole-phrase match only — "later" as a whole reply defers, but a
    # real sentence that happens to contain the word must not.
    result = parse_answer("We'll decide the vendor later this quarter")
    assert result == {"answer_kind": "answered", "answer_text": "We'll decide the vendor later this quarter"}


def test_render_functions_still_round_trip_every_affordance():
    question = {
        "text": "Which payment processor?", "why_asked": "determines integration scope",
        "suggested_options": ["Stripe", "Braintree"], "recommended_default": "Stripe",
    }
    card = render_question_card(question)
    assert "Which payment processor?" in card
    assert "why: determines integration scope" in card

    for kind in ("answered", "dont_know", "decide_later", "not_relevant"):
        summary = render_answer_summary({"answer_kind": kind, "answer_text": "Stripe"})
        assert summary
