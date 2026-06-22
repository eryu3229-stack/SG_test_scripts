#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSV 流式写入工具 — 测一点写一点，最后转 XLSX"""

import csv
import os


class CsvStreamer:
    """流式 CSV 写入器
    
    用法:
        stream = CsvStreamer("path.csv", ["col1", "col2"])
        stream.append({"col1": "val1", "col2": "val2"})
        stream.to_xlsx("path.xlsx", sheet_name="测试数据")
    """

    def __init__(self, filepath, fieldnames):
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        self.filepath = filepath
        self.file = open(filepath, 'w', newline='', encoding='utf-8-sig')
        self.writer = csv.DictWriter(self.file, fieldnames=fieldnames)
        self.writer.writeheader()
        self.file.flush()

    def append(self, row):
        self.writer.writerow(row)
        self.file.flush()

    def close(self):
        if self.file and not self.file.closed:
            self.file.close()

    def to_xlsx(self, xlsx_path, sheet_name="测试数据", summary_data=None):
        """读取已写入的 CSV，转为 XLSX"""
        self.close()
        import pandas as pd
        df = pd.read_csv(self.filepath, encoding='utf-8-sig')
        xlsx_dir = os.path.dirname(os.path.abspath(xlsx_path))
        if xlsx_dir:
            os.makedirs(xlsx_dir, exist_ok=True)
        with pd.ExcelWriter(xlsx_path, engine='openpyxl') as writer:
            if summary_data is not None:
                pd.DataFrame(summary_data).to_excel(writer, sheet_name='测试摘要', index=False)
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        print(f"Excel 已保存: {xlsx_path}")

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
