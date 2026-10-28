# 7. Connecting email with MCP

[← Background tasks](06-background-newsletter.md) · [Back to README](../../README.md)

The agent reads and drafts email through the
**[Model Context Protocol](https://modelcontextprotocol.io) (MCP)**, an open
standard for exposing tools to AI applications. This project uses a small
mock mail server so everything works offline, without Gmail or OAuth. The
agent itself doesn't need to change to use a real one.

## The server

`mail_server/mock_mail_server.py` uses `FastMCP` from the `mcp` package:

```python
mcp = FastMCP("mock-mail", host="127.0.0.1", port=5002)

@mcp.tool()
def mail_list_messages(query: str = "") -> list[dict]:
    """List inbox messages. ..."""

@mcp.tool()
def mail_read_message(message_id: str) -> dict: ...

@mcp.tool()
def mail_create_draft(to: str, subject: str, body: str) -> dict:
    """Save a reply in the drafts folder. This never sends anything. ..."""

mcp.run(transport="streamable-http")
```

State is kept in `mail_server/mail_store.json`, which is filled from
`seeds/*.json` on first use. There is **no send tool**, so the agent can only
ever create drafts.

## The client side

In `agent.py`:

```python
MAIL_SERVER = {"transport": "streamable-http", "url": "http://127.0.0.1:5002/mcp"}

mail_client = MultiServerMCPClient({"mock-mail": MAIL_SERVER})
mail_tools = await mail_client.get_tools()
```

`langchain-mcp-adapters` turns each MCP tool into a regular LangChain tool.
They're given to **inbox-manager only**, with `mail_create_draft` requiring
approval (chapter 3).

This runs inside `make_graph`, so the mail server must be running **before**
`langgraph dev` handles a request. That's why `start.sh` starts it first and
waits for port 5002.

## Testing with your own emails

```bash
# Add an email
uv run python mail_server/send_to_inbox.py \
  --from "Ana Souza <ana@cafe.example>" \
  --subject "Bossa nova for our café" \
  --body "Hi Jane, could you quote 25 Latin tracks and 10 Jazz tracks?"

# Start over
uv run python mail_server/send_to_inbox.py --reset
```

Then ask the agent: *"Any new quote requests?"* Saved drafts appear in the
`drafts` list in `mail_server/mail_store.json`.

## Using a real mailbox

Because inbox-manager only knows tool names and descriptions, you can replace
the mock with a real mail MCP server (for example, a Gmail MCP server):

1. Change `MAIL_SERVER` to point to the real server (URL or `stdio`
   command, plus authentication).
2. Update the tool names in `INBOX_PROMPT` and the `interrupt_on` key in
   `subagents.py` to match the new server's draft tool.
3. **Keep draft creation behind approval.** Check that the new server can't
   send email without approval. If it has a send tool, don't give it to the
   agent, or put it behind `interrupt_on` too.

## Where to go next

- Add a tool for **marking messages as handled**, so "any new quote
  requests?" skips ones already answered.
- Put skill changes in a pull request and write **evals** in LangSmith: a set
  of example emails with expected totals, scored automatically.
- **Deploy** to LangGraph Platform. The same `langgraph.json` works there.
