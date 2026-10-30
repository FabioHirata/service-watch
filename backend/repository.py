"""Transactional persistence and authoritative window aggregation in SQLite."""
import sqlite3
import time
from contextlib import contextmanager
from .config import SERVICE_IDS

STATUSES = ('investigating', 'identified', 'monitoring', 'resolved')
SERVICES = [{'id': k, 'name': k, 'group': 'application' if i < 2 else 'infrastructure', 'icon': ['↗','▣','≋','▤'][i]} for i, k in enumerate(SERVICE_IDS)]

class DomainError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def now_ms():
    return int(time.time()*1000)


class Repository:
    def __init__(self, path):
        self.path = str(path)
        with self.connection() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS observations (
              id INTEGER PRIMARY KEY, service_id TEXT NOT NULL, at INTEGER NOT NULL,
              ok INTEGER NOT NULL CHECK(ok IN (0,1)), latency REAL NOT NULL,
              status_code INTEGER, error TEXT);
            CREATE INDEX IF NOT EXISTS observations_window ON observations(service_id, at);
            CREATE TABLE IF NOT EXISTS incidents (
              id INTEGER PRIMARY KEY AUTOINCREMENT, service_id TEXT NOT NULL, title TEXT NOT NULL,
              severity TEXT NOT NULL, status TEXT NOT NULL, created_at INTEGER NOT NULL);
            CREATE UNIQUE INDEX IF NOT EXISTS one_active_incident ON incidents(service_id) WHERE status != 'resolved';
            CREATE TABLE IF NOT EXISTS updates (
              id INTEGER PRIMARY KEY, incident_id INTEGER NOT NULL REFERENCES incidents(id),
              at INTEGER NOT NULL, status TEXT NOT NULL, message TEXT NOT NULL);
            ''')

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:
                yield db
        finally:
            db.close()

    def add_observations(self, rows):
        with self.connection() as db:
            db.executemany('INSERT INTO observations(service_id,at,ok,latency,status_code,error) VALUES(?,?,?,?,?,?)',
                [(r['serviceId'],r['at'],int(r['ok']),r['latency'],r.get('statusCode'),r.get('error')) for r in rows])
            # Bounded 30-day retention; incident history is not removed.
            db.execute('DELETE FROM observations WHERE at < ?', (now_ms()-30*86400000,))

    def create_incident(self, data, at=None):
        if not isinstance(data, dict):
            raise DomainError('invalid_request')
        if data.get('serviceId') not in SERVICE_IDS:
            raise DomainError('invalid_service')
        if data.get('severity') not in ('degraded', 'outage'):
            raise DomainError('invalid_severity')
        title = data.get('title')
        message = data.get('message')
        if not isinstance(title, str) or not 5 <= len(title.strip()) <= 100:
            raise DomainError('invalid_title')
        if not isinstance(message, str) or not 10 <= len(message.strip()) <= 600:
            raise DomainError('invalid_message')
        at = now_ms() if at is None else at
        try:
            with self.connection() as db:
                cursor = db.execute("INSERT INTO incidents(service_id,title,severity,status,created_at) VALUES(?,?,?,'investigating',?)", (data['serviceId'],title.strip(),data['severity'],at))
                incident_id = cursor.lastrowid
                db.execute("INSERT INTO updates(incident_id,at,status,message) VALUES(?,?,'investigating',?)", (incident_id,at,message.strip()))
            return f'INC-{incident_id}'
        except sqlite3.IntegrityError as exc:
            raise DomainError('duplicate_incident') from exc

    def update_incident(self, identifier, data, at=None):
        if not isinstance(data, dict):
            raise DomainError('invalid_request')
        if data.get('status') not in STATUSES:
            raise DomainError('invalid_status')
        message = data.get('message')
        if not isinstance(message, str) or not 10 <= len(message.strip()) <= 600:
            raise DomainError('invalid_message')
        digits = identifier[4:] if isinstance(identifier, str) and identifier.startswith('INC-') else ''
        if not digits or len(digits) > 19 or not digits.isascii() or not digits.isdigit():
            raise DomainError('not_found')
        numeric_id = int(digits)
        if not 1 <= numeric_id <= 9223372036854775807:
            raise DomainError('not_found')
        with self.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM incidents WHERE id=?', (numeric_id,)).fetchone()
            if not row:
                raise DomainError('not_found')
            if row['status'] == 'resolved':
                raise DomainError('resolved')
            previous = db.execute('SELECT MAX(at) FROM updates WHERE incident_id=?', (row['id'],)).fetchone()[0]
            at = now_ms() if at is None else at
            if at < previous:
                raise DomainError('invalid_request')
            db.execute('UPDATE incidents SET status=? WHERE id=?', (data['status'],row['id']))
            db.execute('INSERT INTO updates(incident_id,at,status,message) VALUES(?,?,?,?)', (row['id'],at,data['status'],message.strip()))

    def state(self, hours=24, at=None):
        if hours not in (1,6,24):
            raise DomainError('invalid_request')
        at = now_ms() if at is None else at
        start = at-hours*3600000
        result = {'version':1,'mode':'api','now':at,'hours':hours,'services':SERVICES,'observations':[],'incidents':[],'metrics':{}}
        with self.connection() as db:
            db.execute('BEGIN')  # One consistent read snapshot for observations, totals and history.
            for service in SERVICE_IDS:
                row = db.execute('SELECT COUNT(*) AS n,SUM(ok) AS successes,AVG(CASE WHEN ok=1 THEN latency END) AS latency FROM observations WHERE service_id=? AND at>? AND at<=?', (service,start,at)).fetchone()
                result['metrics'][service] = {'samples':row['n'],'uptime':row['successes']/row['n']*100 if row['n'] else None,'latency':round(row['latency']) if row['latency'] is not None else None}
                recent = db.execute('SELECT * FROM observations WHERE service_id=? AND at>? AND at<=? ORDER BY at DESC,id DESC LIMIT 288', (service,start,at)).fetchall()
                result['observations'].extend({'serviceId':r['service_id'],'at':r['at'],'ok':bool(r['ok']),'latency':r['latency'],'statusCode':r['status_code'],'error':r['error']} for r in reversed(recent))
            for row in db.execute('SELECT * FROM incidents ORDER BY id DESC'):
                updates = [{'at':r['at'],'status':r['status'],'message':r['message']} for r in db.execute('SELECT * FROM updates WHERE incident_id=? ORDER BY id', (row['id'],))]
                result['incidents'].append({'id':f"INC-{row['id']}",'serviceId':row['service_id'],'title':row['title'],'severity':row['severity'],'status':row['status'],'createdAt':row['created_at'],'updates':updates})
        return result
