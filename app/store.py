from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

DB_PATH = os.getenv(
    "STORE_DB_PATH",
    str(Path(__file__).resolve().parent.parent / "data" / "code_review.db"),
)

_lock = threading.Lock()


def _reset_path(path: str) -> None:
    """Point the store at a different DB file (used by tests)."""
    global DB_PATH
    DB_PATH = path


def _connect() -> sqlite3.Connection:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    _init(conn)
    return conn


def _init(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pr_findings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            pr_number INTEGER NOT NULL,
            head_sha TEXT NOT NULL,
            file TEXT NOT NULL,
            line INTEGER,
            column INTEGER,
            end_line INTEGER,
            end_column INTEGER,
            severity TEXT NOT NULL,
            rule TEXT NOT NULL,
            linter TEXT NOT NULL,
            message TEXT NOT NULL,
            code TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS pr_suggestions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            repo TEXT NOT NULL,
            pr_number INTEGER NOT NULL,
            head_sha TEXT NOT NULL,
            file TEXT NOT NULL,
            line INTEGER,
            severity TEXT NOT NULL,
            message TEXT NOT NULL,
            suggestion TEXT,
            reason TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pr_findings ON pr_findings(repo, pr_number)"
    )
    conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_pr_suggestions ON pr_suggestions(repo, pr_number)"
    )
    conn.commit()


def save_pr_review(
    repo: str,
    pr_number: int,
    head_sha: str,
    report,
    suggestions: List,
) -> None:
    """Replace the stored review for a PR with the latest findings."""
    now = datetime.now(timezone.utc).isoformat()
    with _lock:
        conn = _connect()
        try:
            conn.execute(
                "DELETE FROM pr_findings WHERE repo = ? AND pr_number = ?",
                (repo, pr_number),
            )
            conn.execute(
                "DELETE FROM pr_suggestions WHERE repo = ? AND pr_number = ?",
                (repo, pr_number),
            )
            for f in report.findings:
                conn.execute(
                    """
                    INSERT INTO pr_findings (
                        repo, pr_number, head_sha, file, line, column,
                        end_line, end_column, severity, rule, linter,
                        message, code, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        repo,
                        pr_number,
                        head_sha,
                        f.file,
                        f.line,
                        f.column,
                        f.end_line,
                        f.end_column,
                        f.severity.value,
                        f.rule,
                        f.linter,
                        f.message,
                        f.code,
                        now,
                    ),
                )
            for s in suggestions:
                conn.execute(
                    """
                    INSERT INTO pr_suggestions (
                        repo, pr_number, head_sha, file, line, severity,
                        message, suggestion, reason, created_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        repo,
                        pr_number,
                        head_sha,
                        s.file,
                        s.line,
                        s.severity.value,
                        s.message,
                        s.suggestion,
                        s.reason,
                        now,
                    ),
                )
            conn.commit()
        finally:
            conn.close()


def get_pr_review(repo: str, pr_number: int) -> Dict:
    """Return stored findings + suggestions for a PR, keyed by file."""
    with _lock:
        conn = _connect()
        try:
            findings = conn.execute(
                "SELECT * FROM pr_findings WHERE repo = ? AND pr_number = ? "
                "ORDER BY file, line",
                (repo, pr_number),
            ).fetchall()
            suggestions = conn.execute(
                "SELECT * FROM pr_suggestions WHERE repo = ? AND pr_number = ? "
                "ORDER BY file, line",
                (repo, pr_number),
            ).fetchall()
        finally:
            conn.close()

    files: Dict[str, List[Dict]] = {}
    for row in findings:
        files.setdefault(row["file"], []).append(dict(row))
    for row in suggestions:
        item = dict(row)
        item["source"] = "ai"
        item["rule"] = "refactor"
        item["linter"] = "ai"
        files.setdefault(row["file"], []).append(item)
    return {
        "files": {path: items for path, items in sorted(files.items())},
        "count": sum(len(items) for items in files.values()),
    }
