# Offline Reader

A self-hosted way to read whole websites offline (e.g. on a plane). You feed a URL to an
endpoint; the server crawls and faithfully preserves the site as a set of self-contained
pages; an installable PWA downloads chosen Captures onto your phone and reads them with no
network — and no manual file handling.

## Language

**Capture**:
A saved website — one root URL crawled and faithfully preserved as a set of self-contained
Pages you can read offline. The unit of the Library. (Verb: _to Capture_ is the server-side
act of crawling and snapshotting a site from the web.) _Avoid_: site, mirror, archive,
bookmark.

**Page**:
One captured web page, saved as a single self-contained HTML file — its styles, images, and
fonts inlined; scripts removed — that renders as it looked at capture time, offline.
_Avoid_: snapshot, document.

**Crawl**:
Turning a root URL into a Capture — fetching and rendering its pages with a headless
browser, bounded by Scope and by size/count caps. _Avoid_: spider, scrape.

**Scope**:
The rules that decide which pages a Crawl includes — by default the root URL's path prefix,
adjustable with include/exclude patterns and depth/count caps. _Avoid_: filter, boundary.

**Library**:
The catalog of Captures available to browse and Download.

**Download** (device side):
Pulling a Capture's Pages into the app's on-device storage so they read with no network. The
server _Crawls_ from the web; the phone _Downloads_ from the Library, in-app. _Avoid_: sync,
pin, cache.

**Refresh**:
Re-running a Capture's Crawl for current content; the new Pages replace the old ones in
place — latest only, no version history. _Avoid_: update, re-sync.

**Reader**:
The PWA's reading surface — renders a Page in a sandboxed frame with a table of contents for
moving between a Capture's Pages, fully offline. _Avoid_: viewer.
