#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SG Test Scripts 集成测试 GUI（独立程序）"""

import os
import queue
import sys
import threading
from datetime import datetime
import tkinter as tk
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
for path in (parent_dir,
             os.path.join(parent_dir, 'instruments'),
             os.path.join(parent_dir, 'procedures'),
             os.path.join(parent_dir, 'configs'),
             os.path.join(parent_dir, 'utils')):
    if path not in sys.path:
        sys.path.append(path)

from harmonic_test_config import (
    PROJECT_NAME as HARMONIC_NAME,
    FREQUENCY_SWEEP_CONFIG as HARMONIC_FREQ_CONFIG,
    SPECTRUM_ANALYZER_CONFIG as HARMONIC_SA_CONFIG,
    HARMONIC_MEASUREMENT_CONFIG,
)
from low_freq_max_power_config import (
    project_name as LF_PROJECT_NAME,
    settling_time as LF_SETTLING_TIME,
    sa_settling_time as LF_SA_SETTLING_TIME,
    post_close_wait as LF_POST_CLOSE_WAIT,
    measurement_times as LF_MEASUREMENT_TIMES,
    start_power as LF_START_POWER,
    power_step as LF_POWER_STEP,
    max_set_power as LF_MAX_SET_POWER,
    max_measured_power as LF_MAX_MEASURED_POWER,
    power_tolerance as LF_POWER_TOLERANCE,
    max_power_drop as LF_MAX_POWER_DROP,
    attenuator_value as LF_ATTENUATOR_VALUE,
    use_attenuator as LF_USE_ATTENUATOR,
    frequency_ranges as LF_FREQUENCY_RANGES,
    spectrum_analyzer_config as LF_SA_CONFIG,
)
from max_power_config import (
    project_name as MP_PROJECT_NAME,
    settling_time as MP_SETTLING_TIME,
    pm_settling_time as MP_PM_SETTLING_TIME,
    post_close_wait as MP_POST_CLOSE_WAIT,
    measurement_times as MP_MEASUREMENT_TIMES,
    start_power as MP_START_POWER,
    power_step as MP_POWER_STEP,
    max_set_power as MP_MAX_SET_POWER,
    max_measured_power as MP_MAX_MEASURED_POWER,
    power_tolerance as MP_POWER_TOLERANCE,
    max_power_drop as MP_MAX_POWER_DROP,
    attenuator_value as MP_ATTENUATOR_VALUE,
    use_attenuator as MP_USE_ATTENUATOR,
    frequency_ranges as MP_FREQUENCY_RANGES,
)
from power_sweep_config import (
    project_name as PS_PROJECT_NAME,
    start_freq as PS_START_FREQ,
    end_freq as PS_END_FREQ,
    step_freq as PS_STEP_FREQ,
    power_settings as PS_POWER_SETTINGS,
    settling_time as PS_SETTLING_TIME,
    pm_settling_time as PS_PM_SETTLING_TIME,
    post_close_wait as PS_POST_CLOSE_WAIT,
    measurement_times as PS_MEASUREMENT_TIMES,
    attenuator_enabled as PS_ATTENUATOR_ENABLED,
    attenuator_value as PS_ATTENUATOR_VALUE,
)
from single_frequency_power_sweep_config import (
    project_name as SF_PROJECT_NAME,
    test_config as SF_DEFAULT_CONFIG,
)
from subharmonic_test_config import (
    PROJECT_NAME as SUBHARMONIC_NAME,
    FREQUENCY_SWEEP_CONFIG as SUBHARMONIC_FREQ_CONFIG,
    SPECTRUM_ANALYZER_CONFIG as SUBHARMONIC_SA_CONFIG,
    SUBHARMONIC_MEASUREMENT_CONFIG,
)
from utils.parameter_parsing import (
    parse_float,
    parse_frequency,
    parse_power,
    parse_time,
)
from utils.gui_fonts import apply_gui_font, enable_dpi_awareness


def parse_int(value, label):
    """解析整数，失败时抛出带名称的错误。"""
    try:
        return int(str(value).strip())
    except ValueError:
        raise ValueError(f"{label}格式错误: {value}")


def parse_csv_floats(value, label):
    """解析逗号分隔的浮点数列表。"""
    text = str(value).replace("，", ",").strip()
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        raise ValueError(f"{label}不能为空。")
    return [parse_power(part, label) for part in parts]


def parse_csv_ints(value, label):
    """解析逗号分隔的整数列表。"""
    text = str(value).replace("，", ",").strip()
    parts = [part.strip() for part in text.split(",") if part.strip()]
    if not parts:
        raise ValueError(f"{label}不能为空。")
    try:
        return [int(part) for part in parts]
    except ValueError:
        raise ValueError(f"{label}格式错误: {value}")


class QueueWriter:
    """把 worker 线程的 print 输出转发到 GUI 消息队列。"""

    def __init__(self, msg_queue):
        self.msg_queue = msg_queue

    def write(self, text):
        if text:
            self.msg_queue.put(("log", text))

    def flush(self):
        pass


class IntegratedTestApp:
    """集成测试 GUI 主程序。"""

    def __init__(self, root):
        self.root = root
        self.manager = None
        self.signal_gen = None
        self.spectrum_analyzer = None
        self.power_meter = None
        self.connected = {}
        self.active_tab = None

        self.sg_var = tk.StringVar()
        self.sa_var = tk.StringVar()
        self.pm_var = tk.StringVar()

        self._build_ui()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill=tk.X)
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="信号源:").grid(row=0, column=0, sticky="w", pady=2)
        self.sg_combo = ttk.Combobox(top, textvariable=self.sg_var, width=34)
        self.sg_combo.grid(row=0, column=1, sticky="ew", pady=2, padx=(4, 8))

        ttk.Label(top, text="频谱仪:").grid(row=1, column=0, sticky="w", pady=2)
        self.sa_combo = ttk.Combobox(top, textvariable=self.sa_var, width=34)
        self.sa_combo.grid(row=1, column=1, sticky="ew", pady=2, padx=(4, 8))

        ttk.Label(top, text="功率计:").grid(row=2, column=0, sticky="w", pady=2)
        self.pm_combo = ttk.Combobox(top, textvariable=self.pm_var, width=34)
        self.pm_combo.grid(row=2, column=1, sticky="ew", pady=2, padx=(4, 8))

        self.refresh_btn = ttk.Button(
            top, text="扫描可用仪器", command=self._refresh_resources
        )
        self.refresh_btn.grid(row=0, column=2, rowspan=3, sticky="ns", padx=(4, 0))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))

        self.tabs = [
            SingleFrequencyTab(self.notebook, self),
            PowerSweepTab(self.notebook, self),
            MaxPowerTab(self.notebook, self),
            LowFreqMaxPowerTab(self.notebook, self),
            HarmonicTab(self.notebook, self),
            SubharmonicTab(self.notebook, self),
        ]
        for tab in self.tabs:
            self.notebook.add(tab, text=tab.title)

    def _refresh_resources(self):
        """扫描 VISA 资源并填充三个下拉框。"""
        try:
            from instrument_manager import InstrumentManager

            if self.manager is None:
                self.manager = InstrumentManager()
            resources = self.manager.list_instruments()
            self.sg_combo["values"] = resources
            self.sa_combo["values"] = resources
            self.pm_combo["values"] = resources
            if not resources:
                messagebox.showinfo("提示", "未发现 VISA 资源。")
        except Exception as e:
            messagebox.showerror("错误", f"扫描仪器失败:\n{e}")

    def begin_test(self, tab):
        """全局只允许一个测试同时运行。"""
        if self.active_tab is not None and self.active_tab is not tab:
            return False
        self.active_tab = tab
        return True

    def end_test(self, tab):
        if self.active_tab is tab:
            self.active_tab = None

    def ensure_instruments(self, resources):
        """按资源名称连接需要的仪器，返回仪器对象字典。"""
        from instrument_manager import InstrumentManager
        from power_meter import PowerMeter
        from signal_generator import SignalGenerator
        from spectrum_analyzer import SpectrumAnalyzer

        if self.manager is None:
            self.manager = InstrumentManager()

        definitions = [
            ("signal_generator", "signal_gen", SignalGenerator),
            ("spectrum_analyzer", "spectrum_analyzer", SpectrumAnalyzer),
            ("power_meter", "power_meter", PowerMeter),
        ]
        result = {}
        for kind, attr, wrapper in definitions:
            resource = resources.get(kind)
            if not resource:
                continue
            if self.connected.get(kind) != resource:
                if self.connected.get(kind):
                    self.manager.disconnect_instrument(self.connected[kind])
                instrument = self.manager.connect_instrument(resource, kind)
                if instrument is None:
                    raise RuntimeError(f"{kind}连接失败: {resource}")
                setattr(self, attr, wrapper(instrument))
                self.connected[kind] = resource
            result[kind] = getattr(self, attr)
        return result

    def _on_close(self):
        if self.active_tab is not None:
            self.active_tab.stop_requested = True
        self.root.destroy()


