from __future__ import annotations

import json
import os
import sqlite3
import zipfile

import pandas as pd

from analysis.gpc.tools.gpc_pdf_processor import GPCPDFProcessor
from config import GLOBAL_CONFIG


def get_database_path() -> str:
    """获取谱图数据库文件路径。"""
    return GLOBAL_CONFIG["database"]["path"]


def connect_database() -> sqlite3.Connection:
    """创建 SQLite 数据库连接。"""
    return sqlite3.connect(get_database_path())


def get_spectrum_stats() -> dict:
    """获取谱图数据库各类记录统计。

    Returns:
        包含各类谱图数量和总数的字典，如：
        {'gpc': 10, 'nmr': 20, 'ir': 30, 'raman': 40, 'total': 100}
    """
    try:
        conn = connect_database()
        # 基础谱图统计
        stats_df = pd.read_sql_query("""
            SELECT 'gpc' AS type, COUNT(*) AS cnt FROM gpc_spectrum
            UNION ALL
            SELECT 'nmr', COUNT(*) FROM nmr_spectrum
            UNION ALL
            SELECT 'ir', COUNT(*) FROM ir_spectrum
            UNION ALL
            SELECT 'raman', COUNT(*) FROM raman_spectrum
        """, conn)
        
        # 化学性质统计 (SMILES, 骨架, 官能团)
        chem_stats_df = pd.read_sql_query("SELECT * FROM spectrum_stats LIMIT 1", conn)
        
        conn.close()

        stats = {
            'gpc': 0, 'nmr': 0, 'ir': 0, 'raman': 0, 'total': 0,
            'chem_smiles': 0, 'chem_scaffolds': 0, 'chem_fgs': 0
        }
        for _, row in stats_df.iterrows():
            stats[row['type']] = int(row['cnt'])
            
        if not chem_stats_df.empty:
            stats['chem_smiles'] = int(chem_stats_df['total_smiles'].values[0])
            stats['chem_scaffolds'] = int(chem_stats_df['unique_scaffolds'].values[0])
            stats['chem_fgs'] = int(chem_stats_df['unique_fgs'].values[0])
            
        stats['total'] = sum([stats['gpc'], stats['nmr'], stats['ir'], stats['raman']])
        return stats
    except Exception:
        return {
            'gpc': 0, 'nmr': 0, 'ir': 0, 'raman': 0, 'total': 0,
            'chem_smiles': 0, 'chem_scaffolds': 0, 'chem_fgs': 0
        }


def get_spectrum_files_root() -> str:
    """获取谱图原始文件根目录。"""
    return GLOBAL_CONFIG["paths"]["spectrum_files_root"]


def save_uploaded_file(uploaded_file, spectrum_type: str, save_dir_name: str) -> str | None:
    """保存上传的单个谱图文件。

    Args:
        uploaded_file: Streamlit 上传文件对象。
        spectrum_type: 谱图类型，如 `gpc`、`nmr`、`ir`、`raman`。
        save_dir_name: 该类型下的保存子目录名。

    Returns:
        保存后的文件路径；若未上传文件则返回 `None`。
    """
    if uploaded_file is None:
        return None

    type_dir = os.path.join(get_spectrum_files_root(), spectrum_type)
    sample_dir = os.path.join(type_dir, save_dir_name)
    os.makedirs(sample_dir, exist_ok=True)

    file_path = os.path.join(sample_dir, uploaded_file.name)
    with open(file_path, "wb") as file:
        file.write(uploaded_file.getbuffer())
    return file_path


def save_uploaded_archive(uploaded_file, spectrum_type: str, save_dir_name: str) -> str | None:
    """保存并解压上传的压缩文件。

    Args:
        uploaded_file: Streamlit 上传的压缩包文件对象。
        spectrum_type: 谱图类型。
        save_dir_name: 解压目标子目录名。

    Returns:
        解压后的有效目录路径；若未上传文件则返回 `None`。
    """
    if uploaded_file is None:
        return None

    type_dir = os.path.join(get_spectrum_files_root(), spectrum_type)
    target_dir = os.path.join(type_dir, save_dir_name)
    os.makedirs(target_dir, exist_ok=True)

    zip_path = os.path.join(type_dir, uploaded_file.name)
    with open(zip_path, "wb") as file:
        file.write(uploaded_file.getbuffer())

    with zipfile.ZipFile(zip_path, "r") as zip_ref:
        zip_ref.extractall(target_dir)

    os.remove(zip_path)
    items = os.listdir(target_dir)
    if len(items) == 1:
        item_path = os.path.join(target_dir, items[0])
        if os.path.isdir(item_path):
            return item_path
    return target_dir


def extract_calibration_json(pdf_path: str) -> str | None:
    """从 GPC 标定 PDF 提取 JSON 字符串。

    Args:
        pdf_path: GPC 标定 PDF 文件路径。

    Returns:
        JSON 字符串；若 `pdf_path` 为空则返回 `None`。
    """
    if not pdf_path:
        return None

    with GPCPDFProcessor() as processor:
        result_dict = processor.extract_gpc_calibration_table(pdf_path)
    return json.dumps(result_dict, ensure_ascii=False, indent=2)
