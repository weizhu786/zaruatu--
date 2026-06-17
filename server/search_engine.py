"""
黑伞专利审核 — 多源专利检索引擎

支持的检索源：
  - PatentsView API（免费，US 专利结构化数据）
  - Google Patents（网页抓取，多国覆盖）
  - WIPO PATENTSCOPE（国际专利/PCT）
  - Tavily（TRO/维权/市场/版权）
  - worldtro.com（TRO 案件）
  - 跨境电商侵权预警（中文社区）
"""

import re
import json
import logging
import asyncio
from typing import Optional
from urllib.parse import quote

import httpx

log = logging.getLogger("patent-search")

# ═══════════════════════════════════════════════════════════════
# 工具函数
# ═══════════════════════════════════════════════════════════════

def extract_core_keywords(title: str) -> list[str]:
    """
    从产品标题提取核心关键词。
    规则：去掉品牌/形容词/材质/尺寸 → 找品类核心词
    """
    stop_words = {
        'strong', 'portable', 'new', 'premium', 'high', 'quality',
        'best', 'durable', 'professional', 'heavy', 'duty', 'easy',
        'adjustable', 'foldable', 'lightweight', 'compact', 'large',
        'small', 'mini', 'set', 'pack', 'pcs', 'piece', 'pieces',
        'inch', 'inches', 'cm', 'mm', 'ft', 'feet', 'oz',
        'stainless', 'steel', 'silicone', 'plastic', 'aluminum',
        'aluminium', 'wood', 'metal', 'glass', 'leather', 'cotton',
        'nylon', 'polyester', 'fabric', 'rubber', 'copper', 'zinc',
        'alloy', 'ceramic', 'bamboo', 'carbon', 'fiber',
        'magnetic', 'waterproof', 'reusable', 'disposable',
        '2024', '2025', '2026',
    }
    # 去掉品牌名（首字母大写的独立词）、括号内容
    cleaned = re.sub(r'\([^)]*\)', '', title)
    cleaned = re.sub(r'\[[^\]]*\]', '', cleaned)
    cleaned = re.sub(r'[-–—]', ' ', cleaned)

    words = cleaned.split()
    keywords = []
    for w in words:
        w_clean = w.strip('",.\'!;:').lower()
        if w_clean not in stop_words and len(w_clean) > 2:
            keywords.append(w_clean)

    # 生成 1-3 个 n-gram 核心词
    result = []
    if len(keywords) >= 2:
        result.append(' '.join(keywords[:2]))  # 前两个词的 bigram
    if len(keywords) >= 3:
        result.append(' '.join(keywords[:3]))  # trigram
    result.append(' '.join(keywords[:min(4, len(keywords))]))

    # 去重并保持顺序
    seen = set()
    unique = []
    for r in result:
        if r not in seen:
            seen.add(r)
            unique.append(r)
    return unique[:3]


def extract_patent_ids(text: str) -> list[str]:
    """从文本中提取所有专利号"""
    patterns = [
        r'(?:US|USD)\s*(\d[\d,]{3,}(?:[A-Z]\d)?)',
        r'(?:专利号|Patent\s*(?:No|Number)?)[:\s]*(?:US|USD)?\s*(\d[\d,]{3,}(?:[A-Z]\d)?)',
        r'D\s*(\d[\d,]{3,})',
    ]
    ids = set()
    for pat in patterns:
        for m in re.finditer(pat, text, re.IGNORECASE):
            raw = m.group(1).replace(',', '').replace(' ', '')
            if 5 <= len(raw) <= 12:
                ids.add(raw)
    return sorted(ids)


# ═══════════════════════════════════════════════════════════════
# Justia Patents 搜索（服务端渲染 HTML，可解析）
# ═══════════════════════════════════════════════════════════════

