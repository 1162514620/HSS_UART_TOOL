# 多功能串口助手 (MultiSerial Tool)

一款跨平台（Windows/Mac/Linux）、功能强大、体验优秀的串口调试助手，满足嵌入式开发的所有核心需求。

## 功能特性

### 核心功能
- **串口管理**：自动扫描串口，显示设备描述，支持热插拔检测
- **数据接收**：异步接收，支持Hex/字符串模式，时间戳显示，颜色区分
- **数据发送**：Hex/字符串双模式，手动发送，循环发送，发送历史记录

### 进阶功能
- **波形显示**：基于matplotlib的波形窗口，支持16/32位整数解析，大端/小端字节序，波形缩放平移，PNG保存
- **数据记录与导出**：实时日志记录，自动文件分割，支持TXT/CSV/Bin导出
- **自动重连**：串口断开后自动尝试重连，可设置间隔和最大次数

### 体验优化
- **主题切换**：支持18种ttkbootstrap主题（深色/浅色），实时切换，自动保存设置
- **配置保存**：使用JSON保存所有配置，下次启动自动恢复
- **帮助文档**：内置"快速入门"帮助文档

## 技术栈

- **编程语言**：Python 3.7+
- **UI框架**：ttkbootstrap（基于tkinter的现代化主题库）
- **串口通信**：pyserial
- **波形显示**：matplotlib（可选）
- **其他**：numpy, chardet

## 可用主题

### 深色主题
- darkly, superhero, solar, cyborg, vapor

### 浅色主题
- cosmo, flatly, litera, minty, lumen, sandstone, yeti, pulse, united, morph, journal, simplex, cerculean

## 安装步骤

### 1. 安装Python

确保安装了Python 3.7或更高版本：

```bash
python --version
```

### 2. 克隆项目

```bash
git clone <repository_url>
cd HSS
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 运行程序

```bash
python main.py
```

或使用批处理脚本：

```bash
run.bat
```

## 使用说明

### 基本操作

1. **串口连接**：
   - 在菜单栏点击"串口设置"
   - 选择串口，设置波特率、数据位、停止位、校验位
   - 点击"连接"按钮

2. **发送数据**：
   - 在发送区输入数据
   - 选择"字符串"或"Hex"模式
   - 点击"发送"按钮或按Enter键

3. **接收数据**：
   - 数据会在接收区显示
   - 支持实时波形显示（菜单"系统" > "波形显示"）

### 高级功能

1. **自动重连**：
   - 菜单"系统" > "自动重连设置"
   - 设置重连间隔和最大次数
   - 串口断开后会自动尝试重连

2. **数据记录**：
   - 菜单"系统" > "数据记录"
   - 数据会自动保存到logs目录
   - 文件超过10MB时自动分割

3. **数据导出**：
   - 菜单"文件" > "导出数据"
   - 选择导出格式（TXT/CSV/Bin）
   - 选择保存路径

4. **主题切换**：
   - 菜单"系统" > "主题"
   - 支持18种ttkbootstrap主题
   - 深色主题和浅色主题分类显示

### 快捷键

- **Enter**：发送数据
- **Ctrl+Enter**：在发送区换行

## 项目结构

```
HSS/
├── main.py              # 程序入口
├── main_window.py       # 主窗口UI
├── serial_manager.py    # 串口管理
├── receive_thread.py    # 接收线程
├── command_manager.py   # 命令管理
├── styles.py            # 样式和主题
├── requirements.txt     # 依赖列表
├── setup.py             # 安装配置
├── run.bat              # 启动脚本
└── README.md            # 说明文档
```

## 注意事项

1. **长时间运行**：建议定期清空接收区，避免内存占用过大
2. **高频数据**：高频数据传输时，建议使用Hex模式
3. **日志文件**：日志文件会自动分割，避免过大
4. **异常处理**：所有串口操作都有异常处理，确保程序稳定运行

## 许可证

MIT License
