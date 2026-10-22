# 佛典研究工作台 · Buddhist Text Lab

提供 Windows 安装程序的中文佛典研究项目：NotebookLM 式三栏界面（来源 / 对话 / 笔记），从原文检索出发，基于选定原文与 AI 多轮对话、比较文本、组织分析材料并积累可追溯笔记。

## 0.4 安装版与研究工作区

- **独立桌面客户端**：安装到 Windows 后在自己的窗口中使用，无需另开浏览器。
- **独立研究本**：按主题分别保存典籍、对话和笔记，旧资料保留在默认研究本。
- **原文回查**：点选 P编号查看完整原文与出处，AI 回答可保存为笔记。
- **原生导出**：桌面版使用 Windows 保存文件对话框。

- **来源（左栏）**：导入 TXT、Markdown、可提取文字的 PDF；记录典籍名称、译者/作者、版本/来源；原文字面检索、分页浏览；PDF 保留文件物理页号；支持删除典籍。
- **对话（中栏）**：选择最多 20 段原文作为依据，与 AI 多轮对话；每次回答只引用所选原文并标注 P编号；引用编号自动检查，未引用的回答会明确提示；对话记录本机保存，可随时回看与删除。
- **笔记（右栏）**：双栏原文对照（最多两段）；保存“个人笔记 / 注疏解释 / AI 推断 / 待核查”记录，关联不可变的原文段落，支持编辑与删除；结构化深度分析（单次任务）与提示词生成。
- 导出 Markdown 笔记（含对话记录）和 JSON 研究数据；SQLite 数据库在本机持久保存。
- “AI 接口设置”支持 OpenAI / Chat Completions 兼容接口、自定义模型、连接测试和最大输出 token；Windows 可用 DPAPI 加密保存密钥。
- 无需 API 密钥也能用检索、对照与笔记；TXT/Markdown 功能只依赖 Python 标准库。

## Windows 安装

