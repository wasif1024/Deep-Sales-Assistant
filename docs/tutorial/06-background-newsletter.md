# 6. Background tasks: the newsletter

[← A sandbox per thread](05-sandbox-per-thread.md) · [Next: Connecting email with MCP →](07-mail-over-mcp.md)

Researching four genres on the web and writing a newsletter takes a few
minutes. With a normal subagent, the chat would be blocked the whole time.
This chapter shows how the newsletter runs **in the background** as an
**async subagent**, while Jane keeps working.

## Normal subagents vs. async subagents

| | Normal (`task`) | Async (`start_async_task`) |
|---|---|---|
| Runs | Inside the current run | As a **separate run** on its own thread |
| The caller | Waits for the result | Gets a task ID immediately |
| Getting the result | It's the tool's return value | `check_async_task(task_id)` later |
| Defined as | A dict in `subagents=[...]` | **A separate graph** in `langgraph.json` |

## 1. Register a second graph

```json
"graphs": {
  "agent": "./agent.py:make_graph",
  "newsletter-agent": "./newsletter_agent_graph.py:graph"
}
```

`newsletter_agent_graph.py` is a complete deep agent. It has its *own* normal
subagent, `genre-researcher`, which it calls **once per genre in the same
turn**, so the research runs in parallel:

```python
graph = create_deep_agent(
    model=strong_model,
    tools=[markdown_to_html],
    system_prompt=NEWSLETTER_AGENT_PROMPT,
    subagents=[_genre_researcher],
    backend=_backend,
    name="newsletter-agent",
)
```

The researchers save raw search results to `/research/<genre>/sources.md` and
return only a short segment. That keeps the bulky material out of the
editor's context.

## 2. Give the main agent the async-task tools

```python
AsyncSubAgentMiddleware(
    async_subagents=[{
        "name": "newsletter-agent",
        "description": "Researches the chosen music genres and builds ...",
        "graph_id": "newsletter-agent",
    }]
)
```

This adds `start_async_task`, `check_async_task`, and `list_async_tasks`. It
starts the job through the LangGraph SDK on the **same server**, which is why
`start.sh` runs:

```bash
uv run langgraph dev --n-jobs-per-worker 10
```

Each background task occupies a worker slot for its entire run. With the
default of one slot, the newsletter would take it, and Jane's next message
would have to wait until the newsletter finished.

## 3. Storage for the background job

The newsletter graph doesn't use the sandbox. It uses a `StoreBackend`
namespaced by its own thread ID:

```python
_backend = StoreBackend(
    namespace=lambda rt: (get_config()["configurable"]["thread_id"], "research")
)
```

Every `start_async_task` creates a new thread, so each newsletter's research
is automatically kept separate. The lambda is only called when the store is
used during a run, so `graph` can be a plain module-level object instead of a
factory.

## 4. The skill handles the details

`skills/weekly-newsletter/SKILL.md` handles the situations that go wrong in
practice:

- **Start it once, then end the turn.** Don't poll, and don't do the research
  yourself.
- **Use `list_async_tasks()` to get the ID**, not memory. Long conversations
  get summarized, and a task ID from twenty messages ago may be gone.
- **Save only once.** Jane may ask "is it ready?" twice, so `glob` for an
  existing file before writing.
- **Save the HTML exactly as returned.** The newsletter agent's prompt makes
  it reply with *only* HTML, because any extra sentence would end up in the
  file.

## Try it yourself

- Start the newsletter, then immediately ask for a territory report. Both
  should progress at the same time.
- In LangSmith, find the newsletter's separate trace and the parallel
  genre-researcher calls inside it.
- Write a `customer-digest` async subagent that summarizes a week of a
  customer's purchases. You'll need a graph file, a `langgraph.json` entry,
  and an entry in `async_research.py`.