class TestTabBase(ttk.Frame):
    """测试页签基类，提供统一的布局、日志、结果表和后台执行框架。"""

    title = ""
    needs_zero = False
    required_instruments = ()

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.running = False
        self.stop_requested = False
        self.worker = None
        self.queue = queue.Queue()
        self.pending_params = None
        self.pending_resources = None
        self.result_columns = []
        self._build_ui()
        self.after(100, self._poll_queue)

    def _build_ui(self):
        main = ttk.Frame(self, padding=6)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, minsize=440)
        main.columnconfigure(1, weight=1)
        main.rowconfigure(0, weight=1)

        left = ttk.Frame(main)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        self.param_frame = ttk.LabelFrame(left, text="测试参数", padding=8)
        self.param_frame.pack(fill=tk.BOTH, expand=True)
        self.param_frame.columnconfigure(1, weight=1)
        self._build_params(self.param_frame)

        btn_frame = ttk.Frame(left)
        btn_frame.pack(fill=tk.X, pady=(8, 0))
        self.start_btn = ttk.Button(
            btn_frame, text="开始测试", command=self._start_test
        )
        self.start_btn.pack(side=tk.LEFT, expand=True, fill=tk.X, padx=(0, 4))
        self.stop_btn = ttk.Button(
            btn_frame, text="停止测试", command=self._stop_test, state=tk.DISABLED
        )
        self.stop_btn.pack(side=tk.LEFT, expand=True, fill=tk.X)

        right = ttk.Frame(main)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(0, weight=1)
        right.rowconfigure(1, weight=2)
        right.columnconfigure(0, weight=1)

        log_frame = ttk.LabelFrame(right, text="运行日志", padding=6)
        log_frame.grid(row=0, column=0, sticky="nsew", pady=(0, 6))
        self.log_text = ScrolledText(
            log_frame, height=12, state="disabled", wrap="word"
        )
        self.log_text.pack(fill=tk.BOTH, expand=True)

        result_frame = ttk.LabelFrame(right, text="测量结果", padding=6)
        result_frame.grid(row=1, column=0, sticky="nsew")
        result_frame.columnconfigure(0, weight=1)
        result_frame.rowconfigure(0, weight=1)

        self.result_tree = ttk.Treeview(
            result_frame, columns=(), show="headings", height=10
        )
        vsb = ttk.Scrollbar(
            result_frame, orient=tk.VERTICAL, command=self.result_tree.yview
        )
        self.result_tree.configure(yscrollcommand=vsb.set)
        self.result_tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        self._build_result_columns(result_frame)

    def _add_param(self, row, label, var):
        ttk.Label(self.param_frame, text=label).grid(
            row=row, column=0, sticky="w", pady=2
        )
        ttk.Entry(self.param_frame, textvariable=var, width=24).grid(
            row=row, column=1, sticky="ew", pady=2
        )

    def _build_range_editor(self, frame, default_ranges, start_row=0):
        """构建可动态增删的频率范围输入区。"""
        self.range_rows = []
        ttk.Label(frame, text="频率范围").grid(
            row=start_row, column=0, sticky="nw", pady=2
        )
        self.range_container = ttk.Frame(frame)
        self.range_container.grid(
            row=start_row, column=1, sticky="ew", pady=2
        )
        for col in (1, 2, 3):
            self.range_container.columnconfigure(col, weight=1)
        for item in default_ranges:
            self.range_rows.append([
                tk.StringVar(value=str(item["start"])),
                tk.StringVar(value=str(item["end"])),
                tk.StringVar(value=str(item["step"])),
            ])
        self._rebuild_range_rows()

    def _add_range_row(self):
        self.range_rows.append([tk.StringVar(), tk.StringVar(), tk.StringVar()])
        self._rebuild_range_rows()

    def _remove_range_row(self, index):
        if len(self.range_rows) <= 1:
            messagebox.showwarning("提示", "至少保留一个频率范围。")
            return
        del self.range_rows[index]
        self._rebuild_range_rows()

    def _rebuild_range_rows(self):
        for child in self.range_container.winfo_children():
            child.destroy()

        headers = ["#", "起始", "结束", "步进", ""]
        for col, text in enumerate(headers):
            ttk.Label(self.range_container, text=text).grid(
                row=0, column=col, sticky="w", padx=2
            )

        for index, row_vars in enumerate(self.range_rows, 1):
            ttk.Label(self.range_container, text=str(index)).grid(
                row=index, column=0, sticky="w", padx=2
            )
            ttk.Entry(
                self.range_container, textvariable=row_vars[0], width=18
            ).grid(row=index, column=1, sticky="ew", padx=2)
            ttk.Entry(
                self.range_container, textvariable=row_vars[1], width=18
            ).grid(row=index, column=2, sticky="ew", padx=2)
            ttk.Entry(
                self.range_container, textvariable=row_vars[2], width=18
            ).grid(row=index, column=3, sticky="ew", padx=2)
            ttk.Button(
                self.range_container,
                text="删除",
                command=lambda i=index - 1: self._remove_range_row(i),
            ).grid(row=index, column=4, sticky="e", padx=2)

        ttk.Button(
            self.range_container, text="添加范围", command=self._add_range_row
        ).grid(
            row=len(self.range_rows) + 1, column=0, columnspan=5,
            sticky="ew", pady=(4, 0),
        )

    def _read_range_editor(self):
        """读取频率范围输入区并解析为列表。"""
        ranges = []
        for row_vars in self.range_rows:
            start = parse_frequency(row_vars[0].get(), "起始频率")
            end = parse_frequency(row_vars[1].get(), "结束频率")
            step = parse_frequency(row_vars[2].get(), "频率步进")
            if start <= 0 or end < start or step <= 0:
                raise ValueError(f"频率范围无效: {start} ~ {end}, 步进 {step}")
            ranges.append({"start": start, "end": end, "step": step})
        if not ranges:
            raise ValueError("请至少添加一个频率范围。")
        return ranges

    def _setup_tree(self, columns, specs):
        self.result_columns = list(columns)
        self.result_tree.configure(columns=self.result_columns, show="headings")
        for col, title, width in specs:
            self.result_tree.heading(col, text=title)
            self.result_tree.column(col, width=width, anchor="center")

    def _append_log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message)
        if not message.endswith("\n"):
            self.log_text.insert(tk.END, "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def _read_resources(self):
        resources = {
            "signal_generator": self.app.sg_var.get().strip(),
            "spectrum_analyzer": self.app.sa_var.get().strip(),
            "power_meter": self.app.pm_var.get().strip(),
        }
        for kind in self.required_instruments:
            if not resources.get(kind):
                raise ValueError(f"请填写{kind}的 VISA 资源名称。")
        return resources

    def _start_test(self):
        if self.running:
            return
        if not self.app.begin_test(self):
            messagebox.showwarning("提示", "已有测试正在运行，请等待当前测试结束。")
            return

        try:
            params = self._read_params()
            resources = self._read_resources()
        except ValueError as e:
            self.app.end_test(self)
            messagebox.showerror("参数错误", str(e))
            return

        self.running = True
        self.stop_requested = False
        self.pending_params = params
        self.pending_resources = resources
        self._set_running_ui(True)
        self._clear_results()
        self._configure_result_columns(params)

        self._append_log("=" * 60)
        self._append_log(f"开始测试: {self.title}")
        self._append_log("=" * 60)

        if self.needs_zero:
            confirm = messagebox.askyesno(
                "功率计归零",
                "请断开功率计输入信号，确认处于开路状态。\n\n"
                "已断开请点击“是”，否则请点击“否”。",
            )
            if not confirm:
                self._finish("已取消测试：未确认功率计开路。")
                return
            self.worker = threading.Thread(target=self._zero_worker, daemon=True)
        else:
            self.worker = threading.Thread(target=self._test_worker, daemon=True)
        self.worker.start()

    def _zero_worker(self):
        old_stdout = sys.stdout
        sys.stdout = QueueWriter(self.queue)
        try:
            instruments = self.app.ensure_instruments(self.pending_resources)
            self.queue.put(("log", "正在执行功率计归零，请保持输入断开..."))
            instruments["power_meter"].zero()
            self.queue.put(("zero_done", None))
        except Exception as e:
            self.queue.put(("error", str(e)))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout

    def _test_worker(self):
        old_stdout = sys.stdout
        sys.stdout = QueueWriter(self.queue)
        try:
            instruments = self.app.ensure_instruments(self.pending_resources)
            self.queue.put(("log", "开始执行测试..."))
            self._run_impl(instruments)
            self.queue.put(("done", None))
        except Exception as e:
            self.queue.put(("error", str(e)))
        finally:
            sys.stdout.flush()
            sys.stdout = old_stdout

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "log":
                    self._append_log(payload)
                elif kind == "point":
                    self._add_result_row(payload)
                elif kind == "zero_done":
                    self._on_zero_done()
                elif kind == "error":
                    self._on_error(payload)
                elif kind == "done":
                    self._append_log("测试完成。")
                    self._finish()
        except queue.Empty:
            pass
        self.after(100, self._poll_queue)

    def _on_zero_done(self):
        self._append_log("功率计归零完成。")
        if self.stop_requested:
            self._finish("已停止测试。")
            return
        confirm = messagebox.askyesno(
            "归零完成",
            "请重新连接功率计输入信号。\n\n"
            "连接完成后点击“是”开始测试，点击“否”取消。",
        )
        if not confirm:
            self._finish("已取消测试。")
            return
        self.worker = threading.Thread(target=self._test_worker, daemon=True)
        self.worker.start()

    def _on_error(self, message):
        self._append_log(f"错误: {message}")
        messagebox.showerror("错误", message)
        self._finish()

    def _stop_test(self):
        if not self.running:
            return
        self.stop_requested = True
        self._append_log("正在停止测试，等待当前测量点完成...")
        self.stop_btn.config(state=tk.DISABLED)

    def _add_result_row(self, data):
        values = []
        for key in self.result_columns:
            value = data.get(key, "")
            if value is None:
                value = ""
            values.append(value)
        self.result_tree.insert("", tk.END, values=values)

    def _clear_results(self):
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)

    def _set_running_ui(self, running):
        self.start_btn.config(state=tk.DISABLED if running else tk.NORMAL)
        self.stop_btn.config(state=tk.NORMAL if running else tk.DISABLED)

    def _finish(self, message=None):
        if message:
            self._append_log(message)
        self.running = False
        self.app.end_test(self)
        self._set_running_ui(False)

    def _save_results(self, procedure, prefix):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join(parent_dir, "output")
        os.makedirs(output_dir, exist_ok=True)
        filepath = os.path.join(output_dir, f"{prefix}_{timestamp}.xlsx")
        procedure.save_results(filepath)
        self.queue.put(("log", f"测试结果已保存: {filepath}"))

    def _configure_result_columns(self, params):
        pass

    def _build_params(self, frame):
        raise NotImplementedError

    def _read_params(self):
        raise NotImplementedError

    def _run_impl(self, instruments):
        raise NotImplementedError


