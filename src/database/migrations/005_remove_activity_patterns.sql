-- Migration 005: Remove habit_candidates table and Activity Patterns
DROP INDEX IF EXISTS habit_candidates_status;
DROP TABLE IF EXISTS habit_candidates;

PRAGMA user_version = 5;
