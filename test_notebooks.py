import json
from pathlib import Path
import tempfile
import threading
import unittest
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from core import Library
from notebooks import Notebooks
from server import create_server, TOKEN


class NotebookTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = str(Path(self.tmp.name) / 'research.sqlite3')
        self.manager = Notebooks(self.db)

    def tearDown(self):
        self.tmp.cleanup()

    def test_existing_data_and_isolated_notebooks(self):
        old = Library(self.db)
        old.import_book('old.txt', '旧资料'.encode(), '旧典籍')
        old.close()
        n = self.manager.create('般若研究')
        other = Library(self.manager.path(n['id']))
        self.assertEqual(other.books(), [])
        other.import_book('new.txt', '新资料'.encode(), '新典籍')
        other.close()
        old = Library(self.manager.path('default'))
        self.assertEqual(old.books()[0]['title'], '旧典籍')
        old.close()
        self.assertEqual(Notebooks(self.db).list()[1]['name'], '般若研究')

    def test_unknown_and_path_traversal(self):
        for name in ('../research', 'missing'):
            with self.assertRaises(ValueError):
                self.manager.path(name)
        with self.assertRaises(ValueError):
            self.manager.create(' ')

    def test_overview_rename_and_delete(self):
        old = Library(self.db)
        old.import_book('old.txt', '旧资料'.encode(), '旧典籍')
        old.add_note('', '个人笔记', '笔记')
        old.close()
        n = self.manager.create('临时研究本')
        rows = {r['id']: r for r in self.manager.overview()}
        self.assertEqual((rows['default']['sources'], rows['default']['notes']), (1, 1))
        self.assertEqual((rows[n['id']]['sources'], rows[n['id']]['conversations']), (0, 0))
        self.assertTrue(rows[n['id']]['updated'].endswith('Z'))
        self.assertEqual(self.manager.rename('default', '总库')['name'], '总库')
        self.assertEqual(Notebooks(self.db).list()[0]['name'], '总库')
        with self.assertRaises(ValueError):
            self.manager.rename('missing', '名')
        with self.assertRaises(ValueError):
            self.manager.rename(n['id'], '  ')
        path = Path(self.manager.path(n['id']))
        self.assertTrue(path.exists())
        self.manager.delete(n['id'])
        self.assertFalse(path.exists())
        self.assertEqual([r['id'] for r in self.manager.list()], ['default'])
        with self.assertRaises(ValueError):
            self.manager.delete('default')
        with self.assertRaises(ValueError):
            self.manager.delete(n['id'])

    def test_http_notebook_scope(self):
        server = create_server(self.db)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            request = Request(base + '/api/notebook-create', json.dumps({'name': '新研究本'}).encode(),
                              headers={'X-Research-Token': TOKEN})
            with urlopen(request) as r:
                n = json.load(r)
            with urlopen(Request(base + '/api/books', headers={'X-Notebook-ID': n['id']})) as r:
                self.assertEqual(json.load(r), [])
            with self.assertRaises(HTTPError) as cm:
                urlopen(Request(base + '/api/books', headers={'X-Notebook-ID': 'nonexistent'}))
            self.assertEqual(cm.exception.code, 400)
            with urlopen(Request(base + '/api/notebooks', headers={'X-Notebook-ID': 'stale'})) as r:
                rows = json.load(r)
            self.assertEqual(len(rows), 2)
            self.assertIn('sources', rows[0])
            for path, body in (('/api/notebook-rename', {'id': n['id'], 'name': '改名'}),
                               ('/api/notebook-delete', {'id': n['id']})):
                with urlopen(Request(base + path, json.dumps(body).encode(), headers={'X-Research-Token': TOKEN})):
                    pass
            with urlopen(Request(base + '/api/notebooks')) as r:
                self.assertEqual([x['id'] for x in json.load(r)], ['default'])
        finally:
            server.shutdown()
            server.server_close()
            t.join()


if __name__ == '__main__':
    unittest.main()
