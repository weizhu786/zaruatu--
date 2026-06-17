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
