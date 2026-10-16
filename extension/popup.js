import {DEFAULT_DENYLIST} from './privacy.js';
const enabled = document.querySelector('#enabled');
const denylist = document.querySelector('#denylist');
const status = document.querySelector('#status');
const saved = await chrome.storage.local.get({enabled: false, denylist: DEFAULT_DENYLIST, status: 'off'});
enabled.checked = saved.enabled;
denylist.value = saved.denylist.join('\n');
status.textContent = saved.enabled ? saved.status : 'off';
enabled.addEventListener('change', async () => {
  await chrome.storage.local.set({enabled: enabled.checked, status: enabled.checked ? 'on · waiting for a page' : 'off'});
});
document.querySelector('#save').addEventListener('click', async () => {
  const domains = [...new Set(denylist.value.split('\n').map(s => s.trim().toLowerCase()).filter(Boolean))];
  await chrome.storage.local.set({denylist: domains});
  status.textContent = enabled.checked ? 'on · exclusions saved' : 'off';
});
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && changes.status) status.textContent = changes.status.newValue;
});
