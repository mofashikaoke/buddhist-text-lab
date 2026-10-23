"""Independent research notebooks; existing data remains the default notebook."""
import datetime
import json
from pathlib import Path
import threading
import uuid

from core import Library


class Notebooks:
    def __init__(self, default_db):
        self.default_db = Path(default_db)
        self.index = self.default_db.parent / 'notebooks.json'
        self.lock = threading.Lock()

    def list(self):
        with self.lock:
            return self._read()

    def overview(self):
        """Every notebook with its source/note/conversation counts and last-modified time."""
        rows = []
        for row in self.list():
            path = Path(self.path(row['id']))
            lib = Library(path)
            try:
                stats = lib.stats()
            finally:
                lib.close()
            updated = datetime.datetime.fromtimestamp(path.stat().st_mtime, datetime.timezone.utc)
            rows.append({**row, **stats, 'updated': updated.strftime('%Y-%m-%dT%H:%M:%SZ')})
        return rows

    def _read(self):
        if not self.index.exists():
            return [{'id': 'default', 'name': '我的佛典研究'}]
        try:
            rows = json.loads(self.index.read_text(encoding='utf-8'))
            if not isinstance(rows, list):
                raise ValueError()
            return rows
        except (OSError, ValueError):
            raise ValueError('研究本目录无法读取，请先备份数据文件夹后检查 notebooks.json。') from None

    def _write(self, rows):
        self.index.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.index.with_suffix('.tmp')
        tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
        tmp.replace(self.index)

    @staticmethod
    def _clean_name(name):
        name = str(name).strip()
        if not 1 <= len(name) <= 60:
            raise ValueError('研究本名称应为 1—60 个字符。')
        return name

    def create(self, name):
        name = self._clean_name(name)
        with self.lock:
            rows = self._read()
            row = {'id': uuid.uuid4().hex, 'name': name}
            rows.append(row)
            self._write(rows)
            return row

    def rename(self, notebook_id, name):
        name = self._clean_name(name)
        with self.lock:
            rows = self._read()
            for row in rows:
                if row['id'] == notebook_id:
                    row['name'] = name
                    self._write(rows)
                    return row
        raise ValueError('研究本不存在。')

    def delete(self, notebook_id):
        if notebook_id == 'default':
            raise ValueError('默认研究本不能删除，可以重命名。')
        path = Path(self.path(notebook_id))
        with self.lock:
            self._write([r for r in self._read() if r['id'] != notebook_id])
        for suffix in ('', '.v3.bak'):
            Path(str(path) + suffix).unlink(missing_ok=True)
        return {'deleted': notebook_id}

    def path(self, notebook_id):
        notebook_id = notebook_id or 'default'
        if notebook_id == 'default':
            return str(self.default_db)
        if not any(r['id'] == notebook_id for r in self.list()):
            raise ValueError('研究本不存在。')
        # IDs originate from UUID generation, never directly from a filesystem path.
        if len(notebook_id) != 32 or any(c not in '0123456789abcdef' for c in notebook_id):
            raise ValueError('研究本编号无效。')
        return str(self.default_db.parent / 'notebooks' / (notebook_id + '.sqlite3'))
