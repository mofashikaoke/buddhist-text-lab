"""Independent research notebooks; existing data remains the default notebook."""
import json
from pathlib import Path
import threading
import uuid


class Notebooks:
    def __init__(self, default_db):
        self.default_db = Path(default_db)
        self.index = self.default_db.parent / 'notebooks.json'
        self.lock = threading.Lock()

    def list(self):
        with self.lock:
            return self._read()

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

    def create(self, name):
        name = str(name).strip()
        if not 1 <= len(name) <= 60:
            raise ValueError('研究本名称应为 1—60 个字符。')
        with self.lock:
            rows = self._read()
            row = {'id': uuid.uuid4().hex, 'name': name}
            rows.append(row)
            self.index.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.index.with_suffix('.tmp')
            tmp.write_text(json.dumps(rows, ensure_ascii=False), encoding='utf-8')
            tmp.replace(self.index)
            return row

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
