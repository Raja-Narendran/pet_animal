-- Approved local routines and private execution outcomes.
CREATE TABLE routines(id TEXT PRIMARY KEY, command_id TEXT NOT NULL UNIQUE REFERENCES commands(id) ON DELETE CASCADE, steps TEXT NOT NULL);
CREATE TABLE workflow_runs(id TEXT PRIMARY KEY, routine_id TEXT REFERENCES routines(id) ON DELETE SET NULL, history_id TEXT UNIQUE REFERENCES command_history(id) ON DELETE CASCADE, name TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('running','success','failed','cancelled')), started_at TEXT NOT NULL, finished_at TEXT NOT NULL DEFAULT '');
CREATE TABLE workflow_step_runs(run_id TEXT NOT NULL REFERENCES workflow_runs(id) ON DELETE CASCADE, position INTEGER NOT NULL, step_type TEXT NOT NULL, status TEXT NOT NULL CHECK(status IN ('pending','running','success','failed','skipped','cancelled')), outcome TEXT NOT NULL DEFAULT '', started_at TEXT NOT NULL DEFAULT '', finished_at TEXT NOT NULL DEFAULT '', PRIMARY KEY(run_id,position));
PRAGMA user_version = 7;
