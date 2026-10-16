"""Exercise the unpacked extension in real Chromium, using a disposable profile.

Core must run on 7600; web on 5173. No model calls are made by this test.
"""
import asyncio
import json
import os
from pathlib import Path
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]


async def main():
    from playwright.async_api import async_playwright
    import websockets
    with tempfile.TemporaryDirectory() as profile:
        async with async_playwright() as pw, websockets.connect('ws://localhost:7600/ws') as ws:
            events = []
            async def record():
                async for raw in ws:
                    e = json.loads(raw)
                    if e.get('source') == 'browser':
                        events.append(e)
            task = asyncio.create_task(record())
            context = await pw.chromium.launch_persistent_context(profile, channel=os.environ.get('ARGUS_TEST_BROWSER', 'chromium'), headless=True,
                ignore_default_args=['--disable-extensions'],
                args=[f'--disable-extensions-except={ROOT / "extension"}', f'--load-extension={ROOT / "extension"}'])
            worker = context.service_workers[0] if context.service_workers else await context.wait_for_event('serviceworker')
            extension_id = worker.url.split('/')[2]
            popup = await context.new_page()
            await popup.goto(f'chrome-extension://{extension_id}/popup.html')
            assert not await popup.locator('#enabled').is_checked()
            page = await context.new_page()
            await page.goto('https://example.com')
            await page.bring_to_front()
            await asyncio.sleep(3.7)
            baseline = len(events)
            print('[PASS] extension starts off', flush=True)
            await popup.bring_to_front()
            await popup.locator('#enabled').check()
            await page.bring_to_front()
            started = time.monotonic()
            for _ in range(60):
                if len(events) > baseline:
                    break
                await asyncio.sleep(.1)
            assert len(events) == baseline + 1, await worker.evaluate('chrome.storage.local.get()')
            assert events[-1]['title'] == 'Example Domain'
            elapsed = time.monotonic() - started
            assert elapsed < 4.5, elapsed
            print(f'[PASS] real tab → core browser activity in {elapsed:.2f}s', flush=True)
            await asyncio.sleep(3.2)
            assert len(events) == baseline + 1
            print('[PASS] unchanged URL is sent once', flush=True)

            # Validate visible text and selection extraction on a rendered fixture.
            await page.route('https://privacy.example/**', lambda r: r.fulfill(body='''
              <title>Privacy fixture</title><p id="public">Visible public text</p>
              <input value="INPUT_SECRET"><textarea>TEXTAREA_SECRET</textarea>
              <select><option>OPTION_SECRET</option></select>
              <div contenteditable>EDITABLE_SECRET</div><div style="display:none">HIDDEN_SECRET</div>
            ''', content_type='text/html'))
            await page.goto('https://privacy.example/')
            await page.evaluate("""() => {const s=getSelection(); const r=document.createRange();
                r.selectNodeContents(document.querySelector('#public')); s.removeAllRanges(); s.addRange(r);}""")
            for _ in range(55):
                if any(e['title'] == 'Privacy fixture' for e in events):
                    break
                await asyncio.sleep(.1)
            fixture = next(e for e in events if e['title'] == 'Privacy fixture')
            assert 'SECRET' not in json.dumps(fixture)
            assert fixture['lines'][0] == {'text': 'Visible public text', 'tone': 'hl'}
            print('[PASS] fields, editable and hidden text excluded; selection retained', flush=True)

            await popup.bring_to_front()
            await popup.locator('#denylist').fill('privacy.example')
            await popup.get_by_role('button', name='SAVE EXCLUSIONS').click()
            before = len(events)
            await page.bring_to_front()
            await page.goto('https://privacy.example/denied')
            await asyncio.sleep(3.7)
            assert len(events) == before
            print('[PASS] edited denylist takes effect', flush=True)

            await page.goto('https://example.com/?argus-extension-acceptance')
            await asyncio.sleep(3.8)
            ui = await pw.chromium.launch()
            screen = await ui.new_page(viewport={'width': 1920, 'height': 1080})
            await screen.goto('http://127.0.0.1:5173/')
            await screen.locator('.browser .btitle').filter(has_text='Example Domain').wait_for()
            out = ROOT / 'web/.local/browser'
            out.mkdir(parents=True, exist_ok=True)
            await screen.screenshot(path=str(out / 'browser-tab-1920.png'))
            await ui.close()
            await popup.bring_to_front()
            await popup.locator('#enabled').uncheck()
            assert await popup.locator('#status').inner_text() == 'off'
            await page.bring_to_front()
            await page.goto('https://example.com/?argus-disabled')
            before = len(events)
            await asyncio.sleep(3.7)
            assert len(events) == before
            print('[PASS] off toggle stops sharing', flush=True)
            await context.close()
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    asyncio.run(main())
