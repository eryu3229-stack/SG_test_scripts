import time
import csv
import openpyxl
from openpyxl.styles import Font, Alignment
from datetime import datetime


class TestProcedure:
    """测试流程类"""

    def __init__(self, instrument_manager):
        """初始化测试流程

        Args:
            instrument_manager: 仪器管理器对象
        """
        self.instrument_manager = instrument_manager
        self.test_results = []
        self.test_prepared = False  # 标记是否已完成测试准备

    def add_test_result(self, frequency, set_power, measured_power, attenuator_value=0):
        """添加测试结果

        Args:
            frequency: 测量频率
            set_power: 设定功率
            measured_power: 实际测量功率（平均值）
            attenuator_value: 衰减器衰减值（dB）
        """
        # 如果启用了衰减器，对测量功率进行补偿
        compensated_power = measured_power + attenuator_value if attenuator_value > 0 else measured_power

        self.test_results.append({
            'frequency': frequency,
            'set_power': set_power,
            'measured_power': measured_power,
            'compensated_power': compensated_power,
            'attenuator_value': attenuator_value,
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        })

    def prepare_test(self, signal_generator, power_meter):
        """测试前准备步骤

        Args:
            signal_generator: 信号源对象
            power_meter: 功率计对象
        """
        print("等待功率计归零稳定...")
        time.sleep(2.0)  # 等待2秒确保归零完全稳定

        print("开启测试准备...")
        # 确保信号源初始状态为关闭
        signal_generator.enable_output(False)
        time.sleep(0.5)  # 等待信号源状态稳定

        self.test_prepared = True
        print("测试准备完成")

    def run_test(self, signal_generator, power_meter, test_config, keep_output=False):
        """运行测试

        Args:
            signal_generator: 信号源对象
            power_meter: 功率计对象
            test_config: 测试配置
            keep_output: 是否保持输出开启
        """
        print(f"开始测试: {test_config['test_name']}")

        # 设置信号源
        signal_generator.set_frequency(test_config['frequency'])
        signal_generator.set_power(test_config['power'])
        signal_generator.enable_output(True)

        # 等待信号稳定（信号源建立稳定输出所需时间）
        settling_time = test_config.get('settling_time', 1.5)
        time.sleep(settling_time)

        # 切换功率计的测量频率
        power_meter.set_frequency(test_config['frequency'])
        
        # 功率计频率切换稳定时间
        pm_settling_time = test_config.get('pm_settling_time', 0.5)
        time.sleep(pm_settling_time)

        # 测量实际功率
        measurement_times = test_config.get('measurement_times', 5)
        measured_power = power_meter.measure_power(times=measurement_times)

        # 获取衰减器值
        attenuator_value = 0
        if test_config.get('attenuator_enabled', False):
            attenuator_value = test_config.get('attenuator_value', 0)

        # 添加测试结果
        self.add_test_result(
            test_config['frequency'],
            test_config['power'],
            measured_power,
            attenuator_value
        )

        # 禁用信号源输出（如果不需要保持输出）
        if not keep_output:
            signal_generator.enable_output(False)
            # 信号源关闭后等待时间
            post_close_wait = test_config.get('post_close_wait', 0.1)
            time.sleep(post_close_wait)

        print(f"测试完成: {test_config['test_name']}")

    def save_results(self, filename, test_configs=None):
        """保存测试结果

        Args:
            filename: 保存结果的文件名
            test_configs: 测试配置列表，用于保存配置信息
        """
        if not self.test_results:
            print("没有测试结果可保存")
            return

        try:
            # 确保使用Excel格式
            if not filename.endswith('.xlsx'):
                filename = filename.rsplit('.', 1)[0] + '.xlsx'
                print(f"自动转换为Excel格式: {filename}")
            
            # 保存为Excel格式
            wb = openpyxl.Workbook()
            
            # 第一个sheet：总结和配置
            summary_ws = wb.active
            summary_ws.title = "测试总结"
            
            # 写入总结信息
            summary_ws.cell(row=1, column=1).value = "测试总结"
            summary_ws.cell(row=1, column=1).font = Font(bold=True, size=14)
            
            summary_ws.cell(row=3, column=1).value = "测试项目"
            summary_ws.cell(row=3, column=2).value = "功率扫描测试"
            summary_ws.cell(row=4, column=1).value = "测试时间"
            summary_ws.cell(row=4, column=2).value = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            summary_ws.cell(row=5, column=1).value = "测试点数"
            summary_ws.cell(row=5, column=2).value = len(self.test_results)
            
            # 写入配置信息
            summary_ws.cell(row=7, column=1).value = "测试配置"
            summary_ws.cell(row=7, column=1).font = Font(bold=True)
            
            if test_configs and len(test_configs) > 0:
                config = test_configs[0]
                row = 8
                summary_ws.cell(row, column=1).value = "信号源稳定时间"
                summary_ws.cell(row, column=2).value = config.get('settling_time', 1.5)
                summary_ws.cell(row, column=3).value = "秒"
                row += 1
                
                summary_ws.cell(row, column=1).value = "功率计频率切换稳定时间"
                summary_ws.cell(row, column=2).value = config.get('pm_settling_time', 0.5)
                summary_ws.cell(row, column=3).value = "秒"
                row += 1
                
                summary_ws.cell(row, column=1).value = "信号源关闭后等待时间"
                summary_ws.cell(row, column=2).value = config.get('post_close_wait', 0.1)
                summary_ws.cell(row, column=3).value = "秒"
                row += 1
                
                summary_ws.cell(row, column=1).value = "功率计测量次数"
                summary_ws.cell(row, column=2).value = config.get('measurement_times', 5)
                row += 1
                
                summary_ws.cell(row, column=1).value = "衰减器启用"
                summary_ws.cell(row, column=2).value = "是" if config.get('attenuator_enabled', False) else "否"
                row += 1
                
                if config.get('attenuator_enabled', False):
                    summary_ws.cell(row, column=1).value = "衰减器类型"
                    if config.get('attenuator_freq_dependent', False):
                        summary_ws.cell(row, column=2).value = "频率相关"
                    else:
                        summary_ws.cell(row, column=2).value = "固定值"
                        row += 1
                        summary_ws.cell(row, column=1).value = "衰减值"
                        summary_ws.cell(row, column=2).value = config.get('attenuator_value', 0)
                        summary_ws.cell(row, column=3).value = "dB"
            
            # 调整列宽
            summary_ws.column_dimensions['A'].width = 25
            summary_ws.column_dimensions['B'].width = 15
            summary_ws.column_dimensions['C'].width = 10
            
            # 第二个sheet：测试数据
            data_ws = wb.create_sheet(title="测试数据")
            
            # 写入表头
            headers = ['测量频率', '设定功率', '实际功率', '补偿功率', '衰减器值', '时间戳']
            for col, header in enumerate(headers, 1):
                cell = data_ws.cell(row=1, column=col)
                cell.value = header
                cell.font = Font(bold=True)
                cell.alignment = Alignment(horizontal='center')
            
            # 写入数据
            for row, result in enumerate(self.test_results, 2):
                data_ws.cell(row=row, column=1).value = result['frequency']
                data_ws.cell(row=row, column=2).value = result['set_power']
                data_ws.cell(row=row, column=3).value = result['measured_power']
                data_ws.cell(row=row, column=4).value = result['compensated_power']
                data_ws.cell(row=row, column=5).value = result['attenuator_value']
                data_ws.cell(row=row, column=6).value = result['timestamp']
            
            # 调整列宽
            for col in range(1, len(headers) + 1):
                data_ws.column_dimensions[openpyxl.utils.get_column_letter(col)].width = 18
            
            wb.save(filename)
            print(f"测试结果已保存到: {filename}")
        except Exception as e:
            print(f"保存测试结果失败: {e}")