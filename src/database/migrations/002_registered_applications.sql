-- Discovered software is ephemeral. Only explicit user approvals enter these tables.
CREATE TABLE registered_applications(
    id TEXT PRIMARY KEY, name TEXT NOT NULL, normalized_name TEXT NOT NULL,
    executable_path TEXT NOT NULL UNIQUE, publisher TEXT, version TEXT, icon_path TEXT,
    source TEXT NOT NULL, enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)),
    needs_repair INTEGER NOT NULL DEFAULT 0 CHECK(needs_repair IN (0,1)),
    created_at TEXT NOT NULL, updated_at TEXT NOT NULL
);
CREATE TABLE application_aliases(
    id TEXT PRIMARY KEY, application_id TEXT NOT NULL REFERENCES registered_applications(id) ON DELETE CASCADE,
    alias TEXT NOT NULL, normalized_alias TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL
);
PRAGMA user_version = 2;
