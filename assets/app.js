/* 데이터랩 관측소 — 화면 조립
   차트는 전부 손으로 그린 SVG입니다. 외부 차트 라이브러리를 쓰지 않으므로
   오프라인에서도 열리고, 눈금과 색을 계기판 톤에 정확히 맞출 수 있습니다. */

const HOT = "#e8453c";   // 상승 · 과열
const COLD = "#3e86d6";  // 하락 · 공포
const BRASS = "#c9a227";
const RULE = "#24313c";
const MUTED = "#748795";

// 대분류 표시 순서 (없는 섹터는 이 뒤에 자동으로 붙음)
const SECTOR_ORDER = [
  "반도체", "AI·데이터센터", "에너지·전력", "모빌리티",
  "방산", "조선·해운", "건설", "헬스케어", "소비재",
];

const $ = (id) => document.getElementById(id);

/* ── 도구 ─────────────────────────────────────────── */

function esc(text) {
  return String(text).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]
  ));
}

function signed(value, digits = 1) {
  if (value === null || value === undefined) return "—";
  const n = Number(value);
  return (n > 0 ? "+" : "") + n.toFixed(digits) + "%";
}

function toneOf(value, threshold = 0.5) {
  if (value === null || value === undefined) return "is-flat";
  if (value > threshold) return "is-hot";
  if (value < -threshold) return "is-cold";
  return "is-flat";
}

function shortDate(iso) {
  const [y, m, d] = iso.split("-");
  return `${y.slice(2)}.${m}.${d}`;
}

