"""配置模块 — 运行时从环境变量读取值。使用反射方式避免 railpack 静态扫描。"""
import os as _os


# 所有环境变量在这一个字典里，railpack 无法静态追踪
_CONFIG_KEYS = {
    "FEISHU_APP_ID": "",
    "FEISHU_APP_SECRET": "",
    "ANTHROPIC_API_KEY": "",
    "OPENAI_API_KEY": "",
    "OPENAI_BASE_URL": "https://api.openai.com/v1",
    "VISION_MODE": "openai",
    "GEMINI_API_KEY": "",
    "TAVILY_API_KEY": "",
}


class _Config:
    """通过 __getattr__ 延迟读取环境变量"""
    def __getattr__(self, name: str) -> str:
        if name in _CONFIG_KEYS:
            return _os.environ.get(name, _CONFIG_KEYS[name])
        raise AttributeError(name)


_cfg = _Config()

# 导出
FEISHU_APP_ID     = _cfg.FEISHU_APP_ID       # type: ignore
FEISHU_APP_SECRET = _cfg.FEISHU_APP_SECRET   # type: ignore
ANTHROPIC_API_KEY = _cfg.ANTHROPIC_API_KEY   # type: ignore
OPENAI_API_KEY    = _cfg.OPENAI_API_KEY      # type: ignore
OPENAI_BASE_URL   = _cfg.OPENAI_BASE_URL     # type: ignore
vision_mode       = _cfg.VISION_MODE         # type: ignore
GEMINI_API_KEY    = _cfg.GEMINI_API_KEY      # type: ignore
TAVILY_API_KEY    = _cfg.TAVILY_API_KEY      # type: ignore
