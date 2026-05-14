import os
import pandas as pd 
import numpy as np
import matplotlib.pyplot as plt
import json

def get_metadata(raw_data):
    # 去掉前缀和换行符，提取 JSON 部分
    json_str = raw_data.replace('capture_settings:', '').strip()

    # 解析 JSON
    data = json.loads(json_str)

    # 定义"基本信息与元数据"相关字段映射
    metadata_fields = {
        'laser': '激光波长 (nm)',
        'fExposure': '曝光时间 (s)',
        'noAccums': '累加次数',
        'nokineticScans': '动力学扫描次数',
        'accumCycleTime': '累加周期时间 (s)',
        'kineticCycleTime': '动力学周期时间 (s)',
        'centerWave': '中心波长 (nm)',
        'shWavelength': '波长设置 (nm)',
        'shGrat': '光栅选择',
        'shGratOffset': '光栅偏移',
        'readMode': '读出模式',
        'acquisitionMode': '采集模式',
        'bStepGlue': '步进拼接'
    }

    # 提取
    metadata = {}
    for key, label in metadata_fields.items():
        if key in data:
            metadata[label] = data[key]
    return metadata


# example usage
with open('raman_tests/results/218_0.dat', 'r') as f:
    lines = f.readlines() 
raw_data = lines[1] # 第二行是采集条件

metadata = get_metadata(raw_data)
preprocess_info = {
    '基线校正': 'PEER',
    '平滑算法': 'WhittakerSmooth',
    '归一化': 'Max',
    '信噪比': ''
}
model_info = {
    '输入维度': '1024',
    '拉曼位移范围': '400-4000'
}

report = {
    "基本信息与元数据": metadata,
    "预处理信息": preprocess_info,
    "模型信息": model_info
}

for label, value in report.items():
    print(f"  {label}: {value}")
    