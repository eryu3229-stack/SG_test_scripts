import pyvisa

class InstrumentManager:
    """仪器资源管理类，用于管理和连接多个仪器"""
    
    def __init__(self):
        """初始化仪器管理器"""
        self.rm = pyvisa.ResourceManager()
        self.instruments = {}
        self.connected_instruments = {}
    
    def list_instruments(self):
        """列出所有可用的仪器"""
        return self.rm.list_resources()
    
    def connect_instrument(self, resource_name, instrument_type):
        """连接指定的仪器
        
        Args:
            resource_name: 仪器的资源名称
            instrument_type: 仪器类型 (signal_generator, spectrum_analyzer, power_meter)
        """
        try:
            instrument = self.rm.open_resource(resource_name)
            instrument.timeout = 5000  # 设置超时时间为5秒
            self.connected_instruments[resource_name] = {
                'instrument': instrument,
                'type': instrument_type
            }
            print(f"成功连接到{instrument_type}: {resource_name}")
            return instrument
        except Exception as e:
            print(f"连接仪器失败: {e}")
            return None
    
    def disconnect_instrument(self, resource_name):
        """断开指定仪器的连接"""
        if resource_name in self.connected_instruments:
            try:
                self.connected_instruments[resource_name]['instrument'].close()
                del self.connected_instruments[resource_name]
                print(f"成功断开与{resource_name}的连接")
            except Exception as e:
                print(f"断开连接失败: {e}")
    
    def disconnect_all(self):
        """断开所有仪器的连接"""
        for resource_name in list(self.connected_instruments.keys()):
            self.disconnect_instrument(resource_name)
