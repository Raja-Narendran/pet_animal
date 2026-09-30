-- Pet Animal V2: normalized, local application data.
CREATE TABLE memory_categories(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, sensitive INTEGER NOT NULL DEFAULT 0 CHECK(sensitive IN (0,1)));
CREATE TABLE memories(id TEXT PRIMARY KEY, category_id TEXT NOT NULL REFERENCES memory_categories(id), title TEXT NOT NULL, memory_key TEXT NOT NULL UNIQUE, memory_value TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE INDEX memories_category ON memories(category_id);
CREATE TABLE commands(id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', action_type TEXT NOT NULL, action_config TEXT NOT NULL, success_message TEXT NOT NULL DEFAULT '', failure_message TEXT NOT NULL DEFAULT '', enabled INTEGER NOT NULL DEFAULT 1 CHECK(enabled IN (0,1)), is_builtin INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE TABLE command_phrases(id TEXT PRIMARY KEY, command_id TEXT NOT NULL REFERENCES commands(id) ON DELETE CASCADE, phrase TEXT NOT NULL, normalized_phrase TEXT NOT NULL UNIQUE, created_at TEXT NOT NULL);
CREATE TABLE applications(id TEXT PRIMARY KEY, name TEXT NOT NULL UNIQUE, executable_path TEXT NOT NULL);
CREATE TABLE pet_assets(id TEXT PRIMARY KEY, name TEXT NOT NULL, filename TEXT NOT NULL UNIQUE, imported INTEGER NOT NULL DEFAULT 0);
CREATE TABLE pet_profiles(id TEXT PRIMARY KEY, name TEXT NOT NULL, selected_asset_id TEXT NOT NULL REFERENCES pet_assets(id), is_active INTEGER NOT NULL DEFAULT 0 CHECK(is_active IN (0,1)), created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
CREATE UNIQUE INDEX single_active_profile ON pet_profiles(is_active) WHERE is_active = 1;
CREATE TABLE pet_settings(profile_id TEXT PRIMARY KEY REFERENCES pet_profiles(id) ON DELETE CASCADE, config TEXT NOT NULL);
CREATE TABLE command_history(id TEXT PRIMARY KEY, command_id TEXT REFERENCES commands(id) ON DELETE SET NULL, trigger_phrase TEXT NOT NULL, execution_status TEXT NOT NULL CHECK(execution_status IN ('success','failed')), error_message TEXT NOT NULL DEFAULT '', executed_at TEXT NOT NULL);
CREATE INDEX history_time ON command_history(executed_at);
CREATE TABLE app_settings(key TEXT PRIMARY KEY, value TEXT NOT NULL);
PRAGMA user_version = 1;
