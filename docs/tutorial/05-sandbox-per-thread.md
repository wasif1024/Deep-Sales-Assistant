# 5. A sandbox per thread

[← Skills and memory](04-skills-and-memory.md) · [Next: Background tasks →](06-background-newsletter.md)

The agent writes Python scripts and runs them, for example to draw charts.
Running model-written code on your own machine is risky. This chapter shows
how `agent.py` gives **each conversation thread its own LangSmith sandbox**,
an isolated cloud environment that serves as both its filesystem and the
place its commands run.

## Backends decide where files live

Every deep agent has a **backend** behind its filesystem tools:

| Backend | Files live in | `execute`? |
|---|---|---|
| `StateBackend` | The graph state, in memory | No |
| `StoreBackend` | LangGraph's long-term store | No |
| `LangSmithSandbox` | A remote sandbox | **Yes** |

When the backend can run commands, deepagents **adds the `execute` tool
automatically**. That's why there's no chart tool: the agent writes a script
with `write_file` and runs it with `execute`.

```text
write_file("/outputs/chart.py", "import matplotlib ...")
execute("pip install --break-system-packages matplotlib && python3 /outputs/chart.py")
```

The `--break-system-packages` flag is in the system prompt because the
sandbox's Python is externally managed. Without that hint, the first `pip
install` fails and the model has to work it out.

## One sandbox per thread: a graph factory

One shared sandbox would mix different conversations' files together. A new
sandbox per message would lose the ledger between turns. What's needed is one
sandbox **per thread**, which means the graph must know the thread ID when
it's built.

`langgraph.json` points to a **factory** instead of a ready-made graph:

```json
"graphs": { "agent": "./agent.py:make_graph" }
```

```python
@contextlib.asynccontextmanager
async def make_graph(config: RunnableConfig, runtime: ServerRuntime):
    if runtime.execution_runtime:
        thread_id = config.get("configurable", {}).get("thread_id")
        backend = await _sandbox_backend(thread_id)
    else:
        backend = StateBackend()
    ...
    yield create_deep_agent(..., backend=backend)
```

The server calls `make_graph` for every run, passing the thread's `config`.
It also calls it for things that aren't runs, like drawing the graph in Studio
or returning its schema. In those cases `runtime.execution_runtime` is `None`,
and we use an in-memory backend so that **just looking at the graph never
creates a sandbox**.

See LangSmith's
[graph rebuild docs](https://docs.langchain.com/langsmith/graph-rebuild#context-manager-factory)
for this pattern.

## Find, start, or create

`_get_or_create_sandbox` names sandboxes `thread-<thread_id>`, so the same
thread always gets the same sandbox:

| The sandbox is... | Action |
|---|---|
| `ready` | Reuse it |
| `stopped` (idle too long) | `start_sandbox`; files are kept |
| still starting | `wait_for_sandbox` |
| missing | `create_sandbox`, then upload skills and memory |

Creation also handles a **race**: two runs on a new thread can both see "no
sandbox" and both try to create one. The second create fails, so the code
lists the sandboxes again and uses the one that now exists.

## Keeping costs down

```python
SANDBOX_IDLE_TTL_SECONDS = 600            # stop after 10 idle minutes
SANDBOX_DELETE_AFTER_STOP_SECONDS = 3600  # delete an hour after stopping
```

On top of these limits, `start.sh` runs `stop_sandboxes.py` when you press
Ctrl-C. That script only stops sandboxes named `thread-*`, so it never
touches other sandboxes in your workspace.

## Getting files out: the UI panel

The chat UI's **Sandbox files** panel (`ui/src/app/api/sandbox-files`) lists
the thread's `/outputs/` folder through the LangSmith sandbox API, and
`sandbox-download` serves individual files. That's why the UI needs
`LANGSMITH_API_KEY`, and why the skills tell the agent to save deliverables
under `/outputs/`.

## Try it yourself

- Ask for a bar chart of revenue by year. Look in the trace for the
  `write_file` and `execute` calls.
- Ask: *"Run `uname -a` and `python3 --version` in your sandbox."* Compare
  with your own machine.
- Lower `SANDBOX_IDLE_TTL_SECONDS` to 60, wait two minutes, then send another
  message. Is the earlier ledger still there after the sandbox restarts?
