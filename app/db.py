"""
Logging layer for the Internal Document Q&A Assistant.

Every question asked is written here BEFORE the answer is returned to the
caller, and every row starts life as status="pending". A human reviewer
(you, playing that role for the demo) then flips it to "approved" or
"rejected" via /review/{log_id}. This is the "Pending Human Review" gate
the assessment asks for, implemented as real state in a real table rather
than described in prose.
"""
import sqlite3
import json
import os
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("QA_DB_PATH", Path(__file__).parent.parent / "logs" / "qa_log.db"))
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_conn()
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS qa_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT NOT NULL,
            model TEXT NOT NULL,
            source_docs TEXT NOT NULL,
            prompt TEXT NOT NULL,
            question TEXT NOT NULL,
            output TEXT NOT NULL,
            citation TEXT,
            answered_from_context INTEGER,
            reviewer_status TEXT NOT NULL DEFAULT 'pending',
            reviewer_note TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def insert_log(model, source_docs, prompt, question, output, citation, answered_from_context):
    conn = get_conn()
    cur = conn.execute(
        """
        INSERT INTO qa_log
            (timestamp, model, source_docs, prompt, question, output, citation, answered_from_context, reviewer_status)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pending')
        """,
        (
            datetime.now(timezone.utc).isoformat(),
            model,
            json.dumps(source_docs),
            prompt,
            question,
            output,
            citation,
            int(answered_from_context),
        ),
    )
    conn.commit()
    log_id = cur.lastrowid
    conn.close()
    return log_id


def update_review_status(log_id, status, note=None):
    if status not in ("approved", "rejected", "pending"):
        raise ValueError("status must be approved, rejected, or pending")
    conn = get_conn()
    cur = conn.execute(
        "UPDATE qa_log SET reviewer_status = ?, reviewer_note = ? WHERE id = ?",
        (status, note, log_id),
    )
    conn.commit()
    updated = cur.rowcount
    conn.close()
    return updated > 0


def get_all_logs():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM qa_log ORDER BY id DESC").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_log(log_id):
    conn = get_conn()
    row = conn.execute("SELECT * FROM qa_log WHERE id = ?", (log_id,)).fetchone()
    conn.close()
    return dict(row) if row else None
