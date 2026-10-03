CREATE TABLE file_open_history (path TEXT PRIMARY KEY, opened REAL NOT NULL CHECK(opened > 0));
PRAGMA user_version=6;
