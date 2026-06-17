"""
黑伞专利审核 — 飞书自动化服务

两种使用方式：
  A. 群聊/私聊 @机器人 → 发送产品信息 → 自动审查 → 推送结果
  B. 飞书表单提交 → Webhook → 自动审查 → 推送结果
"""

import os
import re
import json
import time
import logging
import base64
import asyncio
import threading
from typing import Optional
from datetime import datetime

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, HTMLResponse
import uvicorn

load_dotenv()

# ── 日志 ────────────────────────────────────────────
logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
log = logging.getLogger("patent-review")

# ── 配置（从 config.py 导入，避免 railpack 构建时扫描）───
from config import (
    FEISHU_APP_ID, FEISHU_APP_SECRET,
    ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENAI_BASE_URL,
    vision_mode, GEMINI_API_KEY, TAVILY_API_KEY,
)

app = FastAPI(title="黑伞专利审核服务")

# ── 飞书 SDK（轻量版）───────────────────────────────

class FeishuClient:
    """飞书 API 客户端"""
    def __init__(self):
        self._token: Optional[str] = None
        self._expires = 0.0

    async def _get_token(self) -> str:
        if self._token and time.time() < self._expires - 60:
            return self._token
        async with httpx.AsyncClient() as c:
            r = await c.post(
                "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
                json={"app_id": FEISHU_APP_ID, "app_secret": FEISHU_APP_SECRET},
                timeout=10,
            )
            r.raise_for_status()
            data = r.json()
            self._token = data["tenant_access_token"]
            self._expires = time.time() + data.get("expire", 7200)
        return self._token

    async def reply_message(self, msg_id: str, content: str) -> dict:
        """回复消息（群聊/私聊）"""
        token = await self._get_token()
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"https://open.feishu.cn/open-apis/im/v1/messages/{msg_id}/reply",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "content": json.dumps({"text": content}),
                    "msg_type": "text",
                },
                timeout=15,
            )
            r.raise_for_status()
            return r.json()

    async def send_card(self, receive_id: str, receive_type: str, header: str, content: str) -> dict:
        """发送卡片消息"""
        token = await self._get_token()
        async with httpx.AsyncClient() as c:
            r = await c.post(
                f"https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type={receive_type}",
                headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
                json={
                    "receive_id": receive_id,
                    "msg_type": "interactive",
                    "content": json.dumps({
                        "config": {"wide_screen_mode": True},
                        "elements": [{"tag": "markdown", "content": content}],
                        "header": {"title": {"tag": "plain_text", "content": header}}
                    }),
                },
                timeout=15,
            )
            r.raise_for_status()
            return r.json()

    async def download_image(self, image_key: str) -> bytes:
        """下载飞书消息中的图片（image_key 有时效，尽快下载）"""
        token = await self._get_token()
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.get(
                f"https://open.feishu.cn/open-apis/im/v1/images/{image_key}",
                headers={"Authorization": f"Bearer {token}"},
                params={"image_type": "message"},
            )
            if r.status_code == 400:
                # 重试不带 image_type
                r = await c.get(
                    f"https://open.feishu.cn/open-apis/im/v1/images/{image_key}",
                    headers={"Authorization": f"Bearer {token}"},
                )
            r.raise_for_status()
            return r.content

feishu = FeishuClient()

# ── 待审查暂存 ─────────────────────────────────────
pending_reviews: dict = {}  # review_key → form_data
_review_locks: dict = {}    # review_key → timestamp，10分钟内防重复

# ── 文本解析器 ──────────────────────────────────────

