"""Database tools for the chinook-analyst subagent.

The SQL is written by a model, so it's treated as untrusted:

* `query_chinook`: reads only. The connection is opened read-only, and the
  query must also be a single SELECT (or WITH) statement.
* `introspect_schema`: returns every table's CREATE statement, so the analyst
  can learn the schema and save it to memory.
* `add_customer`: the only write. It's a parameterized INSERT into Customer,
  always assigned to Jane, and Jane approves it first (see subagents.py).
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from langchain.tools import tool

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "chinook.db"
_READ_ONLY_URI = f"file:{DB_PATH}?mode=ro"

# Jane Peacock's EmployeeId. Her customers are those with SupportRepId = 3.
REP_EMPLOYEE_ID = 3

# Extra protection on top of the read-only connection.
_WRITE_KEYWORDS = (
    "insert", "update", "delete", "drop", "alter", "create",
    "replace", "truncate", "attach", "detach", "pragma", "vacuum",
)


def _read_only_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_READ_ONLY_URI, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


@tool
def query_chinook(sql: str) -> str:
    """Run one read-only SELECT query on the Chinook database.

    Returns the rows as a JSON array of objects. Anything that would change
    the database is rejected. Use this for every lookup: prices, customers,
    purchase history, sales metrics.
    """
    statement = sql.strip().rstrip(";").strip()
    lowered = statement.lower()

    if not lowered.startswith(("select", "with")):
        return json.dumps({"error": "Only SELECT queries are allowed."})
    if ";" in statement:
        return json.dumps({"error": "Only one statement is allowed."})
    if any(f" {word} " in f" {lowered} " for word in _WRITE_KEYWORDS):
        return json.dumps({"error": "The query contains a write keyword."})

    conn = _read_only_connection()
    try:
        rows = [dict(r) for r in conn.execute(statement).fetchall()]
        return json.dumps(rows, default=str)
    except sqlite3.Error as exc:
        return json.dumps({"error": f"SQL error: {exc}"})
    finally:
        conn.close()


@tool
def introspect_schema() -> str:
    """Return the database schema: the CREATE statement for every table.

    Call it once, then save the schema to your memory so you don't need to
    look it up again.
    """
    conn = _read_only_connection()
    try:
        rows = conn.execute(
            "SELECT name, sql FROM sqlite_master "
            "WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"
        ).fetchall()
        return "\n\n".join(r["sql"] for r in rows if r["sql"])
    finally:
        conn.close()


@tool
def add_customer(
    first_name: str,
    last_name: str,
    email: str,
    company: str = "",
    city: str = "",
    state: str = "",
    country: str = "",
    phone: str = "",
) -> str:
    """Add a NEW customer to the database, assigned to Jane.

    Only use this after searching by email and name to confirm the customer
    doesn't already exist. Jane approves the write before it runs. Returns the
    new CustomerId.
    """
    if not email or "@" not in email:
        return json.dumps({"error": "A valid email address is required."})

    conn = sqlite3.connect(DB_PATH)
    try:
        existing = conn.execute(
            "SELECT CustomerId FROM Customer WHERE lower(Email) = lower(?)", (email,)
        ).fetchone()
        if existing:
            return json.dumps(
                {"error": f"A customer with email {email} already exists "
                          f"(CustomerId {existing[0]})."}
            )

        # SupportRepId is set here, not by the model.
        cursor = conn.execute(
            """
            INSERT INTO Customer
                (FirstName, LastName, Company, City, State, Country, Phone,
                 Email, SupportRepId)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                first_name,
                last_name,
                company or None,
                city or None,
                state or None,
                country or None,
                phone or None,
                email,
                REP_EMPLOYEE_ID,
            ),
        )
        conn.commit()
        return json.dumps(
            {"status": "created", "customer_id": cursor.lastrowid,
             "name": f"{first_name} {last_name}", "email": email}
        )
    except sqlite3.Error as exc:
        return json.dumps({"error": f"SQL error: {exc}"})
    finally:
        conn.close()
