# Decision — Subscription auth and web search on the Agent SDK

**Date:** 2026-09-23
**Resolves:** T01 steps 1 and 2 · DESIGN.md §0.1 · open decision #3 on the build board
**Probe script:** `scripts/verify_auth.py` (re-runnable)

## Environment at time of test

| | |
|---|---|
| OS | Windows 11 Pro 10.0.26200 |
| Python | 3.13.13 (project `.venv`) |
| `claude-agent-sdk` | **0.2.158** |
| Claude Code CLI | 2.1.280 |
| `ANTHROPIC_API_KEY` | **unset** (confirmed by the script at runtime) |

## Question 1 — Does the Agent SDK run on Claude Code subscription auth, with no API credits?

**Answer: YES.**

A single `query()` call with `allowed_tools=[]` and `max_turns=1` returned `'AUTH_OK'` with no
API key present in the environment. The SDK spawns the Claude Code CLI process and inherits the
CLI's existing login, exactly as §0.1 predicted.

**Consequence:** the zero-cost development path holds. Phases A and B (T02–T19) are plain Python
with `pytest` and need no model at all; the model-dependent surfaces run on the subscription.

**Caveat worth knowing:** `ResultMessage.total_cost_usd` still reports a figure (0.17 and 0.14 USD
for the two probes). With no API key present this is the SDK's *equivalent-cost* accounting, not a
metered charge against API credits. Treat it as a useful relative signal when tuning eval runs
(T34, open decision #2) — not as a bill.

## Question 2 — Is web search reachable on that same auth path?

**Answer: YES.**

The second probe asked for a live lookup with `allowed_tools=["WebSearch"]`. Tools actually
invoked: `['ToolSearch', 'WebSearch']`. The model returned a real headline dated 2026-09-22 with
source links — content it could not have produced from training data alone.

**Consequence:** **Guidance Mode (T28) and Research Mode (T29) ship with research from day one,
not degraded.** Open decision #3 is closed.

The `ResearchProvider` degradation path in §6.5 is still worth building as designed — it is the
fallback for search being rate-limited, erroring, or turned off by config, not for it being
absent. But it is no longer the day-one default.

## How to re-verify

```
cd product_planning_agent
.venv/Scripts/python.exe scripts/verify_auth.py
```

Re-run this if the SDK major version changes, if Anthropic changes subscription terms for SDK use,
or if model calls start failing in a way that looks like auth. If the answer to question 1 ever
flips to NO, the plan still holds but the budget does not — flag it before continuing, and switch
`ModelProvider` to the API-key path (one file, by design).