class SingleFrequencyTab(TestTabBase):
    title = "单频点功率扫描"
    needs_zero = True
    required_instruments = ("signal_generator", "power_meter")

    def __init__(self, parent, app):
        self.frequency_var = tk.StringVar(value=str(int(SF_DEFAULT_CONFIG['frequency'])))
        self.start_power_var = tk.StringVar(value=str(SF_DEFAULT_CONFIG['start_power']))
        self.end_power_var = tk.StringVar(value=str(SF_DEFAULT_CONFIG['end_power']))
        self.power_step_var = tk.StringVar(value=str(SF_DEFAULT_CONFIG['power_step']))
        self.settling_time_var = tk.StringVar(value=str(SF_DEFAULT_CONFIG['settling_time']))
        self.pm_settling_time_var = tk.StringVar(
            value=str(SF_DEFAULT_CONFIG['pm_settling_time'])
        )
        self.post_close_wait_var = tk.StringVar(
            value=str(SF_DEFAULT_CONFIG['post_close_wait'])
        )
        self.measurement_times_var = tk.StringVar(
            value=str(SF_DEFAULT_CONFIG['measurement_times'])
        )
        self.max_set_power_var = tk.StringVar(
            value=str(SF_DEFAULT_CONFIG['max_set_power'])
        )
        self.max_measured_power_var = tk.StringVar(
            value=str(SF_DEFAULT_CONFIG['max_measured_power'])
        )
        self.attenuator_var = tk.BooleanVar(
            value=SF_DEFAULT_CONFIG['attenuator_enabled']
        )
        self.attenuator_value_var = tk.StringVar(
            value=str(SF_DEFAULT_CONFIG['attenuator_value'])
        )
        super().__init__(parent, app)

    def _build_params(self, frame):
        params = [
            ("频率", self.frequency_var),
            ("起始功率 (dBm)", self.start_power_var),
            ("结束功率 (dBm)", self.end_power_var),
            ("功率步进 (dB)", self.power_step_var),
            ("信号源稳定时间 (s)", self.settling_time_var),
            ("功率计稳定时间 (s)", self.pm_settling_time_var),
            ("关断后等待 (s)", self.post_close_wait_var),
            ("测量次数", self.measurement_times_var),
            ("信号源功率上限 (dBm)", self.max_set_power_var),
            ("功率计输入保护 (dBm)", self.max_measured_power_var),
        ]
        for row, (label, var) in enumerate(params):
            self._add_param(row, label, var)
        ttk.Checkbutton(
            frame, text="启用衰减器补偿", variable=self.attenuator_var
        ).grid(row=len(params), column=0, sticky="w", pady=(6, 2))
        ttk.Entry(
            frame, textvariable=self.attenuator_value_var, width=24
        ).grid(row=len(params), column=1, sticky="ew", pady=(6, 2))

    def _read_params(self):
        frequency = parse_frequency(self.frequency_var.get(), "频率")
        start_power = parse_power(self.start_power_var.get(), "起始功率")
        end_power = parse_power(self.end_power_var.get(), "结束功率")
        power_step = parse_power(self.power_step_var.get(), "功率步进")
        settling_time = parse_time(self.settling_time_var.get(), "信号源稳定时间")
        pm_settling_time = parse_time(self.pm_settling_time_var.get(), "功率计稳定时间")
        post_close_wait = parse_time(self.post_close_wait_var.get(), "关断后等待")
        measurement_times = parse_int(self.measurement_times_var.get(), "测量次数")
        max_set_power = parse_power(self.max_set_power_var.get(), "信号源功率上限")
        max_measured_power = parse_power(
            self.max_measured_power_var.get(), "功率计输入保护"
        )
        attenuator_enabled = bool(self.attenuator_var.get())
        attenuator_value = parse_float(
            self.attenuator_value_var.get(), "衰减器补偿值"
        )

        if frequency <= 0:
            raise ValueError("频率必须大于 0。")
        if power_step <= 0:
            raise ValueError("功率步进必须大于 0。")
        if end_power < start_power:
            raise ValueError("结束功率不能小于起始功率。")
        if measurement_times <= 0:
            raise ValueError("测量次数必须大于 0。")
        if attenuator_enabled and attenuator_value < 0:
            raise ValueError("衰减器补偿值不能为负。")

        power_points = []
        current_power = start_power
        while current_power <= end_power + 1e-9:
            power_points.append(round(current_power, 6))
            current_power += power_step
        if not power_points:
            raise ValueError("无法生成功率扫描点，请检查起始/结束/步进。")

        return {
            "frequency": frequency,
            "power_points": power_points,
            "settling_time": settling_time,
            "pm_settling_time": pm_settling_time,
            "post_close_wait": post_close_wait,
            "measurement_times": measurement_times,
            "max_set_power": max_set_power,
            "max_measured_power": max_measured_power,
            "attenuator_enabled": attenuator_enabled,
            "attenuator_value": attenuator_value,
        }

    def _build_result_columns(self, frame):
        self._setup_tree(
            ["frequency", "set_power", "measured_power", "compensated_power",
             "status", "timestamp"],
            [
                ("frequency", "频率 (Hz)", 110),
                ("set_power", "设定功率 (dBm)", 110),
                ("measured_power", "测量功率 (dBm)", 110),
                ("compensated_power", "补偿功率 (dBm)", 110),
                ("status", "状态", 80),
                ("timestamp", "时间戳", 150),
            ],
        )

    def _run_impl(self, instruments):
        from single_frequency_power_sweep_procedure import (
            SingleFrequencyPowerSweepProcedure,
        )

        procedure = SingleFrequencyPowerSweepProcedure(self.app.manager)
        procedure.run_test(
            instruments["signal_generator"],
            instruments["power_meter"],
            self.pending_params,
            on_point=lambda point: self.queue.put(("point", point)),
            should_stop=lambda: self.stop_requested,
        )
        if procedure.test_results:
            self._save_results(procedure, SF_PROJECT_NAME)


