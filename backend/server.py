"""Loopback-only application server. Run: python3 -m backend.server."""
import argparse
import json
import mimetypes
import re
import sqlite3
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit
from .collector import collect
from .config import SERVICE_IDS, load_targets
from .repository import DomainError, Repository

DIST = Path(__file__).resolve().parents[1] / 'dist'

class Application:
    def __init__(self, repository, targets):
        self.repository = repository
        self.targets = targets
        self.collection_lock = threading.Lock()

    def collect_once(self):
        if not self.collection_lock.acquire(blocking=False):
            raise DomainError('collecting')
        try:
            self.repository.add_observations(collect(self.targets))
        finally:
            self.collection_lock.release()


def make_server(repository, port=8080, config=None):
    app = Application(repository, [])

    class Handler(BaseHTTPRequestHandler):
        server_version = 'ServiceWatch/1.0'

        def setup(self):
            super().setup()
            self.connection.settimeout(6)

        def log_message(self, fmt, *args):
            pass  # No request headers, URLs or personal text written to logs.

        def send_json(self, status, payload):
            body = json.dumps(payload, ensure_ascii=False, allow_nan=False).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.end_headers()
            self.wfile.write(body)

        def request_context(self):
            allowed = f'127.0.0.1:{self.server.server_port}'
            if self.headers.get('Host') != allowed:
                raise PermissionError('host')
            origin = self.headers.get('Origin')
            if origin and origin != f'http://{allowed}':
                raise PermissionError('origin')
            if self.headers.get('Sec-Fetch-Site') == 'cross-site':
                raise PermissionError('origin')
            parsed = urlsplit(self.path)
            query = parse_qs(parsed.query)
            try:
                hours = int(query.get('hours', ['24'])[0])
            except ValueError as exc:
                raise DomainError('invalid_request') from exc
            if hours not in (1,6,24):
                raise DomainError('invalid_request')
            return parsed.path, hours

        def do_GET(self):
            try:
                path, hours = self.request_context()
                if path == '/api/state':
                    return self.send_json(200, app.repository.state(hours))
                if path.startswith('/fixture/'):
                    service = path.rsplit('/',1)[-1]
                    if service not in SERVICE_IDS:
                        return self.send_json(404, {'error':'not_found'})
                    # Deliberate local fixture: one failing endpoint demonstrates real 503 detection.
                    return self.send_json(503 if service == 'checkout' else 200, {'fixture':True,'service':service})
                if path.startswith('/api/'):
                    return self.send_json(404, {'error':'not_found'})
                target = (DIST / unquote(path).lstrip('/')).resolve()
                if path == '/':
                    target = DIST / 'index.html'
                if not target.is_relative_to(DIST) or not target.is_file():
                    return self.send_json(404, {'error':'not_found'})
                content = target.read_bytes()
                self.send_response(200)
                self.send_header('Content-Type', (mimetypes.guess_type(target.name)[0] or 'application/octet-stream') + '; charset=utf-8')
                self.send_header('Content-Length', str(len(content)))
                self.send_header('X-Content-Type-Options','nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; object-src 'none'; frame-ancestors 'none'; base-uri 'self'")
                self.end_headers()
                self.wfile.write(content)
            except PermissionError:
                self.send_json(403, {'error':'forbidden'})
            except DomainError as exc:
                self.send_json(400, {'error':exc.code})
            except (OSError, sqlite3.Error):
                self.send_json(503, {'error':'unavailable'})

        def do_POST(self):
            try:
                path, hours = self.request_context()
                if self.headers.get('Content-Type','').split(';')[0].strip() != 'application/json':
                    return self.send_json(415, {'error':'invalid_request'})
                if self.headers.get('Transfer-Encoding'):
                    return self.send_json(400, {'error':'invalid_request'})
                try:
                    length = int(self.headers.get('Content-Length','-1'))
                except ValueError:
                    length = -1
                if not 0 < length <= 16384:
                    return self.send_json(413, {'error':'invalid_request'})
                try:
                    data = json.loads(self.rfile.read(length))
                except (ValueError, UnicodeError):
                    return self.send_json(400, {'error':'invalid_request'})
                if not isinstance(data, dict):
                    return self.send_json(400, {'error':'invalid_request'})
                if path == '/api/collect':
                    if data:
                        raise DomainError('invalid_request')  # No target URLs accepted from browser.
                    app.collect_once()
                elif path == '/api/incidents':
                    if set(data) - {'serviceId','title','severity','message'}:
                        raise DomainError('invalid_request')
                    app.repository.create_incident(data)
                elif re.fullmatch(r'/api/incidents/INC-[0-9]+/updates', path):
                    if set(data) - {'status','message'}:
                        raise DomainError('invalid_request')
                    app.repository.update_incident(path.split('/')[3], data)
                else:
                    return self.send_json(404, {'error':'not_found'})
                self.send_json(200, app.repository.state(hours))
            except PermissionError:
                self.send_json(403, {'error':'forbidden'})
            except DomainError as exc:
                status = 409 if exc.code in ('duplicate_incident','resolved','collecting') else 404 if exc.code == 'not_found' else 400
                self.send_json(status, {'error':exc.code})
            except (OSError, sqlite3.Error):
                self.send_json(503, {'error':'unavailable'})

    server = ThreadingHTTPServer(('127.0.0.1',port), Handler)
    server.daemon_threads = True
    try:
        app.targets = load_targets(config, server.server_port)
    except Exception:
        server.server_close()
        raise
    server.application = app
    return server


def main():
    parser = argparse.ArgumentParser(description='Local-only Service Watch API and bounded HTTP collector')
    parser.add_argument('--port',type=int,default=8080)
    parser.add_argument('--host',choices=['127.0.0.1'],default='127.0.0.1',help='Loopback only; accepted for local dev runners')
    parser.add_argument('--strictPort',action='store_true',help='Port binding is always strict; accepted for dev runners')
    parser.add_argument('--db',default='service-watch.sqlite3')
    parser.add_argument('--config',help='Trusted local JSON target configuration')
    args = parser.parse_args()
    server = make_server(Repository(args.db),args.port,args.config)
    print(f'Local backend: http://127.0.0.1:{server.server_port}/?mode=api',flush=True)
    print('No background collection. Click Collect in the UI or POST /api/collect. Ctrl+C stops.',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()

if __name__ == '__main__':
    main()
