def generate_calibration_filename(inst_id, test_date, curve_id, solvent, mix_type):
    """
    生成标准化的校准曲线文件名
    格式: [仪器编号]_[日期]_[编号]_[溶剂]_[混合类型].json
    """
    # 过滤掉非法字符，防止文件名报错
    safe_fields = [str(f).replace("/", "-").replace(" ", "") for f in [inst_id, test_date, curve_id, solvent, mix_type]]
    filename = "_".join(safe_fields) + ".json"
    return filename