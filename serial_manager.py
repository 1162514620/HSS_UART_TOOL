import serial
import serial.tools.list_ports
from typing import List, Tuple, Optional


class SerialManager:
    def __init__(self):
        self.serial_port: Optional[serial.Serial] = None
        self.is_connected = False
    
    def scan_ports(self) -> List[Tuple[str, str]]:
        ports = []
        for port in serial.tools.list_ports.comports():
            ports.append((port.device, port.description))
        return ports
    
    def connect(self, port: str, baudrate: int, databits: int = 8, 
                stopbits: float = 1, parity: str = 'N', rtscts: bool = False) -> Tuple[bool, str]:
        try:
            if self.is_connected:
                self.disconnect()
            
            parity_map = {
                'N': serial.PARITY_NONE,
                'E': serial.PARITY_EVEN,
                'O': serial.PARITY_ODD,
                'M': serial.PARITY_MARK,
                'S': serial.PARITY_SPACE
            }
            
            stopbits_map = {
                1: serial.STOPBITS_ONE,
                1.5: serial.STOPBITS_ONE_POINT_FIVE,
                2: serial.STOPBITS_TWO
            }
            
            self.serial_port = serial.Serial(
                port=port,
                baudrate=baudrate,
                bytesize=databits,
                stopbits=stopbits_map.get(stopbits, serial.STOPBITS_ONE),
                parity=parity_map.get(parity, serial.PARITY_NONE),
                timeout=0.5,  # 增加超时时间，提高兼容性
                write_timeout=0.5,  # 增加写入超时时间
                rtscts=rtscts,  # 启用硬件流控制
                xonxoff=False,  # 禁用软件流控制
                dsrdtr=False,  # 禁用DSR/DTR流控制
                inter_byte_timeout=None  # 禁用字节间超时
            )
            
            self.is_connected = True
            return True, "连接成功"
            
        except serial.SerialException as e:
            return False, str(e)
        except Exception as e:
            return False, f"未知错误: {str(e)}"
    
    def disconnect(self):
        if self.serial_port and self.serial_port.is_open:
            try:
                self.serial_port.close()
            except:
                pass
        self.serial_port = None
        self.is_connected = False
    
    def send(self, data: bytes, retry_count: int = 1) -> bool:
        if not self.is_connected or not self.serial_port:
            return False
        
        attempts = 0
        while attempts <= retry_count:
            try:
                # 根据数据大小采用不同的发送策略
                if len(data) <= 32:
                    # 小数据：直接发送
                    self.serial_port.write(data)
                    self.serial_port.flush()
                    import time
                    time.sleep(0.005)  # 5ms延迟
                else:
                    # 大数据：分块发送
                    chunk_size = 32  # 32字节每块
                    for i in range(0, len(data), chunk_size):
                        chunk = data[i:i+chunk_size]
                        self.serial_port.write(chunk)
                        self.serial_port.flush()
                        # 每块数据后添加适当延迟，确保设备有时间处理
                        import time
                        time.sleep(0.01)  # 10ms延迟
                return True
            except serial.SerialTimeoutException:
                # 超时异常，可能是串口繁忙，尝试重试
                attempts += 1
                if attempts <= retry_count:
                    # 给设备更多恢复时间
                    import time
                    time.sleep(0.1)  # 100ms延迟
                    continue
                else:
                    # 重试次数耗尽，返回失败但保持连接
                    return False
            except serial.SerialException as e:
                # 发生严重异常时，断开连接
                print(f"串口异常: {e}")
                self.disconnect()
                return False
            except Exception as e:
                # 捕获其他异常，避免程序崩溃
                print(f"发送数据时发生异常: {e}")
                attempts += 1
                if attempts <= retry_count:
                    import time
                    time.sleep(0.1)  # 100ms延迟
                    continue
                else:
                    return False
        return False
    
    def receive(self) -> Optional[bytes]:
        if not self.is_connected or not self.serial_port:
            return None
        
        try:
            if self.serial_port.in_waiting > 0:
                return self.serial_port.read(self.serial_port.in_waiting)
            return None
        except serial.SerialException:
            return None
    
    def get_in_waiting(self) -> int:
        if not self.is_connected or not self.serial_port:
            return 0
        return self.serial_port.in_waiting
