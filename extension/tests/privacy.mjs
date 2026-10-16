import assert from 'node:assert/strict';
import {blocked, DEFAULT_DENYLIST} from '../privacy.js';

for (const url of ['chrome://settings', 'file:///secret', 'https://mail.google.com/',
  'https://x.chase.com/', 'https://my.bank.example', 'https://1password.com',
  'https://bitwarden.com', 'https://portal.health.example', 'https://mychart.example',
  'https://paypal.com', 'https://user:secret@example.com']) {
  assert.equal(blocked(url, DEFAULT_DENYLIST), true, url);
  console.log(`[PASS] skipped ${url}`);
}
assert.equal(blocked('https://example.com', DEFAULT_DENYLIST), false);
assert.equal(blocked('https://nvidia.com', DEFAULT_DENYLIST), false);
assert.equal(blocked('https://notchase.com', ['chase.com']), false);
assert.equal(blocked('https://x.example.com', ['example.com']), true);
assert.equal(blocked('https://example.com', ['exampleXcom']), false);
console.log('[PASS] public URLs, subdomains and escaped patterns');
