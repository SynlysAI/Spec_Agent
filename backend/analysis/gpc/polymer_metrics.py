from typing import Any


MONOMER_LIBRARY = {
    "Styrene": 104.15,
    "MMA": 100.12,
    "Ethylene": 28.05,
    "Propylene": 42.08,
    "Vinyl Chloride": 62.5,
    "Lactide": 72.06,
}


def calculate_monomer_dp(mn: float, monomer_type: str = None, custom_m0: float = None, m_end_groups: float = 0) -> Any:
    """计算均聚物的数均聚合度（DPn）。"""
    m0 = custom_m0
    if monomer_type in MONOMER_LIBRARY:
        m0 = MONOMER_LIBRARY[monomer_type]

    if not m0:
        return "错误：请提供有效的单体名称或自定义 M0 值。"

    dp = (mn - m_end_groups) / m0
    return round(dp, 2)


def calculate_complex_polymer_dp(mn: float, components: list[dict[str, float]]) -> Any:
    """计算共聚物的平均聚合度。"""
    total_fraction = sum(component["molar_fraction"] for component in components)
    if not (0.99 <= total_fraction <= 1.01):
        return "错误：组分的摩尔分数之和必须等于 1.0"

    average_m0 = sum(component["m_unit"] * component["molar_fraction"] for component in components)
    total_dp = mn / average_m0

    return {
        "average_m0": round(average_m0, 2),
        "total_dp": round(total_dp, 2),
        "component_segments": [
            {f"component_{index + 1}_dp": round(total_dp * component["molar_fraction"], 2)}
            for index, component in enumerate(components)
        ],
    }
