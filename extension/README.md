# Browser sense and headless browsing

Start the core on port 7600. Open `chrome://extensions`, enable **Developer
mode**, choose **Load unpacked**, and select this `extension/` folder. Open the
Argus extension popup and turn sharing on. It is **off by default**.

After an eligible tab stays active in the focused browser window for 3 seconds,
the extension sends its URL, title, selected text and at most 2,000 characters
of visible page text to `http://localhost:7600/sense/browser_tab`. The browser
window should appear in the LIVE UI within roughly 4 seconds. The popup reports
`sent: <title>`. Each tab URL is sent once, until that tab's URL changes.
No page text is stored by the extension. The local core retains session events.

Incognito, browser-internal pages, form/editable fields and excluded domains
are skipped. Edit the domain denylist in the popup and save it; entries match
subdomains too and support `*`. Defaults cover common banking, health, mail and
password-manager domains; add any sensitive sites specific to your workflow.
Sharing stops when switched off. This does not erase events already received
by the core. If the core is unavailable, delivery quietly retries on the next
tab/focus change. Permissions are only tabs, scripting, storage and all-URL host
access; broad host access is required to read eligible tabs.

## The `browse` tool

From the repository, install the core requirements and Chromium:

```powershell
./.venv/Scripts/python.exe -m pip install -r requirements.txt
./.venv/Scripts/python.exe -m playwright install chromium
```

On macOS/Linux use `.venv/bin/python`. Restart core; `/health` lists `browser_tab`
and `browse`. The agent can call `browse(url, find?, links?)` when `fetch_url`
returns too little or the page needs JavaScript. It reads main/article/body,
optionally extracts matching passages and up to 20 links, and emits a browser
activity via the existing tool result contract.

Chromium is shared lazily, with a new cookie-free context for each call. Only
GET/HEAD requests are allowed; forms, WebSockets, service workers and downloads
are disabled. It does not click, type, log in, or reuse your browser profile.
Every outbound connection uses a proxy that resolves and pins public IPs,
rejecting private, loopback, link-local, reserved and multicast addresses,
including redirects and subresources. Navigation is capped at 15 seconds,
network-idle waiting at 5, and the complete call at 25 including cleanup.

Validation:

```powershell
./.venv/Scripts/python.exe core/sensors/tests/test_browser_tab.py
./.venv/Scripts/python.exe core/tools/tests/test_browse.py
node extension/tests/privacy.mjs
```

The browse suite performs a live `https://example.com` read when Chromium is
installed; otherwise it explicitly skips that check. The sensor and security
tests require no API keys. Page excerpts remain data, never instructions.
