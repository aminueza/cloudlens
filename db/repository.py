"""Full CRUD repository for CloudLens database operations."""

from typing import Any

import aiosqlite

from db.session import get_db


def _row_to_dict(row: aiosqlite.Row | None) -> dict | None:
    """Convert a sqlite Row to a plain dict."""
    if row is None:
        return None
    return dict(row)


def _rows_to_list(rows: list[aiosqlite.Row]) -> list[dict]:
    """Convert a list of sqlite Rows to list of dicts."""
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


async def save_snapshot(
    scope: str,
    graph_json: str,
    structured_json: str | None = None,
    provider: str | None = None,
) -> int:
    """Save a topology snapshot and return its ID."""
    db = await get_db()
    cursor = await db.execute(
        """
        INSERT INTO snapshots (scope, provider, graph_json, structured_json)
        VALUES (?, ?, ?, ?)
        """,
        (scope, provider, graph_json, structured_json),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def get_latest_snapshot(scope: str) -> dict | None:
    """Get the most recent snapshot for a scope."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM snapshots WHERE scope = ? ORDER BY id DESC LIMIT 1",
        (scope,),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def get_previous_snapshot(scope: str, before_id: int) -> dict | None:
    """Get the snapshot immediately before the given ID."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM snapshots WHERE scope = ? AND id < ? ORDER BY id DESC LIMIT 1",
        (scope, before_id),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def get_snapshot_at(scope: str, timestamp: str) -> dict | None:
    """Get the snapshot closest to (but not after) the given timestamp."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT * FROM snapshots
        WHERE scope = ? AND timestamp <= ?
        ORDER BY timestamp DESC LIMIT 1
        """,
        (scope, timestamp),
    )
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def list_snapshots(scope: str, limit: int = 50, offset: int = 0) -> list[dict]:
    """List snapshots for a scope, most recent first."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT id, scope, provider, timestamp FROM snapshots
        WHERE scope = ?
        ORDER BY id DESC LIMIT ? OFFSET ?
        """,
        (scope, limit, offset),
    )
    rows = await cursor.fetchall()
    return _rows_to_list(rows)


async def cleanup_old_snapshots(scope: str, keep: int = 100) -> int:
    """Delete old snapshots beyond the keep limit. Returns count deleted."""
    db = await get_db()
    cursor = await db.execute(
        """
        DELETE FROM snapshots WHERE scope = ? AND id NOT IN (
            SELECT id FROM snapshots WHERE scope = ?
            ORDER BY id DESC LIMIT ?
        )
        """,
        (scope, scope, keep),
    )
    await db.commit()
    return cursor.rowcount


# ---------------------------------------------------------------------------
# Changes
# ---------------------------------------------------------------------------


