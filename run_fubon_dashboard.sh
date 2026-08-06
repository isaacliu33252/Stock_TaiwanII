#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

echo
echo "Group A+ Fubon read-only dashboard refresh"
echo
echo "This will ask for:"
echo "  1. Fubon login password"
echo "  2. Fubon certificate password"
echo
echo "When typing passwords, the screen will not show letters or stars."
echo "Type the password and press Enter."
echo
echo "It only reads holdings and cash. It does not place orders."
echo

.venv/bin/python -m group_a_plus.dashboard.update_dashboard \
  --refresh-fubon \
  --local-config-dir 'C:\fubon' \
  --json

echo
echo "Dashboard: data/private/group_a_plus_dashboard.html"
