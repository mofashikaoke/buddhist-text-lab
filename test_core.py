import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer

from core import Library, citation, research_prompt
from server import Handler, TOKEN


class ResearchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = str(Path(self.tmp.name) / 'lab.sqlite3')
        self.lib = Library(self.path)

    def tearDown(self):
        self.lib.close()
        self.tmp.cleanup()

    def test_import_search_and_duplicate(self):
        text = '甲：无我。\n\n乙：100% 不等于 _。'
        self.lib.import_book('test.txt', text.encode(), '测试文本', '测试作者', '测试版')
        self.assertEqual(self.lib.passages(query='无我')['total'], 1)
        self.assertEqual(self.lib.passages(query='%')['total'], 1)
        self.assertEqual(self.lib.passages(query="' OR 1=1 --")['total'], 0)
        with self.assertRaises(ValueError):
            self.lib.import_book('copy.txt', text.encode(), '副本')

    def test_notes_persist_and_reference_original(self):
        self.lib.import_book('test.md', '测试原文'.encode(), '测试典籍')
        p = self.lib.passages()['items'][0]
        self.lib.add_note(p['id'], '待核查', '需要核查版本。')
        self.lib.close()
        self.lib = Library(self.path)
        n = self.lib.notes()[0]
        self.assertEqual(n['text'], '测试原文')
        self.assertIn('文本无页码', citation(n))
        self.assertIn(f"P{p['id']}", citation(n))
        self.assertEqual(len(self.lib.backup()['notes']), 1)
        with self.assertRaises(ValueError):
            self.lib.add_note(999, '个人笔记', '不存在')
        with self.assertRaises(ValueError):
            self.lib.add_note(p['id'], '原文', '不能把笔记伪装成原文')

    def test_prompt_preserves_evidence(self):
        self.lib.import_book('test.txt', '如实保留\n原文。'.encode(), '测试')
        p = self.lib.passages()['items'][0]
        prompt = research_prompt([p], '分析其前提')
        self.assertIn(p['text'], prompt)
        self.assertIn('证据不足', prompt)
        self.assertIn('分析其前提', prompt)

    def test_empty_and_gb18030(self):
        with self.assertRaises(ValueError):
            self.lib.import_book('empty.txt', b' \n\n ', '空文本')
        self.assertEqual(self.lib.books(), [])
        self.lib.import_book('gb.txt', '中文测试'.encode('gb18030'), '编码测试')
        self.assertEqual(self.lib.passages()['items'][0]['text'], '中文测试')

    def test_http_and_request_protection(self):
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        server.db_path = self.path
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        base = f'http://127.0.0.1:{server.server_port}'
        try:
            with urllib.request.urlopen(base + '/') as r:
                self.assertIn('佛典研究工作台', r.read().decode())
            with urllib.request.urlopen(base + '/api/books') as r:
                self.assertEqual(json.load(r), [])
            req = urllib.request.Request(base + '/api/notes', b'{}', method='POST')
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req)
            self.assertEqual(cm.exception.code, 403)
            req = urllib.request.Request(base + '/api/prompt', b'{"ids":[]}',
                                          headers={'X-Research-Token': TOKEN}, method='POST')
            with self.assertRaises(urllib.error.HTTPError) as cm:
                urllib.request.urlopen(req)
            self.assertEqual(cm.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            t.join()


if __name__ == '__main__':
    unittest.main()
