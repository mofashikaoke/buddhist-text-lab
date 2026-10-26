"""Single-user local research workbench. Bind to loopback only."""
import argparse
import base64
import binascii
import json
import os
import re
import secrets
import sqlite3
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core import (Library, STUDIO_KINDS, notes_markdown, studio_prompt, chat_messages,
                  conversations_markdown)
from notebooks import Notebooks
from ai import Settings, complete, complete_messages, citation_warnings

ROOT = Path(__file__).parent
TOKEN = secrets.token_urlsafe(32)
MAX_BODY = 40 * 1024 * 1024
GROUNDING_LABEL = {'search': '按问题检索', 'mixed': '检索加均匀抽样', 'sample': '均匀抽样'}


def grounding_note(grounding):
    """A warning stored with answers that did not use every passage of the enabled sources."""
    if grounding['mode'] == 'all':
        return None
    return (f"来源较长，本次依据{GROUNDING_LABEL[grounding['mode']]}选出的 "
            f"{len(grounding['passages'])}/{grounding['total']} 段原文；未选入的段落没有参与回答。")


def merge_passages(*groups):
    seen, merged = set(), []
    for group in groups:
        for p in group:
            if p['id'] not in seen:
                seen.add(p['id'])
                merged.append(p)
    return merged


class Handler(BaseHTTPRequestHandler):
    def respond(self, status, data, mime='application/json; charset=utf-8'):
        raw = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Cache-Control', 'no-store')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'")
        self.end_headers()
        self.wfile.write(raw)

    def trusted_host(self):
        return self.headers.get('Host') in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')

    def library(self):
        notebook = self.headers.get('X-Notebook-ID', 'default')
        return Library(self.server.notebooks.path(notebook) if hasattr(self.server, 'notebooks')
                       else self.server.db_path)

    def do_GET(self):
        if not self.trusted_host():
            return self.respond(403, {'error': '只接受本机访问。'})
        route = urlparse(self.path)
        static = {'/': ('index.html', 'text/html; charset=utf-8'),
                  '/app.js': ('app.js', 'text/javascript; charset=utf-8'),
                  '/style.css': ('style.css', 'text/css; charset=utf-8')}
        if route.path in static:
            name, mime = static[route.path]
            return self.respond(200, (ROOT / 'web' / name).read_bytes(), mime)
        try:
            if route.path == '/api/session':
                return self.respond(200, {'token': TOKEN})
            if route.path == '/api/notebooks':
                return self.respond(200, self.server.notebooks.overview())
            if route.path == '/api/settings':
                return self.respond(200, self.server.ai_settings.public())
            lib = self.library()
            try:
                q = parse_qs(route.query)
                if route.path == '/api/books':
                    data = lib.books()
                elif route.path == '/api/passages':
                    data = lib.passages(q.get('book', [None])[0], q.get('q', [''])[0],
                                        100, max(0, int(q.get('offset', ['0'])[0])),
                                        q.get('fold', ['0'])[0] == '1')
                elif route.path == '/api/notes':
                    data = lib.notes()
                elif route.path == '/api/conversations':
                    data = lib.list_conversations()
                elif route.path == '/api/conversation':
                    data = lib.get_conversation(int(q.get('id', ['0'])[0]))
                elif route.path == '/api/export':
                    convs = [lib.get_conversation(c['id']) for c in lib.list_conversations()]
                    data = {'markdown': notes_markdown(lib.notes()) + conversations_markdown(convs),
                            'backup': lib.backup()}
                else:
                    return self.respond(404, {'error': '页面不存在。'})
                self.respond(200, data)
            finally:
                lib.close()
        except (ValueError, TypeError) as exc:
            self.respond(400, {'error': str(exc)})
        except (sqlite3.Error, OSError):
            self.respond(500, {'error': '本地数据库或文件操作失败，请重试。'})

    def do_POST(self):
        if not self.trusted_host() or self.headers.get('X-Research-Token') != TOKEN:
            return self.respond(403, {'error': '请刷新工作台后重试。'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                return self.respond(413, {'error': '请求过大。单次导入文件上限 25 MB。'})
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError('请求格式无效。')
            if self.path.startswith('/api/notebook-'):
                return self.respond(200, self.notebook_action(self.path, data))
            if self.path == '/api/settings':
                return self.respond(200, self.server.ai_settings.save(data))
            if self.path == '/api/models':
                return self.respond(200, self.server.ai_settings.models(data))
            if self.path == '/api/ai-test':
                complete(self.server.ai_settings.snapshot(), '连接测试。请只回答：连接成功。')
                return self.respond(200, {'message': '连接成功，模型已返回正文。'})
            lib = self.library()
            try:
                self.respond(200, self.library_action(lib, self.path, data))
            finally:
                lib.close()
        except (ValueError, KeyError, TypeError, binascii.Error) as exc:
            self.respond(400, {'error': str(exc)})
        except (sqlite3.Error, OSError):
            self.respond(500, {'error': '本地数据库或文件操作失败，请重试。'})

    def notebook_action(self, path, data):
        books = self.server.notebooks
        if path == '/api/notebook-create':
            return books.create(data.get('name', ''))
        if path == '/api/notebook-rename':
            return books.rename(str(data['id']), data.get('name', ''))
        if path == '/api/notebook-delete':
            return books.delete(str(data['id']))
        raise ValueError('操作不存在。')

    def library_action(self, lib, path, data):
        if path == '/api/import':
            raw = base64.b64decode(data['data'], validate=True)
            if len(raw) > 25 * 1024 * 1024:
                raise ValueError('文件上限 25 MB。')
            return lib.import_book(data['filename'], raw, data['title'], data.get('author', ''), data.get('edition', ''))
        if path == '/api/book-enable':
            return lib.set_enabled(data.get('id'), bool(data.get('enabled')))
        if path == '/api/book-delete':
            return lib.delete_book(data['id'])
        if path == '/api/notes':
            if data.get('message_id'):
                return self.note_from_message(lib, data)
            ids = data.get('passage_ids', [])
            if not isinstance(ids, list):
                raise ValueError('引用格式无效。')
            nid = lib.add_note(data.get('title', ''), data['kind'], data['body'], ids)
            return lib.note(nid)
        if path == '/api/note-update':
            lib.update_note(data['id'], data.get('title', ''), data['kind'], data['body'])
            return lib.note(data['id'])
        if path == '/api/note-delete':
            return lib.delete_note(data['id'])
        if path == '/api/conversation-rename':
            return lib.rename_conversation(data['id'], str(data.get('title', '')))
        if path == '/api/conversation-delete':
            return lib.delete_conversation(data['id'])
        if path == '/api/chat':
            return self.chat(lib, data)
        if path == '/api/studio':
            return self.studio(lib, data)
        if path == '/api/prompt':
            kind = data.get('kind') or 'analysis'
            question = str(data.get('question', ''))
            grounding = lib.retrieve(question) if question.strip() else lib.sample()
            return {'prompt': studio_prompt(kind, grounding['passages'], question),
                    'passages': len(grounding['passages']), 'total': grounding['total']}
        raise ValueError('操作不存在。')

    def note_from_message(self, lib, data):
        """Save a chat answer as a note, keeping the passages it actually cites."""
        message = lib.message(data['message_id'])
        if message['role'] != 'assistant':
            raise ValueError('只能把 AI 回答保存为笔记。')
        cited = {int(i) for i in re.findall(r'\bP(\d+)\b', message['body'])}
        evidence = [p for p in message['evidence'] if p['id'] in cited] or message['evidence']
        nid = lib.add_note_with_evidence(data.get('title', ''), 'AI 推断', message['body'], evidence,
                                         'chat', message['warnings'])
        return lib.note(nid)

    def chat(self, lib, data):
        message = str(data.get('message', ''))
        if not message.strip():
            raise ValueError('请输入问题。')
        config = self.server.ai_settings.snapshot()
        cid = data.get('conversation_id')
        is_new = not cid
        if cid:
            cid = int(cid)
            conv = lib.get_conversation(cid)
            history = [(m['role'], m['body']) for m in conv['messages']]
            pinned = conv['conversation']['context']
        else:
            title = str(data.get('title', '')) or ' '.join(message.split())[:30]
            cid = lib.create_conversation(title, config['model'], config['base_url'])['id']
            history, pinned = [], []
        try:
            grounding = lib.retrieve(message)
            passages = merge_passages(pinned, grounding['passages'])
            result = complete_messages(config, chat_messages(passages, history, message))
        except Exception:
            if is_new:
                lib.delete_conversation(cid)  # do not leave an empty conversation behind
            raise
        warnings = citation_warnings(result['text'], passages)
        if result['finish_reason'] == 'length':
            warnings.insert(0, '模型输出因 token 上限而截断；本条回答不完整。')
        note = grounding_note(grounding)
        if note:
            warnings.append(note)
        lib.add_message(cid, 'user', message)
        mid = lib.add_message(cid, 'assistant', result['text'], warnings, passages)
        return {'conversation_id': cid, 'message_id': mid, 'text': result['text'], 'warnings': warnings,
                'evidence': passages, 'usage': result.get('usage', {})}

    def studio(self, lib, data):
        kind = str(data.get('kind', ''))
        if kind not in STUDIO_KINDS:
            raise ValueError('不支持的 Studio 类型。')
        question = str(data.get('question', ''))
        if kind == 'analysis' and not question.strip():
            raise ValueError('深度分析需要填写研究问题。')
        grounding = lib.retrieve(question) if kind == 'analysis' else lib.sample()
        prompt = studio_prompt(kind, grounding['passages'], question)
        result = complete(self.server.ai_settings.snapshot(), prompt)
        warnings = citation_warnings(result['text'], grounding['passages'])
        if result['finish_reason'] == 'length':
            warnings.insert(0, '模型输出因 token 上限而截断；本条产出不完整。')
        note = grounding_note(grounding)
        if note:
            warnings.append(note)
        title = STUDIO_KINDS[kind][0] + (f'：{question.strip()[:30]}' if kind == 'analysis' else '')
        nid = lib.add_note_with_evidence(title, 'AI 推断', result['text'], grounding['passages'], 'studio', warnings)
        return lib.note(nid)

    def log_message(self, fmt, *args):
        # Do not log search queries or uploaded text.
        pass


def main():
    parser = argparse.ArgumentParser(description='佛典研究工作台（本机单用户）')
    parser.add_argument('--port', type=int, default=8787)
    parser.add_argument('--data', default=os.environ.get('BUDDHIST_LAB_DATA', str(ROOT / 'data' / 'research.sqlite3')))
    args = parser.parse_args()
    server = create_server(args.data, args.port)
    print(f'佛典研究工作台：http://127.0.0.1:{args.port} （Ctrl+C 退出）', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def create_server(db_path, port=0):
    Library(db_path).close()
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.db_path = db_path
    server.notebooks = Notebooks(db_path)
    server.ai_settings = Settings(Path(db_path).parent / 'ai-settings.json')
    return server


if __name__ == '__main__':
    main()
