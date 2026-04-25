<!-- markdownlint-disable MD033 MD041 -->

<p align="center">
  <img src="./docs/assets/banner.svg" alt="clearscript — 本地优先的 ASR 逐字稿整理工具" width="100%">
</p>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/协议-MIT-D02020?style=for-the-badge&labelColor=121212" alt="MIT License"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/PYTHON-3.11+-1040C0?style=for-the-badge&labelColor=121212" alt="Python 3.11+"></a>
  <a href="https://github.com/Chen17-sq/clearscript/releases"><img src="https://img.shields.io/badge/版本-0.0.1-F0C020?style=for-the-badge&labelColor=121212" alt="v0.0.1"></a>
  <a href="https://github.com/Chen17-sq/clearscript/actions/workflows/ci.yml"><img src="https://img.shields.io/github/actions/workflow/status/Chen17-sq/clearscript/ci.yml?branch=main&style=for-the-badge&labelColor=121212&color=121212&label=CI" alt="CI"></a>
  <a href="./README.md"><img src="https://img.shields.io/badge/English-FFFFFF?style=for-the-badge&labelColor=121212" alt="English"></a>
</p>

<p align="center">
  <b>本地优先</b>  ·  <b>自带模型</b>  ·  <b>复利成长术语库</b>
</p>

<hr>

## 这是什么

**clearscript** 把各种 ASR 工具的原始输出，整理成档案级、可分享的逐字稿。运行在你本机、用你选的模型、每次跑都更准。

它是某个用了上百次 VC ref check / 创始人访谈 / 投决会 / 播客录音整理的个人 Claude skill 的开源继任版本。

<table>
<tr>
<td width="33%" valign="top">

### 🟥 &nbsp;本地优先

转录稿和术语库都在你本机硬盘上。无强制注册、无 telemetry、无云端依赖。唯一的网络调用，就是你授权的那次 LLM 请求。

</td>
<td width="33%" valign="top">

### 🟦 &nbsp;自带模型

5 个 adapter 覆盖 **20+ 服务**：Anthropic · OpenAI · DeepSeek · Moonshot · 通义 · Together · Groq · Fireworks · Mistral · OpenRouter · Gemini · Ollama · llama.cpp · LM Studio · 自定义 endpoint（含 Colab 隧道）。

</td>
<td width="33%" valign="top">

### 🟨 &nbsp;复利成长术语库

本地 SQLite 知识库：术语 / 说话人 / 编辑偏好，跑一次长一次。下次开 session 自动按上下文加载相关子集。同步导出 markdown 视图，可读、可 git。

</td>
</tr>
</table>

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## 为什么需要它

现存的逐字稿整理工具基本只有两种：

- **云端 SaaS**（Otter、Rev、Sonix）：音频和文字都被上传，由闭源模型处理，存在别人的服务器上。隐私只是 checkbox，不是架构。
- **通用 LLM 对话**（直接粘进 ChatGPT）：每次都从零开始，模型不记得你的说话人、不熟悉你这行的术语、也不知道你已经手工修了几百遍的固定错误。

clearscript 是第三条路：

<table>
<thead>
<tr>
  <th></th>
  <th align="center">云 SaaS</th>
  <th align="center">通用 LLM</th>
  <th align="center"><b>clearscript</b></th>
</tr>
</thead>
<tbody>
<tr><td>数据留在本地</td><td align="center">✗</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
<tr><td>自带模型</td><td align="center">✗</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
<tr><td>可离线（接本地模型时）</td><td align="center">✗</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
<tr><td>术语库可复利成长</td><td align="center">✗</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
<tr><td>全程可审计、可回滚</td><td align="center">✗</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
<tr><td>多格式输入输出</td><td align="center">部分</td><td align="center">✗</td><td align="center"><b>✓</b></td></tr>
</tbody>
</table>

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## 快速开始

> 需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/Chen17-sq/clearscript.git
cd clearscript
uv sync
export ANTHROPIC_API_KEY=sk-ant-...   # 或 DEEPSEEK_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY
```

### 方式一 —— Web UI（推荐）

```bash
uv run clearscript serve
```

自动打开 **http://127.0.0.1:7681**。Bauhaus 风格单页界面：选 provider，贴稿子或拖文件，点"Clean transcript"，下载 `.md` / `.docx`。

### 方式二 —— CLI

```bash
uv run clearscript run examples/01-basic-cleanup/input.txt --provider claude
```

整理后的稿子写在原文件旁边：`input.cleaned.md`，附带 JSON change log。

想用别的模型？

```bash
# OpenAI-compatible (DeepSeek / Moonshot / 通义 / Together / Groq / Fireworks / OpenRouter / ...)
export DEEPSEEK_API_KEY=sk-...
uv run clearscript run input.txt --provider deepseek

