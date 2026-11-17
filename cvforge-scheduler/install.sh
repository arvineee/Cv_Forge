#!/usr/bin/env bash
# Run on the VPS as root:  sudo bash install.sh
set -euo pipefail
cd "$(dirname "$0")"

APP_DIR="${APP_DIR:-/var/www/cvforge}"
APP_USER="${APP_USER:-www-data}"

# Adjust the unit files to your real paths/user if they differ from the defaults.
for f in cvforge-*.service; do
  sed -i "s|/var/www/cvforge|$APP_DIR|g; s|^User=.*|User=$APP_USER|" "$f"
done

cp cvforge-*.service cvforge-*.timer /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now cvforge-nudges.timer cvforge-cv-reminders.timer cvforge-prune-visits.timer

echo
systemctl list-timers 'cvforge-*' --no-pager
echo
echo "Test now (no waiting):  sudo systemctl start cvforge-nudges.service"
echo "Logs:                   journalctl -u cvforge-nudges.service -n 50 --no-pager"
