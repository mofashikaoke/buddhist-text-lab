import json
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from http.server import ThreadingHTTPServer

from core import (Library, STUDIO_KINDS, chat_messages, citation, conversations_markdown, notes_markdown,
                  research_prompt, studio_prompt)
from server import Handler, TOKEN


def long_corpus(lib, passages=60):
    """A source far larger than the retrieval budget; passage i mentions its own unique term."""
    filler = '如是我闻一时佛在舍卫国祇树给孤独园与大比丘众千二百五十人俱。' * 20
    text = '\n\n'.join(f'第{i}章 专名{i:03d}独有。' + filler for i in range(passages))
    lib.import_book('big.txt', text.encode(), '大部典籍')


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

    def test_multi_term_search_requires_all_terms(self):
        self.lib.import_book('t.txt', '如是我闻。\n\n无我无常。\n\n如是无常。'.encode(), '测试')
        self.assertEqual(self.lib.passages(query='如是 无常')['total'], 1)
        self.assertEqual(self.lib.passages(query='  无常  ')['total'], 2)
        self.assertEqual(self.lib.passages(query='无我 如是')['total'], 0)
        self.assertEqual(self.lib.passages(query='   ')['total'], 3)

    def test_script_folding_is_opt_in(self):
        self.lib.import_book('t.txt', '觀自在菩薩，般若波羅蜜多。\n\n观自在菩萨在此。\n\n無關內容。'.encode(), '繁简')
        self.assertEqual(self.lib.passages(query='观自在')['total'], 1)
        self.assertEqual(self.lib.passages(query='觀自在')['total'], 1)
        result = self.lib.passages(query='观自在', fold_script=True)
        self.assertEqual(result['total'], 2)
        self.assertIn('觀自在', result['highlight'])
        self.assertEqual(self.lib.passages(query='般若波罗蜜多 菩萨', fold_script=True)['total'], 1)
        self.assertEqual(self.lib.passages(query='無關', fold_script=True)['total'], 1)

    def test_oversized_block_is_split_without_losing_text(self):
        lines = [f'第{i}行' + '文' * 200 + '。' for i in range(20)]
        self.lib.import_book('lines.txt', '\n'.join(lines).encode(), '分行文本')
        items = self.lib.passages()['items']
        self.assertGreater(len(items), 1)
        self.assertTrue(all(len(p['text']) <= 1500 for p in items))
        self.assertEqual('\n'.join(p['text'] for p in items), '\n'.join(lines))
        sentences = ''.join(f'句{i}' + '文' * 100 + '。' for i in range(40))
        self.lib.import_book('one.txt', sentences.encode(), '单行文本')
        pieces = [p['text'] for p in self.lib.passages(book_id=self.lib.books()[-1]['id'])['items']]
        self.assertGreater(len(pieces), 1)
        self.assertEqual(''.join(pieces), sentences)
        self.assertTrue(all(len(t) <= 1500 for t in pieces))

    def test_short_single_newline_block_stays_one_passage(self):
        self.lib.import_book('s.txt', '如实保留\n原文。'.encode(), '短文')
        self.assertEqual([p['text'] for p in self.lib.passages()['items']], ['如实保留\n原文。'])

    def test_empty_and_gb18030(self):
        with self.assertRaises(ValueError):
            self.lib.import_book('empty.txt', b' \n\n ', '空文本')
        self.assertEqual(self.lib.books(), [])
        self.lib.import_book('gb.txt', '中文测试'.encode('gb18030'), '编码测试')
        self.assertEqual(self.lib.passages()['items'][0]['text'], '中文测试')

    # ---- sources on/off and grounding ------------------------------------
    def test_enable_disable_sources(self):
        a = self.lib.import_book('a.txt', '甲书内容'.encode(), '甲')['id']
        b = self.lib.import_book('b.txt', '乙书内容'.encode(), '乙')['id']
        self.assertEqual([x['enabled'] for x in self.lib.books()], [1, 1])
        self.lib.set_enabled(a, False)
        self.assertEqual(self.lib.enabled_book_ids(), [b])
        self.assertEqual([p['title'] for p in self.lib.retrieve('内容')['passages']], ['乙'])
        self.lib.set_enabled(None, False)
        with self.assertRaises(ValueError):
            self.lib.retrieve('内容')
        self.lib.set_enabled(None, True)
        self.assertEqual(len(self.lib.enabled_book_ids()), 2)
        with self.assertRaises(ValueError):
            self.lib.set_enabled(999, True)

    def test_small_sources_are_used_whole(self):
        self.lib.import_book('t.txt', '第一段。\n\n第二段。\n\n第三段。'.encode(), '小典籍')
        got = self.lib.retrieve('任意问题')
        self.assertEqual(got['mode'], 'all')
        self.assertEqual([p['text'] for p in got['passages']], ['第一段。', '第二段。', '第三段。'])

    def test_large_sources_are_retrieved_by_question(self):
        long_corpus(self.lib)
        got = self.lib.retrieve('专名042独有是什么意思')
        self.assertEqual(got['mode'], 'mixed')  # one real match, the rest spread across the source
        self.assertLessEqual(len(got['passages']), 12)
        self.assertLessEqual(sum(len(p['text']) for p in got['passages']), 30000 + 1500)
        self.assertEqual([p['ordinal'] for p in got['passages'] if '专名042' in p['text']], [43])
        ordinals = [p['ordinal'] for p in got['passages']]
        self.assertEqual(ordinals, sorted(ordinals))

    def test_unmatched_question_falls_back_to_spread_sample(self):
        long_corpus(self.lib)
        got = self.lib.retrieve('zzzz')
        self.assertEqual(got['mode'], 'sample')
        ords = [p['ordinal'] for p in got['passages']]
        self.assertGreater(len(ords), 3)
        self.assertGreater(ords[-1] - ords[0], 30)
        studio = self.lib.sample()
        self.assertEqual(studio['mode'], 'sample')
        self.assertEqual(studio['total'], 60)

    # ---- notes ---------------------------------------------------------------
    def test_notes_are_free_standing_snapshots(self):
        self.lib.import_book('test.md', '测试原文'.encode(), '测试典籍')
        p = self.lib.passages()['items'][0]
        free = self.lib.add_note('随想', '个人笔记', '没有引用的笔记。')
        cited = self.lib.add_note('', '待核查', '需要核查版本。', [p['id'], p['id']])
        self.lib.close()
        self.lib = Library(self.path)
        notes = {n['id']: n for n in self.lib.notes()}
        self.assertEqual(notes[free]['evidence'], [])
        self.assertEqual(len(notes[cited]['evidence']), 1)
        self.assertIn('文本无页码', citation(notes[cited]['evidence'][0]))
        with self.assertRaises(ValueError):
            self.lib.add_note('', '原文', '不能把笔记伪装成原文')
        with self.assertRaises(ValueError):
            self.lib.add_note('', '个人笔记', '  ')
        with self.assertRaises(ValueError):
            self.lib.add_note('', '个人笔记', '引用不存在', [999])
        self.lib.delete_book(self.lib.books()[0]['id'])
        self.assertEqual(self.lib.passages()['total'], 0)
        kept = [n for n in self.lib.notes() if n['id'] == cited][0]
        self.assertEqual(kept['evidence'][0]['text'], '测试原文')
        self.assertEqual(len(self.lib.backup()['notes']), 2)

    def test_note_update_and_delete(self):
        nid = self.lib.add_note('初', '个人笔记', '初版')
        self.lib.update_note(nid, '修订', '待核查', '修订版')
        n = self.lib.notes()[0]
        self.assertEqual((n['title'], n['kind'], n['body']), ('修订', '待核查', '修订版'))
        self.lib.delete_note(nid)
        self.assertEqual(self.lib.notes(), [])
        with self.assertRaises(ValueError):
            self.lib.delete_note(999)
        with self.assertRaises(ValueError):
            self.lib.update_note(999, '', '个人笔记', 'x')
        with self.assertRaises(ValueError):
            self.lib.delete_book(999)

    # ---- conversations -------------------------------------------------------
    def test_conversation_flow_keeps_per_message_evidence(self):
        self.lib.import_book('test.txt', '第一段原文。\n\n第二段原文。'.encode(), '测试典籍')
        passages = self.lib.retrieve('问')['passages']
        conv = self.lib.create_conversation('', 'test-model', 'http://127.0.0.1:1')
        self.assertEqual(conv['title'], '新对话')
        self.lib.add_message(conv['id'], 'user', '核心论点是什么？')
        self.lib.add_message(conv['id'], 'assistant', '依据 P1……', ['警告'], passages)
        got = self.lib.get_conversation(conv['id'])
        self.assertEqual(len(got['messages']), 2)
        self.assertEqual(got['messages'][0]['evidence'], [])
        self.assertEqual([p['text'] for p in got['messages'][1]['evidence']], ['第一段原文。', '第二段原文。'])
        self.assertEqual(got['messages'][1]['warnings'], ['警告'])
        self.assertEqual(self.lib.rename_conversation(conv['id'], '  般若研读  ')['title'], '般若研读')
        self.assertEqual(self.lib.list_conversations()[0]['messages'], 2)
        with self.assertRaises(ValueError):
            self.lib.rename_conversation(conv['id'], '   ')
        with self.assertRaises(ValueError):
            self.lib.rename_conversation(999, '不存在')
        self.lib.delete_book(self.lib.books()[0]['id'])
        self.assertEqual(len(self.lib.get_conversation(conv['id'])['messages'][1]['evidence']), 2)
        self.lib.delete_conversation(conv['id'])
        self.assertEqual(self.lib.list_conversations(), [])
        with self.assertRaises(ValueError):
            self.lib.get_conversation(conv['id'])

    def test_prompts_preserve_evidence(self):
        self.lib.import_book('test.txt', '如实保留\n原文。'.encode(), '测试')
        p = self.lib.passages()['items'][0]
        prompt = research_prompt([p], '分析其前提')
        self.assertIn(p['text'], prompt)
        self.assertIn('证据不足', prompt)
        self.assertIn('分析其前提', prompt)
        for kind in STUDIO_KINDS:
            text = studio_prompt(kind, [p], '问题')
            self.assertIn(p['text'], text)
            self.assertIn('证据不足', text)
        with self.assertRaises(ValueError):
            studio_prompt('unknown', [p])
        with self.assertRaises(ValueError):
            studio_prompt('summary', [])
        messages = chat_messages([p], [('user', '前一问'), ('assistant', '前一答')], '新问')
        self.assertEqual([m['role'] for m in messages], ['system', 'user', 'assistant', 'user'])
        self.assertIn(p['text'], messages[0]['content'])

    def test_exports_include_cited_text(self):
        self.lib.import_book('test.txt', '被引用的原文。'.encode(), '测试典籍')
        passages = self.lib.retrieve('问')['passages']
        self.lib.add_note('标题', 'AI 推断', '结论 P1', [passages[0]['id']], warnings=['需核查'])
        conv = self.lib.create_conversation('对话', 'm', 'e')
        self.lib.add_message(conv['id'], 'assistant', '回答 P1', (), passages)
        notes_md = notes_markdown(self.lib.notes())
        convs_md = conversations_markdown([self.lib.get_conversation(conv['id'])])
        for md in (notes_md, convs_md):
            self.assertIn('被引用的原文。', md)
        self.assertIn('需核查', notes_md)

    # ---- migration -------------------------------------------------------------
    def test_v3_database_is_migrated_and_backed_up(self):
        old = str(Path(self.tmp.name) / 'old.sqlite3')
        db = sqlite3.connect(old)
        db.executescript('''
        CREATE TABLE books (id INTEGER PRIMARY KEY, title TEXT NOT NULL, author TEXT NOT NULL,
          edition TEXT NOT NULL, filename TEXT NOT NULL, digest TEXT UNIQUE NOT NULL);
        CREATE TABLE passages (id INTEGER PRIMARY KEY, book_id INTEGER NOT NULL REFERENCES books(id),
          page INTEGER NOT NULL, ordinal INTEGER NOT NULL, text TEXT NOT NULL);
        CREATE TABLE notes (id INTEGER PRIMARY KEY, passage_id INTEGER NOT NULL REFERENCES passages(id),
          kind TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL DEFAULT '2026-01-01T00:00:00Z');
        CREATE TABLE analyses (id INTEGER PRIMARY KEY, question TEXT NOT NULL, evidence TEXT NOT NULL,
          model TEXT NOT NULL, endpoint TEXT NOT NULL, body TEXT NOT NULL, warnings TEXT NOT NULL,
          usage TEXT NOT NULL, created TEXT NOT NULL DEFAULT '2026-01-02T00:00:00Z');
        CREATE TABLE conversations (id INTEGER PRIMARY KEY, title TEXT NOT NULL, context TEXT NOT NULL,
          model TEXT NOT NULL, endpoint TEXT NOT NULL, created TEXT NOT NULL DEFAULT '2026-01-03T00:00:00Z');
        CREATE TABLE messages (id INTEGER PRIMARY KEY, conversation_id INTEGER NOT NULL
          REFERENCES conversations(id) ON DELETE CASCADE, role TEXT NOT NULL, body TEXT NOT NULL,
          warnings TEXT NOT NULL DEFAULT '[]', created TEXT NOT NULL DEFAULT '2026-01-03T00:00:01Z');
        INSERT INTO books VALUES (1,'旧典籍','作者','版本','a.txt','digest1');
        INSERT INTO passages VALUES (1,1,0,1,'旧原文。');
        INSERT INTO notes(id,passage_id,kind,body) VALUES (1,1,'个人笔记','旧笔记');
        INSERT INTO analyses(id,question,evidence,model,endpoint,body,warnings,usage)
          VALUES (1,'旧问题','[{"id":1,"title":"旧典籍","author":"作者","edition":"版本","page":0,"ordinal":1,"text":"旧原文。"}]','m','e','旧分析','["旧警告"]','{}');
        INSERT INTO conversations(id,title,context,model,endpoint) VALUES (1,'旧对话','[]','m','e');
        INSERT INTO messages(conversation_id,role,body) VALUES (1,'user','旧问');
        ''')
        db.commit()
        db.close()
        lib = Library(old)
        try:
            self.assertEqual(lib.db.execute('PRAGMA user_version').fetchone()[0], 4)
            self.assertEqual(lib.books()[0]['enabled'], 1)
            notes = lib.notes()
            self.assertEqual(sorted(n['origin'] for n in notes), ['analysis', 'manual'])
            manual = [n for n in notes if n['origin'] == 'manual'][0]
            self.assertEqual(manual['body'], '旧笔记')
            self.assertEqual(manual['created'], '2026-01-01T00:00:00Z')
            self.assertEqual(manual['evidence'][0]['text'], '旧原文。')
            analysis = [n for n in notes if n['origin'] == 'analysis'][0]
            self.assertEqual((analysis['title'], analysis['body'], analysis['warnings']), ('旧问题', '旧分析', ['旧警告']))
            self.assertEqual(lib.get_conversation(1)['messages'][0]['evidence'], [])
            self.assertTrue(Path(old + '.v3.bak').exists())
        finally:
            lib.close()
        again = Library(old)
        try:
            self.assertEqual(len(again.notes()), 2)
        finally:
            again.close()

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
            req = urllib.request.Request(base + '/api/prompt', '{"question":"问"}'.encode(),
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
