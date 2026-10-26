import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import socket
import ssl
import urllib.error
from ai import Settings, citation_warnings, complete, describe_network_error, protect_key, validate_url
from core import Library
from server import TOKEN, create_server


class MockModel(BaseHTTPRequestHandler):
    received = None

    def do_GET(self):
        type(self).received = {'path': self.path, 'authorization': self.headers.get('Authorization')}
        if self.path.startswith('/unauthorized'):
            self.send_response(401)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'object': 'list', 'data': [{'id': 'model-b'}, {'id': 'model-a'}]}).encode())

    def do_POST(self):
        type(self).received = {'payload': json.loads(self.rfile.read(int(self.headers['Content-Length']))),
                               'authorization': self.headers.get('Authorization'), 'path': self.path}
        if self.path == '/unauthorized/chat/completions':
            self.send_response(401)
            self.end_headers()
            self.wfile.write(b'private secret key must not be echoed')
            return
        if self.path == '/reset/chat/completions':
            self.connection.close()  # drop the connection without any HTTP response
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
        MockModel.received = None

    def tearDown(self):
        self.model.shutdown()
        self.model.server_close()
        self.thread.join()
        self.tmp.cleanup()

    def start_app(self, books, settings=None):
        """An app server over a database holding the given {title: text} sources."""
        db = str(Path(self.tmp.name) / 'app.sqlite3')
        lib = Library(db)
        for title, text in books.items():
            lib.import_book(title + '.txt', text.encode(), title)
        lib.close()
        app = create_server(db)
        app.ai_settings.save(settings or self.config)
        thread = threading.Thread(target=app.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(lambda: (app.shutdown(), app.server_close(), thread.join()))
        base = f'http://127.0.0.1:{app.server_port}'

        def post(path, payload):
            req = Request(base + path, json.dumps(payload).encode(),
                          headers={'X-Research-Token': TOKEN, 'Content-Type': 'application/json'})
            with urlopen(req) as r:
                return json.load(r)

        def get(path):
            with urlopen(base + path) as r:
                return json.load(r)

        return db, post, get

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

    def test_dropped_connection_becomes_value_error(self):
        with self.assertRaises(ValueError):
            complete({**self.config, 'base_url': self.base + '/reset'}, 'test')

    def test_network_failures_name_their_cause(self):
        cases = [(urllib.error.URLError(ssl.SSLCertVerificationError('CERTIFICATE_VERIFY_FAILED')), '证书'),
                 (urllib.error.URLError(socket.gaierror(11001, 'getaddrinfo failed')), 'DNS'),
                 (urllib.error.URLError(TimeoutError('timed out')), '超时'),
                 (urllib.error.URLError(ConnectionRefusedError()), '拒绝'),
                 (ConnectionResetError(), '中断'),
                 (urllib.error.URLError(OSError('weird')), 'OSError')]
        for exc, word in cases:
            message = describe_network_error(exc)
            self.assertIn(word, message)
            self.assertNotIn('test-secret', message)

    def test_model_list_uses_form_values_and_never_forwards_saved_key(self):
        db, post, get = self.start_app({'甲书': '甲书的原文。'})
        got = post('/api/models', {'base_url': self.base, 'api_key': ''})
        self.assertEqual(got['models'], ['model-a', 'model-b'])
        self.assertEqual(MockModel.received['path'], '/models')
        self.assertEqual(MockModel.received['authorization'], 'Bearer test-secret')  # same destination: saved key
        post('/api/models', {'base_url': self.base + '/other', 'api_key': ''})
        self.assertIsNone(MockModel.received['authorization'])  # new destination: saved key is not sent
        post('/api/models', {'base_url': self.base + '/other', 'api_key': 'typed-key'})
        self.assertEqual(MockModel.received['authorization'], 'Bearer typed-key')
        with self.assertRaises(HTTPError) as cm:
            post('/api/models', {'base_url': self.base + '/unauthorized', 'api_key': 'x'})
        self.assertEqual(cm.exception.code, 400)
        self.assertEqual(get('/api/settings')['model'], 'test-model')  # nothing was saved by listing

    def test_bad_model_error_points_to_the_model_list(self):
        from ai import HTTP_MESSAGES
        for code in (400, 404, 422):
            self.assertIn('获取模型列表', HTTP_MESSAGES[code])

    def test_payment_required_is_explained(self):
        class Broke(MockModel):
            def do_POST(self):
                self.rfile.read(int(self.headers['Content-Length']))
                self.send_response(402)
                self.end_headers()
        server = ThreadingHTTPServer(('127.0.0.1', 0), Broke)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with self.assertRaises(ValueError) as cm:
                complete({**self.config, 'base_url': f'http://127.0.0.1:{server.server_port}'}, 'x')
            self.assertIn('余额不足', str(cm.exception))
        finally:
            server.shutdown()
            server.server_close()
            thread.join()

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
        for pasted in ('https://example.com/v1/chat/completions', 'https://example.com/v1/messages', 'https://example.com/v1/'):
            self.assertEqual(validate_url(pasted), 'https://example.com/v1')
        warnings = citation_warnings('[P1] and [P99]', [{'id': 1}])
        self.assertTrue(any('P99' in w for w in warnings))

    # ---- chat grounded in the enabled sources ----------------------------------
    def test_chat_uses_enabled_sources_only_and_keeps_history(self):
        db, post, get = self.start_app({'甲书': '甲书的原文。', '乙书': '乙书没有启用的秘密段落。'})
        post('/api/book-enable', {'id': 2, 'enabled': False})
        first = post('/api/chat', {'message': '第一问'})
        self.assertIn('P1', first['text'])
        sent = MockModel.received['payload']['messages']
        self.assertIn('甲书的原文', sent[0]['content'])
        self.assertNotIn('秘密段落', sent[0]['content'])
        self.assertEqual(sent[-1]['content'], '第一问')
        self.assertEqual([p['title'] for p in first['evidence']], ['甲书'])
        second = post('/api/chat', {'conversation_id': first['conversation_id'], 'message': '第二问'})
        sent = MockModel.received['payload']['messages']
        self.assertEqual([m['content'] for m in sent[-3:]], ['第一问', '原文支持此解释 [P1]。', '第二问'])
        saved = get('/api/conversation?id=' + str(first['conversation_id']))
        self.assertEqual(len(saved['messages']), 4)
        self.assertEqual(saved['conversation']['title'], '第一问')
        self.assertEqual(saved['messages'][1]['evidence'][0]['text'], '甲书的原文。')
        self.assertTrue(any('编号' in w for m in saved['messages'] for w in m['warnings']))
        post('/api/book-enable', {'id': None, 'enabled': True})
        post('/api/chat', {'conversation_id': first['conversation_id'], 'message': '第三问'})
        self.assertIn('秘密段落', MockModel.received['payload']['messages'][0]['content'])
        lib = Library(db)
        self.assertEqual(len(lib.list_conversations()), 1)
        lib.close()

    def test_chat_without_enabled_sources_is_refused_and_leaves_nothing_behind(self):
        db, post, get = self.start_app({'甲书': '甲书的原文。'})
        post('/api/book-enable', {'id': None, 'enabled': False})
        with self.assertRaises(HTTPError) as cm:
            post('/api/chat', {'message': '问'})
        self.assertEqual(cm.exception.code, 400)
        self.assertEqual(get('/api/conversations'), [])
        self.assertIsNone(MockModel.received)

    def test_failed_first_chat_leaves_no_empty_conversation(self):
        db, post, get = self.start_app({'甲书': '选中原文'}, {**self.config, 'base_url': self.base + '/unauthorized'})
        with self.assertRaises(HTTPError) as cm:
            post('/api/chat', {'message': '问'})
        self.assertEqual(cm.exception.code, 400)
        self.assertEqual(get('/api/conversations'), [])

    def test_large_source_notes_that_only_part_was_used(self):
        filler = '如是我闻一时佛在舍卫国祇树给孤独园。' * 40
        text = '\n\n'.join(f'第{i}章 专名{i:03d}独有。' + filler for i in range(60))
        db, post, get = self.start_app({'大部': text})
        answer = post('/api/chat', {'message': '专名042独有讲了什么'})
        self.assertTrue(any('检索' in w and '/60' in w for w in answer['warnings']))
        sent = MockModel.received['payload']['messages'][0]['content']
        self.assertIn('专名042', sent)
        self.assertLess(len(answer['evidence']), 13)

    def test_answer_can_be_saved_as_note_with_cited_evidence_only(self):
        db, post, get = self.start_app({'甲书': '甲书第一段。\n\n甲书第二段。'})
        answer = post('/api/chat', {'message': '问'})
        note = post('/api/notes', {'message_id': answer['message_id'], 'title': '存档'})
        self.assertEqual((note['kind'], note['origin'], note['title']), ('AI 推断', 'chat', '存档'))
        self.assertEqual([p['id'] for p in note['evidence']], [1])  # the answer cites only P1
        self.assertIn('P1', note['body'])
        user_message = get('/api/conversation?id=' + str(answer['conversation_id']))['messages'][0]
        with self.assertRaises(HTTPError):
            post('/api/notes', {'message_id': user_message['id']})

    # ---- Studio -----------------------------------------------------------------
    def test_studio_outputs_are_saved_as_notes_with_snapshots(self):
        db, post, get = self.start_app({'甲书': '甲书的原文。', '乙书': '乙书的原文。'})
        post('/api/book-enable', {'id': 2, 'enabled': False})
        note = post('/api/studio', {'kind': 'summary'})
        self.assertEqual((note['title'], note['origin']), ('来源摘要', 'studio'))
        self.assertEqual([p['title'] for p in note['evidence']], ['甲书'])
        sent = MockModel.received['payload']['messages'][1]['content']
        self.assertIn('甲书的原文', sent)
        self.assertNotIn('乙书的原文', sent)
        analysis = post('/api/studio', {'kind': 'analysis', 'question': '解释前提'})
        self.assertIn('解释前提', analysis['title'])
        self.assertIn('解释前提', MockModel.received['payload']['messages'][1]['content'])
        self.assertEqual(len(get('/api/notes')), 2)
        for bad in ({'kind': 'analysis', 'question': ' '}, {'kind': 'nope'}):
            with self.assertRaises(HTTPError) as cm:
                post('/api/studio', bad)
            self.assertEqual(cm.exception.code, 400)
        lib = Library(db)
        self.assertNotIn('test-secret', json.dumps(lib.backup()))
        lib.close()

    def test_prompt_endpoint_needs_no_ai(self):
        db, post, get = self.start_app({'甲书': '甲书的原文。'}, {**self.config, 'base_url': self.base + '/reset'})
        result = post('/api/prompt', {'kind': 'glossary'})
        self.assertIn('甲书的原文', result['prompt'])
        self.assertEqual(result['passages'], 1)
        self.assertIsNone(MockModel.received)


if __name__ == '__main__':
    unittest.main()
