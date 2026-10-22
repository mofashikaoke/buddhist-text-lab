"""Installed desktop app using an embedded WebView2 window."""
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
from urllib.request import urlopen
from server import create_server


def data_dir():
    return Path(os.environ.get('LOCALAPPDATA', str(Path.home() / '.local' / 'share'))) / 'BuddhistTextLab'


class DesktopAPI:
    def __init__(self, folder):
        self.folder = folder
        self.window = None

    def open_data_folder(self):
        os.startfile(str(self.folder))
        return True

    def save_text(self, name, text):
        import webview
        if not isinstance(text, str) or len(text) > 80 * 1024 * 1024:
            raise ValueError('导出内容超出上限。')
        filename = Path(name).name
        paths = self.window.create_file_dialog(webview.FileDialog.SAVE, save_filename=filename)
        if not paths:
            return {'saved': False}
        path = paths if isinstance(paths, str) else paths[0]
        Path(path).write_text(text, encoding='utf-8-sig')
        return {'saved': True}


def run_window(server, folder, smoke_output=None):
    import webview
    api = DesktopAPI(folder)
    window = webview.create_window('佛典研究工作台', f'http://127.0.0.1:{server.server_port}',
                                   js_api=api, width=1480, height=960, min_size=(1100, 720),
                                   background_color='#f6f4ee', text_select=True)
    api.window = window
    errors = []
    def verify():
        if not smoke_output:
            return
        try:
            # loaded means renderer is ready; app bootstrap may still be fetching data.
            ready = False
            for _ in range(100):
                ready = window.evaluate_js("Boolean(document.getElementById('send-chat') && document.getElementById('notebook-select').options.length && window.pywebview && window.pywebview.api.save_text)")
                if ready:
                    break
                time.sleep(0.1)
            if not ready:
                raise RuntimeError('Desktop UI elements missing')
            result = window.evaluate_js("document.title")
            if result != '佛典研究工作台':
                raise RuntimeError('Unexpected desktop title')
            Path(smoke_output).write_text('PASS: embedded WebView2 window and UI resources', encoding='utf-8')
        except Exception as exc:
            errors.append(str(exc))
        finally:
            window.destroy()
    window.events.loaded += verify
    webview.start(gui='edgechromium', private_mode=False, storage_path=str(folder / 'webview'))
    if errors:
        raise RuntimeError('; '.join(errors))


def smoke_test(output, gui=False):
    from pypdf import PdfReader
    from ai import protect_key
    if os.name == 'nt':
        assert protect_key(protect_key(b'smoke-test'), True) == b'smoke-test'
    with tempfile.TemporaryDirectory() as tmp:
        folder = Path(tmp)
        server = create_server(str(folder / 'research.sqlite3'))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            if gui:
                run_window(server, folder, output)
            else:
                base = f'http://127.0.0.1:{server.server_port}'
                for route, expected in [('/', '佛典研究工作台'), ('/app.js', 'loadBooks'), ('/style.css', ':root')]:
                    with urlopen(base + route) as r:
                        assert expected in r.read().decode('utf-8'), route
                with urlopen(base + '/api/notebooks') as r:
                    assert json.load(r)[0]['id'] == 'default'
                Path(output).write_text('PASS: packaged assets, HTTP, SQLite, PDF module, DPAPI', encoding='utf-8')
        finally:
            server.shutdown()
            server.server_close()
            thread.join()


def main():
    for flag, gui in [('--smoke-test', False), ('--gui-smoke-test', True)]:
        if flag in sys.argv:
            smoke_test(sys.argv[sys.argv.index(flag) + 1], gui)
            return
    folder = data_dir()
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == 'nt':
        import ctypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateMutexW.argtypes = [ctypes.c_void_p, ctypes.c_bool, ctypes.c_wchar_p]
        kernel.CreateMutexW.restype = ctypes.c_void_p
        mutex = kernel.CreateMutexW(None, False, 'Local\\BuddhistTextLab.Desktop')
        if ctypes.get_last_error() == 183:
            ctypes.windll.user32.MessageBoxW(None, '佛典研究工作台已在运行，请在任务栏打开。', '佛典研究工作台', 0)
            return
    server = create_server(str(folder / 'research.sqlite3'))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        run_window(server, folder)
    except Exception:
        import traceback
        (folder / 'startup-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        if os.name == 'nt':
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, '桌面窗口启动失败。请检查 Microsoft WebView2 Runtime 是否已安装，或重新运行安装程序。详情见数据目录 startup-error.log。', '佛典研究工作台', 16)
        raise
    finally:
        server.shutdown()
        server.server_close()
        thread.join()


if __name__ == '__main__':
    main()
