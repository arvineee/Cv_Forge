-- Optional: the app creates this table automatically (flask setup / flask ensure-schema / first visit to Admin -> Job sources).
CREATE TABLE IF NOT EXISTS job_feed_sources (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL,
  url VARCHAR(1000) NOT NULL,
  country VARCHAR(80) NOT NULL DEFAULT 'Kenya',
  location VARCHAR(180) NULL,
  employment_type VARCHAR(60) NULL,
  is_active TINYINT(1) NOT NULL DEFAULT 1,
  last_synced_at DATETIME NULL,
  last_status VARCHAR(20) NULL,
  last_message VARCHAR(300) NULL,
  last_entry_count INT NOT NULL DEFAULT 0,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY uq_job_feed_sources_url (url(255)),
  KEY ix_job_feed_sources_is_active (is_active)
);