async def search_google_patents(
    query: str,
    country: str = "US",
    patent_type: str = "all",
    max_results: int = 10
) -> dict:
    """
    搜索专利（通过 Justia Patents，支持服务端渲染）。

    返回: {
        "results": [{"id": "US10184252B2", "title": "...", "url": "..."}],
        "query": str, "country": str, "source": str
    }
    """
    # Justia Patents 搜索 URL
    url = f"https://patents.justia.com/search?q={quote(query)}"

    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html",
                    "Accept-Language": "en-US,en;q=0.9",
                },
                follow_redirects=True,
            )
            r.raise_for_status()
            html = r.text
    except httpx.ConnectError as e:
        log.warning(f"Justia Patents: Cannot connect: {e}")
        return {"results": [], "error": f"Connection failed: {str(e)[:200]}"}
    except Exception as e:
        log.warning(f"Justia Patents search failed: {e}")
        return {"results": [], "error": str(e)[:200]}

    results = _parse_justia_results(html, country, patent_type)
    return {
        "results": results[:max_results],
        "query": query,
        "country": country,
        "source": "Justia Patents",
    }


def _parse_justia_results(html: str, country: str, patent_type: str) -> list[dict]:
    """从 Justia Patents 搜索结果页提取专利信息"""
    results = []
    seen_ids = set()

    # Justia 结果格式:
    # <a href="/patent/2025/.../US10184252B2">Title</a>
    # 或 <h5><a href="/patent/.../USD897062">Title</a></h5>

    # 模式1: /patent/YEAR/.../PATENT_ID
    for m in re.finditer(
        r'/patent/\d{4}/[^"]*?/([A-Z]{2,4}\d{4,}[A-Z]?\d*)[^"]*',
        html, re.IGNORECASE
    ):
        pid = m.group(1).upper()
        if pid in seen_ids:
            continue
        seen_ids.add(pid)
        if _match_country_type(pid, country, patent_type):
            results.append({"id": pid, "title": "", "url": f"https://patents.justia.com/patent/{pid}", "source": "Justia"})

    # 模式2: 专利标题文本
    if results:
        for i, r in enumerate(results):
            pid = r["id"]
            # 找专利号附近的标题
            title_pat = re.search(
                re.escape(pid) + r'[^<]*</a>\s*(?:</h\d>\s*)?(?:<[^>]+>)?([^<]{10,200})',
                html, re.IGNORECASE
            )
            if not title_pat:
                # 尝试找 <a> 标签内的文本
                title_pat = re.search(
                    r'href="[^"]*' + re.escape(pid) + r'[^"]*"[^>]*>([^<]{5,200})</a>',
                    html, re.IGNORECASE
                )
            if title_pat:
                results[i]["title"] = title_pat.group(1).strip()[:200]

    return results


def _match_country_type(pid: str, country: str, patent_type: str) -> bool:
    """检查专利号是否匹配目标国家和类型"""
    if country and country != "ALL":
        if country == "US" and not pid.startswith("US"):
            return False
    if patent_type == "design":
        if not (pid.startswith("USD") or pid.startswith("D")):
            return False
    elif patent_type == "utility":
        if pid.startswith("USD") or pid.startswith("D"):
            return False
    return True


async def fetch_patent_detail(patent_id: str) -> dict:
    """获取单个专利详情（摘要、权利要求、附图链接）"""
    url = f"https://patents.google.com/patent/{patent_id}/en"

    try:
        async with httpx.AsyncClient(timeout=20) as c:
            r = await c.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                    "Accept": "text/html",
                },
                follow_redirects=True,
            )
            r.raise_for_status()
            html = r.text
    except Exception as e:
        return {"id": patent_id, "error": str(e)}

    # 提取标题
    title_match = re.search(r'<title>([^<]+)</title>', html)
    title = title_match.group(1).strip() if title_match else ""
    # 清理 Google Patents 标题后缀
    title = re.sub(r'\s*-\s*Google Patents$', '', title)

    # 提取摘要
    abstract_match = re.search(
        r'<meta\s+name="description"\s+content="([^"]+)"',
        html, re.IGNORECASE
    )
    abstract = abstract_match.group(1) if abstract_match else ""

    # 提取权利要求
    claims_text = _extract_claims(html)

    # 提取发明人/申请人
    assignee_match = re.search(
        r'<dd[^>]*itemprop="assignee"[^>]*>.*?<span[^>]*>([^<]+)</span>',
        html, re.DOTALL | re.IGNORECASE
    )
    assignee = assignee_match.group(1).strip() if assignee_match else ""

    # 提取日期
    date_match = re.search(
        r'<time[^>]*itemprop="publicationDate"[^>]*datetime="([^"]+)"',
        html, re.IGNORECASE
    )
    pub_date = date_match.group(1)[:10] if date_match else ""

    return {
        "id": patent_id,
        "title": title,
        "abstract": abstract[:500] if abstract else "",
        "claims": claims_text[:2000] if claims_text else "",
        "assignee": assignee,
        "pub_date": pub_date,
        "url": url,
        "is_design": patent_id.startswith("USD") or "/USD" in patent_id,
    }