class PowerSweepTab(TestTabBase):
    title = "功率扫描测试"
    needs_zero = True
    required_instruments = ("signal_generator", "power_meter")

    def __init__(self, parent, app):
        self.start_freq_var = tk.StringVar(value=str(int(PS_START_FREQ)))
        self.end_freq_var = tk.StringVar(value=str(int(PS_END_FREQ)))
        self.step_freq_var = tk.StringVar(value=str(int(PS_STEP_FREQ)))
        self.power_settings_var = tk.StringVar(
            value=", ".join(str(value) for value in PS_POWER_SETTINGS)
        )
        self.settling_time_var = tk.StringVar(value=str(PS_SETTLING_TIME))
        self.pm_settling_time_var = tk.StringVar(value=str(PS_PM_SETTLING_TIME))
        self.post_close_wait_var = tk.StringVar(value=str(PS_POST_CLOSE_WAIT))
        self.measurement_times_var = tk.StringVar(value=str(PS_MEASUREMENT_TIMES))
        self.attenuator_var = tk.BooleanVar(value=PS_ATTENUATOR_ENABLED)
        self.attenuator_value_var = tk.StringVar(value=str(PS_ATTENUATOR_VALUE))
        super().__init__(parent, app)

    def _build_params(self, frame):
        params = [
            ("起始频率", self.start_freq_var),
            ("结束频率", self.end_freq_var),
            ("频率步进", self.step_freq_var),
            ("功率设置 (dBm, 逗号分隔)", self.power_settings_var),
            ("信号源稳定时间 (s)", self.settling_time_var),
            ("功率计稳定时间 (s)", self.pm_settling_time_var),
            ("关断后等待 (s)", self.post_close_wait_var),
            ("测量次数", self.measurement_times_var),
        ]
        for row, (label, var) in enumerate(params):
            self._add_param(row, label, var)
        ttk.Checkbutton(
            frame, text="启用衰减器补偿", variable=self.attenuator_var
        ).grid(row=len(params), column=0, sticky="w", pady=(6, 2))
        ttk.Entry(
            frame, textvariable=self.attenuator_value_var, width=24
        ).grid(row=len(params), column=1, sticky="ew", pady=(6, 2))

    def _read_params(self):
        start_freq = parse_frequency(self.start_freq_var.get(), "起始频率")
        end_freq = parse_frequency(self.end_freq_var.get(), "结束频率")
        step_freq = parse_frequency(self.step_freq_var.get(), "频率步进")
        power_settings = parse_csv_floats(
            self.power_settings_var.get(), "功率设置"
        )
        settling_time = parse_time(self.settling_time_var.get(), "信号源稳定时间")
        pm_settling_time = parse_time(self.pm_settling_time_var.get(), "功率计稳定时间")
        post_close_wait = parse_time(self.post_close_wait_var.get(), "关断后等待")
        measurement_times = parse_int(self.measurement_times_var.get(), "测量次数")
        attenuator_enabled = bool(self.attenuator_var.get())
        attenuator_value = parse_float(
            self.attenuator_value_var.get(), "衰减器补偿值"
        )

        if start_freq <= 0 or end_freq < start_freq or step_freq <= 0:
            raise ValueError("频率范围参数无效。")
        if measurement_times <= 0:
            raise ValueError("测量次数必须大于 0。")

        test_points = []
        for power in power_settings:
            current_freq = start_freq
            while current_freq <= end_freq + 1e-9:
                test_points.append({
                    "test_name": f"{current_freq / 1e6:.0f}MHz_{power}dBm测试",
                    "frequency": current_freq,
                    "power": power,
                    "settling_time": settling_time,
                    "pm_settling_time": pm_settling_time,
                    "post_close_wait": post_close_wait,
                    "measurement_times": measurement_times,
                    "attenuator_enabled": attenuator_enabled,
                    "attenuator_value": attenuator_value,
                })
                current_freq += step_freq
            if test_points and test_points[-1]["frequency"] != end_freq:
                test_points.append({
                    "test_name": f"{end_freq / 1e6:.0f}MHz_{power}dBm测试",
                    "frequency": end_freq,
                    "power": power,
                    "settling_time": settling_time,
                    "pm_settling_time": pm_settling_time,
                    "post_close_wait": post_close_wait,
                    "measurement_times": measurement_times,
                    "attenuator_enabled": attenuator_enabled,
                    "attenuator_value": attenuator_value,
                })

        if not test_points:
            raise ValueError("无法生成测试点。")
        return {"test_points": test_points}

    def _build_result_columns(self, frame):
        self._setup_tree(
            ["frequency", "set_power", "measured_power", "compensated_power",
             "timestamp"],
            [
                ("frequency", "频率 (Hz)", 110),
                ("set_power", "设定功率 (dBm)", 110),
                ("measured_power", "测量功率 (dBm)", 110),
                ("compensated_power", "补偿功率 (dBm)", 110),
                ("timestamp", "时间戳", 150),
            ],
        )

    def _run_impl(self, instruments):
        from power_sweep_procedure import TestProcedure

        procedure = TestProcedure(self.app.manager)
        procedure.prepare_test(
            instruments["signal_generator"], instruments["power_meter"]
        )
        points = self.pending_params["test_points"]
        for index, point in enumerate(points):
            if self.stop_requested:
                break
            keep_output = index < len(points) - 1
            procedure.run_test(
                instruments["signal_generator"],
                instruments["power_meter"],
                point,
                keep_output=keep_output,
            )
            if procedure.test_results:
                self.queue.put(("point", dict(procedure.test_results[-1])))
        instruments["signal_generator"].enable_output(False)
        if procedure.test_results:
            self._save_results(procedure, PS_PROJECT_NAME)


