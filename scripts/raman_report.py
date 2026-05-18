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
        


# example usage
# 读取日志
with open('/home/lyt/projects/Spec_Agent/ExRaman_2026-04-23.log', 'r') as f:
    content = f.readlines()
log = get_log(content) # 提取与测试有关内容
# 写入新日志文件
with open('/home/lyt/projects/Spec_Agent/log.log', 'w') as l:
    for c in log:
        l.writelines(c)