def _extract_claims(html: str) -> str:
    """从 Google Patents 页面提取权利要求文本"""
    # 查找 claims section
    claims_section = re.search(
        r'<section[^>]*id="claims"[^>]*>(.*?)</section>',
        html, re.DOTALL | re.IGNORECASE
    )
    if not claims_section:
        claims_section = re.search(
            r'<div[^>]*class="claims"[^>]*>(.*?)</div>',
            html, re.DOTALL | re.IGNORECASE
        )
    if not claims_section:
        # 尝试匹配 claim text
        claims_match = re.findall(
            r'<div[^>]*class="claim"[^>]*>(.*?)</div>',
            html, re.DOTALL | re.IGNORECASE
        )
        if claims_match:
            claims = []
            for i, c in enumerate(claims_match[:10], 1):
                text = re.sub(r'<[^>]+>', ' ', c).strip()
                text = re.sub(r'\s+', ' ', text)
                if len(text) > 10:
                    claims.append(f"Claim {i}: {text[:300]}")
            return "\n".join(claims)
        return ""

    text = claims_section.group(1)
    # 清理 HTML 标签
    text = re.sub(r'<[^>]+>', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text[:2000]


async def batch_fetch_patents(patent_ids: list[str]) -> list[dict]:
    """批量获取专利详情，最多 8 个并行"""
    if not patent_ids:
        return []
    tasks = [fetch_patent_detail(pid) for pid in patent_ids[:8]]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [
        r for r in results
        if isinstance(r, dict) and not r.get("error")
    ]


# ═══════════════════════════════════════════════════════════════
# Lens.org 专利搜索（免费学术 API，无需 API Key）
# ═══════════════════════════════════════════════════════════════

async def search_lens_patents(
    keywords: list[str],
    patent_type: str = None,
    max_results: int = 8
) -> list[dict]:
    """
    使用 Lens.org 免费 API 搜索专利。
    Lens.org 覆盖全球 1.4 亿专利，无需 API Key。
    """
    query = " OR ".join([f'title:"{kw}" OR abstract:"{kw}"' for kw in keywords[:3]])

    params = {
        "q": query,
        "size": max_results,
        "sort": "relevance",
    }

    # 过滤设计专利
    if patent_type == "design":
        params["q"] = f"({params['q']}) AND type:design"

    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.get(
                "https://api.lens.org/scholarly/search",
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "PatentReviewBot/2.0",
                },
            )
            if r.status_code == 401 or r.status_code == 403:
                log.warning("Lens.org API requires authentication, skipping")
                return []
            r.raise_for_status()
            data = r.json()
    except Exception as e:
        log.warning(f"Lens.org API failed: {e}")
        return []

    results = []
    for item in data.get("data", [])[:max_results]:
        pid = item.get("document_id", "")
        title = item.get("title", "")
        abstract = item.get("abstract", "")[:500] if item.get("abstract") else ""

        results.append({
            "id": pid,
            "title": title[:200] if title else "",
            "abstract": abstract,
            "type": item.get("patent_type", ""),
            "date": item.get("date_published", "")[:10],
            "source": "Lens.org",
            "url": f"https://www.lens.org/lens/patent/{pid}",
        })

    return results


# ═══════════════════════════════════════════════════════════════
# WIPO PATENTSCOPE
# ═══════════════════════════════════════════════════════════════

