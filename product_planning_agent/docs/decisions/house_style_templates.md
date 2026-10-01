# Decision — No existing Coditas requirement/story templates

**Date:** 2026-09-23
**Resolves:** T04 (`completed_tasks/t04_config_areas_profiles_house_style.md`) · DESIGN.md §6.7 ·
open decision #1 on the build board

## Question

Do Coditas-wide requirement/story templates already exist that this tool should adopt, rather than
designing its own?

## Answer: no.

No existing Coditas template was found to adopt. T04 defines this project's own default house
style instead — a requirement template deliberately close to the canonical ledger schema, so the
export mapping starts near-identity:

```
ID · statement · type · status · confidence (+ basis) · priority
covers_areas · derived_from · depends_on
custom_fields: {}        <- empty by default; where a client template's extras land
```

## Consequence

House style is designed to be *replaced*, not permanent: it is three things at the boundary — an
export mapping, a `custom_fields` dict validated against `config/house_style.yaml`, and a
terminology map (`ppa/config/house_style.py`). The canonical schema itself never changes. If a real
Coditas-wide template appears later, adopting it is a config change, not a rewrite — that was the
whole point of keeping style at the edge instead of baking it into the ledger schema.

## How to re-verify

If a Coditas template set does appear later, compare its field list against the canonical schema
above and update `config/house_style.yaml`'s `requirement`/`story` mappings — no code change should
be required for that alone.
