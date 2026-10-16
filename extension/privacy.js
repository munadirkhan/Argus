export const DEFAULT_DENYLIST = [
  'mail.google.com', 'outlook.live.com', 'outlook.office.com', 'mail.*', '*.bank*',
  '1password.com', 'bitwarden.com', 'lastpass.com', 'chase.com', 'paypal.com',
  'bankofamerica.com', 'wellsfargo.com', 'td.com', 'rbcroyalbank.com',
  'mychart.*', '*.mychart.*', '*.health*', 'health.*', 'patient.*', '*.patient.*',
];

export function blocked(url, denylist) {
  try {
    const parsed = new URL(url);
    if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password) return true;
    const host = parsed.hostname.toLowerCase().replace(/\.$/, '');
    return denylist.some((pattern) => {
      const clean = pattern.trim().toLowerCase();
      if (!clean) return false;
      const escaped = clean.replace(/[.+?^${}()|[\]\\]/g, '\\$&').replace(/\*/g, '.*');
      return new RegExp(`^(?:.*\\.)?${escaped}$`).test(host);
    });
  } catch { return true; }
}

// This function is serialized into the tab by chrome.scripting. Keep it self-contained.
export function collectPage() {
  const excluded = 'input, textarea, select, option, [contenteditable]:not([contenteditable="false"]), [role="textbox"], script, style, noscript';
  const fields = [...document.querySelectorAll(excluded)];
  const selected = window.getSelection();
  let selection = '';
  if (selected && selected.rangeCount) {
    const safe = !fields.some(field => {
      for (let i = 0; i < selected.rangeCount; i++) {
        if (selected.getRangeAt(i).intersectsNode(field)) return true;
      }
      return false;
    });
    if (safe) selection = selected.toString().slice(0, 1000);
  }
  // Read rendered text nodes, skipping form/editable subtrees BEFORE reading
  // their text. body.innerText alone can include textarea/select contents.
  const walker = document.createTreeWalker(document.body || document.documentElement, NodeFilter.SHOW_TEXT);
  const parts = [];
  let length = 0, visited = 0, node;
  while (length < 2000 && visited++ < 20000 && (node = walker.nextNode())) {
    const parent = node.parentElement;
    if (!parent || parent.closest(excluded)) continue;
    if (!parent.checkVisibility({checkOpacity: true, checkVisibilityCSS: true})) continue;
    const value = node.textContent.replace(/\s+/g, ' ').trim();
    if (value) { parts.push(value); length += value.length + 1; }
  }
  return {url: location.href, title: document.title, selection,
    text: parts.join(' ').slice(0, 2000), ts: Date.now() / 1000};
}