async def search_wipo(keywords: list[str]) -> list[dict]:
    """搜索 WIPO PATENTSCOPE（PCT 国际申请）"""
    query = " OR ".join([f'EN_TI:"{kw}"' for kw in keywords[:3]])
    query += " OR " + " OR ".join([f'EN_AB:"{kw}"' for kw in keywords[:3]])

    url = "https://patentscope.wipo.int/search/en/search.jsf"
    # WIPO 网页搜索 - 简化版
    search_url = (
        f"https://patentscope.wipo.int/search/en/result.jsf?"
        f"query={quote(query)}&office=&sortOption=Relevance&"
        f"maxRec=10"
    )

    try:
        async with httpx.AsyncClient(timeout=25) as c:
            r = await c.get(search_url, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "text/html",
            }, follow_redirects=True)
            html = r.text
    except Exception as e:
        log.warning(f"WIPO search failed: {e}")
        return []

    # 解析结果
    results = []
    patent_ids = set()

    # WIPO 结果格式: WO/2020/123456
    for m in re.finditer(r'(WO\s*/\s*\d{4}\s*/\s*\d{4,})', html):
        pid = m.group(1).replace(' ', '')
        if pid not in patent_ids:
            patent_ids.add(pid)
            results.append({
                "id": pid,
                "source": "WIPO PATENTSCOPE",
                "url": f"https://patentscope.wipo.int/search/en/detail.jsf?docId={pid}",
            })

    return results[:5]


# ═══════════════════════════════════════════════════════════════
# Tavily 搜索（增强版）
# ═══════════════════════════════════════════════════════════════

async def search_tavily(query: str, api_key: str, search_depth: str = "advanced") -> str:
    """Tavily 搜索 - 返回纯文本结果"""
    if not api_key:
        return ""

    try:
        async with httpx.AsyncClient(timeout=30) as c:
            r = await c.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": api_key,
                    "query": query,
                    "search_depth": search_depth,
                    "max_results": 5,
                    "include_answer": True,
                },
            )
            r.raise_for_status()
            data = r.json()

            parts = []
            answer = data.get("answer", "")
            if answer:
                parts.append(f"[Tavily Answer]\n{answer}")

            for item in data.get("results", []):
                parts.append(
                    f"- {item.get('title', '')}\n"
                    f"  {item.get('content', '')[:300]}\n"
                    f"  URL: {item.get('url', '')}"
                )

            return "\n\n".join(parts)[:3000]
    except Exception as e:
        log.warning(f"Tavily search failed: {e}")
        return ""


# ═══════════════════════════════════════════════════════════════
# TRO / 维权专项搜索
# ═══════════════════════════════════════════════════════════════

async def search_tro_keith(keywords: list[str], product_name: str) -> str:
    """
    TRO + Keith 律所专项搜索。
    使用 Google（通过 Tavily）搜索 TRO 案件。
    """
    queries = []

    # Keith 律师专项
    for kw in keywords[:2]:
        queries.append(f'Keith "{kw}" TRO copyright lawsuit 2025 2026 Amazon sellers')
        queries.append(f'"{kw}" "VA" copyright registration Keith')

    # TRO 通用
    queries.append(f'"{product_name}" TRO lawsuit Amazon 2025 2026')
    queries.append(f'"{product_name}" 跨境电商 侵权 TRO 临时禁令')

    return "\n".join(queries)


async def search_worldtro(keywords: list[str]) -> str:
    """尝试访问 worldtro.com 获取 TRO 信息"""
    # worldtro.com 是付费网站，但我们可以搜提及它的文章
    queries = []
    for kw in keywords[:2]:
        queries.append(f'site:worldtro.com "{kw}"')
        queries.append(f'worldtro "{kw}" TRO')
    return "\n".join(queries)


async def search_amz_warning(keywords: list[str]) -> str:
    """搜索跨境电商侵权预警"""
    queries = []
    for kw in keywords[:2]:
        queries.append(f'"{kw}" 侵权预警 AMZ123 sellerdefense 2025 2026')
        queries.append(f'"{kw}" 专利侵权 亚马逊 下架 listing')
        queries.append(f'"{kw}" 跨境 维权 麦家星球 跨境魔方')
    return "\n".join(queries)


# ═══════════════════════════════════════════════════════════════
# 市场验证搜索
# ═══════════════════════════════════════════════════════════════

async def search_market(keywords: list[str], product_name: str) -> str:
    """搜索各电商平台验证产品通用性"""
    queries = []
    for kw in keywords[:1]:
        queries.append(f'site:aliexpress.com "{kw}"')
        queries.append(f'site:etsy.com "{kw}"')
        queries.append(f'site:ebay.com "{kw}"')
        queries.append(f'"{kw}" AliExpress Etsy sellers supplier')
    return "\n".join(queries)


# ═══════════════════════════════════════════════════════════════
# 统一搜索编排
# ═══════════════════════════════════════════════════════════════

