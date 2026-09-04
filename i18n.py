"""轻量国际化模块：以中文原文为 key，英文查表翻译，未命中时原样返回"""

_current_language = 'zh'

# 英文翻译表（key 为中文原文；含 {xx} 占位符的条目由调用方 .format 填充）
_EN = {
    # ── 菜单栏 ──
    '数据': 'Data',
    '导出数据': 'Export Data',
    '数据记录': 'Data Logging',
    '主题': 'Theme',
    '── 深色主题 ──': '── Dark Themes ──',
    '── 浅色主题 ──': '── Light Themes ──',
    '编码': 'Encoding',
    '接收编码': 'Receive Encoding',
    '发送编码': 'Send Encoding',
    '设置': 'Settings',
    '自动重连设置': 'Auto Reconnect',
    '地址偏移': 'Address Offset',
    'HEX换行字节数...': 'HEX Line Break...',
    '扩展': 'Tools',
    '波形显示': 'Waveform',
    '语言': 'Language',

    # ── 串口控制栏 ──
    '串口控制': 'Serial Control',
    '串口:': 'Port:',
    '刷新': 'Refresh',
    '波特率:': 'Baud:',
    '校验:': 'Parity:',
    '连接': 'Connect',
    '断开': 'Disconnect',
    '更多设置': 'More Settings',

    # ── 接收区 ──
    '接收区': 'Receive',
    '字符串': 'Text',
    '对照': 'Compare',
    '清空接收区': 'Clear',
    '暂停显示': 'Pause',
    '继续显示': 'Resume',
    '时间戳': 'Timestamp',
    '方向': 'Direction',
    '回显': 'Echo',
    '超时:': 'Timeout:',
    'ms(0=自动)': 'ms (0=auto)',

    # ── 发送区 ──
    '发送区': 'Send',
    ' 发送 ': ' Send ',
    '自动转义': 'Auto Escape',
    '回车换行': 'CRLF',
    '循环发送': 'Loop Send',
    '间隔:': 'Interval:',
    '次数:': 'Count:',
    '(0=无限)': '(0 = inf)',
    '校验': 'Checksum',
    '第': 'From',
    '字节到第': 'to',
    '字节': '',
    '末尾': 'End',
    '添加帧头帧尾': 'Add Frame Header/Footer',
    '帧头:': 'Header:',
    '帧尾:': 'Footer:',

    # ── 多命令发送面板 ──
    '功能面板': 'Function Panel',
    '多命令发送': 'Multi-Command',
    '新增页面': 'New Page',
    '删除页面': 'Delete Page',
    '页面:': 'Page:',
    '重命名': 'Rename',
    '添加命令': 'Add Command',
    '清空当前': 'Clear Page',
    '宽度:': 'Width:',
    '应用': 'Apply',

    # ── 自动应答 ──
    '自动应答': 'Auto Reply',
    '开启自动应答': 'Enable Auto Reply',
    '关闭自动应答': 'Disable Auto Reply',
    '状态': 'Status',
    '模式': 'Mode',
    '触发': 'Trigger',
    '响应': 'Response',
    '添加规则': 'Add Rule',
    '删除规则': 'Delete Rule',
    '编辑规则': 'Edit Rule',
    '匹配模式:': 'Match Mode:',
    '匹配内容:': 'Match Content:',
    '使用正则表达式': 'Use Regex',
    '应答模式:': 'Reply Mode:',
    '应答内容:': 'Reply Content:',
    '延时(ms):': 'Delay (ms):',
    '启用此规则': 'Enable Rule',
    '匹配内容和应答内容不能为空': 'Match content and reply content cannot be empty',

    # ── 页面/命令对话框 ──
    '重命名页面': 'Rename Page',
    '请输入新的页面名称：': 'Enter new page name:',
    '页面名称已存在或无效': 'Page name already exists or invalid',
    '请输入页面名称：': 'Enter page name:',
    '页面名称已存在': 'Page name already exists',
    '至少需要保留一个页面': 'At least one page is required',
    '确定删除页面「{page_name}」及其所有命令？': 'Delete page "{page_name}" and all its commands?',
    '编辑命令': 'Edit Command',
    '删除命令': 'Delete Command',
    '模式:': 'Mode:',
    '标签:': 'Label:',
    '内容:': 'Content:',
    '非法字符: {chars}': 'Invalid characters: {chars}',
    'Hex 长度必须为偶数': 'Hex length must be even',
    '内容不能为空': 'Content cannot be empty',
    'Hex 格式错误': 'Invalid hex format',
    'Hex数据长度必须为偶数': 'Hex data length must be even',

    # ── 状态栏 / 消息 ──
    '状态: 未连接': 'Status: Disconnected',
    '状态: 已连接 {port}': 'Status: Connected {port}',
    '接收: {n} 字节': 'Received: {n} bytes',
    '发送: {n} 字节': 'Sent: {n} bytes',
    '状态: 自动重连失败（已达最大次数 {n}）': 'Status: Auto reconnect failed (max {n} attempts)',
    '状态: 正在重连 {cur}/{max}...': 'Status: Reconnecting {cur}/{max}...',
    '提示': 'Notice',
    '确认': 'Confirm',
    '错误': 'Error',
    '成功': 'Success',
    '确定': 'OK',
    '取消': 'Cancel',
    '串口已断开！': 'Serial port disconnected!',
    '请选择串口！': 'Please select a port!',
    '波特率必须是数字！': 'Baud rate must be a number!',
    '连接失败': 'Connection Failed',
    '无法连接串口: {msg}': 'Cannot connect: {msg}',
    '无效的Hex数据格式！': 'Invalid hex data format!',
    '未连接串口，数据仅作为回显显示！': 'Not connected; data shown as echo only!',
    '发送失败': 'Send Failed',
    '串口连接已断开！': 'Serial connection lost!',
    '请先连接串口！': 'Please connect first!',
    '编码错误': 'Encoding Error',
    '无法用{encoding}编码: {e}': 'Cannot encode with {encoding}: {e}',
    '[错误] {msg}\n': '[Error] {msg}\n',

    # ── 波形显示 ──
    'matplotlib 未安装，波形显示功能不可用。\n请运行: pip install matplotlib':
        'matplotlib is not installed; waveform is unavailable.\nRun: pip install matplotlib',
    '字节大小:': 'Byte Size:',
    '32位': '32-bit',
    '16位': '16-bit',
    '字节序:': 'Byte Order:',
    '大端': 'Big Endian',
    '小端': 'Little Endian',
    '清空波形': 'Clear',
    '保存图片': 'Save Image',
    '采样点': 'Sample',
    '数值': 'Value',
    '轴设置': 'Axis Settings',
    'X轴标签:': 'X Label:',
    'Y轴标签:': 'Y Label:',
    '范围:': 'Range:',
    '保存波形图片': 'Save Waveform Image',
    'PNG图片': 'PNG Image',
    '所有文件': 'All Files',
    '波形图片已保存到: {path}': 'Waveform saved to: {path}',
    '保存失败: {e}': 'Save failed: {e}',

    # ── 记录 / 导出 ──
    '时间': 'Time',
    '类型': 'Type',
    '无法开始记录: {e}': 'Cannot start logging: {e}',
    '没有数据可导出！': 'No data to export!',
    '文本文件': 'Text File',
    'CSV文件': 'CSV File',
    '二进制文件': 'Binary File',
    '数据已导出到: {path}': 'Data exported to: {path}',
    '导出失败: {e}': 'Export failed: {e}',
    '停止记录': 'Stop',
    '开始记录': 'Start',
    '文件: {name}': 'File: {name}',
    '未记录': 'Not logging',

    # ── 设置对话框 ──
    '串口设置 - 更多设置': 'Serial Settings',
    '数据位:': 'Data Bits:',
    '停止位:': 'Stop Bits:',
    '校验位:': 'Parity:',
    '启用硬件流控制 (RTS/CTS)': 'Hardware Flow Control (RTS/CTS)',
    '连接状态:': 'Status:',
    '已连接': 'Connected',
    '未连接': 'Disconnected',
    'HEX换行字节数': 'HEX Line Break',
    '设置HEX显示每多少字节换行（0为不限制）：': 'Bytes per line in HEX view (0 = unlimited):',
    '启用自动重连': 'Enable Auto Reconnect',
    '间隔 (秒):': 'Interval (s):',
    '最大次数:': 'Max Attempts:',

    # ── 主题名 ──
    '经典（浅）': 'Classic (Light)',
    '经典（深）': 'Classic (Dark)',
    '数据（浅）': 'PyData (Light)',
    '数据（深）': 'PyData (Dark)',
    '极地（浅）': 'Nord (Light)',
    '极地（深）': 'Nord (Dark)',
    '日光（浅）': 'Solarized (Light)',
    '日光（深）': 'Solarized (Dark)',
    '奶茶（浅）': 'Catppuccin (Light)',
    '奶茶（深）': 'Catppuccin (Dark)',
    '复古（浅）': 'Gruvbox (Light)',
    '复古（深）': 'Gruvbox (Dark)',
    '德古拉（浅）': 'Dracula (Light)',
    '德古拉（深）': 'Dracula (Dark)',
    '东京夜（浅）': 'Tokyo Night (Light)',
    '东京夜（深）': 'Tokyo Night (Dark)',
    '极简（浅）': 'One (Light)',
    '极简（深）': 'One (Dark)',
    '常青（浅）': 'Everforest (Light)',
    '常青（深）': 'Everforest (Dark)',
    '蒸汽波（浅）': 'Vapor (Light)',
    '蒸汽波（深）': 'Vapor (Dark)',
    '薄荷（浅）': 'Minty (Light)',
    '薄荷（深）': 'Minty (Dark)',
    '脉冲（浅）': 'Pulse (Light)',
    '脉冲（深）': 'Pulse (Dark)',
    '联合（浅）': 'United (Light)',
    '联合（深）': 'United (Dark)',
    '砂岩（浅）': 'Sandstone (Light)',
    '砂岩（深）': 'Sandstone (Dark)',
}


def get_language():
    """获取当前语言（'zh' / 'en'）"""
    return _current_language


def set_language(lang):
    """设置当前语言（'zh' / 'en'）"""
    global _current_language
    if lang in ('zh', 'en'):
        _current_language = lang


def t(text):
    """翻译：英文模式查表，中文模式原样返回，未命中原样返回"""
    if _current_language == 'en':
        return _EN.get(text, text)
    return text
