# 데이터랩 관측소

네이버 데이터랩 검색어 트렌드로 **테마별 관심도**와 **투자심리 온도**를 한 페이지에서 봅니다.
Python 으로 수집해 JSON 으로 떨구고, 정적 페이지가 그걸 읽는 구조입니다.

```
GitHub Actions (매일 18:30 KST)
   └─ python -m collector
        └─ data/themes.json, data/sentiment.json
             └─ index.html (GitHub Pages)
```

## 화면

| 탭 | 보는 것 |
|---|---|
| 테마 관심도 | 12개 테마의 3년 검색 관심도. 4주 변화율로 정렬, 행을 열면 전체 추이 |
| 공포 · 탐욕 | 탐욕/공포 키워드군의 표준화 격차로 만든 0~100 지수 |

## 준비

### 1. API 키 발급

**NAVER API HUB** 에서 신청합니다. 예전 창구인 developers.naver.com 에서
이쪽으로 이관되는 중이라, 새로 시작한다면 API HUB 쪽이 맞습니다.

- https://www.ncloud.com/product/applicationService/naverApiHub

이 프로젝트는 하루 5콜(테마 3 + 공포·탐욕 2)이면 끝납니다.
API HUB 무료 한도는 앱당 하루 1,000콜이라 근처도 가지 않습니다.

> **발급처에 따라 인증 방식이 다릅니다.** 키 값은 어느 쪽이든
> `NAVER_CLIENT_ID` / `NAVER_CLIENT_SECRET` 에 넣고, 발급처만
> `NAVER_API_STYLE` 로 지정하면 엔드포인트와 헤더가 함께 맞춰집니다.
>
> - `NAVER_API_STYLE=legacy` (기본): developers.naver.com 키.
>   헤더 `X-Naver-Client-Id` / `X-Naver-Client-Secret`.
> - `NAVER_API_STYLE=apihub`: NAVER API HUB(ncloud) 키.
>   헤더 `X-NCP-APIGW-API-KEY-ID` / `X-NCP-APIGW-API-KEY`,
>   엔드포인트 `naverapihub.apigw.ntruss.com/search-trend/v1/search`.
>
> 엔드포인트만 따로 바꿀 일이 있으면 `NAVER_DATALAB_ENDPOINT` 로 덮어씁니다.

### 2. GitHub Secrets 등록

리포지토리 → Settings → Secrets and variables → Actions 에 두 개를 넣습니다.

- `NAVER_CLIENT_ID`
- `NAVER_CLIENT_SECRET`

### 3. Pages 켜기

Settings → Pages → Source 를 `Deploy from a branch` / `main` / `/ (root)` 로 지정합니다.

## 로컬에서 돌리기

```bash
pip install -r requirements.txt

export NAVER_CLIENT_ID=발급받은_아이디
export NAVER_CLIENT_SECRET=발급받은_시크릿

python -m collector              # 전부
python -m collector themes       # 테마만
python -m collector sentiment    # 공포·탐욕만

python -m http.server 8000       # http://localhost:8000
```

키가 아직 없다면 샘플 데이터로 화면부터 볼 수 있습니다.

```bash
python tools/make_sample.py
```

샘플일 때는 페이지 상단에 안내 띠가 뜹니다.

## 설계에서 신경 쓴 두 가지

### 상대 지수를 같은 자로 재는 문제

데이터랩은 **한 번의 요청 안에서** 최댓값을 100으로 잡습니다.
키워드 그룹은 요청당 5개까지만 되는데, 테마가 12개면 요청을 세 번 나눠야 하고,
그러면 세 결과가 서로 다른 자로 잰 값이 됩니다. 그대로 합치면 순위가 엉망이 됩니다.

그래서 **앵커 키워드**(기본값 `코스피`)를 매 요청에 함께 넣습니다.
앵커의 실제 검색량은 요청이 달라져도 같으니, 앵커 시계열의 평균이 일치하도록
각 요청 결과에 배율 하나를 곱하면 전부 같은 축에 올라갑니다.
`collector/datalab.py` 의 `fetch()` 가 이 일을 합니다.

같은 이유로 **매번 전체 기간을 다시 받아 덮어씁니다.** 매일 하루치만 이어 붙이면
기준점이 어긋나 그래프가 뒤틀립니다.

### 브라우저에서 직접 못 부르는 문제

데이터랩은 Client Secret 을 헤더에 요구하고 CORS 도 막혀 있습니다.
정적 페이지가 네이버를 직접 호출할 수 없다는 뜻입니다.
수집은 반드시 Actions 쪽에서 돌고, 페이지는 만들어진 JSON 만 읽습니다.
`index.html` 어디에도 키가 들어가지 않습니다.

## 키워드 바꾸기

`config/themes.yaml` 과 `config/sentiment.yaml` 만 고치면 됩니다.

```yaml
groups:
  - groupName: 화면에_표시될_이름
    keywords: [실제, 검색, 키워드]      # 그룹당 최대 20개
```

한 그룹 안의 키워드는 검색량이 합산됩니다. 같은 대상을 가리키는 표기 변형
(`HBM`, `고대역폭메모리`)을 한 그룹에 묶고, 다른 대상은 그룹을 나누세요.

**앵커 고를 때:** 검색량이 극단적으로 크거나 작은 키워드는 피하세요.
너무 크면 나머지 값이 전부 0에 가깝게 눌리고, 너무 작으면 배율 계산이 불안정해집니다.
관측 대상들과 비슷한 규모가 좋습니다.

## 공포·탐욕 지수를 어떻게 계산하나

1. 탐욕 3개 그룹, 공포 3개 그룹의 일간 시계열을 각각 z-score 로 표준화
2. `50 + 민감도 × (탐욕 평균 z − 공포 평균 z)`, 0~100 으로 자름
3. 7일 이동평균

표준화를 거치는 이유는 두 키워드군의 절대 검색량 자체가 다르기 때문입니다.
그냥 빼면 항상 한쪽이 이깁니다. 각자의 평소 수준에서 얼마나 벗어났는지를 봐야 합니다.

민감도와 이동평균 기간은 `config/sentiment.yaml` 에서 조정합니다.

## 알아둘 한계

- 검색량은 **관심의 크기**지 방향이 아닙니다. 급등할 때도 급락할 때도 검색은 늘어납니다.
- 데이터랩은 절대 검색량을 주지 않습니다. 여기 숫자는 전부 상대 지수입니다.
- 공포·탐욕 지수는 검증되지 않은 실험적 보조지표입니다. 단독 매매 근거로 쓰지 마세요.
- 키워드 선정이 결과를 좌우합니다. 신조어가 자리 잡기 전에는 검색량이 잡히지 않습니다.

## 라이선스

개인 용도. 데이터 출처는 네이버 데이터랩입니다.
