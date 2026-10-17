"""Browser regression tests with an isolated contract fixture (no model calls).

Run Vite on 5173, then: python web/tests/test_ui.py
Requires the acceptance-only Playwright runtime and Chromium.
"""
import asyncio
import argparse
import json
from pathlib import Path
import tempfile
import time


async def verify(browser, width, height, evidence):
    context = await browser.new_context(viewport={'width': width, 'height': height}, accept_downloads=True)
    page = await context.new_page()
    errors, messages, sockets = [], [], []
    page.on('pageerror', lambda error: errors.append(str(error)))
    page.on('console', lambda msg: errors.append(msg.text) if msg.type == 'error' else None)
    await page.route('**/health', lambda route: route.fulfill(json={
        'sensors': ['terminal', 'browser_tab'], 'budget_usd': 10, 'models': {}}))
    async def socket(route):
        sockets.append(route)
        route.on_message(lambda raw: messages.append(json.loads(raw)))
    await page.route_web_socket('**/ws', socket)
    await page.goto('http://localhost:5173/')
    await page.locator('.sense').filter(has_text='TERMINAL').wait_for()
    seq = 0
    def send(event):
        nonlocal seq
        seq += 1
        raw = json.dumps({'v': 1, 'seq': seq, 'ts': time.time(), **event})
        sockets[-1].send(raw)
        return raw
    send({'type': 'session.state', 'cwd': 'C:/ui-test', 'runtime': 'local', 'status': 'connected', 'label': 'contract fixture'})
    send({'type': 'fs.tree', 'root': 'C:/ui-test', 'nodes': []})
    await page.keyboard.press('Shift+R')
    await page.wait_for_function("document.querySelector('.record-toggle').getAttribute('aria-pressed') === 'true'")
    lines = [{'text': '$ node dev.js', 'tone': 'dim'}, {'text': 'TypeError: missing data in watchlist.js:24', 'tone': 'err'}]
    event = {'type': 'activity', 'source': 'terminal', 'app': 'Terminal', 'title': 'node dev.js', 'lines': lines, 'focus': True}
    send(event)
    await page.locator('.terminal-output .err').wait_for()
    await page.evaluate("window.oldError = document.querySelector('.terminal-output .err')")
    await page.wait_for_timeout(500)
    send({**event, 'lines': lines + [{'text': 'long output ' * 90}, {'text': 'newest-line'}], 'focus': False})
    await page.get_by_text('newest-line', exact=True).wait_for()
    checks = await page.evaluate('''() => {
      const terminal = document.querySelector('.terminal-output');
      const senses = document.querySelector('.senses');
      const oracles = document.querySelector('.oracles');
      return {
        stable: window.oldError === document.querySelector('.terminal-output .err'),
        scrolled: terminal.scrollHeight - terminal.scrollTop - terminal.clientHeight < 2,
        visible: document.querySelector('.sight').getBoundingClientRect().width > 0,
        fits: document.documentElement.scrollWidth <= innerWidth,
        separated: oracles.getBoundingClientRect().bottom <= senses.getBoundingClientRect().top,
      };
    }''')
    assert all(checks.values()), checks
    # Observe the pulse at ingestion, independently of slow WebGL frame checks.
    await page.wait_for_function("document.querySelectorAll('.sense.lit').length === 0")
    await page.evaluate("window.sawPulse = false; window.pulseObserver = new MutationObserver(() => { if ([...document.querySelectorAll('.sense.lit')].some(e => e.textContent.includes('TERMINAL'))) window.sawPulse = true; }); window.pulseObserver.observe(document.querySelector('.senses'), {subtree: true, attributes: true})")
    send({**event, 'lines': [{'text': 'pulse-check'}]})
    await page.wait_for_function('window.sawPulse')
    await page.evaluate('window.pulseObserver.disconnect()')
    await page.wait_for_timeout(2300)
    assert await page.locator('.sense.lit').count() == 0
    print(f'[PASS] {width}×{height}: visible terminal, stable error node, burst scrolling, sensor pulse', flush=True)

    observation = {'type': 'watcher.observation', 'id': 'obs_test1', 'confidence': .9,
        'observation': 'The test fixture crashed.', 'suggestion': 'Want me to fix it?', 'dismissible': True}
    send(observation)
    await page.locator('.btn-accept').wait_for()
    await page.keyboard.press('Enter')
    await page.wait_for_timeout(100)
    assert messages[-1] == {'type': 'user.accept', 'id': 'obs_test1'}
    await page.keyboard.press('/')
    assert await page.locator('#argus-composer').evaluate('(e) => e === document.activeElement')
    await page.keyboard.type('path/to/file')
    send({**observation, 'id': 'obs_test2'})
    await page.locator('.btn-dismiss').wait_for()
    await page.keyboard.press('Escape')
    assert await page.locator('.btn-dismiss').is_visible(), 'typing must not trigger global shortcuts'
    assert await page.locator('#argus-composer').input_value() == 'path/to/file'
    await page.locator('#argus-composer').evaluate('(e) => e.blur()')
    await page.keyboard.press('Escape')
    await page.wait_for_timeout(100)
    assert messages[-1] == {'type': 'user.dismiss', 'id': 'obs_test2'}
    future = send({'type': 'future.event', 'unknown_payload': {'verbatim': 'kept'}, 'ts': 1234567890.125})
    # Wait for a following rendered frame: fixed sleeps race the websocket on CI.
    send({**event, 'lines': [{'text': 'recorder-synchronized'}]})
    await page.get_by_text('recorder-synchronized', exact=True).wait_for()
    async with page.expect_download() as download:
        await page.keyboard.press('Shift+R')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'recording.jsonl'
        item = await download.value
        assert item.suggested_filename == 'argus-session.jsonl'
        await item.save_as(path)
        raw = path.read_text(encoding='utf-8').splitlines()
        assert future in raw
        assert any(json.loads(row)['type'] == 'fs.tree' for row in raw)
        assert all('ts' in json.loads(row) for row in raw)
    print('[PASS] keyboard shortcuts protect typing; raw recorder preserves timestamps and unknown fields', flush=True)
    await page.keyboard.press('Shift+R')
    async with page.expect_download():
        await page.get_by_role('button', name='SIMULATE', exact=True).click()
    await page.get_by_text('SIMULATED SESSION', exact=True).wait_for()
    assert await page.locator('.simpill').is_visible()
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    assert await page.locator('.record-toggle').count() == 0
    assert 'SIMULATED FEED · ILLUSTRATIVE' in await page.locator('.tape').inner_text()
    await page.get_by_role('button', name='CODE (RECORDED)', exact=True).click()
    await page.get_by_text('RECORDED LIVE RUN', exact=True).wait_for()
    await page.locator('.btn-accept').wait_for()
    if evidence:
        evidence.mkdir(parents=True, exist_ok=True)
        await page.screenshot(path=str(evidence / f'code-recorded-{width}.png'))
    await page.get_by_text('INSCRIBED', exact=True).wait_for()
    await page.locator('.terminal-output .ok').filter(has_text='[exit 0]').wait_for()
    assert await page.locator('.pill.rec').is_visible()
    assert await page.evaluate('document.documentElement.scrollWidth <= innerWidth')
    montage = await page.evaluate('''async () => {
      const { SCENARIOS } = await import('/src/sim/scenarios.ts');
      const { useArgus } = await import('/src/lib/store.ts');
      useArgus.getState().reset();
      SCENARIOS.montage.events.forEach(event => useArgus.getState().ingest(event));
      const state = useArgus.getState();
      return { plans: Object.keys(state.plans).length,
        expected: SCENARIOS.montage.events.filter(e => e.type === 'agent.plan').length,
        steps: Object.values(state.plans).flatMap(p => p.steps).every(s => s.status === 'done') };
    }''')
    assert montage['plans'] == montage['expected'] and montage['steps'], montage
    print('[PASS] real Code recording replays through clean exit; montage keeps independent plan/step identities', flush=True)
    assert not errors, errors
    await context.close()


async def main(evidence):
    from playwright.async_api import async_playwright
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        for size in [(1920, 1080), (1280, 720)]:
            await verify(browser, *size, evidence)
        page = await browser.new_page(viewport={'width': 1280, 'height': 720})
        await page.route('**/health', lambda route: route.fulfill(json={'sensors': []}))
        await page.route_web_socket('**/ws', lambda route: None)
        await page.goto('http://localhost:5173/?record=1')
        await page.wait_for_selector('.video-mode')
        assert await page.locator('#argus-composer').get_attribute('placeholder') == ''
        assert await page.locator('body').evaluate('(e) => getComputedStyle(e).cursor') == 'none'
        assert await page.locator('.state .word').inner_text() == 'WATCHING'
        print('[PASS] video mode: cursor hidden, no placeholder, eyes start idle')
        await browser.close()
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--evidence', type=Path)
    asyncio.run(main(parser.parse_args().evidence))
