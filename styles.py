"""主题管理：直接使用 ttkbootstrap 内置主题与主题色板，不自定义颜色。"""

import ttkbootstrap as ttkb

# ttkbootstrap 2.2.2 实际内置主题（模块级不调 ttkb.Style()，避免与 ttkb.Window 单 root 冲突）
_FALLBACK_THEMES = [
    'bootstrap-light', 'bootstrap-dark',
    'pydata-light', 'pydata-dark',
    'nord-light', 'nord-dark',
    'solarized-light', 'solarized-dark',
    'catppuccin-light', 'catppuccin-dark',
    'gruvbox-light', 'gruvbox-dark',
    'dracula-light', 'dracula-dark',
    'tokyo-night-light', 'tokyo-night-dark',
    'one-light', 'one-dark',
    'everforest-light', 'everforest-dark',
    'vapor-light', 'vapor-dark',
    'minty-light', 'minty-dark',
    'pulse-light', 'pulse-dark',
    'united-light', 'united-dark',
    'sandstone-light', 'sandstone-dark',
]

# 主题英文名 -> 中文显示名（贴切意译，基于各主题配色风格）
THEME_LABELS = {
    'bootstrap-light': '经典（浅）',
    'bootstrap-dark': '经典（深）',
    'pydata-light': '数据（浅）',
    'pydata-dark': '数据（深）',
    'nord-light': '极地（浅）',
    'nord-dark': '极地（深）',
    'solarized-light': '日光（浅）',
    'solarized-dark': '日光（深）',
    'catppuccin-light': '奶茶（浅）',
    'catppuccin-dark': '奶茶（深）',
    'gruvbox-light': '复古（浅）',
    'gruvbox-dark': '复古（深）',
    'dracula-light': '德古拉（浅）',
    'dracula-dark': '德古拉（深）',
    'tokyo-night-light': '东京夜（浅）',
    'tokyo-night-dark': '东京夜（深）',
    'one-light': '极简（浅）',
    'one-dark': '极简（深）',
    'everforest-light': '常青（浅）',
    'everforest-dark': '常青（深）',
    'vapor-light': '蒸汽波（浅）',
    'vapor-dark': '蒸汽波（深）',
    'minty-light': '薄荷（浅）',
    'minty-dark': '薄荷（深）',
    'pulse-light': '脉冲（浅）',
    'pulse-dark': '脉冲（深）',
    'united-light': '联合（浅）',
    'united-dark': '联合（深）',
    'sandstone-light': '砂岩（浅）',
    'sandstone-dark': '砂岩（深）',
}

_current_theme = 'bootstrap-light'
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


def is_dark_theme(theme_name: str = None) -> bool:
    """以 -dark 后缀判断深色主题（ttkbootstrap 2.2.2 命名约定）"""
    name = theme_name if theme_name is not None else _current_theme
    return name.endswith('-dark')


# 业务色名 -> ttkbootstrap Colors 属性 映射
_NAME_MAP = {
    'recv': 'info', 'send': 'success', 'error': 'danger',
    'timestamp': 'warning', 'success': 'success', 'info': 'info',
    'text': 'fg', 'bg_input': 'inputbg', 'select_bg': 'selectbg',
    'select_fg': 'selectfg',
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
    return 'dark' if is_dark_theme() else 'light'


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
