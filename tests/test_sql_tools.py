"""The database guardrails described in docs/tutorial/02-tools-and-guardrails.md."""

import json
import sqlite3

import pytest

from tools.sql import REP_EMPLOYEE_ID, add_customer, introspect_schema, query_chinook


def run_query(sql: str):
    return json.loads(query_chinook.invoke({"sql": sql}))


def test_select_returns_rows(temp_db):
    rows = run_query("SELECT COUNT(*) AS n FROM Customer WHERE SupportRepId = 3")
    assert rows == [{"n": 24}]


def test_with_query_is_allowed(temp_db):
    rows = run_query("WITH g AS (SELECT Name FROM Genre) SELECT COUNT(*) AS n FROM g")
    assert rows[0]["n"] > 0


@pytest.mark.parametrize(
    "sql",
    [
        "DELETE FROM Customer",
        "DROP TABLE Customer",
        "UPDATE Track SET UnitPrice = 0",
        "PRAGMA writable_schema = 1",
        "SELECT 1; DROP TABLE Customer",
        "SELECT * FROM Customer WHERE 1 = 1 UNION SELECT * FROM Customer; DELETE FROM Invoice",
    ],
)
def test_writes_are_rejected(temp_db, sql):
    assert "error" in run_query(sql)


def test_connection_is_read_only_even_if_checks_are_bypassed(temp_db):
    from tools.sql import _read_only_connection

    conn = _read_only_connection()
    with pytest.raises(sqlite3.OperationalError):
        conn.execute("DELETE FROM Customer")
    conn.close()


def test_sql_errors_are_returned_not_raised(temp_db):
    result = run_query("SELECT * FROM invoices")
    assert "no such table" in result["error"]


def test_introspect_schema_lists_tables(temp_db):
    schema = introspect_schema.invoke({})
    for table in ("Customer", "Invoice", "Track", "Genre"):
        assert f"CREATE TABLE [{table}]" in schema


def test_add_customer_assigns_jane(temp_db):
    result = json.loads(
        add_customer.invoke(
            {"first_name": "Test", "last_name": "User", "email": "test.user@example.com"}
        )
    )
    assert result["status"] == "created"

    conn = sqlite3.connect(temp_db)
    rep = conn.execute(
        "SELECT SupportRepId FROM Customer WHERE CustomerId = ?", (result["customer_id"],)
    ).fetchone()[0]
    conn.close()
    assert rep == REP_EMPLOYEE_ID


def test_add_customer_rejects_duplicate_email(temp_db):
    existing = run_query("SELECT Email FROM Customer LIMIT 1")[0]["Email"]
    result = json.loads(
        add_customer.invoke(
            {"first_name": "Dup", "last_name": "User", "email": existing.upper()}
        )
    )
    assert "already exists" in result["error"]


def test_add_customer_requires_valid_email(temp_db):
    result = json.loads(
        add_customer.invoke({"first_name": "No", "last_name": "Email", "email": "nope"})
    )
    assert "error" in result


def test_add_customer_values_cannot_inject_sql(temp_db):
    before = run_query("SELECT COUNT(*) AS n FROM Invoice")[0]["n"]
    add_customer.invoke(
        {
            "first_name": "Robert'); DELETE FROM Invoice; --",
            "last_name": "Tables",
            "email": "bobby@example.com",
        }
    )
    assert run_query("SELECT COUNT(*) AS n FROM Invoice")[0]["n"] == before
