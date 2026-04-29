"""
导出所有谱图数据到 txt 文件，并生成对应的 JSON 索引文件
"""
import os
import json
import numpy as np
import pandas as pd
import torch
from tqdm import tqdm


def export_all_spectra(
    pkl_path: str = r'E:\spectrum_files\raman\raman_db.pkl',
    output_dir: str = r'E:\spectrum_files\raman\spectrum',
    json_path: str = r'E:\spectrum_files\raman\spectrum_index.json',
    x0: int = 400,
    x1: int = 4000
):
    """
    导出所有谱图数据到 txt 文件，并生成 JSON 索引

    Args:
        pkl_path: test.pkl 文件路径
        output_dir: 谱图 txt 文件输出目录
        json_path: JSON 索引文件输出路径
        x0: 波数下限 (cm^-1)
        x1: 波数上限 (cm^-1)
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)

    # 读取数据（使用 torch.load 因为 ir_db.pkl 是用 torch.save 保存的）
    print(f"正在读取数据文件: {pkl_path}")
    df = torch.load(pkl_path, weights_only=False)
    print(f"数据读取完成，共 {len(df)} 条记录")

    # 初始化索引列表
    index_list = []

    # 导出每条谱图数据
    print("开始导出谱图数据...")
    for idx in tqdm(range(len(df)), desc="导出进度"):
        spectrum = df['spectrum'].values[idx]
        smiles = df['structure'].values[idx]  # ir_db.pkl 中使用 'structure' 列

        # 生成文件名（使用 SMILES 的安全版本，避免特殊字符）
        filename = f"RAMAN_{idx:05d}.txt"

        # 完整文件路径
        file_path = os.path.join(output_dir, filename)

        # 生成 x 轴值（波数，从 x1 到 x0）
        x_values = np.linspace(x1, x0, len(spectrum))

        # 合并 x, y 数据
        data_to_save = np.column_stack((x_values, spectrum))

        # 保存为 txt 文件（两列，制表符分隔）
        np.savetxt(file_path, data_to_save, fmt='%.6f', delimiter=' ')

        # 添加到索引列表
        index_list.append({
            'spectrum_file': file_path,
            'smiles': smiles
        })

    # 保存 JSON 索引文件
    print(f"正在保存 JSON 索引文件: {json_path}")
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(index_list, f, ensure_ascii=False, indent=2)

    print("=" * 50)
    print(f"导出完成！")
    print(f"  - 谱图文件目录: {output_dir}")
    print(f"  - JSON 索引文件: {json_path}")
    print(f"  - 导出记录数: {len(index_list)}")
    print("=" * 50)

    return index_list


if __name__ == "__main__":
    export_all_spectra()