class MaxPowerTab(TestTabBase):
    title = "最大功率测试"
    needs_zero = True
    required_instruments = ("signal_generator", "power_meter")

    def __init__(self, parent, app):
        self.start_power_var = tk.StringVar(value=str(MP_START_POWER))
        self.power_step_var = tk.StringVar(value=str(MP_POWER_STEP))
        self.max_set_power_var = tk.StringVar(value=str(MP_MAX_SET_POWER))
        self.max_measured_power_var = tk.StringVar(value=str(MP_MAX_MEASURED_POWER))
        self.power_tolerance_var = tk.StringVar(value=str(MP_POWER_TOLERANCE))
        self.max_power_drop_var = tk.StringVar(value=str(MP_MAX_POWER_DROP))
        self.settling_time_var = tk.StringVar(value=str(MP_SETTLING_TIME))
        self.pm_settling_time_var = tk.StringVar(value=str(MP_PM_SETTLING_TIME))
        self.post_close_wait_var = tk.StringVar(value=str(MP_POST_CLOSE_WAIT))
        self.measurement_times_var = tk.StringVar(value=str(MP_MEASUREMENT_TIMES))
        self.attenuator_var = tk.BooleanVar(value=MP_USE_ATTENUATOR)
        self.attenuator_value_var = tk.StringVar(value=str(MP_ATTENUATOR_VALUE))
        super().__init__(parent, app)

    def _build_params(self, frame):
        self._build_range_editor(frame, MP_FREQUENCY_RANGES)
        params = [
            ("起始功率 (dBm)", self.start_power_var),
            ("功率步进 (dB)", self.power_step_var),
            ("信号源功率上限 (dBm)", self.max_set_power_var),
            ("功率计输入保护 (dBm)", self.max_measured_power_var),
            ("功率容差 (dB)", self.power_tolerance_var),
            ("最大功率下降 (dB)", self.max_power_drop_var),
            ("信号源稳定时间 (s)", self.settling_time_var),
            ("功率计稳定时间 (s)", self.pm_settling_time_var),
            ("关断后等待 (s)", self.post_close_wait_var),
            ("测量次数", self.measurement_times_var),
        ]
        for row, (label, var) in enumerate(params, 1):
            self._add_param(row, label, var)
        ttk.Checkbutton(
            frame, text="启用衰减器补偿", variable=self.attenuator_var
        ).grid(row=len(params) + 1, column=0, sticky="w", pady=(6, 2))
        ttk.Entry(
            frame, textvariable=self.attenuator_value_var, width=24
        ).grid(row=len(params) + 1, column=1, sticky="ew", pady=(6, 2))

    def _read_params(self):
        ranges = self._read_range_editor()
        start_power = parse_power(self.start_power_var.get(), "起始功率")
        power_step = parse_power(self.power_step_var.get(), "功率步进")
        max_set_power = parse_power(self.max_set_power_var.get(), "信号源功率上限")
        max_measured_power = parse_power(
            self.max_measured_power_var.get(), "功率计输入保护"
        )
        power_tolerance = parse_float(self.power_tolerance_var.get(), "功率容差")
        max_power_drop = parse_float(self.max_power_drop_var.get(), "最大功率下降")
        settling_time = parse_time(self.settling_time_var.get(), "信号源稳定时间")
        pm_settling_time = parse_time(self.pm_settling_time_var.get(), "功率计稳定时间")
        post_close_wait = parse_time(self.post_close_wait_var.get(), "关断后等待")
        measurement_times = parse_int(self.measurement_times_var.get(), "测量次数")
        use_attenuator = bool(self.attenuator_var.get())
        attenuator_value = parse_float(
            self.attenuator_value_var.get(), "衰减器补偿值"
        )

        if power_step <= 0 or measurement_times <= 0:
            raise ValueError("功率步进和测量次数必须大于 0。")

        test_configs = []
        for freq_range in ranges:
            current_freq = freq_range["start"]
            while current_freq <= freq_range["end"]:
                test_configs.append({
                    "test_name": f"{current_freq / 1e6:.0f}MHz最大功率测试",
                    "frequency": current_freq,
                    "start_power": start_power,
                    "power_step": power_step,
                    "max_set_power": max_set_power,
                    "max_measured_power": max_measured_power,
                    "power_tolerance": power_tolerance,
                    "max_power_drop": max_power_drop,
                    "attenuator_value": attenuator_value,
                    "use_attenuator": use_attenuator,
                    "settling_time": settling_time,
                    "pm_settling_time": pm_settling_time,
                    "post_close_wait": post_close_wait,
                    "measurement_times": measurement_times,
                })
                current_freq += freq_range["step"]
        if not test_configs:
            raise ValueError("无法生成测试点。")
        return {"test_configs": test_configs}

    def _build_result_columns(self, frame):
        self._setup_tree(
            ["frequency", "max_power", "max_measured_power",
             "saturation_point", "steps", "notes", "timestamp"],
            [
                ("frequency", "频率 (Hz)", 110),
                ("max_power", "最大实际功率 (dBm)", 120),
                ("max_measured_power", "最大测量功率 (dBm)", 120),
                ("saturation_point", "是否饱和", 80),
                ("steps", "步进数", 70),
                ("notes", "备注", 160),
                ("timestamp", "时间戳", 150),
            ],
        )

    def _run_impl(self, instruments):
        from max_power_procedure import MaxPowerProcedure

        procedure = MaxPowerProcedure(self.app.manager)
        configs = self.pending_params["test_configs"]
        for index, config in enumerate(configs):
            if self.stop_requested:
                break
            keep_output = index < len(configs) - 1
            procedure.run_test(
                instruments["signal_generator"],
                instruments["power_meter"],
                config,
                keep_output=keep_output,
                should_stop=lambda: self.stop_requested,
            )
            if procedure.test_results:
                self.queue.put(("point", dict(procedure.test_results[-1])))
        if self.stop_requested:
            instruments["signal_generator"].enable_output(False)
        if procedure.test_results:
            self._save_results(procedure, MP_PROJECT_NAME)


