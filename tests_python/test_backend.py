import http.client
import json
import socket
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from backend.collector import probe
from backend.config import parse_target, load_targets
from backend.repository import DomainError, Repository, now_ms
from backend.server import make_server


class ConfigTests(unittest.TestCase):
    def test_exact_allowlist_no_dns_credentials_metadata_or_unsafe_addresses(self):
        valid = parse_target('api','http://127.0.0.1:8080/health',['http://127.0.0.1:8080'])
        self.assertEqual(valid.path,'/health')
        self.assertEqual(parse_target('api','http://[::1]:8080/',['http://[::1]:8080']).host,'::1')
        for url in ['http://localhost:8080/', 'http://169.254.169.254/latest/meta-data', 'http://10.0.0.1/', 'http://0.0.0.0/', 'http://127.0.0.2/', 'http://224.0.0.1/', 'file:///etc/passwd', 'http://user:secret@127.0.0.1:8080/', 'http://127.0.0.1:8080/#x', 'http://127.0.0.1:8080/\r\nInjected:x']:
            with self.subTest(url=url), self.assertRaises(ValueError):
                parse_target('api',url,['http://127.0.0.1:8080'])
        with self.assertRaises(ValueError):
            parse_target('api','http://127.0.0.1:8081/',['http://127.0.0.1:8080'])
        for timeout in [0, 8, True, '2']:
            with self.assertRaises(ValueError):
                parse_target('api','http://127.0.0.1:8080/',['http://127.0.0.1:8080'],timeout)

    def test_local_config_and_explicit_public_ip(self):
        targets = load_targets(port=8099)
        self.assertEqual(len(targets),4)
        self.assertTrue(all(t.host=='127.0.0.1' and t.port==8099 for t in targets))
        self.assertEqual(parse_target('api','https://8.8.8.8/',['https://8.8.8.8:443']).host,'8.8.8.8')  # no request made


class CollectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        class FakeHandler(BaseHTTPRequestHandler):
            def log_message(self,*args): pass
            def do_GET(self):
                if self.path == '/slow':
                    time.sleep(.4)
                    return
                if self.path == '/drip':
                    try:
                        for byte in b'HTTP/1.1 200 OK\r\n':
                            self.connection.send(bytes([byte])); time.sleep(.04)
                    except OSError:
                        pass
                    return
                if self.path == '/large':
                    self.connection.sendall(b'HTTP/1.1 200 OK\r\nX-Long: '+b'x'*17000)
                    return
                self.send_response(503 if self.path=='/failure' else 302 if self.path=='/redirect' else 200)
                if self.path == '/redirect':
                    self.send_header('Location','http://169.254.169.254/latest/meta-data')
                self.end_headers()
        cls.server=ThreadingHTTPServer(('127.0.0.1',0),FakeHandler)
        cls.server.daemon_threads=True
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.origin=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def target(self,path,timeout=.2):
        return parse_target('api',self.origin+path,[self.origin],timeout)

    def test_success_failure_and_redirect_without_following(self):
        result=probe(self.target('/ok'))
        self.assertTrue(result['ok']);self.assertEqual(result['statusCode'],200)
        self.assertGreaterEqual(result['latency'],0)
        for path,status in [('/failure',503),('/redirect',302)]:
            result=probe(self.target(path));self.assertFalse(result['ok']);self.assertEqual(result['statusCode'],status);self.assertEqual(result['error'],'http_error')

    def test_absolute_timeout_including_slow_drip_and_bounded_headers(self):
        for path in ['/slow','/drip']:
            start=time.monotonic();result=probe(self.target(path,.1))
            self.assertEqual(result['error'],'timeout');self.assertLess(time.monotonic()-start,.6)
        self.assertEqual(probe(self.target('/large'))['error'],'network_error')

    def test_connection_refusal_becomes_observation(self):
        with socket.socket() as s:
            s.bind(('127.0.0.1',0));port=s.getsockname()[1]
        origin=f'http://127.0.0.1:{port}'
        self.assertEqual(probe(parse_target('api',origin+'/',[origin],.1))['error'],'network_error')


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'db.sqlite3';self.repo=Repository(self.path)
        self.data={'serviceId':'api','title':'Test incident','severity':'outage','message':'Investigating a simulated failure.'}
    def tearDown(self): self.tmp.cleanup()

    def test_sql_metrics_exact_window_and_no_data(self):
        at=now_ms();rows=[{'serviceId':'api','at':at-3600000,'ok':False,'latency':999}, {'serviceId':'api','at':at-100,'ok':True,'latency':100}, {'serviceId':'api','at':at,'ok':False,'latency':900}, {'serviceId':'api','at':at+1,'ok':True,'latency':200}]
        self.repo.add_observations(rows);state=self.repo.state(1,at)
        self.assertEqual(state['metrics']['api'],{'samples':2,'uptime':50.0,'latency':100})
        self.assertIsNone(state['metrics']['queue']['uptime'])
        self.assertEqual(len(state['observations']),2)

    def test_metrics_include_more_samples_than_chart_preview(self):
        at=now_ms();self.repo.add_observations([{'serviceId':'api','at':at-i,'ok':i!=299,'latency':10} for i in range(300)])
        state=self.repo.state(1,at);self.assertEqual(len(state['observations']),288);self.assertEqual(state['metrics']['api']['samples'],300);self.assertAlmostEqual(state['metrics']['api']['uptime'],299/300*100)

    def test_incident_lifecycle_persists_and_resolved_is_immutable(self):
        identifier=self.repo.create_incident(self.data,100)
        self.repo.update_incident(identifier,{'status':'monitoring','message':'Monitoring recovery after the fix.'},101)
        self.repo.update_incident(identifier,{'status':'resolved','message':'Recovery confirmed by the operator.'},102)
        fresh=Repository(self.path).state()['incidents'][0]
        self.assertEqual(fresh['status'],'resolved');self.assertEqual(len(fresh['updates']),3)
        with self.assertRaisesRegex(DomainError,'resolved'):
            self.repo.update_incident(identifier,{'status':'investigating','message':'Trying to reopen resolved history.'},103)
        self.assertNotEqual(self.repo.create_incident(self.data),identifier)

    def test_validation_and_atomic_duplicate_protection(self):
        for change,code in [({'title':'bad'},'invalid_title'),({'serviceId':'bad'},'invalid_service'),({'severity':'bad'},'invalid_severity'),({'message':'short'},'invalid_message')]:
            with self.assertRaisesRegex(DomainError,code):self.repo.create_incident(self.data|change)
        def create():
            try:return self.repo.create_incident(self.data)
            except DomainError as exc:return exc.code
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:create(),range(2)))
        self.assertEqual(results.count('duplicate_incident'),1)
        self.assertEqual(len(self.repo.state()['incidents']),1)
        with self.assertRaisesRegex(DomainError,'invalid_status'):
            self.repo.update_incident('INC-1',{'status':'bad','message':'A valid detailed status message.'})
        with self.assertRaisesRegex(DomainError,'not_found'):
            self.repo.update_incident('INC-999',{'status':'resolved','message':'A valid detailed status message.'})


