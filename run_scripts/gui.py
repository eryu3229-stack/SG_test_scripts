# -*- coding: utf-8 -*-
# SG Test Scripts GUI - 信号源自动化测试界面

import sys, os, time, threading
from datetime import datetime
from queue import Queue

current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
for d in ["", "instruments", "procedures", "configs", "utils"]:
    p = os.path.join(parent_dir, d)
    if p not in sys.path:
        sys.path.append(p)

import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from instrument_manager import InstrumentManager
from signal_generator import SignalGenerator
from spectrum_analyzer import SpectrumAnalyzer
from power_meter import PowerMeter
from utils.formatting import format_frequency


class LogRedirector:
    def __init__(self, queue):
        self.queue = queue

    def write(self, msg):
        if msg.strip():
            self.queue.put(msg.rstrip())

    def flush(self):
        pass


class SignalTestGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("信号源自动化测试")
        self.geometry("1100x780")
        self.manager = None
        self.signal_gen = None
        self.spectrum_analyzer = None
        self.power_meter = None
        self.test_thread = None
        self.running = False
        self.log_queue = Queue()
        self.current_results = []
        self.test_types = [
            ("谐波测试", "harmonic"),
            ("分谐波测试", "subharmonic"),
            ("最大功率测试", "max_power"),
            ("低频最大功率", "low_freq"),
            ("功率扫描测试", "power_sweep"),
        ]
        self._build_ui()
        self._build_tab_contents()
        self.after(100, self._poll_log)

    def _build_ui(self):
        self._build_instrument_panel()
        self._build_center_area()

    def _build_instrument_panel(self):
        f = ttk.LabelFrame(self, text="仪器连接", padding=8)
        f.pack(fill="x", padx=8, pady=(8, 2))
        ttk.Label(f, text="信号源:").grid(row=0, column=0, sticky="w", padx=(0, 4))
        self.sg_var = tk.StringVar(value="TCPIP::192.168.1.100::INSTR")
        ttk.Entry(f, textvariable=self.sg_var, width=40).grid(row=0, column=1, padx=4)
        ttk.Label(f, text="频谱仪:").grid(row=1, column=0, sticky="w", padx=(0, 4))
        self.sa_var = tk.StringVar(value="TCPIP::192.168.1.101::INSTR")
        ttk.Entry(f, textvariable=self.sa_var, width=40).grid(row=1, column=1, padx=4)
        ttk.Label(f, text="功率计:").grid(row=2, column=0, sticky="w", padx=(0, 4))
        self.pm_var = tk.StringVar(value="USB::0x0AAD::0x015F::101930::INSTR")
        ttk.Entry(f, textvariable=self.pm_var, width=40).grid(row=2, column=1, padx=4)
        self.connect_btn = ttk.Button(f, text="连接仪器", command=self._connect_instruments)
        self.connect_btn.grid(row=0, column=2, rowspan=3, padx=(8, 0), sticky="ns")
        self.conn_status = ttk.Label(f, text="未连接", foreground="gray")
        self.conn_status.grid(row=0, column=3, rowspan=3, padx=(8, 0), sticky="w")
        f.columnconfigure(1, weight=1)

    def _build_center_area(self):
        paned = ttk.PanedWindow(self, orient="vertical")
        paned.pack(fill="both", expand=True, padx=8, pady=4)
        top = ttk.Frame(paned)
        paned.add(top, weight=2)
        self.notebook = ttk.Notebook(top)
        self.notebook.pack(side="left", fill="both", expand=True)
        self.tab_frames = {}
        for label, key in self.test_types:
            f = ttk.Frame(self.notebook, padding=8)
            self.notebook.add(f, text=label)
            self.tab_frames[key] = f
        ctrl = ttk.Frame(top, padding=8)
        ctrl.pack(side="right", fill="y")
        self.run_btn = ttk.Button(ctrl, text="\u25b6 运行", command=self._run_test, width=14)
        self.run_btn.pack(pady=4)
        self.stop_btn = ttk.Button(ctrl, text="\u25a0 停止", command=self._stop_test, state="disabled", width=14)
        self.stop_btn.pack(pady=4)
        self.save_btn = ttk.Button(ctrl, text="保存结果", command=self._save_results, width=14)
        self.save_btn.pack(pady=4)
        ttk.Separator(ctrl, orient="horizontal").pack(fill="x", pady=8)
        self.progress = ttk.Progressbar(ctrl, mode="indeterminate", length=120)
        self.progress.pack(pady=4)
        self.status_var = tk.StringVar(value="就绪")
        ttk.Label(ctrl, textvariable=self.status_var, wraplength=140).pack(pady=4)
        bot = ttk.Frame(paned)
        paned.add(bot, weight=1)
        lf = ttk.LabelFrame(bot, text="运行日志", padding=4)
        lf.pack(side="left", fill="both", expand=True)
        self.log_text = scrolledtext.ScrolledText(lf, height=10, font=("Consolas", 9), wrap="word")
        self.log_text.pack(fill="both", expand=True)
        rf = ttk.LabelFrame(bot, text="测试结果", padding=4)
        rf.pack(side="right", fill="both", expand=True)
        self.result_tree = ttk.Treeview(rf, height=6, show="headings")
        self.result_tree.pack(fill="both", expand=True)
        ttk.Scrollbar(rf, orient="vertical", command=self.result_tree.yview).pack(side="right", fill="y")

    def _log(self, msg):
        self.log_text.insert("end", msg + "\n")
        self.log_text.see("end")

    def _poll_log(self):
        while not self.log_queue.empty():
            self._log(self.log_queue.get_nowait())
        self.after(100, self._poll_log)

    def _connect_instruments(self):
        self.connect_btn.config(state="disabled")
        t = threading.Thread(target=self._connect_thread, daemon=True)
        t.start()

    def _connect_thread(self):
        try:
            mgr = InstrumentManager()
            sg = sa = pm = None
            r = self.sg_var.get().strip()
            if r:
                i = mgr.connect_instrument(r, "signal_generator")
                if i:
                    sg = SignalGenerator(i)
                    self._log(f"SG: {sg.get_idn()}")
            r = self.sa_var.get().strip()
            if r:
                i = mgr.connect_instrument(r, "spectrum_analyzer")
                if i:
                    sa = SpectrumAnalyzer(i)
                    self._log(f"SA: {sa.get_idn()}")
            r = self.pm_var.get().strip()
            if r:
                i = mgr.connect_instrument(r, "power_meter")
                if i:
                    pm = PowerMeter(i)
                    self._log(f"PM: {pm.get_idn()}")
            self.manager, self.signal_gen, self.spectrum_analyzer, self.power_meter = mgr, sg, sa, pm
            parts = [n for n, v in [("SG", sg), ("SA", sa), ("PM", pm)] if v]
            self.after(0, lambda: self.conn_status.config(
                text=f"OK: {', '.join(parts)}" if parts else "无仪器", foreground="green" if parts else "red"))
            self._log(f"连接完成: {', '.join(parts)}")
        except Exception as e:
            self._log(f"失败: {e}")
        finally:
            self.after(0, lambda: self.connect_btn.config(state="normal"))

    def _run_test(self):
        if not self.manager:
            import tkinter.messagebox as mb
            mb.showwarning("提示", "请先连接仪器")
            return
        key = self.test_types[self.notebook.index("current")][1]
        if key in ("max_power", "power_sweep"):
            if not self._zero_power_meter():
                return
        self._start_test(key)

    def _start_test(self, key):
        pass  # will be filled in next step

    def _stop_test(self):
        self.running = False
        self._log("已停止")
        self.after(0, self._finish_run)

    def _finish_run(self):
        self.running = False
        self.run_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.progress.stop()
        self.status_var.set("完成")

    def _save_results(self):
        if not self.current_results:
            import tkinter.messagebox as mb
            mb.showinfo("提示", "无结果可保存")
            return
        try:
            import pandas as pd
            out = os.path.join(parent_dir, "output")
            os.makedirs(out, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fp = os.path.join(out, f"gui_{ts}.xlsx")
            pd.DataFrame(self.current_results).to_excel(fp, index=False)
            self._log(f"保存: {fp}")
        except Exception as e:
            self._log(f"保存失败: {e}")



    def _build_tab_contents(self):
        for key in [k for _, k in self.test_types]:
            getattr(self, f"_build_{k}_tab")()

    def _add_param(self, parent, label, default, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 4))
        var = tk.StringVar(value=str(default))
        ttk.Entry(parent, textvariable=var, width=30).grid(row=row, column=1, sticky="ew", padx=4)
        return var

    def _build_harmonic_tab(self):
        f = self.tab_frames["harmonic"]
        import harmonic_test_config as cfg
        fcfg = cfg.FREQUENCY_SWEEP_CONFIG
        params = [
            ("起止频率", f"{format_frequency(fcfg['start_frequency'])} - {format_frequency(fcfg['end_frequency'])}"),
            ("步进频率", format_frequency(fcfg['step_frequency'])),
            ("固定功率 (dBm)", str(fcfg["fixed_power"])),
        ]
        for i, (label, val) in enumerate(params):
            self._add_param(f, label, val, i)

    def _build_subharmonic_tab(self):
        ttk.Label(self.tab_frames["subharmonic"], text="参数面板待完善").pack()

    def _build_max_power_tab(self):
        ttk.Label(self.tab_frames["max_power"], text="参数面板待完善").pack()

    def _build_low_freq_tab(self):
        ttk.Label(self.tab_frames["low_freq"], text="参数面板待完善").pack()

    def _build_power_sweep_tab(self):
        ttk.Label(self.tab_frames["power_sweep"], text="参数面板待完善").pack()

    def _start_test(self, key):
        self.running = True
        self.run_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.progress.start()
        self.status_var.set(f"执行中: {key}")
        self.current_results = []
        for item in self.result_tree.get_children():
            self.result_tree.delete(item)

        def worker():
            import io, contextlib
            log_buf = io.StringIO()
            old_out, old_err = sys.stdout, sys.stderr
            try:
                sys.stdout = sys.stderr = log_buf
                self._log(f"开始测试: {key}")
                getattr(self, f"_exec_{key}")()
            except Exception as e:
                self._log(f"错误: {e}")
            finally:
                sys.stdout, sys.stderr = old_out, old_err
                leftover = log_buf.getvalue()
                for line in leftover.split("\n"):
                    if line.strip():
                        self._log(line.strip())
                self.after(0, self._finish_run)

        threading.Thread(target=worker, daemon=True).start()

    def _exec_harmonic(self):
        from harmonic_test_procedure import HarmonicTestProcedure
        import harmonic_test_config as cfg
        proc = HarmonicTestProcedure(self.manager)
        points = cfg.generate_frequency_points()
        self._log(f"测试点数: {len(points)}")
        for i, pt in enumerate(points):
            if not self.running: break
            r = proc.run_harmonic_test(
                self.signal_gen, self.spectrum_analyzer, pt,
                cfg.SPECTRUM_ANALYZER_CONFIG, cfg.HARMONIC_MEASUREMENT_CONFIG,
                keep_output=(i < len(points) - 1))
            if r:
                self.current_results.append(r)
                self._update_results(r)

    def _zero_power_meter(self):
        if not self.power_meter:
            import tkinter.messagebox as mb
            mb.showwarning("提示", "此测试需要连接功率计")
            return False
        if not mb.askyesno("功率计归零", "请断开功率计输入信号。\\n确认已断开吗？"):
            return False
        try:
            self.power_meter.zero()
            mb.showinfo("归零完成", "请重新连接功率计输入信号。\\n连接完成后点击确定。")
            return True
        except Exception as e:
            mb.showerror("归零失败", str(e))
            return False
    def _exec_subharmonic(self):
        if not self.spectrum_analyzer:
            self._log("错误: 需要连接频谱仪"); return
        from subharmonic_test_procedure import SubharmonicTestProcedure
        import subharmonic_test_config as cfg
        proc = SubharmonicTestProcedure(self.manager)
        points = cfg.generate_frequency_points()
        self._log(f"测试点数: {len(points)}")
        for i, pt in enumerate(points):
            if not self.running: break
            r = proc.run_subharmonic_test(
                self.signal_gen, self.spectrum_analyzer, pt,
                cfg.SPECTRUM_ANALYZER_CONFIG, cfg.SUBHARMONIC_MEASUREMENT_CONFIG,
                keep_output=(i < len(points) - 1))
            if r:
                self.current_results.append(r)
                self._update_results(r)


    def _exec_max_power(self):
        if not self.power_meter:
            self._log("错误: 需要连接功率计"); return
        from max_power_procedure import MaxPowerProcedure
        import max_power_config as cfg
        proc = MaxPowerProcedure(self.manager)
        configs = cfg.test_configs
        self._log(f"测试点数: {len(configs)}")
        for i, tc in enumerate(configs):
            if not self.running: break
            proc.run_test(self.signal_gen, self.power_meter, tc,
                         keep_output=(i < len(configs) - 1))
        for r in proc.test_results:
            self.current_results.append(r)
            self._update_results(r)


    def _exec_low_freq(self):
        if not self.spectrum_analyzer:
            self._log("错误: 需要连接频谱仪"); return
        from low_freq_max_power_procedure import LowFreqMaxPowerProcedure
        import low_freq_max_power_config as cfg
        proc = LowFreqMaxPowerProcedure(self.manager)
        configs = cfg.test_configs
        self._log(f"测试点数: {len(configs)}")
        for i, tc in enumerate(configs):
            if not self.running: break
            proc.run_test(self.signal_gen, self.spectrum_analyzer, tc,
                         keep_output=(i < len(configs) - 1))
        for r in proc.test_results:
            self.current_results.append(r)
            self._update_results(r)


    def _exec_power_sweep(self):
        if not self.power_meter:
            self._log("错误: 需要连接功率计"); return
        from power_sweep_procedure import TestProcedure
        import power_sweep_config as cfg
        proc = TestProcedure(self.manager)
        configs = cfg.test_configs
        proc.prepare_test(self.signal_gen, self.power_meter)
        self._log(f"测试点数: {len(configs)}")
        for i, tc in enumerate(configs):
            if not self.running: break
            proc.run_test(self.signal_gen, self.power_meter, tc,
                         keep_output=(i < len(configs) - 1))
        for r in proc.test_results:
            self.current_results.append(r)
            self._update_results(r)
    def _update_results(self, result):
        if not isinstance(result, dict): return
        keys = list(result.keys())
        cols = [k for k in keys if k != "timestamp"]
        if self.result_tree["columns"] != cols:
            self.result_tree["columns"] = cols
            HEAD = {"frequency_hz": "频率(Hz)", "frequency_mhz": "频率(MHz)",
                    "set_power_dbm": "设定功率", "fundamental_power_dbm": "基波功率",
                    "harmonic_power_dbm": "谐波功率", "harmonic_suppression_dbc": "抑制(dBc)"}
            for c in cols:
                self.result_tree.heading(c, text=HEAD.get(c, c))
                self.result_tree.column(c, width=100, anchor="center")
        vals = [result.get(k, "") for k in cols]
        self.result_tree.insert("", "end", values=vals)


if __name__ == "__main__":
    app = SignalTestGUI()
    app.mainloop()