async def run_full_search(
    form_data: dict,
    tavily_api_key: str = "",
) -> dict:
    """
    统一编排多源搜索，返回结构化结果给 LLM 分析。

    搜索策略（按目标市场）：
      - Google Patents（主力，免费，覆盖所有国家）
      - Lens.org（补充，全球专利学术搜索）
      - WIPO PATENTSCOPE（PCT 国际申请）
      - Tavily（TRO/维权/市场/版权/Keith）
    """
    title = form_data.get("产品标题", "")
    name = form_data.get("产品名称", form_data.get("产品编号", ""))
    brand = form_data.get("品牌名", "")
    market = form_data.get("目标市场", "US").upper().strip()

    # 核心关键词
    keywords = extract_core_keywords(title)
    primary_kw = keywords[0] if keywords else name

    log.info(f"Search: market={market}, keywords={keywords}, brand={brand}")

    # ── 并行执行所有搜索 ──
    tasks = {}

    # 1. Google Patents — 主力检索（按目标市场 + 专利类型分别搜）
    if "US" in market or market == "ALL":
        tasks["gp_us_design"] = search_google_patents(
            primary_kw, country="US", patent_type="design", max_results=8
        )
        tasks["gp_us_utility"] = search_google_patents(
            primary_kw, country="US", patent_type="utility", max_results=10
        )
    else:
        # 非 US 市场：全类型搜索
        tasks[f"gp_{market}"] = search_google_patents(
            primary_kw, country=market, max_results=10
        )

    # 2. 次要关键词补充搜索
    if len(keywords) > 1 and keywords[1] != primary_kw:
        tasks["gp_secondary"] = search_google_patents(
            keywords[1], country="US", max_results=6
        )

    # 3. Lens.org — 补充全球专利搜索
    tasks["lens"] = search_lens_patents(keywords, max_results=6)

    # 4. WIPO PATENTSCOPE — 国际专利
    tasks["wipo"] = search_wipo(keywords)

    # 5. Tavily 多渠道搜索（如果有 API Key）
    if tavily_api_key:
        # TRO + Keith
        tro_query = f'"{primary_kw}" TRO lawsuit Keith copyright Amazon sellers 2025 2026'
        tasks["tavily_tro"] = search_tavily(tro_query, tavily_api_key)

        # 商标
        if brand:
            tm_query = f'"{brand}" trademark registration USPTO Amazon'
        else:
            tm_query = f'"{primary_kw}" trademark USPTO registered'
        tasks["tavily_trademark"] = search_tavily(tm_query, tavily_api_key)

        # 版权 + Keith
        copyright_query = f'Keith "{primary_kw}" copyright VA registration lawsuit 2025 2026 Amazon'
        tasks["tavily_copyright"] = search_tavily(copyright_query, tavily_api_key)

        # 市场 + 供应商
        market_query = f'"{primary_kw}" AliExpress Etsy sellers Amazon suppliers wholesale'
        tasks["tavily_market"] = search_tavily(market_query, tavily_api_key)

        # 跨境电商侵权预警
        amz_query = f'"{primary_kw}" 侵权 专利 TRO 亚马逊 跨境 2025 2026 AMZ123'
        tasks["tavily_amz"] = search_tavily(amz_query, tavily_api_key)

        # 品牌诉讼
        if brand:
            brand_query = f'"{brand}" Amazon lawsuit patent trademark infringement TRO'
            tasks["tavily_brand"] = search_tavily(brand_query, tavily_api_key)

    # 6. ✨ 执行全部搜索（并行）
    results = {}
    log.info(f"Running {len(tasks)} parallel searches...")

    gathered = await asyncio.gather(*tasks.values(), return_exceptions=True)
    for key, result in zip(tasks.keys(), gathered):
        if isinstance(result, Exception):
            log.warning(f"Search {key} failed: {result}")
            results[key] = None
        else:
            results[key] = result

    # ── 提取所有专利 ID 并批量获取详情 ──
    all_patent_ids = set()

    # 从 Google Patents 结果
    for key in list(results.keys()):
        if key.startswith("gp_"):
            google_data = results.get(key, {})
            items = google_data.get("results", []) if isinstance(google_data, dict) else []
            for item in items:
                if isinstance(item, dict) and item.get("id"):
                    all_patent_ids.add(item["id"])

    # 从 Lens.org 结果
    lens_results = results.get("lens", []) or []
    for item in lens_results:
        if isinstance(item, dict) and item.get("id"):
            all_patent_ids.add(item["id"])

    # 批量获取前 10 个专利详情（设计专利优先，因为最需要视觉比对信息）
    design_ids = [pid for pid in all_patent_ids if pid.startswith("USD") or pid.startswith("D")]
    utility_ids = [pid for pid in all_patent_ids if pid not in design_ids]
    top_ids = (design_ids + utility_ids)[:10]
    patent_details = await batch_fetch_patents(top_ids)

    results["_patent_details"] = {
        p["id"]: p for p in patent_details if isinstance(p, dict)
    }
    results["_search_meta"] = {
        "keywords": keywords,
        "primary_keyword": primary_kw,
        "market": market,
        "total_searches": len(tasks),
        "patent_ids_found": sorted(all_patent_ids),
    }

    log.info(f"Search complete: {len(all_patent_ids)} patents found, "
             f"{len(patent_details)} details fetched from Google Patents")

    return results


