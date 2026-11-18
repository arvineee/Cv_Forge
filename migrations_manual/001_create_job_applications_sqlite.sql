-- SQLite manual fallback. Back up the DB first; execute once.
CREATE TABLE job_applications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    resume_id INTEGER NULL REFERENCES resumes(id) ON DELETE SET NULL,
    company_name VARCHAR(180) NOT NULL,
    job_title VARCHAR(180) NOT NULL,
    job_url VARCHAR(1000),
    location VARCHAR(180),
    employment_type VARCHAR(60),
    salary_range VARCHAR(120),
    status VARCHAR(20) NOT NULL DEFAULT 'saved',
    date_applied DATE,
    deadline DATE,
    interview_at DATETIME,
    notes TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX ix_job_applications_user_id ON job_applications(user_id);
CREATE INDEX ix_job_applications_status ON job_applications(status);
