"""SQLite database session management via aiosqlite."""

import aiosqlite

_db: aiosqlite.Connection | None = None

DEFAULT_DB_PATH = "cloudlens.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    provider TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    graph_json TEXT NOT NULL,
    structured_json TEXT
);

CREATE TABLE IF NOT EXISTS changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    provider TEXT,
    snapshot_id INTEGER,
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    change_type TEXT NOT NULL,
    resource_type TEXT,
    resource_name TEXT,
    severity TEXT DEFAULT 'info',
    detail TEXT,
    FOREIGN KEY (snapshot_id) REFERENCES snapshots(id)
);

CREATE TABLE IF NOT EXISTS incidents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    title TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'warning',
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    description TEXT,
    affected_resources TEXT
);

CREATE TABLE IF NOT EXISTS incident_annotations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    incident_id INTEGER NOT NULL,
    author TEXT NOT NULL DEFAULT 'system',
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    content TEXT NOT NULL,
    FOREIGN KEY (incident_id) REFERENCES incidents(id)
);

CREATE TABLE IF NOT EXISTS compliance_rules (
    id TEXT PRIMARY KEY,
    scope TEXT NOT NULL,
    name TEXT NOT NULL,
    description TEXT,
    severity TEXT NOT NULL DEFAULT 'warning',
    enabled INTEGER NOT NULL DEFAULT 1,
    params TEXT
);

CREATE TABLE IF NOT EXISTS compliance_violations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    rule_id TEXT NOT NULL,
    resource_name TEXT,
    resource_type TEXT,
    detail TEXT,
    severity TEXT DEFAULT 'warning',
    timestamp TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (rule_id) REFERENCES compliance_rules(id)
);

CREATE TABLE IF NOT EXISTS health_checks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    provider TEXT,
    check_name TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    resource_name TEXT,
    detail TEXT,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS ai_conversations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope TEXT NOT NULL,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    timestamp TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

DEFAULT_RULES: list[dict] = [
    {
        "id": "prod-firewall",
        "name": "Production Firewall Required",
        "description": "Every production network must have a Firewall",
        "severity": "critical",
        "handler": "require_resource",
        "params": '{"env": "prd", "resource_type": "firewall"}',
    },
    {
        "id": "prod-security-group",
        "name": "Production Security Groups Required",
        "description": "Every production network must have security groups",
        "severity": "warning",
        "handler": "require_resource",
        "params": '{"env": "prd", "resource_type": "security_group"}',
    },
    {
        "id": "peering-connected",
        "name": "Peering Connected",
        "description": "All peerings must be in connected/active state",
        "severity": "critical",
        "handler": "peering_connected",
        "params": "{}",
    },
    {
        "id": "no-empty-sg",
        "name": "No Empty Security Groups",
        "description": "Security groups must have at least one rule",
        "severity": "warning",
        "handler": "sg_has_rules",
        "params": "{}",
    },
    {
        "id": "address-overlap",
        "name": "No Address Overlap",
        "description": "Network address spaces must not overlap within same environment",
        "severity": "critical",
        "handler": "address_overlap",
        "params": "{}",
    },
    {
        "id": "subnet-has-sg",
        "name": "Subnet Security Group",
        "description": "Production subnets should have security groups",
        "severity": "warning",
        "handler": "subnet_has_sg",
        "params": '{"env": "prd"}',
    },
    {
        "id": "no-orphan-pip",
        "name": "No Orphaned Public IPs",
        "description": "Public IPs should be associated with a resource",
        "severity": "warning",
        "handler": "no_orphan_resource",
        "params": '{"resource_type": "public_ip"}',
    },
]


async def init_db(db_path: str = DEFAULT_DB_PATH) -> aiosqlite.Connection:
    """Initialize the database, create tables, and seed default rules."""
    global _db
    _db = await aiosqlite.connect(db_path)
    _db.row_factory = aiosqlite.Row
    await _db.executescript(_SCHEMA)

    # Seed default compliance rules
    for rule in DEFAULT_RULES:
        await _db.execute(
            """
            INSERT OR IGNORE INTO compliance_rules (id, scope, name, description, severity, enabled, params)
            VALUES (?, ?, ?, ?, ?, 1, ?)
            """,
            (
                rule["id"],
                "*",
                rule["name"],
                rule["description"],
                rule["severity"],
                rule.get("params", "{}"),
            ),
        )
    await _db.commit()
    return _db


async def get_db() -> aiosqlite.Connection:
    """Return the current database connection, initializing if needed."""
    global _db
    if _db is None:
        _db = await init_db()
    return _db


async def close_db() -> None:
    """Close the database connection."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None
