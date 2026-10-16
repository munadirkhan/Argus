import {DEFAULT_DENYLIST, blocked, collectPage} from './privacy.js';

let timer;
let generation = 0;
let sending;
const defaults = {enabled: false, denylist: DEFAULT_DENYLIST, status: 'off'};

async function settings() {
  const value = await chrome.storage.local.get(defaults);
  return {...value, denylist: Array.isArray(value.denylist) ? value.denylist : DEFAULT_DENYLIST};
}

async function focusedTab() {
  const window = await chrome.windows.getLastFocused();
  if (!window.focused || window.incognito) return null;
  const [tab] = await chrome.tabs.query({active: true, windowId: window.id});
  return tab && !tab.incognito && tab.status === 'complete' ? tab : null;
}

export async function schedule() {
  clearTimeout(timer);
  sending?.abort();
  const version = ++generation;
  try {
    const config = await settings();
    if (!config.enabled) return;
    const tab = await focusedTab();
    if (!tab || blocked(tab.url, config.denylist) || version !== generation) return;
    timer = setTimeout(() => capture(tab, version).catch(() => {}), 3000);
  } catch { /* A closed tab/window is ordinary, not an error to surface. */ }
}

async function capture(tab, version) {
  const config = await settings();
  const current = await focusedTab();
  if (!config.enabled || version !== generation || current?.id !== tab.id || current.url !== tab.url || blocked(current.url, config.denylist)) return;
  const key = `sent:${tab.id}`;
  if ((await chrome.storage.session.get(key))[key] === tab.url) return;
  const results = await chrome.scripting.executeScript({target: {tabId: tab.id}, func: collectPage});
  const payload = results[0]?.result;
  const latest = await settings();
  const focused = await focusedTab();
  if (!payload || payload.url !== tab.url || !latest.enabled || version !== generation || focused?.id !== tab.id || focused.url !== tab.url || blocked(payload.url, latest.denylist)) return;
  sending = new AbortController();
  const timeout = setTimeout(() => sending?.abort(), 2500);
  try {
    const response = await fetch('http://localhost:7600/sense/browser_tab', {
      method: 'POST', headers: {'Content-Type': 'application/json'},
      body: JSON.stringify(payload), signal: sending.signal,
    });
    if (response.ok && (await response.json()).ok && version === generation) {
      await chrome.storage.session.set({[key]: tab.url});
      await chrome.storage.local.set({status: `sent: ${payload.title}`});
    }
  } catch { /* Core off: retry only on a later tab/focus change. */ }
  finally { clearTimeout(timeout); }
}

chrome.tabs.onActivated.addListener(schedule);
chrome.tabs.onUpdated.addListener((id, change, tab) => {
  if (change.url) chrome.storage.session.remove(`sent:${id}`).catch(() => {});
  if (tab.active && (change.url || change.status)) schedule();
});
chrome.tabs.onRemoved.addListener(id => chrome.storage.session.remove(`sent:${id}`).catch(() => {}));
chrome.windows.onFocusChanged.addListener(schedule);
chrome.storage.onChanged.addListener((changes, area) => {
  if (area === 'local' && (changes.enabled || changes.denylist)) {
    schedule();
    if (changes.enabled?.newValue === false) chrome.storage.local.set({status: 'off'});
  }
});
chrome.runtime.onInstalled.addListener(async () => {
  const stored = await chrome.storage.local.get();
  await chrome.storage.local.set({...defaults, ...stored});
  schedule();
});
schedule();
