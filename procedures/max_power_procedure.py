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
        stop_power = test_config.get('stop_power', test_config.get('max_set_power', start_power))
        power_step = test_config['power_step']
        max_set_power = test_config['max_set_power']
        max_measured_power = test_config['max_measured_power']

        # stop_power 是扫描终点，max_set_power 是硬安全限制
        if stop_power > max_set_power:
            print(f"警告: stop_power ({stop_power} dBm) > max_set_power ({max_set_power} dBm)，"
                  f"将 stop_power 限制为 {max_set_power} dBm")
            stop_power = max_set_power
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
        print(f"起始功率: {start_power} dBm, 终止功率: {stop_power} dBm, 步进: {power_step} dB")
        print(f"信号源硬限制: {max_set_power} dBm")
        print(f"功率计最大读数限制: {max_measured_power} dBm")
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
        
        # 3. 外接衰减器：由人告知的物理事实，**从不下发到仪器**，
        #    唯一用途是把功率计读数折算回 DUT 端（见 actual_power = measured_power + ext_att_db）
        ext_att_db = attenuator_value if use_attenuator else 0.0

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
        max_set_power_at_peak = None  # 取到最大实际功率时的信号源设定功率
        prev_measured_power = None  # 上一步原始测量值（用于测量失败回退）
        prev_actual_power = None    # 上一步补偿后的实际功率（用于饱和/过载检测）
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
                self.add_power_sweep_point(
                    frequency, current_power, None, None, step_count,
                    'MEAS_FAIL', ext_att_db=ext_att_db,
                )
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
            
            # 条件1: 达到扫描终止功率（正常扫描终点）
            if current_power >= stop_power:
                stop_reason = f"达到扫描终止功率 ({stop_power} dBm)"
                print(f"停止条件: {stop_reason}")
                stop_scan = True
            
            # 条件2: 达到信号源硬限制（安全冗余）
            if current_power >= max_set_power:
                stop_reason = f"达到信号源硬限制 ({max_set_power} dBm)"
                print(f"停止条件: {stop_reason}")
                stop_scan = True
            
            # 条件3: 功率计原始读值超过最大输入（保护探头；比较对象是功率计读值，不是补偿值）
            if measured_power >= max_measured_power:
                stop_reason = f"达到功率计最大读数 ({max_measured_power} dBm)"
                print(f"停止条件: {stop_reason}")
                stop_scan = True
            
            # 条件4: 饱和检测（补偿后的实际输出功率增加小于容差）
            if prev_actual_power is not None:
                power_increase = actual_power - prev_actual_power
                if power_increase < power_tolerance:
                    saturation_detected = True
                    stop_reason = f"检测到饱和 (实际功率增加仅{power_increase:.2f} dB < 容差 {power_tolerance} dB)"
                    print(f"停止条件: {stop_reason}")
                    stop_scan = True
            
            # 条件5: 过载检测（补偿后的实际输出功率下降）
            if prev_actual_power is not None:
                power_drop = prev_actual_power - actual_power
                if power_drop > max_power_drop:
                    overload_detected = True
                    stop_reason = f"检测到过载 (实际功率下降 {power_drop:.2f} dB > 最大允许 {max_power_drop} dB)"
                    print(f"停止条件: {stop_reason}")
                    stop_scan = True
            
            # 记录数据点
            status = 'OK'
            if saturation_detected:
                status = 'SATURATED'
            elif overload_detected:
                status = 'OVERLOAD'
            elif stop_scan:
                status = 'LIMIT'

            self.add_power_sweep_point(
                frequency, current_power, measured_power, actual_power,
                step_count, status, ext_att_db=ext_att_db,
            )

            # 更新最大功率记录
            if max_achieved_power is None or actual_power > max_achieved_power:
                max_achieved_power = actual_power
                max_achieved_measured = measured_power
                max_set_power_at_peak = current_power
            
            # 准备下一次迭代
            prev_measured_power = measured_power
            prev_actual_power = actual_power
            
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
            set_power_at_max=max_set_power_at_peak,
            max_measured_power=max_achieved_measured,
            max_actual_power=max_achieved_power,
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