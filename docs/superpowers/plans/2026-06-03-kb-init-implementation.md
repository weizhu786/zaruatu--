# 黑伞专利侵权审核知识库初始化 — 实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 基于 LLM.md 模式文档，初始化黑伞专利侵权审核知识库的三层架构（原始资料层、Wiki 知识库层、Schema 配置层）

**Architecture:** 三层结构：`raw/`（不可变原始资料）、`wiki/`（LLM 维护的可变知识库，含 entities/concepts/sources/synthesis 子目录）、`CLAUDE.md`（LLM 操作规范）。附加 `wiki/index.md`（内容索引）、`wiki/log.md`（操作日志）、`wiki/overview.md`（领域总览）。

**Tech Stack:** Obsidian (Markdown + YAML frontmatter)、Dataview 兼容格式

---

### Task 1: 创建目录结构

**Files:**
- Create: `raw/` 目录
- Create: `wiki/` 目录及其子目录 `wiki/entities/`、`wiki/concepts/`、`wiki/sources/`、`wiki/synthesis/`
- Note: `.gitkeep` 文件确保空目录被 git 跟踪（后续可选）

- [ ] **Step 1: 创建所有目录**

```bash
mkdir -p "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\raw"
mkdir -p "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki\entities"
mkdir -p "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki\concepts"
mkdir -p "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki\sources"
mkdir -p "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki\synthesis"
```

- [ ] **Step 2: 验证目录创建成功**

```bash
find "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库" -type d -not -path "*/.claude/*" -not -path "*/.claudian/*" -not -path "*/.obsidian/*" | sort
```

预期输出（目录存在）：
```
D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库
D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\docs
D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\docs\superpowers
D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\docs\superpowers\specs
D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\docs\superpowers\plans
D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\raw
D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki
D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki\concepts
D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki\entities
D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki\sources
D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki\synthesis
```

---

### Task 2: 创建 CLAUDE.md（Schema 配置文件）

**Files:**
- Create: `CLAUDE.md` — 告诉 LLM 如何维护 Wiki 的核心规范文件

- [ ] **Step 1: 写入 CLAUDE.md**

```markdown
# 黑伞专利侵权审核知识库 — 操作规范

本文档是 Schema 层配置，指导 LLM 如何维护本知识库。

## 目录结构

```
raw/                      # 原始资料（不可变，只读）
  └── 用户放入原始文档，LLM 读取但不修改
wiki/                     # LLM 维护的知识库
  ├── index.md            # 内容索引（LLM 维护）
  ├── log.md              # 操作日志（LLM 追加）
  ├── overview.md         # 领域总览
  ├── entities/           # 实体页：专利、公司、产品、人物
  ├── concepts/           # 概念页：法律概念、技术概念
  ├── sources/            # 资料来源摘要
  └── synthesis/          # 综合分析/对比/问答页
