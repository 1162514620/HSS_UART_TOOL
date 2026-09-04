"""从 SSCOM 配置文件导入 AT 指令到 history.json 的移远模组AT指令页面"""
import json
import re
from datetime import datetime

ini_path = r'd:\work\Workspace\python\HSS串口助手\sscom51.ini'
history_path = r'd:\work\Workspace\python\HSS串口助手\history.json'

lines = open(ini_path, encoding='utf-8').readlines()

meta = {}       # idx -> (mode_int, label)
contents = {}   # idx -> (type_char, content)

for line in lines:
    line = line.strip()
    if not line or line.startswith(';'):
        continue
    m = re.match(r'^N(\d+)=(.*)', line)
    if not m:
        continue
    num = int(m.group(1))
    val = m.group(2).strip()
    if 101 <= num <= 199:
        parts = val.split(',', 2)
        mode_int = int(parts[0]) if parts[0] else 0
        label = parts[1] if len(parts) > 1 else ''
        meta[num - 100] = (mode_int, label)
    elif 1 <= num <= 99:
        parts = val.split(',', 1)
        type_char = parts[0] if parts else ''
        content = parts[1] if len(parts) > 1 else ''
        contents[num] = (type_char, content)

ts = datetime.now().strftime('%Y-%m-%dT%H:%M:%S.%f')
commands = []

for idx in sorted(contents.keys()):
    if idx not in meta:
        continue
    mode_int, label = meta[idx]
    type_char, content = contents[idx]
    if not content.strip():
        continue
    mode = 'hex' if type_char.upper() == 'H' else 'string'
    commands.append({
        'timestamp': ts,
        'mode': mode,
        'content': content,
        'label': label,
    })

print(f'解析到 {len(commands)} 条指令')
for c in commands:
    print(f"  [{c['mode']}] {c['label']}: {c['content'][:60]}")

with open(history_path, 'r', encoding='utf-8') as f:
    data = json.load(f)

data['pages']['移远模组AT指令'] = commands

with open(history_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f'\n已写入 history.json -> 移远模组AT指令页面 ({len(commands)} 条)')
