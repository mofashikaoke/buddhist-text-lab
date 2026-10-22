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

    def test_conversation_grounding_flow(self):
        self.lib.import_book('test.txt', '第一段原文。\n\n第二段原文。'.encode(), '测试典籍')
        pids = [p['id'] for p in self.lib.passages()['items']]
        with self.assertRaises(ValueError):
            self.lib.create_conversation('空', [], 'm', 'http://127.0.0.1:1')
        conv = self.lib.create_conversation('', pids, 'test-model', 'http://127.0.0.1:1')
        self.assertIn('测试典籍', conv['title'])
        self.assertEqual(len(self.lib.list_conversations()), 1)
        self.lib.add_message(conv['id'], 'user', '核心论点是什么？')
        self.lib.add_message(conv['id'], 'assistant', '依据 P1……', ['编号检查仅确认引用是否来自所选材料；引文准确性和推理仍需核查。'])
        got = self.lib.get_conversation(conv['id'])
        self.assertEqual(len(got['messages']), 2)
        self.assertEqual(len(got['conversation']['context']), 2)
        self.assertEqual(got['messages'][1]['warnings'][0][:2], '编号')
        self.lib.delete_conversation(conv['id'])
        self.assertEqual(self.lib.list_conversations(), [])
        with self.assertRaises(ValueError):
            self.lib.get_conversation(conv['id'])

    def test_note_update_delete_and_book_delete(self):
        self.lib.import_book('test.txt', '原文段落'.encode(), '测试典籍')
        p = self.lib.passages()['items'][0]
        nid = self.lib.add_note(p['id'], '个人笔记', '初版')
        self.lib.update_note(nid, '待核查', '修订版')
        self.assertEqual(self.lib.notes()[0]['body'], '修订版')
        self.lib.delete_note(nid)
        self.assertEqual(self.lib.notes(), [])
        with self.assertRaises(ValueError):
            self.lib.delete_note(999)
        nid = self.lib.add_note(p['id'], '个人笔记', '随书删除')
        self.lib.delete_book(self.lib.books()[0]['id'])
        self.assertEqual(self.lib.books(), [])
        self.assertEqual(self.lib.passages()['total'], 0)
        self.assertEqual(self.lib.notes(), [])
        with self.assertRaises(ValueError):
            self.lib.delete_book(999)

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
