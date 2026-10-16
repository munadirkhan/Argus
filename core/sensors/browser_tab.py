"""Opt-in browser context pushed by the unpacked Chrome extension."""
from __future__ import annotations
import math
from urllib.parse import urlsplit
from .base import Sensor


class BrowserTab(Sensor):
    name = 'browser_tab'
    interval = 0.5

    def __init__(self):
        self.latest = None
        self.pending = False

    def receive(self, payload):
        if not isinstance(payload, dict):
            return False
        if not all(isinstance(payload.get(k, ''), str) for k in ('url', 'title', 'text', 'selection')):
            return False
        if 'title' not in payload or 'url' not in payload:
            return False
        url = payload['url']
        try:
            parsed = urlsplit(url)
            if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
                    parsed.username or parsed.password or len(url) > 8192 or
                    any(ord(c) < 32 for c in url)):
                return False
            _ = parsed.port
        except ValueError:
            return False
        ts = payload.get('ts')
        if ts is not None and (type(ts) not in (int, float) or not math.isfinite(ts)):
            return False
        page = {'url': url, 'title': payload['title'][:500],
                'text': payload.get('text', '')[:4000],
                'selection': payload.get('selection', '')[:1000]}
        if page != self.latest:
            self.latest = page
            self.pending = True
        return True

    async def poll(self):
        if not self.pending or self.latest is None:
            return []
        self.pending = False
        page = self.latest
        lines = ([{'text': page['selection'], 'tone': 'hl'}] if page['selection'] else [])
        lines += [{'text': line[:500]} for line in page['text'].splitlines() if line.strip()][:6]
        return [{'type': 'activity', 'source': 'browser', 'app': 'Browser',
                 'title': page['title'], 'url': page['url'], 'lines': lines, 'focus': True}]

    def context(self):
        if self.latest is None:
            return ''
        page = self.latest
        return f"User is reading: {page['title']} ({page['url']})\n{page['selection']}\n{page['text'][:600]}"

    def alert(self, event):
        return False


SENSOR = BrowserTab()
