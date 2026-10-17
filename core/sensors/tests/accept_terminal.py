"""Real crash acceptance, including UI screenshots and raw websocket recording.

Start core + web against a seeded workspace first, then:
  python core/sensors/tests/accept_terminal.py --workspace PATH --output web/.local
With a configured live model, add --proceed to click the offer and verify the fix.
Requires Playwright/Chromium (only this acceptance harness, not the sensor).
"""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[3]


async def main(args):
    import httpx
    import websockets
    from playwright.async_api import async_playwright
    out = args.output.resolve()
    out.mkdir(parents=True, exist_ok=True)
    workspace = args.workspace.resolve()
    errors = []
    events = []
    crash_seen = asyncio.Event()
    async with httpx.AsyncClient() as client:
        health = (await client.get('http://localhost:7600/health')).json()
    assert 'terminal' in health['sensors'], health
    assert Path(health['root']).resolve() == workspace, health['root']
    async with websockets.connect('ws://localhost:7600/ws') as ws, async_playwright() as pw:
        async def record():
            with (out / 'argus-session.jsonl').open('w', encoding='utf-8') as log:
                async for raw in ws:
                    event = json.loads(raw)
                    events.append(event)
                    log.write(raw + '\n')
                    log.flush()
                    if event.get('source') == 'terminal' and any('TypeError' in l['text'] for l in event.get('lines', [])):
                        crash_seen.set()

        recording = asyncio.create_task(record())
        browser = await pw.chromium.launch()
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        page.on('pageerror', lambda e: errors.append(str(e)))
        await page.goto('http://localhost:5173/')
        await page.get_by_role('button', name='LIVE', exact=True).wait_for()
        await asyncio.sleep(1)
        recorder = page.locator('.record-toggle')
        if await recorder.count():
            await page.keyboard.press('Shift+R')

        async def run_fixture():
            return await asyncio.create_subprocess_exec(sys.executable, '-m', 'core.sensors.terminal_log',
                'run', '--', 'node', str(workspace / 'dev.js'), cwd=ROOT,
                env={**os.environ, 'ARGUS_WATCH_ROOT': str(workspace)},
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.STDOUT)

        started = time.monotonic()
        child = await run_fixture()
        await asyncio.wait_for(crash_seen.wait(), 10)
        latency = time.monotonic() - started - 1.5
        await child.communicate()
        assert child.returncode != 0
        await page.locator('.term .err').filter(has_text='TypeError').wait_for()
        await page.screenshot(path=str(out / 'terminal-crash-1920.png'))
        print(f'PASS: real crash displayed, approximately {latency:.3f}s from crash to websocket', flush=True)
        if args.proceed:
            button = page.locator('.btn-accept')
            await button.wait_for(timeout=60_000)
            await page.screenshot(path=str(out / 'terminal-prophecy-1920.png'))
            await button.click()
            await page.get_by_text('INSCRIBED', exact=True).first.wait_for(timeout=180_000)
            await page.screenshot(path=str(out / 'terminal-inscribed-1920.png'))
            child = await run_fixture()
            stdout, _ = await child.communicate()
            assert child.returncode == 0, stdout.decode(errors='replace')
            await page.locator('.term .ok').filter(has_text='[exit 0]').wait_for()
            await page.screenshot(path=str(out / 'terminal-fixed-1920.png'))
            print('PASS: Proceed wrote code and the real app now exits 0', flush=True)
        if await recorder.count():
            async with page.expect_download() as download_info:
                await page.keyboard.press('Shift+R')
            await (await download_info.value).save_as(out / 'ui-recording.jsonl')
        assert not errors, errors
        (out / 'acceptance.json').write_text(json.dumps({'sensors': health['sensors'],
            'latency_seconds_approx': round(latency, 3), 'proceed_verified': args.proceed,
            'console_errors': errors}, indent=2), encoding='utf-8')
        await browser.close()
        recording.cancel()
        try:
            await recording
        except asyncio.CancelledError:
            pass


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--proceed', action='store_true')
    asyncio.run(main(parser.parse_args()))
