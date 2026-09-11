from typing import List, Dict
import json
import os
import sys


def _get_app_dir():
    """获取程序所在目录（兼容 PyInstaller 打包）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


class CommandManager:
    """命令管理模块 - 多页面多命令发送

    数据结构（与旧版 history.json 兼容）：
      page_order: List[str]              页面顺序
      pages: Dict[str, List[dict]]       每页命令列表
        每条命令: {
            "mode": "string"|"hex",
            "content": 原始输入文本（不转义）,
            "label": 可选标签/注释,
            "timestamp": 创建/修改时间（仅记录用）
        }
    """

    def __init__(self):
        self.history_file = os.path.join(_get_app_dir(), "cmd.json")
        self.pages: Dict[str, List[dict]] = {}
        self.page_order: List[str] = []
        self.load_commands()

    def _ensure_default_page(self):
        """确保至少有一个默认页面"""
        if not self.page_order:
            self.pages["默认"] = []
            self.page_order = ["默认"]

    # ==================== 命令增删改 ====================

    def add_command(self, content: str, mode: str, label: str = "",
                    page: str = None) -> None:
        """添加一条命令到指定页面（追加到末尾，不去重，不上限）

        Args:
            content: 命令原始内容（不转义）
            mode: 'string' 或 'hex'
            label: 可选标签
            page: 目标页面名，None 则使用当前活动页面
        """
        self._ensure_default_page()
        if page is None or page not in self.pages:
            page = self.page_order[0]

        from datetime import datetime
        item = {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "content": content,
            "label": (label or "").strip(),
        }
        self.pages[page].append(item)
        self.save_commands()

    def update_command(self, page: str, index: int,
                       content: str, mode: str, label: str = "") -> bool:
        """编辑指定页面中某条命令，成功返回 True"""
        if page not in self.pages or not (0 <= index < len(self.pages[page])):
            return False
        from datetime import datetime
        self.pages[page][index] = {
            "timestamp": datetime.now().isoformat(),
            "mode": mode,
            "content": content,
            "label": (label or "").strip(),
        }
        self.save_commands()
        return True

    def remove_command(self, page: str, index: int) -> None:
        """从指定页面删除指定索引的命令"""
        if page in self.pages and 0 <= index < len(self.pages[page]):
            del self.pages[page][index]
            self.save_commands()

    def insert_command(self, page: str, index: int, item: dict) -> None:
        """将命令 dict 插入指定页面的指定位置（越界则追加到末尾）"""
        self._ensure_default_page()
        if page is None or page not in self.pages:
            page = self.page_order[0]
        cmds = self.pages[page]
        if not (0 <= index <= len(cmds)):
            index = len(cmds)
        cmds.insert(index, dict(item))
        self.save_commands()

    # ==================== 查询 ====================

    def get_command_display_list(self, page: str = None) -> List[str]:
        """获取指定页面的命令显示列表（用于 Listbox）"""
        self._ensure_default_page()
        if page is None or page not in self.pages:
            page = self.page_order[0]

        result = []
        for item in self.pages[page]:
            label = (item.get("label") or "").strip()
            content = item.get("content", "")
            display_content = self._escape_for_display(content)
            if label:
                result.append(f'[{item["mode"].upper()}] *{label}')
            else:
                result.append(f'[{item["mode"].upper()}] {display_content}')
        return result

    def get_full_commands(self, page: str = None) -> List[dict]:
        """获取指定页面的完整命令列表"""
        self._ensure_default_page()
        if page is None or page not in self.pages:
            page = self.page_order[0]
        return self.pages[page]

    @staticmethod
    def _escape_for_display(text: str) -> str:
        """将不可见字符转义为可见形式（用于列表显示）"""
        return text.replace('\r', '\\r').replace('\n', '\\n').replace('\t', '\\t')

    # ==================== 页面管理 ====================

    def add_page(self, name: str) -> bool:
        """添加新页面，成功返回 True"""
        if name in self.pages:
            return False
        self.pages[name] = []
        self.page_order.append(name)
        self.save_commands()
        return True

    def remove_page(self, name: str) -> None:
        """删除页面（至少保留一个）"""
        if len(self.page_order) <= 1:
            return
        if name in self.pages:
            del self.pages[name]
            self.page_order.remove(name)
            self.save_commands()

    def rename_page(self, old_name: str, new_name: str) -> bool:
        """重命名页面，成功返回 True"""
        if old_name not in self.pages or new_name in self.pages or not new_name.strip():
            return False
        self.pages[new_name] = self.pages.pop(old_name)
        idx = self.page_order.index(old_name)
        self.page_order[idx] = new_name
        self.save_commands()
        return True

    def get_pages(self) -> List[str]:
        """获取页面名列表"""
        self._ensure_default_page()
        return list(self.page_order)

    # ==================== 持久化 ====================

    def save_commands(self) -> None:
        """保存命令到文件"""
        try:
            data = {
                "page_order": self.page_order,
                "pages": self.pages
            }
            with open(self.history_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_commands(self) -> None:
        """从文件加载命令"""
        try:
            if os.path.exists(self.history_file):
                with open(self.history_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict) and "page_order" in data:
                    self.page_order = data["page_order"]
                    self.pages = data["pages"]
                else:
                    # 兼容旧格式（单列表）
                    self.pages = {"默认": data if isinstance(data, list) else []}
                    self.page_order = ["默认"]
                self._ensure_default_page()
        except Exception:
            self.pages = {}
            self.page_order = []
            self._ensure_default_page()