async def save_changes(changes: list[dict]) -> None:
    """Bulk-insert change records."""
    if not changes:
        return
    db = await get_db()
    await db.executemany(
        """
        INSERT INTO changes (scope, provider, snapshot_id, change_type, resource_type,
                             resource_name, severity, detail)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                c.get("scope"),
                c.get("provider"),
                c.get("snapshot_id"),
                c.get("change_type"),
                c.get("resource_type"),
                c.get("resource_name"),
                c.get("severity", "info"),
                c.get("detail"),
            )
            for c in changes
        ],
    )
    await db.commit()


async def get_changes(scope: str, limit: int = 100, offset: int = 0) -> list[dict]:
    """Get recent changes for a scope."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT * FROM changes WHERE scope = ?
        ORDER BY id DESC LIMIT ? OFFSET ?
        """,
        (scope, limit, offset),
    )
    rows = await cursor.fetchall()
    return _rows_to_list(rows)


async def get_change_summary(scope: str, since: str | None = None) -> dict:
    """Get summary counts of changes by type and severity."""
    db = await get_db()
    where = "WHERE scope = ?"
    params: list[Any] = [scope]
    if since:
        where += " AND timestamp >= ?"
        params.append(since)

    cursor = await db.execute(
        f"""
        SELECT change_type, severity, COUNT(*) as count
        FROM changes {where}
        GROUP BY change_type, severity
        """,
        params,
    )
    rows = await cursor.fetchall()
    summary: dict[str, dict[str, int]] = {}
    for r in rows:
        row = dict(r)
        ct = row["change_type"]
        if ct not in summary:
            summary[ct] = {}
        summary[ct][row["severity"]] = row["count"]
    return summary


# ---------------------------------------------------------------------------
# Incidents
# ---------------------------------------------------------------------------


async def create_incident(
    scope: str,
    title: str,
    severity: str = "warning",
    description: str | None = None,
    affected_resources: str | None = None,
) -> int:
    """Create an incident and return its ID."""
    db = await get_db()
    cursor = await db.execute(
        """
        INSERT INTO incidents (scope, title, severity, description, affected_resources)
        VALUES (?, ?, ?, ?, ?)
        """,
        (scope, title, severity, description, affected_resources),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def update_incident(
    incident_id: int,
    status: str | None = None,
    severity: str | None = None,
    description: str | None = None,
) -> dict | None:
    """Update an incident's fields."""
    db = await get_db()
    updates: list[str] = []
    params: list[Any] = []
    if status is not None:
        updates.append("status = ?")
        params.append(status)
    if severity is not None:
        updates.append("severity = ?")
        params.append(severity)
    if description is not None:
        updates.append("description = ?")
        params.append(description)
    if not updates:
        return await get_incident(incident_id)

    updates.append("updated_at = datetime('now')")
    params.append(incident_id)
    await db.execute(
        f"UPDATE incidents SET {', '.join(updates)} WHERE id = ?",
        params,
    )
    await db.commit()
    return await get_incident(incident_id)


async def get_incident(incident_id: int) -> dict | None:
    """Get a single incident by ID."""
    db = await get_db()
    cursor = await db.execute("SELECT * FROM incidents WHERE id = ?", (incident_id,))
    row = await cursor.fetchone()
    return _row_to_dict(row)


async def list_incidents(
    scope: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[dict]:
    """List incidents for a scope, optionally filtered by status."""
    db = await get_db()
    where = "WHERE scope = ?"
    params: list[Any] = [scope]
    if status:
        where += " AND status = ?"
        params.append(status)
    params.extend([limit, offset])
    cursor = await db.execute(
        f"""
        SELECT * FROM incidents {where}
        ORDER BY created_at DESC LIMIT ? OFFSET ?
        """,
        params,
    )
    rows = await cursor.fetchall()
    return _rows_to_list(rows)


async def add_annotation(incident_id: int, content: str, author: str = "system") -> int:
    """Add an annotation to an incident."""
    db = await get_db()
    cursor = await db.execute(
        """
        INSERT INTO incident_annotations (incident_id, author, content)
        VALUES (?, ?, ?)
        """,
        (incident_id, author, content),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


# ---------------------------------------------------------------------------
# Compliance
# ---------------------------------------------------------------------------


async def list_compliance_rules(scope: str) -> list[dict]:
    """List all compliance rules applicable to a scope."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT * FROM compliance_rules WHERE scope IN (?, '*') ORDER BY id",
        (scope,),
    )
    rows = await cursor.fetchall()
    return _rows_to_list(rows)


async def upsert_compliance_rule(
    rule_id: str,
    scope: str,
    name: str,
    description: str | None = None,
    severity: str = "warning",
    enabled: bool = True,
    params: str | None = None,
) -> None:
    """Insert or update a compliance rule."""
    db = await get_db()
    await db.execute(
        """
        INSERT INTO compliance_rules (id, scope, name, description, severity, enabled, params)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(id) DO UPDATE SET
            name = excluded.name,
            description = excluded.description,
            severity = excluded.severity,
            enabled = excluded.enabled,
            params = excluded.params
        """,
        (rule_id, scope, name, description, severity, int(enabled), params),
    )
    await db.commit()


async def save_violations(violations: list[dict]) -> None:
    """Bulk-insert compliance violations."""
    if not violations:
        return
    db = await get_db()
    await db.executemany(
        """
        INSERT INTO compliance_violations (scope, rule_id, resource_name, resource_type, detail, severity)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (
                v.get("scope"),
                v.get("rule_id"),
                v.get("resource_name"),
                v.get("resource_type"),
                v.get("detail"),
                v.get("severity", "warning"),
            )
            for v in violations
        ],
    )
    await db.commit()


async def get_violations(
    scope: str, rule_id: str | None = None, limit: int = 200
) -> list[dict]:
    """Get compliance violations, optionally filtered by rule."""
    db = await get_db()
    where = "WHERE scope = ?"
    params: list[Any] = [scope]
    if rule_id:
        where += " AND rule_id = ?"
        params.append(rule_id)
    params.append(limit)
    cursor = await db.execute(
        f"""
        SELECT * FROM compliance_violations {where}
        ORDER BY id DESC LIMIT ?
        """,
        params,
    )
    rows = await cursor.fetchall()
    return _rows_to_list(rows)


async def clear_violations(scope: str) -> None:
    """Clear all violations for a scope (before re-evaluation)."""
    db = await get_db()
    await db.execute("DELETE FROM compliance_violations WHERE scope = ?", (scope,))
    await db.commit()


# ---------------------------------------------------------------------------
# Health Checks
# ---------------------------------------------------------------------------


async def save_health_checks(checks: list[dict]) -> None:
    """Bulk-insert health check results."""
    if not checks:
        return
    db = await get_db()
    await db.executemany(
        """
        INSERT INTO health_checks (scope, provider, check_name, status, severity,
                                   resource_name, detail)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                c.get("scope"),
                c.get("provider"),
                c.get("check_name"),
                c.get("status"),
                c.get("severity", "info"),
                c.get("resource_name"),
                c.get("detail"),
            )
            for c in checks
        ],
    )
    await db.commit()


async def get_health_checks(scope: str, limit: int = 200) -> list[dict]:
    """Get recent health checks for a scope."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT * FROM health_checks WHERE scope = ?
        ORDER BY id DESC LIMIT ?
        """,
        (scope, limit),
    )
    rows = await cursor.fetchall()
    return _rows_to_list(rows)


async def get_health_summary(scope: str) -> dict:
    """Get summary of latest health checks grouped by status."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT status, severity, COUNT(*) as count
        FROM health_checks WHERE scope = ?
        GROUP BY status, severity
        """,
        (scope,),
    )
    rows = await cursor.fetchall()
    summary: dict[str, int] = {"pass": 0, "fail": 0, "warn": 0}
    for r in rows:
        row = dict(r)
        status = row["status"]
        if status in summary:
            summary[status] += row["count"]
    return summary


# ---------------------------------------------------------------------------
# AI Conversations
# ---------------------------------------------------------------------------


async def save_ai_message(scope: str, role: str, content: str) -> int:
    """Save an AI conversation message."""
    db = await get_db()
    cursor = await db.execute(
        """
        INSERT INTO ai_conversations (scope, role, content)
        VALUES (?, ?, ?)
        """,
        (scope, role, content),
    )
    await db.commit()
    return cursor.lastrowid  # type: ignore[return-value]


async def get_ai_history(scope: str, limit: int = 50) -> list[dict]:
    """Get AI conversation history for a scope."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT * FROM ai_conversations WHERE scope = ?
        ORDER BY id ASC LIMIT ?
        """,
        (scope, limit),
    )
    rows = await cursor.fetchall()
    return _rows_to_list(rows)
