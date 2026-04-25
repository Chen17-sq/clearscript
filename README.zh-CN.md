# clearscript

> 本地优先的 ASR 逐字稿整理工具，自带可复利的术语知识库。任意模型即插即用。

[English](./README.md) · [路线图](./docs/ROADMAP.md) · [架构](./docs/architecture.md) · [设计系统](./docs/DESIGN_SYSTEM.md)

**clearscript** 把各种 ASR 工具（飞书妙记 / Typeless / PLAUD / 腾讯会议 / 通义听悟 / 元宝 / 通用 `.txt`/`.srt`/`.vtt`/`.json` 等等）的原始输出，整理成档案级、可分享的逐字稿。它是 **local-first** 的——转录稿和术语库始终留在你的本机；同时是 **模型无关** 的——Claude、GPT、Gemini、DeepSeek、Qwen、Ollama、llama.cpp、自部署 endpoint（包括 Google Colab 隧道），都能接进来。

本项目是某个用了上百次 VC ref check / 创始人访谈 / 投决会 / 播客录音整理的个人 Claude skill 的开源继任版本。

---

## 为什么需要 clearscript

现存的逐字稿整理工具基本只有两种：

- **云端 SaaS**（Otter、Rev、Sonix）：音频和文字都被上传，由闭源模型处理，存在别人的服务器上。隐私只是一个 checkbox，不是架构层面的承诺。
- **通用 LLM 对话**（直接粘进 ChatGPT）：每次都从零开始，模型不记得你的说话人、不熟悉你这行的术语、也不知道你已经手工修了几百遍的固定错误。

clearscript 是第三条路：

| | 云 SaaS | 通用 LLM | clearscript |
|---|---|---|---|
| 数据留在本地 | ✗ | ✗ | ✓ |
| 自带模型 | ✗ | ✗ | ✓ |
| 可离线（接本地模型时） | ✗ | ✗ | ✓ |
| 术语库可复利成长 | ✗ | ✗ | ✓ |
| 全程可审计、可回滚 | ✗ | ✗ | ✓ |
| 多格式输入输出 | 部分 | ✗ | ✓ |

---

## 项目状态

**v0.0.1 — pre-alpha**。仓库已搭好整体架构，跑通最小 happy path（`txt` 输入 → Claude → `md` 输出）。完整 v0.1 计划见 [ROADMAP.md](./docs/ROADMAP.md)。

---

## 核心理念

### 1. Local-first

- 所有转录稿、项目数据、知识库都在你本机硬盘上
- 无强制注册、无 telemetry、无云端依赖
- 唯一的网络调用是你授权的那次 LLM 请求
- 项目格式是开放的（Markdown + SQLite + JSON），数据永远归你

### 2. 自带模型（BYOM）

一份 `providers.toml` 让你按需混搭：

```toml
default_provider = "claude"

[providers.claude]
type = "anthropic"
api_key_env = "ANTHROPIC_API_KEY"

[providers.deepseek]
type = "openai-compat"
base_url = "https://api.deepseek.com/v1"
api_key_env = "DEEPSEEK_API_KEY"

[providers.local]
type = "ollama"
base_url = "http://localhost:11434"

[providers.colab]
type = "openai-compat"
base_url = "https://abc-123.ngrok.io/v1"
```

不同 stage 可以指派不同模型：便宜的做预处理，旗舰款负责重活。

### 3. 复利成长的术语知识库

每次跑一次都在喂养本地 SQLite 知识库：术语 / 说话人 / 公司 / 编辑偏好 / 负面规则。下次开 session 自动按上下文加载相关子集，**用得越多越准**。同时同步导出 markdown 视图，可读、可 git。

### 4. 分层、可审计的编辑

编辑分明确的命名层进行（说话人归一 → 头尾裁剪 → ASR 错误修正 → 句子级重建 → 信息保全 → 对话格式化 → 标点统一）。每一处改动都记录 `{原文, 新文, 原因, 来源, 置信度}`，可 review、可回滚、可阻止模型走偏。

---

## 快速开始

> 需要 Python 3.11+ 和 [uv](https://docs.astral.sh/uv/)。

```bash
git clone https://github.com/Chensiqi17/clearscript.git
cd clearscript
uv sync
export ANTHROPIC_API_KEY=sk-ant-...
uv run clearscript run examples/01-basic-cleanup/input.txt --provider claude
```

整理后的稿子写在原文件旁边：`input.cleaned.md`。

---

## 支持的输入格式（v0.1 目标）

| 格式 | 说明 |
|---|---|
| `.txt` | 通用，自动识别说话人 label |
| `.md` | 自动检测 AI 摘要并剥离 |
| `.docx` | 通用 + 飞书妙记专用解析 |
| `.srt` / `.vtt` | 字幕格式，含时间戳 |
| `.json` | PLAUD、常见 ASR API |
| `.html` | 飞书妙记网页导出 |
| `.lrc` | 类歌词时间戳格式 |
| 通义听悟 | 阿里转录工具导出 |
| 腾讯会议 | 会议纪要导出 |
| 元宝 | 腾讯 AI 助手导出 |
| Typeless | 含 AI 摘要剥离 |

---

## 支持的模型 provider（v0.1 目标）

5 个 adapter 覆盖 20+ 服务：

- **`anthropic`** —— Claude 系列
- **`openai`** —— GPT 系列
- **`openai-compat`** —— DeepSeek、Moonshot/Kimi、通义、Together、Groq、Fireworks、Mistral、OpenRouter、Perplexity、智谱、百川、MiniMax、阶跃、零一万物、Cohere、Cerebras、SambaNova、火山方舟、阿里百炼、SiliconFlow、自定义 endpoint
- **`google`** —— Gemini 系列
- **`ollama`** —— 本地模型，也覆盖 llama.cpp server / LM Studio (通过 OpenAI-compat 模式)

---

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
│   └── prompts/             # LLM prompt 模板
├── web/                     # SvelteKit web UI（v0.1 起）
├── tests/                   # pytest 测试
├── docs/                    # MkDocs 文档源
└── examples/                # 虚构的 before/after 样例
```

---

## 贡献

欢迎提 issue 和 PR，详见 [CONTRIBUTING.md](./CONTRIBUTING.md)。特别容易上手的方向：

- **新增 ASR 格式 adapter**：为我们还没支持的工具写一个 parser
- **贡献 domain pack**（v0.3 后开放）：行业专属术语包
- **提交 ASR 错误模式**：开 issue 提交 `ASR 原文 → 正确` 词条

---

## License

[MIT](./LICENSE)
