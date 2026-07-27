# offline-reader capture image — single-file-cli crawling into the shared PVC.
#
# Published as ghcr.io/viktorbarzin/offline-reader-capture (CI handled separately).
# Base: zenika/alpine-chrome:with-node — a hardened headless Chromium + Node, the
# official single-file-cli runtime path. Chromium lives at /usr/bin/chromium-browser.
FROM zenika/alpine-chrome:with-node

# npm global install needs root; the base image otherwise runs as the unprivileged
# "chrome" user (uid 1000), which we restore before running the crawl.
USER root

# single-file-cli v2.0.83 — pinned for reproducible captures (crawl flags in
# capture.sh are verified against this exact version).
RUN npm install -g single-file-cli@2.0.83

COPY capture.sh /usr/local/bin/capture.sh
RUN chmod +x /usr/local/bin/capture.sh

# Chromium path on this base image; capture.sh also defaults to it.
ENV CHROME_PATH=/usr/bin/chromium-browser

# Back to the unprivileged user the base image ships with.
USER chrome

ENTRYPOINT ["/usr/local/bin/capture.sh"]
