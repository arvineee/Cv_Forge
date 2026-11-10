# CVForge optimization and deployment notes

This update keeps the existing Flask application factory, blueprints, payment
providers, authentication flows, database schema, and PythonAnywhere deployment
model. No database migration is required.

## Changes

- Visitor tracking now records GET page views through a bounded, per-process
  queue and batches inserts (up to 50 rows, with a 250 ms flush window). The
  request no longer waits for the visitor-tracking database commit. POST
  submissions are not counted as page views. If the queue fills, analytics
  events are dropped rather than delaying customer requests. Events still in
  memory when a PythonAnywhere worker restarts may be lost; this queue is only
  for non-critical analytics, never account, CV, payment, or subscription data.
- Offer seat counts are cached within a pricing operation so the same capped
  offer is not counted repeatedly for multiple plans.
- Flask-served static assets receive a one-day public cache header. Dynamic
  pages, authentication, checkout, and generated documents are not given this
  static-asset cache policy.
- HSTS max-age is increased to two years while retaining `includeSubDomains`.
  `preload` is deliberately not added because CVForge does not control the
  parent `pythonanywhere.com` domain.
- An optional Content-Security-Policy-Report-Only header can be configured
  through `CONTENT_SECURITY_POLICY_REPORT_ONLY`. It is not enforced by default,
  so third-party payment, OAuth, support, and AI integrations are not blocked
  by an unverified policy.

## PythonAnywhere deployment

1. Back up the existing application directory and database before deployment.
2. Upload/extract the updated source files over the application source.
3. Keep the existing `.env` or PythonAnywhere environment variables unchanged.
4. Keep the existing `instance/` database, `uploads/` directory, and any other
   user-generated files in place. They are intentionally not included in the
   source ZIP.
5. Confirm the PythonAnywhere WSGI file still imports `app.create_app` using
   the same project path and virtual environment.
6. Reload the web app from the PythonAnywhere Web tab.
7. Smoke-test the homepage, login/register, dashboard, CV PDF/DOCX generation,
   pricing, checkout initiation for each enabled provider, and payment webhook
   callbacks. Do not test live payments with real money; use provider test mode
   where available.

## Optional settings

```ini
VISITOR_TRACKING_ASYNC=true
VISITOR_TRACKING_QUEUE_SIZE=2048
STATIC_ASSET_MAX_AGE=86400
# Start with report-only; inspect browser console violations before enforcing.
# CONTENT_SECURITY_POLICY_REPORT_ONLY=default-src 'self'; object-src 'none'; base-uri 'self'
```

Set `VISITOR_TRACKING_ASYNC=false` only as a temporary diagnostic fallback; it
restores synchronous writes and can increase request latency.

## Validation performed in the build environment

- Python bytecode compilation: passed.
- 17 offer/pricing logic tests: passed.
- Additional dependency-light test modules: passed (some app-integration tests
  were skipped because Flask and Werkzeug are not installed in the build
  environment).
- Full Flask integration, payment-provider, and PythonAnywhere runtime tests
  could not be executed here because the environment has no network access to
  install the project's Flask dependencies. Run the full suite in the existing
  project virtualenv or PythonAnywhere console before production rollout.
