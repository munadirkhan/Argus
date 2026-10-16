"""Read JavaScript pages in an isolated, public-network-only Chromium context."""
from __future__ import annotations
import asyncio
import re
from .base import Tool, ToolResult
from ._browse_network import PublicProxy, validate_url

INSTALL = 'browse needs: pip install playwright && python -m playwright install chromium'


class Browse(Tool):
    name = 'browse'
    description = ('Read a page with JavaScript. Use only when fetch_url returned little or nothing useful, '
                   'or the page needs JavaScript. Read-only; cannot click, log in, or submit forms.')
    parameters = {'type': 'object', 'properties': {
        'url': {'type': 'string', 'description': 'Public http(s) page URL.'},
        'find': {'type': 'string', 'description': 'Optional text: return passages around its matches.'},
        'links': {'type': 'boolean', 'description': 'Also include up to 20 page links.'}}, 'required': ['url']}

    def __init__(self):
        self.browser = None
        self.playwright = None
        self.proxy = None
        self.lock = None
        self.loop = None

    async def _browser(self, factory):
        loop = asyncio.get_running_loop()
        if self.loop is not loop:
            self.loop, self.lock = loop, asyncio.Lock()
            self.browser = self.playwright = self.proxy = None
        async with self.lock:
            if self.browser is None or not self.browser.is_connected():
                await self.close()
                self.proxy = PublicProxy()
                endpoint = await self.proxy.start()
                try:
                    self.playwright = await factory().start()
                    self.browser = await self.playwright.chromium.launch(headless=True,
                        proxy={'server': endpoint}, args=['--proxy-bypass-list=<-loopback>'])
                except BaseException:
                    await self.close()
                    raise
            return self.browser

    async def close(self):
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()
        if self.proxy:
            await self.proxy.close()
        self.browser = self.playwright = self.proxy = None

    async def run(self, url: str, find: str = '', links: bool = False) -> ToolResult:
        context = None
        try:
            async with asyncio.timeout(23):
                parsed = await validate_url(url)
                if not isinstance(find, str) or not isinstance(links, bool):
                    return ToolResult(ok=False, summary='find must be text; links must be boolean')
                try:
                    from playwright.async_api import async_playwright, TimeoutError as PlaywrightTimeout
                except ImportError:
                    return ToolResult(ok=False, summary=INSTALL)
                try:
                    browser = await self._browser(async_playwright)
                except Exception:
                    return ToolResult(ok=False, summary=INSTALL)
                context = await browser.new_context(accept_downloads=False, service_workers='block')
                context.set_default_timeout(3000)
                async def guard(route):
                    try:
                        if route.request.method not in ('GET', 'HEAD'):
                            return await route.abort()
                        await validate_url(route.request.url)
                        await route.continue_()
                    except Exception:
                        await route.abort()
                await context.route('**/*', guard)
                await context.route_web_socket('**/*', lambda ws: ws.close())
                await context.add_init_script("""
                    Object.defineProperty(window, 'RTCPeerConnection', {value: undefined, configurable: false});
                    for (const name of ['submit', 'requestSubmit'])
                        Object.defineProperty(HTMLFormElement.prototype, name, {value() {}, configurable: false});
                    document.addEventListener('submit', event => event.preventDefault(), true);
                """)
                page = await context.new_page()
                page.on('dialog', lambda dialog: dialog.dismiss())
                response = await page.goto(url, timeout=15000, wait_until='domcontentloaded')
                if response and response.status >= 400:
                    return ToolResult(ok=False, summary=f'browse HTTP {response.status}')
                try:
                    await page.wait_for_load_state('networkidle', timeout=5000)
                except PlaywrightTimeout:
                    pass
                parsed = await validate_url(page.url)
                data = await page.evaluate("""() => {
                  const root = document.querySelector('main') || document.querySelector('article') || document.body;
                  return {title: document.title, text: (root?.innerText || '').slice(0, 200000),
                    links: Array.from((root || document).querySelectorAll('a[href]')).slice(0, 200)
                      .map(a => ({text: a.innerText.trim(), url: a.href}))};
                }""")
                text = re.sub(r'[ \t]+', ' ', data['text']).strip()
                if find:
                    matches = list(re.finditer(re.escape(find), text, re.I))[:20]
                    spans = []
                    for match in matches:
                        start, end = max(0, match.start() - 250), min(len(text), match.end() + 450)
                        if spans and start <= spans[-1][1]:
                            spans[-1] = (spans[-1][0], end)
                        else:
                            spans.append((start, end))
                    text = '\n…\n'.join(text[a:b] for a, b in spans) if spans else f'No passages matching {find[:100]!r}.\n' + text
                if links:
                    from ._browse_network import parse_url
                    lines = []
                    for link in data['links']:
                        try:
                            parse_url(link['url'])
                        except ValueError:
                            continue
                        if link['text']:
                            label = link['text'].replace('[', '').replace(']', '')[:160]
                            lines.append(f"[{label}]({link['url']})")
                        if len(lines) == 20:
                            break
                    text = text[:8000] + ('\n\n' + '\n'.join(lines) if lines else '')
                text = text[:12000]
                title = data['title'][:500] or parsed.hostname
                return ToolResult(ok=True, summary=f'{parsed.hostname} · {len(text)} chars', detail=text,
                    meta={'activity': {'type': 'activity', 'source': 'browser', 'app': 'Argus · browsing',
                        'title': title, 'url': page.url, 'focus': True,
                        'lines': [{'text': l[:400]} for l in text.splitlines() if l.strip()][:6]}})
        except TimeoutError:
            return ToolResult(ok=False, summary='browse timed out (25s limit)')
        except Exception as exc:
            return ToolResult(ok=False, summary=f'browse refused or failed: {str(exc)[:150]}')
        finally:
            if context:
                try:
                    await asyncio.wait_for(context.close(), timeout=1)
                except Exception:
                    pass


TOOL = Browse()
