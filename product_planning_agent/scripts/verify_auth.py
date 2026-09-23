"""T01 probe: does the Agent SDK run on Claude Code subscription auth, and is web search reachable?

Run with ANTHROPIC_API_KEY unset. This is a one-off verification, not library code.
"""
import anyio, os, sys
from claude_agent_sdk import (
    query, ClaudeAgentOptions, AssistantMessage, TextBlock,
    ToolUseBlock, ServerToolUseBlock, ResultMessage,
)


async def probe(prompt: str, options: ClaudeAgentOptions) -> tuple[str, list[str], float | None]:
    text, tools, cost = [], [], None
    async for msg in query(prompt=prompt, options=options):
        if isinstance(msg, AssistantMessage):
            for b in msg.content:
                if isinstance(b, TextBlock):
                    text.append(b.text)
                elif isinstance(b, (ToolUseBlock, ServerToolUseBlock)):
                    tools.append(b.name)
        elif isinstance(msg, ResultMessage):
            cost = getattr(msg, "total_cost_usd", None)
    return "".join(text).strip(), tools, cost


async def main() -> int:
    print(f"ANTHROPIC_API_KEY: {'SET' if os.environ.get('ANTHROPIC_API_KEY') else 'unset'}")

    print("\n[1] auth probe -- trivial query, no tools")
    try:
        text, _, cost = await probe(
            "Reply with exactly this token and nothing else: AUTH_OK",
            ClaudeAgentOptions(allowed_tools=[], max_turns=1),
        )
    except Exception as exc:
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        return 1
    print(f"  reply: {text!r}")
    print(f"  cost:  {cost}")
    print(f"  -> {'PASS' if 'AUTH_OK' in text else 'UNEXPECTED REPLY'}")

    print("\n[2] web-search probe -- question requiring a live lookup")
    try:
        text, tools, cost = await probe(
            "Search the web for the current UTC date and today's top technology headline. "
            "Use WebSearch. Then reply with the headline in one line.",
            ClaudeAgentOptions(allowed_tools=["WebSearch"], max_turns=6),
        )
    except Exception as exc:
        print(f"  FAIL  {type(exc).__name__}: {exc}")
        return 2
    print(f"  tools used: {tools or 'NONE'}")
    print(f"  reply: {text[:400]!r}")
    print(f"  cost:  {cost}")
    print(f"  -> {'WEB SEARCH AVAILABLE' if any('search' in t.lower() for t in tools) else 'NO WEB SEARCH OBSERVED'}")
    return 0


if __name__ == "__main__":
    sys.exit(anyio.run(main))
