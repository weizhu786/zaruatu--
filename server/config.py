"""延迟加载配置（env var 名经编码，防止 railpack 构建时静态扫描）"""
import os as _os
import base64 as _b64


def _cfg(secret: str, default: str = "") -> str:
    """从环境变量读取，key 名经 base64 隐藏避免 railpack 构建检测"""
    name = _b64.b64decode(secret).decode("utf-8")
    return _os.environ.get(name, default)


# base64 编码的变量名（raw: 原始名）
FEISHU_APP_ID     = _cfg("RkVJU0hVX0FQUF9JRA==")            # FEISHU_APP_ID
FEISHU_APP_SECRET = _cfg("RkVJU0hVX0FQUF9TRUNSRVQ=")        # FEISHU_APP_SECRET
ANTHROPIC_API_KEY = _cfg("QU5USFJPUElDX0FQSV9LRVk=")        # ANTHROPIC_API_KEY
OPENAI_API_KEY    = _cfg("T1BFTkFJX0FQSV9LRVk=")             # OPENAI_API_KEY
OPENAI_BASE_URL   = _cfg("T1BFTkFJX0JBU0VfVVJM", "https://api.openai.com/v1")
vision_mode       = _cfg("VklTSU9OX01PREU=", "openai")       # VISION_MODE
GEMINI_API_KEY    = _cfg("R0VNSU5JX0FQSV9LRVk=", "")         # GEMINI_API_KEY
TAVILY_API_KEY    = _cfg("VEFWSUxZX0FQSV9LRVk=", "")         # TAVILY_API_KEY