class LowFreqMaxPowerTab(TestTabBase):
    title = "低频段最大功率测试"
    required_instruments = ("signal_generator", "spectrum_analyzer")

    def __init__(self, parent, app):
        self.start_power_var = tk.StringVar(value=str(LF_START_POWER))
        self.power_step_var = tk.StringVar(value=str(LF_POWER_STEP))
        self.max_set_power_var = tk.StringVar(value=str(LF_MAX_SET_POWER))
        self.max_measured_power_var = tk.StringVar(value=str(LF_MAX_MEASURED_POWER))
        self.power_tolerance_var = tk.StringVar(value=str(LF_POWER_TOLERANCE))
        self.max_power_drop_var = tk.StringVar(value=str(LF_MAX_POWER_DROP))
        self.settling_time_var = tk.StringVar(value=str(LF_SETTLING_TIME))
        self.sa_settling_time_var = tk.StringVar(value=str(LF_SA_SETTLING_TIME))
        self.post_close_wait_var = tk.StringVar(value=str(LF_POST_CLOSE_WAIT))
        self.measurement_times_var = tk.StringVar(value=str(LF_MEASUREMENT_TIMES))
        self.attenuator_var = tk.BooleanVar(value=LF_USE_ATTENUATOR)
        self.attenuator_value_var = tk.StringVar(value=str(LF_ATTENUATOR_VALUE))
        self.span_var = tk.StringVar(value=str(LF_SA_CONFIG["span"]))
        self.rbw_var = tk.StringVar(value=str(LF_SA_CONFIG["rbw"]))
        self.vbw_var = tk.StringVar(value=str(LF_SA_CONFIG["vbw"]))
        self.reference_level_var = tk.StringVar(value=str(LF_SA_CONFIG["reference_level"]))
        self.attenuation_var = tk.StringVar(value=str(LF_SA_CONFIG["attenuation"]))
        super().__init__(parent, app)

    def _build_params(self, frame):
        self._build_range_editor(frame, LF_FREQUENCY_RANGES)
        params = [
            ("起始功率 (dBm)", self.start_power_var),
            ("功率步进 (dB)", self.power_step_var),
            ("信号源功率上限 (dBm)", self.max_set_power_var),
            ("频谱仪输入保护 (dBm)", self.max_measured_power_var),
            ("功率容差 (dB)", self.power_tolerance_var),
            ("最大功率下降 (dB)", self.max_power_drop_var),
            ("信号源稳定时间 (s)", self.settling_time_var),
            ("频谱仪稳定时间 (s)", self.sa_settling_time_var),
            ("关断后等待 (s)", self.post_close_wait_var),
            ("测量次数", self.measurement_times_var),
            ("跨度", self.span_var),
            ("RBW", self.rbw_var),
            ("VBW", self.vbw_var),
            ("参考电平 (dBm)", self.reference_level_var),
            ("频谱仪衰减 (dB)", self.attenuation_var),
        ]
        for row, (label, var) in enumerate(params, 1):
            self._add_param(row, label, var)
        ttk.Checkbutton(
            frame, text="启用衰减器补偿", variable=self.attenuator_var
        ).grid(row=len(params) + 1, column=0, sticky="w", pady=(6, 2))
        ttk.Entry(
            frame, textvariable=self.attenuator_value_var, width=24
        ).grid(row=len(params) + 1, column=1, sticky="ew", pady=(6, 2))

    def _read_params(self):
        ranges = self._read_range_editor()
        start_power = parse_power(self.start_power_var.get(), "起始功率")
        power_step = parse_power(self.power_step_var.get(), "功率步进")
        max_set_power = parse_power(self.max_set_power_var.get(), "信号源功率上限")
        max_measured_power = parse_power(
            self.max_measured_power_var.get(), "频谱仪输入保护"
        )
        power_tolerance = parse_float(self.power_tolerance_var.get(), "功率容差")
        max_power_drop = parse_float(self.max_power_drop_var.get(), "最大功率下降")
        settling_time = parse_time(self.settling_time_var.get(), "信号源稳定时间")
        sa_settling_time = parse_time(
            self.sa_settling_time_var.get(), "频谱仪稳定时间"
        )
        post_close_wait = parse_time(self.post_close_wait_var.get(), "关断后等待")
        measurement_times = parse_int(self.measurement_times_var.get(), "测量次数")
        sa_config = {
            "input_coupling": "DC",
            "span": parse_frequency(self.span_var.get(), "跨度"),
            "rbw": parse_frequency(self.rbw_var.get(), "RBW"),
            "vbw": parse_frequency(self.vbw_var.get(), "VBW"),
            "reference_level": parse_power(
                self.reference_level_var.get(), "参考电平"
            ),
            "attenuation": parse_float(self.attenuation_var.get(), "频谱仪衰减"),
            "sweep_time": None,
        }
        use_attenuator = bool(self.attenuator_var.get())
        attenuator_value = parse_float(
            self.attenuator_value_var.get(), "衰减器补偿值"
        )

        if power_step <= 0 or measurement_times <= 0:
            raise ValueError("功率步进和测量次数必须大于 0。")

        test_configs = []
        for freq_range in ranges:
            current_freq = freq_range["start"]
            while current_freq <= freq_range["end"]:
                test_configs.append({
                    "test_name": f"{current_freq / 1e3:.0f}kHz最大功率测试"
                    if current_freq < 1e6
                    else f"{current_freq / 1e6:.0f}MHz最大功率测试",
                    "frequency": current_freq,
                    "start_power": start_power,
                    "power_step": power_step,
                    "max_set_power": max_set_power,
                    "max_measured_power": max_measured_power,
                    "power_tolerance": power_tolerance,
                    "max_power_drop": max_power_drop,
                    "attenuator_value": attenuator_value,
                    "use_attenuator": use_attenuator,
                    "settling_time": settling_time,
                    "sa_settling_time": sa_settling_time,
                    "post_close_wait": post_close_wait,
                    "measurement_times": measurement_times,
                    "spectrum_analyzer_config": sa_config,
                })
                current_freq += freq_range["step"]
        if not test_configs:
            raise ValueError("无法生成测试点。")
        return {"test_configs": test_configs}

    def _build_result_columns(self, frame):
        self._setup_tree(
            ["frequency", "max_power", "max_measured_power",
             "saturation_point", "steps", "notes", "timestamp"],
            [
                ("frequency", "频率 (Hz)", 110),
                ("max_power", "最大实际功率 (dBm)", 120),
                ("max_measured_power", "最大测量功率 (dBm)", 120),
                ("saturation_point", "是否饱和", 80),
                ("steps", "步进数", 70),
                ("notes", "备注", 160),
                ("timestamp", "时间戳", 150),
            ],
        )

    def _run_impl(self, instruments):
        from low_freq_max_power_procedure import LowFreqMaxPowerProcedure

        procedure = LowFreqMaxPowerProcedure(self.app.manager)
        configs = self.pending_params["test_configs"]
        for index, config in enumerate(configs):
            if self.stop_requested:
                break
            keep_output = index < len(configs) - 1
            procedure.run_test(
                instruments["signal_generator"],
                instruments["spectrum_analyzer"],
                config,
                keep_output=keep_output,
                should_stop=lambda: self.stop_requested,
            )
            if procedure.test_results:
                self.queue.put(("point", dict(procedure.test_results[-1])))
        if self.stop_requested:
            instruments["signal_generator"].enable_output(False)
        if procedure.test_results:
            self._save_results(procedure, LF_PROJECT_NAME)


