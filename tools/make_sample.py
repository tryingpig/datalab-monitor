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


def _win_stats(points, days):
    """collector.themes._window_stats 와 같은 계산(샘플용 복제)."""
    last = points[-1]
    target = (date.fromisoformat(last["period"]) - timedelta(days=days)).isoformat()
    window = [p for p in points if p["period"] > target] or points
    ref = None
    for p in points[:-1]:
        if p["period"] <= target:
            ref = p
    if ref is None and window[0]["period"] < last["period"]:
        ref = window[0]
    change = round((last["ratio"] / ref["ratio"] - 1) * 100, 1) if ref and ref["ratio"] > 0 else None
    vals = [p["ratio"] for p in window]
    below = sum(1 for v in vals if v <= last["ratio"])
    return {"change": change, "peak": round(max(vals), 2), "percentile": round(below / len(vals) * 100, 1)}


def make_themes() -> dict:
    cfg = yaml.safe_load(open("config/themes.yaml", encoding="utf-8"))
    days = cfg["lookback_days"]
    smooth = cfg.get("smooth_days", 7)
    windows = cfg["windows"]
    end = date.today()
    periods = [(end - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]

    raw = {}
    for idx, group in enumerate(cfg["groups"]):
        drift = random.uniform(-0.05, 0.12)
        raw[group["groupName"]] = wave(days, drift, 2.6, idx * 0.7)

    # 7일 이동평균
    def smoothed(vals):
        out = []
        for i in range(len(vals)):
            chunk = vals[max(0, i - smooth + 1) : i + 1]
            out.append(sum(chunk) / len(chunk))
        return out

    sm = {name: smoothed(vals) for name, vals in raw.items()}
    peak = max(v for series in sm.values() for v in series)
    factor = 100 / peak

    themes = []
    for group in cfg["groups"]:
        name = group["groupName"]
        values = [round(v * factor, 2) for v in sm[name]]
        points = [{"period": periods[i], "ratio": values[i]} for i in range(days)]
        themes.append(
            {
                "name": name,
                "keywords": group["keywords"],
                "current": values[-1],
                "windows": {w["key"]: _win_stats(points, w["days"]) for w in windows},
                "series": points,
            }
        )

    default_window = cfg.get("default_window", windows[0]["key"])
    themes.sort(key=lambda t: (t["windows"][default_window]["change"] is None,
                               -(t["windows"][default_window]["change"] or 0)))
    return {
        "sample": True,
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "start_date": periods[0],
        "end_date": periods[-1],
        "time_unit": "date",
        "windows": windows,
        "default_window": default_window,
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
