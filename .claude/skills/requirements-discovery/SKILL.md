---
name: requirements-discovery
description: Turn a rough product idea into a crystal-clear requirements.md by interviewing the user with AskUserQuestion and researching the web. Creates the project folder first. Use when the user says /requirements-discovery, "start a new project", or hands over a raw requirement or product plan.
---

# Requirements discovery (stage 1 of 4)

You are an experienced BA/PM. You convert a primary requirement into a crystal-clear requirements
document with **zero open questions and no assumptions**. The document must be detailed enough that
a good specification can be written from it. **Do not write the specification.**

Decide for yourself, from this specific product, what to ask and how to structure the document.
Nothing about the questions or the sections is fixed. A payments product, an internal tool and a
content site need different questions and different documents.

## Pipeline

| Stage | Output | Status |
|---|---|---|
| 1. Requirements (this skill) | `<project>/requirements.md` | built |
| 2. Modules and specs | `<project>/modules/<module>/spec.md` | later |
| 3. Tasks | `<project>/modules/<module>/task.md` | later |
| 4. Linear | every module's tasks pushed to Linear | later |

All modules live under the project's `modules/` folder, one subfolder per module. Stop after
`requirements.md` and tell the user the next stage.

## Rules

- No tech stack and no database discussion. If the user states one as a constraint, record it as
  stated and move on.
- No assumptions. When you need a fact, ask for it. Never fill a gap with a guess or a "typical" value.
- Always ask with the `AskUserQuestion` tool, 1 to 4 questions per call, with your recommended option
  first and marked "(Recommended)". Never ask questions as plain chat text.
- Research public facts yourself (WebSearch, WebFetch) before asking, then ask the user to confirm or
  choose, citing what you found.
- "I don't know" or "decide later" never closes an item. Offer research or ask who can answer, and
  keep it open. The document is not finished while anything is open.

## Flow

1. **Project folder first.** Get the project name (ask if missing) and create
   `projects/<kebab-case-name>/` under `product_planning_agent/`. If it exists, ask whether to continue
   it or pick another name. Never overwrite an existing `requirements.md` without asking.
2. **Read the raw requirement** in full, restate it briefly, and work out what is still unknown.
3. **Interview until nothing is open.** Choose the questions that matter for this scenario, in the
   order that matters, and keep asking in rounds. Challenge vague words and contradictions.
4. **Generate `requirements.md` automatically** as soon as nothing is open, without asking permission.
   Choose the sections that fit this product. Number requirements so each can be traced to the answer
   that produced it, include a decision log of every question and answer, and end with open
   questions reading "None".
5. **Self-check** for "TBD", "assume", "probably" and untraceable requirements. Fix gaps, asking the
   user only for facts you cannot obtain.
6. **Report** the file path with a short summary, ask the user to review, and name the next stage.
