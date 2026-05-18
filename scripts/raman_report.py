import os
import pandas as pd 
import numpy as np
import matplotlib.pyplot as plt
import json


def get_log(content):
    
    keywords = ['对焦', 'Actual exposure time', 'grating']
    
    log = []
    body_id = [content.index(c) for c in content if 'body: "{' in c]
    for i in range(0, len(body_id)-1, 2):
        print(i)
        log.extend(content[body_id[i]: body_id[i+1]])
    return log
        
    # for c in content:
    #     body_id = content.index('body: "{')
    #     if '对焦' in c: log.append(c)
    #     exp_time_id = content.index('Actual exposure time')
    #     c.extend(content[exp_time_id:exp_time_id+4])
        
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

# 读取日志
with open('/home/lyt/projects/Spec_Agent/ExRaman_2026-04-23.log', 'r') as f:
    content = f.readlines()
log = get_log(content) # 提取与测试有关内容
# 写入新日志文件
with open('/home/lyt/projects/Spec_Agent/log.log', 'w') as l:
    for c in log:
        l.writelines(c)