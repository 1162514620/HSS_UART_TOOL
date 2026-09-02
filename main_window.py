import tkinter as tk
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
from styles import (get_color, set_theme, get_current_theme, apply_theme,
                    get_themes, DARK_THEMES, get_theme_type)


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
        self.loop_var = tk.BooleanVar(value=False)
        self.loop_interval_var = tk.IntVar(value=1000)
        self.loop_count_var = tk.IntVar(value=0)
        self.auto_reconnect_var = tk.BooleanVar(value=False)
        self.reconnect_interval_var = tk.IntVar(value=5)
        self.reconnect_max_var = tk.IntVar(value=10)

        # 校验自动添加
        self.checksum_enable_var = tk.BooleanVar(value=False)
        self.checksum_start_var = tk.IntVar(value=0)
        self.checksum_end_var = tk.StringVar(value='末尾')
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
        menubar.add_cascade(label="数据", menu=data_menu)
        data_menu.add_command(label="导出数据", command=self.export_data)
        data_menu.add_command(label="数据记录", command=self.show_record_dialog)

        # 主题菜单（使用 ttkbootstrap 内置主题）
        theme_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="主题", menu=theme_menu)

        all_themes = get_themes()
        light_themes = [t for t in all_themes if t not in DARK_THEMES]

        theme_menu.add_command(label="── 深色主题 ──", state='disabled')
        for theme_name in sorted(DARK_THEMES):
            theme_menu.add_command(
                label=f"    {theme_name}",
                command=lambda t=theme_name: self.set_theme(t))

        theme_menu.add_separator()
        theme_menu.add_command(label="── 浅色主题 ──", state='disabled')
        for theme_name in sorted(light_themes):
            theme_menu.add_command(
                label=f"    {theme_name}",
                command=lambda t=theme_name: self.set_theme(t))

        # 编码菜单
        encoding_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="编码", menu=encoding_menu)

        recv_enc_menu = tk.Menu(encoding_menu, tearoff=0)
        encoding_menu.add_cascade(label="接收编码", menu=recv_enc_menu)
        for enc in ENCODINGS:
            recv_enc_menu.add_radiobutton(
                label=enc, variable=self.encoding_var, value=enc,
                command=self.save_settings)

        encoding_menu.add_separator()

        send_enc_menu = tk.Menu(encoding_menu, tearoff=0)
        encoding_menu.add_cascade(label="发送编码", menu=send_enc_menu)
        for enc in ENCODINGS:
            send_enc_menu.add_radiobutton(
                label=enc, variable=self.send_encoding_var, value=enc,
                command=self.save_settings)

        # 设置菜单
        settings_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="设置", menu=settings_menu)
        settings_menu.add_command(
            label="自动重连设置", command=self.show_reconnect_settings_dialog)
        settings_menu.add_separator()
        settings_menu.add_checkbutton(label="地址偏移", variable=self.hex_addr_var,
                                      command=self.save_settings)
        settings_menu.add_command(
            label="HEX换行字节数...", command=self._show_hex_newline_dialog)

        # 扩展菜单
        extend_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="扩展", menu=extend_menu)
        extend_menu.add_command(label="波形显示", command=self.toggle_waveform)

        # 帮助菜单
        help_menu = tk.Menu(menubar, tearoff=0)
        menubar.add_cascade(label="帮助", menu=help_menu)
        help_menu.add_command(label="使用说明", command=self.show_help)

    # ==================== 串口控制栏 ====================

    def create_serial_control_bar(self):
        """在接收区上方添加串口控制栏"""
        self.ctrl_frame = ttk.LabelFrame(self.root, text="串口控制")
        self.ctrl_frame.pack(fill=tk.X, padx=6, pady=(6, 2))

        row1 = ttk.Frame(self.ctrl_frame)
        row1.pack(fill=tk.X, padx=4, pady=(4, 2))

        ttk.Label(row1, text="串口:").pack(side=tk.LEFT, padx=(0, 2))
        self.port_combo = ttk.Combobox(row1, textvariable=self.port_var,
                                       state='readonly', width=20)
        self.port_combo.pack(side=tk.LEFT, padx=2)
        ttk.Button(row1, text="刷新", command=self.refresh_ports_ui,
                   width=5).pack(side=tk.LEFT, padx=2)

        ttk.Separator(row1, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(row1, text="波特率:").pack(side=tk.LEFT, padx=(0, 2))
        self.baudrate_combo = ttk.Combobox(row1, textvariable=self.baudrate_var,
                                           values=BAUDRATES, width=8)
        self.baudrate_combo.pack(side=tk.LEFT, padx=2)

        ttk.Separator(row1, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        ttk.Label(row1, text="校验:").pack(side=tk.LEFT, padx=(0, 2))
        self.parity_combo = ttk.Combobox(row1, textvariable=self.parity_var,
                                         values=['None', 'Even',
                                                 'Odd', 'Mark', 'Space'],
                                         state='readonly', width=7)
        self.parity_combo.pack(side=tk.LEFT, padx=2)

        ttk.Separator(row1, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)

        self.connect_btn = ttk.Button(row1, text="连接",
                                      command=self.toggle_connection)
        self.connect_btn.pack(side=tk.LEFT, padx=4)

        ttk.Button(row1, text="更多设置", command=self.show_serial_settings_dialog).pack(
            side=tk.LEFT, padx=2)

    def refresh_ports_ui(self):
        """刷新串口列表（更新UI控件）"""
        ports = self.serial_manager.scan_ports()
        self.last_ports = ports
        values = [f"{n} - {d}" for n, d in ports]
        self.port_combo['values'] = values
        if values and not self.port_var.get():
            self.port_combo.current(0)

    # ==================== 主内容区 ====================

    def create_main_content(self):
        """创建主内容区：左侧(接收+发送) + 右侧(多命令发送)"""
        content = ttk.Frame(self.root)
        content.pack(fill=tk.BOTH, expand=True, padx=6, pady=2)

        # 左侧：接收区 + 发送区（纵向排列，横向自动伸缩）
        self.left_frame = ttk.Frame(content)
        self.left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.create_receive_area(self.left_frame)
        self.create_send_area(self.left_frame)

        # 右侧：多命令发送（固定宽度，纵向自动伸缩）
        self.create_command_panel(content)

    # ==================== 接收区 ====================

    def create_receive_area(self, parent):
        """创建接收区，操作按键在文本框下方"""
        self.recv_frame = ttk.LabelFrame(parent, text="接收区")
        self.recv_frame.pack(fill=tk.BOTH, expand=True, padx=0, pady=(0, 2))

        # Notebook (字符串/HEX 选项卡) - 占据主要空间
        self.recv_notebook = ttk.Notebook(self.recv_frame)
        self.recv_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))

        # 字符串选项卡
        string_tab = ttk.Frame(self.recv_notebook)
        self.recv_notebook.add(string_tab, text="字符串")
        self.string_recv_text = self._create_scrolled_text(string_tab)

        # HEX 选项卡
        hex_tab = ttk.Frame(self.recv_notebook)
        self.recv_notebook.add(hex_tab, text="HEX")
        self.hex_recv_text = self._create_scrolled_text(hex_tab)

        # 配置文本标签颜色
        self._configure_text_tags(self.string_recv_text)
        self._configure_text_tags(self.hex_recv_text)

        # 操作工具栏 - 在文本框下方
        toolbar = ttk.Frame(self.recv_frame)
        toolbar.pack(fill=tk.X, padx=4, pady=(0, 4))

        ttk.Button(toolbar, text="清空接收区", command=self.clear_receive_area).pack(
            side=tk.LEFT, padx=2)
        self.pause_btn = ttk.Button(
            toolbar, text="暂停显示", command=self.toggle_pause)
        self.pause_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Checkbutton(toolbar, text="时间戳", variable=self.timestamp_var).pack(
            side=tk.LEFT, padx=2)
        ttk.Checkbutton(toolbar, text="方向", variable=self.direction_var).pack(
            side=tk.LEFT, padx=2)
        ttk.Checkbutton(toolbar, text="回显", variable=self.echo_var).pack(
            side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Label(toolbar, text="超时:").pack(side=tk.LEFT)
        self.recv_timeout_var = tk.IntVar(value=0)
        self.recv_timeout_var.trace_add('write', self._on_recv_timeout_changed)
        ttk.Spinbox(toolbar, from_=0, to=10000000,
                    textvariable=self.recv_timeout_var, width=8).pack(
            side=tk.LEFT, padx=2)
        ttk.Label(toolbar, text="us(0=自动)").pack(side=tk.LEFT)

    # ==================== 发送区 ====================

    def create_send_area(self, parent):
        """创建发送区（不含历史记录，历史在右侧）"""
        self.send_frame = ttk.LabelFrame(parent, text="发送区")
        self.send_frame.pack(fill=tk.X, padx=0, pady=(2, 0))

        # Notebook (字符串/HEX 输入)
        self.send_notebook = ttk.Notebook(self.send_frame)
        self.send_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=(4, 0))

        # 字符串输入
        str_tab = ttk.Frame(self.send_notebook)
        self.send_notebook.add(str_tab, text="字符串")
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

        self.send_btn = ttk.Button(toolbar, text=" 发送 ",
                                   command=self.send_data)
        self.send_btn.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)
        self.auto_escape_cb = ttk.Checkbutton(toolbar, text="自动转义", variable=self.auto_escape_var)
        self.auto_escape_cb.pack(side=tk.LEFT, padx=2)
        self.crlf_cb = ttk.Checkbutton(toolbar, text="回车换行", variable=self.crlf_var)
        self.crlf_cb.pack(side=tk.LEFT, padx=2)

        ttk.Separator(toolbar, orient=tk.VERTICAL).pack(
            side=tk.LEFT, fill=tk.Y, padx=6)
        ttk.Checkbutton(toolbar, text="循环发送", variable=self.loop_var,
                        command=self._on_loop_toggle).pack(side=tk.LEFT, padx=2)
        ttk.Label(toolbar, text="间隔:").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Spinbox(toolbar, from_=1, to=60000, textvariable=self.loop_interval_var,
                    width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(toolbar, text="ms").pack(side=tk.LEFT)
        ttk.Label(toolbar, text="次数:").pack(side=tk.LEFT, padx=(8, 0))
        ttk.Spinbox(toolbar, from_=0, to=999999, textvariable=self.loop_count_var,
                    width=6).pack(side=tk.LEFT, padx=2)
        ttk.Label(toolbar, text="(0=无限)").pack(side=tk.LEFT)

        # 校验自动添加行
        checksum_row = ttk.Frame(self.send_frame)
        checksum_row.pack(fill=tk.X, padx=4, pady=(0, 4))

        self.checksum_checkbtn = ttk.Checkbutton(checksum_row, text="校验", variable=self.checksum_enable_var)
        self.checksum_checkbtn.pack(side=tk.LEFT, padx=2)
        ttk.Label(checksum_row, text="第").pack(side=tk.LEFT, padx=(4, 0))
        self.checksum_start_spin = ttk.Spinbox(checksum_row, from_=0, to=9999,
                    textvariable=self.checksum_start_var, width=4)
        self.checksum_start_spin.pack(side=tk.LEFT, padx=2)
        ttk.Label(checksum_row, text="字节到第").pack(side=tk.LEFT)
        self.checksum_end_combo = ttk.Combobox(checksum_row, textvariable=self.checksum_end_var,
                     values=['末尾', '-1', '-2', '-3', '-4'], width=4,
                     state='readonly')
        self.checksum_end_combo.pack(side=tk.LEFT, padx=2)
        ttk.Label(checksum_row, text="字节").pack(side=tk.LEFT)
        self.checksum_type_combo = ttk.Combobox(checksum_row, textvariable=self.checksum_type_var,
                     values=['ADD8', 'ADD16', 'XOR8', 'ModBusCRC16'],
                     width=12, state='readonly')
        self.checksum_type_combo.pack(side=tk.LEFT, padx=(8, 2))

        # 帧头帧尾行
        frame_row = ttk.Frame(self.send_frame)
        frame_row.pack(fill=tk.X, padx=4, pady=(0, 4))

        ttk.Checkbutton(frame_row, text="添加帧头帧尾", variable=self.frame_enable_var).pack(
            side=tk.LEFT, padx=2)
        ttk.Label(frame_row, text="帧头:").pack(side=tk.LEFT, padx=(4, 0))
        self.frame_header_entry = ttk.Entry(frame_row, textvariable=self.frame_header_content_var,
                                            width=10, font=('Consolas', 9))
        self.frame_header_entry.pack(side=tk.LEFT, padx=2)
        ttk.Label(frame_row, text="帧尾:").pack(side=tk.LEFT, padx=(4, 0))
        self.frame_footer_entry = ttk.Entry(frame_row, textvariable=self.frame_footer_content_var,
                                            width=10, font=('Consolas', 9))
        self.frame_footer_entry.pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(frame_row, text="HEX", variable=self.frame_hex_var).pack(
            side=tk.LEFT, padx=(6, 2))

    # ==================== 多命令发送面板 ====================

    def create_command_panel(self, parent):
        """创建右侧面板（多命令发送 / 自动应答 切换）"""
        self.hist_panel_width = 220
        self.hist_frame = ttk.LabelFrame(parent, text="功能面板")
        self.hist_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(6, 0))

        self.hist_frame.configure(width=self.hist_panel_width)
        self.hist_frame.pack_propagate(False)

        # 顶层 Tab：多命令发送 / 自动应答
        self.func_notebook = ttk.Notebook(self.hist_frame)
        self.func_notebook.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # === 多命令发送 Tab ===
        cmd_tab = ttk.Frame(self.func_notebook)
        self.func_notebook.add(cmd_tab, text="多命令发送")

        # 页面 Notebook（在多命令发送 Tab 内部）
        self.hist_notebook = ttk.Notebook(cmd_tab)
        self.hist_notebook.pack(fill=tk.BOTH, expand=True)
        self.hist_notebook.bind('<Button-3>', self._on_tab_right_click)

        self.hist_listboxes: dict = {}
        for page_name in self.command_manager.get_pages():
            self._add_command_tab(page_name)

        # 底部按钮：两行布局
        cmd_bottom = ttk.Frame(cmd_tab)
        cmd_bottom.pack(fill=tk.X, padx=2, pady=(0, 2))

        btn_row1 = ttk.Frame(cmd_bottom)
        btn_row1.pack(fill=tk.X, pady=(0, 2))
        ttk.Button(btn_row1, text="新增页面",
                   command=self._add_new_command_page).pack(
                       side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(btn_row1, text="删除页面",
                   command=self._delete_current_command_page).pack(
                       side=tk.LEFT, fill=tk.X, expand=True)

        btn_row2 = ttk.Frame(cmd_bottom)
        btn_row2.pack(fill=tk.X)
        ttk.Button(btn_row2, text="添加命令",
                   command=self._add_command_to_current_page).pack(
                       side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(btn_row2, text="清空当前",
                   command=self.clear_commands).pack(
                       side=tk.LEFT, fill=tk.X, expand=True)

        # === 自动应答 Tab ===
        self._create_auto_reply_tab()

        # 面板底部：宽度设置
        bottom = ttk.Frame(self.hist_frame)
        bottom.pack(fill=tk.X, padx=4, pady=(0, 4))
        width_row = ttk.Frame(bottom)
        width_row.pack(fill=tk.X)
        ttk.Label(width_row, text="宽度:").pack(side=tk.LEFT)
        self.hist_width_var = tk.IntVar(value=self.hist_panel_width)
        ttk.Spinbox(width_row, from_=100, to=500, textvariable=self.hist_width_var,
                    width=5, command=self._apply_hist_width).pack(side=tk.LEFT, padx=2)
        ttk.Button(width_row, text="设置", width=4,
                   command=self._apply_hist_width).pack(side=tk.LEFT)

    def _create_auto_reply_tab(self):
        """创建自动应答 Tab"""
        reply_tab = ttk.Frame(self.func_notebook)
        self.func_notebook.add(reply_tab, text="自动应答")

        # 开启/关闭按钮
        top_row = ttk.Frame(reply_tab)
        top_row.pack(fill=tk.X, padx=2, pady=2)
        self.auto_reply_btn = ttk.Button(top_row, text="开启自动应答",
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
        self.reply_rules_list.heading('status', text='状态')
        self.reply_rules_list.heading('mode', text='模式')
        self.reply_rules_list.heading('trigger', text='触发')
        self.reply_rules_list.heading('reply', text='响应')
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
        ttk.Button(btn_row, text="添加规则",
                   command=self._add_reply_rule).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 2))
        ttk.Button(btn_row, text="删除规则",
                   command=self._delete_reply_rule).pack(side=tk.LEFT, fill=tk.X, expand=True)

    def _toggle_auto_reply(self):
        self.auto_reply_enabled = not self.auto_reply_enabled
        if self.auto_reply_enabled:
            self.auto_reply_btn.configure(text="关闭自动应答")
        else:
            self.auto_reply_btn.configure(text="开启自动应答")

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
        menu.add_command(label="编辑规则", command=lambda: self._edit_reply_rule())
        menu.add_command(label="删除规则", command=self._delete_reply_rule)
        menu.tk_popup(event.x_root, event.y_root)

    def _create_reply_rule_dialog(self, rule=None, edit_idx=None):
        """创建/编辑自动应答规则对话框"""
        dialog = tk.Toplevel(self.root)
        dialog.title("编辑规则" if rule else "添加规则")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # 匹配模式
        row = 0
        ttk.Label(frame, text="匹配模式:").grid(
            row=row, column=0, sticky='w', pady=2)
        match_mode = tk.StringVar(
            value=rule['match_mode'] if rule else 'string')
        ttk.Combobox(frame, textvariable=match_mode,
                     values=['string', 'hex'], width=10,
                     state='readonly').grid(row=row, column=1, sticky='w', pady=2)

        # 匹配内容
        row += 1
        ttk.Label(frame, text="匹配内容:").grid(
            row=row, column=0, sticky='w', pady=2)
        match_content = tk.StringVar(
            value=rule['match_content'] if rule else '')
        ttk.Entry(frame, textvariable=match_content, width=30).grid(
            row=row, column=1, sticky='w', pady=2)

        # 正则
        row += 1
        use_regex = tk.BooleanVar(value=rule.get(
            'use_regex', False) if rule else False)
        ttk.Checkbutton(frame, text="使用正则表达式", variable=use_regex).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=2)

        # 应答模式
        row += 1
        ttk.Label(frame, text="应答模式:").grid(
            row=row, column=0, sticky='w', pady=2)
        reply_mode = tk.StringVar(
            value=rule['reply_mode'] if rule else 'string')
        ttk.Combobox(frame, textvariable=reply_mode,
                     values=['string', 'hex'], width=10,
                     state='readonly').grid(row=row, column=1, sticky='w', pady=2)

        # 应答内容
        row += 1
        ttk.Label(frame, text="应答内容:").grid(
            row=row, column=0, sticky='w', pady=2)
        reply_content = tk.StringVar(
            value=rule['reply_content'] if rule else '')
        ttk.Entry(frame, textvariable=reply_content, width=30).grid(
            row=row, column=1, sticky='w', pady=2)

        # 延时
        row += 1
        ttk.Label(frame, text="延时(ms):").grid(
            row=row, column=0, sticky='w', pady=2)
        delay = tk.IntVar(value=rule.get('delay', 100) if rule else 100)
        ttk.Spinbox(frame, from_=0, to=60000, textvariable=delay, width=8).grid(
            row=row, column=1, sticky='w', pady=2)

        # 启用
        row += 1
        enabled = tk.BooleanVar(value=rule.get(
            'enabled', True) if rule else True)
        ttk.Checkbutton(frame, text="启用此规则", variable=enabled).grid(
            row=row, column=0, columnspan=2, sticky='w', pady=2)

        # 按钮
        row += 1
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=row, column=0, columnspan=2, pady=(10, 0))

        def on_ok():
            mc = match_content.get().strip()
            rc = reply_content.get().strip()
            if not mc or not rc:
                messagebox.showwarning("提示", "匹配内容和应答内容不能为空", parent=dialog)
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

        ttk.Button(btn_frame, text="确定", command=on_ok).pack(
            side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="取消", command=dialog.destroy).pack(
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
        """创建一个命令页面标签"""
        tab = ttk.Frame(self.hist_notebook)
        self.hist_notebook.add(tab, text=page_name)

        container = ttk.Frame(tab)
        container.pack(fill=tk.BOTH, expand=True)

        scroll = ttk.Scrollbar(container, orient=tk.VERTICAL)
        # 用 ttk.Treeview 替代 Listbox，外观随主题统一
        # show='tree' 只显示 #0 列、无表头；iid=str(index) 便于按索引定位
        tree = ttk.Treeview(container, yscrollcommand=scroll.set,
                            selectmode='browse', show='tree')
        scroll.configure(command=tree.yview)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)

        # 填充数据
        for i, item in enumerate(self.command_manager.get_command_display_list(page_name)):
            tree.insert('', 'end', iid=str(i), text=item)

        # 绑定事件
        tree.bind('<Double-Button-1>', self.on_command_double_click)
        tree.bind('<Button-1>', self.on_command_single_click)
        tree.bind('<Button-3>', self.show_command_context_menu)

        self.hist_listboxes[page_name] = tree

    def _get_current_page_name(self) -> str:
        """获取当前选中的页面名"""
        idx = self.hist_notebook.index('current')
        return self.command_manager.get_pages()[idx]

    def _on_tab_right_click(self, event):
        """右键点击标签页时弹出重命名菜单"""
        # 获取点击位置对应的标签索引
        tab_idx = self.hist_notebook.index(f"@{event.x},{event.y}")
        if tab_idx < 0:
            return
        page_name = self.command_manager.get_pages()[tab_idx]
        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="重命名页面",
                         command=lambda: self._rename_command_page(page_name))
        menu.tk_popup(event.x_root, event.y_root)

    def _rename_command_page(self, old_name: str):
        new_name = simpledialog.askstring(
            "重命名页面", "请输入新的页面名称：",
            initialvalue=old_name, parent=self.root)
        if new_name is None or new_name.strip() == old_name:
            return
        new_name = new_name.strip()
        if not new_name:
            return
        if not self.command_manager.rename_page(old_name, new_name):
            messagebox.showwarning("提示", "页面名称已存在或无效")
            return
        # 更新 UI
        idx = self.command_manager.get_pages().index(new_name)
        self.hist_notebook.tab(idx, text=new_name)
        self.hist_listboxes[new_name] = self.hist_listboxes.pop(old_name)

    def _add_new_command_page(self):
        name = simpledialog.askstring(
            "新增页面", "请输入页面名称：", parent=self.root)
        if name is None:
            return
        name = name.strip()
        if not name:
            return
        if not self.command_manager.add_page(name):
            messagebox.showwarning("提示", "页面名称已存在")
            return
        self._add_command_tab(name)
        self.hist_notebook.select(len(self.command_manager.get_pages()) - 1)

    def _delete_current_command_page(self):
        pages = self.command_manager.get_pages()
        if len(pages) <= 1:
            messagebox.showwarning("提示", "至少需要保留一个页面")
            return
        page_name = self._get_current_page_name()
        if not messagebox.askyesno(
                "确认", f"确定删除页面「{page_name}」及其所有命令？"):
            return
        # 先记下当前索引，再删数据，最后 forget 该 tab
        cur_idx = self.hist_notebook.index('current')
        self.command_manager.remove_page(page_name)
        self.hist_listboxes.pop(page_name, None)
        self.hist_notebook.forget(cur_idx)
        # 选中邻近的 tab
        if cur_idx >= self.hist_notebook.index('end'):
            cur_idx = self.hist_notebook.index('end') - 1
        if cur_idx >= 0:
            self.hist_notebook.select(cur_idx)

    def _add_command_to_current_page(self):
        """打开"添加命令"对话框，添加到当前页面"""
        page = self._get_current_page_name()
        self._command_dialog(page, edit_idx=None)

    def _command_dialog(self, page: str, edit_idx: int = None):
        """添加/编辑命令对话框

        Args:
            page: 目标页面
            edit_idx: 编辑模式时给定索引；None 为新增
        """
        is_edit = edit_idx is not None
        existing = None
        if is_edit:
            cmds = self.command_manager.get_full_commands(page)
            if edit_idx < 0 or edit_idx >= len(cmds):
                return
            existing = cmds[edit_idx]

        dialog = tk.Toplevel(self.root)
        dialog.title("编辑命令" if is_edit else "添加命令")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        frame = ttk.Frame(dialog, padding=10)
        frame.pack(fill=tk.BOTH, expand=True)

        # 模式
        ttk.Label(frame, text="模式:").grid(row=0, column=0, sticky='w', pady=4)
        mode_var = tk.StringVar(value=existing['mode'] if existing else 'string')
        ttk.Combobox(frame, textvariable=mode_var,
                     values=['string', 'hex'], width=10,
                     state='readonly').grid(row=0, column=1, sticky='w', pady=4, padx=4)

        # 标签
        ttk.Label(frame, text="标签:").grid(row=1, column=0, sticky='w', pady=4)
        label_var = tk.StringVar(value=(existing or {}).get('label', ''))
        ttk.Entry(frame, textvariable=label_var, width=30).grid(
            row=1, column=1, sticky='w', pady=4, padx=4)

        # 内容
        ttk.Label(frame, text="内容:").grid(row=2, column=0, sticky='nw', pady=4)
        content_text = tk.Text(frame, width=30, height=4,
                               font=('Consolas', 10), undo=True)
        content_text.grid(row=2, column=1, sticky='w', pady=4, padx=4)
        if existing:
            content_text.insert('1.0', existing.get('content', ''))

        # Hex 校验提示
        hint = ttk.Label(frame, text="", foreground=get_color('error'))
        hint.grid(row=3, column=1, sticky='w', pady=(0, 4), padx=4)

        def validate_hex():
            if mode_var.get() != 'hex':
                hint.configure(text="")
                return True
            raw = content_text.get('1.0', tk.END).strip()
            cleaned = raw.replace(' ', '').upper()
            if not cleaned:
                hint.configure(text="")
                return False
            invalid = set(cleaned) - set('0123456789ABCDEF')
            if invalid:
                hint.configure(text=f"非法字符: {', '.join(sorted(invalid))}")
                return False
            if len(cleaned) % 2 != 0:
                hint.configure(text="Hex 长度必须为偶数")
                return False
            hint.configure(text="")
            return True

        content_text.bind('<KeyRelease>', lambda e: validate_hex())
        mode_var.trace_add('write', lambda *_: validate_hex())

        def on_ok():
            mode = mode_var.get()
            content = content_text.get('1.0', tk.END).strip()
            label = label_var.get().strip()
            if not content:
                messagebox.showwarning("提示", "内容不能为空", parent=dialog)
                return
            if mode == 'hex' and not validate_hex():
                messagebox.showwarning("提示", "Hex 格式错误", parent=dialog)
                return
            if is_edit:
                self.command_manager.update_command(page, edit_idx, content, mode, label)
            else:
                self.command_manager.add_command(content, mode, label, page)
            self._update_current_command_list(page)
            dialog.destroy()

        btn = ttk.Frame(frame)
        btn.grid(row=4, column=0, columnspan=2, pady=(8, 0))
        ttk.Button(btn, text="确定", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn, text="取消", command=dialog.destroy).pack(side=tk.LEFT, padx=5)

        self._center_dialog(dialog)
        self.root.wait_window(dialog)

    def _apply_hist_width(self):
        """应用历史面板宽度"""
        try:
            w = self.hist_width_var.get()
            w = max(100, min(500, w))
            self.hist_frame.configure(width=w)
            self.hist_panel_width = w
        except Exception:
            pass

    # ==================== 状态栏 ====================

    def create_status_bar(self):
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, side=tk.BOTTOM, padx=6, pady=2)

        self.status_label = ttk.Label(self.status_frame, text="状态: 未连接",
                                      style='Status.TLabel',
                                      foreground=get_color('error'))
        self.status_label.pack(side=tk.LEFT)

        self.recv_count_label = ttk.Label(self.status_frame, text="接收: 0 字节")
        self.recv_count_label.pack(side=tk.RIGHT, padx=10)

        self.send_count_label = ttk.Label(self.status_frame, text="发送: 0 字节")
        self.send_count_label.pack(side=tk.RIGHT, padx=10)

        self.send_status_label = ttk.Label(self.status_frame, text="")
        self.send_status_label.pack(side=tk.RIGHT, padx=10)

    # ==================== 事件绑定 ====================

    def setup_connections(self):
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
                messagebox.showwarning("提示", "串口已断开！")

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
                messagebox.showwarning("错误", "请选择串口！")
            return False

        port_name = port_text.split(' - ')[0]

        try:
            baudrate = int(self.baudrate_var.get())
        except ValueError:
            if not silent:
                messagebox.showwarning("错误", "波特率必须是数字！")
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
            self.status_label.configure(text=f"状态: 已连接 {port_name}",
                                        foreground=get_color('success'))
            self.connect_btn.configure(text="断开")

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
                messagebox.showerror("连接失败", f"无法连接串口: {message}")
                if self.auto_reconnect_var.get():
                    self._start_reconnect_timer()
            return False

    def disconnect_serial(self):
        if self.receive_thread:
            self.receive_thread.stop()
            self.receive_thread = None

        self.serial_manager.disconnect()
        self.is_connected = False
        self.status_label.configure(text="状态: 未连接",
                                    foreground=get_color('error'))
        self.connect_btn.configure(text="连接")

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
        """根据当前波特率自动计算超时时间（微秒），为字节间隔的5倍"""
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
        # 转换为微秒，5倍
        timeout_us = int(bits_per_byte / baudrate * 1_000_000 * 5)
        return max(timeout_us, 100)  # 最小100us

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
            elapsed_us = (time.time() - last_ts) * 1_000_000
            if elapsed_us > timeout:
                for tw in [self.string_recv_text, self.hex_recv_text]:
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
        for tw in [self.string_recv_text, self.hex_recv_text]:
            self._append_text(tw, f"[错误] {error_msg}\n", ('error',))

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

    def clear_receive_area(self):
        for tw in [self.string_recv_text, self.hex_recv_text]:
            tw.configure(state=tk.NORMAL)
            tw.delete('1.0', tk.END)
            tw.configure(state=tk.DISABLED)
        self.received_data.clear()
        self.recv_bytes = 0
        self.update_counts()

    def toggle_pause(self):
        self.is_paused = not self.is_paused
        self.pause_btn.configure(text="继续显示" if self.is_paused else "暂停显示")

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
                messagebox.showwarning("编码错误", f"无法用{encoding}编码: {e}")
                return
        else:
            hex_text = self.hex_input.get('1.0', tk.END).strip()
            if not hex_text:
                return
            self.validate_hex_input()
            if self.hex_status_label.cget('text'):
                messagebox.showwarning(
                    "错误", self.hex_status_label.cget('text'))
                return
            data = self.parse_hex_input(hex_text)
            if data is None:
                messagebox.showwarning("错误", "无效的Hex数据格式！")
                return

        # 校验自动添加
        if self.checksum_enable_var.get():
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
            messagebox.showwarning("提示", "未连接串口，数据仅作为回显显示！")
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
                self.status_label.configure(text="状态: 未连接",
                                            foreground=get_color('error'))
                messagebox.showwarning("发送失败", "串口连接已断开！")
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
                messagebox.showwarning("错误", "请先连接串口！")
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
            self.hex_status_label.configure(text=f"非法字符: {', '.join(invalid)}")
        elif len(cleaned) % 2 != 0:
            self.hex_status_label.configure(text="Hex数据长度必须为偶数")
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
        if end_str == '末尾':
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

        if self.checksum_enable_var.get():
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

    def _update_current_command_list(self, page: str = None):
        """刷新指定页面的命令列表显示（默认当前页）"""
        if page is None:
            page = self._get_current_page_name()
        tree = self.hist_listboxes.get(page)
        if not tree:
            return
        tree.delete(*tree.get_children())
        for i, item in enumerate(self.command_manager.get_command_display_list(page)):
            tree.insert('', 'end', iid=str(i), text=item)

    def update_command_lists(self):
        """刷新所有页面的命令列表"""
        for page_name, tree in self.hist_listboxes.items():
            tree.delete(*tree.get_children())
            for i, item in enumerate(self.command_manager.get_command_display_list(page_name)):
                tree.insert('', 'end', iid=str(i), text=item)

    def on_command_single_click(self, event):
        """单击命令：填充到发送框（不发送）"""
        tree = event.widget
        # 延迟执行以确保先完成选择
        self.root.after(100, lambda: self._fill_send_from_command(tree))

    def _tree_selected_index(self, tree):
        """获取 Treeview 当前选中项的整数索引（iid=str(index)）"""
        sel = tree.selection()
        if not sel:
            return None
        try:
            return int(sel[0])
        except (ValueError, IndexError):
            return None

    def _fill_send_from_command(self, tree):
        """将选中命令填充到发送框"""
        idx = self._tree_selected_index(tree)
        if idx is None:
            return
        page = self._get_current_page_name()
        commands = self.command_manager.get_full_commands(page)
        if idx >= len(commands):
            return
        self._load_command_to_send_input(commands[idx])

    def on_command_double_click(self, event):
        """双击命令：填入发送框并立即发送"""
        tree = event.widget
        idx = self._tree_selected_index(tree)
        if idx is None:
            return
        page = self._get_current_page_name()
        commands = self.command_manager.get_full_commands(page)
        if idx >= len(commands):
            return
        self._load_command_to_send_input(commands[idx])
        self.send_data()

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

    def clear_commands(self):
        page = self._get_current_page_name()
        self.command_manager.clear_commands(page)
        tree = self.hist_listboxes.get(page)
        if tree:
            tree.delete(*tree.get_children())

    def show_command_context_menu(self, event):
        tree = event.widget
        iid = tree.identify_row(event.y)
        if not iid:
            return
        tree.selection_remove(tree.selection())
        tree.selection_set(iid)

        menu = tk.Menu(self.root, tearoff=0)
        menu.add_command(label="编辑命令", command=self.edit_selected_command)
        menu.add_command(label="删除命令", command=self.delete_selected_command)
        menu.tk_popup(event.x_root, event.y_root)

    def delete_selected_command(self):
        page = self._get_current_page_name()
        tree = self.hist_listboxes.get(page)
        if not tree:
            return
        idx = self._tree_selected_index(tree)
        if idx is None:
            return
        self.command_manager.remove_command(page, idx)
        # 重建列表以保持 iid 与索引一致
        self._update_current_command_list(page)

    def edit_selected_command(self):
        """打开编辑对话框，编辑当前选中的命令"""
        page = self._get_current_page_name()
        tree = self.hist_listboxes.get(page)
        if not tree:
            return
        idx = self._tree_selected_index(tree)
        if idx is None:
            return
        self._command_dialog(page, edit_idx=idx)

    # ==================== 波形显示 ====================

    def toggle_waveform(self):
        if self.waveform_window and self.waveform_window.winfo_exists():
            self.waveform_window.destroy()
            self.waveform_window = None
            self.waveform_fig = None
            self.waveform_ax = None
            self.waveform_line = None
            self.waveform_canvas = None
        else:
            self.create_waveform_window()

    def create_waveform_window(self):
        try:
            from matplotlib.figure import Figure
            from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        except ImportError:
            messagebox.showwarning(
                "提示", "matplotlib 未安装，波形显示功能不可用。\n请运行: pip install matplotlib")
            return

        self.waveform_window = tk.Toplevel(self.root)
        self.waveform_window.title("波形显示")
        self.waveform_window.geometry("800x500")

        # 控制栏
        ctrl = ttk.Frame(self.waveform_window)
        ctrl.pack(fill=tk.X, padx=4, pady=2)

        ttk.Label(ctrl, text="字节大小:").pack(side=tk.LEFT, padx=2)
        self.waveform_bytesize_var = tk.StringVar(
            value="32位" if self.waveform_bytesize == 4 else "16位")
        ttk.Combobox(ctrl, textvariable=self.waveform_bytesize_var,
                     values=["16位", "32位"], state='readonly', width=6).pack(side=tk.LEFT, padx=2)

        ttk.Label(ctrl, text="字节序:").pack(side=tk.LEFT, padx=2)
        self.waveform_endian_var = tk.StringVar(
            value="大端" if self.waveform_endian == 'big' else "小端")
        ttk.Combobox(ctrl, textvariable=self.waveform_endian_var,
                     values=["小端", "大端"], state='readonly', width=6).pack(side=tk.LEFT, padx=2)

        # 字节大小/字节序变化时回写到实例属性并持久化
        self.waveform_bytesize_var.trace_add(
            'write', lambda *_: self._sync_waveform_format())
        self.waveform_endian_var.trace_add(
            'write', lambda *_: self._sync_waveform_format())

        ttk.Button(ctrl, text="清空波形", command=self.clear_waveform).pack(
            side=tk.LEFT, padx=4)
        ttk.Button(ctrl, text="保存图片", command=self.save_waveform_image).pack(
            side=tk.LEFT, padx=4)

        # Matplotlib 图表
        self.waveform_fig = Figure(
            figsize=(8, 4), dpi=100, facecolor=get_color('background'))
        self.waveform_ax = self.waveform_fig.add_subplot(111)
        self.waveform_ax.set_facecolor(get_color('bg_input'))
        self.waveform_ax.tick_params(colors=get_color('text'))
        self.waveform_xlabel = self.waveform_settings.get('xlabel', '采样点')
        self.waveform_ylabel = self.waveform_settings.get('ylabel', '数值')
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
        axis_frame = ttk.LabelFrame(self.waveform_window, text="轴设置")
        axis_frame.pack(fill=tk.X, padx=4, pady=2)

        # X轴
        x_row = ttk.Frame(axis_frame)
        x_row.pack(fill=tk.X, padx=4, pady=2)
        ttk.Label(x_row, text="X轴标签:").pack(side=tk.LEFT)
        self.wf_xlabel_var = tk.StringVar(value=self.waveform_xlabel)
        ttk.Entry(x_row, textvariable=self.wf_xlabel_var,
                  width=12).pack(side=tk.LEFT, padx=2)
        ttk.Label(x_row, text="范围:").pack(side=tk.LEFT, padx=(8, 0))
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
        ttk.Label(y_row, text="Y轴标签:").pack(side=tk.LEFT)
        self.wf_ylabel_var = tk.StringVar(value=self.waveform_ylabel)
        ttk.Entry(y_row, textvariable=self.wf_ylabel_var,
                  width=12).pack(side=tk.LEFT, padx=2)
        ttk.Label(y_row, text="范围:").pack(side=tk.LEFT, padx=(8, 0))
        self.wf_ylim_min_var = tk.StringVar(
            value=str(ws.get('ylim', [None, None])[0]) if ws.get('ylim') else "")
        self.wf_ylim_max_var = tk.StringVar(
            value=str(ws.get('ylim', [None, None])[1]) if ws.get('ylim') else "")
        ttk.Entry(y_row, textvariable=self.wf_ylim_min_var,
                  width=8).pack(side=tk.LEFT, padx=2)
        ttk.Label(y_row, text="~").pack(side=tk.LEFT)
        ttk.Entry(y_row, textvariable=self.wf_ylim_max_var,
                  width=8).pack(side=tk.LEFT, padx=2)

        ttk.Button(y_row, text="应用", command=self._apply_waveform_axis_settings).pack(
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
        self.waveform_bytesize = 4 if self.waveform_bytesize_var.get() == "32位" else 2
        self.waveform_endian = 'big' if self.waveform_endian_var.get() == "大端" else 'little'
        self.save_settings()

    def update_waveform(self, data):
        if not self.waveform_ax:
            return

        # 波形窗口已打开时 waveform_bytesize_var / waveform_endian_var 必然存在
        bs = 2 if self.waveform_bytesize_var.get() == "16位" else 4
        endian = 'little' if self.waveform_endian_var.get() == "小端" else 'big'

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
            title="保存波形图片",
            filetypes=[("PNG图片", "*.png"), ("所有文件", "*.*")]
        )
        if path:
            try:
                self.waveform_fig.savefig(path, dpi=150, bbox_inches='tight')
                messagebox.showinfo("成功", f"波形图片已保存到: {path}")
            except Exception as e:
                messagebox.showwarning("错误", f"保存失败: {e}")

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
            self.log_writer.writerow(["时间", "类型", "数据"])
            self.log_start_time = datetime.now()
            self.log_file_size = 0
        except Exception as e:
            messagebox.showwarning("错误", f"无法开始记录: {e}")

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
            messagebox.showwarning("错误", "没有数据可导出！")
            return

        path = filedialog.asksaveasfilename(
            title="导出数据",
            filetypes=[("文本文件", "*.txt"), ("CSV文件", "*.csv"),
                       ("二进制文件", "*.bin"), ("所有文件", "*.*")]
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
                    writer.writerow(["时间", "类型", "数据"])
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

            messagebox.showinfo("成功", f"数据已导出到: {path}")
        except Exception as e:
            messagebox.showwarning("错误", f"导出失败: {e}")

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
                text=f"状态: 自动重连失败（已达最大次数 {max_times}）",
                foreground=get_color('error'))
            return

        # 状态栏提示重连进度
        self.status_label.configure(
            text=f"状态: 正在重连 {self.reconnect_count}/{max_times}...",
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
        # 统一 Treeview 外观：字体与 Text 控件一致、行高统一、去缩进
        style = ttk.Style()
        style.configure('Treeview', font=('Consolas', 10),
                        rowheight=24, indent=0)
        style.configure('Treeview.Heading',
                        font=('Microsoft YaHei', 9, 'bold'), indent=0)

        # 接收区文本
        for tw in [self.string_recv_text, self.hex_recv_text]:
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
        dialog.title("串口设置 - 更多设置")
        dialog.transient(self.root)
        dialog.grab_set()

        main = ttk.Frame(dialog, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        # 串口选择行
        row0 = ttk.Frame(main)
        row0.pack(fill=tk.X, pady=4)
        ttk.Label(row0, text="串口:", width=8).pack(side=tk.LEFT)
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

        ttk.Button(row0, text="刷新", command=refresh,
                   width=5).pack(side=tk.LEFT, padx=4)

        # 波特率
        row1 = ttk.Frame(main)
        row1.pack(fill=tk.X, pady=4)
        ttk.Label(row1, text="波特率:", width=8).pack(side=tk.LEFT)
        baud_combo = ttk.Combobox(row1, values=BAUDRATES, width=28)
        baud_combo.set(self.baudrate_var.get())
        baud_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        # 数据位
        row2 = ttk.Frame(main)
        row2.pack(fill=tk.X, pady=4)
        ttk.Label(row2, text="数据位:", width=8).pack(side=tk.LEFT)
        data_combo = ttk.Combobox(row2, values=['5', '6', '7', '8'],
                                  state='readonly', width=28)
        data_combo.set(self.databits_var.get())
        data_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        # 停止位
        row3 = ttk.Frame(main)
        row3.pack(fill=tk.X, pady=4)
        ttk.Label(row3, text="停止位:", width=8).pack(side=tk.LEFT)
        stop_combo = ttk.Combobox(row3, values=['1', '1.5', '2'],
                                  state='readonly', width=28)
        stop_combo.set(self.stopbits_var.get())
        stop_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        # 校验位
        row4 = ttk.Frame(main)
        row4.pack(fill=tk.X, pady=4)
        ttk.Label(row4, text="校验位:", width=8).pack(side=tk.LEFT)
        parity_combo = ttk.Combobox(row4, values=['None', 'Even', 'Odd', 'Mark', 'Space'],
                                    state='readonly', width=28)
        parity_combo.set(self.parity_var.get())
        parity_combo.pack(side=tk.LEFT, padx=4, fill=tk.X, expand=True)

        # 硬件流控制
        rtscts_var = tk.BooleanVar(value=self.rtscts_var.get())
        ttk.Checkbutton(main, text="启用硬件流控制 (RTS/CTS)",
                        variable=rtscts_var).pack(anchor=tk.W, pady=4)

        ttk.Separator(main, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=8)

        # 连接状态与操作
        status_frame = ttk.Frame(main)
        status_frame.pack(fill=tk.X, pady=4)
        ttk.Label(status_frame, text="连接状态:").pack(side=tk.LEFT)
        status_lbl = ttk.Label(status_frame, text="已连接" if self.is_connected else "未连接",
                               foreground=get_color('success') if self.is_connected else get_color('error'))
        status_lbl.pack(side=tk.LEFT, padx=8)

        btn_text = "断开" if self.is_connected else "连接"
        conn_btn = ttk.Button(status_frame, text=btn_text)
        conn_btn.pack(side=tk.RIGHT, padx=4)

        def on_connect():
            if self.is_connected:
                self.disconnect_serial()
                conn_btn.configure(text="连接")
                status_lbl.configure(text="未连接", foreground=get_color('error'))
                self.connect_btn.configure(text="连接")
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
                    conn_btn.configure(text="断开")
                    status_lbl.configure(
                        text="已连接", foreground=get_color('success'))
                    self.connect_btn.configure(text="断开")

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

        ttk.Button(btn_frame, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="取消",
                   command=dialog.destroy).pack(side=tk.RIGHT)

        # 自适应大小并居中
        self._center_dialog(dialog)

        self.root.wait_window(dialog)

    def _show_hex_newline_dialog(self):
        result = simpledialog.askinteger(
            "HEX换行字节数",
            "设置HEX显示每多少字节换行（0为不限制）：",
            initialvalue=self._safe_int(self.hex_newline_count_var, 0),
            minvalue=0, maxvalue=256,
            parent=self.root)
        if result is not None:
            self.hex_newline_count_var.set(result)
            self.save_settings()

    def show_reconnect_settings_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("自动重连设置")
        dialog.geometry("380x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        main = ttk.Frame(dialog, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        ar_var = tk.BooleanVar(value=self.auto_reconnect_var.get())
        ttk.Checkbutton(main, text="启用自动重连", variable=ar_var).grid(
            row=0, column=0, columnspan=2, sticky=tk.W, pady=4)

        ttk.Label(main, text="间隔 (秒):").grid(
            row=1, column=0, sticky=tk.W, pady=4)
        interval_spin = ttk.Spinbox(main, from_=1, to=30, width=10)
        interval_spin.set(self.reconnect_interval_var.get())
        interval_spin.grid(row=1, column=1, sticky=tk.W, pady=4, padx=4)

        ttk.Label(main, text="最大次数:").grid(
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
        ttk.Button(btn_frame, text="确定", command=on_ok).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_frame, text="取消",
                   command=dialog.destroy).pack(side=tk.RIGHT)

        self.root.wait_window(dialog)

    def show_record_dialog(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("数据记录")
        dialog.geometry("400x200")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        main = ttk.Frame(dialog, padding=15)
        main.pack(fill=tk.BOTH, expand=True)

        is_recording = self.log_file is not None
        btn_text = "停止记录" if is_recording else "开始记录"
        rec_btn = ttk.Button(main, text=btn_text)
        rec_btn.pack(fill=tk.X, pady=4)

        file_info = f"文件: {os.path.basename(self.log_file_path)}" if is_recording else "未记录"
        status_lbl = ttk.Label(main, text=file_info)
        status_lbl.pack(fill=tk.X, pady=4)

        def toggle():
            self.toggle_log()
            is_rec = self.log_file is not None
            rec_btn.configure(text="停止记录" if is_rec else "开始记录")
            status_lbl.configure(
                text=f"文件: {os.path.basename(self.log_file_path)}" if is_rec else "未记录")

        rec_btn.configure(command=toggle)

        ttk.Button(main, text="确定", command=dialog.destroy).pack(side=tk.RIGHT, pady=(10, 0))

        self.root.wait_window(dialog)

    def show_help(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("使用说明")
        dialog.geometry("700x500")
        dialog.transient(self.root)

        text = self._create_scrolled_text(dialog)
        text.configure(state=tk.NORMAL, wrap=tk.WORD,
                       font=('Microsoft YaHei', 10))

        help_content = """HSS串口助手 - 使用说明

1. 功能概述
  - 串口参数配置和连接管理
  - 数据发送（支持字符串和Hex模式）
  - 数据接收（支持字符串和Hex模式，带选项卡切换）
  - 多页面多命令发送
  - 自动应答
  - 实时波形显示
  - 自动重连功能
  - 数据记录和导出
  - 主题切换（ttkbootstrap 内置主题）

2. 操作步骤

  2.1 串口连接
    1. 在顶部"串口控制"栏选择串口、波特率、校验位
    2. 点击"连接"按钮；更多参数（数据位/停止位/流控）点"更多设置"
    3. 自动重连可在"设置 > 自动重连设置"中开启

  2.2 发送数据
    1. 在发送区选择"字符串"或"Hex"选项卡
    2. 输入数据
    3. 点击"发送"按钮（或按 Ctrl+Enter 发送、Enter 换行）

  2.3 多命令发送
    1. 右侧"多命令发送"面板，可新增/重命名/删除页面
    2. 点"添加命令"录入 模式/标签/内容
    3. 双击命令 = 立即发送；单击 = 填入发送框
    4. 右键命令可编辑或删除

  2.4 接收数据
    1. 数据会在接收区自动显示
    2. 可切换"字符串"或"HEX"选项卡
    3. 勾选"时间戳"/"方向"/"回显"控制显示

  2.5 波形显示
    在菜单"扩展" > "波形显示"中打开

  2.6 数据记录与导出
    1. 在菜单"数据" > "数据记录"中开始/停止记录（CSV）
    2. 在菜单"数据" > "导出数据"中导出为 txt/csv/bin

3. 快捷键
  Ctrl+Enter：发送数据
  Enter：在发送区换行
"""
        text.insert('1.0', help_content)
        text.configure(state=tk.DISABLED)

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
            'recv_timeout': self._safe_int(self.recv_timeout_var, 0),
            'frame_enable': self.frame_enable_var.get(),
            'frame_header_content': self.frame_header_content_var.get(),
            'frame_footer_content': self.frame_footer_content_var.get(),
            'frame_hex': self.frame_hex_var.get(),
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

        # 历史面板宽度
        hist_width = s.get('hist_panel_width', 220)
        if hasattr(self, 'hist_frame'):
            self.hist_frame.configure(width=hist_width)
            self.hist_panel_width = hist_width
            if hasattr(self, 'hist_width_var'):
                self.hist_width_var.set(hist_width)

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
        theme = s.get('theme', 'cosmo')
        if theme in get_themes():
            self.set_theme(theme)

    # ==================== 工具方法 ====================

    def update_counts(self):
        self.recv_count_label.configure(text=f"接收: {self.recv_bytes} 字节")
        self.send_count_label.configure(text=f"发送: {self.sent_bytes} 字节")

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
