# 4. Skills and memory

[← Subagents and approvals](03-subagents-and-approvals.md) · [Next: A sandbox per thread →](05-sandbox-per-thread.md)

A deep agent's instructions come from three places:

| Source | When it's loaded | Used for |
|---|---|---|
| `system_prompt` | Always | Who the agent is, and environment facts (the sandbox, how to install packages) |
| **Memory** (`AGENTS.md`) | Always | Persona, team, standing rules |
| **Skills** (`skills/*/SKILL.md`) | Only when a task matches | Step-by-step playbooks |

```python
create_deep_agent(
    ...,
    system_prompt=SYSTEM_PROMPT,
    memory=["/AGENTS.md"],
    skills=["/skills"],
)
```

## Memory: `AGENTS.md`

`AGENTS.md` is the agent's operating manual. It's added to every model call,
so keep it to things that are **always** true:

- who Jane is, and what "my customers" means (`SupportRepId = 3`)
- the team table: which specialist owns which system
- which actions need approval, and that a chat message doesn't count as approval
- ground rules: exact prices, save files under `/outputs/`, add timestamps to file names

Because it's a file on the backend and not a string in code, an agent *could*
edit its own memory. The main agent doesn't need to, but chinook-analyst
does.

### The analyst's own memory

```python
"middleware": [
    MemoryMiddleware(
        backend=backend,
        sources=["/agents/chinook-analyst/AGENTS.md"],
    )
],
```

The first time it's asked something, the analyst calls `introspect_schema`
and **writes the schema to its own `AGENTS.md`**. On later tasks in the same
sandbox the schema is already in memory, which saves a tool call and reduces
guessed table names.

`backend=backend` is important: the memory has to be on the **same
backend** (the thread's sandbox) as the main agent, or the analyst would save
its notes in one place and look for them in another. This is why
`build_subagents` takes `backend` as an argument instead of defining the
subagents at import time.

## Skills: loaded when needed

A skill is a folder containing a `SKILL.md` with YAML front matter:

```markdown
---
name: rfq-quote
description: "Turn a customer's request for quote (RFQ) email into a priced,
  reviewed quote and a draft reply. Use whenever a customer asks for pricing..."
---

# Request for Quote (RFQ)
...
```

The agent only sees each skill's **name and description** at first. When a
request matches, it reads the full `SKILL.md` with `read_file` and follows it.
This keeps the prompt small even with many skills.

**The description decides when a skill is used.** Write it as "what this
does + when to use it", with the phrases people actually type ("territory
report", "how are my accounts doing").

### What makes a good skill

Look at `skills/territory-report/SKILL.md`:

- **Numbered steps** the agent can turn into todos.
- **The specialist to use for each step** ("Ask **chinook-analyst** for...").
- **Exact commands where precision matters**, e.g. the timestamp expression,
  so it's never improvised.
- **Reasons for the rules.** "Refer to the image by its bare filename ...
  only a relative path will work" explains *why*, which helps the model handle
  cases the rule doesn't cover.

### How skills reach the sandbox

The agent's filesystem is the sandbox, so `skills/` and `AGENTS.md` on your
machine have to be **copied into it**. `agent.py` does this once, when a
thread's sandbox is first created:

```python
async def _sandbox_backend(thread_id: str) -> LangSmithSandbox:
    sandbox, is_new = await asyncio.to_thread(_get_or_create_sandbox, f"thread-{thread_id}")
    backend = LangSmithSandbox(sandbox)
    if is_new:
        await asyncio.to_thread(_upload_skills_and_memory, backend)
    return backend
```

This means **editing a skill only affects new threads.** Start a new chat
after changing a `SKILL.md`.

## Try it yourself

- Write a `customer-lookup` skill: given a name, summarize that customer's
  history and favorite genres. Start a new thread and ask about a customer
  (e.g. "Tell me about Luís Gonçalves").
- Remove the "Why" sentences from the territory-report skill and see whether
  the chart still shows up correctly, both in the chat and in the downloaded
  report.
