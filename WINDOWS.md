# 佛典研究工作台 · Windows 桌面版（0.3）

适用 Windows 10 / 11，64 位。不需要另装 Python。

## 安装

1. 在 [Releases 页面](https://github.com/mofashikaoke/buddhist-text-lab/releases/latest)下载 `BuddhistTextLab-Setup-*.exe`（附 `SHA256SUMS.txt` 可校验）。
2. 双击安装程序，按向导完成安装（默认装到 `C:\Program Files\BuddhistTextLab`，可在开始菜单找到，可选创建桌面快捷方式）。
3. 从开始菜单启动“佛典研究工作台”。启动窗口会自动打开默认浏览器中的研究界面。
4. 保持启动窗口打开；点击窗口的关闭按钮即可退出服务。
5. 在右上角“设置”中填写 API 基础地址、模型名和 API Key，点击“保存设置”。
6. 点击“测试连接”，确认接口可用；测试会发送简短请求，按所用服务商规则计费。
7. 在左侧“来源”导入典籍、检索原文，点“加入对话”选定依据，在中间栏提问；右侧可对照原文、记笔记、做结构化分析。

API 基础地址示例：`https://api.openai.com/v1`。其他兼容服务填写其官方文档指定的基础地址。模型名使用你账号可用的模型 ID，不填写网页产品名称。输出参数默认 `max_completion_tokens`，部分兼容接口需改用 `max_tokens`。

软件不附赠 API 额度或密钥，ChatGPT 网页订阅不能代替 API Key。不配置 AI 也能使用检索、对照与笔记功能。

如需免安装版本，可下载 portable ZIP，解压后直接运行其中的 `BuddhistTextLab.exe`。

## 卸载

在 Windows“设置 → 应用”中找到“佛典研究工作台”卸载，或从开始菜单选择“卸载佛典研究工作台”。卸载不会删除 `%LOCALAPPDATA%\BuddhistTextLab` 中的研究数据；如需彻底清除请手动删除该目录。

## 数据与密钥

- 数据目录：`%LOCALAPPDATA%\BuddhistTextLab`，启动窗口显示完整路径。
- 典籍、对话与笔记：`research.sqlite3`。退出程序后备份该文件；AI 对话与分析记录也存放于其中。
- 配置：`ai-settings.json`。勾选保存密钥时使用 Windows DPAPI 加密，仅供当前 Windows 账号解密；未勾选则密钥只保存在进程内存。
- 更换 API 地址后需重新填写密钥，旧密钥不会自动发给新地址。
- 只有主动发起对话或分析时，所选原文、元数据和问题才会发送至配置接口。原文件与其他典籍不发送。
- AI 结果保留原文快照与模型信息，引用编号检查不等于证明引文与结论正确。
- 程序未做商业代码签名，发布包附有 SHA-256 校验文件。

## 从 0.2 迁移

退出旧服务及 EXE，将旧数据目录（0.2 为 `%LOCALAPPDATA%\BuddhistTextLab`，源码版为项目 `data` 目录）中的 `research.sqlite3` 复制到新数据目录（先备份已有数据库，再决定是否覆盖）。启动新版会自动创建对话记录表，原有书目、笔记与分析记录保留。

## 技术形式

安装程序用 Inno Setup 制作，内含 PyInstaller 打包的 Python 运行环境、PDF 解析库和网页资源。启动器是 Windows 原生窗口，主要研究界面使用系统默认浏览器，在本机回环地址运行。它不是公网网站，也不是内嵌 Chromium 安装包。
