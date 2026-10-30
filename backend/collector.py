"""Bounded real HTTP checks. No DNS resolution, proxy env, redirect or body download."""
import re
import socket
import ssl
import time
from concurrent.futures import ThreadPoolExecutor

_TLS_CONTEXT = ssl.create_default_context()


def probe(target):
    start = time.monotonic()
    deadline = start + target.timeout
    connection = None
    status = None
    error = None
    try:
        connection = socket.create_connection((target.host, target.port), timeout=target.timeout)
        if target.scheme == 'https':
            connection.settimeout(max(.001, deadline-time.monotonic()))
            connection = _TLS_CONTEXT.wrap_socket(connection, server_hostname=target.host)
        host = f'[{target.host}]' if ':' in target.host else target.host
        request = f'GET {target.path} HTTP/1.1\r\nHost: {host}:{target.port}\r\nUser-Agent: ServiceWatch-Local/1.0\r\nConnection: close\r\n\r\n'
        connection.settimeout(max(.001, deadline-time.monotonic()))
        connection.sendall(request.encode('ascii'))
        headers = bytearray()
        while b'\r\n\r\n' not in headers:
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                raise TimeoutError('deadline')
            connection.settimeout(remaining)
            chunk = connection.recv(min(1024, 16384-len(headers)))
            if not chunk:
                raise ValueError('Incomplete HTTP headers')
            headers.extend(chunk)
            if len(headers) >= 16384 and b'\r\n\r\n' not in headers:
                raise ValueError('HTTP headers too large')
        match = re.match(rb'HTTP/1\.[01] ([1-5][0-9]{2})(?: |\r\n)', headers)
        if not match:
            raise ValueError('Invalid HTTP response')
        status = int(match.group(1))
        if not 200 <= status < 300:
            error = 'http_error'  # 3xx is a failure: redirects are never followed.
    except (TimeoutError, socket.timeout):
        error = 'timeout'
    except (OSError, ValueError, ssl.SSLError):
        error = 'network_error'
    finally:
        if connection:
            connection.close()
    return {'serviceId': target.service_id, 'at': int(time.time()*1000), 'ok': error is None,
            'latency': round((time.monotonic()-start)*1000, 2), 'statusCode': status, 'error': error}


def collect(targets):
    with ThreadPoolExecutor(max_workers=min(4, len(targets))) as pool:
        return list(pool.map(probe, targets))
