"""Single-user local research workbench. Bind to loopback only."""
import argparse
import base64
import binascii
import json
import os
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from core import Library, notes_markdown, analyses_markdown, research_prompt, chat_messages, conversations_markdown
from ai import Settings, complete, complete_messages, citation_warnings

ROOT = Path(__file__).parent
TOKEN = secrets.token_urlsafe(32)
MAX_BODY = 40 * 1024 * 1024


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
        if route.path == '/api/session':
            return self.respond(200, {'token': TOKEN})
        lib = Library(self.server.db_path)
        try:
            q = parse_qs(route.query)
            if route.path == '/api/books':
                data = lib.books()
            elif route.path == '/api/passages':
                data = lib.passages(q.get('book', [None])[0], q.get('q', [''])[0],
                                    100, max(0, int(q.get('offset', ['0'])[0])))
            elif route.path == '/api/notes':
                data = lib.notes()
            elif route.path == '/api/conversations':
                data = lib.list_conversations()
            elif route.path == '/api/conversation':
                data = lib.get_conversation(int(q.get('id', ['0'])[0]))
            elif route.path == '/api/analyses':
                data = lib.analyses()
            elif route.path == '/api/settings':
                data = self.server.ai_settings.public()
            elif route.path == '/api/export':
                convs = [lib.get_conversation(c['id']) for c in lib.list_conversations()]
                data = {'markdown': notes_markdown(lib.notes()) + analyses_markdown(lib.analyses())
                        + conversations_markdown(convs), 'backup': lib.backup()}
            else:
                return self.respond(404, {'error': '页面不存在。'})
            self.respond(200, data)
        except (ValueError, TypeError) as exc:
            self.respond(400, {'error': str(exc)})
        finally:
            lib.close()

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
            lib = Library(self.server.db_path)
            try:
                if self.path == '/api/import':
                    raw = base64.b64decode(data['data'], validate=True)
                    if len(raw) > 25 * 1024 * 1024:
                        raise ValueError('文件上限 25 MB。')
                    result = lib.import_book(data['filename'], raw, data['title'],
                                             data.get('author', ''), data.get('edition', ''))
                elif self.path == '/api/notes':
                    lib.add_note(data['passage_id'], data['kind'], data['body'])
                    result = {'saved': True}
                elif self.path == '/api/note-update':
                    result = lib.update_note(data['id'], data['kind'], data['body'])
                elif self.path == '/api/note-delete':
                    result = lib.delete_note(data['id'])
                elif self.path == '/api/book-delete':
                    result = lib.delete_book(data['id'])
                elif self.path == '/api/conversation-delete':
                    result = lib.delete_conversation(data['id'])
                elif self.path == '/api/chat':
                    message = str(data.get('message', ''))
                    if not message.strip():
                        raise ValueError('请输入问题。')
                    config = self.server.ai_settings.snapshot()
                    cid = data.get('conversation_id')
                    if cid:
                        conv = lib.get_conversation(int(cid))
                        passages = conv['conversation']['context']
                        history = [(m['role'], m['body']) for m in conv['messages']]
                        cid = int(cid)
                    else:
                        ids = list(dict.fromkeys(data.get('ids', [])))
                        created = lib.create_conversation(str(data.get('title', '')), ids,
                                                          config['model'], config['base_url'])
                        cid = created['id']
                        conv = lib.get_conversation(cid)
                        passages = conv['conversation']['context']
                        history = []
                    result = complete_messages(config, chat_messages(passages, history, message))
                    warnings = citation_warnings(result['text'], passages)
                    if result['finish_reason'] == 'length':
                        warnings.insert(0, '模型输出因 token 上限而截断；本条回答不完整。')
                    lib.add_message(cid, 'user', message)
                    mid = lib.add_message(cid, 'assistant', result['text'], warnings)
                    result = {'conversation_id': cid, 'message_id': mid, 'text': result['text'],
                              'warnings': warnings, 'usage': result.get('usage', {})}
                elif self.path == '/api/settings':
                    result = self.server.ai_settings.save(data)
                elif self.path == '/api/ai-test':
                    config = self.server.ai_settings.snapshot()
                    complete(config, '连接测试。请只回答：连接成功。')
                    result = {'message': '连接成功，模型已返回正文。'}
                elif self.path in ('/api/prompt', '/api/analyze'):
                    ids = list(dict.fromkeys(data['ids']))
                    if not 1 <= len(ids) <= 20:
                        raise ValueError('一次选择 1—20 段原文。')
                    passages = [lib.passage(i) for i in ids]
                    question = str(data.get('question', ''))
                    prompt = research_prompt(passages, question)
                    if self.path == '/api/prompt':
                        result = {'prompt': prompt}
                    else:
                        config = self.server.ai_settings.snapshot()
                        result = complete(config, prompt)
                        warnings = citation_warnings(result['text'], passages)
                        if result['finish_reason'] == 'length':
                            warnings.insert(0, '模型输出因 token 上限而截断；本条分析不完整。')
                        result['id'] = lib.save_analysis(question, passages, config['model'],
                                                         config['base_url'], result, warnings)
                        result['warnings'] = warnings
                else:
                    return self.respond(404, {'error': '操作不存在。'})
                self.respond(200, result)
            finally:
                lib.close()
        except (ValueError, KeyError, TypeError, binascii.Error) as exc:
            self.respond(400, {'error': str(exc)})

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
    server.ai_settings = Settings(Path(db_path).parent / 'ai-settings.json')
    return server


if __name__ == '__main__':
    main()
