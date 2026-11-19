> **Update:** job feed URLs are now managed in the app at **Admin -> Job sources**. Paste a feed URL, it is tested and approved automatically, and listings import immediately. The .env settings described below still work and can be imported with one click.

# CVForge Job Discovery — operator setup

Sprint 007 adds an RSS/Atom vacancy catalogue. It does **not** scrape job-board pages, bypass access controls, or assume that a website offers a public feed. Only feeds you have permission to consume and display should be configured.

## What is included

- Authenticated `/career/jobs` search by keyword, country and location.
- Vacancy cards with the original publisher link, save-to-Career-Workspace action and CV matching shortcut.
- RSS and Atom ingestion through `flask sync-job-feeds`.
- Deduplication by a SHA-256 key derived from source name and feed GUID/ID (or link); listings missing from a successfully fetched feed are deactivated.
- Configurable HTTPS hostname allow-list, no redirects, a 2 MB response cap, 15-second read timeout and a 200-entry per-feed processing cap.
- No AI calls are made during feed sync. CV matching uses the existing Job Match workflow when the user chooses it.

## 1. Apply the database migration

Back up the production database first. Apply exactly one script matching the live database engine:

- PostgreSQL: `migrations_manual/002_create_job_opportunities_postgresql.sql`
- SQLite: `migrations_manual/002_create_job_opportunities_sqlite.sql`

Do not run both. The Sprint 005 `job_applications` migration must already be applied as well.

## 2. Configure sources on Ubuntu

Add these values to the existing production environment file (do not replace the file):

```dotenv
JOB_FEED_ALLOWED_DOMAINS=careers.example.org,work.example.net
JOB_FEEDS_JSON=[{"name":"Example Careers","url":"https://careers.example.org/jobs/rss.xml","country":"Kenya","location":"Kenya"}]
```

These are illustrative placeholders, not real feeds. Replace them with verified feed URLs and domains that the publisher permits CVForge to consume. `JOB_FEED_ALLOWED_DOMAINS` must list the feed hosts. Keep the domain list as narrow as possible. The feed URL must use HTTPS and redirects are rejected.

A source may be RSS or Atom. Feed entries should expose title, link, and description/summary/content. Author/creator is used as the employer label when available; otherwise the UI says “See original listing”. Do not assume every feed has company, salary, location, closing date or employment type fields.

## 3. Test manually before scheduling

From the project directory, with the production virtual environment activated:

```bash
flask sync-job-feeds
```

Run it once manually, inspect the reported counts and logs, then visit `https://cvforge.site/career/jobs` with a test account. Confirm original links, duplicates, text rendering and save-to-workspace behaviour.

## 4. Schedule on Ubuntu

After manual verification, add a cron entry for the actual Linux service user. Replace paths and service account placeholders with the values used by the VPS:

```cron
15 */4 * * * cd /srv/cvforge/current && /srv/cvforge/venv/bin/flask sync-job-feeds >> /var/log/cvforge/job-feed-sync.log 2>&1
```

Create the log directory with restricted permissions and configure log rotation. Do not run the command concurrently from multiple schedulers. The importer is idempotent for the same source name and GUID/link.

## Security and editorial controls

- Configure only publisher-approved feeds and preserve source attribution/linking.
- Review publisher terms and applicable copyright/database rights before enabling a source.
- The importer fetches only allow-listed HTTPS feed hosts, rejects redirects, checks DNS answers are public IP addresses, and caps feed size.
- This is not a substitute for a managed egress firewall. For higher assurance, restrict outbound traffic from the worker to the approved feed hosts at the VPS/network layer.
- Imported vacancies can expire or be removed at the publisher. The listing page tells users to verify the original source; CVForge does not guarantee vacancy availability.
- No automatic email alerts are sent in this sprint.

## Rollback

Stop the cron entry first. Revert the application release. The new table can be left unused safely; drop it only after confirming no later release depends on it and after taking a fresh backup. No user application records are altered by this migration.
