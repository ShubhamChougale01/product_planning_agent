"""T21 probe: does a real agent invocation actually complete through
`ppa.providers.model.ModelProvider` end to end?

Run with ANTHROPIC_API_KEY unset — subscription auth, same as
`scripts/verify_auth.py` (T01). This is a one-off verification, not library
code, and not part of the pytest suite: `ppa/orchestrator/loop.py`'s own
tests prove the outer loop's mechanics using a fixture `Agent` (see
`tests/test_agents/test_loop.py`'s own module docstring and decision #28 in
`blockers.md`), keeping the automated suite free and fast per DESIGN.md
Part 0.1. This script is what actually proves the SDK plumbing the task
header calls "Needs a model: Yes — first agent invocation" — a real
`ModelProvider`-built client, given a system prompt and zero tools, running
one real turn.
"""

import anyio
import sys

from claude_agent_sdk import AssistantMessage, ResultMessage, TextBlock

from ppa.providers.model import ModelProvider


async def main() -> int:
    provider = ModelProvider()
    print(f"provider: {provider.describe()}")

    client = provider.client(
        system_prompt="You are a smoke test. Reply with exactly this token and nothing else: TURN_OK",
        allowed_tools=[],
        max_turns=1,
    )

    text: list[str] = []
    cost: float | None = None

    async with client:
        await client.query("Confirm you are online.")
        async for msg in client.receive_response():
            if isinstance(msg, AssistantMessage):
                for block in msg.content:
                    if isinstance(block, TextBlock):
                        text.append(block.text)
            elif isinstance(msg, ResultMessage):
                cost = getattr(msg, "total_cost_usd", None)

    reply = "".join(text).strip()
    print(f"reply: {reply!r}")
    print(f"cost:  {cost}")
    ok = "TURN_OK" in reply
    print(f"-> {'PASS' if ok else 'UNEXPECTED REPLY'}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(anyio.run(main))
