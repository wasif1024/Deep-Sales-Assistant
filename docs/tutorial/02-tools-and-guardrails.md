# 2. Tools and guardrails

[← Architecture](01-architecture.md) · [Next: Subagents and approvals →](03-subagents-and-approvals.md)

Tools are how the agent acts on the world. This chapter covers the custom
tools in `tools/` and, just as important, what each one **refuses** to do.

A rule that applies throughout: **anything a model produces is untrusted
input.** SQL written by a model, or text from a web search, is handled like
input from a stranger.

## Defining a tool

A tool is a Python function with the `@tool` decorator. The model sees its
name, its arguments, and its docstring, so the docstring is effectively part
of the prompt:

```python
from langchain.tools import tool

@tool
def query_chinook(sql: str) -> str:
    """Run one read-only SELECT query on the Chinook database.

    Returns the rows as a JSON array of objects. ...
    """
```

## `query_chinook`: three layers of protection

The analyst writes its own SQL, which is flexible but risky. `tools/sql.py`
protects the database in three ways, each of which would stop a destructive
query on its own:

```python
_READ_ONLY_URI = f"file:{DB_PATH}?mode=ro"          # 1. read-only connection

if not lowered.startswith(("select", "with")):       # 2. SELECT/WITH only
    return json.dumps({"error": "Only SELECT queries are allowed."})
if ";" in statement:                                  #    one statement only
    return json.dumps({"error": "Only one statement is allowed."})
if any(f" {word} " in f" {lowered} " for word in _WRITE_KEYWORDS):  # 3. no write keywords
    return json.dumps({"error": "The query contains a write keyword."})
```

Errors are **returned as data, not raised**. The model reads
`{"error": "SQL error: no such table: invoices"}`, corrects itself, and tries
again. The analyst's prompt asks for exactly this (see chapter 3).

Try it:

```bash
uv run python -c "from tools.sql import query_chinook; print(query_chinook.invoke({'sql': 'DROP TABLE Customer'}))"
# {"error": "Only SELECT queries are allowed."}
```

## `add_customer`: the only write

There's one deliberate exception to "read only", and it's tightly limited:

- It uses a **parameterized** `INSERT` (`VALUES (?, ?, ...)`), so values
  can't inject SQL.
- It can only write to the `Customer` table.
- `SupportRepId` is **set in code** (`REP_EMPLOYEE_ID = 3`), not taken from
  the model, so the agent can't assign customers to another rep.
- It checks for an existing customer with the same email first.
- It needs **human approval**, which is set up where the subagent is defined
  ([chapter 3](03-subagents-and-approvals.md)).

## `introspect_schema`: learning the database

Instead of putting the whole schema in the prompt, the analyst can ask for
it:

```python
@tool
def introspect_schema() -> str:
    """Return the database schema: the CREATE statement for every table. ..."""
```

It calls this once, then saves the result to its memory file, so later
conversations don't have to look it up again
([chapter 4](04-skills-and-memory.md)).

## `markdown_to_html`: sanitizing web content

The newsletter is assembled from web search results, which could contain
`<script>` tags or `onerror=` attributes. `tools/html.py` keeps the page
template (which we wrote and trust) separate from the body (which we don't):

```python
body = md.markdown(markdown_text, extensions=["tables", "fenced_code"])
return _PAGE.format(title=title, body=nh3.clean(body))
```

[`nh3`](https://github.com/messense/nh3) removes everything except a safe
set of HTML tags and attributes.

## `internet_search`: dealing with flaky networks

`tools/search.py` wraps Tavily. The genre researchers run several searches in
parallel, and a shared HTTP client sometimes reused connections the server
had already closed. The fix is a new client per call, plus a few retries:

```python
client = TavilyClient(api_key=os.environ["TAVILY_API_KEY"])
for attempt in range(_MAX_ATTEMPTS):
    try:
        return client.search(query, max_results=max_results, topic="news")
    except RequestsConnectionError as e:
        ...
```

The module is only imported when `TAVILY_API_KEY` is set, so without a key
the rest of the agent still works.

## Code interpreter: exact arithmetic

Models make arithmetic mistakes. `agent.py` adds a JavaScript code
interpreter (`langchain-quickjs`) so the agent can calculate totals with
real code:

```python
middleware = [CodeInterpreterMiddleware(ptc=["execute", "write_file"])]
```

`AGENTS.md` and the `rfq-quote` skill both say to use it for every money
calculation.

## Try it yourself

- Add a `top_tracks_by_genre(genre: str, limit: int)` tool that runs a fixed,
  parameterized query, and give it to chinook-analyst. Compare its results
  with the analyst's free-form SQL.
- Change `_WRITE_KEYWORDS` and see which queries get through. Notice that the
  read-only connection still blocks them.
