"""延迟加载配置，从环境变量读取（避免 railpack 构建时检测）"""
import os as _os


def _get(key: str, default: str = "") -> str:
    return _os.environ.get(key, default)


FEISHU_APP_ID = _get("FEISHU_APP_ID")
FEISHU_APP_SECRET = _get("FEISHU_APP_SECRET")
ANTHROPIC_API_KEY = _get("ANTHROPIC_API_KEY")
OPENAI_API_KEY = _get("OPENAI_API_KEY")
OPENAI_BASE_URL = _get("OPENAI_BASE_URL", "https://api.openai.com/v1")
vision_mode = _get("VISION_MODE", "openai")
GEMINI_API_KEY = _get("GEMINI_API_KEY", "")
TAVILY_API_KEY = _get("TAVILY_API_KEY", "")
