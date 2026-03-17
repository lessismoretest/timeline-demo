#!/usr/bin/env python3
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen


BASE_URL = "https://data.stats.gov.cn/english/easyquery.htm"
OUTPUT_PATH = Path(__file__).resolve().parents[1] / "assets" / "data" / "china-birth-cohorts.json"


def fetch_query(indicator_code: str) -> dict:
    params = {
        "m": "QueryData",
        "dbcode": "hgnd",
        "rowcode": "zb",
        "colcode": "sj",
        "wds": "[]",
        "dfwds": json.dumps(
            [
                {"wdcode": "zb", "valuecode": indicator_code},
                {"wdcode": "sj", "valuecode": "1949-2025"},
            ],
            ensure_ascii=False,
        ),
    }
    url = f"{BASE_URL}?{urlencode(params)}"
    with urlopen(url) as response:
        return json.load(response)["returndata"]


def extract_series(payload: dict, series_code: str) -> dict[int, float]:
    values: dict[int, float] = {}
    for node in payload["datanodes"]:
        wd_values = {item["wdcode"]: item["valuecode"] for item in node["wds"]}
        if wd_values.get("zb") != series_code:
            continue
        values[int(wd_values["sj"])] = float(node["data"]["data"])
    return values


def cohort_sum(births_by_year: dict[int, float], year: int, age_start: int, age_end: int) -> float | None:
    lower_year = year - age_end
    upper_year = year - age_start
    years = list(range(lower_year, upper_year + 1))
    if not years:
        return None
    if any(item not in births_by_year for item in years):
        return None
    return round(sum(births_by_year[item] for item in years), 1)


def retirement_sum(births_by_year: dict[int, float], year: int, min_source_year: int) -> float | None:
    upper_year = year - 60
    if upper_year < min_source_year:
        return None
    years = list(range(min_source_year, upper_year + 1))
    if any(item not in births_by_year for item in years):
        return None
    return round(sum(births_by_year[item] for item in years), 1)


def retirement_sum_adjusted(births_by_year: dict[int, float], year: int, min_source_year: int) -> float | None:
    upper_year = year - 60
    if upper_year < min_source_year:
        return None

    total = 0.0
    has_any = False
    for birth_year in range(min_source_year, upper_year + 1):
        age = year - birth_year
        if birth_year not in births_by_year:
            return None
        has_any = True
        if 60 <= age <= 69:
            survival = 0.88
        elif 70 <= age <= 79:
            survival = 0.68
        else:
            survival = 0.38
        total += births_by_year[birth_year] * survival

    if not has_any:
        return None
    return round(total, 1)


def main() -> None:
    population_payload = fetch_query("A0301")
    birth_rate_payload = fetch_query("A0302")
    graduate_payload = fetch_query("A0M09")

    population_total = extract_series(population_payload, "A030101")
    birth_rate = extract_series(birth_rate_payload, "A030201")
    higher_education_graduates = extract_series(graduate_payload, "A0M0901")

    source_years = sorted(set(population_total) & set(birth_rate))
    min_source_year = min(source_years)

    births_by_year: dict[int, float] = {}
    birth_series = []
    for year in source_years:
        previous_population = population_total.get(year - 1, population_total[year])
        average_population = (previous_population + population_total[year]) / 2
        births_wan = round(average_population * birth_rate[year] / 1000, 1)
        births_by_year[year] = births_wan
        birth_series.append(
            {
                "year": year,
                "populationWan": round(population_total[year], 1),
                "birthRatePerThousand": round(birth_rate[year], 2),
                "birthsWan": births_wan,
            }
        )

    birth_series_last_50 = [item for item in birth_series if 1976 <= item["year"] <= 2025]

    cohort_series = []
    for year in range(2009, 2046):
        cohort_series.append(
            {
                "year": year,
                "preschoolWan": cohort_sum(births_by_year, year, 0, 5),
                "primaryWan": cohort_sum(births_by_year, year, 6, 11),
                "juniorWan": cohort_sum(births_by_year, year, 12, 14),
                "seniorWan": cohort_sum(births_by_year, year, 15, 17),
                "k12Wan": None,
                "collegeWan": cohort_sum(births_by_year, year, 18, 22),
                "age22Wan": round(births_by_year[year - 22], 1) if (year - 22) in births_by_year else None,
                "graduatesWan": round(higher_education_graduates[year], 1) if year in higher_education_graduates else None,
                "workforceWan": cohort_sum(births_by_year, year, 22, 59),
                "silverWan": retirement_sum(births_by_year, year, min_source_year),
                "silverAdjustedWan": retirement_sum_adjusted(births_by_year, year, min_source_year),
            }
        )

    for item in cohort_series:
        components = [item["primaryWan"], item["juniorWan"], item["seniorWan"]]
        if all(value is not None for value in components):
            item["k12Wan"] = round(sum(components), 1)
        age_22 = item.get("age22Wan")
        graduates = item.get("graduatesWan")
        if age_22 not in (None, 0) and graduates is not None:
            item["graduateConversionRate"] = round((graduates / age_22) * 100, 1)
        else:
            item["graduateConversionRate"] = None

    payload = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "source": {
            "name": "National Bureau of Statistics of China - National Data",
            "url": BASE_URL,
            "database": "hgnd",
            "indicators": {
                "populationTotal": "A030101",
                "birthRate": "A030201",
            },
        },
        "notes": [
            "所有数值单位均为万人。",
            "出生人口由国家统计局年末总人口与人口出生率按年均人口近似推算。",
            "上图展示 1976-2025 近 50 年出生人口。",
            "下图展示 2009-2045 的 cohort 推算结果，只使用 1949-2025 的真实出生数据。",
            "不同年龄段的最远可完整推算年份不同：学龄前到 2025、小学到 2031、初中到 2037、高中到 2040、大学生到 2043、职场和银发可到 2045。",
            "退休/银发人群统一按 60 岁及以上口径处理，未按性别法定退休年龄拆分。",
            "银发简化生存率模式采用分段近似：60-69岁按88%，70-79岁按68%，80岁及以上按38%。",
            "高校毕业生采用国家统计局教育口径：普通高等学校毕业生。",
            "毕业转化率=高校毕业生/22岁cohort，仅用于趋势参考，不代表真实升学路径转化统计。",
        ],
        "ageBands": [
            {"key": "preschoolWan", "label": "学龄前儿童", "ageRange": "0-5"},
            {"key": "primaryWan", "label": "小学", "ageRange": "6-11"},
            {"key": "juniorWan", "label": "初中", "ageRange": "12-14"},
            {"key": "seniorWan", "label": "高中", "ageRange": "15-17"},
            {"key": "k12Wan", "label": "K12", "ageRange": "6-17"},
            {"key": "collegeWan", "label": "大学生", "ageRange": "18-22"},
            {"key": "age22Wan", "label": "22岁 cohort", "ageRange": "22"},
            {"key": "graduatesWan", "label": "高校毕业生", "ageRange": "official"},
            {"key": "graduateConversionRate", "label": "毕业转化率", "ageRange": "ratio"},
            {"key": "workforceWan", "label": "职场人群", "ageRange": "22-59"},
            {"key": "silverWan", "label": "退休/银发", "ageRange": "60+"},
        ],
        "birthSeries": birth_series,
        "birthSeriesLast50": birth_series_last_50,
        "cohortSeries": cohort_series,
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