```

## 页面模板

所有 Wiki 页面使用统一 frontmatter 格式：

```yaml
---
type: entity | concept | source | synthesis
title: 页面标题
tags: [标签1, 标签2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: ["[[raw/xxx.md]]"]
aliases: [别名1]
---
```

正文使用标准 Markdown。

## 命名规范

| 页面类型 | 格式 | 示例 |
|---------|------|------|
| 实体页 | `实体名称.md` | `华为技术有限公司.md` |
| 概念页 | `概念名称.md` | `等同原则.md` |
| 来源摘要 | `YYYY-MM-DD-简短描述.md` | `2026-05-10-最高院专利侵权判例.md` |
| 综合页 | 主题名.md | `华为vs三星专利对比分析.md` |

## 工作流

### Ingest（收录资料）

当用户将新资料放入 `raw/` 并通知你时：

1. 读取 `raw/` 中的新资料，理解内容
2. 与用户讨论要点和关注方向
3. 在 `wiki/sources/` 创建摘要页面
4. 更新或创建相关的 `wiki/entities/` 和 `wiki/concepts/` 页面
5. 如果发现关联或矛盾，在 `wiki/synthesis/` 中添加分析
6. 更新 `wiki/index.md` 添加新页面条目
7. 追加 `wiki/log.md` 记录本次操作

### Query（问答查询）

当用户提问时：

1. 读取 `wiki/index.md` 定位相关页面
2. 读取具体页面获取详细信息
3. 综合答案（可生成 Markdown 表格、列表等格式）
4. 如果答案有长期价值，存入 `wiki/synthesis/` 并更新索引
5. 追加 `wiki/log.md` 记录本次查询

### Lint（健康检查）

当用户要求检查时：

1. 审查页面间的矛盾和陈旧断言
2. 识别孤儿页（无入链页面）
3. 发现缺少交叉引用的页面
4. 建议新的探索方向和资料来源
5. 追加 `wiki/log.md` 记录检查结果

## 链接规范

- 页面间引用使用 `[[wiki/路径/页面名]]` 格式
- 引用原始资料使用 `[[raw/文件名]]` 格式
- 同义词/别名记录在 frontmatter 的 `aliases` 字段

## Dataview 兼容

所有页面 frontmatter 包含 `type`、`tags`、`created`、`updated` 字段，支持 Dataview 查询。
```

- [ ] **Step 2: 验证文件创建成功**

```bash
ls -la "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\CLAUDE.md"
```

预期输出：`CLAUDE.md` 存在且非空

---

### Task 3: 创建 raw/README.md（原始资料目录说明）

**Files:**
- Create: `raw/README.md` — 告诉用户如何使用原始资料目录

- [ ] **Step 1: 写入 raw/README.md**

```markdown
# 原始资料目录 (Raw Sources)

本目录存放所有原始资料，**不可变、只读**。LLM 读取本目录内容来构建和更新 Wiki 知识库，但从不修改这里的文件。

## 使用方法

1. **获取资料**：通过 Obsidian Web Clipper、手动保存、导出等方式获取原始文档
2. **转为 Markdown**：确保文件为 `.md` 格式（PDF/网页 → 粘贴转 MD）
3. **下载图片**（可选）：在 Obsidian 设置中配置附件路径为 `raw/assets/`，使用热键下载图片到本地
4. **放入 raw/**：将文件放入本目录或按分类建子目录
5. **通知 LLM**：告诉 LLM 有新资料需要 Ingest

## 规范

- 文件名格式：`YYYY-MM-DD-简短描述.md`
- 保留原文完整内容，不做删减
- 如有图片存入 `raw/assets/`，使用 `![[raw/assets/xxx.png]]` 引用
- 可从 `raw/assets/` 使用 `![[xxx.png]]` 在 wiki 页面引用图片（注：LLM 需要先读文本再看图片）

## 子目录建议

- `articles/` — 文章和报道
- `cases/` — 法院判例和判决书
- `patents/` — 专利文档
- `laws/` — 法律法规
- `assets/` — 图片等附件

> 子目录是可选的，按需创建。核心原则是文件放入 raw/ 后不再修改。
```

- [ ] **Step 2: 验证文件创建成功**

```bash
ls -la "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\raw\README.md"
```

---

### Task 4: 创建 wiki/index.md（内容索引）

**Files:**
- Create: `wiki/index.md` — 知识库的目录索引，初始展示空库状态

- [ ] **Step 1: 写入 wiki/index.md**

```markdown
---
type: index
title: 知识库索引
created: 2026-06-03
updated: 2026-06-03
---

# 黑伞专利侵权审核知识库索引

> 最后更新：2026-06-03
> 总计：0 个页面（初始化阶段）

## 实体 (Entities)

*暂无 — 请收录资料后由 LLM 生成*

## 概念 (Concepts)

*暂无 — 请收录资料后由 LLM 生成*

## 资料来源 (Sources)

*暂无 — 请收录资料后由 LLM 生成*

## 综合分析 (Synthesis)

*暂无 — 请收录资料后由 LLM 生成*
```

- [ ] **Step 2: 验证文件创建成功**

```bash
ls -la "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki\index.md"
```

---

### Task 5: 创建 wiki/log.md（操作日志）

**Files:**
- Create: `wiki/log.md` — 按时间顺序记录所有操作

- [ ] **Step 1: 写入 wiki/log.md**

```markdown
---
type: log
title: 操作日志
created: 2026-06-03
updated: 2026-06-03
---

# 操作日志

## [2026-06-03] init | 知识库初始化

- 基于 LLM.md 模式初始化知识库结构
- 创建 raw/ 原始资料目录
- 创建 wiki/ 知识库目录（含 entities/concepts/sources/synthesis 子目录）
- 创建 CLAUDE.md Schema 配置文件
- 创建 wiki/index.md 内容索引
- 创建 wiki/log.md 操作日志
- 创建 wiki/overview.md 领域总览页
```

- [ ] **Step 2: 验证文件创建成功**

```bash
ls -la "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki\log.md"
```

---

### Task 6: 创建 wiki/overview.md（领域总览）

**Files:**
- Create: `wiki/overview.md` — 知识库范围和主题的总览页面

- [ ] **Step 1: 写入 wiki/overview.md**

```markdown
---
type: synthesis
title: 黑伞专利侵权审核知识库总览
tags: [专利, 侵权, 知识产权, 审核]
created: 2026-06-03
updated: 2026-06-03
aliases: [知识库总览, 领域概览]
---

# 黑伞专利侵权审核知识库总览

## 目标

本知识库系统性地收集、整理和分析与**专利侵权审核**相关的知识资源，包括法律法规、判例分析、技术标准和实务指南。

## 范围

### 核心主题

- **专利侵权判定原则**：全面覆盖原则、等同原则、禁止反悔原则、捐献原则等
- **专利有效性分析**：新颖性、创造性、实用性审查
- **侵权抗辩事由**：现有技术抗辩、合法来源抗辩、不侵权抗辩等
- **损害赔偿计算**：实际损失、许可费、法定赔偿等
- **诉讼程序**：管辖、证据规则、保全措施、禁令等
- **国际比较**：中国专利法、美国专利法、欧洲专利公约等

### 资料类型

- 法律法规及司法解释
- 法院判例（最高院指导案例、典型案例）
- 学术论文和研究报告
- 实务操作指南
- 技术标准和行业规范

## 当前状态

- 初始化日期：2026-06-03
- 实体页：0
- 概念页：0
- 资料来源：0
- 综合分析：0

> 开始使用：将原始资料放入 `raw/` 目录，然后通知 LLM 进行 Ingest。

## 相关链接

- [[wiki/index.md|知识库索引]]
- [[wiki/log.md|操作日志]]
```

- [ ] **Step 2: 验证文件创建成功**

```bash
ls -la "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库\wiki\overview.md"
```

---

### Task 7: 最终验证

**Files:** 检查所有已创建的文件

- [ ] **Step 1: 验证完整目录结构**

```bash
echo "=== 目录结构 ==="
find "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库" -type d -not -path "*/.claude/*" -not -path "*/.claudian/*" -not -path "*/.obsidian/*" -not -path "*/docs/*" | sort
echo ""
echo "=== 新创建的 Wiki 文件 ==="
find "D:\黑伞专利侵权审核知识库\黑伞专利侵权审核知识库" -maxdepth 1 -name "CLAUDE.md" -o -path "*/raw/*.md" -o -path "*/wiki/*.md" | sort
```

预期输出包含所有创建的目录和文件。