class APITests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.repo=Repository(Path(self.tmp.name)/'api.sqlite3')
        self.server=make_server(self.repo,0);self.port=self.server.server_port
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.tmp.cleanup()
    def request(self,method,path,data=None,headers=None):
        connection=http.client.HTTPConnection('127.0.0.1',self.port,timeout=4)
        body=json.dumps(data).encode() if data is not None else None
        request_headers={'Content-Type':'application/json'}| (headers or {})
        connection.request(method,path,body=body,headers=request_headers);response=connection.getresponse();raw=response.read();status=response.status;connection.close()
        return status,json.loads(raw)

    def test_real_local_collection_persistence_metrics_and_incident_api(self):
        status,state=self.request('GET','/api/state');self.assertEqual(status,200);self.assertEqual(state['observations'],[])
        status,state=self.request('POST','/api/collect?hours=1',{});self.assertEqual(status,200);self.assertEqual(len(state['observations']),4);self.assertEqual(state['hours'],1)
        self.assertEqual(state['metrics']['api']['uptime'],100);self.assertEqual(state['metrics']['checkout']['uptime'],0)
        data={'serviceId':'checkout','title':'Checkout unavailable','severity':'outage','message':'The local fixture returns HTTP 503.'}
        status,state=self.request('POST','/api/incidents',data);self.assertEqual(status,200);identifier=state['incidents'][0]['id']
        self.assertEqual(self.request('POST','/api/incidents',data)[0],409)
        status,state=self.request('POST',f'/api/incidents/{identifier}/updates',{'status':'resolved','message':'Manual response completed for this test.'});self.assertEqual(status,200);self.assertEqual(state['incidents'][0]['status'],'resolved')
        self.assertEqual(state['metrics']['checkout']['uptime'],0)  # Resolving never rewrites observations.
        self.assertEqual(len(Repository(self.repo.path).state()['observations']),4)

    def test_refuses_cross_origin_host_form_urls_and_bad_input(self):
        for headers in [{'Origin':'https://evil.example'},{'Host':'evil.example'},{'Sec-Fetch-Site':'cross-site'}]:
            self.assertEqual(self.request('POST','/api/collect',{},headers)[0],403)
        self.assertEqual(self.request('POST','/api/collect',{}, {'Content-Type':'text/plain'})[0],415)
        self.assertEqual(self.request('POST','/api/collect',{'url':'http://169.254.169.254/'})[0],400)
        self.assertEqual(self.request('GET','/api/state?hours=999')[0],400)
        self.assertEqual(self.request('POST','/api/incidents',[])[0],400)
        self.assertEqual(self.request('GET','/../backend/server.py')[0],404)
        self.assertEqual(self.request('GET','/api/missing')[0],404)

    def test_huge_incident_ids_return_json_not_server_exception(self):
        data={'status':'resolved','message':'A valid detailed status update.'}
        for suffix in ['0','9223372036854775808','9'*30,'9'*5000]:
            status,response=self.request('POST','/api/incidents/INC-'+suffix+'/updates',data)
            self.assertEqual(status,404);self.assertEqual(response,{'error':'not_found'})

    def test_no_implicit_collection_and_concurrent_collection_is_rejected(self):
        self.assertEqual(self.repo.state()['observations'],[])
        with self.server.application.collection_lock:
            status,data=self.request('POST','/api/collect',{})
        self.assertEqual(status,409);self.assertEqual(data['error'],'collecting')

if __name__=='__main__':unittest.main()
