-- CVForge Sprint 007: public job discovery catalogue (SQLite)
CREATE TABLE IF NOT EXISTS job_opportunities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    external_key VARCHAR(64) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    company_name VARCHAR(180) NOT NULL DEFAULT 'See original listing',
    description TEXT NOT NULL,
    url VARCHAR(1000) NOT NULL,
    source_name VARCHAR(120) NOT NULL,
    source_url VARCHAR(1000) NOT NULL,
    country VARCHAR(80) NOT NULL DEFAULT 'International',
    location VARCHAR(180),
    employment_type VARCHAR(60),
    published_at DATETIME,
    last_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN NOT NULL DEFAULT 1,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_job_opportunities_external_key ON job_opportunities (external_key);
CREATE INDEX IF NOT EXISTS ix_job_opportunities_title ON job_opportunities (title);
CREATE INDEX IF NOT EXISTS ix_job_opportunities_country ON job_opportunities (country);
CREATE INDEX IF NOT EXISTS ix_job_opportunities_location ON job_opportunities (location);
CREATE INDEX IF NOT EXISTS ix_job_opportunities_published_at ON job_opportunities (published_at);
CREATE INDEX IF NOT EXISTS ix_job_opportunities_is_active ON job_opportunities (is_active);
