#!/usr/bin/env bash
set -euo pipefail

SITE_NAME="${1:-}"
BENCH_PATH="${2:-/home/frappe/frappe-bench}"
APP_NAME="erpnext_payment_uploading"
APP_BRANCH="${APP_BRANCH:-codex/payment-upload}"
APP_REPOSITORY="${APP_REPOSITORY:-https://github.com/jryandechavez/erpnext-payment-uploading.git}"

if [[ -z "$SITE_NAME" ]]; then
	echo "Usage: sudo bash install.sh <site-name> [bench-path]" >&2
	exit 1
fi

if [[ ! -d "$BENCH_PATH/apps/frappe" || ! -f "$BENCH_PATH/sites/apps.txt" ]]; then
	echo "Not a valid Frappe Bench: $BENCH_PATH" >&2
	exit 1
fi

APPS_FILE="$BENCH_PATH/sites/apps.txt"
cp "$APPS_FILE" "$APPS_FILE.before-${APP_NAME}-install"

# Normalize apps.txt before Bench appends to it. This prevents a missing final
# newline from producing names such as "hrmserpnext_payment_uploading".
python3 - "$APPS_FILE" "$APP_NAME" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
app = sys.argv[2]
lines = []
for raw in path.read_text().splitlines():
    value = raw.strip()
    if not value:
        continue
    if value != app and value.endswith(app):
        prefix = value[:-len(app)]
        if prefix:
            lines.append(prefix)
        value = app
    if value not in lines:
        lines.append(value)
path.write_text("\n".join(lines) + "\n")
PY

chown frappe:frappe "$APPS_FILE"

if [[ ! -d "$BENCH_PATH/apps/$APP_NAME" ]]; then
	runuser -u frappe -- bash -lc "cd '$BENCH_PATH' && bench get-app --skip-assets --branch '$APP_BRANCH' '$APP_REPOSITORY'"
else
	echo "$APP_NAME already exists in apps; skipping clone."
fi

# Keep the registry normalized even when recovering from a previously failed
# get-app command.
python3 - "$APPS_FILE" "$APP_NAME" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
app = sys.argv[2]
lines = [line.strip() for line in path.read_text().splitlines() if line.strip()]
lines = list(dict.fromkeys(lines))
if app not in lines:
    lines.append(app)
path.write_text("\n".join(lines) + "\n")
PY

chown -R frappe:frappe "$BENCH_PATH/apps/$APP_NAME" "$APPS_FILE"

runuser -u frappe -- bash -lc "
set -e
cd '$BENCH_PATH'
./env/bin/python -m pip install --quiet --upgrade -e 'apps/$APP_NAME'
bench --site '$SITE_NAME' install-app '$APP_NAME' || bench --site '$SITE_NAME' list-apps | grep -qx '$APP_NAME'
bench --site '$SITE_NAME' migrate
bench --site '$SITE_NAME' clear-cache
bench --site '$SITE_NAME' list-apps
"

cd "$BENCH_PATH"
bench restart

echo "Installed $APP_NAME on $SITE_NAME"
echo "Open: /app/payment-upload"
