# SelfOS

**Your personal operating system — structured memory + AI collaboration, works with any LLM.**

SelfOS is an open framework for building a personal knowledge and memory system that AI agents can read, update, and reason over. Think of it as the OS layer between you and your AI assistant — your second brain that persists across every conversation.

> "An AI that remembers nothing about you is a stranger. SelfOS turns it into a collaborator."

**[中文文档 →](#chinese)**

---

## What is this?

Most AI assistants forget you the moment the session ends. SelfOS fixes that by giving your AI a structured, version-controlled knowledge base about your life — your goals, career, health, research, decisions, and context.

- **Git-native**: everything is Markdown + Git. Your life has version history.
- **AI-agnostic**: works with Claude Code, Codex, or any agent that can read files.
- **Privacy-first**: runs entirely on your local machine. No cloud, no database.
- **Structured but flexible**: opinionated enough to be useful out of the box, open enough to adapt to your life.

---

## How it works

```
You ──→ AI Agent ──→ reads vault/ ──→ understands your context
                  ──→ proposes changes to 91_Staging/
                  ──→ you approve
                  ──→ applies to canonical files
                  ──→ commits to Git
```

The vault is a directory of Markdown files organized by life domain. The AI reads these files at the start of each session and maintains them over time. The staging workflow ensures nothing is written without your approval.

---

## Vault structure

```
vault/
├── PROFILE.md          # Who you are — identity, background, skills
├── NOW.md              # Current state — priorities, active projects, blockers
├── GOALS.md            # Short and long-term goals
├── DECISIONS.md        # Append-only decision log
│
├── 01_Career/          # Career history, opportunities, criteria
├── 02_Work/            # Active work projects and logs
├── 03_Research/        # Research projects, experiments, papers
├── 04_Health_Fitness/  # Training plans, logs, health data
├── 05_Life/            # Learning, relationships, housing, side projects
├── 06_Reviews/         # Weekly and monthly reviews
├── 07_World_Observer/  # External signals, market intelligence, reading
│
├── 90_Inbox/           # Raw input (git-ignored, treated as sensitive)
├── 91_Staging/         # Proposed changes awaiting approval
├── 98_Archive/         # Historical records
└── 99_Templates/       # Reusable templates
```

---

## Memory system

SelfOS includes a persistent memory layer for AI agents — a set of structured Markdown files the agent reads at session start to recall who you are, your preferences, and your ongoing work.

```
memory/
├── MEMORY.md           # Index of all memory files
├── user-profile.md     # Background, role, goals, preferences
├── feedback.md         # How you like to work with AI
└── project-context.md  # Current project state
```

Memory files use a simple frontmatter schema:

```yaml
---
name: user-profile
description: Background, role, and preferences — read before any advice
metadata:
  type: user  # user | feedback | project | reference
---
```

---

## Getting started

### Step 1 — Clone

```bash
git clone https://github.com/Liam-coding/SelfOS.git
cd SelfOS
```

### Step 2 — Bootstrap from your AI conversation history

```bash
python bootstrap.py
```

That's it. The script finds your Claude Code and Codex sessions automatically, extracts your messages, filters sensitive data, and writes a digest to `vault/90_Inbox/`.

**Limit to recent sessions:**
```bash
python bootstrap.py --days 90
```

Then tell your AI agent:

> "Read vault/90_Inbox/YYYY-MM-DD-sessions-digest.md and distribute insights to vault modules."

The AI reads the digest and writes one staging file per vault module — career, work, research, goals, decisions — for your review before anything is committed.

**What gets extracted:** your messages across all Claude Code and Codex sessions, grouped by project, sorted by recency.

**What gets filtered:** AI replies, API keys, tokens, passwords, emails, system notifications, one-word acks.

**Privacy:** `vault/90_Inbox/` is git-ignored. Session content never leaves your machine.

### Step 3 — Fill in the blanks

Open `vault/PROFILE.md` and `vault/NOW.md`. These are the two files your AI reads most. Fill in what bootstrap couldn't infer — your goals, current priorities, role.

### Step 4 — Install the `/digest` skill (Claude Code only)

Copy the skill into your Claude Code skills directory:

```bash
# macOS / Linux
cp -r .claude/skills/digest ~/.claude/skills/

# Windows
xcopy /E /I .claude\skills\digest %USERPROFILE%\.claude\skills\digest
```

From now on, after running `python bootstrap.py`, just type `/digest` in Claude Code — it will read your latest digest and distribute insights to the vault automatically.

### Step 5 — Start your first session

```bash
cd SelfOS/
python bootstrap.py    # extract your AI conversation history
claude                 # open Claude Code
```

Then type:

```
/digest
```

Claude reads your sessions, proposes updates to each vault module, and waits for your approval before writing anything.

---

## The staging workflow

SelfOS enforces a strict **propose → approve → apply → commit** cycle. Your AI never writes directly to canonical vault files.

```
1. You give the AI information or ask it to update something
2. AI writes a proposal to vault/91_Staging/YYYY-MM-DD-topic.md
3. You review: "looks good" / "apply" / "change X first"
4. AI applies to canonical files and commits to Git
```

This means every change to your vault is something you consciously approved.

---

## Information classification

Every claim in the vault is labeled so you always know how confident to be:

| Label | Meaning |
|-------|---------|
| `confirmed` | You stated it directly, with a source and date |
| `hypothesis` | Unverified — clearly labeled, not treated as fact |
| `ai-inference` | AI interpretation — never promoted to confirmed |
| `historical-decision` | A past choice, preserved even if later superseded |
| `time-series` | Dated measurements (weight, test scores, etc.) |

---

## Supported AI agents

| Agent | Status | Setup |
|-------|--------|-------|
| Claude Code | ✅ Native | Open Claude Code in `vault/` — `CLAUDE.md` auto-loads |
| OpenAI Codex | ✅ Supported | Add system prompt from Step 4 above |
| Any file-reading agent | ✅ Compatible | Point at `PROFILE.md` + `memory/` + `CLAUDE.md` |

See [`docs/agent-integration.md`](docs/agent-integration.md) for detailed setup per agent.

---

## Philosophy

Your AI assistant should know you — not just what you said in the last message, but who you are, what you're working toward, and how you think. SelfOS is the infrastructure layer that makes that possible.

Today it's a pattern. The goal is for it to become the standard OS layer between every person and their AI — a personal context layer that travels with you, works with any agent, and compounds over time. Fork it, build on it, help shape what it becomes.

---

## Contributing

PRs welcome. If you adapt SelfOS to a new AI agent or workflow, open a PR to add it to the supported agents table.

---

## Author

**Liam (Jialei Liu)**
- GitHub: [@Liam-coding](https://github.com/Liam-coding)
- Email: jialei.liu.sh@gmail.com

---

<a name="chinese"></a>

---

# SelfOS — 中文文档

**你的个人操作系统 — 结构化记忆 + AI 协作，支持任意大模型。**

SelfOS 是一个开源框架，用于构建 AI 可读、可更新、可推理的个人知识与记忆系统。把它理解为你和 AI 助手之间的 OS 层——一个跨会话持久存在的第二大脑。

> "对你一无所知的 AI 是陌生人。SelfOS 让它成为真正的协作者。"

---

## 这是什么？

大多数 AI 助手在会话结束后就忘记了你。SelfOS 通过给 AI 一个结构化、版本控制的知识库来解决这个问题——包含你的目标、职业、健康、研究、决策和上下文。

- **Git 原生**：一切都是 Markdown + Git，你的人生有版本历史。
- **AI 无关**：支持 Claude Code、Codex 或任何能读文件的 Agent。
- **隐私优先**：完全运行在本地，无云端，无数据库。
- **结构化但灵活**：开箱即用，也可以完全按你的方式定制。

---

## 工作原理

```
你 ──→ AI Agent ──→ 读取 vault/ ──→ 理解你的上下文
                 ──→ 提议变更到 91_Staging/
                 ──→ 你审批
                 ──→ 写入正式文件
                 ──→ Git 提交
```

vault 是一组按生活领域组织的 Markdown 文件。AI 在每次会话开始时读取这些文件，并随时间维护它们。Staging 工作流确保没有你的审批，AI 什么都不会写入。

---

## 快速开始

### 第一步 — 克隆仓库

```bash
git clone https://github.com/Liam-coding/SelfOS.git
cd SelfOS
```

### 第二步 — 从 AI 会话历史 Bootstrap

```bash
python bootstrap.py
```

就这一行。脚本自动找到你的 Claude Code 和 Codex 会话，提取你的消息，过滤敏感信息，将摘要写入 `vault/90_Inbox/`。

**只提取最近一段时间：**
```bash
python bootstrap.py --days 90
```

然后告诉你的 AI：

> "读取 vault/90_Inbox/YYYY-MM-DD-sessions-digest.md，将信息分散到 vault 各模块。"

AI 会读取摘要，按模块（职业、工作、研究、目标、决策）分别写入 staging 文件，等待你审批后再提交。

**会提取什么：** 你在所有 Claude Code 和 Codex 会话中发送的消息，按项目分组，按时间排序。

**会过滤什么：** AI 的回复、API key、token、密码、邮箱、系统通知、单字确认。

**隐私：** `vault/90_Inbox/` 已 git-ignored，会话内容永远不离开你的本地机器。

### 第三步 — 补全空白

打开 `vault/PROFILE.md` 和 `vault/NOW.md`，填入 bootstrap 无法推断的内容——你的目标、当前优先级、职位。

### 第四步 — 安装 `/digest` skill（仅 Claude Code）

将 skill 复制到 Claude Code 的 skills 目录：

```bash
# macOS / Linux
cp -r .claude/skills/digest ~/.claude/skills/

# Windows
xcopy /E /I .claude\skills\digest %USERPROFILE%\.claude\skills\digest
```

之后每次运行 `python bootstrap.py`，只需在 Claude Code 里输入 `/digest`，它会自动读取最新 digest 并将信息分散到 vault 各模块。

### 第五步 — 开始第一次会话

```bash
cd SelfOS/
python bootstrap.py    # 提取 AI 会话历史
claude                 # 打开 Claude Code
```

然后输入：

```
/digest
```

Claude 读取你的会话记录，为每个 vault 模块提出更新建议，等待你审批后再写入。

---

## Staging 工作流

SelfOS 强制执行严格的 **提议 → 审批 → 应用 → 提交** 循环，AI 永远不会直接写入正式 vault 文件。

```
1. 你给 AI 信息，或要求它更新某些内容
2. AI 将提议写入 vault/91_Staging/YYYY-MM-DD-主题.md
3. 你审阅："好的" / "应用" / "先改一下 X"
4. AI 应用到正式文件并 Git 提交
```

这意味着 vault 中的每一处变更都是你主动审批过的。

---

## 信息分类

vault 中的每条信息都有标签，让你始终清楚其可信度：

| 标签 | 含义 |
|------|------|
| `confirmed` | 你直接陈述的，有来源和日期 |
| `hypothesis` | 未验证——明确标注，不作为事实处理 |
| `ai-inference` | AI 的推断——不会被提升为 confirmed |
| `historical-decision` | 过去的决定，即使被覆盖也会保留 |
| `time-series` | 有日期的测量数据（体重、考试成绩等） |

---

## 支持的 AI Agent

| Agent | 状态 | 接入方式 |
|-------|------|---------|
| Claude Code | ✅ 原生支持 | 在 `vault/` 下打开 Claude Code，自动加载 `CLAUDE.md` |
| OpenAI Codex | ✅ 支持 | 按第四步添加系统提示 |
| 任意可读文件的 Agent | ✅ 兼容 | 指向 `PROFILE.md` + `memory/` + `CLAUDE.md` |

详细接入说明见 [`docs/agent-integration.md`](docs/agent-integration.md)。

---

## 哲学

你的 AI 助手应该了解你——不只是你上条消息说了什么，而是你是谁、你在追求什么、你怎么思考。SelfOS 是让这一切成为可能的基础设施层。

现在它是一种模式。目标是让它成为每个人和 AI 之间的标准 OS 层——一个随你迁移、兼容任意 Agent、随时间持续积累的个人上下文层。Fork 它，在上面构建，帮助塑造它的未来。

---

## License

MIT
