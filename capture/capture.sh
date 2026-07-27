#!/bin/sh
# offline-reader capture entrypoint.
#
# Crawls SEED_URL with single-file-cli (v2.0.83) into OUTPUT_DIR as a set of
# self-contained HTML Pages plus a crawl session (url -> filename map). Driven
# entirely by env vars set by the backend's K8sJobRunner (ADR-0002):
#
#   SEED_URL     (required)  root URL to capture
#   OUTPUT_DIR   (required)  where Pages land, e.g. /data/captures/<cid>/pages
#   MAX_DEPTH    (3)         crawl depth (0 = the single root Page)
#   WORKERS      (2)         parallel browser workers
#   WAIT_MS      (500)       extra settle delay after networkIdle
#   MAX_PAGES    (1000)      hard Page cap (enforced here — no native flag)
#   SCOPE_TYPE   (prefix)    page|prefix|host|domain (informational; the crawl
#                            flags below enforce the default prefix scope)
#   CHROME_PATH  (/usr/bin/chromium-browser)
#
# There is NO page-cap flag in single-file-cli, so we run it in the background
# and SIGTERM it once MAX_PAGES *.html files exist. single-file writes the
# session incrementally and closes cleanly on SIGTERM, so a page-capped crawl
# still yields a buildable manifest.
set -eu

: "${SEED_URL:?SEED_URL is required}"
: "${OUTPUT_DIR:?OUTPUT_DIR is required}"
MAX_DEPTH="${MAX_DEPTH:-3}"
WORKERS="${WORKERS:-2}"
WAIT_MS="${WAIT_MS:-500}"
MAX_PAGES="${MAX_PAGES:-1000}"
SCOPE_TYPE="${SCOPE_TYPE:-prefix}"
CHROME_PATH="${CHROME_PATH:-/usr/bin/chromium-browser}"

# The crawl scope base is the seed truncated at its last '/', so the seed MUST
# end in exactly one trailing slash (strip any, then add one).
SEED="${SEED_URL%/}/"

mkdir -p "$OUTPUT_DIR"

echo "capture: seed=$SEED depth=$MAX_DEPTH workers=$WORKERS max_pages=$MAX_PAGES scope=$SCOPE_TYPE"

count_pages() {
	# Count every captured Page file, not just *.html: single-file-cli names
	# Pages from the URL path, so clean URLs (e.g. '/') produce extension-less
	# names like '_'. Exclude the crawl's own session.json/errors.txt.
	find "$OUTPUT_DIR" -maxdepth 1 -type f ! -name 'session.json' ! -name 'errors.txt' 2>/dev/null | wc -l
}

# --crawl flags are verified for single-file-cli v2.0.83 — do not "correct" them.
# --no-sandbox / --disable-dev-shm-usage / --single-process are built into the tool.
# SC2016: the `$1` in --crawl-rewrite-rule is single-file's regex backreference,
# not a shell var — it MUST stay single-quoted (unexpanded).
# shellcheck disable=SC2016
single-file "$SEED" \
	--crawl-links=true --crawl-inner-links-only=true --crawl-no-parent=true \
	--crawl-max-depth="$MAX_DEPTH" --crawl-remove-URL-fragment=true \
	--crawl-rewrite-rule='^(.*)\?.*$ $1' \
	--crawl-save-session="${OUTPUT_DIR}/session.json" \
	--filename-template='{url-pathname-flat}' --filename-conflict-action=uniquify \
	--browser-wait-until=networkIdle --browser-wait-delay="$WAIT_MS" \
	--load-deferred-images=true --max-parallel-workers="$WORKERS" \
	--output-directory="${OUTPUT_DIR}/" --errors-file="${OUTPUT_DIR}/errors.txt" \
	--browser-executable-path="$CHROME_PATH" &
SF_PID=$!

# Watcher: stop the crawl once MAX_PAGES Pages are on disk.
while kill -0 "$SF_PID" 2>/dev/null; do
	pages=$(count_pages)
	if [ "$pages" -ge "$MAX_PAGES" ]; then
		echo "capture: reached MAX_PAGES=$MAX_PAGES ($pages pages) — stopping single-file"
		kill -TERM "$SF_PID" 2>/dev/null || true
		break
	fi
	sleep 2
done

# single-file's TERM-induced exit is non-zero but a page-capped crawl is a
# success, so don't let it fail the Job.
wait "$SF_PID" 2>/dev/null || true

# Present the layout the backend expects: session.json + errors.txt at the
# Capture root (one level above the pages/ output dir); Pages stay in OUTPUT_DIR.
CAPTURE_ROOT=$(dirname "$OUTPUT_DIR")
if [ -f "${OUTPUT_DIR}/session.json" ]; then
	mv -f "${OUTPUT_DIR}/session.json" "${CAPTURE_ROOT}/session.json"
fi
if [ -f "${OUTPUT_DIR}/errors.txt" ]; then
	mv -f "${OUTPUT_DIR}/errors.txt" "${CAPTURE_ROOT}/errors.txt"
fi

echo "capture: done — $(count_pages) pages in $OUTPUT_DIR"
