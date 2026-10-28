# 3. Subagents and approvals

[← Tools and guardrails](02-tools-and-guardrails.md) · [Next: Skills and memory →](04-skills-and-memory.md)

The main agent rarely does the work itself. It hands it off. This chapter
covers how the specialists are defined in `subagents.py` and how two of their
tools are set up to need human approval.

## Why use subagents?

- **Separate context.** When chinook-analyst writes and fixes five SQL
  queries, all that back-and-forth stays in *its* context. The main agent only
  gets the final answer.
- **The right model for each job.** Database lookups and reading email use
  the cheaper `model`. Checking a quote uses `strong_model`.
- **Limited access.** Each specialist gets only the tools it needs.

## Defining a subagent

A subagent is a dict passed in `subagents=[...]`:

```python
quote_reviewer = {
    "name": "quote-reviewer",
    "description": (
        "Checks a draft quote's math and pricing before it's sent. Send it "
        "the line items, discount, and total."
    ),
    "system_prompt": REVIEWER_PROMPT,
    "model": strong_model,
}
```

- **`description`** is what the *main agent* reads when choosing who to
  delegate to. Write it like a tool description.
- **`system_prompt`** is what the *subagent* reads.
- **`tools`** are what it can use. quote-reviewer has none; it only reasons
  about the numbers it's given.

The main agent delegates with the built-in `task` tool:
`task(subagent_type="quote-reviewer", description="Check this quote: ...")`.

## Requiring approval: `interrupt_on`

```python
_APPROVAL = {"allowed_decisions": ["approve", "edit", "reject"]}

chinook_analyst = {
    ...
    "tools": [query_chinook, introspect_schema, add_customer],
    "interrupt_on": {"add_customer": _APPROVAL},
}
```

When the analyst calls `add_customer`, LangGraph **pauses the run before the
tool executes** and saves its state. The UI shows the pending call. Jane can:

- **Approve**: the tool runs with the model's arguments.
- **Edit**: she changes the arguments (fixes a typo in the email address, for
  example), and the tool runs with her version.
- **Reject**: the tool doesn't run, and the model is told why.

inbox-manager is set up the same way for `mail_create_draft`.

### Asking in chat is not the same as approval

Both `AGENTS.md` and the subagent prompts say *don't ask for permission in a
chat message; just make the call*. Without that instruction, models tend to
write "Shall I add this customer?" and stop. Nothing happens, because the
approval mechanism only runs when the tool is actually called. The pause is
the request for permission.

## Why gated tools never go on the main agent

This is the most important design decision in the file. deepagents
**always** adds a `general-purpose` subagent, and it **inherits the main
agent's tools**. If `add_customer` were a main-agent tool with
`interrupt_on`, the main agent could hand the task to `general-purpose`,
which has the same tool but **not** the approval rule, and skip the approval.

Putting each gated tool *only* on the specialist that owns it means every
path to a write goes through that specialist's approval.

## Prompts aimed at specific mistakes

Each prompt is written to prevent a particular mistake seen in testing. For
example, the analyst's last paragraph:

```text
Use table and column names exactly as they appear in your memory or in the
`introspect_schema` output. Chinook table names are singular (`Invoice`,
not `invoices`). If a query fails with "no such table" ... re-check the
schema with `introspect_schema` and retry. Never guess a name.
```

Smaller models often guess plural table names. This paragraph, together with
returning errors as data (chapter 2), lets them correct themselves.

## Try it yourself

- Add a `discount-approver` subagent that must approve any discount above
  15%. What tool would it need, and where should its `interrupt_on` go?
- Reject a draft in the UI with a reason ("too formal"). Watch how
  inbox-manager and the main agent respond in the LangSmith trace.
