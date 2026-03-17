"""SQLite audit logger for signing operations."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Optional

import aiosqlite

from app.config import get_settings

log = logging.getLogger(__name__)

CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS audit_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    action TEXT NOT NULL,
    filename TEXT,
    file_size INTEGER,
    signing_method TEXT,
    certificate_fingerprint TEXT,
    algorithm TEXT,
    requester_id TEXT,
    status TEXT NOT NULL,
    error TEXT,
    duration_ms INTEGER
)
"""

_db: Optional[aiosqlite.Connection] = None


async def init_db() -> None:
    """Open the SQLite database and create the audit table."""
    global _db
    settings = get_settings()
    _db = await aiosqlite.connect(str(settings.db_path))
    _db.row_factory = aiosqlite.Row
    await _db.execute(CREATE_TABLE)
    await _db.commit()
    log.info("Audit database initialized: %s", settings.db_path)


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db:
        await _db.close()
        _db = None


async def log_event(
    action: str,
    status: str,
    *,
    filename: Optional[str] = None,
    file_size: Optional[int] = None,
    signing_method: Optional[str] = None,
    certificate_fingerprint: Optional[str] = None,
    algorithm: Optional[str] = None,
    requester_id: Optional[str] = None,
    error: Optional[str] = None,
    duration_ms: Optional[int] = None,
) -> None:
    """Insert an audit log entry."""
    if not _db:
        log.warning("Audit DB not initialized, skipping log")
        return
    now = datetime.now(timezone.utc).isoformat()
    await _db.execute(
        """INSERT INTO audit_log
           (timestamp, action, filename, file_size, signing_method,
            certificate_fingerprint, algorithm, requester_id, status, error, duration_ms)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            now, action, filename, file_size, signing_method,
            certificate_fingerprint, algorithm, requester_id, status, error, duration_ms,
        ),
    )
    await _db.commit()


async def query_logs(
    limit: int = 100,
    offset: int = 0,
    action: Optional[str] = None,
    status: Optional[str] = None,
) -> list[dict[str, Any]]:
    """Query audit logs with optional filters."""
    if not _db:
        return []

    query = "SELECT * FROM audit_log WHERE 1=1"
    params: list[Any] = []

    if action:
        query += " AND action = ?"
        params.append(action)
    if status:
        query += " AND status = ?"
        params.append(status)

    query += " ORDER BY id DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    cursor = await _db.execute(query, params)
    rows = await cursor.fetchall()
    return [dict(row) for row in rows]
