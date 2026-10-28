"""The mock mailbox and its MCP tools (mail_server/)."""

import mock_mail_server as server


def test_first_load_seeds_the_inbox(temp_mailbox):
    store = temp_mailbox.load_store()
    assert len(store["inbox"]) == 1
    assert store["drafts"] == []


def test_list_messages_returns_summaries(temp_mailbox):
    [summary] = server.mail_list_messages()
    assert set(summary) == {"id", "from", "subject", "date", "snippet"}
    assert len(summary["snippet"]) <= 141


def test_list_messages_filters_by_query(temp_mailbox):
    sender = temp_mailbox.load_store()["inbox"][0]["from"]
    assert len(server.mail_list_messages(sender.split()[0].upper())) == 1
    assert server.mail_list_messages("no-such-text-anywhere") == []


def test_read_message(temp_mailbox):
    [summary] = server.mail_list_messages()
    message = server.mail_read_message(summary["id"])
    assert message["body"].startswith(summary["snippet"].rstrip("…"))


def test_read_missing_message(temp_mailbox):
    assert "error" in server.mail_read_message("msg-999")


def test_create_draft_saves_and_never_sends(temp_mailbox):
    result = server.mail_create_draft("a@b.example", "Re: Quote", "Hello")
    assert result["status"] == "draft_saved"

    store = temp_mailbox.load_store()
    assert store["drafts"][0]["id"] == result["draft_id"] == "draft-1"
    assert len(store["inbox"]) == 1  # nothing added or sent


def test_no_send_tool_exists():
    assert not any("send" in name for name in dir(server) if name.startswith("mail_"))


def test_next_id_counts_by_prefix(temp_mailbox):
    messages = [{"id": "msg-1"}, {"id": "draft-1"}, {"id": "msg-2"}]
    assert temp_mailbox.next_id(messages, "msg") == "msg-3"
    assert temp_mailbox.next_id(messages, "draft") == "draft-2"