def parse_chat_message(text: str) -> Optional[dict]:
    """解析用户发来的产品信息文本，提取结构化字段"""
    # 去掉 @机器人 前缀
    text = re.sub(r'@\S+\s*', '', text).strip()

    # 支持两种格式：
    # 格式1: 键值对
    #   审查新品
    #   编号：888
    #   名称：硅胶杯盖
    #   标题：Silicone Cup Lid for Travel Mugs
    #   市场：US
    #   材质：硅胶
    #   品牌：xxx
    #   五点：...

    data = {}

    # 匹配键值对
    patterns = {
        "总表编号": r'(?:总表编号|编号|code)\s*[:：]\s*(.+)',
        "产品编号": r'(?:总表编号|编号|code)\s*[:：]\s*(.+)',
        "产品名称": r'(?:名称|产品名称|品名)\s*[:：]\s*(.+)',
        "产品标题": r'(?:标题|完整标题|listing.?title)\s*[:：]\s*(.+)',
        "目标市场": r'(?:市场|目标市场|market)\s*[:：]\s*(.+)',
        "材质": r'(?:材质|material)\s*[:：]\s*(.+)',
        "品牌名": r'(?:品牌|brand)\s*[:：]\s*(.+)',
        "五点描述": r'(?:五点|bullet.?points?|描述)\s*[:：]\s*(.+)',
        "亚马逊链接": r'(?:亚马逊.*链接|amazon.*url|产品链接)\s*[:：]\s*(https?://[^\s]+)',
        "ASIN": r'(?:asin)\s*[:：]\s*([A-Z0-9]{10})',
        "参考链接": r'(?:亚马逊.*链接|链接|amazon|url)\s*[:：]\s*(https?://[^\s]+)',
    }

    for field, pattern in patterns.items():
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            data[field] = match.group(1).strip()

    # 如果没有用键值对格式，尝试命令行格式
    #   审查 888 硅胶杯盖 "Silicone Cup Lid" US 硅胶
    if not data.get("产品名称"):
        # 去掉"审查新品""审查"等前缀
        stripped = re.sub(r'^(审查新品|审查|review)\s*', '', text, flags=re.IGNORECASE).strip()
        parts = [p.strip().strip('"\'') for p in re.split(r'\s{2,}|\t|\n', stripped) if p.strip()]
        if len(parts) >= 3:
            data["产品编号"] = data.get("产品编号", parts[0])
            data["产品名称"] = data.get("产品名称", parts[1])
            data["产品标题"] = data.get("产品标题", parts[2])
            if len(parts) >= 4:
                data["目标市场"] = data.get("目标市场", parts[3])
            if len(parts) >= 5:
                data["材质"] = data.get("材质", parts[4])

    # 至少需要名称或编号
    if not data.get("产品名称") and not data.get("产品编号"):
        return None

    return data

# ── AI 审查引擎（v2: 多源检索 + 完整五层框架）────────────────

try:
    from search_engine import (
        run_full_search,
        format_search_results,
        extract_core_keywords,
        extract_patent_ids,
    )
except Exception as _import_err:
    import traceback
    log.critical(f"Failed to import search_engine: {_import_err}")
    log.critical(traceback.format_exc())
    # 降级：定义占位函数
    async def run_full_search(*a, **kw): return {}
    def format_search_results(*a, **kw): return "（检索引擎加载失败）"
    def extract_core_keywords(title): return [title]
    def extract_patent_ids(text): return []

# ── 完整系统提示词（基于 CLAUDE.md 五层框架）─────────────

FULL_SYSTEM_PROMPT = """你是跨境电商专利侵权审查 AI。你必须严格基于提供的「实时搜索数据」进行分析，**绝对禁止编造任何专利号、商标号、案件号**。

## 核心全局规则

### 管辖权优先级
- 目标市场决定查哪个国家的数据库。US → USPTO，CA → CIPO，EU → EUIPO
- 不在目标市场的 IP **不写入报告**
- 例外：版权（伯尔尼公约）、PCT/Hague/马德里国际申请指定了目标市场

### TRO 特别预警
- 🔴TRO = 有执行历史的专利/商标/版权 → 风险自动至少升一级
- Keith 律所代理 → 风险至少 🟡，实质性相似 → 🔴
- 🔴TRO 标记的 IP 结论**不得为 Go**

## 审查框架（五层递进）

### 第一层：产品特征拆解
- 从标题提取核心关键词（1-3 个品类核心词，忽略品牌/形容词/材质/尺寸）
- 判断：是否有印刷图案（触发版权排查）？
- 判断：纯装饰品 or 功能性产品？

### 版权排查层（有印刷图案时执行）
- 搜索 Keith + 图案关键词 + TRO
- 「法律 vs 现实」原则：通用的内容仍可能被登记版权并执行
- 版权侵权 = 实质性相似，标准比设计专利更宽泛
- Keith 律所 → 执行力度极高 → 风险上调

### 第二层：商标排查
- 核心关键词是否被注册为商标（同品类 → 🔴）
- 品牌名 + TRO/lawsuit 查询
- 已知高危商标：Susan G. Komen "running ribbon"、NFL 等

### 第三层：设计专利排查
- 检索目标市场设计专利 → 视觉比对产品图 vs 专利图
- 判断：整体视觉印象是否实质性相同

### 第四层：发明专利排查（功能性产品必须执行）
- 制作 Claim Chart：逐项比对产品特征 vs 权利要求要素
- 适用全面覆盖原则 + 等同原则
- 权利要求的术语可能被宽泛解释 → 专利说明书交叉核查
- 已 TRO 执行的专利 → 风险至少上调一级

### 第五层：市场验证
- AliExpress/1688 同类产品多→设计通用性高（有利）
- worldtro/Justia TRO 案件 → 实际执行力度
- 跨境电商侵权预警 → 动态风险

## 决策矩阵（从严执行）
- 任何一项 🔴 → ❌ No-Go
- 任何一项 🟡 → ⚠️ 需修改设计
- 全部 🟢 → ✅ Go

## 输出格式
使用 emoji + 表格，按五层结构输出。每个专利号必须来自搜索数据。
没有发现就写「未发现相关专利」。TRO 状态严格来自搜索数据。"""