/* 값 배열을 SVG path 로 바꿉니다. */
function pathFrom(values, width, height, pad = 0) {
  const hi = Math.max(...values);
  const lo = Math.min(...values);
  const span = hi - lo || 1;
  const stepX = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0;
  return values
    .map((v, i) => {
      const x = pad + i * stepX;
      const y = pad + (height - pad * 2) * (1 - (v - lo) / span);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

function sparkline(values, width = 64, height = 20, color = MUTED) {
  const d = pathFrom(values, width, height, 2);
  return `<svg class="rail__spark" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}"
    fill="none" aria-hidden="true"><path d="${d}" stroke="${color}" stroke-width="1.4"
    stroke-linejoin="round" stroke-linecap="round"/></svg>`;
}

/* 축과 눈금이 있는 큰 선형 차트. */
function lineChart(points, valueKey, color, options = {}) {
  const W = 700;
  const H = options.height || 190;
  const padL = 6;
  const padB = 22;
  const values = points.map((p) => p[valueKey]);
  const hi = options.max ?? Math.max(...values);
  const lo = options.min ?? Math.min(...values);
  const span = hi - lo || 1;
  const stepX = points.length > 1 ? (W - padL * 2) / (points.length - 1) : 0;
  const plotH = H - padB;

  const xy = (v, i) => [
    padL + i * stepX,
    (plotH - 8) * (1 - (v - lo) / span) + 6,
  ];

  const line = values
    .map((v, i) => {
      const [x, y] = xy(v, i);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");

  const last = xy(values[values.length - 1], values.length - 1);
  const first = points[0].period;
  const mid = points[Math.floor(points.length / 2)].period;
  const end = points[points.length - 1].period;

  const bands = (options.bands || [])
    .map((b) => {
      const [, yTop] = xy(b.to, 0);
      const [, yBottom] = xy(b.from, 0);
      return `<rect x="0" y="${yTop.toFixed(1)}" width="${W}" height="${Math.abs(yBottom - yTop).toFixed(1)}"
        fill="${b.color}" opacity="0.07"/>`;
    })
    .join("");

  const grid = (options.gridlines || [])
    .map((g) => {
      const [, y] = xy(g, 0);
      return `<line x1="0" y1="${y.toFixed(1)}" x2="${W}" y2="${y.toFixed(1)}"
        stroke="${RULE}" stroke-dasharray="2 4"/>
        <text x="${W - 2}" y="${(y - 4).toFixed(1)}" fill="${MUTED}" font-size="9"
        font-family="IBM Plex Mono, monospace" text-anchor="end">${g}</text>`;
    })
    .join("");

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="none"
    role="img" aria-label="${esc(options.label || "추이 그래프")}" style="display:block">
    ${bands}${grid}
    <path d="${line}" fill="none" stroke="${color}" stroke-width="1.6"
      stroke-linejoin="round" stroke-linecap="round"/>
    <circle cx="${last[0].toFixed(1)}" cy="${last[1].toFixed(1)}" r="3" fill="${color}"/>
    <text x="0" y="${H - 6}" fill="${MUTED}" font-size="10"
      font-family="IBM Plex Mono, monospace">${shortDate(first)}</text>
    <text x="${W / 2}" y="${H - 6}" fill="${MUTED}" font-size="10"
      font-family="IBM Plex Mono, monospace" text-anchor="middle">${shortDate(mid)}</text>
    <text x="${W}" y="${H - 6}" fill="${MUTED}" font-size="10"
      font-family="IBM Plex Mono, monospace" text-anchor="end">${shortDate(end)}</text>
  </svg>`;
}

/* ── 테마 관심도 ───────────────────────────────────── */

/* ISO 날짜를 days 만큼 뒤로. */
function shiftISO(iso, days) {
  const d = new Date(iso + "T00:00:00Z");
  d.setUTCDate(d.getUTCDate() - days);
  return d.toISOString().slice(0, 10);
}

/* 시계열에서 최근 days 구간만 잘라냅니다. */
function sliceWindow(series, days) {
  if (!series.length) return series;
  const target = shiftISO(series[series.length - 1].period, days);
  const cut = series.filter((p) => p.period > target);
  return cut.length >= 2 ? cut : series;
}

function renderThemes(data) {
  const themes = data.themes;
  if (!themes || themes.length === 0) {
    $("themeReadout").innerHTML =
      `<div class="readout__cell"><span class="readout__label">데이터 없음</span>
       <span class="readout__value">—</span></div>`;
    $("themeRail").innerHTML =
      `<li class="footnote">수집된 테마가 없습니다. 키워드 설정을 확인하세요.</li>`;
    return;
  }

  const windows = data.windows || [{ key: "1y", days: 365, label: "1년" }];
  const daysOf = (key) => (windows.find((w) => w.key === key) || windows[0]).days;
  let current = data.default_window || windows[0].key;

  // 기간 버튼
  $("themeWindows").innerHTML = windows
    .map(
      (w) => `<button class="winbtn${w.key === current ? " is-active" : ""}" type="button"
        data-win="${w.key}" aria-pressed="${w.key === current}">${esc(w.label)}</button>`
    )
    .join("");

  function draw(winKey) {
    current = winKey;
    const days = daysOf(winKey);
    const stat = (t) => t.windows[winKey] || {};
    const chg = (t) => stat(t).change;

    const ranked = [...themes].sort(
      (a, b) => (chg(a) === null) - (chg(b) === null) || (chg(b) ?? 0) - (chg(a) ?? 0)
    );
    const rising = ranked.filter((t) => (chg(t) ?? 0) > 0).length;
    const falling = ranked.filter((t) => (chg(t) ?? 0) < 0).length;
    const hottest = ranked[0];

    $("themeReadout").innerHTML = [
      ["관측 테마", `${themes.length}`, ""],
      ["관심 상승", `${rising}`, "is-hot"],
      ["관심 하락", `${falling}`, "is-cold"],
      ["최고 상승", signed(chg(hottest)), toneOf(chg(hottest))],
    ]
      .map(
        ([label, value, tone]) => `<div class="readout__cell">
          <span class="readout__label">${label}</span>
          <span class="readout__value ${tone}">${value}</span>
        </div>`
      )
      .join("");

    const widest = Math.max(...ranked.map((t) => Math.abs(chg(t) ?? 0)), 1);
    const now = Date.now();
    const isNew = (t) =>
      t.first_seen && now - Date.parse(t.first_seen + "T00:00:00Z") <= 7 * 864e5;

    const rowHTML = (theme) => {
      const change = chg(theme);
      const tone = toneOf(change);
      const pct = (Math.abs(change ?? 0) / widest) * 50;
      const dir = (change ?? 0) >= 0 ? "hot" : "cold";
      const color = (change ?? 0) >= 0 ? HOT : COLD;
      const values = sliceWindow(theme.series, days).map((p) => p.ratio);
      const badge = isNew(theme) ? `<span class="rail__new">NEW</span>` : "";

      return `<li class="rail__item">
        <button class="rail__row" type="button" aria-expanded="false" data-name="${esc(theme.name)}">
          <span class="rail__name">${esc(theme.name)}${badge}
            <span class="rail__keywords">${esc(theme.keywords.join(" · "))}</span>
          </span>
          ${sparkline(values, 64, 20, color)}
          <span class="rail__bar">
            <span class="rail__fill rail__fill--${dir}" style="width:${pct.toFixed(1)}%"></span>
          </span>
          <span class="rail__change ${tone}">${signed(change)}</span>
        </button>
      </li>`;
    };

    // 대분류로 묶어서 렌더 — 섹터는 고정 순서, 섹터 안은 변화율 정렬(ranked 순서 유지)
    const buckets = new Map();
    ranked.forEach((t) => {
      const s = t.sector || "기타";
      (buckets.get(s) || buckets.set(s, []).get(s)).push(t);
    });
    const order = [...SECTOR_ORDER, ...buckets.keys()];
    const done = new Set();
    let html = "";
    for (const s of order) {
      if (done.has(s) || !buckets.has(s)) continue;
      done.add(s);
      html += `<li class="rail__sector">${esc(s)}</li>` + buckets.get(s).map(rowHTML).join("");
    }
    $("themeRail").innerHTML = html;
  }

  draw(current);

  $("themeWindows").addEventListener("click", (event) => {
    const btn = event.target.closest(".winbtn");
    if (!btn) return;
    [...$("themeWindows").children].forEach((b) => {
      const on = b === btn;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-pressed", String(on));
    });
    draw(btn.dataset.win);
  });

  $("themeRail").addEventListener("click", (event) => {
    const row = event.target.closest(".rail__row");
    if (!row) return;
    const theme = themes.find((t) => t.name === row.dataset.name);
    toggleTheme(row, theme, current, daysOf(current), windows);
  });
}

function toggleTheme(row, theme, winKey, days, windows) {
  const item = row.parentElement;
  const open = row.getAttribute("aria-expanded") === "true";
  const existing = item.querySelector(".rail__detail");

  if (open) {
    row.setAttribute("aria-expanded", "false");
    if (existing) existing.remove();
    return;
  }

  row.setAttribute("aria-expanded", "true");
  const stat = theme.windows[winKey] || {};
  const label = (windows.find((w) => w.key === winKey) || {}).label || "";
  const color = (stat.change ?? 0) >= 0 ? HOT : COLD;
  const sliced = sliceWindow(theme.series, days);
  const detail = document.createElement("div");
  detail.className = "rail__detail";
  detail.innerHTML =
    lineChart(sliced, "ratio", color, {
      height: 170,
      label: `${theme.name} ${label} 검색 관심도 추이`,
    }) +
    `<p class="rail__stats">
      <span>현재 <b>${theme.current.toFixed(1)}</b></span>
      <span>${label} 최고 <b>${(stat.peak ?? 0).toFixed(1)}</b></span>
      <span>${label} 백분위 <b>${(stat.percentile ?? 0).toFixed(0)}</b></span>
      <span>${label} 변화 <b>${signed(stat.change)}</b></span>
    </p>`;
  item.appendChild(detail);
}

/* ── 공포 · 탐욕 ───────────────────────────────────── */

function gaugeScale(score) {
  const W = 700;
  const H = 62;
  const barY = 20;
  const barH = 10;
  const x = (score / 100) * W;

  const ticks = [0, 25, 50, 75, 100]
    .map((t) => {
      const tx = Math.min(W - 0.5, Math.max(0.5, (t / 100) * W));
      const anchor = t === 0 ? "start" : t === 100 ? "end" : "middle";
      return `<line x1="${tx}" y1="${barY + barH + 3}" x2="${tx}" y2="${barY + barH + 9}"
          stroke="${BRASS}" stroke-width="1"/>
        <text x="${tx}" y="${H - 4}" fill="${MUTED}" font-size="10"
          font-family="IBM Plex Mono, monospace" text-anchor="${anchor}">${t}</text>`;
    })
    .join("");

  return `<svg viewBox="0 0 ${W} ${H}" width="100%" height="${H}" preserveAspectRatio="none"
    role="img" aria-label="공포 탐욕 지수 ${score}" style="display:block">
    <defs>
      <linearGradient id="moodGrad" x1="0" x2="1">
        <stop offset="0%" stop-color="${COLD}"/>
        <stop offset="50%" stop-color="#3f5163"/>
        <stop offset="100%" stop-color="${HOT}"/>
      </linearGradient>
    </defs>
    <rect x="0" y="${barY}" width="${W}" height="${barH}" fill="url(#moodGrad)" opacity="0.55"/>
    ${ticks}
    <g class="gauge__needle" style="transform:translateX(${x.toFixed(1)}px)">
      <polygon points="-6,${barY - 12} 6,${barY - 12} 0,${barY - 2}" fill="${BRASS}"/>
      <line x1="0" y1="${barY - 2}" x2="0" y2="${barY + barH + 2}" stroke="${BRASS}" stroke-width="2"/>
    </g>
  </svg>`;
}

function renderMood(data) {
  const tone = data.score >= 60 ? HOT : data.score <= 40 ? COLD : BRASS;

  $("gauge").innerHTML = `
    <div class="gauge__score" style="color:${tone}">${data.score.toFixed(1)}</div>
    <p class="gauge__label" style="color:${tone}">${esc(data.label)}</p>
    <p class="gauge__deltas">1주 전 ${data.score_week_ago ?? "—"} · 1개월 전 ${data.score_month_ago ?? "—"}</p>
    <div class="gauge__scale">${gaugeScale(data.score)}</div>`;

  $("moodChart").innerHTML = lineChart(data.series, "value", BRASS, {
    height: 190,
    min: 0,
    max: 100,
    gridlines: [25, 50, 75],
    bands: [
      { from: 75, to: 100, color: HOT },
      { from: 0, to: 25, color: COLD },
    ],
    label: "공포 탐욕 지수 1년 추이",
  });

  const list = (items) =>
    items
      .map(
        (item) => `<li>
          <span>${esc(item.name)}</span>
          <span class="signals__value ${Math.abs(item.deviation) < 5 ? "is-quiet" : ""}">${signed(item.deviation, 0)}</span>
        </li>`
      )
      .join("");

  $("greedList").innerHTML = list(data.greed);
  $("fearList").innerHTML = list(data.fear);
}

/* ── 탭 ────────────────────────────────────────────── */

function wireTabs() {
  const tabs = [...document.querySelectorAll(".tab")];
  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((other) => {
        const active = other === tab;
        other.classList.toggle("is-active", active);
        other.setAttribute("aria-selected", String(active));
        $(other.getAttribute("aria-controls")).hidden = !active;
      });
    });
  });
}

/* ── 시작 ──────────────────────────────────────────── */

async function load(name) {
  const response = await fetch(`data/${name}.json?v=${Date.now()}`);
  if (!response.ok) throw new Error(`${name}.json 을 불러오지 못했습니다 (${response.status})`);
  return response.json();
}

async function start() {
  wireTabs();
  try {
    const [themes, mood] = await Promise.all([load("themes"), load("sentiment")]);

    renderThemes(themes);
    renderMood(mood);

    const stamp = themes.generated_at.replace("T", " ").slice(0, 16);
    $("stamp").textContent = `갱신 ${stamp} KST · 기준 ${themes.start_date} ~ ${themes.end_date}`;

    if (themes.sample || mood.sample) $("sampleNote").hidden = false;
  } catch (error) {
    $("stamp").textContent = error.message;
    $("themeReadout").innerHTML =
      `<div class="readout__cell"><span class="readout__label">데이터 없음</span>
       <span class="readout__value">—</span></div>`;
    $("panel-themes").insertAdjacentHTML(
      "beforeend",
      `<p class="footnote">먼저 <code>python tools/make_sample.py</code> 로 샘플을 만들거나,
       <code>python -m collector</code> 로 실제 데이터를 수집하세요.</p>`
    );
  }
}

start();