# ═══════════════════════════════════════════════════════════════
# 搜索结果 → LLM 输入格式化
# ═══════════════════════════════════════════════════════════════

def format_search_results(results: dict) -> str:
    """将多源搜索结果格式化为 LLM 可读文本"""
    meta = results.get("_search_meta", {})
    parts = []

    parts.append(f"## 📡 实时检索数据（{meta.get('total_searches', 0)} 个数据源）")
    parts.append(f"核心关键词: {', '.join(meta.get('keywords', []))}")
    parts.append(f"目标市场: {meta.get('market', 'US')}")
    parts.append("")

    # ── Google Patents 结果（主力数据源）──
    for key in sorted(results.keys()):
        if not key.startswith("gp_"):
            continue
        google_data = results[key]
        if not isinstance(google_data, dict):
            continue
        items = google_data.get("results", [])[:8]
        if not items:
            continue

        label = key.replace("gp_", "").replace("_", " ").title()
        parts.append(f"### 🔍 Google Patents — {label}")
        parts.append("| 专利号 | 标题 |")
        parts.append("|--------|------|")
        for item in items:
            pid = item.get("id", "")
            title = (item.get("title", "") or "")[:100]
            parts.append(f"| {pid} | {title} |")
        parts.append("")

    # ── Lens.org 结果 ──
    lens_results = results.get("lens", []) or []
    if lens_results:
        parts.append("### 🔬 Lens.org 全球专利")
        for item in lens_results[:6]:
            parts.append(f"- **{item.get('id', '')}**: {item.get('title', '')[:100]}")
            if item.get("abstract"):
                parts.append(f"  {item['abstract'][:200]}")
        parts.append("")

    # ── WIPO ──
    wipo = results.get("wipo", []) or []
    if wipo:
        parts.append("### 🌐 WIPO 国际申请")
        for w in wipo[:5]:
            parts.append(f"- {w.get('id', '')}")
        parts.append("")

    # ── 专利详情（摘要 + 权利要求）──
    details = results.get("_patent_details", {})
    if details:
        parts.append("### 📄 专利详情（Google Patents 提取）")
        for pid, detail in list(details.items())[:8]:
            parts.append(f"#### {pid} — {detail.get('title', '')[:100]}")
            if detail.get("assignee"):
                parts.append(f"权利人: {detail['assignee']}")
            if detail.get("pub_date"):
                parts.append(f"公开日: {detail['pub_date']}")
            if detail.get("abstract"):
                parts.append(f"摘要: {detail['abstract'][:400]}")
            if detail.get("claims"):
                parts.append(f"权利要求:\n{detail['claims'][:800]}")
            if detail.get("is_design"):
                parts.append(f"📐 类型: 设计专利（外观保护）")
            else:
                parts.append(f"🔧 类型: 发明专利（功能/结构保护）")
            parts.append(f"链接: {detail.get('url', '')}")
            parts.append("")

    # ── Tavily 搜索结果 ──
    tavily_keys = [k for k in results if k.startswith("tavily_")]
    for key in tavily_keys:
        text = results[key]
        if text and isinstance(text, str) and len(text) > 20:
            label = key.replace("tavily_", "").replace("_", " ").title()
            parts.append(f"### 🌐 {label}")
            parts.append(text[:1500])
            parts.append("")

    return "\n".join(parts)[:15000]
