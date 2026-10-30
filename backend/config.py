"""Configuration is trusted local input, never supplied through the HTTP API."""
from dataclasses import dataclass
import ipaddress
import json
from urllib.parse import urlsplit

SERVICE_IDS = ('api', 'checkout', 'queue', 'database')

@dataclass(frozen=True)
class Target:
    service_id: str
    url: str
    host: str
    port: int
    scheme: str
    path: str
    timeout: float = 2.0


def parse_target(service_id, url, allowed_origins, timeout=2.0):
    if service_id not in SERVICE_IDS or not isinstance(url, str):
        raise ValueError('Unknown service or invalid URL')
    if any(ord(c) <= 32 or ord(c) >= 127 for c in url):
        raise ValueError('URL must be ASCII without whitespace/control characters')
    parts = urlsplit(url)
    if parts.scheme not in ('http', 'https') or parts.username or parts.password or parts.fragment:
        raise ValueError('Only credential-free HTTP(S) URLs without fragments are allowed')
    try:
        address = ipaddress.ip_address(parts.hostname or '')
        port = parts.port or (443 if parts.scheme == 'https' else 80)
    except ValueError as exc:
        raise ValueError('Use an explicit IP literal; DNS names are intentionally unsupported') from exc
    # Never permit cloud metadata, LAN ranges, multicast, unspecified or reserved targets.
    if str(address) not in ('127.0.0.1', '::1') and not address.is_global:
        raise ValueError('Only exact loopback or globally routable IPs are accepted')
    if address.is_multicast or address.is_unspecified or (address.is_reserved and str(address) != '::1'):
        raise ValueError('Unsafe target address')
    if not 1 <= port <= 65535 or not isinstance(timeout, (float, int)) or isinstance(timeout, bool) or not .1 <= timeout <= 5:
        raise ValueError('Port or timeout outside permitted bounds (0.1–5 seconds)')
    host = str(address)
    origin = f'{parts.scheme}://{"[" + host + "]" if address.version == 6 else host}:{port}'
    if origin not in allowed_origins:
        raise ValueError('Target origin is not explicitly allowlisted')
    return Target(service_id, url, host, port, parts.scheme, (parts.path or '/') + ('?' + parts.query if parts.query else ''), float(timeout))


def load_targets(filename=None, port=8080):
    if filename is None:
        origin = f'http://127.0.0.1:{port}'
        return [parse_target(s, f'{origin}/fixture/{s}', [origin]) for s in SERVICE_IDS]
    with open(filename, encoding='utf-8') as stream:
        config = json.load(stream)
    if not isinstance(config, dict) or not isinstance(config.get('allowed_origins'), list) or not isinstance(config.get('services'), list):
        raise ValueError('Configuration needs allowed_origins and services arrays')
    services = config['services']
    if len(services) != 4 or {s.get('id') for s in services if isinstance(s, dict)} != set(SERVICE_IDS):
        raise ValueError('Configure exactly the four supported service IDs')
    return [parse_target(s['id'], s['url'], config['allowed_origins'], s.get('timeout', 2)) for s in services]
