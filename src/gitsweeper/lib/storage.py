"""SQLite storage layer.

Portable SQL only: no AUTOINCREMENT, no JSON1, no SQLite-only functions.
Datetimes are stored as ISO 8601 UTC strings (TEXT), which compare
correctly with lexicographic ordering. Switching to Postgres later means
replacing INTEGER PRIMARY KEY with a portable IDENTITY column and
swapping the connection factory.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS repositories (
        id              INTEGER PRIMARY KEY,
        owner           TEXT    NOT NULL,
        name            TEXT    NOT NULL,
        owner_namespace TEXT,
        fetched_at      TEXT    NOT NULL,
        UNIQUE (owner, name, owner_namespace)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pull_requests (
        id           INTEGER PRIMARY KEY,
        repo_id      INTEGER NOT NULL REFERENCES repositories(id),
        number       INTEGER NOT NULL,
        state        TEXT    NOT NULL,
        created_at   TEXT    NOT NULL,
        merged_at    TEXT,
        closed_at    TEXT,
        author       TEXT    NOT NULL,
        raw_payload  TEXT    NOT NULL,
        fetched_at   TEXT    NOT NULL,
        UNIQUE (repo_id, number)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS pr_first_responses (
        pr_id             INTEGER PRIMARY KEY REFERENCES pull_requests(id),
        first_response_at TEXT,
        responder         TEXT,
        fetched_at        TEXT    NOT NULL
    )
    """,
)


def _utcnow_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path: str | Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    for stmt in SCHEMA_STATEMENTS:
        conn.execute(stmt)
    conn.commit()


def get_or_create_repository(
    conn: sqlite3.Connection,
    owner: str,
    name: str,
    owner_namespace: str | None = None,
) -> int:
    row = conn.execute(
        "SELECT id FROM repositories "
        "WHERE owner = ? AND name = ? AND owner_namespace IS ?",
        (owner, name, owner_namespace),
    ).fetchone()
    if row is not None:
        conn.execute(
            "UPDATE repositories SET fetched_at = ? WHERE id = ?",
            (_utcnow_iso(), row["id"]),
        )
        conn.commit()
        return int(row["id"])
    cur = conn.execute(
        "INSERT INTO repositories (owner, name, owner_namespace, fetched_at) "
        "VALUES (?, ?, ?, ?)",
        (owner, name, owner_namespace, _utcnow_iso()),
    )
    conn.commit()
    return int(cur.lastrowid)


def upsert_pull_requests(
    conn: sqlite3.Connection,
    repo_id: int,
    prs: Iterable[dict[str, Any]],
) -> int:
    """Insert or update pull-request rows. Returns count written."""
    fetched_at = _utcnow_iso()
    count = 0
    for pr in prs:
        merged_at = pr.get("merged_at")
        state = "merged" if merged_at else pr.get("state", "open")
        conn.execute(
            """
            INSERT INTO pull_requests
                (repo_id, number, state, created_at, merged_at, closed_at,
                 author, raw_payload, fetched_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (repo_id, number) DO UPDATE SET
                state       = excluded.state,
                created_at  = excluded.created_at,
                merged_at   = excluded.merged_at,
                closed_at   = excluded.closed_at,
                author      = excluded.author,
                raw_payload = excluded.raw_payload,
                fetched_at  = excluded.fetched_at
            """,
            (
                repo_id,
                int(pr["number"]),
                state,
                pr["created_at"],
                merged_at,
                pr.get("closed_at"),
                (pr.get("user") or {}).get("login") or "",
                json.dumps(pr, separators=(",", ":")),
                fetched_at,
            ),
        )
        count += 1
    conn.commit()
    return count


def list_pull_requests(
    conn: sqlite3.Connection,
    repo_id: int,
    merged_since: str | None = None,
) -> list[sqlite3.Row]:
    """Return PR rows. If merged_since is given, only PRs with
    merged_at >= merged_since are returned (string compare on ISO 8601)."""
    if merged_since is None:
        return conn.execute(
            "SELECT * FROM pull_requests WHERE repo_id = ? ORDER BY number",
            (repo_id,),
        ).fetchall()
    return conn.execute(
        "SELECT * FROM pull_requests "
        "WHERE repo_id = ? AND merged_at IS NOT NULL AND merged_at >= ? "
        "ORDER BY number",
        (repo_id, merged_since),
    ).fetchall()


def upsert_first_response(
    conn: sqlite3.Connection,
    pr_id: int,
    first_response_at: str | None,
    responder: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO pr_first_responses
            (pr_id, first_response_at, responder, fetched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT (pr_id) DO UPDATE SET
            first_response_at = excluded.first_response_at,
            responder         = excluded.responder,
            fetched_at        = excluded.fetched_at
        """,
        (pr_id, first_response_at, responder, _utcnow_iso()),
    )
    conn.commit()


def list_first_responses(
    conn: sqlite3.Connection,
    repo_id: int,
    merged_since: str | None = None,
) -> list[sqlite3.Row]:
    """Return joined PR + first-response rows for PRs in a repo. Includes
    rows where pr_first_responses.pr_id is NULL (no first-response computed
    yet) so callers can distinguish 'not yet fetched' from 'no response'."""
    base = (
        "SELECT pr.id AS pr_id, pr.number, pr.author, pr.created_at, "
        "       pr.merged_at, fr.first_response_at, fr.responder, "
        "       fr.fetched_at AS fr_fetched_at "
        "FROM pull_requests pr "
        "LEFT JOIN pr_first_responses fr ON fr.pr_id = pr.id "
        "WHERE pr.repo_id = ? "
    )
    if merged_since is None:
        return conn.execute(base + "ORDER BY pr.number", (repo_id,)).fetchall()
    return conn.execute(
        base + "AND pr.merged_at IS NOT NULL AND pr.merged_at >= ? "
        "ORDER BY pr.number",
        (repo_id, merged_since),
    ).fetchall()
