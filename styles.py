"""主题管理：直接使用 ttkbootstrap 内置主题与主题色板，不自定义颜色。"""

import ttkbootstrap as ttkb

# ttkbootstrap 深色主题集合（仅用于菜单分类显示，非配色）
DARK_THEMES = {'cyborg', 'darkly', 'solar', 'superhero', 'vapor'}

# 兜底主题列表（模块级不调 ttkb.Style()，避免与 ttkb.Window 单 root 冲突）
_FALLBACK_THEMES = [
    'cosmo', 'flatly', 'litera', 'lumen', 'minty', 'morph',
    'pulse', 'quartz', 'simplex', 'united', 'yeti', 'journal',
    'cerulean', 'cyborg', 'darkly', 'solar', 'superhero', 'vapor',
]

_current_theme = 'cosmo'
_themes_cache = None


def get_themes():
    """运行时获取 ttkbootstrap 内置主题（须在 root 创建后调用）。"""
    global _themes_cache
    if _themes_cache is None:
        try:
            _themes_cache = list(ttkb.Style().theme_names())
        except Exception:
            _themes_cache = list(_FALLBACK_THEMES)
    return _themes_cache


# 业务色名 -> ttkbootstrap Colors 属性 映射
_NAME_MAP = {
    'recv': 'info', 'send': 'success', 'error': 'danger',
    'timestamp': 'warning', 'success': 'success', 'info': 'info',
    'text': 'fg', 'bg_input': 'inputbg', 'select_bg': 'selectbg',
    'border': 'border', 'background': 'bg', 'accent': 'primary',
}


def get_color(name: str) -> str:
    """从当前 ttkbootstrap 主题色板取色（不自定义颜色表）。"""
    try:
        colors = ttkb.Style().colors
        attr = _NAME_MAP.get(name, 'fg')
        return str(getattr(colors, attr, '#000000'))
    except Exception:
        return '#000000'


def get_theme_type() -> str:
    return 'dark' if _current_theme in DARK_THEMES else 'light'


def get_current_theme() -> str:
    return _current_theme


def set_theme(theme_name: str):
    global _current_theme
    _current_theme = theme_name


def apply_theme(root, theme_name: str = None):
    """切换并应用主题到 root（ttk 控件自动跟随，无需手动配色）。"""
    if theme_name:
        set_theme(theme_name)
    try:
        style = ttkb.Style()
        style.theme_use(_current_theme)
    except Exception:
        style = None
    return style
