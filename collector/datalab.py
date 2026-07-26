"""네이버 데이터랩 검색어 트렌드 클라이언트.

데이터랩은 "한 번의 요청 안에서" 최댓값을 100으로 잡아 나머지를 상대화합니다.
그래서 키워드 그룹이 5개를 넘어 요청을 나누면, 각 요청의 결과가 서로 다른 자로
잰 값이 되어 그대로 합치면 안 됩니다.

해결: 같은 앵커 그룹을 모든 요청에 함께 넣고, 앵커 시계열의 평균이 같아지도록
각 요청 결과에 배율을 곱해 되돌립니다. 앵커는 요청이 달라져도 실제 검색량이
동일하므로, 배율 하나로 전체 요청을 같은 축에 올릴 수 있습니다.
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from datetime import date, timedelta

# 인증 방식 두 가지를 지원합니다.
#   legacy : developers.naver.com 에서 발급한 키. 헤더 X-Naver-Client-Id/Secret.
#   apihub : NAVER API HUB(ncloud) 에서 발급한 키. 헤더 X-NCP-APIGW-API-KEY-ID/KEY.
# 어느 쪽이든 키 값 자체는 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 환경변수에 넣습니다.
# 발급처만 NAVER_API_STYLE 로 지정하면 엔드포인트와 헤더가 함께 바뀝니다.
_STYLES = {
    "legacy": {
        "endpoint": "https://openapi.naver.com/v1/datalab/search",
        "id_header": "X-Naver-Client-Id",
        "secret_header": "X-Naver-Client-Secret",
    },
    "apihub": {
        "endpoint": "https://naverapihub.apigw.ntruss.com/search-trend/v1/search",
        "id_header": "X-NCP-APIGW-API-KEY-ID",
        "secret_header": "X-NCP-APIGW-API-KEY",
    },
}

STYLE = os.environ.get("NAVER_API_STYLE", "legacy").strip().lower()
if STYLE not in _STYLES:
    STYLE = "legacy"

# 엔드포인트만 따로 덮어쓰고 싶으면 NAVER_DATALAB_ENDPOINT 로. (헤더는 STYLE 을 따름)
ENDPOINT = os.environ.get("NAVER_DATALAB_ENDPOINT") or _STYLES[STYLE]["endpoint"]
ID_HEADER = _STYLES[STYLE]["id_header"]
SECRET_HEADER = _STYLES[STYLE]["secret_header"]

MAX_GROUPS_PER_CALL = 5  # 네이버 제한
RETRIES = 3


class DataLabError(RuntimeError):
    pass


def _credentials() -> tuple[str, str]:
    cid = os.environ.get("NAVER_CLIENT_ID")
    secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not cid or not secret:
        raise DataLabError(
            "NAVER_CLIENT_ID 와 NAVER_CLIENT_SECRET 환경변수가 필요합니다. "
            "로컬은 .env, GitHub Actions는 리포지토리 Secrets에 넣으세요."
        )
    return cid, secret


def _post(payload: dict) -> dict:
    cid, secret = _credentials()
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        ENDPOINT,
        data=body,
        headers={
            ID_HEADER: cid,
            SECRET_HEADER: secret,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    last = None
    for attempt in range(RETRIES):
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", "replace")
            last = DataLabError(f"HTTP {exc.code}: {detail}")
            # 400 잘못된 요청, 401/403 인증 실패는 재시도해도 소용없습니다.
            # 429(한도 초과)와 5xx는 잠깐 뒤 재시도합니다.
            if exc.code in (400, 401, 403):
                raise last from exc
        except urllib.error.URLError as exc:
            last = DataLabError(f"연결 실패: {exc}")
        time.sleep(2 ** attempt)
    raise last or DataLabError("알 수 없는 오류")


def _mean(series: list[dict]) -> float:
    values = [p["ratio"] for p in series]
    return sum(values) / len(values) if values else 0.0


def date_range(lookback_days: int) -> tuple[str, str]:
    end = date.today()
    start = end - timedelta(days=lookback_days)
    return start.isoformat(), end.isoformat()


def _drop_last_bucket(series: dict[str, list[dict]]) -> None:
    """가장 최근 버킷(period)을 모든 그룹에서 제거합니다. 제자리 수정.

    주간/월간은 진행 중인 마지막 버킷이 아직 안 끝나 값이 찌그러지고,
    일간은 오늘치가 아직 하루가 안 지나 부분값입니다. 그대로 두면
    '현재값'과 변화율이 전부 왜곡되므로 최신 버킷 하나를 잘라냅니다.
    (일요일에 돌려 마지막 주가 이미 완결이어도 한 점만 손해라 무방합니다.)
    """
    latest = max(
        (p["period"] for points in series.values() for p in points),
        default=None,
    )
    if latest is None:
        return
    for name in series:
        series[name] = [p for p in series[name] if p["period"] != latest]


def fetch(
    groups: list[dict],
    anchor: dict,
    start_date: str,
    end_date: str,
    time_unit: str = "week",
    trim_incomplete: bool = True,
) -> dict[str, list[dict]]:
    """키워드 그룹 전체를 하나의 공통 축으로 맞춰 반환합니다.

    반환 형태: {그룹명: [{"period": "2026-07-20", "ratio": 41.3}, ...]}
    각 그룹의 시계열은 period 오름차순으로 정렬돼 있습니다. 데이터랩이
    검색량이 미미한 구간을 응답에서 빼는 경우가 있어 그룹마다 길이·날짜가
    다를 수 있습니다. 소비 측은 인덱스가 아니라 period(날짜)로 맞추세요.
    """
    if not groups:
        return {}

    per_call = MAX_GROUPS_PER_CALL - 1  # 앵커 자리 하나 확보
    chunks = [groups[i : i + per_call] for i in range(0, len(groups), per_call)]

    anchor_name = anchor["groupName"]
    reference_mean: float | None = None
    merged: dict[str, list[dict]] = {}

    for index, chunk in enumerate(chunks):
        payload = {
            "startDate": start_date,
            "endDate": end_date,
            "timeUnit": time_unit,
            "keywordGroups": [anchor] + chunk,
        }
        response = _post(payload)
        series = {r["title"]: r["data"] for r in response.get("results", [])}

        # 진행 중인 마지막 버킷 제거 — 앵커 평균을 내기 전에 해야
        # 배율이 온전한 구간만으로 계산됩니다.
        if trim_incomplete:
            _drop_last_bucket(series)

        anchor_series = series.pop(anchor_name, [])
        anchor_mean = _mean(anchor_series)

        if reference_mean is None:
            reference_mean = anchor_mean
            scale = 1.0
        elif anchor_mean > 0:
            scale = reference_mean / anchor_mean
        else:
            print(f"  ! 앵커 검색량이 0입니다 (호출 {index + 1}). 보정 없이 진행합니다.")
            scale = 1.0

        for name, points in series.items():
            merged[name] = sorted(
                (
                    {"period": p["period"], "ratio": round(p["ratio"] * scale, 4)}
                    for p in points
                ),
                key=lambda p: p["period"],
            )

        print(f"  · 호출 {index + 1}/{len(chunks)} 완료 (배율 {scale:.4f})")
        time.sleep(0.3)  # 예의상 간격

    return merged


def value_on_or_before(points: list[dict], target_iso: str) -> dict | None:
    """target_iso(포함) 이하 날짜 중 가장 최근 지점. period 오름차순 가정."""
    chosen = None
    for p in points:
        if p["period"] <= target_iso:
            chosen = p
        else:
            break
    return chosen


def shift_iso(iso: str, days: int) -> str:
    """ISO 날짜를 days 만큼 뒤로 민 ISO 문자열."""
    return (date.fromisoformat(iso) - timedelta(days=days)).isoformat()


def rescale_to_100(merged: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """전체 시계열의 최댓값이 100이 되도록 다시 맞춥니다. 표시용."""
    peak = max(
        (p["ratio"] for points in merged.values() for p in points),
        default=0.0,
    )
    if peak <= 0:
        return merged
    factor = 100.0 / peak
    return {
        name: [{"period": p["period"], "ratio": round(p["ratio"] * factor, 2)} for p in points]
        for name, points in merged.items()
    }