# ── 提示词构建 ─────────────────────────────────────

def build_review_prompt(form_data: dict) -> str:
    """构建产品信息提示词"""
    title = form_data.get("产品标题", "")
    name = form_data.get("产品名称", form_data.get("产品编号", ""))
    market = form_data.get("目标市场", "US").upper()
    material = form_data.get("材质", "")
    brand = form_data.get("品牌名", "")
    bullets = form_data.get("五点描述", "")
    asin = form_data.get("ASIN", "")
    link = form_data.get("亚马逊链接") or form_data.get("参考链接", "")

    keywords = extract_core_keywords(title)
    kws = "、".join(keywords) if keywords else "（无法提取）"

    return f"""## 产品信息

| 字段 | 内容 |
|------|------|
| 编号 | {form_data.get('总表编号') or form_data.get('产品编号', 'N/A')} |
| 名称 | {name} |
| 标题 | {title} |
| 目标市场 | {market} |
| 材质 | {material or '未提供'} |
| 品牌 | {brand or '无'} |
| ASIN | {asin or '无'} |
| 链接 | {link or '无'} |

### 五点描述
{bullets if bullets else '（未提供）'}

### AI 提取核心关键词
**{kws}**"""


def build_analysis_prompt(form_data: dict, search_results_text: str, image_description: str = "") -> str:
    """构建完整分析提示词（产品信息 + 搜索数据 + 输出要求）"""
    product_section = build_review_prompt(form_data)

    img_section = ""
    if image_description:
        img_section = f"\n\n## 产品图片分析（AI 视觉）\n{image_description}"

    output_format = """
## 输出格式要求

严格按以下结构输出报告。每个专利号必须来自上面的搜索数据。没有就写「未发现」。

```
━━━━━━━━━━━━━━━━━━━━━━━━
🔑 核心关键词
  • xxx  • xxx  • xxx

📋 第一层：产品特征
  类别：xxx | 造型：xxx | 功能：xxx
  材质：xxx | 是否触发版权排查：是/否

⚠️ 版权排查（如有印刷图案）
  搜索词 → 结果摘要
  > 版权风险：🟢/🟡/🔴 + 依据

🏷️ 第二层：商标风险
  [核心关键词] → [数据库/检索结果] → 🟢/🟡/🔴
  > 一行结论

🎨 第三层：设计专利
  | 专利号 | 权利人 | 授权日 | 风险 |
  |--------|--------|--------|:----:|
  | Dxxxxxx | xxx | 20xx | 🟡 |
  > 视觉比对结论

🔧 第四层：发明专利
  | 专利号 | 权利人 | Claim比对 | 风险 |
  |--------|--------|----------|:----:|
  | USxxxxx | xxx | 要素覆盖 | 🔴 |
  > Claim Chart 分析

⚠️ TRO / 维权风险
  🟢 未发现执行历史 / 🔴 有（案件号）→ 标注 🔴TRO

🌐 第五层：市场验证
  同类产品：多/少 | 维权力度：强/中/弱

━━━━━━━━━━━━━━━━━━━━━━━━
🎯 最终结论
  ✅ Go / ⚠️ 需修改设计 / ❌ No-Go
  > 一句话核心理由（说明哪一层出了问题）
━━━━━━━━━━━━━━━━━━━━━━━━
```"""

    return (
        product_section
        + img_section
        + "\n\n---\n\n"
        + search_results_text
        + "\n\n---\n"
        + output_format
    )


# ── 审查编排 ──────────────────────────────────────

