.PHONY: run setup doctor test css sync
run:     ; flask --app run.py run --debug
setup:   ; flask --app run.py setup          # tables + seed data + admin (idempotent)
doctor:  ; flask --app run.py doctor         # tells you what is misconfigured
test:    ; python -m pytest -q tests
sync:    ; flask --app run.py sync-job-feeds
# Rebuild Tailwind after changing classes in templates (needs: npm i -D tailwindcss@3.4.17)
css:     ; npx tailwindcss -c tailwind.config.js -i tailwind.input.css -o app/static/css/tw.css --minify