打开仓库的 [Releases 页面](https://github.com/mofashikaoke/buddhist-text-lab/releases/latest)，下载 `BuddhistTextLab-Setup-0.4.*-x64.exe`。64 位 Windows 10 / 11 双击安装（默认装到 Program Files），安装完成后在开始菜单启动。不需要安装 Python。首次构建完成后才会出现下载文件；构建状态见 [Actions](https://github.com/mofashikaoke/buddhist-text-lab/actions/workflows/windows.yml)。

- 安装后在独立 WebView2 桌面窗口中运行，关闭主窗口退出程序。
- 在“设置”中填写 API 基础地址、模型名和 API Key，点击“保存设置”后再点“测试连接”。
- 在左侧“来源”检索原文，点“加入对话”选定依据，在中间栏提问；右侧可对照原文、记笔记、做结构化分析。
- 软件不包含 API Key 或额度，需填写自己的服务商凭证。标签与引用编号检查不代表结论已被验证。

安装包附 SHA-256 校验文件。安装向导提供目录选择、开始菜单、可选桌面快捷方式以及卸载入口；升级和卸载保留用户数据。缺少 WebView2 时通过微软组件安装器补装（需网络）。

完整操作、数据目录和迁移方法见 [WINDOWS.md](WINDOWS.md)。

## 从源码运行（Windows）

1. 安装 Python 3.10 或更高版本。
2. 下载本仓库：GitHub 页面选择 **Code → Download ZIP**，解压到电脑。
3. 如需导入 PDF，在项目目录打开终端执行：

   ```powershell
   py -3 -m pip install -r requirements.txt
   ```

4. 双击 `start.bat`，或执行：

   ```powershell
   py -3 server.py
   ```

5. 浏览器打开 <http://127.0.0.1:8787>。使用过程中保留终端窗口，关闭终端或按 Ctrl+C 停止服务。

macOS / Linux 使用 `python3 -m pip install -r requirements.txt` 和 `python3 server.py`。

## 建议研究流程

1. 导入自己有来源记录的文本，填写版本信息。
2. 在左侧搜索术语或句子，核对 PDF 原页。提取文字可能丢失排版、脚注关系或读序。
3. 把相关段落“加入对话”作为依据，或放入右侧“对照”。
4. 在中间栏多轮追问；需要一次性长篇分析时，用右侧“结构化分析”。
5. 将引文、解释和推断分开记录；注疏解释要补充注疏作者和出处。
6. 定期导出笔记，并备份 `%LOCALAPPDATA%\BuddhistTextLab\research.sqlite3`。

## 数据与边界

- 默认只监听 `127.0.0.1`，用于本机单用户，不适合直接开放到公网。
- 应用仅在主动发起对话或分析时向配置接口发送所选原文、元数据和问题；连接测试仅发送简短测试消息。
- 原始 PDF 不保存，保存的是提取文本、元数据、文件 SHA-256 和笔记。请另外保留原文件。
- PDF 引用采用**文件物理页号**，不是印刷页码；TXT/Markdown 没有页码。
- 段落以空行分隔，PDF 每页独立处理；长段不截断。无空行的 PDF 可能整页对应一段。
- 扫描版 PDF 不支持 OCR；混合 PDF 中提取不到文字的页数会提示，含图片的部分页面仍应人工核对。
- 检索为精确字面匹配，不自动进行繁简转换、异体字归并、语义检索或译本对齐。
- 单个文件上限 25 MB；同一文件内容不会重复导入。对话依据原文上限 20 段、上下文 10 万字符。
- JSON 导出可供其他程序使用，本版没有 JSON 回导功能。完整迁移请在服务停止后复制 SQLite 数据库，并使用相同版本程序启动。
- 典籍、对话与笔记保存在本机数据库，`.gitignore` 阻止它们进入 GitHub。不要将数据库提交到仓库。
- 本仓库不预装任何典籍，不捏造藏经编号、译者、引文或版本信息。

自定义数据文件和端口：

```powershell
py -3 server.py --port 8788 --data D:\BuddhistResearch\research.sqlite3
```

## 验证

```powershell
py -3 -m unittest -v
```

测试覆盖导入、重复文件、字面检索、数据持久化、笔记关联与编辑删除、典籍删除、对话依据隔离与历史、AI 模拟接口端到端对话与分析、选材隔离、错误脱敏、密钥存储和 HTTP 写入保护。Windows 构建还运行 DPAPI 测试及打包产物冒烟测试。

## 后续迭代

- PDF 页图与原文定位、OCR、繁简/异体字检索。
- 笔记版本记录、备份恢复、典籍元数据修订。
- 基于真实版本资料的跨典籍语义检索与术语研究。

GitHub 用于保存源代码与版本；仓库本身不是已部署、可直接在线使用的服务。

## 构建安装程序

GitHub Actions 在 Windows x64 上运行测试、用 PyInstaller 打包，再用 Inno Setup 编译安装程序；验证实际安装、覆盖升级、独立 WebView2 窗口和卸载保留数据后发布 Release。可在 Windows 项目目录手动执行：

```powershell
py -3 -m pip install -r requirements-desktop.txt pyinstaller
py -3 -m PyInstaller --noconfirm --clean --onedir --windowed --name BuddhistTextLab --add-data "web;web" --collect-all pypdf --collect-all webview desktop.py
"C:\Program Files (x86)\Inno Setup 6\ISCC.exe" installer/BuddhistTextLab.iss /DAppVersion=0.4.0
```

接口实现参考 [OpenAI Chat Completions 官方文档](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)，打包路径与资源处理参考 [PyInstaller 官方文档](https://pyinstaller.org/en/stable/runtime-information.html)，安装脚本参考 [Inno Setup 官方文档](https://jrsoftware.org/ishelp/)。

桌面版操作与数据目录详见 [WINDOWS.md](WINDOWS.md)。构建依赖见 `requirements-desktop.txt`。研究本数据库应整体备份数据根目录。
