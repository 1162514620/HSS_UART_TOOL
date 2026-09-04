import threading
import time
from typing import Callable, Optional


class ReceiveThread(threading.Thread):
    """基于 threading.Thread 的串口数据接收线程"""

    def __init__(self, serial_manager, on_data: Callable[[bytes], None],
                 on_error: Optional[Callable[[str], None]] = None):
        super().__init__(daemon=True)
        self.serial_manager = serial_manager
        self.on_data = on_data
        self.on_error = on_error
        self.running = True
        self.recv_timeout = 0  # 接收聚合超时(ms)，0=不聚合

    def run(self):
        while self.running:
            if self.serial_manager.is_connected:
                try:
                    data = self.serial_manager.receive()
                    if data:
                        timeout = self.recv_timeout
                        if timeout > 0:
                            # 聚合模式：等待超时时间内无新数据才提交
                            buffer = data
                            deadline = time.monotonic() + timeout / 1000.0
                            while self.running:
                                remaining = deadline - time.monotonic()
                                if remaining <= 0:
                                    break
                                # 每 1ms 检查一次缓冲区
                                time.sleep(min(remaining, 0.001))
                                chunk = self.serial_manager.receive()
                                if chunk:
                                    buffer += chunk
                                    # 收到新数据，重置超时
                                    deadline = time.monotonic() + timeout / 1000.0
                            self.on_data(buffer)
                        else:
                            self.on_data(data)
                except Exception as e:
                    if self.on_error and self.running:
                        self.on_error(str(e))
            else:
                # 未连接时减少 CPU 占用
                time.sleep(0.1)

    def stop(self):
        self.running = False