# 100% 本地 (Ollama / llama.cpp server / LM Studio)
uv run clearscript run input.txt --provider ollama --model qwen2.5:14b
```

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## 项目状态

> **v0.0.1 — pre-alpha**。仓库已搭好整体架构，跑通最小 happy path（`txt` 输入 → LLM → `md`/`docx` 输出）。完整 v0.1 计划见 [路线图](./docs/ROADMAP.md)。

<table>
<tr>
<td width="50%" valign="top">

### v0.0.1 已 ship

- 5 个 LLM provider adapter（覆盖 20+ 服务）
- `.txt` ingest（含说话人启发式）
- SQLite 库: terms / aliases / speakers / patterns / sessions / negatives + FTS5
- 单趟 pipeline（ingest → LLM → md/docx + JSON changelog）
- CLI: `run` · `providers` · `lib stats / add-term / lookup`
- 内置 prompt 库（system + 7 个 stage + 7 个 layer 规格）
- 支持 `~/.config/clearscript/prompts/` 用户覆盖
- 双语文档、MIT 协议、完整的 GitHub 模板
- 27 个单测，CI 跑 macOS + Linux + Windows × Py 3.11/3.12/3.13

</td>
<td width="50%" valign="top">

### v0.1 即将发布

- 12 种 ASR 输入格式（飞书妙记、Typeless、通义听悟、腾讯会议、元宝、PLAUD、SRT、VTT、JSON、HTML、LRC 等）
- 完整 pipeline 分解（pre-scan → context briefing → chunking → self-review → batch-ask → re-scan）
- L3.5 句子级推理层
- SvelteKit web UI，应用 [Bauhaus 设计系统](./docs/DESIGN_SYSTEM.md)
- 术语库 Mode A（项目起始激活）+ Mode C（in-flight 学习）
- PyInstaller 打包桌面安装包（.app · .exe · .AppImage）
- MkDocs Material 文档站，自动部署到 GitHub Pages

</td>
</tr>
</table>

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## 设计原则（不可妥协）

这几条约束每一个功能决定：

- 🟥 &nbsp;**绝不上 telemetry。** 永远不上。不是 opt-in，不是匿名，不是"只是用来分析崩溃"。
- 🟦 &nbsp;**绝不在你授权的 LLM 请求之外发任何网络请求。**
- 🟨 &nbsp;**绝不用私有数据格式。** Markdown / SQLite / JSON——永远可以脱离 clearscript 读出来。
- ⬛ &nbsp;**绝不假设有云服务可用。** 任何需要注册账号的功能都是默认关闭的可选项。

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## 项目结构

```
clearscript/
├── src/clearscript/         # Python 包
│   ├── core/                # Pipeline 编排
│   ├── ingest/              # ASR 格式 parser
│   ├── providers/           # LLM provider adapter
│   ├── library/             # 术语知识库
│   ├── layers/              # 编辑层 (L1-L6 + L3.5 + Self-review)
│   ├── export/              # 输出格式化
│   ├── storage/             # 项目文件布局
│   └── prompts/             # LLM prompt 模板 (markdown, 用户可覆盖)
├── web/                     # SvelteKit web UI (v0.1 起)
├── tests/                   # pytest 测试
├── docs/                    # MkDocs 文档源 + 设计系统 + 资源
└── examples/                # 虚构的 before/after 样例
```

完整 pipeline 契约见 [`docs/architecture.md`](./docs/architecture.md)。

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

## 贡献

欢迎 issue 和 PR，详见 [`CONTRIBUTING.md`](./CONTRIBUTING.md)。容易上手的方向：

- **新增 ASR 格式 adapter**：为我们还没支持的工具写一个 parser
- **提交 ASR 错误模式**：开 issue 提交 `ASR 原文 → 正确` 词条
- **测试新 provider**：试一个我们还没 smoke-test 过的 provider，反馈一下
- **贡献 domain pack**（v0.3 后开放）：行业专属术语包

<p align="center"><img src="./docs/assets/divider.svg" alt="" width="100%"></p>

<p align="center">
  <img src="./docs/assets/logo.svg" alt="clearscript logo" width="80">
</p>
<p align="center"><sub><b>clearscript</b> · 基于 <a href="./LICENSE">MIT 协议</a>开源 · Built for people who care about their transcripts</sub></p>
