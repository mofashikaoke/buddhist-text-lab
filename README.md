# 佛典研究工作台 · Buddhist Text Lab

提供 Windows EXE 的中文佛典研究项目，用于从原文检索出发，比较文本、组织分析材料并积累可追溯笔记。

## 首版已实现

- 导入 TXT、Markdown、可提取文字的 PDF；记录典籍名称、译者/作者、版本/来源。
- 原文字面检索、分页浏览、段落编号；PDF 保留文件物理页号。
- 双栏原文对照，支持不同典籍之间选段。
- 选择最多 20 段执行 AI 分析或生成提示词，包含原文出处、术语、论证结构、最强反驳和证据不足处理要求。
- 保存“个人笔记 / 注疏解释 / AI 推断 / 待核查”记录，关联不可变的原文段落。
- 导出 Markdown 笔记和 JSON 研究数据；SQLite 数据库在本机持久保存。
- 无需 API 密钥，无需 Node.js；TXT/Markdown 功能只依赖 Python 标准库。

## Windows EXE 下载与 AI 分析

打开仓库的 [Releases 页面](https://github.com/mofashikaoke/buddhist-text-lab/releases/latest)，下载 `BuddhistTextLab.exe` 或 ZIP。64 位 Windows 10 / 11 双击运行，不需要安装 Python。首次打包完成后才会出现下载文件；构建状态见 [Actions](https://github.com/mofashikaoke/buddhist-text-lab/actions/workflows/windows.yml)。

- 桌面启动器自动打开浏览器研究界面；关闭启动器停止服务。
- “AI 接口设置”支持 OpenAI / Chat Completions 兼容接口、自定义模型、连接测试和最大输出 token。
- 选择原文后可直接发起 AI 分析，结果保留模型、接口、问题及原文快照。
- Windows 可用 DPAPI 加密保存密钥；不勾选则只保存于本次进程内存。密钥不会写入研究数据库或导出文件。
- 软件不包含 API Key 或额度，需填写自己的服务商凭证。标签与引用编号检查不代表结论已被验证。

完整操作、数据目录和迁移方法见 [WINDOWS.md](WINDOWS.md)。


## 在 Windows 上运行

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
2. 搜索术语或句子，核对 PDF 原页。提取文字可能丢失排版、脚注关系或读序。
3. 把相关段落加入“原文对照”或“研究材料”。
4. 在“分析工作区”填写具体问题，调用配置的 AI 接口分析，或仅生成提示词。
5. 将引文、解释和推断分开记录；注疏解释要补充注疏作者和出处。
6. 定期导出笔记，并备份 `data/research.sqlite3`。

## 数据与边界

- 默认只监听 `127.0.0.1`，用于本机单用户，不适合直接开放到公网。
- 应用仅在主动点击 AI 分析时向配置接口发送所选原文、元数据和问题；连接测试仅发送简短测试消息。
- 原始 PDF 不保存，保存的是提取文本、元数据、文件 SHA-256 和笔记。请另外保留原文件。
- PDF 引用采用**文件物理页号**，不是印刷页码；TXT/Markdown 没有页码。
- 段落以空行分隔，PDF 每页独立处理；长段不截断。无空行的 PDF 可能整页对应一段。
- 扫描版 PDF 不支持 OCR；混合 PDF 中提取不到文字的页数会提示，含图片的部分页面仍应人工核对。
- 检索为精确字面匹配，不自动进行繁简转换、异体字归并、语义检索或译本对齐。
- 单个文件上限 25 MB；同一文件内容不会重复导入。
- JSON 导出可供其他程序使用，本版没有 JSON 回导功能。完整迁移请在服务停止后复制 SQLite 数据库，并使用相同版本程序启动。
- 典籍与笔记保存在本机数据库，`.gitignore` 阻止它们进入 GitHub。不要将数据库提交到仓库。
- 本仓库不预装任何典籍，不捏造藏经编号、译者、引文或版本信息。

自定义数据文件和端口：

```powershell
py -3 server.py --port 8788 --data D:\BuddhistResearch\research.sqlite3
```

## 验证

```powershell
py -3 -m unittest -v
```

测试覆盖导入、重复文件、字面检索、数据持久化、笔记关联、AI 模拟接口端到端分析、选材隔离、错误脱敏、密钥存储和 HTTP 写入保护。Windows 构建还运行 DPAPI 测试及打包 EXE 冒烟测试。

## 后续迭代

- 结构化引文逐字核对与更完整的分析质量检查。
- PDF 页图与原文定位、OCR、繁简/异体字检索。
- 笔记编辑和版本记录、备份恢复、典籍元数据修订。
- 基于真实版本资料的跨典籍语义检索与术语研究。

GitHub 用于保存源代码与版本；仓库本身不是已部署、可直接在线使用的服务。

## 构建 EXE

GitHub Actions 在 Windows x64 上运行测试、用 PyInstaller 打包单文件、启动打包产物验证资源与服务，并发布 Release。可在 Windows 项目目录手动执行：

```powershell
py -3 -m pip install -r requirements.txt pyinstaller
py -3 -m PyInstaller --noconfirm --clean --onefile --windowed --name BuddhistTextLab --add-data "web:web" --collect-all pypdf desktop.py
```

接口实现参考 [OpenAI Chat Completions 官方文档](https://developers.openai.com/api/reference/resources/chat/subresources/completions/methods/create)，打包路径与资源处理参考 [PyInstaller 官方文档](https://pyinstaller.org/en/stable/runtime-information.html)。
