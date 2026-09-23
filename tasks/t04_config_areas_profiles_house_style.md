# T04 — Configuration: coverage areas, user profiles, house style

| | |
|---|---|
| **Phase** | A · Foundation (no model, no cost) |
| **Estimate** | 0.75 day |
| **Needs a model?** | No |
| **Design reference** | DESIGN.md §1.2, §6.1, §6.3, S1.4–S1.6 |

## Prerequisites

- [ ] **T02**

## Why this task exists

Three pieces of declarative config that shape agent behaviour without touching code. Coverage
areas are the denominator for progress *and* the source of every question. Profiles make
criticality role-dependent. House style keeps client templates at the edge so they never fork
the core schema.

## What to build

### 1. Coverage areas — `ppa/config/areas.py`

Twelve areas as data: `key`, `label`, `description`, `probe_hints[]`.

`problem · users · jobs · scope_in · scope_out · success · constraints · existing_system ·
platform · data · nfr · rollout`

States: `UNTOUCHED → PARTIAL → SUFFICIENT → CONFIRMED`.

**Criticality is not a field on the area.** It is a per-profile lookup (below).

### 2. User profile — `ppa/config/profiles.py`

```python
class UserProfile(BaseModel):
    role: Literal["engineer", "product", "mixed"]
    technical_depth: Literal["high", "medium", "low"]
    domain_familiarity: Literal["high", "medium", "low"]
```

`critical_areas(profile) -> set[str]`. Engineers and product people need different things nailed
down before planning can start: an engineer answers `nfr`/`data`/`platform` directly but needs
guidance on `success`; product inverts. Encode that table.

### 3. House style — `config/house_style.yaml` + loader

```yaml
name: coditas_default
terminology:
  requirement: "Requirement"
  story: "User Story"
requirement:
  required_custom_fields: [module, client_ref]
  template: templates/coditas_requirement.md.j2
story:
  template: templates/coditas_story.md.j2
  fields: [id, title, description, acceptance_criteria, estimate, priority]
export:
  format: markdown
```

The canonical schema never changes. Style is three things at the boundary: an export mapping,
a `custom_fields` dict validated against the config, and a terminology map.

**Resolved 2026-09-23: no existing Coditas templates.** So define our own standard, and design
it to be replaced rather than to be permanent — a team template may appear later, and the whole
point of keeping style at the edge is that adopting one is then a config change.

Our default requirement template — deliberately close to the canonical schema so the mapping is
near-identity at first:

```
ID · statement · type · status · confidence (+ basis) · priority
covers_areas · derived_from · depends_on
custom_fields: {}        <- empty by default; where a client template's extras land
```

Ship `custom_fields` as an empty, *validated* dict from day one even though nothing uses it.
That is the seam. If you leave it out because v1 has no client fields, adding it later means
touching every entity and every writer.

## Files touched

```
ppa/config/areas.py
ppa/config/profiles.py
ppa/config/house_style.py
config/house_style.yaml
config/templates/coditas_requirement.md.j2
tests/test_config/
```

## Done when

- [ ] Twelve areas defined as data, editable without touching logic
- [ ] `critical_areas()` returns **different** sets for `engineer` and `product` profiles
- [ ] Swapping the style config changes rendered output and required custom fields
- [ ] Zero changes to `ppa/ledger/models.py` are needed to support a new style
- [ ] A `custom_fields` dict missing a required field is rejected
- [ ] The default template is defined and documented as *replaceable*, not final
- [ ] `custom_fields` is validated and empty-by-default — the seam exists before anything needs it

## On completion

1. Every **Done when** box above is ticked — not "mostly", all of them.
2. Tests pass: `pytest tests/test_config/`
3. Commit: `git add -A && git commit -m "T04: Configuration: coverage areas, user profiles, house style"`
4. **Move this file into the completed folder:**

   ```
   Windows:  move tasks\t04_*.md completed_tasks\
   bash:     mv tasks/t04_*.md completed_tasks/
   ```

5. Open `tasks/README.md` and tick `T04` on the board.
