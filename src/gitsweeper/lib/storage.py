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

from gitsweeper.lib.forge.base import ForgeComment, ForgePullRequest

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
    """
    CREATE TABLE IF NOT EXISTS pr_close_actors (
        pr_id        INTEGER PRIMARY KEY REFERENCES pull_requests(id),
        actor        TEXT,
        fetched_at   TEXT    NOT NULL
    )
    """,
    # Local cache of PR discussion bodies, populated via the provider's
    # comment listing. The first time `retro` runs for a repo it fetches and
    # writes one row per comment; later runs read from here. Uniqueness is
    # (pr_id, created_at, author): no forge guarantees a stable comment id in
    # the normalized `ForgeComment`, so we de-dupe on the natural key instead
    # — re-fetching the same comment updates its body in place rather than
    # duplicating the row. Portable SQL (no AUTOINCREMENT, no JSON1); body is
    # plain TEXT.
    """
    CREATE TABLE IF NOT EXISTS pr_comments (
        pr_id        INTEGER NOT NULL REFERENCES pull_requests(id),
        author       TEXT,
        created_at   TEXT,
        body         TEXT,
        fetched_at   TEXT    NOT NULL,
        UNIQUE (pr_id, created_at, author)
    )
    """,
    # Marker that a PR's comments were fetched, independent of how many comments
    # came back. `pr_comments` only holds rows for PRs that HAVE comments, so a
    # PR with zero comments would otherwise look unfetched and be re-fetched on
    # every run. One row per fetched PR records that the listing call happened.
    """
    CREATE TABLE IF NOT EXISTS pr_comment_fetches (
        pr_id        INTEGER PRIMARY KEY REFERENCES pull_requests(id),
        fetched_at   TEXT    NOT NULL
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
    prs: Iterable[ForgePullRequest],
) -> int:
    """Insert or update pull-request rows. Returns count written."""
    fetched_at = _utcnow_iso()
    count = 0
    for pr in prs:
        state = "merged" if pr.merged_at else pr.state
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
                pr.number,
                state,
                pr.created_at,
                pr.merged_at,
                pr.closed_at,
                pr.author,
                json.dumps(pr.raw, separators=(",", ":")),
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
    author: str | None = None,
) -> list[sqlite3.Row]:
    """Return PR rows. `merged_since` filters merged_at lexicographically;
    `author` matches case-insensitively against the stored author login."""
    sql = "SELECT * FROM pull_requests WHERE repo_id = ?"
    params: list = [repo_id]
    if merged_since is not None:
        sql += " AND merged_at IS NOT NULL AND merged_at >= ?"
        params.append(merged_since)
    if author is not None:
        sql += " AND LOWER(author) = LOWER(?)"
        params.append(author)
    sql += " ORDER BY number"
    return conn.execute(sql, params).fetchall()


def upsert_comments(
    conn: sqlite3.Connection,
    pr_id: int,
    comments: Iterable[ForgeComment],
) -> int:
    """Insert or update cached comment rows for one PR. Returns count written.

    De-dupes on (pr_id, created_at, author): re-fetching the same comment
    updates its body and fetched_at in place rather than duplicating the row,
    so a re-run is idempotent."""
    fetched_at = _utcnow_iso()
    count = 0
    for comment in comments:
        conn.execute(
            """
            INSERT INTO pr_comments (pr_id, author, created_at, body, fetched_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT (pr_id, created_at, author) DO UPDATE SET
                body       = excluded.body,
                fetched_at = excluded.fetched_at
            """,
            (pr_id, comment.author, comment.created_at, comment.body, fetched_at),
        )
        count += 1
    conn.commit()
    return count


def list_comments(
    conn: sqlite3.Connection,
    repo_id: int,
) -> list[sqlite3.Row]:
    """Return cached comment rows joined to their PR for a repo.

    Each row carries the PR number plus the comment's author, created_at,
    and body, ordered by PR number then comment time. Callers that only
    need per-PR counts can group on `number`."""
    sql = (
        "SELECT pr.number AS number, "
        "       c.author AS author, c.created_at AS created_at, c.body AS body "
        "FROM pr_comments c "
        "JOIN pull_requests pr ON pr.id = c.pr_id "
        "WHERE pr.repo_id = ? "
        "ORDER BY pr.number, c.created_at"
    )
    return conn.execute(sql, (repo_id,)).fetchall()


def list_prs_with_comments(
    conn: sqlite3.Connection,
    repo_id: int,
) -> set[int]:
    """Return the set of PR ids that already have at least one cached comment.

    The `retro` fetch loop uses this to skip PRs whose comments are already
    cached so a second run does not re-fetch them."""
    rows = conn.execute(
        "SELECT DISTINCT pr_id FROM pr_comments c "
        "JOIN pull_requests pr ON pr.id = c.pr_id "
        "WHERE pr.repo_id = ?",
        (repo_id,),
    ).fetchall()
    return {int(r["pr_id"]) for r in rows}


def mark_comments_fetched(conn: sqlite3.Connection, pr_id: int) -> None:
    """Record that a PR's comments were fetched, even if there were none.

    Idempotent: re-marking a PR updates its fetched_at in place. Paired with
    :func:`list_prs_comments_fetched` so the retro fetch loop can skip a PR it
    has already fetched regardless of whether that PR has any comment rows."""
    conn.execute(
        """
        INSERT INTO pr_comment_fetches (pr_id, fetched_at)
        VALUES (?, ?)
        ON CONFLICT (pr_id) DO UPDATE SET
            fetched_at = excluded.fetched_at
        """,
        (pr_id, _utcnow_iso()),
    )
    conn.commit()


def list_prs_comments_fetched(
    conn: sqlite3.Connection,
    repo_id: int,
) -> set[int]:
    """Return the set of PR ids whose comments were already fetched.

    The `retro` fetch loop uses this (not the presence of comment rows) to skip
    PRs it has fetched so a second run does not re-fetch — including PRs that
    turned out to have zero comments."""
    rows = conn.execute(
        "SELECT cf.pr_id AS pr_id FROM pr_comment_fetches cf "
        "JOIN pull_requests pr ON pr.id = cf.pr_id "
        "WHERE pr.repo_id = ?",
        (repo_id,),
    ).fetchall()
    return {int(r["pr_id"]) for r in rows}


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
    author: str | None = None,
) -> list[sqlite3.Row]:
    """Return joined PR + first-response rows for PRs in a repo. Includes
    rows where pr_first_responses.pr_id is NULL (no first-response computed
    yet) so callers can distinguish 'not yet fetched' from 'no response'."""
    sql = (
        "SELECT pr.id AS pr_id, pr.number, pr.author, pr.created_at, "
        "       pr.merged_at, pr.closed_at, "
        "       fr.first_response_at, fr.responder, "
        "       fr.fetched_at AS fr_fetched_at "
        "FROM pull_requests pr "
        "LEFT JOIN pr_first_responses fr ON fr.pr_id = pr.id "
        "WHERE pr.repo_id = ?"
    )
    params: list = [repo_id]
    if merged_since is not None:
        sql += " AND pr.merged_at IS NOT NULL AND pr.merged_at >= ?"
        params.append(merged_since)
    if author is not None:
        sql += " AND LOWER(pr.author) = LOWER(?)"
        params.append(author)
    sql += " ORDER BY pr.number"
    return conn.execute(sql, params).fetchall()


def upsert_close_actor(
    conn: sqlite3.Connection,
    pr_id: int,
    actor: str | None,
) -> None:
    conn.execute(
        """
        INSERT INTO pr_close_actors (pr_id, actor, fetched_at)
        VALUES (?, ?, ?)
        ON CONFLICT (pr_id) DO UPDATE SET
            actor      = excluded.actor,
            fetched_at = excluded.fetched_at
        """,
        (pr_id, actor, _utcnow_iso()),
    )
    conn.commit()


def list_close_actors(
    conn: sqlite3.Connection,
    repo_id: int,
    author: str | None = None,
) -> list[sqlite3.Row]:
    """Return joined PR + close-actor rows for closed-without-merge PRs.
    Includes rows where pr_close_actors.pr_id is NULL so callers can
    distinguish 'not yet enriched' from 'enriched, actor unknown'."""
    sql = (
        "SELECT pr.id AS pr_id, pr.number, pr.author, "
        "       pr.created_at, pr.closed_at, "
        "       ca.actor AS close_actor, "
        "       ca.fetched_at AS ca_fetched_at "
        "FROM pull_requests pr "
        "LEFT JOIN pr_close_actors ca ON ca.pr_id = pr.id "
        "WHERE pr.repo_id = ? "
        "  AND pr.merged_at IS NULL "
        "  AND pr.closed_at IS NOT NULL"
    )
    params: list = [repo_id]
    if author is not None:
        sql += " AND LOWER(pr.author) = LOWER(?)"
        params.append(author)
    sql += " ORDER BY pr.number"
    return conn.execute(sql, params).fetchall()