async def run_ai_review(form_data: dict, images: list = None) -> str:
    """
    审查编排器 v2：
    1. 提取核心关键词
    2. 多源并行检索（PatentsView + Google Patents + WIPO + Tavily）
    3. 视觉分析图片（如有）
    4. LLM 分析 + 输出报告
    """
    images = images or []
    market = form_data.get("目标市场", "US").upper()
    product_label = form_data.get("产品名称") or form_data.get("产品编号", "未知")

    # ── Step 1: 多源检索 ──
    log.info(f"[{product_label}] Starting multi-source search for {market}...")
    search_results = await run_full_search(form_data, TAVILY_API_KEY)
    search_text = format_search_results(search_results)
    log.info(f"[{product_label}] Search done: {len(search_text)} chars, "
             f"{len(search_results.get('_patent_details', {}))} patent details")

    # ── Step 2: 图片视觉分析（如有图片） ──
    image_description = ""
    if images and GEMINI_API_KEY:
        log.info(f"[{product_label}] Analyzing {len(images)} images with Gemini Vision...")
        image_description = await _analyze_images(images, form_data)

    # ── Step 3: LLM 分析 ──
    prompt = build_analysis_prompt(form_data, search_text, image_description)

    # 优先用 Gemini（支持更大上下文 + 更准确），fallback DeepSeek
    if GEMINI_API_KEY:
        result = await _llm_analyze_gemini(prompt)
        if result and len(result) > 100:
            return result
        log.warning(f"[{product_label}] Gemini failed/incomplete, fallback to DeepSeek")

    if ANTHROPIC_API_KEY:
        result = await _llm_analyze_claude(prompt)
        if result and len(result) > 100:
            return result

    if OPENAI_API_KEY:
        return await _llm_analyze_deepseek(prompt)

    raise RuntimeError("未配置任何 AI API Key")


async def _analyze_images(images_b64: list, form_data: dict) -> str:
    """用 Gemini Vision 分析产品图片，提取特征"""
    title = form_data.get("产品标题", "")
    name = form_data.get("产品名称", "")

    vision_prompt = (
        f"请分析以下产品图片（产品：{name}，标题：{title}），用中文输出：\n"
        "1. 产品类别和整体造型\n"
        "2. 颜色方案和材质外观\n"
        "3. 关键视觉特征（形状、图案、文字、logo、装饰）\n"
        "4. 是否有印刷图案/图形/文字/角色形象？（版权风险信号）\n"
        "5. 表面处理和纹理\n"
        "6. 与同类产品的视觉差异点\n"
        "输出不超过 400 字。"
    )

    parts = [{"text": vision_prompt}]
    for img in images_b64[:3]:
        parts.append({"inline_data": {"mime_type": "image/jpeg", "data": img}})

    try:
        async with httpx.AsyncClient(timeout=120) as c:
            r = await c.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
                json={
                    "contents": [{"parts": parts}],
                    "generationConfig": {"maxOutputTokens": 1500, "temperature": 0.1},
                },
            )
            r.raise_for_status()
            return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        log.warning(f"Image analysis failed: {e}")
        return ""


# ── LLM 调用 ─────────────────────────────────────

async def _llm_analyze_gemini(prompt: str) -> str:
    """Gemini 2.0 Flash 分析（免费，高上下文）"""
    try:
        async with httpx.AsyncClient(timeout=600) as c:
            r = await c.post(
                f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent?key={GEMINI_API_KEY}",
                json={
                    "system_instruction": {"parts": [{"text": FULL_SYSTEM_PROMPT}]},
                    "contents": [{"parts": [{"text": prompt[:30000]}]}],
                    "generationConfig": {
                        "maxOutputTokens": 4000,
                        "temperature": 0.1,
                    },
                },
            )
            r.raise_for_status()
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:
        log.error(f"Gemini analysis failed: {e}")
        return ""


async def _llm_analyze_claude(prompt: str) -> str:
    """Claude API（备选，最准确但需付费）"""
    try:
        async with httpx.AsyncClient(timeout=600) as c:
            r = await c.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": "claude-sonnet-4-20250514",
                    "max_tokens": 8000,
                    "system": FULL_SYSTEM_PROMPT,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            if r.status_code == 200:
                return r.json()["content"][0]["text"]
            log.warning(f"Claude API returned {r.status_code}")
    except Exception as e:
        log.error(f"Claude analysis failed: {e}")
    return ""


