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

- [x] Twelve areas defined as data, editable without touching logic
- [x] `critical_areas()` returns **different** sets for `engineer` and `product` profiles
- [x] Swapping the style config changes rendered output and required custom fields
- [x] Zero changes to `ppa/ledger/models.py` are needed to support a new style
- [x] A `custom_fields` dict missing a required field is rejected
- [x] The default template is defined and documented as *replaceable*, not final
- [x] `custom_fields` is validated and empty-by-default — the seam exists before anything needs it

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

---

## Build record (completed 2026-09-23)

### A dependency the task implies but T01 never listed

`config/templates/coditas_requirement.md.j2` and the `.j2` extension throughout DESIGN.md §6.3
commit to Jinja2 template syntax, but T01's pyproject dependency list (`pydantic`, `typer`, `rich`,
`claude-agent-sdk`, `pyyaml`, `pytest`, `pytest-cov`, `freezegun`) never included a template engine
— and this task's own Done-when box ("swapping the style config changes rendered output") cannot
be satisfied without one. Hand-rolling substitution instead of using the library the file extension
already promises would be worse, not more minimal. Added `jinja2>=3.1` to `pyproject.toml`. Logged
in `blockers.md` as a decision, not just a silent `pip install`.

### A profile → critical-areas table, filled by assumption (same pattern as T02's decision #7)

DESIGN.md §6.1 gives exactly one example sentence ("an engineer answers `nfr`/`data`/`platform`
directly ... product inverts") and no full table. Built one, flagged for confirmation rather than
treated as settled:

| | Always critical | + role-specific |
|---|---|---|
| **engineer** | `problem`, `users` (§6.4: never assume, any profile) | `nfr`, `data`, `platform` |
| **product** | `problem`, `users` | `success`, `scope_in`, `scope_out` |
| **mixed** | `problem`, `users` | union of both extras |

`technical_depth` and `domain_familiarity` are accepted on `UserProfile` per the task's own class
shape but don't currently narrow `critical_areas()` further — nothing in the design calls for that
yet, and narrowing further would be a second guess stacked on the first. Logged in `blockers.md`
for the same reason decision #7 was: it's a real gap filled to unblock the build, not something to
bury in a docstring as if it were beyond question.

### Repo hygiene widened for the new file type

`config/templates/coditas_requirement.md.j2` is the first `.j2` file in the repo.
`test_no_credential_values_are_committed` (T01/T06) now scans `.j2` alongside the existing
suffixes — a template is free text like `.md`, and a future client template pasted in during style
customization is exactly the kind of file a credential could hide in unnoticed. No model-id scan
change needed: a template renders data, it doesn't configure the model seam.

### What exists now

```
ppa/config/areas.py                          # AreaStatus, CoverageArea, AREAS (12), AREAS_BY_KEY
ppa/config/profiles.py                       # UserProfile, critical_areas()
ppa/config/house_style.py                    # HouseStyle, load/validate/render
config/house_style.yaml                      # shipped default, required_custom_fields: []
config/templates/coditas_requirement.md.j2   # default requirement template
tests/test_config/                           # 29 tests (areas, profiles, house_style)
```

### Verification

```
$ .venv/Scripts/python.exe -m pytest tests/test_config/ -> 29 passed
$ .venv/Scripts/python.exe -m pytest                     -> 172 passed
```

No changes to `ppa/ledger/models.py` — verified by `git status` showing it untouched by this
commit, not just by argument.

### Notes for whoever picks up T05

- `ppa/config/house_style.py` imports `Requirement` from `ppa/ledger/models.py` for rendering
  only — it reads fields, it never requires new ones.
- If decision from this build (the critical-areas table) gets overturned, only
  `ppa/config/profiles.py`'s `_ROLE_CRITICAL_EXTRA` dict needs to change — nothing downstream
  depends on the specific areas yet.
