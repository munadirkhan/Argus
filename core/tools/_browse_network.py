"""Public-only egress for Chromium. DNS answers are pinned at TCP connect time.

The browser talks through this loopback proxy; it never resolves target hosts
itself. Checking only Playwright routes would leave a DNS-rebinding race.
"""
import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


def parse_url(url):
    if not isinstance(url, str) or not url or any(ord(c) <= 32 for c in url) or '\\' in url:
        raise ValueError('browse requires an http(s) URL')
    parsed = urlsplit(url)
    if (parsed.scheme not in ('http', 'https') or not parsed.hostname or
            parsed.username is not None or parsed.password is not None):
        raise ValueError('browse requires an http(s) URL without credentials')
    host = parsed.hostname.rstrip('.').lower()
    port = parsed.port or (443 if parsed.scheme == 'https' else 80)
    if '%' in host or host == 'localhost' or host.endswith('.localhost'):
        raise ValueError('browse refuses local/private addresses')
    return parsed, host, port


async def public_addresses(host, port):
    answers = await asyncio.get_running_loop().getaddrinfo(host, port, type=socket.SOCK_STREAM)
    addresses = list(dict.fromkeys(answer[4][0] for answer in answers))
    if not addresses:
        raise ValueError('hostname has no addresses')
    for address in addresses:
        ip = ipaddress.ip_address(address)
        ip = getattr(ip, 'ipv4_mapped', None) or ip
        if not ip.is_global or ip.is_multicast or ip.is_reserved:
            raise ValueError('browse refuses local/private addresses')
    return addresses


async def validate_url(url):
    parsed, host, port = parse_url(url)
    await public_addresses(host, port)
    return parsed


class PublicProxy:
    def __init__(self):
        self.server = None
        self.tasks = set()

    async def start(self):
        self.server = await asyncio.start_server(self.handle, '127.0.0.1', 0, limit=16_384)
        return f'http://127.0.0.1:{self.server.sockets[0].getsockname()[1]}'

    async def close(self):
        if self.server:
            self.server.close()
            await self.server.wait_closed()
        tasks = list(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def handle(self, reader, writer):
        task = asyncio.current_task()
        self.tasks.add(task)
        upstream = None
        try:
            async with asyncio.timeout(25):
                raw = await reader.readuntil(b'\r\n\r\n')
                first, *headers = raw.decode('latin-1').split('\r\n')
                method, target, _ = first.split(' ', 2)
                if method == 'CONNECT':
                    parsed, host, port = parse_url('https://' + target)
                elif method in ('GET', 'HEAD'):
                    parsed, host, port = parse_url(target)
                else:
                    raise ValueError('read-only proxy')
                addresses = await public_addresses(host, port)
                # Connecting to this literal IP pins the vetted DNS answer.
                remote, upstream = await asyncio.open_connection(addresses[0], port)
                if method == 'CONNECT':
                    writer.write(b'HTTP/1.1 200 Connection Established\r\n\r\n')
                    await writer.drain()
                    async def pipe(src, dst):
                        while data := await src.read(65536):
                            dst.write(data)
                            await dst.drain()
                    a = asyncio.create_task(pipe(reader, upstream))
                    b = asyncio.create_task(pipe(remote, writer))
                    try:
                        await asyncio.wait([a, b], return_when=asyncio.FIRST_COMPLETED)
                    finally:
                        a.cancel()
                        b.cancel()
                        await asyncio.gather(a, b, return_exceptions=True)
                else:
                    safe = [h for h in headers if h and h.partition(':')[0].lower() not in
                            ('host', 'connection', 'proxy-connection', 'proxy-authorization', 'content-length', 'transfer-encoding')]
                    request_path = (parsed.path or '/') + ('?' + parsed.query if parsed.query else '')
                    request = f'{method} {request_path} HTTP/1.1\r\nHost: {parsed.netloc}\r\nConnection: close\r\n'
                    upstream.write((request + '\r\n'.join(safe) + '\r\n\r\n').encode('latin-1'))
                    await upstream.drain()
                    while data := await remote.read(65536):
                        writer.write(data)
                        await writer.drain()
        except (OSError, ValueError, TimeoutError, asyncio.IncompleteReadError, asyncio.LimitOverrunError):
            try:
                writer.write(b'HTTP/1.1 403 Forbidden\r\nConnection: close\r\nContent-Length: 0\r\n\r\n')
                await writer.drain()
            except OSError:
                pass
        finally:
            if upstream:
                upstream.close()
            writer.close()
            self.tasks.discard(task)
