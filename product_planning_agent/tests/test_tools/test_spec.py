"""ToolSpec contract tests (T13). Every Done-when box in
tasks/t13_toolspec_contract_and_registry.md that concerns `ppa/tools/spec.py`
maps to at least one test here.
"""

from __future__ import annotations

import dataclasses

from ppa.tools.spec import ToolSpec, render_description


def _full_spec(**overrides) -> ToolSpec:
    base = dict(
        name="manage_linear_issue",
        purpose="Create or update an implementation issue in Linear from an approved story.",
        inputs={
            "story_id": "str, the Delivery story's id",
            "project_key": "str, the Linear project key",
        },
        required=["story_id", "project_key"],
        optional=[],
        formats={"project_key": "^[A-Z]{2,10}$"},
        returns="{issue_url: str, issue_key: str}",
        examples=[
            'manage_linear_issue(story_id="STORY-001", project_key="ENG")',
            'manage_linear_issue(story_id="STORY-002", project_key="OPS")',
        ],
        edge_cases=["story already has a linked issue"],
        limitations=["only creates, never deletes, a Linear issue"],
        use_when=["workflow_state == PLAN_APPROVED", "the story passed validate_story"],
        do_not_use_when=[
            "the plan is draft or in review -> BUSINESS error",
            "the user is still in Discovery -> PERMISSION error",
        ],
        related_tools={
            "generate_story": "produces the story; pushes nothing",
            "validate_story": "checks a story; never creates an issue",
        },
    )
    base.update(overrides)
    return ToolSpec(**base)


def test_toolspec_has_exactly_thirteen_fields():
    field_names = {f.name for f in dataclasses.fields(ToolSpec)}
    assert field_names == {
        "name", "purpose", "inputs", "required", "optional", "formats", "returns",
        "examples", "edge_cases", "limitations", "use_when", "do_not_use_when",
        "related_tools",
    }
    assert len(field_names) == 13


def test_toolspec_is_frozen():
    spec = _full_spec()
    try:
        spec.name = "renamed"  # type: ignore[misc]
        assert False, "expected a FrozenInstanceError"
    except dataclasses.FrozenInstanceError:
        pass


def test_render_description_includes_every_field():
    spec = _full_spec()
    text = render_description(spec)

    assert spec.name in text
    assert spec.purpose in text
    assert spec.returns in text
    for input_name in spec.inputs:
        assert input_name in text
    for example in spec.examples:
        assert example in text
    for edge_case in spec.edge_cases:
        assert edge_case in text
    for limitation in spec.limitations:
        assert limitation in text
    for condition in spec.use_when:
        assert condition in text
    for condition in spec.do_not_use_when:
        assert condition in text
    for other_name, distinction in spec.related_tools.items():
        assert other_name in text
        assert distinction in text


def test_render_description_marks_required_vs_optional_inputs():
    spec = _full_spec(
        inputs={"a": "str, required field", "b": "str, optional field"},
        required=["a"],
        optional=["b"],
    )
    text = render_description(spec)
    assert "a (required)" in text
    assert "b (optional)" in text


def test_render_description_shows_format_constraint():
    spec = _full_spec()
    text = render_description(spec)
    assert "^[A-Z]{2,10}$" in text


def test_render_description_handles_no_inputs_and_no_related_tools():
    spec = _full_spec(inputs={}, required=[], optional=[], formats={}, related_tools={"x": "y"})
    text = render_description(spec)
    assert "(none)" in text  # the "no inputs" placeholder
