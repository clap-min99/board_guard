"""SQLite persistence for confirmed PCB inspection results."""

import sqlite3
from contextlib import closing
from pathlib import Path


DB_PATH = Path(__file__).resolve().parent / "data" / "inspections.db"


def _connect():
    """Return a short-lived connection suitable for the calling thread."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 5000")
    return connection


def init_database():
    """Create the inspection database and schema when they do not exist."""
    with _connect() as connection:
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = NORMAL")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS inspections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                inspected_at TEXT NOT NULL
                    DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
                side TEXT NOT NULL CHECK (side IN ('front', 'back')),
                state TEXT NOT NULL CHECK (state IN ('PASS', 'FAIL')),
                score REAL,
                threshold REAL NOT NULL,
                image_path TEXT,
                model_name TEXT NOT NULL,
                model_version TEXT NOT NULL,
                inference_ms REAL NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_inspections_inspected_at
            ON inspections(inspected_at DESC)
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_inspections_state
            ON inspections(state)
            """
        )


def save_inspection(
    *,
    side,
    state,
    score,
    threshold,
    image_path,
    model_name,
    model_version,
    inference_ms,
):
    """Persist one confirmed PASS/FAIL result and return its database id."""
    with _connect() as connection:
        cursor = connection.execute(
            """
            INSERT INTO inspections (
                side,
                state,
                score,
                threshold,
                image_path,
                model_name,
                model_version,
                inference_ms
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                side,
                state,
                score,
                threshold,
                image_path,
                model_name,
                model_version,
                inference_ms,
            ),
        )
        return cursor.lastrowid


def get_inspection_summary():
    """Return persisted totals used to restore the dashboard after restart."""
    with _connect() as connection:
        row = connection.execute(
            """
            SELECT
                COALESCE(MAX(id), 0) AS latest_id,
                COUNT(*) AS total_count,
                COALESCE(SUM(CASE WHEN state = 'PASS' THEN 1 ELSE 0 END), 0)
                    AS pass_count,
                COALESCE(SUM(CASE WHEN state = 'FAIL' THEN 1 ELSE 0 END), 0)
                    AS fail_count
            FROM inspections
            """
        ).fetchone()

    total_count = row["total_count"]
    fail_count = row["fail_count"]
    return {
        "latest_id": row["latest_id"],
        "total_count": total_count,
        "pass_count": row["pass_count"],
        "fail_count": fail_count,
        "fail_rate": round(fail_count / total_count * 100, 1)
        if total_count
        else 0.0,
    }


def get_inspection_history(*, state, filter="all", page=1, page_size=20):
    """Read counts and a page of confirmed results from one DB snapshot."""
    if state not in ("PASS", "FAIL"):
        raise ValueError("state must be PASS or FAIL")
    if filter not in ("all", "front", "back", "latest"):
        raise ValueError("Invalid history filter")
    if not 1 <= page <= 2147483647 or not 1 <= page_size <= 100:
        raise ValueError("Invalid history page or page size")

    with closing(_connect()) as connection, connection:
        connection.execute("BEGIN")
        counts = dict(connection.execute(
            """
            SELECT COUNT(*) AS 'all',
                   COALESCE(SUM(side = 'front'), 0) AS front,
                   COALESCE(SUM(side = 'back'), 0) AS back
            FROM inspections WHERE state = ?
            """,
            (state,),
        ).fetchone())
        counts["latest"] = min(5, counts["all"])
        total = counts[filter]
        if filter == "latest":
            page_size = 5
        pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, pages)
        offset = (page - 1) * page_size
        where = "state = ?"
        parameters = [state]
        if filter in ("front", "back"):
            where += " AND side = ?"
            parameters.append(filter)
        rows = connection.execute(
            f"""
            SELECT id, inspected_at, side, state, score, threshold,
                   inference_ms, model_name, model_version
            FROM inspections WHERE {where}
            ORDER BY inspected_at DESC, id DESC LIMIT ? OFFSET ?
            """,
            (*parameters, page_size, offset),
        ).fetchall()

    return {
        "rows": [dict(row) for row in rows],
        "counts": counts,
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
    }
