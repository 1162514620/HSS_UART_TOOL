import tkinter as tk
import tkinter.font as tkfont
import ttkbootstrap as ttk
from tkinter import messagebox, filedialog, simpledialog
import os
import sys
import json
import re
import struct
import time
import csv
from collections import deque
from datetime import datetime

from serial_manager import SerialManager
from receive_thread import ReceiveThread
from command_manager import CommandManager
from i18n import t, set_language, get_language
from styles import (get_color, set_theme, get_current_theme, apply_theme,
                    get_themes, THEME_LABELS, is_dark_theme, get_theme_type)


def _get_app_dir():
    """获取程序所在目录（兼容 PyInstaller 打包）"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


SETTINGS_FILE = os.path.join(_get_app_dir(), "settings.json")

BAUDRATES = ['300', '600', '1200', '2400', '4800', '9600',
             '19200', '38400', '57600', '115200', '230400', '460800', '921600']
ENCODINGS = ['UTF-8', 'GB2312', 'GBK', 'GB18030', 'Big5', 'ASCII']

# 接收区缓存上限（条），避免长时间运行内存无限增长
MAX_RECEIVED_DATA = 10000


class MainWindow:
    # ==================== 初始化 ====================

    def __init__(self, root):
        self.root = root
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

        # 提前读取语言设置，确保首次创建 UI 即为用户选择的语言
        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                set_language(json.load(f).get('language', 'zh'))
        except Exception:
            pass

        # 核心组件
        self.serial_manager = SerialManager()
        self.command_manager = CommandManager()
        self.receive_thread = None

        # 状态
        self.is_connected = False
        self.is_paused = False
        self.last_ports = []

        # 波形
        self.waveform_data = []
        self.waveform_max_points = 1000
        self.waveform_bytesize = 2
        self.waveform_endian = 'little'
        self.waveform_window = None
        self.waveform_fig = None
        self.waveform_ax = None
        self.waveform_line = None
        self.waveform_canvas = None
        self.waveform_update_pending = False

        # 日志
        self.log_file = None
        self.log_writer = None
        self.log_file_path = ""
        self.log_start_time = None
        self.log_file_size = 0
        self.max_log_size = 10 * 1024 * 1024

        # 自动重连
        self.reconnect_count = 0
        self.reconnect_timer_id = None

        # 发送
        self.recv_bytes = 0
        self.sent_bytes = 0
        self.received_data = deque(maxlen=MAX_RECEIVED_DATA)
        self.send_queue = []
        self.is_sending = False
        self.send_success_rate = 1.0
        self.send_history_results = []
        self.last_send_time = 0

        # 循环发送
        self.loop_timer_id = None
        self.loop_sent_count = 0

        # 串口扫描
        self.scan_timer_id = None

        # tkinter 变量
        self.port_var = tk.StringVar()
        self.baudrate_var = tk.StringVar(value='115200')
        self.databits_var = tk.StringVar(value='8')
        self.stopbits_var = tk.StringVar(value='1')
        self.parity_var = tk.StringVar(value='None')
        self.rtscts_var = tk.BooleanVar(value=False)
        self.encoding_var = tk.StringVar(value='GB2312')
        self.send_encoding_var = tk.StringVar(value='GB2312')
        self.timestamp_var = tk.BooleanVar(value=True)
        self.hex_addr_var = tk.BooleanVar(value=False)
        self.hex_newline_count_var = tk.IntVar(value=0)
        self.direction_var = tk.BooleanVar(value=True)
        self.echo_var = tk.BooleanVar(value=True)
        self.auto_escape_var = tk.BooleanVar(value=False)
        self.crlf_var = tk.BooleanVar(value=False)
        self.auto_wrap_var = tk.BooleanVar(value=False)
        self.loop_var = tk.BooleanVar(value=False)
        self.loop_interval_var = tk.IntVar(value=1000)
        self.loop_count_var = tk.IntVar(value=0)
        self.auto_reconnect_var = tk.BooleanVar(value=False)
        self.reconnect_interval_var = tk.IntVar(value=5)
        self.reconnect_max_var = tk.IntVar(value=10)

        # 校验自动添加
        self.checksum_enable_var = tk.BooleanVar(value=False)
        self.checksum_start_var = tk.IntVar(value=0)
        self.checksum_end_var = tk.StringVar(value=t('末尾'))
        self.checksum_type_var = tk.StringVar(value='ADD8')

        # 帧头帧尾
        self.frame_enable_var = tk.BooleanVar(value=False)
        self.frame_header_content_var = tk.StringVar(value='')
        self.frame_footer_content_var = tk.StringVar(value='')
        self.frame_hex_var = tk.BooleanVar(value=False)  # True=HEX模式, False=字符串模式

        # 自动应答
        self.auto_reply_enabled = False
        self.auto_reply_rules = []

        self.waveform_settings = {}

        self.init_ui()
        self.refresh_ports_ui()
        # 窗口显示后再自动扫描一次串口（部分USB转串口设备枚举较慢）
        self.root.after(300, self.refresh_ports_ui)
        self.start_port_scan()

    def init_ui(self):
        self.create_menu_bar()
        self.create_serial_control_bar()
        self.create_main_content()
        self.create_status_bar()
        self.setup_connections()
        self.load_settings()
        # 兜底：确保非 ttk 控件按当前主题配色（load_settings 未必触发）
        self.on_theme_applied()

    # ==================== 菜单栏 ====================

    def create_menu_bar(self):
        menubar = tk.Menu(self.root)
        self.root.config(menu=menubar)

        data_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("数据"), menu=data_menu)
        data_menu.add_command(label=t("导出数据"), command=self.export_data)
        data_menu.add_command(label=t("数据记录"), command=self.show_record_dialog)

        # 主题菜单（使用 ttkbootstrap 内置主题，显示贴切中文名）
        theme_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("主题"), menu=theme_menu)

        all_themes = get_themes()
        dark_themes = sorted([th for th in all_themes if is_dark_theme(th)])
        light_themes = sorted([th for th in all_themes if not is_dark_theme(th)])

        theme_menu.add_command(label=t("── 深色主题 ──"), state='disabled')
        for theme_name in dark_themes:
            theme_menu.add_command(
                label=f"    {t(THEME_LABELS.get(theme_name, theme_name))}",
                command=lambda th=theme_name: self.set_theme(th))

        theme_menu.add_separator()
        theme_menu.add_command(label=t("── 浅色主题 ──"), state='disabled')
        for theme_name in light_themes:
            theme_menu.add_command(
                label=f"    {t(THEME_LABELS.get(theme_name, theme_name))}",
                command=lambda th=theme_name: self.set_theme(th))

        # 编码菜单
        encoding_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("编码"), menu=encoding_menu)

        recv_enc_menu = tk.Menu(encoding_menu, tearoff=0)
        encoding_menu.add_cascade(label=t("接收编码"), menu=recv_enc_menu)
        for enc in ENCODINGS:
            recv_enc_menu.add_radiobutton(
                label=enc, variable=self.encoding_var, value=enc,
                command=self.save_settings)

        encoding_menu.add_separator()

        send_enc_menu = tk.Menu(encoding_menu, tearoff=0)
        encoding_menu.add_cascade(label=t("发送编码"), menu=send_enc_menu)
        for enc in ENCODINGS:
            send_enc_menu.add_radiobutton(
                label=enc, variable=self.send_encoding_var, value=enc,
                command=self.save_settings)

        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("设置"), menu=settings_menu)
        settings_menu.add_command(
            label=t("自动重连设置"), command=self.show_reconnect_settings_dialog)
        settings_menu.add_separator()
        settings_menu.add_checkbutton(label=t("地址偏移"), variable=self.hex_addr_var,
                                      command=self.save_settings)
        settings_menu.add_command(
            label=t("HEX换行字节数..."), command=self._show_hex_newline_dialog)

        # 扩展菜单
        extend_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("扩展"), menu=extend_menu)
        extend_menu.add_command(label=t("波形显示"), command=self.toggle_waveform)

        # 语言菜单（切换中英文，重建 UI）
        lang_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label=t("语言"), menu=lang_menu)
        self.language_var = tk.StringVar(value=get_language())
        for code, label in (('zh', '中文'), ('en', 'English')):
            lang_menu.add_radiobutton(
                label=label, variable=self.language_var,
                value=code, command=self._switch_language)

    # ==================== 串口控制栏 ====================

    def create_serial_control_bar(self):
        """在接收区上方添加串口控制栏"""
        self.ctrl_frame = ttk.LabelFrame(self.root, text=t("串口控制"))
        self.ctrl_frame.pack(fill=tk.X, padx=6, pady=(6, 2))

        row1 = ttk.Frame(self.ctrl_frame)
        row1.pack(fill=tk.X, padx=4, pady=(4, 2))

        ttk.Label(row1, text=t("串口:")).pack(side=tk.LEFT, padx=(0, 2))
        self.port_combo = ttk.Combobox(row1, textvariable=self.port_var,
                                       state='readonly', width=20)
        self.port_combo.pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text=t("刷新"), command=self.refresh_ports_ui,
                   width=5).pack(side=tk.LEFT, padx=2)

        ttk.Separator(row1, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(row1, text=t("波特率:")).pack(side=tk.LEFT, padx=(0, 2))
        self.baudrate_combo = ttk.Combobox(row1, textvariable=self.baudrate_var,
                                           values=BAUDRATES, width=8)
        self.baudrate_combo.pack(side=tk.LEFT, padx=2)

        ttk.Separator(row1, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(row1, text=t("校验:")).pack(side=tk.LEFT, padx=(0, 2))
        self.parity_combo = ttk.Combobox(row1, textvariable=self.parity_var,
                                         values=['None', 'Even',
                                                 'Odd', 'Mark', 'Space'],
                                         state='readonly', width=7)
        self.parity_combo.pack(side=tk.LEFT, padx=2)

        ttk.Separator(row1, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        self.connect_btn = ttk.Button(row1, text=t("连接"),
                                      command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT, padx=4)

        ttk.Button(row1, text=t("更多设置"), command=self.show_serial_settings_dialog).pack(
            side=tk.LEFT, padx=2)

    def refresh_ports_ui(self):
        """刷新串口列表（更新UI控件）"""
        ports = self.serial_manager.scan_ports()
        self.last_ports = ports
        values = [f"{n} - {d}" for n, d in ports]
        self.port_combo['values'] = values
        # 当前选中端口不在新列表中时，改选第一个可用端口
        if values and self.port_var.get() not in values:
            self.port_combo.current(0)
        elif not values:
            self.port_var.set('')

    # ==================== 主内容区 ====================

    def create_main_content(self):
        """创建主内容区：PanedWindow 左右分割，拖动 sash 改变右侧面板宽度"""
        self.content_pw = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        self.content_pw.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)

        # 左侧：接收区 + 发送区
        self.left_frame = ttk.Frame(self.content_pw)
        # weight=1：窗口大小变化时多余空间分配给左侧，右侧面板宽度保持用户设置值
        self.content_pw.add(self.left_frame, weight=1)

        self.create_receive_area(self.left_frame)
        self.create_send_area(self.left_frame)

        # 右侧：多命令发送 / 自动应答
        self.create_command_panel(self.content_pw)

    # ==================== 接收区 ====================

    def create_receive_area(self, parent):
        """创建接收区，操作按键在文本框下方"""
        self.recv_frame = ttk.LabelFrame(parent, text=t("接收区"))
        self.recv_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=(0, 2))

        # Notebook (字符串/HEX 选项卡) - 占据主要空间
        self.recv_notebook = ttk.Notebook(self.recv_frame)
        self.recv_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))

        # 字符串选项卡
        string_tab = ttk.Frame(self.recv_notebook)
        self.recv_notebook.add(string_tab, text=t("字符串"))
        self.string_recv_text = self._create_scrolled_text(string_tab)

        # HEX 选项卡
        hex_tab = ttk.Frame(self.recv_notebook)
        self.recv_notebook.add(hex_tab, text="HEX")
        self.hex_recv_text = self._create_scrolled_text(hex_tab)

        # 对照选项卡（HEX 与字符串一上一下同时显示）
        compare_tab = ttk.Frame(self.recv_notebook)
        self.recv_notebook.add(compare_tab, text=t("对照"))
        self.compare_recv_text = self._create_scrolled_text(compare_tab)

        # 配置文本标签颜色
        self._configure_text_tags(self.string_recv_text)
        self._configure_text_tags(self.hex_recv_text)
        self._configure_text_tags(self.compare_recv_text)

        # 操作工具栏 - 在文本框下方
        toolbar = ttk.Frame(self.recv_frame)
        toolbar.pack(fill=tk.X, padx=4, pady=(0, 4))

        ttk.Button(toolbar, text=t("清空接收区"), command=self.clear_receive_area).pack(
            side=tk.LEFT, padx=2)
        self.pause_btn = ttk.Button(
            toolbar, text=t("暂停显示"), command=self.toggle_pause)
        self.pause_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Checkbutton(toolbar, text=t("时间戳"), variable=self.timestamp_var).pack(
            side=tk.LEFT, padx=2)
        ttk.Checkbutton(toolbar, text=t("方向"), variable=self.direction_var).pack(
            side=tk.LEFT, padx=2)
        ttk.Checkbutton(toolbar, text=t("回显"), variable=self.echo_var).pack(
            side=tk.LEFT, padx=2)
        ttk.Checkbutton(toolbar, text=t("自动换行"), variable=self.auto_wrap_var,
                        command=self._toggle_auto_wrap).pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(toolbar, text=t("超时:")).pack(side=tk.LEFT)
        # 语言切换重建 UI 时保留原超时值与 trace（变量随 root 存活）
        if not hasattr(self, 'recv_timeout_var'):
            self.recv_timeout_var = tk.IntVar(value=0)
            self.recv_timeout_var.trace_add('write', self._on_recv_timeout_changed)
        ttk.Spinbox(toolbar, from_=0, to=10000,
                    textvariable=self.recv_timeout_var, width=8).pack(
                        side=tk.LEFT, padx=2)
        ttk.Label(toolbar, text=t("ms(0=自动)")).pack(side=tk.LEFT)

    # ==================== 发送区 ====================

    def create_send_area(self, parent):
        """创建发送区（不含历史记录，历史在右侧）"""
        self.send_frame = ttk.LabelFrame(parent, text=t("发送区"))
        self.send_frame.pack(fill=tk.X, padx=0, pady=(2, 0))

        # Notebook (字符串/HEX 输入)
        self.send_notebook = ttk.Notebook(self.send_frame)
        self.send_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))

        # 字符串输入
        str_tab = ttk.Frame(self.send_notebook)
        self.send_notebook.add(str_tab, text=t("字符串"))
        self.string_input = tk.Text(str_tab, height=4, wrap=tk.WORD, undo=True,
                                    font=('Consolas', 10))
        self.string_input.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.string_input.insert('1.0', '')

        # HEX 输入
        hex_tab = ttk.Frame(self.send_notebook)
        self.send_notebook.add(hex_tab, text="Hex")
        self.hex_input = tk.Text(hex_tab, height=4, wrap=tk.NONE, undo=True,
                                 font=('Consolas', 10))
        self.hex_input.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.hex_status_label = ttk.Label(
            hex_tab, text="", foreground=get_color('error'))
        self.hex_status_label.pack(fill=tk.X, padx=2)

        # 工具栏
        toolbar = ttk.Frame(self.send_frame)
        toolbar.pack(fill=tk.X, padx=4, pady=(0, 4))

        self.send_btn = ttk.Button(toolbar, text=t(" 发送 "),
                                   command=self.send_data)
        self.send_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)
        self.auto_escape_cb = ttk.Checkbutton(toolbar, text=t("自动转义"), variable=self.auto_escape_var)
        self.auto_escape_cb.pack(side=tk.LEFT, padx=2)
        self.crlf_cb = ttk.Checkbutton(toolbar, text=t("回车换行"), variable=self.crlf_var)
        self.crlf_cb.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Checkbutton(toolbar, text=t("循环发送"), variable=self.loop_var,
                        command=self._on_loop_toggle).pack(side=tk.LEFT, padx=2)
        ttk.Label(toolbar, text=t("间隔:")).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Spinbox(toolbar, from_=1, to=60000, textvariable=self.loop_interval_var,
                    width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(toolbar, text="ms").pack(side=tk.LEFT)
        ttk.Label(toolbar, text=t("次数:")).pack(side=tk.LEFT, padx=(8, 0))
        ttk.Spinbox(toolbar, from_=0, to=999999, textvariable=self.loop_count_var,
                    width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(toolbar, text=t("(0=无限)")).pack(side=tk.LEFT)

        # 校验自动添加行
        checksum_row = ttk.Frame(self.send_frame)
        checksum_row.pack(fill=tk.X, padx=4, pady=(0, 4))

        self.checksum_checkbtn = ttk.Checkbutton(checksum_row, text=t("校验"), variable=self.checksum_enable_var)
        self.checksum_checkbtn.pack(side=tk.LEFT, padx=2)
        ttk.Label(checksum_row, text=t("第")).pack(side=tk.LEFT, padx=(4, 0))
        self.checksum_start_spin = ttk.Spinbox(checksum_row, from_=0, to=9999,
                    textvariable=self.checksum_start_var, width=4)
        self.checksum_start_spin.pack(side=tk.LEFT, padx=2)
        ttk.Label(checksum_row, text=t("字节到第")).pack(side=tk.LEFT)
        # 组合框值为翻译文本；语言切换时把旧语言的"末尾"迁移到新语言
        if self.checksum_end_var.get() in ('末尾', 'End'):
            self.checksum_end_var.set(t('末尾'))
        self.checksum_end_combo = ttk.Combobox(checksum_row, textvariable=self.checksum_end_var,
                     values=[t('末尾'), '-1', '-2', '-3', '-4'], width=4,
                     state='readonly')
        self.checksum_end_combo.pack(side=tk.LEFT, padx=2)
        ttk.Label(checksum_row, text=t("字节")).pack(side=tk.LEFT)
        self.checksum_type_combo = ttk.Combobox(checksum_row, textvariable=self.checksum_type_var,
                     values=['ADD8', 'ADD16', 'XOR8', 'ModBusCRC16'],
                     width=12, state='readonly')
        self.checksum_type_combo.pack(side=tk.LEFT, padx=(8, 2))

        # 帧头帧尾行
        frame_row = ttk.Frame(self.send_frame)
        frame_row.pack(fill=tk.X, padx=4, pady=(0, 4))

        ttk.Checkbutton(frame_row, text=t("添加帧头帧尾"), variable=self.frame_enable_var).pack(
            side=tk.LEFT, padx=2)
        ttk.Label(frame_row, text=t("帧头:")).pack(side=tk.LEFT, padx=(4, 0))
        self.frame_header_entry = ttk.Entry(frame_row, textvariable=self.frame_header_content_var,
                                            width=10, font=('Consolas', 9))
        self.frame_header_entry.pack(side=tk.LEFT, padx=2)
        ttk.Label(frame_row, text=t("帧尾:")).pack(side=tk.LEFT, padx=(4, 0))
        self.frame_footer_entry = ttk.Entry(frame_row, textvariable=self.frame_footer_content_var,
                                            width=10, font=('Consolas', 9))
        self.frame_footer_entry.pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(frame_row, text="HEX", variable=self.frame_hex_var).pack(
            side=tk.LEFT, padx=(6, 2))

    # ==================== 多命令发送面板 ====================

    def create_command_panel(self, parent):
        """创建右侧面板（多命令发送 / 自动应答 切换）

        parent: Panedwindow，通过 add() 加入为窗格，支持原生 sash 拖动
        """
        # 语言切换重建 UI 时保留用户设置的宽度
        if not hasattr(self, 'hist_panel_width'):
            self.hist_panel_width = 220
        # 命令行选中高亮样式（依赖主题色板，重建/换主题时重新配置）
        self._config_cmd_selection_style()
        self.hist_frame = ttk.LabelFrame(parent, text=t("功能面板"))
        parent.add(self.hist_frame)
        self.hist_frame.configure(width=self.hist_panel_width)
        # 拖动 sash 改变宽度后同步宽度变量/设置
        # （sash 属于 Panedwindow 本体，绑定其上精确捕获拖动；
        #   不用 hist_frame 的 <Configure>，避免窗口缩放引起的宽度变化误存为设置值）
        try:
            parent.bind('<B1-Motion>', self._sync_hist_width_from_sash)
            parent.bind('<ButtonRelease-1>', self._sync_hist_width_from_sash)
        except Exception:
            pass

        # 顶层 Tab：多命令发送 / 自动应答
        self.func_notebook = ttk.Notebook(self.hist_frame)
        self.func_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # === 多命令发送 Tab ===
        cmd_tab = ttk.Frame(self.func_notebook)
        self.func_notebook.add(cmd_tab, text=t("多命令发送"))

        # 页面操作按钮行（新增页面 / 删除页面）——位于页面选择行上方
        page_ops = ttk.Frame(cmd_tab)
        page_ops.pack(fill=tk.X, padx=2, pady=(2, 2))
        ttk.Button(page_ops, text=t("新增页面"),
                   command=self._add_new_command_page).pack(
                       side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(page_ops, text=t("删除页面"),
                   command=self._delete_current_command_page).pack(
                       side=tk.LEFT, fill=tk.X, expand=True)

        # 页面选择器（Combobox + 重命名按钮）——解决多页面 Tab 头拥挤问题
        page_top = ttk.Frame(cmd_tab)
        page_top.pack(fill=tk.X, padx=2, pady=(0, 2))
        ttk.Label(page_top, text=t("页面:")).pack(side=tk.LEFT)
        self.page_selector = ttk.Combobox(
            page_top, state='readonly', values=self.command_manager.get_pages())
        self.page_selector.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(2, 2))
        self.page_selector.bind(
            '<<ComboboxSelected>>', self._on_page_selector_changed)
        ttk.Button(page_top, text=t("重命名"), width=6,
                   command=self._rename_current_page).pack(side=tk.LEFT)

        # 中部：命令内容容器（Frame 叠放，切页时 pack 对应容器）
        self.page_content = ttk.Frame(cmd_tab)
        self.page_content.pack(fill=tk.BOTH, expand=True, padx=2)

        self.command_widgets: dict = {}   # page_name -> list of {'entry': Entry, 'btn': Button, 'frame': Frame}
        self.command_canvases: dict = {}  # page_name -> Canvas
        self._cmd_frames: dict = {}      # page_name -> Canvas 内命令行容器 Frame
        self._page_frames: dict = {}     # page_name -> content Frame
        self._mousewheel_funcs: dict = {} # page_name -> 鼠标滚轮函数
        self._cmd_send_headers: dict = {} # page_name -> "发送按钮"表头标签（随按钮宽度同步）
        self._current_page_idx = 0
        self._selected_cmd_index = None  # 当前选中的命令索引
        self._cmd_clipboard = None       # 命令剪切板（右键复制/剪切/粘贴用）

        for page_name in self.command_manager.get_pages():
            self._add_command_tab(page_name)
        if self.command_manager.get_pages():
            self._switch_to_page(0)

        # 底部按钮：添加命令（直接在末尾追加空命令行）
        cmd_bottom = ttk.Frame(cmd_tab)
        cmd_bottom.pack(fill=tk.X, padx=2, pady=(0, 2))

        ttk.Button(cmd_bottom, text=t("添加命令"),
                   command=self._add_command_to_current_page).pack(fill=tk.X)

        # === 自动应答 Tab ===
        self._create_auto_reply_tab()

        # 面板底部：宽度设置
        bottom = ttk.Frame(self.hist_frame)
        bottom.pack(fill=tk.X, padx=4, pady=(0, 4))
        width_row = ttk.Frame(bottom)
        width_row.pack(fill=tk.X)
        # 页面宽度
        ttk.Label(width_row, text=t("页面宽度:")).pack(side=tk.LEFT)
        self.hist_width_var = tk.IntVar(value=self.hist_panel_width)
        ttk.Spinbox(width_row, from_=100, to=500, textvariable=self.hist_width_var,
                    width=5).pack(side=tk.LEFT, padx=2)
        # 按钮宽度
        ttk.Label(width_row, text=t("按钮宽度:")).pack(side=tk.LEFT, padx=(8, 0))
        self.cmd_btn_width_var = tk.IntVar(value=4)
        ttk.Spinbox(width_row, from_=2, to=999, textvariable=self.cmd_btn_width_var,
                    width=4).pack(side=tk.LEFT, padx=2)
        # 应用按钮（两者共用）
        ttk.Button(width_row, text=t("应用"), width=4,
                   command=self._apply_cmd_panel_widths).pack(side=tk.LEFT, padx=(4, 0))

    def _create_auto_reply_tab(self):
        """创建自动应答 Tab"""
        reply_tab = ttk.Frame(self.func_notebook)
        self.func_notebook.add(reply_tab, text=t("自动应答"))

        # 开启/关闭按钮
        top_row = ttk.Frame(reply_tab)
        top_row.pack(fill=tk.X, padx=2, pady=2)
        self.auto_reply_btn = ttk.Button(top_row, text=t("开启自动应答"),
                                         command=self._toggle_auto_reply)
        self.auto_reply_btn.pack(fill=tk.X)

        # 规则列表（ttk.Treeview 多列表头，外观随主题统一）
        list_frame = ttk.Frame(reply_tab)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)

        scroll = ttk.Scrollbar(list_frame, orient=tk.VERTICAL)
        self.reply_rules_list = ttk.Treeview(
            list_frame, yscrollcommand=scroll.set,
            selectmode='browse', show='headings',
            columns=('status', 'mode', 'trigger', 'reply'))
        self.reply_rules_list.heading('status', text=t('状态'))
        self.reply_rules_list.heading('mode', text=t('模式'))
        self.reply_rules_list.heading('trigger', text=t('触发'))
        self.reply_rules_list.heading('reply', text=t('响应'))
        self.reply_rules_list.column('status', width=44, anchor='center', stretch=False)
        self.reply_rules_list.column('mode', width=50, anchor='center', stretch=False)
        self.reply_rules_list.column('trigger', anchor='w', stretch=True)
        self.reply_rules_list.column('reply', anchor='w', stretch=True)
        scroll.configure(command=self.reply_rules_list.yview)
        self.reply_rules_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.reply_rules_list.bind('<Double-Button-1>', self._edit_reply_rule)
        self.reply_rules_list.bind('<Button-3>', self._reply_rule_context_menu)

        # 添加/删除按钮
        btn_row = ttk.Frame(reply_tab)
        btn_row.pack(fill=tk.X, padx=2, pady=2)
        ttk.Button(btn_row, text=t("添加规则"),
                   command=self._add_reply_rule).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(btn_row, text=t("删除规则"),
                   command=self._delete_reply_rule).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _toggle_auto_reply(self):
        self.auto_reply_enabled = not self.auto_reply_enabled
        if self.auto_reply_enabled:
            self.auto_reply_btn.configure(text=t("关闭自动应答"))
        else:
            self.auto_reply_btn.configure(text=t("开启自动应答"))

    def _add_reply_rule(self):
        """添加自动应答规则"""
        dialog = self._create_reply_rule_dialog()
        self.root.wait_window(dialog)

    def _edit_reply_rule(self, event=None):
        """双击编辑规则"""
        idx = self._tree_selected_index(self.reply_rules_list)
        if idx is None or idx >= len(self.auto_reply_rules):
            return
        rule = self.auto_reply_rules[idx]
        dialog = self._create_reply_rule_dialog(rule, idx)
        self.root.wait_window(dialog)

    def _delete_reply_rule(self):
        idx = self._tree_selected_index(self.reply_rules_list)
        if idx is None or idx >= len(self.auto_reply_rules):
            return
        del self.auto_reply_rules[idx]
        # 重建列表以保持 iid 与索引一致
        self._refresh_reply_rules_list()

    def _reply_rule_context_menu(self, event):
        iid = self.reply_rules_list.identify_row(event.y)
        if not iid:
            return
        self.reply_rules_list.selection_remove(
            self.reply_rules_list.selection())
        self.reply_rules_list.selection_set(iid)
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label=t("编辑规则"), command=lambda: self._edit_reply_rule())
        menu.add_command(label=t("删除规则"), command=self._delete_reply_rule)
        menu.tk_popup(event.x_root, event.y_root)

    def _create_reply_rule_dialog(self, rule=None, edit_idx=None):
        """创建/编辑自动应答规则对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title(t("编辑规则") if rule else t("添加规则"))
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # 匹配模式
        row = 0
        ttk.Label(frame, text=t("匹配模式:")).grid(
            row=row, column=0, sticky='w', pady=2)
        match_mode = tk.StringVar(
            value=rule['match_mode'] if rule else 'string')
        ttk.Combobox(frame, textvariable=match_mode,
                     values=['string', 'hex'], width=10,
                     state='readonly').grid(row=row, column=1, sticky='w', pady=2)

        # 匹配内容
        row += 1
        ttk.Label(frame, text=t("匹配内容:")).grid(
            row=row, column=0, sticky='w', pady=2)
        match_content = tk.StringVar(
            value=rule['match_content'] if rule else '')
        ttk.Entry(frame, textvariable=match_content, width=30).grid(
            row=row, column=1, sticky='w', pady=2)

        # 正则
        row += 1
        use_regex = tk.BooleanVar(value=rule.get(
            'use_regex', False) if rule else False)
        ttk.Checkbutton(frame, text=t("使用正则表达式"), variable=use_regex).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=2)

        # 应答模式
        row += 1
        ttk.Label(frame, text=t("应答模式:")).grid(
            row=row, column=0, sticky='w', pady=2)
        reply_mode = tk.StringVar(
            value=rule['reply_mode'] if rule else 'string')
        ttk.Combobox(frame, textvariable=reply_mode,
                     values=['string', 'hex'], width=10,
                     state='readonly').grid(row=row, column=1, sticky='w', pady=2)

        # 应答内容
        row += 1
        ttk.Label(frame, text=t("应答内容:")).grid(
            row=row, column=0, sticky='w', pady=2)
        reply_content = tk.StringVar(
            value=rule['reply_content'] if rule else '')
        ttk.Entry(frame, textvariable=reply_content, width=30).grid(
            row=row, column=1, sticky='w', pady=2)

        # 延时
        row += 1
        ttk.Label(frame, text=t("延时(ms):")).grid(
            row=row, column=0, sticky='w', pady=2)
        delay = tk.IntVar(value=rule.get('delay', 100) if rule else 100)
        ttk.Spinbox(frame, from_=0, to=60000, textvariable=delay, width=8).grid(
            row=row, column=1, sticky='w', pady=2)

        # 启用
        row += 1
        enabled = tk.BooleanVar(value=rule.get(
            'enabled', True) if rule else True)
        ttk.Checkbutton(frame, text=t("启用此规则"), variable=enabled).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=2)

        # 按钮
        row += 1
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(10, 0))

        def on_ok():
            mc = match_content.get().strip()
            rc = reply_content.get().strip()
            if not mc or not rc:
                messagebox.showwarning(t("提示"), t("匹配内容和应答内容不能为空"), parent=dialog)
                return
            new_rule = {
                'match_mode': match_mode.get(),
                'match_content': mc,
                'use_regex': use_regex.get(),
                'reply_mode': reply_mode.get(),
                'reply_content': rc,
                'delay': delay.get(),
                'enabled': enabled.get(),
            }
            if edit_idx is not None:
                self.auto_reply_rules[edit_idx] = new_rule
            else:
                self.auto_reply_rules.append(new_rule)
            self._refresh_reply_rules_list()
            dialog.destroy()

        ttk.Button(btn_frame, text=t("确定"), command=on_ok).pack(
            side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text=t("取消"), command=dialog.destroy).pack(
            side=tk.LEFT, padx=5)

        self._center_dialog(dialog)
        return dialog

    def _refresh_reply_rules_list(self):
        """刷新自动应答规则列表"""
        tree = self.reply_rules_list
        tree.delete(*tree.get_children())
        for i, rule in enumerate(self.auto_reply_rules):
            status = "ON" if rule.get('enabled', True) else "OFF"
            mode = rule['match_mode'].upper()
            if rule.get('use_regex'):
                mode += " [RE]"
            trigger = rule['match_content']
            reply = rule['reply_content']
            tree.insert('', 'end', iid=str(i),
                        values=(status, mode, trigger, reply))

    def _add_command_tab(self, page_name: str):
        """创建一个命令页面（文本框+发送按钮布局，存入 dict）"""
        container = ttk.Frame(self.page_content)

        # 带滚动条的命令容器
        scroll = ttk.Scrollbar(container, orient=tk.VERTICAL)
        # Canvas 为经典 Tk 控件，不随 ttk 主题，需手动指定主题色背景
        canvas = tk.Canvas(container, highlightthickness=0,
                           bg=get_color('bg_input'))
        scroll.configure(command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)

        # 表头行：标注各列用途（与命令行列对齐）
        header = ttk.Frame(container)
        header.pack(fill=tk.X, padx=2, pady=(0, 1))
        ttk.Label(header, text='', width=3, anchor='center').pack(side=tk.LEFT)
        ttk.Label(header, text='HEX', anchor='center').pack(side=tk.LEFT, padx=(0, 2))
        ttk.Label(header, text=t('命令内容(双击注释)'), anchor='w').pack(
            side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        # 右侧占位宽度同步滚动条实际宽度，使"发送按钮"表头与按钮列对齐
        spacer = ttk.Frame(header, width=13)
        spacer.pack(side=tk.RIGHT)
        send_hdr = ttk.Label(header, text=t('发送按钮'), anchor='center')
        send_hdr.pack(side=tk.RIGHT)
        self._cmd_send_headers[page_name] = send_hdr

        def _sync_spacer(_event=None):
            w = scroll.winfo_width()
            if w > 10:
                spacer.configure(width=w)
        container.bind('<Configure>', _sync_spacer, add='+')

        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 命令行容器
        cmd_frame = ttk.Frame(canvas)
        canvas_window = canvas.create_window((0, 0), window=cmd_frame, anchor='nw')

        # 绑定滚动和调整大小事件
        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 内容不足时禁止滚动到空白区域
            region = canvas.bbox('all')
            if region:
                content_height = region[3] - region[1]
                canvas_height = canvas.winfo_height()
                if content_height < canvas_height:
                    canvas.yview_moveto(0)

        def on_canvas_configure(event):
            canvas.itemconfig(canvas_window, width=event.width)
            # 内容不足时禁止滚动到空白区域
            region = canvas.bbox('all')
            if region:
                content_height = region[3] - region[1]
                canvas_height = event.height
                if content_height < canvas_height:
                    canvas.yview_moveto(0)

        cmd_frame.bind('<Configure>', on_frame_configure)
        canvas.bind('<Configure>', on_canvas_configure)

        # 鼠标滚轮函数（需要绑定到所有子控件）
        def on_mousewheel(event):
            # 内容不足时禁止滚动
            widgets = self.command_widgets.get(page_name, [])
            if not widgets:
                return 'break'
            region = canvas.bbox('all')
            if region:
                content_height = region[3] - region[1]
                canvas_height = canvas.winfo_height()
                if content_height < canvas_height:
                    canvas.yview_moveto(0)
                    return 'break'
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        # 绑定到 Canvas 和命令容器
        canvas.bind('<MouseWheel>', on_mousewheel)
        cmd_frame.bind('<MouseWheel>', on_mousewheel)

        # 存储滚轮函数（_add_command_row 需要用到）
        self._mousewheel_funcs[page_name] = on_mousewheel

        # 存储每页的命令控件（必须先注册，_add_command_row 依赖这些条目）
        self.command_widgets[page_name] = []
        self._page_frames[page_name] = container
        self.command_canvases[page_name] = canvas
        self._cmd_frames[page_name] = cmd_frame

        # 填充数据
        commands = self.command_manager.get_full_commands(page_name)
        for i, item in enumerate(commands):
            self._add_command_row(page_name, i, item)

    def _add_command_row(self, page_name: str, index: int, item: dict):
        """为单条命令创建一行（文本框+发送按钮）"""
        widgets = self.command_widgets.get(page_name)
        if widgets is None:
            return

        cmd_frame = self._cmd_frames.get(page_name)
        if not cmd_frame:
            return

        # 创建命令行 Frame
        row_frame = ttk.Frame(cmd_frame)
        row_frame.pack(fill=tk.X, padx=2, pady=1)

        # 最左侧：命令选择标签（点击选中整行：选择标签+文本框+发送按钮高亮）
        # fill=Y 使标签高度与 Entry/Button 一致，选中高亮时不会出现高度差
        sel_label = ttk.Label(row_frame, text='○', width=3, anchor='center',
                              cursor='hand2')
        sel_label.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 3))
        sel_label.bind('<Button-1>',
                       lambda event, p=page_name, idx=index:
                           self._select_row_click(p, idx) or 'break')

        # HEX 勾选框：勾选=HEX 命令，未勾选=字符串命令（新命令默认字符串）
        mode = item.get('mode', 'string')
        mode_var = tk.BooleanVar(value=(mode == 'hex'))
        mode_check = ttk.Checkbutton(
            row_frame, variable=mode_var,
            command=lambda p=page_name, idx=index, v=mode_var:
                self._update_command_mode(p, idx, 'hex' if v.get() else 'string'))
        mode_check.pack(side=tk.LEFT, padx=(0, 2))

        # 文本框（显示命令内容）
        content = item.get('content', '')
        entry = ttk.Entry(row_frame, font=('Consolas', 9))
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        entry.insert(0, content)

        # 发送按钮（默认显示命令序号）
        label = item.get('label', '')
        btn_text = label if label else str(index + 1)
        btn = ttk.Button(row_frame, text=btn_text, width=4,
                         command=lambda idx=index: self._send_command_at_index(page_name, idx))
        btn.pack(side=tk.RIGHT)

        # 文本框修改后自动保存
        def on_entry_change(event, idx=index, e=entry, p=page_name):
            new_content = e.get()
            self._update_command_content(p, idx, new_content)

        entry.bind('<FocusOut>', on_entry_change)
        entry.bind('<Return>', on_entry_change)

        # 双击文本框：修改对应发送按钮的文本内容
        def on_entry_double_click(event, idx=index, b=btn, p=page_name):
            new_label = simpledialog.askstring(
                t("修改按钮文本"), t("请输入按钮显示文本："),
                initialvalue=b.cget('text'), parent=self.root)
            if new_label is not None:
                new_label = new_label.strip()
                # 空文本恢复为命令序号
                b.configure(text=new_label if new_label else str(idx + 1))
                self._update_command_label(p, idx, new_label)
            return 'break'

        entry.bind('<Double-Button-1>', on_entry_double_click)

        # 左键：进入编辑模式，清除行选中状态（恢复样式与光标）
        def on_entry_left_click(event, p=page_name):
            self._set_selected_row(p, None)
            return None  # 放行默认处理（聚焦、光标定位）

        entry.bind('<Button-1>', on_entry_left_click)

        # 判定是否处于"命令级操作"状态：该行被标签点击选中 且 文本框无选中文本
        def _cmd_op_active(idx=index, e=entry):
            if self._selected_cmd_index != idx:
                return False
            try:
                e.index('sel.first')
                return False  # 有选中文本 -> 按文本编辑处理
            except tk.TclError:
                return True

        def on_copy(event, idx=index, e=entry, p=page_name):
            if _cmd_op_active(idx, e):
                self._copy_command_at_index(p, idx)
                return 'break'
            return None

        def on_cut(event, idx=index, e=entry, p=page_name):
            if _cmd_op_active(idx, e):
                self._cut_command_at_index(p, idx)
                return 'break'
            return None

        def on_paste(event, idx=index, e=entry, p=page_name):
            if _cmd_op_active(idx, e) and self._cmd_clipboard:
                self._paste_command_at_index(p, idx)
                return 'break'
            return None  # 命令剪贴板为空 -> 正常文本粘贴

        def on_delete_key(event, idx=index, e=entry, p=page_name):
            if _cmd_op_active(idx, e):
                self._delete_command_at_index(p, idx)
                return 'break'
            return None  # 正常文本删除

        for seq, cb in (('<Control-c>', on_copy), ('<Control-C>', on_copy),
                        ('<Control-x>', on_cut), ('<Control-X>', on_cut),
                        ('<Control-v>', on_paste), ('<Control-V>', on_paste),
                        ('<Delete>', on_delete_key)):
            entry.bind(seq, cb)

        # 绑定鼠标滚轮到每行的子控件（解决焦点在Entry时滚轮失效问题）
        mousewheel_func = self._mousewheel_funcs.get(page_name)
        if mousewheel_func:
            entry.bind('<MouseWheel>', mousewheel_func)
            btn.bind('<MouseWheel>', mousewheel_func)
            sel_label.bind('<MouseWheel>', mousewheel_func)
            mode_check.bind('<MouseWheel>', mousewheel_func)
            row_frame.bind('<MouseWheel>', mousewheel_func)

        # 存储控件引用
        widgets.append({
            'frame': row_frame,
            'sel_label': sel_label,
            'mode_check': mode_check,
            'entry': entry,
            'btn': btn,
            'index': index
        })

    def _send_command_at_index(self, page_name: str, index: int):
        """发送指定索引的命令"""
        commands = self.command_manager.get_full_commands(page_name)
        if 0 <= index < len(commands):
            self._load_command_to_send_input(commands[index])
            self.send_data()

    def _update_command_content(self, page_name: str, index: int, new_content: str):
        """更新命令内容"""
        commands = self.command_manager.get_full_commands(page_name)
        if 0 <= index < len(commands):
            self.command_manager.update_command(
                page_name, index, new_content,
                commands[index].get('mode', 'string'),
                commands[index].get('label', ''))

    def _update_command_label(self, page_name: str, index: int, new_label: str):
        """更新命令标签（按钮文本）"""
        commands = self.command_manager.get_full_commands(page_name)
        if 0 <= index < len(commands):
            self.command_manager.update_command(
                page_name, index,
                commands[index].get('content', ''),
                commands[index].get('mode', 'string'),
                new_label)

    def _update_command_mode(self, page_name: str, index: int, mode: str):
        """更新命令模式（勾选框：勾选=HEX，未勾选=字符串）"""
        commands = self.command_manager.get_full_commands(page_name)
        if 0 <= index < len(commands):
            self.command_manager.update_command(
                page_name, index,
                commands[index].get('content', ''),
                mode,
                commands[index].get('label', ''))

    def _select_row_click(self, page_name: str, index: int):
        """点击选择标签：选中整行（高亮），焦点给文本框以便使用快捷键"""
        self._set_selected_row(page_name, index)
        widgets = self.command_widgets.get(page_name, [])
        if 0 <= index < len(widgets):
            widgets[index]['entry'].focus_set()

    def _delete_command_at_index(self, page_name: str, index: int):
        """删除指定索引的命令"""
        self.command_manager.remove_command(page_name, index)
        self._rebuild_command_page(page_name)

    def _config_cmd_selection_style(self):
        """配置命令行样式（初始化和主题切换时调用）"""
        style = ttk.Style()
        # 选中样式：选择标签+文本框+发送按钮高亮；光标色=输入框背景色（视觉隐形），
        # 避免与行选中状态混淆
        style.configure('CmdSelected.TLabel',
                        background=get_color('select_bg'),
                        foreground=get_color('select_fg'),
                        anchor='center')
        style.configure('CmdSelected.TEntry',
                        fieldbackground=get_color('select_bg'),
                        foreground=get_color('select_fg'),
                        insertbackground=get_color('bg_input'))
        style.configure('CmdSelected.TButton',
                        background=get_color('select_bg'),
                        foreground=get_color('select_fg'))

    def _set_selected_row(self, page_name: str, index):
        """设置选中的命令行（选择标签+文本框+发送按钮高亮）；index 为 None 时清除选中"""
        # 先恢复该页所有行的默认样式
        for w in self.command_widgets.get(page_name, []):
            w['sel_label'].configure(text='○', style='TLabel')
            w['entry'].configure(style='TEntry')
            w['btn'].configure(style='TButton')
        if index is None:
            self._selected_cmd_index = None
            return
        widgets = self.command_widgets.get(page_name, [])
        if 0 <= index < len(widgets):
            widgets[index]['sel_label'].configure(text='●', style='CmdSelected.TLabel')
            widgets[index]['entry'].configure(style='CmdSelected.TEntry')
            widgets[index]['btn'].configure(style='CmdSelected.TButton')
            self._selected_cmd_index = index

    def _copy_command_at_index(self, page_name: str, index: int):
        """复制指定索引的命令到内部剪贴板"""
        commands = self.command_manager.get_full_commands(page_name)
        if 0 <= index < len(commands):
            self._cmd_clipboard = dict(commands[index])

    def _cut_command_at_index(self, page_name: str, index: int):
        """剪切指定索引的命令到内部剪贴板"""
        commands = self.command_manager.get_full_commands(page_name)
        if 0 <= index < len(commands):
            self._cmd_clipboard = dict(commands[index])
            self.command_manager.remove_command(page_name, index)
            self._rebuild_command_page(page_name)

    def _paste_command_at_index(self, page_name: str, index: int):
        """将内部剪贴板命令粘贴到指定行的下一行（未选中则追加末尾）"""
        if not self._cmd_clipboard:
            return
        commands = self.command_manager.get_full_commands(page_name)
        insert_at = index + 1 if 0 <= index < len(commands) else len(commands)
        self.command_manager.insert_command(page_name, insert_at, self._cmd_clipboard)
        self._rebuild_command_page(page_name)

    def _rebuild_command_page(self, page_name: str):
        """重建指定页面的命令列表"""
        widgets = self.command_widgets.get(page_name, [])
        for w in widgets:
            w['frame'].destroy()
        self.command_widgets[page_name] = []
        self._selected_cmd_index = None

        # 强制更新 frame 的几何信息
        cmd_frame = self._cmd_frames.get(page_name)
        if cmd_frame:
            cmd_frame.update_idletasks()

        commands = self.command_manager.get_full_commands(page_name)
        for i, item in enumerate(commands):
            self._add_command_row(page_name, i, item)

        # 强制更新 canvas 的 scrollregion 和滚动位置
        canvas = self.command_canvases.get(page_name)
        if canvas:
            canvas.update_idletasks()
            canvas.configure(scrollregion=canvas.bbox("all"))
            # 内容为空时重置滚动位置
            if not commands:
                canvas.yview_moveto(0)
            else:
                # 内容不足时禁止滚动到空白区域
                region = canvas.bbox('all')
                if region:
                    content_height = region[3] - region[1]
                    canvas_height = canvas.winfo_height()
                    if content_height < canvas_height:
                        canvas.yview_moveto(0)

    def _switch_to_page(self, idx: int):
        """按索引切页：Combobox 同步 + 叠放对应 Frame"""
        pages = self.command_manager.get_pages()
        if idx < 0 or idx >= len(pages):
            return
        name = pages[idx]
        self._current_page_idx = idx
        self.page_selector.configure(values=pages)
        self.page_selector.current(idx)
        # 叠放切换：隐藏所有，显示目标
        for frame in self._page_frames.values():
            frame.pack_forget()
        frame = self._page_frames.get(name)
        if frame is not None:
            frame.pack(fill=tk.BOTH, expand=True)

    def _on_page_selector_changed(self, _event=None):
        """用户在 Combobox 选页时触发切页"""
        idx = self.page_selector.current()
        self._switch_to_page(idx)

    def _get_current_page_name(self) -> str:
        """获取当前选中的页面名"""
        pages = self.command_manager.get_pages()
        if 0 <= self._current_page_idx < len(pages):
            return pages[self._current_page_idx]
        return pages[0] if pages else ''

    def _rename_current_page(self):
        old_name = self._get_current_page_name()
        if not old_name:
            return
        self._rename_command_page(old_name)

    def _rename_command_page(self, old_name: str):
        new_name = simpledialog.askstring(
            t("重命名页面"), t("请输入新的页面名称："),
            initialvalue=old_name, parent=self.root)
        if new_name is None or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        if not self.command_manager.rename_page(old_name, new_name):
            messagebox.showwarning(t("提示"), t("页面名称已存在或无效"))
            return
        # 更新 UI：Combobox 值 + 字典 key
        widgets = self.command_widgets.pop(old_name, None)
        canvas = self.command_canvases.pop(old_name, None)
        cmd_frame = self._cmd_frames.pop(old_name, None)
        frame = self._page_frames.pop(old_name, None)
        mousewheel_func = self._mousewheel_funcs.pop(old_name, None)
        if widgets is not None:
            self.command_widgets[new_name] = widgets
        if canvas is not None:
            self.command_canvases[new_name] = canvas
        if cmd_frame is not None:
            self._cmd_frames[new_name] = cmd_frame
        if frame is not None:
            self._page_frames[new_name] = frame
        if mousewheel_func is not None:
            self._mousewheel_funcs[new_name] = mousewheel_func
        pages = self.command_manager.get_pages()
        self.page_selector.configure(values=pages)
        new_idx = pages.index(new_name)
        self._current_page_idx = new_idx
        self.page_selector.current(new_idx)

    def _add_new_command_page(self):
        name = simpledialog.askstring(
            t("新增页面"), t("请输入页面名称："), parent=self.root)
        if name is None:
            return
        name = name.strip()
        if not name:
            return
        if not self.command_manager.add_page(name):
            messagebox.showwarning(t("提示"), t("页面名称已存在"))
            return
        self._add_command_tab(name)
        self._switch_to_page(len(self.command_manager.get_pages()) - 1)

    def _delete_current_command_page(self):
        pages = self.command_manager.get_pages()
        if len(pages) <= 1:
            messagebox.showwarning(t("提示"), t("至少需要保留一个页面"))
            return
        page_name = self._get_current_page_name()
        if not messagebox.askyesno(
                t("确认"), t("确定删除页面「{page_name}」及其所有命令？").format(page_name=page_name)):
            return
        cur_idx = self._current_page_idx
        self.command_manager.remove_page(page_name)
        self.command_widgets.pop(page_name, None)
        self.command_canvases.pop(page_name, None)
        self._cmd_frames.pop(page_name, None)
        self._mousewheel_funcs.pop(page_name, None)
        frame = self._page_frames.pop(page_name, None)
        if frame is not None:
            frame.pack_forget()
            frame.destroy()
        # 选邻近索引并刷新 Combobox + 显示
        new_pages = self.command_manager.get_pages()
        if cur_idx >= len(new_pages):
            cur_idx = len(new_pages) - 1
        self._switch_to_page(cur_idx if cur_idx >= 0 else 0)

    def _add_command_to_current_page(self):
        """在当前页面末尾直接添加一条空命令行（默认字符串模式，不弹窗）"""
        page = self._get_current_page_name()
        if not page:
            return
        self.command_manager.add_command('', 'string', '', page)
        self._rebuild_command_page(page)
        # 滚动到底部并聚焦新行文本框，方便直接输入
        canvas = self.command_canvases.get(page)
        if canvas:
            canvas.update_idletasks()
            canvas.yview_moveto(1.0)
        widgets = self.command_widgets.get(page, [])
        if widgets:
            widgets[-1]['entry'].focus_set()

    def _apply_hist_width(self):
        """手动宽度输入 → 应用（sashpos 是分割线 x 坐标，需换算：位置 = 总宽 - 面板宽）"""
        try:
            w = self.hist_width_var.get()
            w = max(100, min(800, w))
            self.hist_panel_width = w
            self._set_right_panel_width(w)
        except Exception:
            pass

    def _apply_cmd_panel_widths(self):
        """应用页面宽度和按钮宽度"""
        # 1. 应用页面宽度
        self._apply_hist_width()
        # 2. 应用按钮宽度
        try:
            btn_width = self.cmd_btn_width_var.get()
            btn_width = max(2, btn_width)
            self._update_cmd_btn_width(btn_width)
        except Exception:
            pass

    def _update_cmd_btn_width(self, width: int):
        """更新所有命令行的按钮宽度（含"发送按钮"表头）"""
        for page_name, widgets in self.command_widgets.items():
            for w in widgets:
                w['btn'].configure(width=width)
        for lbl in getattr(self, '_cmd_send_headers', {}).values():
            lbl.configure(width=width)

    def _set_right_panel_width(self, w):
        """设置右侧面板宽度为 w（实测补偿 sash 开销，保证实际宽度 == 设置值）"""
        try:
            self.content_pw.update_idletasks()
            pw_w = self.content_pw.winfo_width()
            if pw_w <= 10:
                # 窗口尚未完成布局，稍后重试
                self.root.after(100, lambda: self._set_right_panel_width(w))
                return
            # sashpos 与面板实际宽度之间有一段固定开销（sash 宽度等），
            # 实测后补偿，否则实际宽度会比设置值偏小
            overhead = pw_w - self.content_pw.sashpos(0) - self.hist_frame.winfo_width()
            if 0 <= overhead <= 30:
                self._pw_overhead = overhead
            else:
                overhead = getattr(self, '_pw_overhead', 0)
            self.content_pw.sashpos(0, max(0, pw_w - w - overhead))
        except Exception:
            pass

    def _sync_hist_width_from_sash(self, _event=None):
        """拖动 sash 后同步实际宽度，使 Spinbox/保存设置与实际一致"""
        try:
            w = self.hist_frame.winfo_width()
            if w and hasattr(self, 'hist_width_var'):
                self.hist_width_var.set(w)
                self.hist_panel_width = w
        except Exception:
            pass

    # ==================== 状态栏 ====================

    def create_status_bar(self):
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=2)

        self.status_label = ttk.Label(self.status_frame, text=t("状态: 未连接"),
                                      style='Status.TLabel',
                                      foreground=get_color('error'))
        self.status_label.pack(side=tk.LEFT)

        self.recv_count_label = ttk.Label(
            self.status_frame, text=t("接收: {n} 字节").format(n=0))
        self.recv_count_label.pack(side=tk.RIGHT, padx=10)

        self.send_count_label = ttk.Label(
            self.status_frame, text=t("发送: {n} 字节").format(n=0))
        self.send_count_label.pack(side=tk.RIGHT, padx=10)

        self.send_status_label = ttk.Label(self.status_frame, text="")
        self.send_status_label.pack(side=tk.RIGHT, padx=10)

    # ==================== 事件绑定 ====================

    def setup_connections(self):
        self._bind_widget_events()

        # 勾选项变化时保存设置
        for var in [self.timestamp_var, self.direction_var, self.echo_var,
                    self.hex_addr_var, self.auto_escape_var, self.crlf_var,
                    self.loop_var, self.auto_reconnect_var]:
            var.trace_add('write', lambda *_: self.save_settings())

        for var in [self.encoding_var, self.send_encoding_var]:
            var.trace_add('write', lambda *_: self.save_settings())

        self.loop_interval_var.trace_add(
            'write', lambda *_: self.save_settings())
        self.loop_count_var.trace_add('write', lambda *_: self.save_settings())
        self.hex_newline_count_var.trace_add(
            'write', lambda *_: self.save_settings())

        # 串口参数变更时自动重连
        for var in [self.port_var, self.baudrate_var, self.parity_var,
                    self.databits_var, self.stopbits_var, self.rtscts_var]:
            var.trace_add('write', lambda *_: self._on_serial_param_changed())

        # 帧头帧尾保存
        for var in [self.frame_enable_var, self.frame_header_content_var,
                    self.frame_footer_content_var, self.frame_hex_var]:
            var.trace_add('write', lambda *_: self.save_settings())

        self._reconnect_timer_id = None  # 防抖定时器

    def _bind_widget_events(self):
        """控件级事件绑定（语言切换重建 UI 后需重新执行；
        变量 trace 不在此处，避免重复注册）"""
        # 接收模式切换
        self.recv_notebook.bind('<<NotebookTabChanged>>',
                                self._on_recv_tab_changed)

        # 发送模式切换
        self.send_notebook.bind('<<NotebookTabChanged>>',
                                self._on_send_tab_changed)

        # HEX 输入验证
        self.hex_input.bind(
            '<KeyRelease>', lambda e: self.validate_hex_input())

        # 命令列表事件已在 _add_command_tab 中绑定

        # Enter 发送
        self.string_input.bind('<Return>', self._on_string_enter)
        self.string_input.bind('<Control-Return>', self._on_ctrl_enter)

    # ==================== 语言切换 ====================

    def _switch_language(self):
        """切换中英文：销毁全部控件后按新语言重建，保留运行时状态"""
        lang = self.language_var.get()
        if lang == get_language():
            return
        set_language(lang)
        self.save_settings()  # 保存语言选择

        # 记录需要恢复的 UI 状态
        send_tab = self.send_notebook.index('current')
        recv_tab = self.recv_notebook.index('current')
        page_idx = self._current_page_idx

        # 波形窗口随语言一起关闭（可随时重新打开）
        self._close_waveform()

        # 销毁全部控件，按新语言重建
        for child in self.root.winfo_children():
            child.destroy()
        self.create_serial_control_bar()
        self.create_main_content()
        self.create_status_bar()
        self._bind_widget_events()
        self.on_theme_applied()  # 配色 + 重建菜单

        # ── 恢复运行时状态 ──
        self.refresh_ports_ui()
        self.connect_btn.configure(
            text=t("断开") if self.is_connected else t("连接"))
        self.pause_btn.configure(
            text=t("继续显示") if self.is_paused else t("暂停显示"))
        if self.is_connected:
            port = self.port_var.get().split(' - ')[0]
            self.status_label.configure(
                text=t("状态: 已连接 {port}").format(port=port),
                foreground=get_color('success'))
        self.update_counts()
        self.auto_reply_btn.configure(
            text=t("关闭自动应答") if self.auto_reply_enabled else t("开启自动应答"))
        self._refresh_reply_rules_list()
        self._switch_to_page(page_idx)
        self.send_notebook.select(send_tab)
        self._on_send_tab_changed(None)
        self.recv_notebook.select(recv_tab)
        self._set_right_panel_width(self.hist_panel_width)
        self._toggle_auto_wrap()

    def _on_recv_tab_changed(self, event):
        pass

    def _on_send_tab_changed(self, event):
        """发送模式切换：字符串模式禁用校验，HEX模式禁用自动转义/回车换行"""
        current_tab = self.send_notebook.index('current')
        if current_tab == 0:  # 字符串模式
            # 禁用校验功能
            state = 'disabled'
            self.checksum_checkbtn.configure(state=state)
            self.checksum_start_spin.configure(state=state)
            self.checksum_end_combo.configure(state=state)
            self.checksum_type_combo.configure(state=state)
            # 启用自动转义和回车换行
            self.auto_escape_cb.configure(state='normal')
            self.crlf_cb.configure(state='normal')
        else:  # HEX模式
            # 启用校验功能
            state = 'normal'
            self.checksum_checkbtn.configure(state=state)
            self.checksum_start_spin.configure(state=state)
            self.checksum_end_combo.configure(state=state)
            self.checksum_type_combo.configure(state=state)
            # 禁用自动转义和回车换行
            self.auto_escape_cb.configure(state='disabled')
            self.crlf_cb.configure(state='disabled')

    def _on_string_enter(self, event):
        # Ctrl+Enter 发送，Enter 换行
        if event.state & 0x4:
            self.send_data()
            return 'break'
        return None

    def _on_ctrl_enter(self, event):
        self.send_data()
        return 'break'

    # ==================== 串口扫描 ====================

    def start_port_scan(self):
        self.refresh_ports()
        self._schedule_port_scan()

    def _schedule_port_scan(self):
        self.scan_timer_id = self.root.after(1000, self._port_scan_tick)

    def _port_scan_tick(self):
        self.check_port_change()
        self._schedule_port_scan()

    def check_port_change(self):
        current_ports = self.serial_manager.scan_ports()
        current_names = [p[0] for p in current_ports]
        last_names = [p[0] for p in self.last_ports]

        if set(current_names) != set(last_names):
            self.last_ports = current_ports
            saved = self.port_var.get().split(
                ' - ')[0] if self.port_var.get() else ''
            # 如果已连接的串口消失，自动断开
            if self.is_connected and saved not in current_names:
                self.disconnect_serial()
                messagebox.showwarning(t("提示"), t("串口已断开！"))

    def refresh_ports(self):
        ports = self.serial_manager.scan_ports()
        self.last_ports = ports

    # ==================== 串口连接 ====================

    def toggle_connection(self):
        if self.is_connected:
            self.disconnect_serial()
        else:
            self.connect_serial()
            self.reset_reconnect_count()

    def connect_serial(self, silent=False):
        """连接串口

        Args:
            silent: True 时失败不弹错误框、不自动启动重连定时器
                    （由调用方自行处理重连与提示，如 try_reconnect）
        Returns:
            True 表示连接成功
        """
        port_text = self.port_var.get()
        if not port_text:
            if not silent:
                messagebox.showwarning(t("错误"), t("请选择串口！"))
            return False

        port_name = port_text.split(' - ')[0]

        try:
            baudrate = int(self.baudrate_var.get())
        except ValueError:
            if not silent:
                messagebox.showwarning(t("错误"), t("波特率必须是数字！"))
            return False

        databits = int(self.databits_var.get())
        stopbits_map = {'1': 1, '1.5': 1.5, '2': 2}
        stopbits = stopbits_map.get(self.stopbits_var.get(), 1)
        parity_map = {'None': 'N', 'Even': 'E',
                      'Odd': 'O', 'Mark': 'M', 'Space': 'S'}
        parity = parity_map.get(self.parity_var.get(), 'N')
        rtscts = self.rtscts_var.get()

        success, message = self.serial_manager.connect(
            port_name, baudrate, databits, stopbits, parity, rtscts
        )

        if success:
            self.is_connected = True
            self.status_label.configure(
                text=t("状态: 已连接 {port}").format(port=port_name),
                foreground=get_color('success'))
            self.connect_btn.configure(text=t("断开"))

            self.receive_thread = ReceiveThread(
                self.serial_manager,
                on_data=self._on_data_from_thread,
                on_error=self._on_error_from_thread
            )
            timeout = self._safe_int(self.recv_timeout_var, 0)
            if timeout == 0:
                timeout = self._calc_auto_timeout()
            self.receive_thread.recv_timeout = timeout
            self.receive_thread.start()

            self.recv_bytes = 0
            self.sent_bytes = 0
            self.update_counts()
            self.reset_reconnect_count()
            return True
        else:
            if not silent:
                messagebox.showerror(t("连接失败"),
                                      t("无法连接串口: {msg}").format(msg=message))
                if self.auto_reconnect_var.get():
                    self._start_reconnect_timer()
            return False

    def disconnect_serial(self):
        if self.receive_thread:
            self.receive_thread.stop()
            self.receive_thread = None

        self.serial_manager.disconnect()
        self.is_connected = False
        self.status_label.configure(text=t("状态: 未连接"),
                                    foreground=get_color('error'))
        self.connect_btn.configure(text=t("连接"))

        if self.loop_timer_id:
            self.root.after_cancel(self.loop_timer_id)
            self.loop_timer_id = None
            self.loop_var.set(False)

        if self.auto_reconnect_var.get():
            self._start_reconnect_timer()

    def _on_serial_param_changed(self):
        """串口参数变更时，如果已连接则自动重连（防抖处理）"""
        if not self.is_connected:
            return
        # 防抖：取消之前的定时器，重新设置
        if self._reconnect_timer_id:
            self.root.after_cancel(self._reconnect_timer_id)
        self._reconnect_timer_id = self.root.after(300, self._do_serial_reconnect)

    def _do_serial_reconnect(self):
        """实际执行串口重连"""
        self._reconnect_timer_id = None
        if not self.is_connected:
            return
        self.disconnect_serial()
        self.connect_serial()

    # ==================== 数据接收 ====================

    def _on_recv_timeout_changed(self, *args):
        """超时值变化时同步到接收线程，0=自动模式按波特率计算"""
        timeout = self._safe_int(self.recv_timeout_var, 0)
        if timeout == 0:
            # 自动模式：按当前波特率计算，5倍字节间隔
            timeout = self._calc_auto_timeout()
        if hasattr(self, 'receive_thread') and self.receive_thread:
            self.receive_thread.recv_timeout = timeout

    def _calc_auto_timeout(self):
        """根据当前波特率自动计算超时时间（毫秒），为字节间隔的5倍"""
        try:
            baudrate = int(self.baudrate_var.get())
        except (ValueError, tk.TclError):
            baudrate = 115200
        if baudrate <= 0:
            baudrate = 115200
        # 每个字节的位数：起始位1 + 数据位 + 校验位(0或1) + 停止位
        try:
            databits = int(self.databits_var.get())
        except (ValueError, tk.TclError):
            databits = 8
        stopbits = float(self.stopbits_var.get()) if self.stopbits_var.get() else 1.0
        parity = self.parity_var.get()
        parity_bits = 0 if parity == 'None' else 1
        bits_per_byte = 1 + databits + parity_bits + stopbits
        # 字节间隔(秒) = bits_per_byte / baudrate
        # 转换为毫秒，5倍
        timeout_ms = int(bits_per_byte / baudrate * 1000 * 5)
        return max(timeout_ms, 1)  # 最小1ms

    def _on_data_from_thread(self, data):
        """从接收线程调用 - 通过 root.after 安排 UI 更新"""
        self.root.after(0, self.on_data_received, data)

    def _on_error_from_thread(self, error_msg):
        """从接收线程调用"""
        self.root.after(0, self.on_receive_error, error_msg)

    def on_data_received(self, data):
        if self.is_paused:
            return

        # 接收超时分隔（仅换行，不显示超时文字）
        timeout = self._safe_int(self.recv_timeout_var, 0)
        if timeout == 0:
            timeout = self._calc_auto_timeout()
        if timeout > 0 and self.received_data:
            last_ts = self.received_data[-1].get('timestamp', 0)
            elapsed_ms = (time.time() - last_ts) * 1000
            if elapsed_ms > timeout:
                for tw in [self.string_recv_text, self.hex_recv_text, self.compare_recv_text]:
                    self._append_text(tw, "\n", ('timeout',))

        self.recv_bytes += len(data)
        self.update_counts()

        # 记录到日志
        if self.log_file and self.log_writer:
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
            self.log_writer.writerow([ts, "RX", data.hex().upper()])
            self.log_file.flush()
            self.log_file_size += len(data)
            if self.log_file_size > self.max_log_size:
                self.rotate_log_file()

        # 更新波形
        self.update_waveform(data)

        # 解码
        encoding = self.encoding_var.get()
        try:
            string_data = data.decode(encoding)
        except UnicodeDecodeError:
            string_data = data.decode(encoding, errors='replace')

        self.received_data.append({
            'raw': data,
            'string': string_data,
            'timestamp': time.time()
        })

        self.update_recv_displays(data, string_data, is_recv=True)

        # 自动应答
        if self.auto_reply_enabled:
            self._process_auto_reply(data, string_data)

    def on_receive_error(self, error_msg):
        for tw in [self.string_recv_text, self.hex_recv_text, self.compare_recv_text]:
            self._append_text(tw, t("[错误] {msg}\n").format(msg=error_msg), ('error',))

    def update_recv_displays(self, raw_data, string_data, is_recv):
        if not is_recv and not self.echo_var.get():
            return

        ts = None
        if self.timestamp_var.get():
            ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]

        direction = None
        if self.direction_var.get():
            direction = "[RX]" if is_recv else "[TX]"

        # 字符串显示
        tags = []
        parts = []
        if ts:
            parts.append(f"[{ts}] ")
            tags.append('timestamp')
        if direction:
            parts.append(f"{direction} ")
            tags.append('text_color')
        parts.append(string_data + "\n")
        tags.append('recv' if is_recv else 'send')
        self._append_text_rich(self.string_recv_text, parts, tags)

        # HEX 显示
        hex_str = raw_data.hex().upper()
        hex_list = [hex_str[i:i+2] for i in range(0, len(hex_str), 2)]
        bytes_per_line = self.hex_newline_count_var.get()

        lines = []
        if bytes_per_line > 0:
            for i in range(0, len(hex_list), bytes_per_line):
                chunk = hex_list[i:i+bytes_per_line]
                line = ' '.join(chunk)
                if self.hex_addr_var.get():
                    line = f"{i:04X}: {line}"
                lines.append(line)
            hex_text = '\n'.join(lines)
        else:
            hex_text = ' '.join(hex_list)

        parts = []
        tags = []
        if ts:
            parts.append(f"[{ts}] ")
            tags.append('timestamp')
        if direction:
            parts.append(f"{direction} ")
            tags.append('text_color')
        parts.append(hex_text + "\n")
        tags.append('recv' if is_recv else 'send')
        self._append_text_rich(self.hex_recv_text, parts, tags)

        # 对照显示：HEX 在上，字符串在下，一上一下同时展示
        parts = []
        tags = []
        if ts:
            parts.append(f"[{ts}] ")
            tags.append('timestamp')
        if direction:
            parts.append(f"{direction} ")
            tags.append('text_color')
        parts.append(f"HEX: {hex_text}\n")
        tags.append('recv' if is_recv else 'send')
        parts.append(f"ASC: {string_data}\n\n")
        tags.append('recv' if is_recv else 'send')
        self._append_text_rich(self.compare_recv_text, parts, tags)

    def clear_receive_area(self):
        for tw in [self.string_recv_text, self.hex_recv_text, self.compare_recv_text]:
            tw.configure(state=tk.NORMAL)
            tw.delete('1.0', tk.END)
            tw.configure(state=tk.DISABLED)
        self.received_data.clear()
        self.recv_bytes = 0
        self.update_counts()

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.pause_btn.configure(
            text=t("继续显示") if self.is_paused else t("暂停显示"))

    # ==================== 数据发送 ====================

    def send_data(self):
        if self.send_notebook.index('current') == 0:
            text = self.string_input.get('1.0', tk.END).rstrip('\n')
            if not text:
                return
            if self.auto_escape_var.get():
                text = text.replace('\\r', '\r').replace('\\n', '\n')
            if self.crlf_var.get():
                text += '\r\n'
            encoding = self.send_encoding_var.get()
            try:
                data = text.encode(encoding)
            except UnicodeEncodeError as e:
                messagebox.showwarning(
                    t("编码错误"),
                    t("无法用{encoding}编码: {e}").format(encoding=encoding, e=e))
                return
        else:
            hex_text = self.hex_input.get('1.0', tk.END).strip()
            if not hex_text:
                return
            self.validate_hex_input()
            if self.hex_status_label.cget('text'):
                messagebox.showwarning(
                    t("错误"), self.hex_status_label.cget('text'))
                return
            data = self.parse_hex_input(hex_text)
            if data is None:
                messagebox.showwarning(t("错误"), t("无效的Hex数据格式！"))
                return

        # 校验自动添加（仅 HEX 模式生效，字符串模式不追加校验）
        if self.checksum_enable_var.get() and self.send_notebook.index('current') != 0:
            data = self._append_checksum(data)

        # 帧头帧尾添加（在所有校验、回车换行之后）
        data = self._apply_frame_header_footer(data)

        # 发送
        success = self.serial_manager.send(
            data) if self.is_connected else False

        # 回显
        if not self.is_paused:
            encoding = self.send_encoding_var.get()
            try:
                string_data = data.decode(encoding)
            except UnicodeDecodeError:
                string_data = data.decode(encoding, errors='replace')
            self.update_recv_displays(data, string_data, is_recv=False)

        if not self.is_connected:
            messagebox.showwarning(t("提示"), t("未连接串口，数据仅作为回显显示！"))
            return

        if success:
            self.sent_bytes += len(data)
            self.update_counts()

            if self.log_file and self.log_writer:
                ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                self.log_writer.writerow([ts, "TX", data.hex().upper()])
                self.log_file.flush()

            self.send_history_results.append(True)
        else:
            self.send_history_results.append(False)
            if not self.serial_manager.is_connected and self.is_connected:
                self.is_connected = False
                self.status_label.configure(text=t("状态: 未连接"),
                                            foreground=get_color('error'))
                messagebox.showwarning(t("发送失败"), t("串口连接已断开！"))
                if self.auto_reconnect_var.get():
                    self._start_reconnect_timer()

        # 维护发送成功率统计
        if len(self.send_history_results) > 50:
            self.send_history_results.pop(0)
        if self.send_history_results:
            self.send_success_rate = sum(
                self.send_history_results) / len(self.send_history_results)

    def _on_loop_toggle(self):
        """循环发送复选框切换"""
        if self.loop_var.get():
            # 勾选：开始循环
            if not self.is_connected:
                messagebox.showwarning(t("错误"), t("请先连接串口！"))
                self.loop_var.set(False)
                return
            self.loop_sent_count = 0
            self._do_loop_send()
        else:
            # 取消勾选：停止循环
            if self.loop_timer_id:
                self.root.after_cancel(self.loop_timer_id)
                self.loop_timer_id = None

    def _do_loop_send(self):
        max_count = self.loop_count_var.get()
        if max_count > 0 and self.loop_sent_count >= max_count:
            # 次数到了，自动取消勾选
            self.loop_var.set(False)
            self.loop_timer_id = None
            return
        if not self.loop_var.get():
            return
        self.send_data()
        self.loop_sent_count += 1
        interval = max(1, self.loop_interval_var.get())
        self.loop_timer_id = self.root.after(interval, self._do_loop_send)

    def validate_hex_input(self):
        text = self.hex_input.get('1.0', tk.END).strip()
        cleaned = text.replace(' ', '').upper()
        if not cleaned:
            self.hex_status_label.configure(text="")
            return
        valid = set('0123456789ABCDEF')
        invalid = set(cleaned) - valid
        if invalid:
            self.hex_status_label.configure(
                text=t("非法字符: {chars}").format(chars=', '.join(invalid)))
        elif len(cleaned) % 2 != 0:
            self.hex_status_label.configure(text=t("Hex数据长度必须为偶数"))
        else:
            self.hex_status_label.configure(text="")

    def parse_hex_input(self, text):
        cleaned = text.replace(' ', '').upper()
        valid = set('0123456789ABCDEF')
        if set(cleaned) - valid or len(cleaned) % 2 != 0:
            return None
        try:
            return bytes.fromhex(cleaned)
        except ValueError:
            return None

    # ==================== 校验算法 ====================

    def _get_checksum_range(self, data: bytes) -> tuple:
        """根据配置获取参与校验计算的数据范围和插入位置
        返回 (calc_data, insert_pos)
        """
        start = self._safe_int(self.checksum_start_var, 0)
        end_str = self.checksum_end_var.get()
        if end_str in ('末尾', 'End'):  # 值随语言显示，双语兼容判断
            insert_pos = len(data)
        else:
            try:
                end = int(end_str)
            except (ValueError, TypeError):
                end = -1
            if end < 0:
                insert_pos = len(data) + end
            else:
                insert_pos = end
        insert_pos = max(0, min(insert_pos, len(data)))
        start = max(0, min(start, insert_pos))
        calc_data = data[start:insert_pos]
        return calc_data, insert_pos

    def _append_checksum(self, data: bytes) -> bytes:
        """计算校验并插入到指定位置"""
        calc_data, insert_pos = self._get_checksum_range(data)
        cksum_type = self.checksum_type_var.get()

        if cksum_type == 'ADD8':
            s = sum(calc_data) & 0xFF
            cksum_bytes = bytes([s])
        elif cksum_type == 'ADD16':
            s = sum(calc_data) & 0xFFFF
            cksum_bytes = struct.pack('>H', s)
        elif cksum_type == 'XOR8':
            x = 0
            for b in calc_data:
                x ^= b
            cksum_bytes = bytes([x])
        elif cksum_type == 'ModBusCRC16':
            crc = self._modbus_crc16(calc_data)
            cksum_bytes = struct.pack('<H', crc)
        else:
            return data

        return data[:insert_pos] + cksum_bytes + data[insert_pos:]

    @staticmethod
    def _modbus_crc16(data: bytes) -> int:
        """ModBus CRC16 校验"""
        crc = 0xFFFF
        for b in data:
            crc ^= b
            for _ in range(8):
                if crc & 0x0001:
                    crc = (crc >> 1) ^ 0xA001
                else:
                    crc >>= 1
        return crc

    def _apply_frame_header_footer(self, data: bytes) -> bytes:
        """在所有处理后添加帧头帧尾"""
        if not self.frame_enable_var.get():
            return data
        is_hex = self.frame_hex_var.get()
        header = self._parse_frame_data(self.frame_header_content_var.get(), is_hex)
        if header:
            data = header + data
        footer = self._parse_frame_data(self.frame_footer_content_var.get(), is_hex)
        if footer:
            data = data + footer
        return data

    @staticmethod
    def _parse_frame_data(text: str, is_hex: bool) -> bytes:
        """解析帧头帧尾数据：HEX模式解析为bytes，字符串模式直接编码"""
        text = text.strip()
        if not text:
            return b''
        if is_hex:
            return MainWindow._parse_frame_hex(text)
        else:
            return text.encode('utf-8')

    @staticmethod
    def _parse_frame_hex(text: str) -> bytes:
        """解析帧头帧尾的HEX字符串，支持多种格式"""
        text = text.strip()
        if not text:
            return b''
        # 去除 0x/0X 前缀
        if text.lower().startswith('0x'):
            text = text[2:]
        # 去除常见分隔符
        cleaned = text.replace(' ', '').replace(',', '').replace(';', '') \
                       .replace('\n', '').replace('\r', '').replace('\t', '')
        if not cleaned:
            return b''
        # 补零：奇数长度时前面补0
        if len(cleaned) % 2 != 0:
            cleaned = '0' + cleaned
        try:
            return bytes.fromhex(cleaned)
        except ValueError:
            return b''

    # ==================== 自动应答 ====================

    def _process_auto_reply(self, raw_data: bytes, string_data: str):
        """处理自动应答匹配"""
        for rule in self.auto_reply_rules:
            if not rule.get('enabled', True):
                continue
            if self._match_reply_rule(rule, raw_data, string_data):
                delay = rule.get('delay', 100)
                self.root.after(delay, lambda r=rule: self._send_auto_reply(r))

    def _match_reply_rule(self, rule: dict, raw_data: bytes, string_data: str) -> bool:
        """检查接收数据是否匹配规则"""
        match_mode = rule['match_mode']
        match_content = rule['match_content']
        use_regex = rule.get('use_regex', False)

        if match_mode == 'hex':
            # HEX 模式匹配
            try:
                match_bytes = bytes.fromhex(match_content.replace(' ', ''))
            except ValueError:
                return False
            if use_regex:
                try:
                    return bool(re.search(match_content, raw_data.hex().upper()))
                except re.error:
                    return False
            return match_bytes in raw_data
        else:
            # 字符串模式匹配
            if use_regex:
                try:
                    return bool(re.search(match_content, string_data))
                except re.error:
                    return False
            return match_content in string_data

    def _send_auto_reply(self, rule: dict):
        """发送自动应答数据"""
        if not self.is_connected:
            return
        reply_mode = rule['reply_mode']
        reply_content = rule['reply_content']

        if reply_mode == 'hex':
            try:
                data = bytes.fromhex(reply_content.replace(' ', ''))
            except ValueError:
                return
        else:
            encoding = self.send_encoding_var.get()
            try:
                data = reply_content.encode(encoding)
            except UnicodeEncodeError:
                return

        # 校验仅对 HEX 应答生效
        if reply_mode == 'hex' and self.checksum_enable_var.get():
            data = self._append_checksum(data)

        # 帧头帧尾
        data = self._apply_frame_header_footer(data)

        success = self.serial_manager.send(data)
        if success:
            self.sent_bytes += len(data)
            self.update_counts()
            # 回显
            if not self.is_paused and self.echo_var.get():
                encoding = self.send_encoding_var.get()
                try:
                    string_data = data.decode(encoding)
                except UnicodeDecodeError:
                    string_data = data.decode(encoding, errors='replace')
                self.update_recv_displays(data, string_data, is_recv=False)

    # ==================== 多命令发送 ====================

    def update_command_lists(self):
        """刷新所有页面的命令列表"""
        for page_name in self.command_widgets.keys():
            self._rebuild_command_page(page_name)

    def _load_command_to_send_input(self, item: dict):
        """根据命令 item 切换发送选项卡并填入内容"""
        mode = item.get("mode")
        content = item.get("content", "")
        if mode == 'string':
            self.send_notebook.select(0)
            self.string_input.delete('1.0', tk.END)
            self.string_input.insert('1.0', content)
        elif mode == 'hex':
            self.send_notebook.select(1)
            self.hex_input.delete('1.0', tk.END)
            self.hex_input.insert('1.0', content)

    def _tree_selected_index(self, tree):
        """获取 Treeview 当前选中项的整数索引（iid=str(index)）"""
        sel = tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except (ValueError, IndexError):
            return None

    def _toggle_auto_wrap(self):
        """切换接收框自动换行"""
        wrap_mode = tk.WORD if self.auto_wrap_var.get() else tk.NONE
        for text_widget in [self.string_recv_text, self.hex_recv_text, self.compare_recv_text]:
            text_widget.configure(wrap=wrap_mode)

    # ==================== 波形显示 ====================

    def toggle_waveform(self):
        if self.waveform_window and self.waveform_window.winfo_exists():
            self._close_waveform()
        else:
            self.create_waveform_window()

    def _close_waveform(self):
        """关闭波形窗口并清理引用"""
        if self.waveform_window and self.waveform_window.winfo_exists():
            self.waveform_window.destroy()
        self.waveform_window = None
        self.waveform_fig = None
        self.waveform_ax = None
        self.waveform_line = None
        self.waveform_canvas = None

    def create_waveform_window(self):
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        except ImportError:
            messagebox.showwarning(
                t("提示"),
                t("matplotlib 未安装，波形显示功能不可用。\n请运行: pip install matplotlib"))
            return

        self.waveform_window = tk.Toplevel(self.root)
        self.waveform_window.title(t("波形显示"))
        self.waveform_window.geometry("800x500")

        # 控制栏
        ctrl = ttk.Frame(self.waveform_window)
        ctrl.pack(fill=tk.X, padx=4, pady=2)

        ttk.Label(ctrl, text=t("字节大小:")).pack(side=tk.LEFT, padx=2)
        self.waveform_bytesize_var = tk.StringVar(
            value=t("32位") if self.waveform_bytesize == 4 else t("16位"))
        ttk.Combobox(ctrl, textvariable=self.waveform_bytesize_var,
                     values=[t("16位"), t("32位")], state='readonly', width=6).pack(side=tk.LEFT, padx=2)

        ttk.Label(ctrl, text=t("字节序:")).pack(side=tk.LEFT, padx=2)
        self.waveform_endian_var = tk.StringVar(
            value=t("大端") if self.waveform_endian == 'big' else t("小端"))
        ttk.Combobox(ctrl, textvariable=self.waveform_endian_var,
                     values=[t("小端"), t("大端")], state='readonly', width=6).pack(side=tk.LEFT, padx=2)

        # 字节大小/字节序变化时回写到实例属性并持久化
        self.waveform_bytesize_var.trace_add(
            'write', lambda *_: self._sync_waveform_format())
        self.waveform_endian_var.trace_add(
            'write', lambda *_: self._sync_waveform_format())

        ttk.Button(ctrl, text=t("清空波形"), command=self.clear_waveform).pack(
            side=tk.LEFT, padx=4)
        ttk.Button(ctrl, text=t("保存图片"), command=self.save_waveform_image).pack(
            side=tk.LEFT, padx=4)

        # Matplotlib 图表
        self.waveform_fig = Figure(
            figsize=(8, 4), dpi=100, facecolor=get_color('background'))
        self.waveform_ax = self.waveform_fig.add_subplot(111)
        self.waveform_ax.set_facecolor(get_color('bg_input'))
        self.waveform_ax.tick_params(colors=get_color('text'))
        self.waveform_xlabel = self.waveform_settings.get('xlabel', t('采样点'))
        self.waveform_ylabel = self.waveform_settings.get('ylabel', t('数值'))
        self.waveform_ax.set_xlabel(
            self.waveform_xlabel, color=get_color('text'))
        self.waveform_ax.set_ylabel(
            self.waveform_ylabel, color=get_color('text'))
        for spine in self.waveform_ax.spines.values():
            spine.set_color(get_color('border'))

        self.waveform_line, = self.waveform_ax.plot(
            [], [], color=get_color('recv'), linewidth=1.5)
        self.waveform_ax.grid(True, alpha=0.3, color=get_color('border'))

        # 恢复保存的轴范围
        ws = self.waveform_settings
        if ws.get('xlim'):
            self.waveform_ax.set_xlim(ws['xlim'])
        if ws.get('ylim'):
            self.waveform_ax.set_ylim(ws['ylim'])

        self.waveform_canvas = FigureCanvasTkAgg(
            self.waveform_fig, master=self.waveform_window)
        self.waveform_canvas.draw()

        # 导航工具栏（支持缩放、拖动、重置）
        nav_toolbar = NavigationToolbar2Tk(
            self.waveform_canvas, self.waveform_window)
        nav_toolbar.update()

        self.waveform_canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        # 轴设置区域
        axis_frame = ttk.LabelFrame(self.waveform_window, text=t("轴设置"))
        axis_frame.pack(fill=tk.X, padx=4, pady=2)

        # X轴
        x_row = ttk.Frame(axis_frame)
        x_row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(x_row, text=t("X轴标签:")).pack(side=tk.LEFT)
        self.wf_xlabel_var = tk.StringVar(value=self.waveform_xlabel)
        ttk.Entry(x_row, textvariable=self.wf_xlabel_var,
                  width=12).pack(side=tk.LEFT, padx=2)
        ttk.Label(x_row, text=t("范围:")).pack(side=tk.LEFT, padx=(8, 0))
        self.wf_xlim_min_var = tk.StringVar(
            value=str(ws.get('xlim', [None, None])[0]) if ws.get('xlim') else "")
        self.wf_xlim_max_var = tk.StringVar(
            value=str(ws.get('xlim', [None, None])[1]) if ws.get('xlim') else "")
        ttk.Entry(x_row, textvariable=self.wf_xlim_min_var,
                  width=8).pack(side=tk.LEFT, padx=2)
        ttk.Label(x_row, text="~").pack(side=tk.LEFT)
        ttk.Entry(x_row, textvariable=self.wf_xlim_max_var,
                  width=8).pack(side=tk.LEFT, padx=2)

        # Y轴
        y_row = ttk.Frame(axis_frame)
        y_row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(y_row, text=t("Y轴标签:")).pack(side=tk.LEFT)
        self.wf_ylabel_var = tk.StringVar(value=self.waveform_ylabel)
        ttk.Entry(y_row, textvariable=self.wf_ylabel_var,
                  width=12).pack(side=tk.LEFT, padx=2)
        ttk.Label(y_row, text=t("范围:")).pack(side=tk.LEFT, padx=(8, 0))
        self.wf_ylim_min_var = tk.StringVar(
            value=str(ws.get('ylim', [None, None])[0]) if ws.get('ylim') else "")
        self.wf_ylim_max_var = tk.StringVar(
            value=str(ws.get('ylim', [None, None])[1]) if ws.get('ylim') else "")
        ttk.Entry(y_row, textvariable=self.wf_ylim_min_var,
                  width=8).pack(side=tk.LEFT, padx=2)
        ttk.Label(y_row, text="~").pack(side=tk.LEFT)
        ttk.Entry(y_row, textvariable=self.wf_ylim_max_var,
                  width=8).pack(side=tk.LEFT, padx=2)

        ttk.Button(y_row, text=t("应用"), command=self._apply_waveform_axis_settings).pack(
            side=tk.LEFT, padx=8)

        self.waveform_fig.tight_layout()

    def _apply_waveform_axis_settings(self):
        """应用并保存波形轴设置"""
        if not self.waveform_ax:
            return
        # 标签
        xlabel = self.wf_xlabel_var.get()
        ylabel = self.wf_ylabel_var.get()
        self.waveform_ax.set_xlabel(xlabel, color=get_color('text'))
        self.waveform_ax.set_ylabel(ylabel, color=get_color('text'))
        self.waveform_xlabel = xlabel
        self.waveform_ylabel = ylabel

        # 轴范围
        try:
            xmin = float(self.wf_xlim_min_var.get()
                         ) if self.wf_xlim_min_var.get() else None
            xmax = float(self.wf_xlim_max_var.get()
                         ) if self.wf_xlim_max_var.get() else None
            if xmin is not None and xmax is not None:
                self.waveform_ax.set_xlim(xmin, xmax)
        except ValueError:
            pass
        try:
            ymin = float(self.wf_ylim_min_var.get()
                         ) if self.wf_ylim_min_var.get() else None
            ymax = float(self.wf_ylim_max_var.get()
                         ) if self.wf_ylim_max_var.get() else None
            if ymin is not None and ymax is not None:
                self.waveform_ax.set_ylim(ymin, ymax)
        except ValueError:
            pass

        self.waveform_canvas.draw_idle()

        # 保存到配置
        self.waveform_settings = {
            'xlabel': xlabel,
            'ylabel': ylabel,
            'xlim': [self.waveform_ax.get_xlim()[0], self.waveform_ax.get_xlim()[1]],
            'ylim': [self.waveform_ax.get_ylim()[0], self.waveform_ax.get_ylim()[1]],
        }
        self.save_settings()

    def _sync_waveform_format(self):
        """波形字节大小/字节序变化时同步到实例属性并持久化"""
        if not hasattr(self, 'waveform_bytesize_var'):
            return
        self.waveform_bytesize = 4 if self.waveform_bytesize_var.get() in ("32位", "32-bit") else 2
        self.waveform_endian = 'big' if self.waveform_endian_var.get() in ("大端", "Big Endian") else 'little'
        self.save_settings()

    def update_waveform(self, data):
        if not self.waveform_ax:
            return

        # 波形窗口已打开时 waveform_bytesize_var / waveform_endian_var 必然存在
        bs = 2 if self.waveform_bytesize_var.get() in ("16位", "16-bit") else 4
        endian = 'little' if self.waveform_endian_var.get() in ("小端", "Little Endian") else 'big'

        try:
            for i in range(0, len(data), bs):
                if i + bs <= len(data):
                    value = int.from_bytes(
                        data[i:i+bs], byteorder=endian, signed=True)
                    self.waveform_data.append(value)
        except Exception:
            pass

        if len(self.waveform_data) > self.waveform_max_points:
            self.waveform_data = self.waveform_data[-self.waveform_max_points:]

        # 批量刷新
        if not self.waveform_update_pending:
            self.waveform_update_pending = True
            self.root.after(50, self._refresh_waveform)

    def _refresh_waveform(self):
        self.waveform_update_pending = False
        if not self.waveform_line or not self.waveform_data:
            return
        self.waveform_line.set_ydata(self.waveform_data)
        self.waveform_line.set_xdata(range(len(self.waveform_data)))
        self.waveform_ax.relim()
        self.waveform_ax.autoscale_view()
        self.waveform_canvas.draw_idle()

    def clear_waveform(self):
        self.waveform_data = []
        if self.waveform_line:
            self.waveform_line.set_ydata([])
            self.waveform_line.set_xdata([])
            self.waveform_ax.relim()
            self.waveform_ax.autoscale_view()
            self.waveform_canvas.draw_idle()

    def save_waveform_image(self):
        if not self.waveform_fig:
            return
        path = filedialog.asksaveasfilename(
            title=t("保存波形图片"),
            filetypes=[(t("PNG图片"), "*.png"), (t("所有文件"), "*.*")]
        )
        if path:
            try:
                self.waveform_fig.savefig(path, dpi=150, bbox_inches='tight')
                messagebox.showinfo(t("成功"), t("波形图片已保存到: {path}").format(path=path))
            except Exception as e:
                messagebox.showwarning(t("错误"), t("保存失败: {e}").format(e=e))

    # ==================== 数据记录 ====================

    def toggle_log(self):
        if self.log_file:
            self.stop_log()
        else:
            self.start_log()

    def start_log(self):
        try:
            log_dir = os.path.join(os.getcwd(), "logs")
            os.makedirs(log_dir, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            self.log_file_path = os.path.join(log_dir, f"serial_log_{ts}.csv")
            self.log_file = open(self.log_file_path, 'w',
                                 newline='', encoding='utf-8')
            self.log_writer = csv.writer(self.log_file)
            self.log_writer.writerow([t("时间"), t("类型"), t("数据")])
            self.log_start_time = datetime.now()
            self.log_file_size = 0
        except Exception as e:
            messagebox.showwarning(t("错误"), t("无法开始记录: {e}").format(e=e))

    def stop_log(self):
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
        self.log_file = None
        self.log_writer = None
        self.log_file_path = ""
        self.log_start_time = None
        self.log_file_size = 0

    def rotate_log_file(self):
        if self.log_file:
            try:
                self.log_file.close()
            except Exception:
                pass
        self.log_file = None
        self.start_log()

    def export_data(self):
        if not self.received_data:
            messagebox.showwarning(t("错误"), t("没有数据可导出！"))
            return

        path = filedialog.asksaveasfilename(
            title=t("导出数据"),
            filetypes=[(t("文本文件"), "*.txt"), (t("CSV文件"), "*.csv"),
                       (t("二进制文件"), "*.bin"), (t("所有文件"), "*.*")]
        )
        if not path:
            return

        try:
            ext = os.path.splitext(path)[1].lower()
            if ext == '.bin':
                with open(path, 'wb') as f:
                    for item in self.received_data:
                        f.write(item['raw'])
            elif ext == '.csv':
                with open(path, 'w', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    writer.writerow([t("时间"), t("类型"), t("数据")])
                    for item in self.received_data:
                        ts = datetime.fromtimestamp(
                            item['timestamp']).strftime("%H:%M:%S.%f")[:-3]
                        writer.writerow([ts, "RX", item['string']])
            else:
                with open(path, 'w', encoding='utf-8') as f:
                    for item in self.received_data:
                        ts = datetime.fromtimestamp(
                            item['timestamp']).strftime("%H:%M:%S.%f")[:-3]
                        f.write(f"[{ts}] [RX] {item['string']}\n")

            messagebox.showinfo(t("成功"), t("数据已导出到: {path}").format(path=path))
        except Exception as e:
            messagebox.showwarning(t("错误"), t("导出失败: {e}").format(e=e))

    # ==================== 自动重连 ====================

    def _start_reconnect_timer(self):
        if self.reconnect_timer_id:
            return
        interval = self.reconnect_interval_var.get() * 1000
        self.reconnect_timer_id = self.root.after(interval, self.try_reconnect)

    def try_reconnect(self):
        self.reconnect_timer_id = None

        if not self.auto_reconnect_var.get() or self.is_connected:
            return

        self.reconnect_count += 1
        max_times = self.reconnect_max_var.get()

        if self.reconnect_count > max_times:
            # 达到最大次数：仅状态栏提示，不弹模态框
            self.status_label.configure(
                text=t("状态: 自动重连失败（已达最大次数 {n}）").format(n=max_times),
                foreground=get_color('error'))
            return

        # 状态栏提示重连进度
        self.status_label.configure(
            text=t("状态: 正在重连 {cur}/{max}...").format(
                cur=self.reconnect_count, max=max_times),
            foreground=get_color('timestamp'))

        # 静默连接：失败不弹窗、不重复启动定时器（由本函数统一调度）
        self.connect_serial(silent=True)

        if not self.is_connected:
            interval = self.reconnect_interval_var.get() * 1000
            self.reconnect_timer_id = self.root.after(
                interval, self.try_reconnect)

    def reset_reconnect_count(self):
        self.reconnect_count = 0
        if self.reconnect_timer_id:
            self.root.after_cancel(self.reconnect_timer_id)
            self.reconnect_timer_id = None

    # ==================== 主题 ====================

    def set_theme(self, theme_name):
        """切换 ttkbootstrap 主题"""
        apply_theme(self.root, theme_name)
        self.on_theme_applied()
        self.save_settings()

    def on_theme_applied(self):
        """主题应用后刷新非 ttk 控件（Text/状态栏/波形）配色。

        ttk 控件由 ttkbootstrap 主题自动接管，无需手动配色。
        颜色全部取自当前主题色板（get_color），不自定义颜色表。
        """
        # 统一 Treeview 外观：字体与 Text 控件一致、去缩进
        # 行高按中文回退字体的实际测量值动态计算（点数会随 DPI 缩放，
        # 写死像素行高在高分屏下会裁切中文），上下留余量实现垂直居中
        style = ttk.Style()
        cn_font = tkfont.Font(family='Microsoft YaHei', size=10)
        row_height = max(24, cn_font.metrics('linespace') + 10)
        style.configure('Treeview', font=('Consolas', 10),
                        rowheight=row_height, indent=0)
        style.configure('Treeview.Heading',
                        font=('Microsoft YaHei', 9, 'bold'), indent=0)

        # 命令行选中高亮样式（随主题换色）
        self._config_cmd_selection_style()

        # 命令页 Canvas 为经典 Tk 控件，不随 ttk 主题，需手动配色
        for canvas in self.command_canvases.values():
            canvas.configure(bg=get_color('bg_input'))

        # 接收区文本
        for tw in [self.string_recv_text, self.hex_recv_text, self.compare_recv_text]:
            tw.configure(bg=get_color('bg_input'), fg=get_color('text'),
                         insertbackground=get_color('text'),
                         selectbackground=get_color('select_bg'))
            self._configure_text_tags(tw)

        # 发送区文本
        for tw in [self.string_input, self.hex_input]:
            tw.configure(bg=get_color('bg_input'), fg=get_color('text'),
                         insertbackground=get_color('text'),
                         selectbackground=get_color('select_bg'))

        # 状态栏
        if self.is_connected:
            self.status_label.configure(foreground=get_color('success'))
        else:
            self.status_label.configure(foreground=get_color('error'))

        # 波形窗口
        if self.waveform_fig:
            self.waveform_fig.set_facecolor(get_color('background'))
            if self.waveform_ax:
                self.waveform_ax.set_facecolor(get_color('bg_input'))
                self.waveform_ax.tick_params(colors=get_color('text'))
                self.waveform_ax.xaxis.label.set_color(get_color('text'))
                self.waveform_ax.yaxis.label.set_color(get_color('text'))
                for spine in self.waveform_ax.spines.values():
                    spine.set_color(get_color('border'))
            if self.waveform_line:
                self.waveform_line.set_color(get_color('recv'))
            if self.waveform_canvas:
                self.waveform_canvas.draw_idle()

        # 重建菜单（菜单颜色跟随主题）
        self.create_menu_bar()

    # ==================== 对话框 ====================

    def _center_dialog(self, dialog, width=None, height=None):
        """将对话框居中显示在主窗口中央"""
        dialog.update_idletasks()
        if width is None or height is None:
            width = dialog.winfo_reqwidth()
            height = dialog.winfo_reqheight()
        parent = self.root
        parent_x = parent.winfo_rootx()
        parent_y = parent.winfo_rooty()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        x = parent_x + (parent_w - width) // 2
        y = parent_y + (parent_h - height) // 2
        dialog.geometry(f"{width}x{height}+{x}+{y}")

    def show_serial_settings_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(t("串口设置 - 更多设置"))
        dialog.transient(self.root)
        dialog.grab_set()

        main = ttk.Frame(dialog, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # 串口选择行
        row0 = ttk.Frame(main)
        row0.pack(fill=tk.X, pady=4)
        ttk.Label(row0, text=t("串口:"), width=8).pack(side=tk.LEFT)
        port_combo = ttk.Combobox(row0, state='readonly', width=28)
        port_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)
        ports = self.serial_manager.scan_ports()
        port_values = [f"{n} - {d}" for n, d in ports]
        port_combo['values'] = port_values
        if self.port_var.get():
            for i, v in enumerate(port_values):
                if v == self.port_var.get():
                    port_combo.current(i)
                    break

        def refresh():
            p = self.serial_manager.scan_ports()
            vals = [f"{n} - {d}" for n, d in p]
            cur = port_combo.get()
            port_combo['values'] = vals
            for i, v in enumerate(vals):
                if v == cur:
                    port_combo.current(i)
                    break

        ttk.Button(row0, text=t("刷新"), command=refresh,
                   width=5).pack(side=tk.LEFT, padx=4)

        # 波特率
        row1 = ttk.Frame(main)
        row1.pack(fill=tk.X, pady=4)
        ttk.Label(row1, text=t("波特率:"), width=8).pack(side=tk.LEFT)
        baud_combo = ttk.Combobox(row1, values=BAUDRATES, width=28)
        baud_combo.set(self.baudrate_var.get())
        baud_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        # 数据位
        row2 = ttk.Frame(main)
        row2.pack(fill=tk.X, pady=4)
        ttk.Label(row2, text=t("数据位:"), width=8).pack(side=tk.LEFT)
        data_combo = ttk.Combobox(row2, values=['5', '6', '7', '8'],
                                  state='readonly', width=28)
        data_combo.set(self.databits_var.get())
        data_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        # 停止位
        row3 = ttk.Frame(main)
        row3.pack(fill=tk.X, pady=4)
        ttk.Label(row3, text=t("停止位:"), width=8).pack(side=tk.LEFT)
        stop_combo = ttk.Combobox(row3, values=['1', '1.5', '2'],
                                  state='readonly', width=28)
        stop_combo.set(self.stopbits_var.get())
        stop_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        # 校验位
        row4 = ttk.Frame(main)
        row4.pack(fill=tk.X, pady=4)
        ttk.Label(row4, text=t("校验位:"), width=8).pack(side=tk.LEFT)
        parity_combo = ttk.Combobox(row4, values=['None', 'Even', 'Odd', 'Mark', 'Space'],
                                    state='readonly', width=28)
        parity_combo.set(self.parity_var.get())
        parity_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        # 硬件流控制
        rtscts_var = tk.BooleanVar(value=self.rtscts_var.get())
        ttk.Checkbutton(main, text=t("启用硬件流控制 (RTS/CTS)"),
                        variable=rtscts_var).pack(anchor=tk.W, pady=4)

        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        # 连接状态与操作
        status_frame = ttk.Frame(main)
        status_frame.pack(fill=tk.X, pady=4)
        ttk.Label(status_frame, text=t("连接状态:")).pack(side=tk.LEFT)
        status_lbl = ttk.Label(status_frame, text=t("已连接") if self.is_connected else t("未连接"),
                               foreground=get_color('success') if self.is_connected else get_color('error'))
        status_lbl.pack(side=tk.LEFT, padx=8)

        btn_text = t("断开") if self.is_connected else t("连接")
        conn_btn = ttk.Button(status_frame, text=btn_text)
        conn_btn.pack(side=tk.RIGHT, padx=4)

        def on_connect():
            if self.is_connected:
                self.disconnect_serial()
                conn_btn.configure(text=t("连接"))
                status_lbl.configure(text=t("未连接"), foreground=get_color('error'))
                self.connect_btn.configure(text=t("连接"))
            else:
                cur = port_combo.get()
                if cur:
                    self.port_var.set(cur)
                self.baudrate_var.set(baud_combo.get())
                self.databits_var.set(data_combo.get())
                self.stopbits_var.set(stop_combo.get())
                self.parity_var.set(parity_combo.get())
                self.rtscts_var.set(rtscts_var.get())
                self.connect_serial()
                if self.is_connected:
                    conn_btn.configure(text=t("断开"))
                    status_lbl.configure(
                        text=t("已连接"), foreground=get_color('success'))
                    self.connect_btn.configure(text=t("断开"))

        conn_btn.configure(command=on_connect)

        # 底部按钮
        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=(8, 4))
        btn_frame = ttk.Frame(main)
        btn_frame.pack(fill=tk.X, pady=(4, 0))

        def on_ok():
            cur = port_combo.get()
            if cur:
                self.port_var.set(cur)
            self.baudrate_var.set(baud_combo.get())
            self.databits_var.set(data_combo.get())
            self.stopbits_var.set(stop_combo.get())
            self.parity_var.set(parity_combo.get())
            self.rtscts_var.set(rtscts_var.get())
            self.save_settings()
            dialog.destroy()

        ttk.Button(btn_frame, text=t("确定"), command=on_ok).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text=t("取消"),
                   command=dialog.destroy).pack(side=tk.RIGHT)

        # 自适应大小并居中
        self._center_dialog(dialog)

        self.root.wait_window(dialog)

    def _show_hex_newline_dialog(self):
        result = simpledialog.askinteger(
            t("HEX换行字节数"),
            t("设置HEX显示每多少字节换行（0为不限制）："),
            initialvalue=self._safe_int(self.hex_newline_count_var, 0),
            minvalue=0, maxvalue=256,
            parent=self.root)
        if result is not None:
            self.hex_newline_count_var.set(result)
            self.save_settings()

    def show_reconnect_settings_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(t("自动重连设置"))
        dialog.geometry("380x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        main = ttk.Frame(dialog, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        ar_var = tk.BooleanVar(value=self.auto_reconnect_var.get())
        ttk.Checkbutton(main, text=t("启用自动重连"), variable=ar_var).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=4)

        ttk.Label(main, text=t("间隔 (秒):")).grid(
            row=1, column=0, sticky=tk.W, pady=4)
        interval_spin = ttk.Spinbox(main, from_=1, to=30, width=10)
        interval_spin.set(self.reconnect_interval_var.get())
        interval_spin.grid(row=1, column=1, sticky=tk.W, pady=4, padx=4)

        ttk.Label(main, text=t("最大次数:")).grid(
            row=2, column=0, sticky=tk.W, pady=4)
        max_spin = ttk.Spinbox(main, from_=1, to=999, width=10)
        max_spin.set(self.reconnect_max_var.get())
        max_spin.grid(row=2, column=1, sticky=tk.W, pady=4, padx=4)

        def on_ok():
            self.auto_reconnect_var.set(ar_var.get())
            self.reconnect_interval_var.set(int(interval_spin.get()))
            self.reconnect_max_var.set(int(max_spin.get()))
            self.save_settings()
            dialog.destroy()

        btn_frame = ttk.Frame(main)
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(15, 0))
        ttk.Button(btn_frame, text=t("确定"), command=on_ok).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text=t("取消"),
                   command=dialog.destroy).pack(side=tk.RIGHT)

        self.root.wait_window(dialog)

    def show_record_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title(t("数据记录"))
        dialog.geometry("400x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        main = ttk.Frame(dialog, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        is_recording = self.log_file is not None
        btn_text = t("停止记录") if is_recording else t("开始记录")
        rec_btn = ttk.Button(main, text=btn_text)
        rec_btn.pack(fill=tk.X, pady=4)

        file_info = t("文件: {name}").format(
            name=os.path.basename(self.log_file_path)) if is_recording else t("未记录")
        status_lbl = ttk.Label(main, text=file_info)
        status_lbl.pack(fill=tk.X, pady=4)

        def toggle():
            self.toggle_log()
            is_rec = self.log_file is not None
            rec_btn.configure(text=t("停止记录") if is_rec else t("开始记录"))
            status_lbl.configure(
                text=t("文件: {name}").format(
                    name=os.path.basename(self.log_file_path)) if is_rec else t("未记录"))

        rec_btn.configure(command=toggle)

        ttk.Button(main, text=t("确定"), command=dialog.destroy).pack(side=tk.RIGHT, pady=(10, 0))

        self.root.wait_window(dialog)

    # ==================== 设置保存/加载 ====================

    def _safe_int(self, var, default=0):
        try:
            v = var.get()
            return v if v else default
        except (tk.TclError, ValueError):
            return default

    def save_settings(self):
        settings = {
            'port': self.port_var.get(),
            'baudrate': self.baudrate_var.get(),
            'databits': self.databits_var.get(),
            'stopbits': self.stopbits_var.get(),
            'parity': self.parity_var.get(),
            'rtscts': self.rtscts_var.get(),
            'encoding': self.encoding_var.get(),
            'send_encoding': self.send_encoding_var.get(),
            'timestamp': self.timestamp_var.get(),
            'hex_addr': self.hex_addr_var.get(),
            'hex_newline_count': self._safe_int(self.hex_newline_count_var, 0),
            'direction': self.direction_var.get(),
            'echo': self.echo_var.get(),
            'auto_escape': self.auto_escape_var.get(),
            'crlf': self.crlf_var.get(),
            'loop_interval': self._safe_int(self.loop_interval_var, 1000),
            'loop_count': self._safe_int(self.loop_count_var, 0),
            'auto_reconnect': self.auto_reconnect_var.get(),
            'reconnect_interval': self._safe_int(self.reconnect_interval_var, 5),
            'reconnect_max': self._safe_int(self.reconnect_max_var, 10),
            'theme': get_current_theme(),
            'send_mode': self.send_notebook.index('current'),
            'string_input': self.string_input.get('1.0', tk.END).rstrip('\n'),
            'hex_input': self.hex_input.get('1.0', tk.END).rstrip('\n'),
            'waveform_bytesize': self.waveform_bytesize,
            'waveform_endian': self.waveform_endian,
            'waveform_settings': self.waveform_settings,
            'hist_panel_width': self.hist_panel_width,
            'cmd_btn_width': self.cmd_btn_width_var.get(),
            'current_page': self._get_current_page_name(),
            'recv_timeout': self._safe_int(self.recv_timeout_var, 0),
            'frame_enable': self.frame_enable_var.get(),
            'frame_header_content': self.frame_header_content_var.get(),
            'frame_footer_content': self.frame_footer_content_var.get(),
            'frame_hex': self.frame_hex_var.get(),
            'language': get_language(),
            'auto_wrap': self.auto_wrap_var.get(),
        }
        try:
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_settings(self):
        if not os.path.exists(SETTINGS_FILE):
            return

        try:
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                s = json.load(f)
        except Exception:
            return

        self.port_var.set(s.get('port', ''))
        self.baudrate_var.set(s.get('baudrate', '115200'))
        self.databits_var.set(s.get('databits', '8'))
        self.stopbits_var.set(s.get('stopbits', '1'))
        self.parity_var.set(s.get('parity', 'None'))
        self.rtscts_var.set(s.get('rtscts', False))
        self.encoding_var.set(s.get('encoding', 'GB2312'))
        self.send_encoding_var.set(s.get('send_encoding', 'GB2312'))
        self.timestamp_var.set(s.get('timestamp', True))
        self.hex_addr_var.set(s.get('hex_addr', False))
        self.hex_newline_count_var.set(s.get('hex_newline_count', 0))
        self.direction_var.set(s.get('direction', True))
        self.echo_var.set(s.get('echo', True))
        self.auto_escape_var.set(s.get('auto_escape', False))
        self.crlf_var.set(s.get('crlf', False))
        self.loop_interval_var.set(s.get('loop_interval', 1000))
        self.loop_count_var.set(s.get('loop_count', 0))
        self.auto_reconnect_var.set(s.get('auto_reconnect', False))
        self.reconnect_interval_var.set(s.get('reconnect_interval', 5))
        self.reconnect_max_var.set(s.get('reconnect_max', 10))
        self.recv_timeout_var.set(s.get('recv_timeout', 0))
        self.waveform_bytesize = s.get('waveform_bytesize', 2)
        self.waveform_endian = s.get('waveform_endian', 'little')
        self.waveform_settings = s.get('waveform_settings', {})
        self.frame_enable_var.set(s.get('frame_enable', False))
        self.frame_header_content_var.set(s.get('frame_header_content', ''))
        self.frame_footer_content_var.set(s.get('frame_footer_content', ''))
        self.frame_hex_var.set(s.get('frame_hex', False))
        self.auto_wrap_var.set(s.get('auto_wrap', False))
        self._toggle_auto_wrap()

        # 右侧面板宽度（sashpos 是分割线 x 坐标，需换算：位置 = 总宽 - 面板宽）
        hist_width = s.get('hist_panel_width', 220)
        if hasattr(self, 'content_pw') and hasattr(self, 'hist_frame'):
            hist_width = max(100, min(800, hist_width))
            self.hist_panel_width = hist_width
            if hasattr(self, 'hist_width_var'):
                self.hist_width_var.set(hist_width)
            # 启动时窗口未完成布局，_set_right_panel_width 内部会延迟重试
            self._set_right_panel_width(hist_width)

        # 按钮宽度
        cmd_btn_width = s.get('cmd_btn_width', 4)
        if hasattr(self, 'cmd_btn_width_var'):
            self.cmd_btn_width_var.set(cmd_btn_width)
            self._update_cmd_btn_width(cmd_btn_width)

        # 恢复上次选中的命令页面（按名称，页面不存在则保持第一页）
        cur_page = s.get('current_page', '')
        if cur_page and hasattr(self, 'page_selector'):
            pages = self.command_manager.get_pages()
            if cur_page in pages:
                self._switch_to_page(pages.index(cur_page))

        # 发送框内容
        self.string_input.delete('1.0', tk.END)
        self.string_input.insert('1.0', s.get('string_input', ''))
        self.hex_input.delete('1.0', tk.END)
        self.hex_input.insert('1.0', s.get('hex_input', ''))

        # 发送选项卡
        send_mode = s.get('send_mode', 0)
        try:
            self.send_notebook.select(send_mode)
        except Exception:
            pass

        # 初始化发送模式状态
        self._on_send_tab_changed(None)

        # 主题
        theme = s.get('theme', 'bootstrap-light')
        if theme in get_themes():
            self.set_theme(theme)

    # ==================== 工具方法 ====================

    def update_counts(self):
        self.recv_count_label.configure(
            text=t("接收: {n} 字节").format(n=self.recv_bytes))
        self.send_count_label.configure(
            text=t("发送: {n} 字节").format(n=self.sent_bytes))

    def _create_scrolled_text(self, parent):
        """创建带滚动条的只读 Text 控件"""
        frame = ttk.Frame(parent)
        frame.pack(fill=tk.BOTH, expand=True)

        text = tk.Text(frame, wrap=tk.NONE, state=tk.DISABLED, undo=False,
                       font=('Consolas', 10), width=0, height=0)
        y_scroll = ttk.Scrollbar(frame, orient=tk.VERTICAL, command=text.yview)
        x_scroll = ttk.Scrollbar(
            frame, orient=tk.HORIZONTAL, command=text.xview)
        text.configure(yscrollcommand=y_scroll.set,
                       xscrollcommand=x_scroll.set)

        text.grid(row=0, column=0, sticky='nsew')
        y_scroll.grid(row=0, column=1, sticky='ns')
        x_scroll.grid(row=1, column=0, sticky='ew')

        frame.grid_rowconfigure(0, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        return text

    def _configure_text_tags(self, text_widget):
        """为 Text 控件配置颜色标签"""
        text_widget.tag_configure(
            'timestamp', foreground=get_color('timestamp'))
        text_widget.tag_configure('recv', foreground=get_color('recv'))
        text_widget.tag_configure('send', foreground=get_color('send'))
        text_widget.tag_configure('error', foreground=get_color('error'))
        text_widget.tag_configure('timeout', foreground='gray')
        text_widget.tag_configure('text_color', foreground=get_color('text'))

    def _append_text(self, text_widget, content, tags=None):
        """向只读 Text 控件追加文本"""
        text_widget.configure(state=tk.NORMAL)
        if tags:
            text_widget.insert(tk.END, content, tags)
        else:
            text_widget.insert(tk.END, content)
        text_widget.see(tk.END)
        text_widget.configure(state=tk.DISABLED)

    def _append_text_rich(self, text_widget, parts, tags):
        """向只读 Text 控件追加多段带不同标签的文本"""
        text_widget.configure(state=tk.NORMAL)
        for part, tag in zip(parts, tags):
            text_widget.insert(tk.END, part, (tag,))
        text_widget.see(tk.END)
        text_widget.configure(state=tk.DISABLED)

    def on_closing(self):
        """窗口关闭处理"""
        # 停止定时器
        if self.scan_timer_id:
            self.root.after_cancel(self.scan_timer_id)
        if self.loop_timer_id:
            self.root.after_cancel(self.loop_timer_id)
        if self.reconnect_timer_id:
            self.root.after_cancel(self.reconnect_timer_id)
        if getattr(self, '_reconnect_timer_id', None):
            self.root.after_cancel(self._reconnect_timer_id)
            self._reconnect_timer_id = None

        # 停止接收线程
        if self.receive_thread:
            self.receive_thread.stop()

        # 断开串口
        self.serial_manager.disconnect()

        # 停止日志
        if self.log_file:
            self.stop_log()

        # 关闭波形窗口
        if self.waveform_window and self.waveform_window.winfo_exists():
            self.waveform_window.destroy()

        # 保存设置
        self.save_settings()

        self.root.destroy()