async def _llm_analyze_deepseek(prompt: str) -> str:
    """DeepSeek 分析（便宜，但不能联网 → 依赖预搜索数据）"""
    try:
        async with httpx.AsyncClient(timeout=600) as c:
            r = await c.post(
                f"{OPENAI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": os.getenv("LLM_MODEL", "deepseek-chat"),
                    "max_tokens": 8000,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": FULL_SYSTEM_PROMPT},
                        {"role": "user", "content": prompt},
                    ],
                },
            )
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"]
    except Exception as e:
        log.error(f"DeepSeek analysis failed: {e}")
        raise


def run_review_in_thread(form_data: dict, reply_target: dict, images: list = None):
    """在独立线程中运行审查"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(process_review(form_data, reply_target, images))
    finally:
        loop.close()


async def process_review(form_data: dict, reply_target: dict, images: list = None):
    """后台执行审查（v2: 多源并行检索 + 完整五层分析）→ 推送结果"""
    product_label = form_data.get('产品名称') or form_data.get('产品编号') or '未知产品'
    market = form_data.get('目标市场', 'US')
    try:
        # 1. 通知审查开始
        if not images:
            header = f"⏳ 审查中：{product_label}"
            start_msg = (
                f"**产品编号**：{form_data.get('产品编号', 'N/A')}\n"
                f"**目标市场**：{market}\n"
                f"> 📡 正在多源检索：Google Patents + Lens.org + WIPO + Tavily\n"
                f"> 预计 2-5 分钟，请稍候…"
            )
            await _send_result(reply_target, header, start_msg)

        # 2. 执行 AI 审查（v2 多源检索管线）
        log.info(f"[{product_label}] Review started (v2 pipeline)")
        result = await run_ai_review(form_data, images or [])

        # 3. 截断适配飞书消息长度
        max_len = 14000
        if len(result) > max_len:
            result = result[:max_len - 100] + "\n\n---\n> ⚠️ 报告过长已截断，完整分析可通过网页端查看"

        # 4. 推送结果
        report_date = datetime.now().strftime('%Y-%m-%d %H:%M')
        final_msg = (
            f"{result}\n\n---\n"
            f"> 🤖 专利审核 AI v2 | {report_date}\n"
            f"> 📡 数据源：Google Patents + Lens.org + WIPO + Tavily\n"
            f"> ⚠️ 仅供参考，最终决策请人工确认"
        )
        await _send_result(reply_target, f"🔍 {product_label} 审查报告", final_msg)
        log.info(f"[{product_label}] Review complete")

    except Exception as e:
        log.exception(f"[{product_label}] Review failed")
        await _send_result(
            reply_target,
            f"❌ 审查失败",
            f"**{product_label}**\n错误：{str(e)}\n请稍后重试或联系管理员。"
        )


async def _send_result(target: dict, header: str, content: str):
    """根据 target 类型发送结果"""
    try:
        if target["type"] == "message":
            await feishu.reply_message(target["msg_id"], f"{header}\n\n{content}")
        else:
            await feishu.send_card(target["open_id"], "open_id", header, content)
    except Exception:
        # 回退：尝试 reply
        if target.get("msg_id"):
            await feishu.reply_message(target["msg_id"], f"{header}\n\n{content}")


# ── FastAPI 路由 ─────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "service": "黑伞专利审核服务"}


@app.get("/test-reply")
async def test_reply():
    """测试回复通道"""
    msg_id = "om_x100b6d8f79ff1c8cb36139821f8d94d"
    await feishu.reply_message(msg_id, "✅ 回复通道正常！")
    return {"code": 0, "msg": "ok"}


@app.get("/test-search")
async def test_search(q: str = "gutter cleaning tool", market: str = "US"):
    """测试多源检索引擎"""
    from search_engine import run_full_search, format_search_results
    form_data = {
        "产品标题": q,
        "产品名称": q,
        "目标市场": market,
    }
    results = await run_full_search(form_data, TAVILY_API_KEY)
    formatted = format_search_results(results)
    meta = results.get("_search_meta", {})
    return {
        "code": 0,
        "keywords": meta.get("keywords", []),
        "patents_found": meta.get("patent_ids_found", []),
        "total_searches": meta.get("total_searches", 0),
        "search_data_preview": formatted[:3000],
    }


@app.get("/debug")
async def debug_info():
    """调试端点：显示运行环境信息"""
    import platform, sys as _sys
    info = {
        "python": _sys.version,
        "platform": platform.platform(),
        "cwd": os.getcwd(),
        "env_keys": [k for k in os.environ if not any(s in k.lower() for s in ('key', 'secret', 'token', 'pass'))],
        "search_engine_ok": True,
    }
    try:
        from search_engine import run_full_search
    except Exception as e:
        info["search_engine_ok"] = False
        info["search_engine_error"] = str(e)
    return info


@app.get("/")
async def web_form():
    """网页端提交表单（备用）"""
    return HTMLResponse("""
    <!DOCTYPE html><html><head><meta charset="utf-8"><title>专利审核提交</title>
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <style>body{font-family:sans-serif;max-width:600px;margin:2rem auto;padding:0 1rem}
    input,textarea,select{width:100%;padding:8px;margin:4px 0 16px;border:1px solid #ddd;border-radius:6px;box-sizing:border-box}
    textarea{height:80px}label{font-weight:bold;font-size:14px}
    button{background:#0052d9;color:white;border:none;padding:12px 24px;border-radius:6px;font-size:16px;cursor:pointer}
    button:hover{background:#0042b0}button:disabled{background:#999}
    h1{color:#333}.result{background:#f5f5f5;padding:16px;border-radius:8px;margin-top:16px;white-space:pre-wrap;display:none}</style></head><body>
    <h1>🔍 专利侵权审查</h1>
    <form id="form">
    <label>产品编号 *</label><input name="产品编号" required placeholder="如 888">
    <label>产品名称 *</label><input name="产品名称" required placeholder="如 硅胶杯盖">
    <label>产品标题 *</label><input name="产品标题" required placeholder="完整 Amazon Listing 标题">
    <label>目标市场</label><select name="目标市场"><option>US</option><option>CA</option><option>EU</option><option>FR</option><option>JP</option></select>
    <label>材质</label><input name="材质" placeholder="如 硅胶、不锈钢">
    <label>品牌名</label><input name="品牌名" placeholder="如无则不填">
    <label>五点描述</label><textarea name="五点描述" placeholder="Amazon Bullet Points"></textarea>
    <label>开发员</label><input name="开发员" placeholder="如无则不填">
    <label>参考链接</label><input name="参考链接" placeholder="Amazon ASIN 链接">
    <button type="submit" id="btn">提交审查</button>
    </form>
    <div class="result" id="result"></div>
    <script>
    document.getElementById('form').onsubmit=async function(e){
    e.preventDefault();var btn=document.getElementById('btn');btn.disabled=true;btn.textContent='审查中…';
    var data={};new FormData(this).forEach((v,k)=>data[k]=v);
    try{var r=await fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
    var j=await r.json();document.getElementById('result').style.display='block';
    document.getElementById('result').textContent='✅ 已提交！机器人将在 3-8 分钟内推送审查报告。';}
    catch(err){document.getElementById('result').style.display='block';document.getElementById('result').textContent='❌ 提交失败：'+err.message;}
    btn.disabled=false;btn.textContent='提交审查';};</script></body></html>""")


@app.post("/feishu/webhook")
async def feishu_webhook(request: Request):
    """接收飞书事件（机器人消息 + 表单提交）"""
    body = await request.json()
    log.info(f"Event: {json.dumps(body, ensure_ascii=False)[:800]}")

    # URL 验证
    if body.get("type") == "url_verification":
        return JSONResponse({"challenge": body.get("challenge", "")})

    # ── A. 机器人收到消息 ──
    event = body.get("event", {})
    event_type = body.get("header", {}).get("event_type", "")

    if event_type == "im.message.receive_v1":
        return await _handle_chat_message(event, body)

    # ── B. 表单/流程 Webhook ──
    # 尝试从多种格式中提取表单数据
    form_data = _extract_form_data(body, event)

    if form_data:
        open_id = (
            event.get("operator", {}).get("open_id", "")
            or body.get("open_id", "")
            or "admin"
        )
        asyncio.create_task(process_review(form_data, {"type": "user", "open_id": open_id}))
        return JSONResponse({"code": 0, "msg": "审查已开始"})

    # 其他事件，返回 ok 避免飞书重试
    return JSONResponse({"code": 0})


async def _handle_chat_message(event: dict, body: dict):
    """处理 @机器人 消息 — 支持文字+图片"""
    msg_id = event.get("message", {}).get("message_id", "")
    chat_id = event.get("message", {}).get("chat_id", "")
    msg_type = event.get("message", {}).get("message_type", "text")
    if not msg_id:
        return JSONResponse({"code": 0})

    # ── 获取发送者（群聊区分不同人，text/post/image 统一）──
    sender_id = event.get("sender", {}).get("sender_id", {}).get("open_id", chat_id)
    review_key = f"{chat_id}:{sender_id}" if sender_id and sender_id != chat_id else chat_id

    # ── 📸 图片消息 ──
    if msg_type == "image":
        msg_content = event.get("message", {}).get("content", "{}")
        try:
            image_key = json.loads(msg_content).get("image_key", "")
        except json.JSONDecodeError:
            image_key = ""
        if image_key:
            log.info(f"Chat [{review_key}]: image received, downloading now...")
            existing = pending_reviews.get(review_key, {})
            if not existing.get("_review_key"):
                existing["_review_key"] = review_key
            try:
                img_bytes = await feishu.download_image(image_key)
                existing["_images_b64"] = existing.get("_images_b64", []) + [base64.b64encode(img_bytes).decode()]
                existing["_image_count"] = existing.get("_image_count", 0) + 1
                log.info(f"Image downloaded OK: {len(img_bytes)} bytes")
            except Exception as e:
                log.error(f"Image download failed: {e}")
            pending_reviews[review_key] = existing
            await feishu.reply_message(msg_id, f"📸 图片已收到！（共{existing['_image_count']}张）\n请继续发送产品文字信息。")
        return JSONResponse({"code": 0})

    # ── 📝+📸 富文本消息（文字+图片一起发）──
    if msg_type == "post":
        return await _handle_post_message(event, review_key, msg_id)

    # 提取消息文本
    msg_content = event.get("message", {}).get("content", "{}")
    try:
        text = json.loads(msg_content).get("text", "")
    except json.JSONDecodeError:
        text = msg_content

    log.info(f"Chat [{chat_id}]: {text[:200]}")

    # ── 第二步：用户确认开始审查 ──
    if text.strip().lower() in ("开始", "确认", "go", "start", "yes", "ok", "1"):
        # 防重复——直接锁 pending_reviews 里的数据
        existing = pending_reviews.get(review_key) or pending_reviews.get(chat_id)
        if not existing or existing.get("_locked"):
            return JSONResponse({"code": 0})
        existing["_locked"] = True
        form_data = existing
        name = form_data.get("产品名称") or form_data.get("产品编号") or form_data.get("总表编号")
        has_imgs = bool(form_data.get("_images_b64"))
        if not name and not has_imgs:
            return JSONResponse({"code": 0})

        if not name:
            name = "图片审查"
            form_data["产品名称"] = name
            form_data["目标市场"] = form_data.get("目标市场", "US")

        # 取预下载的图片
        images_b64 = form_data.pop("_images_b64", [])
        img_count = form_data.pop("_image_count", len(images_b64))
        await feishu.reply_message(msg_id,
            f"⏳ 正在审查 **{name}**{'（含' + str(len(images_b64)) + '张图片）' if images_b64 else ''}预计 3-8 分钟…")

        log.info(f"Review START: {name}, images={len(images_b64)}, fields={list(form_data.keys())}")
        await process_review(form_data, {"type": "message", "msg_id": msg_id}, images_b64)
        return JSONResponse({"code": 0})

    # ── 第一步：解析产品信息并暂存 ──
    form_data = parse_chat_message(text)
    if not form_data:
        await feishu.reply_message(msg_id,
            "👋 专利侵权审查助手\n\n"
            "请按以下格式发送产品信息：\n\n"
            "```\n"
            "总表编号：999\n"
            "名称：硅胶杯盖\n"
            "标题：Silicone Cup Lid for Travel Mugs\n"
            "市场：US\n"
            "材质：食品级硅胶\n"
            "亚马逊产品链接：https://amazon.com/...\n"
            "ASIN：B0XXXXXXXX\n"
            "五点描述：\n"
            "1. xxx\n"
            "2. xxx\n"
            "```\n\n"
            "📸 也可以直接发送产品图片\n"
            "✅ 发送后回复 **「开始」** 启动审查"
        )
        return JSONResponse({"code": 0})

    # 合并已有的图片
    existing = pending_reviews.pop(review_key, pending_reviews.pop(chat_id, {}))
    existing.update(form_data)
    pending_reviews[review_key] = existing
    images = existing.get("_image_keys", [])
    product = form_data.get("产品名称") or form_data.get("产品编号")
    await feishu.reply_message(msg_id,
        f"✅ 已收到 **{product}**"
        + (f" + {len(images)}张图片" if images else "")
        + f"（目标市场：{form_data.get('目标市场', 'US')}）\n\n"
        "回复 **「开始」** 启动审查。"
    )
    return JSONResponse({"code": 0})


async def _handle_post_message(event: dict, review_key: str, msg_id: str):
    """处理飞书富文本消息（文字+图片混合）"""
    msg_content = event.get("message", {}).get("content", "{}")
    try:
        content_obj = json.loads(msg_content)
    except json.JSONDecodeError:
        return JSONResponse({"code": 0})

    # 遍历 post 内容，提取文字和图片
    # 飞书 post 有两种格式：
    # A. 直接格式: {"content": [[{...}], [{...}]]}  ← P2P 聊天用
    # B. 嵌套格式: {"content": {"zh_cn": {"content": [[...]]}}}
    raw = content_obj.get("content", content_obj)
    if isinstance(raw, list):
        paragraphs = raw
    elif isinstance(raw, dict):
        paragraphs = raw.get("zh_cn", raw.get("en_us", {})).get("content", [])
    else:
        paragraphs = []

    text_parts = []
    image_keys = []

    for para in paragraphs:
        for elem in para:
            if elem.get("tag") == "text":
                text_parts.append(elem.get("text", ""))
            elif elem.get("tag") == "img":
                key = elem.get("image_key", "")
                if key:
                    image_keys.append(key)

    text = "\n".join(text_parts).strip()
    log.info(f"Post [{review_key}]: text={text[:100]}, images={len(image_keys)}")

    # 解析文字部分
    form_data = parse_chat_message(text) if text else {}

    # 合并存储
    existing = pending_reviews.pop(review_key, {})
    if form_data:
        existing.update(form_data)

    # 立即下载图片
    new_images = 0
    for key in image_keys:
        try:
            img_bytes = await feishu.download_image(key)
            existing["_images_b64"] = existing.get("_images_b64", []) + [base64.b64encode(img_bytes).decode()]
            new_images += 1
        except Exception as e:
            log.error(f"Post image download failed: {e}")

    existing["_image_count"] = existing.get("_image_count", 0) + new_images
    pending_reviews[review_key] = existing

    total_imgs = existing["_image_count"]
    product = existing.get("产品名称") or existing.get("产品编号") or "产品"
    await feishu.reply_message(msg_id,
        f"✅ 已收到 **{product}**"
        + (f" + {total_imgs}张图片" if total_imgs else "")
        + f"（目标市场：{existing.get('目标市场', 'US')}）\n\n"
        "回复 **「开始」** 启动审查。"
    )
    return JSONResponse({"code": 0})


def _extract_form_data(body: dict, event: dict) -> Optional[dict]:
    """从飞书表单/流程 webhook 中提取结构化数据"""
    # 尝试多个常见路径
    sources = [
        body.get("action_value"),
        body.get("data"),
        event.get("action_value"),
        body,
    ]

    for src in sources:
        if not isinstance(src, dict):
            continue
        # 如果直接有产品相关字段
        if src.get("产品名称") or src.get("产品编号") or src.get("product_name"):
            return {
                "产品编号": src.get("产品编号") or src.get("product_code", ""),
                "产品名称": src.get("产品名称") or src.get("product_name", ""),
                "产品标题": src.get("产品标题") or src.get("product_title", ""),
                "目标市场": src.get("目标市场") or src.get("target_market", "US"),
                "材质": src.get("材质") or src.get("material", ""),
                "品牌名": src.get("品牌名") or src.get("brand", ""),
                "五点描述": src.get("五点描述") or src.get("bullet_points", ""),
                "开发员": src.get("开发员") or src.get("developer", ""),
                "参考链接": src.get("参考链接") or src.get("reference_link", ""),
                "产品图片": src.get("产品图片") or src.get("images", []),
            }

    return None


@app.post("/api/review")
async def api_review(request: Request):
    """API 直接调用（网页表单 / 外部系统）- 同步执行"""
    try:
        payload = await request.json()
    except Exception as e:
        return JSONResponse({"code": 1, "msg": f"JSON解析失败: {e}"}, status_code=400)
    open_id = payload.get("open_id", "api_user")
    await process_review(payload, {"type": "user", "open_id": open_id})
    return {"code": 0, "msg": "审查完成", "product": payload.get("产品编号")}


# ── 启动 ────────────────────────────────────────────
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
