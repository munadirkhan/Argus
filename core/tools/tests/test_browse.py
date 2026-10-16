"""Offline SSRF checks plus a real example.com read if Chromium is installed."""
import asyncio
import importlib.util
from pathlib import Path
import socket
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from core.tools.browse import Browse, INSTALL
from core.tools._browse_network import PublicProxy, parse_url, public_addresses


def check(name, condition):
    print(f"[{'PASS' if condition else 'FAIL'}] {name}", flush=True)
    assert condition, name


async def main():
    tool = Browse()
    loop = asyncio.get_running_loop()
    for url in [None, '', 123, 'ftp://example.com', 'file:///etc/passwd', 'http://localhost',
                'http://a.localhost.', 'http://user:pass@example.com', 'https://example.com:bad',
                'http://example.com\n', 'http://example.com\\@127.0.0.1']:
        result = await tool.run(url)
        check(f'reject URL {url!r}', not result.ok and tool.browser is None)

    for ip in ['127.0.0.1', '10.0.0.1', '172.16.0.1', '192.168.1.1', '169.254.169.254',
               '0.0.0.0', '100.64.0.1', '224.0.0.1', '::1', 'fc00::1', 'fe80::1', '::ffff:127.0.0.1']:
        async def resolve(*a, **k):
            return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 80))]
        with patch.object(loop, 'getaddrinfo', resolve):
            result = await tool.run('https://apparently-public.example')
        check(f'refuse DNS to {ip}', not result.ok and 'private' in result.summary)

    async def mixed(*a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', (ip, 80)) for ip in ['93.184.215.14', '10.0.0.1']]
    with patch.object(loop, 'getaddrinfo', mixed):
        check('mixed public/private DNS fails closed', not (await tool.run('https://example.com')).ok)
    async def public(*a, **k):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, '', ('93.184.215.14', 443))]
    with patch.object(loop, 'getaddrinfo', public):
        check('accept public DNS', await public_addresses('example.com', 443) == ['93.184.215.14'])
        check('bad tool arguments contained', not (await tool.run('https://example.com', links='yes')).ok)

    proxy = PublicProxy()
    endpoint = await proxy.start()
    port = parse_url(endpoint)[2]
    for request in [b'CONNECT 127.0.0.1:7600 HTTP/1.1\r\n\r\n',
                    b'GET http://169.254.169.254/latest/meta-data HTTP/1.1\r\n\r\n',
                    b'POST http://example.com/ HTTP/1.1\r\n\r\n']:
        reader, writer = await asyncio.open_connection('127.0.0.1', port)
        writer.write(request)
        await writer.drain()
        check('egress proxy rejects unsafe connection', b'403 Forbidden' in await reader.read(1024))
        writer.close()
        await writer.wait_closed()
    await proxy.close()

    if importlib.util.find_spec('playwright') is None:
        print('[SKIP] live example.com: Playwright not installed')
    else:
        from playwright.async_api import async_playwright
        async with async_playwright() as pw:
            installed = Path(pw.chromium.executable_path).exists()
        if not installed:
            print('[SKIP] live example.com: Chromium not installed')
        else:
            started = loop.time()
            result = await tool.run('https://example.com', find='Example', links=True)
            check('live example.com', result.ok and 'documentation' in result.detail and result.meta['activity']['title'] == 'Example Domain')
            check('bounded result and time', len(result.detail) <= 12000 and loop.time() - started < 25)
            check('activity for UI', result.meta['activity']['app'] == 'Argus · browsing' and result.meta['activity']['focus'])
            check('links returned', '](' in result.detail)
            first = tool.browser
            again = await tool.run('https://example.com')
            check('browser reused; context closed', again.ok and tool.browser is first and not first.contexts)
    await tool.close()
    print('ALL CHECKS PASSED')


if __name__ == '__main__':
    asyncio.run(main())
