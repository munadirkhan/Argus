"""Offline checks: python core/sensors/tests/test_terminal_log.py"""
import asyncio
import os
from pathlib import Path
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.sensors.terminal_log import TerminalLog, AnsiStream, classify, signature, strip_ansi


def check(label, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {label}")
    assert condition, label


async def main():
    for pattern in ['Error', 'Exception', 'Traceback', 'FATAL', 'panic:', 'npm ERR!',
                    'Uncaught', '✗', '×', '✘', 'FAILED', 'ERR_MODULE_NOT_FOUND', '[exit 1]', '[exit -9]']:
        check(f"error: {pattern}", classify(pattern) == 'err')
    for pattern in ['WARN', 'warning', 'deprecated']:
        check(f"warning: {pattern}", classify(pattern) == 'warn')
    for pattern in ['ready in 412 ms', 'compiled', '✓', '✔', 'listening on', 'Local:', '[exit 0]']:
        check(f"healthy: {pattern}", classify(pattern) == 'ok')
    check('headers and blanks', classify('$ node Error.js') == 'dim' and classify('  ') == 'dim')
    check('ordinary output', classify('hello') is None)
    for frame in ['    at foo (file.js:12:5)', '  File "x.py", line 3']:
        check('stack inherits error', classify(frame, True) == 'err' and classify(frame) is None)
    check('ANSI CSI + OSC', strip_ansi('\x1b[31mError\x1b[0m\x1b]0;title\x07') == 'Error')
    cleaner = AnsiStream()
    check('streaming split ANSI', ''.join(cleaner.feed(s) for s in ['\x1b[3', '1mError\x1b', '[0m']) == 'Error')
    check('signature keeps file:line', signature('[2026-10-16T12:30:00Z] Error x.js:12:5 0xBEEF 42ms') == '[] Error x.js:12:5')
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / 'terminal.log'
        path.write_text('$ node app.js\nold\nError: old\n', encoding='utf-8')
        sensor = TerminalLog([path])
        check('start at end', await sensor.poll() == [])
        check('initial context', '!! Error: old' in sensor.context() and 'Log: ' in sensor.context())

        def append(data):
            with path.open('ab') as f:
                f.write(data if isinstance(data, bytes) else data.encode())

        append('ready in 1 ms\n\x1b[31mTypeError: x.js:12:5\x1b[0m\n    at foo (x.js:12:5)\n')
        event = (await sensor.poll())[0]
        check('tail event and title', event['title'] == 'node app.js' and event['focus'])
        check('strip ANSI, stack tone', event['lines'][-2]['text'] == 'TypeError: x.js:12:5' and event['lines'][-1]['tone'] == 'err')
        check('new error alerts once', sensor.alert(event) and not sensor.alert(event))
        append('    at next (y.js:3:1)\n[exit 1]\n')
        check('split stack/exit is not a new crash', not sensor.alert((await sensor.poll())[0]))
        append('TypeError: x.js:12:5\n')
        check('dedupe repeated error', not sensor.alert((await sensor.poll())[0]))
        append('ordinary\n')
        event = (await sensor.poll())[0]
        check('old errors do not focus or alert', not event['focus'] and not sensor.alert(event))
        append('compiled\nTypeError: x.js:12:5\n')
        check('healthy line rearms same crash', sensor.alert((await sensor.poll())[0]))
        append(b'part \xe2')
        check('partial line waits', await sensor.poll() == [])
        append(b'\x9c\x93\n')
        check('UTF-8 split preserved', (await sensor.poll())[0]['lines'][-1]['text'] == 'part ✓')
        path.write_text('new\n', encoding='utf-8')
        check('truncation starts at zero', (await sensor.poll())[0]['lines'][-1]['text'] == 'new')
        replacement = Path(tmp) / 'replacement'
        replacement.write_text('rotated longer than old\n', encoding='utf-8')
        os.replace(replacement, path)
        check('larger rotation detected', (await sensor.poll())[0]['lines'][-1]['text'] == 'rotated longer than old')
        path.write_text('same inode truncate and regrow to a larger length\n', encoding='utf-8')
        check('truncate/regrow detected', (await sensor.poll())[0]['lines'][-1]['text'].startswith('same inode'))
        append('\n'.join('x' * 200 for _ in range(100)) + '\n')
        event = (await sensor.poll())[0]
        check('bounded event + context', len(event['lines']) == 12 and len(sensor.context()) <= 1500)
        check('idle emits nothing', await sensor.poll() == [])
        for i in range(25):
            append(f'Error: unique {i}\n')
            sensor.alert((await sensor.poll())[0])
        check('only last 20 signatures retained', len(sensor.tails[path].seen) == 20)
        path.unlink()
        check('missing file tolerated', await sensor.poll() == [])
        missing = Path(tmp) / 'missing.log'
        other = TerminalLog([missing])
        check('not-yet-created file', await other.poll() == [])
        missing.write_text('old history\n', encoding='utf-8')
        check('late file also starts at end', await other.poll() == [])
        env = {**os.environ, 'ARGUS_WATCH_ROOT': tmp, 'PYTHONIOENCODING': 'utf-8'}
        for code in (0, 7):
            child = "import sys; sys.stdout.write('\\x1b[31mhello\\x1b[0m'); sys.stdout.flush(); sys.stderr.write('stderr\\n'); sys.exit(%d)" % code
            result = await asyncio.to_thread(subprocess.run,
                [sys.executable, '-m', 'core.sensors.terminal_log', 'run', '--', sys.executable, '-c', child],
                cwd=Path(__file__).resolve().parents[3], env=env, capture_output=True)
            log = (Path(tmp) / '.argus/terminal.log').read_text(encoding='utf-8')
            check(f'wrapper exit {code}', result.returncode == code)
            check('console unchanged, stderr included', b'\x1b[31mhello\x1b[0mstderr' in result.stdout)
            check('log markers and clean content', log.startswith('$ ') and f'[exit {code}]' in log and '\x1b' not in log and 'hellostderr' in log)
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    asyncio.run(main())
