"""공포·탐욕 보조지표 수집기.

탐욕 키워드군과 공포 키워드군을 각각 표준화(z-score)한 뒤 그 차이로 지수를 만듭니다.
표준화를 거치는 이유: 두 키워드군은 절대 검색량 자체가 다르기 때문에,
그대로 빼면 항상 한쪽이 이깁니다. 각자의 평소 수준 대비 얼마나 튀었는지를 봐야 합니다.

지수는 0~100이고 50이 중립입니다. 검증된 지표가 아니라 참고용입니다.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import yaml

from . import datalab

KST = timezone(timedelta(hours=9))


def _zscore(values: list[float]) -> list[float]:
    n = len(values)
    if n == 0:
        return []
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    sd = var ** 0.5
    if sd == 0:
        return [0.0] * n
    return [(v - mean) / sd for v in values]


def _moving_average(values: list[float], window: int) -> list[float]:
    if window <= 1:
        return values
    out = []
    for i in range(len(values)):
        chunk = values[max(0, i - window + 1) : i + 1]
        out.append(sum(chunk) / len(chunk))
    return out


def _label(score: float) -> str:
    if score >= 75:
        return "극단적 탐욕"
    if score >= 60:
        return "탐욕"
    if score > 40:
        return "중립"
    if score > 25:
        return "공포"
    return "극단적 공포"


def build(config_path: str = "config/sentiment.yaml") -> dict:
    with open(config_path, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)

    start, end = datalab.date_range(cfg["lookback_days"])
    time_unit = cfg.get("time_unit", "date")
    print(f"공포·탐욕 수집: {start} ~ {end} ({time_unit})")

    groups = cfg["greed"] + cfg["fear"]
    merged = datalab.fetch(
        groups=groups,
        anchor=cfg["anchor"],
        start_date=start,
        end_date=end,
        time_unit=time_unit,
    )

    greed_names = [g["groupName"] for g in cfg["greed"]]
    fear_names = [g["groupName"] for g in cfg["fear"]]

    present = [n for n in greed_names + fear_names if merged.get(n)]
    if not present:
        raise RuntimeError("수집된 시계열이 없습니다. 키워드 설정을 확인하세요.")

    # 그룹마다 날짜(period)가 다를 수 있으므로(데이터랩이 저볼륨 구간을 빼고 줌)
    # 인덱스가 아니라 period 로 맞춥니다. 그룹별 z-score 는 자기 시계열 위에서
    # 계산한 뒤 {period: z} 로 되돌려, 같은 날짜끼리만 더하고 뺍니다.
    z_by_period: dict[str, dict[str, float]] = {}
    for name in present:
        points = merged[name]
        zs = _zscore([p["ratio"] for p in points])
        z_by_period[name] = {points[i]["period"]: zs[i] for i in range(len(points))}

    # 전체 그룹의 날짜 합집합(오름차순)이 지수의 시간축입니다.
    periods = sorted({p["period"] for n in present for p in merged[n]})

    def side_mean(names: list[str], period: str) -> float:
        vals = [z_by_period[n][period] for n in names
                if n in z_by_period and period in z_by_period[n]]
        return sum(vals) / len(vals) if vals else 0.0

    sensitivity = cfg.get("sensitivity", 12)
    raw = []
    for period in periods:
        gap = side_mean(greed_names, period) - side_mean(fear_names, period)
        raw.append(max(0.0, min(100.0, 50 + sensitivity * gap)))

    smoothed = _moving_average(raw, cfg.get("smooth_days", 7))
    index_series = [
        {"period": periods[i], "value": round(smoothed[i], 1)} for i in range(len(periods))
    ]

    latest = index_series[-1]["value"]

    def component(name: str) -> dict:
        points = merged[name]
        last_period = points[-1]["period"]
        # 최근 7일 / 최근 90일을 날짜 창으로 자릅니다(인덱스 개수가 아니라).
        recent_from = datalab.shift_iso(last_period, 7)
        base_from = datalab.shift_iso(last_period, 90)
        recent = [p["ratio"] for p in points if p["period"] > recent_from]
        baseline = [p["ratio"] for p in points if p["period"] > base_from]
        base_mean = sum(baseline) / len(baseline) if baseline else 0.0
        recent_mean = sum(recent) / len(recent) if recent else 0.0
        deviation = (recent_mean / base_mean - 1) * 100 if base_mean > 0 else 0.0
        return {
            "name": name,
            "deviation": round(deviation, 1),
            "z": round(z_by_period[name].get(last_period, 0.0), 2),
            "series": [p for p in points if p["period"] > base_from],
        }

    def ago(days: int) -> float | None:
        target = datalab.shift_iso(index_series[-1]["period"], days)
        ref = datalab.value_on_or_before(index_series[:-1], target)
        return ref["value"] if ref else None

    return {
        "sample": False,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "start_date": start,
        "end_date": end,
        "score": latest,
        "label": _label(latest),
        "score_week_ago": ago(7),
        "score_month_ago": ago(30),
        "greed": [component(n) for n in greed_names if n in z_by_period],
        "fear": [component(n) for n in fear_names if n in z_by_period],
        "series": index_series,
    }


def write(out_path: str = "data/sentiment.json") -> None:
    payload = build()
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    print(f"저장 완료: {out_path} (지수 {payload['score']}, {payload['label']})")
