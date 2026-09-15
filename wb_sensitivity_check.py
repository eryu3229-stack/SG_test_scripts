# -*- coding: utf-8 -*-
"""灵敏度改动自检（离线，不需要仪器、不需要第三方依赖）：
1. 全项目 ast.parse 语法检查
2. spurious 流程的行字典键集合 == FIELDNAMES（字段一致性）
3. 配置自洽：段级 input_att_db 覆盖 + 门限/灵敏度阶梯的算术核对
4. 关键辅助函数的行为断言（触底检测 / 段级设置合并）
"""
import ast
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PROBLEMS = []


def check_syntax():
    bad = []
    for dirpath, _, filenames in os.walk(ROOT):
        if any(p in dirpath for p in (".git", "__pycache__", ".workbuddy")):
            continue
        for name in filenames:
            if not name.endswith(".py"):
                continue
            path = os.path.join(dirpath, name)
            try:
                with open(path, "rb") as fh:
                    ast.parse(fh.read(), filename=path)
            except SyntaxError as e:
                bad.append(f"{path}: {e}")
    if bad:
        PROBLEMS.append("语法错误:\n  " + "\n  ".join(bad))
    else:
        print("[1] 语法检查通过（全项目 ast.parse）")


def check_spurious_fields():
    path = os.path.join(ROOT, "procedures", "spurious_procedure.py")
    tree = ast.parse(open(path, "rb").read())
    fieldnames = None
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id == "FIELDNAMES":
                    fieldnames = [e.value for e in node.value.elts]
    if fieldnames is None:
        PROBLEMS.append("未找到 FIELDNAMES")
        return
    # 找到 run_spurious_test 里构造 result 字典的键
    result_keys = None
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "run_spurious_test":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Assign):
                    for t in sub.targets:
                        if isinstance(t, ast.Name) and t.id == "result":
                            if isinstance(sub.value, ast.Dict):
                                result_keys = [k.value for k in sub.value.keys]
    if result_keys is None:
        PROBLEMS.append("未找到 result 字典")
        return
    missing = [k for k in result_keys if k not in fieldnames]
    extra = [k for k in fieldnames if k not in result_keys]
    if len(result_keys) != len(fieldnames) or missing or extra:
        PROBLEMS.append(
            f"字段不一致: 列数 {len(fieldnames)} vs 行键 {len(result_keys)}; "
            f"缺列 {missing}; 多余列 {extra}"
        )
    else:
        print(f"[2] 字段一致：{len(fieldnames)} 列，行字典键与 FIELDNAMES 完全相等")
    print("    列 =", ", ".join(fieldnames))


def check_config_ladder():
    """核对配置里的衰减取值与文档中的灵敏度阶梯一致。"""
    sys.path.insert(0, os.path.join(ROOT, "configs"))
    import spurious_config as cfg

    print(f"[3] 全局 attenuation_db = {cfg.attenuation_db} dB")
    segs = list(cfg.near_carrier_segments) + [cfg.far_carrier_segment]
    for seg in segs:
        att = seg.get("input_att_db")
        eff = cfg.attenuation_db if att is None else att
        span = seg.get("span_hz")
        rbw = seg.get("rbw_hz")
        print(
            f"    {seg['name']:14s} span={span/1e6:8.1f} MHz rbw={rbw:8.1f} Hz "
            f"att={eff:>4.1f} dB  混频器电平={cfg.carrier_power_dbm - eff:>6.1f} dBm "
            f"点数={seg.get('sweep_points')}"
        )
        if cfg.carrier_power_dbm - eff > -10:
            PROBLEMS.append(f"{seg['name']}: 混频器电平高于 −10 dBm（{cfg.carrier_power_dbm - eff}）")
    if cfg.preamp:
        PROBLEMS.append("预放已开启，但本方案假定关闭（会抬高混频器电平）")


def check_helpers():
    path = os.path.join(ROOT, "procedures", "spurious_procedure.py")
    src = open(path, "rb").read()
    tree = ast.parse(src)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    funcs = {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}
    for need in (
        "_resolve_segment_settings",
        "_verify_settings",
        "_measure_average_noise_floor",
        "_detect_floor_clipping",
        "_estimate_noise_floor",
    ):
        if need not in funcs:
            PROBLEMS.append(f"缺少方法 {need}")

    # 抽出来单独跑：触底检测 / 段级设置合并
    import numpy as np

    ns = {"np": np}
    for name in ("_detect_floor_clipping", "_resolve_segment_settings"):
        mod = ast.Module(body=[funcs[name]], type_ignores=[])
        # 去掉 decorator（staticmethod）后编译
        mod.body[0].decorator_list = []
        code = compile(mod, path, "exec")
        exec(code, ns)  # noqa: S102

    flat_noise = list(np.random.default_rng(0).normal(-80.0, 1.0, 200))
    assert ns["_detect_floor_clipping"](flat_noise) is False, "正常噪声被误判触底"
    clipped = list(np.concatenate([np.full(60, -90.0), np.random.default_rng(1).normal(-70, 1, 140)]))
    assert ns["_detect_floor_clipping"](clipped) is True, "触底迹线未被识别"

    merged = ns["_resolve_segment_settings"](
        {"input_att_db": 35, "ref_level_dbm": None, "sweep_points": 20001},
        {"reference_level_dbm": 10, "attenuation_db": 25, "preamp": False, "preamp_band": None},
    )
    assert merged["input_att_db"] == 35, merged
    assert merged["ref_level_dbm"] == 10, merged
    assert merged["sweep_points"] == 20001, merged

    merged2 = ns["_resolve_segment_settings"](
        {"input_att_db": None, "ref_level_dbm": None, "sweep_points": None},
        {"reference_level_dbm": 10, "attenuation_db": 25, "preamp": False, "preamp_band": None},
    )
    assert merged2["input_att_db"] == 25 and merged2["sweep_points"] is None, merged2
    print("[4] 辅助函数断言通过（触底检测 / 段级设置合并）")


if __name__ == "__main__":
    check_syntax()
    check_spurious_fields()
    check_config_ladder()
    check_helpers()
    print()
    if PROBLEMS:
        print("FAIL:")
        for p in PROBLEMS:
            print(" -", p)
        sys.exit(1)
    print("ALL PASS")
