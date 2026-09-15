#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CSV 流式写入工具 — 测一点写一点，逐行 flush 落盘

本工程**只输出 CSV**（不再转 XLSX）。CSV 可逐行 append + flush，
断电/中断时已写入的行仍可读；XLSX 是 zip 容器，必须最后写 EOCD 才能打开，
无法真正做到流式，故弃用。
"""

import csv
import os


class CsvStreamer:
    """流式 CSV 写入器

    用法:
        stream = CsvStreamer("path.csv", ["col1", "col2"])
        stream.append({"col1": "val1", "col2": "val2"})
        stream.close()
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

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

