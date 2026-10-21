import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

from ai import Settings, citation_warnings, complete, protect_key, validate_url
from core import Library
from server import TOKEN, create_server


class MockModel(BaseHTTPRequestHandler):
    received = None

    def do_POST(self):
        type(self).received = {'payload': json.loads(self.rfile.read(int(self.headers['Content-Length']))),
                               'authorization': self.headers.get('Authorization'), 'path': self.path}
        if self.path == '/unauthorized/chat/completions':
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'private secret key must not be echoed')
            return
        if self.path == '/redirect/chat/completions':
            self.send_response(302)
            self.send_header('Location', '/stolen-key')
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'choices': [{'message': {'content': '原文支持此解释 [P1]。'},
                                    'finish_reason': 'stop'}], 'usage': {'total_tokens': 10}}).encode())

    def log_message(self, *args):
        pass


class AITests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.model = ThreadingHTTPServer(('127.0.0.1', 0), MockModel)
        self.thread = threading.Thread(target=self.model.serve_forever, daemon=True)
        self.thread.start()
        self.base = f'http://127.0.0.1:{self.model.server_port}'
        self.config = {'base_url': self.base, 'model': 'test-model', 'api_key': 'test-secret',
                       'max_tokens': 512, 'token_field': 'max_tokens'}

    def tearDown(self):
        self.model.shutdown()
        self.model.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def test_transport_and_redacted_errors(self):
        result = complete(self.config, '测试问题')
        self.assertIn('P1', result['text'])
        self.assertEqual(MockModel.received['path'], '/chat/completions')
        self.assertEqual(MockModel.received['authorization'], 'Bearer test-secret')
        self.assertEqual(MockModel.received['payload']['max_tokens'], 512)
        self.assertEqual(MockModel.received['payload']['messages'][1]['content'], '测试问题')
        for path in ('/unauthorized', '/redirect'):
            with self.assertRaises(ValueError) as cm:
                complete({**self.config, 'base_url': self.base + path}, 'test')
            self.assertNotIn('private secret', str(cm.exception))

    def test_settings_do_not_write_plaintext_and_destination_change_clears_key(self):
        path = Path(self.tmp.name) / 'ai-settings.json'
        settings = Settings(path)
        public = settings.save(self.config)
        self.assertTrue(public['has_key'])
        self.assertNotIn('api_key', public)
        self.assertNotIn('test-secret', path.read_text())
        self.assertFalse(Settings(path).public()['has_key'])
        settings.save({**self.config, 'base_url': self.base + '/new', 'api_key': ''})
        self.assertFalse(settings.public()['has_key'])

    @unittest.skipUnless(os.name == 'nt', 'Windows DPAPI')
    def test_windows_key_roundtrip(self):
        self.assertEqual(protect_key(protect_key(b'test-secret'), True), b'test-secret')
        path = Path(self.tmp.name) / 'settings.json'
        Settings(path).save({**self.config, 'remember_key': True})
        self.assertEqual(Settings(path).snapshot()['api_key'], 'test-secret')
        self.assertNotIn('test-secret', path.read_text())

    def test_url_and_citation_validation(self):
        for url in ('http://remote.example/v1', 'https://user:pass@example.com/v1', 'https://example.com/v1?key=secret'):
            with self.assertRaises(ValueError):
                validate_url(url)
        warnings = citation_warnings('[P1] and [P99]', [{'id': 1}])
        self.assertTrue(any('P99' in w for w in warnings))

    def test_full_analysis_saves_selected_evidence_only(self):
        db = str(Path(self.tmp.name) / 'research.sqlite3')
        lib = Library(db)
        lib.import_book('test.txt', '选中原文\n\n没有选取的秘密段落'.encode(), '测试典籍')
        lib.close()
        app = create_server(db)
        app.ai_settings.save(self.config)
        thread = threading.Thread(target=app.serve_forever, daemon=True)
        thread.start()
        try:
            req = Request(f'http://127.0.0.1:{app.server_port}/api/analyze',
                          json.dumps({'ids': [1], 'question': '解释前提'}).encode(),
                          headers={'X-Research-Token': TOKEN, 'Content-Type': 'application/json'})
            with urlopen(req) as r:
                result = json.load(r)
            self.assertEqual(result['id'], 1)
            sent = MockModel.received['payload']['messages'][1]['content']
            self.assertIn('选中原文', sent)
            self.assertNotIn('没有选取的秘密段落', sent)
            lib = Library(db)
            saved = lib.analyses()[0]
            self.assertEqual(len(saved['evidence']), 1)
            self.assertEqual(saved['model'], 'test-model')
            self.assertNotIn('test-secret', json.dumps(lib.backup()))
            lib.close()
        finally:
            app.shutdown()
            app.server_close()
            thread.join()


if __name__ == '__main__':
    unittest.main()
