from evaluations import _evaluation_output, required_facts, required_tools


def test_evaluation_output_reads_final_answer_and_nested_tool_calls():
    chunks = [
        {
            "event": "values",
            "data": {
                "messages": [
                    {"type": "human", "content": "Find the customer."},
                    {
                        "type": "ai",
                        "content": "The customer is Jane Doe.",
                        "tool_calls": [{"name": "query_database"}],
                    },
                ]
            },
        },
        {
            "event": "debug",
            "data": {
                "payload": {
                    "messages": [
                        {
                            "type": "ai",
                            "tool_calls": [
                                {"function": {"name": "mail_search"}}
                            ],
                        }
                    ]
                }
            },
        },
    ]

    assert _evaluation_output(chunks) == {
        "answer": "The customer is Jane Doe.",
        "tool_calls": ["query_database", "mail_search"],
    }


def test_required_tools_checks_dataset_expectations():
    run = {"outputs": {"tool_calls": ["query_database"]}}
    example = {"outputs": {"required_tools": ["query_database", "mail_search"]}}

    result = required_tools(run, example)

    assert result["score"] == 0
    assert "mail_search" in result["comment"]


def test_required_facts_checks_final_response():
    run = {"outputs": {"answer": "The 10% discount applies to 50 tracks."}}
    example = {"outputs": {"required_facts": ["10% discount", "50 tracks"]}}

    assert required_facts(run, example)["score"] == 1