class HarmonicTab(TestTabBase):
    title = "谐波测试"
    required_instruments = ("signal_generator", "spectrum_analyzer")

    def __init__(self, parent, app):
        freq_config = HARMONIC_FREQ_CONFIG
        sa_config = HARMONIC_SA_CONFIG
        harmonic_config = HARMONIC_MEASUREMENT_CONFIG
        self.start_freq_var = tk.StringVar(value=str(int(freq_config["start_frequency"])))
        self.end_freq_var = tk.StringVar(value=str(int(freq_config["end_frequency"])))
        self.step_freq_var = tk.StringVar(value=str(int(freq_config["step_frequency"])))
        self.fixed_power_var = tk.StringVar(value=str(freq_config["fixed_power"]))
        self.settling_time_var = tk.StringVar(value=str(freq_config["settling_time"]))
        self.span_var = tk.StringVar(value=str(sa_config["span"]))
        self.rbw_var = tk.StringVar(value=str(sa_config["rbw"]))
        self.vbw_var = tk.StringVar(value=str(sa_config["vbw"]))
        self.reference_level_var = tk.StringVar(value=str(sa_config["reference_level"]))
        self.attenuation_var = tk.StringVar(value=str(sa_config["attenuation"]))
        self.sweep_time_var = tk.StringVar(value=str(sa_config["sweep_time"]))
        self.harmonic_order_var = tk.StringVar(
            value=str(harmonic_config["harmonic_order"])
        )
        self.measurement_average_var = tk.StringVar(
            value=str(harmonic_config["measurement_average"])
        )
        super().__init__(parent, app)

    def _build_params(self, frame):
        params = [
            ("起始频率", self.start_freq_var),
            ("结束频率", self.end_freq_var),
            ("频率步进", self.step_freq_var),
            ("固定功率 (dBm)", self.fixed_power_var),
            ("信号源稳定时间 (s)", self.settling_time_var),
            ("频谱仪跨度", self.span_var),
            ("RBW", self.rbw_var),
            ("VBW", self.vbw_var),
            ("参考电平 (dBm)", self.reference_level_var),
            ("频谱仪衰减 (dB)", self.attenuation_var),
            ("扫描时间 (s)", self.sweep_time_var),
            ("谐波阶数", self.harmonic_order_var),
            ("测量平均次数", self.measurement_average_var),
        ]
        for row, (label, var) in enumerate(params):
            self._add_param(row, label, var)

    def _read_params(self):
        start_freq = parse_frequency(self.start_freq_var.get(), "起始频率")
        end_freq = parse_frequency(self.end_freq_var.get(), "结束频率")
        step_freq = parse_frequency(self.step_freq_var.get(), "频率步进")
        fixed_power = parse_power(self.fixed_power_var.get(), "固定功率")
        settling_time = parse_time(self.settling_time_var.get(), "信号源稳定时间")
        harmonic_order = parse_int(self.harmonic_order_var.get(), "谐波阶数")
        measurement_average = parse_int(
            self.measurement_average_var.get(), "测量平均次数"
        )
        sa_config = {
            "span": parse_frequency(self.span_var.get(), "频谱仪跨度"),
            "rbw": parse_frequency(self.rbw_var.get(), "RBW"),
            "vbw": parse_frequency(self.vbw_var.get(), "VBW"),
            "reference_level": parse_power(
                self.reference_level_var.get(), "参考电平"
            ),
            "attenuation": parse_float(self.attenuation_var.get(), "频谱仪衰减"),
            "sweep_time": parse_time(self.sweep_time_var.get(), "扫描时间"),
        }
        if start_freq <= 0 or end_freq < start_freq or step_freq <= 0:
            raise ValueError("频率范围参数无效。")
        if harmonic_order <= 1:
            raise ValueError("谐波阶数必须大于 1。")

        test_points = []
        current_freq = start_freq
        while current_freq <= end_freq + 1e-9:
            test_points.append({
                "frequency": current_freq,
                "set_power": fixed_power,
                "settling_time": settling_time,
            })
            current_freq += step_freq
        if test_points and test_points[-1]["frequency"] != end_freq:
            test_points.append({
                "frequency": end_freq,
                "set_power": fixed_power,
                "settling_time": settling_time,
            })
        return {
            "test_points": test_points,
            "sa_config": sa_config,
            "harmonic_config": {
                "harmonic_order": harmonic_order,
                "measurement_average": measurement_average,
            },
        }

    def _build_result_columns(self, frame):
        self._setup_tree(
            ["frequency_hz", "set_power_dbm", "fundamental_power_dbm",
             "harmonic_power_dbm", "harmonic_suppression_dbc", "timestamp"],
            [
                ("frequency_hz", "频率 (Hz)", 110),
                ("set_power_dbm", "设定功率 (dBm)", 110),
                ("fundamental_power_dbm", "基波功率 (dBm)", 110),
                ("harmonic_power_dbm", "谐波功率 (dBm)", 110),
                ("harmonic_suppression_dbc", "抑制 (dBc)", 100),
                ("timestamp", "时间戳", 150),
            ],
        )

    def _run_impl(self, instruments):
        from harmonic_test_procedure import HarmonicTestProcedure

        procedure = HarmonicTestProcedure(self.app.manager)
        points = self.pending_params["test_points"]
        sa_config = self.pending_params["sa_config"]
        harmonic_config = self.pending_params["harmonic_config"]
        for index, point in enumerate(points):
            if self.stop_requested:
                break
            keep_output = index < len(points) - 1
            procedure.run_harmonic_test(
                instruments["signal_generator"],
                instruments["spectrum_analyzer"],
                point,
                sa_config,
                harmonic_config,
                keep_output=keep_output,
            )
            if procedure.test_results:
                self.queue.put(("point", dict(procedure.test_results[-1])))
        if self.stop_requested:
            instruments["signal_generator"].enable_output(False)
        if procedure.test_results:
            self._save_results(procedure, HARMONIC_NAME)


