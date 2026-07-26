"""아직 수집 전에도 페이지가 렌더되도록 샘플 데이터를 만듭니다.

    python tools/make_sample.py

만들어진 JSON에는 "sample": true 가 들어가고, 페이지 상단에 샘플 안내가 뜹니다.
실제 수집(python -m collector)을 한 번 돌리면 덮어써집니다.
"""

from __future__ import annotations

import json
import math
import random
from datetime import date, datetime, timedelta, timezone

import yaml

KST = timezone(timedelta(hours=9))
random.seed(20260726)


def wave(n: int, drift: float, noise: float, phase: float) -> list[float]:
    out = []
    level = 30.0
    for i in range(n):
        level += drift + math.sin((i / n) * math.pi * 2 + phase) * 1.4
        level = max(3.0, level + random.gauss(0, noise))
        out.append(level)
    return out


def make_themes() -> dict:
    cfg = yaml.safe_load(open("config/themes.yaml", encoding="utf-8"))
    weeks = 156
    end = date.today()
    periods = [(end - timedelta(weeks=weeks - 1 - i)).isoformat() for i in range(weeks)]

    raw = {}
    for idx, group in enumerate(cfg["groups"]):
        drift = random.uniform(-0.12, 0.35)
        raw[group["groupName"]] = wave(weeks, drift, 2.2, idx * 0.7)

    peak = max(v for series in raw.values() for v in series)
    factor = 100 / peak

    themes = []
    for group in cfg["groups"]:
        name = group["groupName"]
        values = [round(v * factor, 2) for v in raw[name]]
        points = [{"period": periods[i], "ratio": values[i]} for i in range(weeks)]
        ordered = sorted(values)
        below = sum(1 for v in ordered if v <= values[-1])
        themes.append(
            {
                "name": name,
                "keywords": group["keywords"],
                "current": values[-1],
                "peak": max(values),
                "percentile": round(below / len(values) * 100, 1),
                "change_short": round((values[-1] / values[-5] - 1) * 100, 1),
                "change_long": round((values[-1] / values[-13] - 1) * 100, 1),
                "series": points,
            }
        )

    themes.sort(key=lambda t: -t["change_short"])
    return {
        "sample": True,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "start_date": periods[0],
        "end_date": periods[-1],
        "time_unit": "week",
        "span_short_label": "4주",
        "span_long_label": "12주",
        "themes": themes,
    }


def make_sentiment() -> dict:
    cfg = yaml.safe_load(open("config/sentiment.yaml", encoding="utf-8"))
    days = 365
    end = date.today()
    periods = [(end - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]

    def component(group, phase, drift):
        values = wave(days, drift, 3.0, phase)
        peak = max(values)
        values = [round(v / peak * 100, 2) for v in values]
        points = [{"period": periods[i], "ratio": values[i]} for i in range(days)]
        recent = values[-7:]
        baseline = values[-90:]
        base = sum(baseline) / len(baseline)
        dev = (sum(recent) / len(recent) / base - 1) * 100
        return {
            "name": group["groupName"],
            "deviation": round(dev, 1),
            "z": round(random.uniform(-1.6, 1.6), 2),
            "series": points[-90:],
        }

    greed = [component(g, i * 1.1, 0.06) for i, g in enumerate(cfg["greed"])]
    fear = [component(g, 3 + i * 1.1, -0.03) for i, g in enumerate(cfg["fear"])]

    base = wave(days, 0.0, 1.1, 0.4)
    peak, low = max(base), min(base)
    series = [
        {
            "period": periods[i],
            "value": round(12 + (base[i] - low) / (peak - low) * 72, 1),
        }
        for i in range(days)
    ]

    score = series[-1]["value"]
    label = (
        "극단적 탐욕" if score >= 75
        else "탐욕" if score >= 60
        else "중립" if score > 40
        else "공포" if score > 25
        else "극단적 공포"
    )

    return {
        "sample": True,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "start_date": periods[0],
        "end_date": periods[-1],
        "score": score,
        "label": label,
        "score_week_ago": series[-8]["value"],
        "score_month_ago": series[-31]["value"],
        "greed": greed,
        "fear": fear,
        "series": series,
    }


if __name__ == "__main__":
    for name, payload in (("themes", make_themes()), ("sentiment", make_sentiment())):
        path = f"data/{name}.json"
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
        print(f"샘플 생성: {path}")
