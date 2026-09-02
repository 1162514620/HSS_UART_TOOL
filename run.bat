@echo off

REM 检查虚拟环境是否存在
if not exist venv\Scripts\activate.bat (
    echo 虚拟环境不存在，正在创建...
    python -m venv venv
    
    echo 激活虚拟环境...
    call venv\Scripts\activate.bat
    
    echo 安装依赖项...
    pip install -r requirements.txt
) else (
    echo 激活虚拟环境...
    call venv\Scripts\activate.bat
)

REM 运行主程序
echo 运行主程序...
python main.py

REM 保持窗口打开，以便查看错误信息
pause