class SubharmonicTab(TestTabBase):
    title = "分谐波测试"
    required_instruments = ("signal_generator", "spectrum_analyzer")

    def __init__(self, parent, app):
        freq_config = SUBHARMONIC_FREQ_CONFIG
        sa_config = SUBHARMONIC_SA_CONFIG
        sub_config = SUBHARMONIC_MEASUREMENT_CONFIG
        self.start_freq_var = tk.StringVar(value=str(int(freq_config["start_frequency"])))
        self.end_freq_var = tk.StringVar(value=str(int(freq_config["end_frequency"])))
        self.step_freq_var = tk.StringVar(value=str(int(freq_config["step_frequency"])))
        self.fixed_power_var = tk.StringVar(value=str(freq_config["fixed_power"]))
        self.settling_time_var = tk.StringVar(value=str(freq_config["settling_time"]))
        self.span_var = tk.StringVar(value=str(sa_config["span"]))
        self.rbw_var = tk.StringVar(value=str(sa_config["rbw"]))
        self.vbw_var = tk.StringVar(value=str(sa_config["vbw"]))
        self.reference_level_var = tk.StringVar(value=str(sa_config["reference_level"]))
        self.attenuation_var = tk.StringVar(value=str(sa_config["attenuation"]))
        self.subharmonic_orders_var = tk.StringVar(
            value=", ".join(str(order) for order in sub_config["subharmonic_orders"])
        )
        self.measurement_average_var = tk.StringVar(
            value=str(sub_config["measurement_average"])
        )
        self.search_offset_var = tk.StringVar(
            value=str(sub_config["subharmonic_search_offset"])
        )
        super().__init__(parent, app)

    def _build_params(self, frame):
        params = [
            ("起始频率", self.start_freq_var),
            ("结束频率", self.end_freq_var),
            ("频率步进", self.step_freq_var),
            ("固定功率 (dBm)", self.fixed_power_var),
            ("信号源稳定时间 (s)", self.settling_time_var),
            ("频谱仪跨度", self.span_var),
            ("RBW", self.rbw_var),
            ("VBW", self.vbw_var),
            ("参考电平 (dBm)", self.reference_level_var),
            ("频谱仪衰减 (dB)", self.attenuation_var),
            ("分谐波阶数 (逗号分隔)", self.subharmonic_orders_var),
            ("测量平均次数", self.measurement_average_var),
            ("搜索偏移", self.search_offset_var),
        ]
        for row, (label, var) in enumerate(params):
            self._add_param(row, label, var)

    def _read_params(self):
        start_freq = parse_frequency(self.start_freq_var.get(), "起始频率")
        end_freq = parse_frequency(self.end_freq_var.get(), "结束频率")
        step_freq = parse_frequency(self.step_freq_var.get(), "频率步进")
        fixed_power = parse_power(self.fixed_power_var.get(), "固定功率")
        settling_time = parse_time(self.settling_time_var.get(), "信号源稳定时间")
        subharmonic_orders = parse_csv_ints(
            self.subharmonic_orders_var.get(), "分谐波阶数"
        )
        measurement_average = parse_int(
            self.measurement_average_var.get(), "测量平均次数"
        )
        search_offset = parse_frequency(self.search_offset_var.get(), "搜索偏移")
        sa_config = {
            "span": parse_frequency(self.span_var.get(), "频谱仪跨度"),
            "rbw": parse_frequency(self.rbw_var.get(), "RBW"),
            "vbw": parse_frequency(self.vbw_var.get(), "VBW"),
            "reference_level": parse_power(
                self.reference_level_var.get(), "参考电平"
            ),
            "attenuation": parse_float(self.attenuation_var.get(), "频谱仪衰减"),
        }
        if start_freq <= 0 or end_freq < start_freq or step_freq <= 0:
            raise ValueError("频率范围参数无效。")
        if any(order <= 1 for order in subharmonic_orders):
            raise ValueError("分谐波阶数必须大于 1。")

        test_points = []
        current_freq = start_freq
        while current_freq <= end_freq + 1e-9:
            test_points.append({
                "frequency": current_freq,
                "set_power": fixed_power,
                "settling_time": settling_time,
            })
            current_freq += step_freq
        if test_points and test_points[-1]["frequency"] != end_freq:
            test_points.append({
                "frequency": end_freq,
                "set_power": fixed_power,
                "settling_time": settling_time,
            })
        return {
            "test_points": test_points,
            "sa_config": sa_config,
            "subharmonic_config": {
                "subharmonic_orders": subharmonic_orders,
                "measurement_average": measurement_average,
                "subharmonic_search_offset": search_offset,
            },
        }

    def _build_result_columns(self, frame):
        self._setup_tree(
            ["frequency_hz", "set_power_dbm", "fundamental_power_dbm",
             "timestamp"],
            [
                ("frequency_hz", "频率 (Hz)", 110),
                ("set_power_dbm", "设定功率 (dBm)", 110),
                ("fundamental_power_dbm", "基波功率 (dBm)", 110),
                ("timestamp", "时间戳", 150),
            ],
        )

    def _configure_result_columns(self, params):
        orders = params["subharmonic_config"]["subharmonic_orders"]
        columns = ["frequency_hz", "set_power_dbm", "fundamental_power_dbm"]
        specs = [
            ("frequency_hz", "频率 (Hz)", 110),
            ("set_power_dbm", "设定功率 (dBm)", 110),
            ("fundamental_power_dbm", "基波功率 (dBm)", 110),
        ]
        for order in orders:
            power_col = f"subharmonic_{order}_power_dbm"
            suppression_col = f"subharmonic_{order}_suppression_dbc"
            columns.append(power_col)
            columns.append(suppression_col)
            specs.append((power_col, f"1/{order}功率 (dBm)", 110))
            specs.append((suppression_col, f"1/{order}抑制 (dBc)", 100))
        specs.append(("timestamp", "时间戳", 150))
        self._setup_tree(columns, specs)

    def _run_impl(self, instruments):
        from subharmonic_test_procedure import SubharmonicTestProcedure

        procedure = SubharmonicTestProcedure(self.app.manager)
        points = self.pending_params["test_points"]
        sa_config = self.pending_params["sa_config"]
        subharmonic_config = self.pending_params["subharmonic_config"]
        for index, point in enumerate(points):
            if self.stop_requested:
                break
            keep_output = index < len(points) - 1
            procedure.run_subharmonic_test(
                instruments["signal_generator"],
                instruments["spectrum_analyzer"],
                point,
                sa_config,
                subharmonic_config,
                keep_output=keep_output,
            )
            if procedure.test_results:
                self.queue.put(("point", dict(procedure.test_results[-1])))
        if self.stop_requested:
            instruments["signal_generator"].enable_output(False)
        if procedure.test_results:
            self._save_results(procedure, SUBHARMONIC_NAME)


def main():
    enable_dpi_awareness()
    root = tk.Tk()
    root.title("SG Test Scripts 集成测试 GUI")
    root.geometry("1280x900")
    apply_gui_font(root, 11)
    IntegratedTestApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
