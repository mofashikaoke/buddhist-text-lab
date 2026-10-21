"""Windows GUI launcher and packaged executable smoke test."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
from urllib.request import urlopen
import webbrowser

from server import create_server


def data_dir():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share'))) / 'BuddhistTextLab'


def smoke_test(output):
    import tkinter
    from pypdf import PdfReader
    from ai import protect_key
    if os.name == 'nt':
        assert protect_key(protect_key(b'smoke-test'), True) == b'smoke-test'
    with tempfile.TemporaryDirectory() as tmp:
        server = create_server(str(Path(tmp) / 'research.sqlite3'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            base = f'http://127.0.0.1:{server.server_port}'
            for route, expected in [('/', '佛典研究工作台'), ('/app.js', 'loadBooks'), ('/style.css', ':root')]:
                with urlopen(base + route) as r:
                    assert expected in r.read().decode('utf-8'), route
            with urlopen(base + '/api/settings') as r:
                assert not json.load(r)['has_key']
            Path(output).write_text('PASS: packaged assets, server, SQLite, PDF import module, Windows DPAPI', encoding='utf-8')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


def main():
    if '--smoke-test' in sys.argv:
        smoke_test(sys.argv[sys.argv.index('--smoke-test') + 1])
        return
    import tkinter as tk
    from tkinter import messagebox
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    root.title('佛典研究工作台')
    root.geometry('530x335')
    root.resizable(False, False)
    root.configure(bg='#f6f4ee')
    try:
        server = create_server(str(folder / 'research.sqlite3'))
    except Exception:
        messagebox.showerror('启动失败', '无法打开研究数据库，请检查数据目录权限。')
        root.destroy()
        return
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f'http://127.0.0.1:{server.server_port}'
    tk.Label(root, text='佛典研究工作台', font=('Microsoft YaHei', 23, 'bold'), fg='#315944', bg='#f6f4ee').pack(pady=(30, 8))
    tk.Label(root, text='典籍检索 · 原文对照 · AI 分析 · 研究笔记', font=('Microsoft YaHei', 11), bg='#f6f4ee').pack()
    tk.Label(root, text='研究界面在浏览器中打开。\n退出本窗口将停止服务，已保存的资料会保留。', bg='#f6f4ee', fg='#707970').pack(pady=15)
    tk.Button(root, text='打开研究工作台', command=lambda: webbrowser.open(url), width=23, bg='#315944', fg='white', font=('Microsoft YaHei', 11)).pack(pady=5)
    tk.Button(root, text='打开数据文件夹', command=lambda: os.startfile(folder), width=23).pack(pady=5)
    def close():
        server.shutdown()
        server.server_close()
        root.destroy()
    root.protocol('WM_DELETE_WINDOW', close)
    root.after(350, lambda: webbrowser.open(url))
    root.mainloop()


if __name__ == '__main__':
    main()
