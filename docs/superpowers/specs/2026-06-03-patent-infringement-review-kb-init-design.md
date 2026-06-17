# 黑伞专利侵权审核知识库初始化设计

## 概述

基于 `LLM.md` 文档描述的"LLM 增量构建持久化 Wiki 知识库"模式，为"黑伞专利侵权审核知识库" Obsidian Vault 搭建初始化结构。

核心模式：**三层架构**（原始资料层 → Wiki 知识库层 → Schema 配置文件层）+ 索引与日志系统。

## 目录结构

```
黑伞专利侵权审核知识库/
├── CLAUDE.md                  # Schema 层 — LLM 操作规范
├── LLM.md                     # 原始模式文档（不变）
├── raw/                       # 原始资料层 — 不可变，只读
│   └── README.md              # 使用说明
├── wiki/                      # Wiki 层 — LLM 维护的知识库
│   ├── index.md               # 内容目录索引
│   ├── log.md                 # 操作日志
│   ├── overview.md            # 领域总览
│   ├── entities/              # 实体页 — 专利、公司、产品、人物
│   ├── concepts/              # 概念页 — 法律概念、技术概念
│   ├── sources/               # 资料来源摘要
│   └── synthesis/             # 综合/对比/分析页
├── 欢迎.md                    # 原有文件，保留
├── 新obsidian必备.md          # 原有文件，保留
└── 未命名.base                # 原有文件，保留
```

### 各目录职责

| 路径 | 用途 | 维护者 | 不可变 |
|------|------|--------|--------|
| `raw/` | 存放原始资料（文章、判决书、专利文档、法规等转为 MD 后放入） | 用户放入，LLM 读取 | 是 |
| `wiki/entities/` | 每个实体一个文件，如 `华为技术有限公司.md`、`专利CN123456.md` | LLM 创建/更新 | 否 |
| `wiki/concepts/` | 概念页，如 `等同原则.md`、`全面覆盖原则.md`、`创造性.md` | LLM 创建/更新 | 否 |
| `wiki/sources/` | 每份资料的摘要页，标明出处和关键信息 | LLM 创建 | 否 |
| `wiki/synthesis/` | 综合分析：对比、趋势、问答延伸等 | LLM 创建 | 否 |
| `wiki/index.md` | 全库内容索引，按类别列出所有页面 | LLM 维护 | 否 |
| `wiki/log.md` | 时间顺序的操作日志 | LLM 追加 | 否 |

## 页面模板约定

所有 Wiki 页面统一使用 YAML frontmatter + Markdown 正文：

```yaml
---
type: entity | concept | source | synthesis
title: 页面标题
tags: [标签1, 标签2]
created: YYYY-MM-DD
updated: YYYY-MM-DD
sources: ["[[raw/xxx.md]]"]
aliases: [别名1, 别名2]
---
```

支持 Dataview 插件生成动态列表和表格。

## 命名规范

- **实体页**：`实体名称.md`（如 `华为技术有限公司.md`）
- **概念页**：`概念名称.md`（如 `等同原则.md`）
- **来源摘要**：`YYYY-MM-DD-简短描述.md`（如 `2026-05-10-最高院专利侵权判例.md`）
- **综合页**：按主题命名，如 `华为 vs 三星专利对比分析.md`

## CLAUDE.md 内容结构

Schema 文件包含以下部分：

1. **目录结构指引** — 说明各目录用途
2. **页面模板约定** — frontmatter 规范、格式要求
3. **命名规范** — 文件命名规则
4. **三大工作流**：
   - **Ingest**：你放入资料→LLM 阅读→讨论要点→写摘要→更新实体/概念页→更新索引→记日志
   - **Query**：你提问→LLM 查索引→读相关页→综合回答→可存为 synthesis/→更新索引→记日志
   - **Lint**：你要求检查→LLM 审查矛盾/过期/孤儿页→建议新方向
5. **跨引用规则** — 使用 `[[]]` Wiki 链接建立关联
6. **引用规则** — 页面引用 raw/ 中的资料时使用 `[[raw/xxx]]` 格式

## index.md 结构

```markdown
# 黑伞专利侵权审核知识库索引

> 最后更新：YYYY-MM-DD | 总计：N 个页面

## 实体 (Entities)
- [[wiki/entities/xxx]] — 一句话描述

## 概念 (Concepts)
- [[wiki/concepts/xxx]] — 一句话描述

## 资料来源 (Sources)
- [[wiki/sources/xxx]] — 一句话描述

## 综合分析 (Synthesis)
- [[wiki/synthesis/xxx]] — 一句话描述
```

## log.md 结构

每条日志统一格式：
```markdown
## [YYYY-MM-DD] <操作类型> | <标题>
```

操作类型：`init`、`ingest`、`query`、`lint`、`update`

## 初始创建的文件清单

1. `CLAUDE.md` — 完整的 Schema 配置文件
2. `raw/README.md` — 原始资料目录使用说明
3. `wiki/index.md` — 初始索引（空库状态）
4. `wiki/log.md` — 初始日志（记录初始化事件）
5. `wiki/overview.md` — 领域总览页面
