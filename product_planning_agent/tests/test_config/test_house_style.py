"""House style tests (T04)."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

from ppa.config.house_style import (
    DEFAULT_HOUSE_STYLE_PATH,
    ExportStyle,
    HouseStyle,
    MissingRequiredCustomFields,
    RequirementStyle,
    load_house_style,
    render_requirement,
    validate_custom_fields,
)
from ppa.ledger.models import Requirement

NOW = datetime(2026, 9, 23, 12, 0, 0, tzinfo=timezone.utc)


def _requirement(**overrides) -> Requirement:
    base = dict(
        id="REQ-001",
        version=1,
        created_at=NOW,
        updated_at=NOW,
        created_by="user:shubham",
        updated_by="user:shubham",
        history=[],
        statement="The system must support SSO login.",
        type="functional",
        priority="must",
        confidence="HIGH",
        confidence_basis="user said it directly",
    )
    base.update(overrides)
    return Requirement(**base)


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def test_default_house_style_loads_and_validates():
    style = load_house_style()
    assert style.name == "coditas_default"
    assert style.requirement.required_custom_fields == []
    assert style.requirement.template == "templates/coditas_requirement.md.j2"
    assert style.export.format == "markdown"


def test_default_house_style_path_points_at_the_shipped_file():
    assert DEFAULT_HOUSE_STYLE_PATH.name == "house_style.yaml"
    assert DEFAULT_HOUSE_STYLE_PATH.exists()


def test_missing_config_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_house_style(tmp_path / "absent.yaml")


def test_house_style_rejects_unknown_top_level_fields(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text(
        "name: x\nrequirement: {template: t.j2}\nexport: {format: markdown}\nnot_a_field: 1\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception):
        load_house_style(bad)


# ---------------------------------------------------------------------------
# Done when: a custom_fields dict missing a required field is rejected.
# ---------------------------------------------------------------------------


def _style_requiring(*fields: str) -> HouseStyle:
    return HouseStyle(
        name="test_style",
        terminology={"requirement": "Feature Brief"},
        requirement=RequirementStyle(
            required_custom_fields=list(fields), template="coditas_requirement.md.j2"
        ),
        export=ExportStyle(format="markdown"),
    )


def test_default_style_requires_nothing_so_empty_custom_fields_passes():
    style = load_house_style()
    validate_custom_fields({}, style)  # must not raise


def test_missing_required_custom_field_is_rejected():
    style = _style_requiring("module", "client_ref")
    with pytest.raises(MissingRequiredCustomFields) as exc_info:
        validate_custom_fields({"module": "billing"}, style)
    assert exc_info.value.missing == ["client_ref"]


def test_all_required_custom_fields_present_passes():
    style = _style_requiring("module", "client_ref")
    validate_custom_fields({"module": "billing", "client_ref": "ACME-42"}, style)  # no raise


def test_extra_custom_fields_beyond_required_are_fine():
    style = _style_requiring("module")
    validate_custom_fields({"module": "billing", "notes": "extra"}, style)  # no raise


# ---------------------------------------------------------------------------
# Done when: swapping the style config changes rendered output and required
# custom fields; zero changes to ppa/ledger/models.py needed.
# ---------------------------------------------------------------------------


def test_render_requirement_with_default_style_produces_markdown():
    style = load_house_style()
    output = render_requirement(_requirement(), style)
    assert "Requirement REQ-001" in output
    assert "The system must support SSO login." in output
    assert "must" in output


def test_render_reflects_custom_fields_when_present():
    style = load_house_style()
    req = _requirement(custom_fields={"module": "billing"})
    output = render_requirement(req, style)
    assert "module: billing" in output


def test_render_shows_empty_custom_fields_by_default():
    style = load_house_style()
    output = render_requirement(_requirement(), style)
    assert "{}" in output


def test_swapping_terminology_changes_rendered_output(tmp_path):
    (tmp_path / "custom.md.j2").write_text(
        "# {{ terminology.requirement }} {{ requirement.id }}\n{{ requirement.statement }}\n",
        encoding="utf-8",
    )
    style = HouseStyle(
        name="client_style",
        terminology={"requirement": "Feature Brief"},
        requirement=RequirementStyle(required_custom_fields=[], template="custom.md.j2"),
        export=ExportStyle(format="markdown"),
    )
    output = render_requirement(_requirement(), style, templates_dir=tmp_path)
    assert "Feature Brief REQ-001" in output
    assert "Requirement REQ-001" not in output


def test_swapping_style_changes_required_custom_fields():
    lenient = load_house_style()
    strict = _style_requiring("client_ref")

    validate_custom_fields({}, lenient)  # passes under the default style
    with pytest.raises(MissingRequiredCustomFields):
        validate_custom_fields({}, strict)  # the same dict fails under a stricter style


def test_rendering_never_requires_touching_ledger_models():
    """No import of, or dependency on, anything beyond Requirement's already
    -shipped fields — proven by using an unmodified Requirement instance."""
    style = load_house_style()
    req = _requirement()
    assert set(Requirement.model_fields) >= {
        "statement",
        "type",
        "status",
        "confidence",
        "confidence_basis",
        "priority",
        "covers_areas",
        "derived_from_answers",
        "depends_on_assumptions",
        "depends_on_decisions",
        "custom_fields",
    }
    render_requirement(req, style)  # must not raise
