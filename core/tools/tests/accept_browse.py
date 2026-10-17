"""Manual real-model browser acceptance against running core and web servers.

Uses configured core credentials and budget. Raw events stay in ignored web/.local.
Run: python core/tools/tests/accept_browse.py
"""
import asyncio
import json
from pathlib import Path


async def main():
    import websockets
    from playwright.async_api import async_playwright
    output = Path('web/.local/browser-live')
    output.mkdir(parents=True, exist_ok=True)
    errors, events = [], []
    finished = asyncio.Event()
    active = False
    async with websockets.connect('ws://localhost:7600/ws') as ws, async_playwright() as pw:
        async def collect():
            with (output / 'argus-session.jsonl').open('w', encoding='utf-8') as log:
                async for raw in ws:
                    event = json.loads(raw)
                    if not active:
                        continue
                    events.append(event)
                    log.write(raw + '\n')
                    log.flush()
                    if event['type'] == 'error':
                        finished.set()
                    if event['type'] == 'agent.message' and event.get('role') == 'assistant' and event.get('done'):
                        finished.set()

        task = asyncio.create_task(collect())
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
        await page.goto('http://127.0.0.1:5173/')
        await page.locator('.sense').filter(has_text='BROWSER').wait_for()
        active = True
        await ws.send(json.dumps({'type': 'user.message', 'text':
            'Use browse to read https://quotes.toscrape.com/js/ (this page needs JavaScript), '
            'find Einstein. Reply briefly with one topic from his quotes. Do not write a file.'}))
        await asyncio.wait_for(finished.wait(), 150)
        calls = [e for e in events if e['type'] == 'tool.call' and e.get('name') == 'browse']
        activities = [e for e in events if e['type'] == 'activity' and e.get('app') == 'Argus · browsing']
        failures = [e for e in events if e['type'] == 'error']
        assert calls and activities and not failures, {'calls': calls, 'errors': failures,
            'results': [e for e in events if e['type'] == 'tool.result']}
        await page.locator('.sight').filter(has_text='Argus · browsing').wait_for()
        for width, height in [(1920, 1080), (1280, 720)]:
            await page.set_viewport_size({'width': width, 'height': height})
            await page.wait_for_timeout(500)
            await page.screenshot(path=str(output / f'browse-{width}.png'))
        assert not errors, errors
        (output / 'acceptance.json').write_text(json.dumps({'real_model': True,
            'browse_calls': len(calls), 'activity_url': activities[-1]['url'],
            'console_errors': errors}, indent=2), encoding='utf-8')
        print('[PASS] real model uses browse on JavaScript page; LIVE UI shows browsing at both sizes')
        await browser.close()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


if __name__ == '__main__':
    asyncio.run(main())
