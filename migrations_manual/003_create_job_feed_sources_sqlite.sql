-- Optional: the app creates this table automatically (flask setup / flask ensure-schema / first visit to Admin -> Job sources).
CREATE TABLE IF NOT EXISTS job_feed_sources (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name VARCHAR(120) NOT NULL,
  url VARCHAR(1000) NOT NULL UNIQUE,
  country VARCHAR(80) NOT NULL DEFAULT 'Kenya',
  location VARCHAR(180),
  employment_type VARCHAR(60),
  is_active BOOLEAN NOT NULL DEFAULT 1,
  last_synced_at DATETIME,
  last_status VARCHAR(20),
  last_message VARCHAR(300),
  last_entry_count INTEGER NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_job_feed_sources_is_active ON job_feed_sources (is_active);
