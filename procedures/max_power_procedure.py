import time
from datetime import datetime
from base_test_procedure import format_frequency
from power_sweep_base import PowerSweepBaseProcedure


class MaxPowerProcedure(PowerSweepBaseProcedure):
    """最大功率测试流程类"""

    def __init__(self, instrument_manager):
        super().__init__(instrument_manager)

    def run_test(self, signal_generator, power_meter, test_config, keep_output=False):
        """运行最大功率测试

        Args:
            signal_generator: 信号源对象
            power_meter: 功率计对象
            test_config: 测试配置
            keep_output: 是否保持输出状态（不关闭），默认为False
        """
        frequency = test_config['frequency']
        start_power = test_config['start_power']
        power_step = test_config['power_step']
        max_set_power = test_config['max_set_power']
        max_measured_power = test_config['max_measured_power']
        power_tolerance = test_config['power_tolerance']
        max_power_drop = test_config['max_power_drop']
        attenuator_value = test_config['attenuator_value']
        use_attenuator = test_config['use_attenuator']
        settling_time = test_config['settling_time']
        pm_settling_time = test_config['pm_settling_time']
        measurement_times = test_config['measurement_times']

        print(f"\n{'=' * 60}")
        print(f"开始最大功率测试: {test_config['test_name']}")
        print(f"频率: {format_frequency(frequency)}")
        print(f"起始功率: {start_power} dBm, 步进: {power_step} dB")
        print(f"最大设定功率限制: {max_set_power} dBm")
        print(f"最大测量功率限制: {max_measured_power} dBm")
        if use_attenuator:
            print(f"衰减器值: {attenuator_value} dB")
        print(f"{'=' * 60}")

        # 1. 设置信号源频率
        signal_generator.set_frequency(frequency)
        
        # 2. 设置功率计频率
        power_meter.set_frequency(frequency)
        
        # 等待功率计频率切换稳定
        print(f"等待功率计稳定 {pm_settling_time}秒...")
        time.sleep(pm_settling_time)
        
        # 3. 配置衰减器（如果使用）
        if use_attenuator and hasattr(power_meter, 'set_input_attenuation'):
            power_meter.set_input_attenuation(attenuator_value)
            print(f"设置功率计输入衰减: {attenuator_value} dB")
        
        # 4. 启用信号源输出（从起始功率开始）
        current_power = start_power
        signal_generator.set_power(current_power)
        signal_generator.enable_output(True)
        print(f"启用信号源输出，起始功率: {current_power} dBm")
        
        # 等待初始稳定
        print(f"等待信号源稳定 {settling_time}秒...")
        time.sleep(settling_time)
        
        # 5. 功率扫描变量初始化
        max_achieved_power = None  # 最大实际功率（考虑衰减）
        max_achieved_measured = None  # 最大测量功率
        prev_measured_power = None
        saturation_detected = False
        overload_detected = False
        limit_reached = False
        step_count = 0
        stop_reason = "正常完成"
        
        # 6. 功率扫描循环
        while True:
            step_count += 1
            print(f"\n--- 功率步进 {step_count}: 设定功率 = {current_power:.1f} dBm ---")
            
            # 设置信号源功率
            signal_generator.set_power(current_power)
            
            # 等待稳定
            time.sleep(settling_time)
            
            # 测量功率
            measured_power = power_meter.measure_power(times=measurement_times)
            
            # 检查功率计错误队列
            power_meter.check_errors()
            
            if measured_power is None:
                print("警告: 功率计测量失败，跳过此点")
                self.add_power_sweep_point(frequency, current_power, None, None, step_count, '测量失败')
                # 尝试继续，但可能意味着有问题
                measured_power = prev_measured_power if prev_measured_power is not None else -float('inf')
            
            # 计算实际功率（考虑衰减器补偿）
            if use_attenuator:
                actual_power = measured_power + attenuator_value
            else:
                actual_power = measured_power
            
            print(f"测量功率: {measured_power:.2f} dBm, 实际功率: {actual_power:.2f} dBm")
            
            # 检查停止条件
            stop_scan = False
            
            # 条件1: 设定功率超过最大限制
            if current_power >= max_set_power:
                stop_reason = f"达到设定功率限制 ({max_set_power} dBm)"
                print(f"停止条件: {stop_reason}")
                stop_scan = True
            
            # 条件2: 测量功率超过功率计最大输入
            if measured_power >= max_measured_power:
                stop_reason = f"达到测量功率限制 ({max_measured_power} dBm)"
                print(f"停止条件: {stop_reason}")
                stop_scan = True
            
            # 条件3: 饱和检测（功率增加小于容差）
            if prev_measured_power is not None:
                power_increase = measured_power - prev_measured_power
                expected_increase = power_step  # 理想情况下，测量功率应增加 power_step dB
                
                if power_increase < power_tolerance:
                    saturation_detected = True
                    stop_reason = f"检测到饱和 (功率增加仅{power_increase:.2f} dB < 容差 {power_tolerance} dB)"
                    print(f"停止条件: {stop_reason}")
                    stop_scan = True
            
            # 条件4: 过载检测（功率下降）
            if prev_measured_power is not None:
                power_drop = prev_measured_power - measured_power
                if power_drop > max_power_drop:
                    overload_detected = True
                    stop_reason = f"检测到过载 (功率下降 {power_drop:.2f} dB > 最大允许 {max_power_drop} dB)"
                    print(f"停止条件: {stop_reason}")
                    stop_scan = True
            
            # 记录数据点
            status = '正常'
            if saturation_detected:
                status = '饱和'
            elif overload_detected:
                status = '过载'
            elif stop_scan:
                status = '超限'
            
            self.add_power_sweep_point(frequency, current_power, measured_power, actual_power, step_count, status)
            
            # 更新最大功率记录
            if max_achieved_power is None or actual_power > max_achieved_power:
                max_achieved_power = actual_power
                max_achieved_measured = measured_power
            
            # 准备下一次迭代
            prev_measured_power = measured_power
            
            # 检查是否停止扫描
            if stop_scan:
                break
            
            # 增加功率
            current_power += power_step
        
        # 7. 测试完成，整理结果
        notes = stop_reason
        if saturation_detected:
            notes += " (饱和点)"
        if overload_detected:
            notes += " (过载点)"
        
        # 添加测试结果
        self.add_test_result(
            frequency=frequency,
            max_power=max_achieved_power,
            max_measured_power=max_achieved_measured,
            attenuation=attenuator_value if use_attenuator else 0.0,
            saturation_point=saturation_detected,
            steps=step_count,
            notes=notes
        )
        
        print(f"\n{'=' * 60}")
        print(f"测试完成: {test_config['test_name']}")
        print(f"最大实际功率: {max_achieved_power:.2f} dBm")
        print(f"最大测量功率: {max_achieved_measured:.2f} dBm")
        print(f"功率步进数: {step_count}")
        print(f"停止原因: {stop_reason}")
        print(f"{'=' * 60}")
        
        # 8. 根据参数决定是否禁用信号源输出
        if not keep_output:
            signal_generator.enable_output(False)
            print("信号源输出已禁用")
            # 短暂等待，确保信号源完全关闭
            time.sleep(test_config['post_close_wait'])
        else:
            print("保持信号源输出状态")