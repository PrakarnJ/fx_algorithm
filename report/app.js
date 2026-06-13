/* XAUUSD bot performance dashboard.
   Loads data.json (produced by backtest/export_report.py) and renders
   KPIs, charts (ECharts) and tables for the selected variant + window. */

"use strict";

const state = {
  variant: null,        // variant key
  window: "oos",        // "oos" | "full" | "walkforward"
  filter: "all",        // trade table filter
  sortKey: "entry_time",
  sortDir: 1,
};

const WINDOW_LABELS = {
  oos: "Out-of-sample (2025+)",
  full: "Full history (2022+)",
  walkforward: "Walk-forward OOS",
};

let DATA = null;
const charts = {};      // id -> echarts instance

/* ───────────────────────── helpers ───────────────────────── */

function css(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function palette() {
  return {
    text: css("--text"),
    muted: css("--muted"),
    border: css("--border"),
    gold: css("--gold"),
    green: css("--green"),
    red: css("--red"),
    panel2: css("--panel-2"),
  };
}

function fmt(v, digits = 2) {
  if (v === null || v === undefined) return "∞";
  return Number(v).toLocaleString("en-US", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
}

function currentVariant() {
  return DATA.variants.find((v) => v.key === state.variant);
}

function currentWindow() {
  return currentVariant().windows[state.window];
}

function makeChart(id) {
  const el = document.getElementById(id);
  if (charts[id]) charts[id].dispose();
  charts[id] = echarts.init(el, null, { renderer: "canvas" });
  return charts[id];
}

function baseTooltip(p) {
  return {
    trigger: "axis",
    backgroundColor: p.panel2,
    borderColor: p.border,
    textStyle: { color: p.text, fontSize: 12 },
  };
}

/* ───────────────────────── KPI cards ───────────────────────── */

function gateChip(pass, label) {
  if (pass === null) return `<span class="gate-chip na">${label}</span>`;
  return `<span class="gate-chip ${pass ? "pass" : "fail"}">${pass ? "✓" : "✗"} ${label}</span>`;
}

function renderKPIs() {
  const m = currentWindow().metrics;
  const gate = DATA.meta.gate;
  const grid = document.getElementById("kpi-grid");

  if (!m.trade_count) {
    grid.innerHTML = `<div class="kpi"><div class="kpi-label">No trades</div></div>`;
    return;
  }

  const pf = m.profit_factor;
  const cards = [
    { label: "Trades", value: m.trade_count, digits: 0,
      sub: gateChip(m.trade_count >= gate.min_trades, `gate ≥ ${gate.min_trades}`) },
    { label: "Win rate", value: m["win_rate_%"], digits: 1, suffix: "%", sub: "" },
    { label: "Expectancy", value: m.expectancy_pts, digits: 3, suffix: " pts",
      cls: m.expectancy_pts > 0 ? "good" : "bad",
      sub: gateChip(m.expectancy_pts > gate.expectancy_min, "gate > 0") },
    { label: "Profit factor", value: pf, digits: 3,
      cls: pf === null || pf >= gate.profit_factor_min ? "good" : "bad",
      sub: gateChip(pf === null || pf >= gate.profit_factor_min, `gate ≥ ${gate.profit_factor_min}`) },
    { label: "Total profit", value: m.total_profit_pts, digits: 1, suffix: " pts",
      cls: m.total_profit_pts > 0 ? "good" : "bad", sub: "" },
    { label: "Max drawdown", value: m.max_dd_pts, digits: 1, suffix: " pts", sub: "" },
    { label: "Avg win / loss", value: null, digits: 0,
      html: `${fmt(m.avg_win_pts, 1)} / ${fmt(m.avg_loss_pts, 1)}`, sub: "" },
    { label: "Sharpe", value: m.sharpe, digits: 2,
      cls: m.sharpe > 0 ? "good" : "bad", sub: "" },
  ];

  grid.innerHTML = cards
    .map((c) => {
      const valueHtml = c.html !== undefined ? c.html : fmt(c.value, c.digits) + (c.suffix || "");
      return `<div class="kpi">
        <div class="kpi-label">${c.label}</div>
        <div class="kpi-value ${c.cls || ""}">${valueHtml}</div>
        <div class="kpi-sub">${c.sub}</div>
      </div>`;
    })
    .join("");
}

/* ───────────────────────── equity + drawdown chart ───────────────────────── */

function renderEquity() {
  const p = palette();
  const eq = currentWindow().equity;
  const chart = makeChart("chart-equity");

  chart.setOption({
    tooltip: { ...baseTooltip(p), valueFormatter: (v) => fmt(v, 1) + " pts" },
    axisPointer: { link: [{ xAxisIndex: "all" }] },
    grid: [
      { left: 56, right: 20, top: 24, height: "52%" },
      { left: 56, right: 20, top: "72%", height: "20%" },
    ],
    xAxis: [
      { type: "time", gridIndex: 0, axisLine: { lineStyle: { color: p.border } },
        axisLabel: { show: false }, splitLine: { show: false } },
      { type: "time", gridIndex: 1, axisLine: { lineStyle: { color: p.border } },
        axisLabel: { color: p.muted, fontSize: 11 }, splitLine: { show: false } },
    ],
    yAxis: [
      { type: "value", gridIndex: 0, name: "equity (pts)",
        nameTextStyle: { color: p.muted, fontSize: 11 },
        axisLabel: { color: p.muted, fontSize: 11 },
        splitLine: { lineStyle: { color: p.border, opacity: 0.6 } } },
      { type: "value", gridIndex: 1, inverse: true, name: "drawdown",
        nameTextStyle: { color: p.muted, fontSize: 11 },
        axisLabel: { color: p.muted, fontSize: 11 },
        splitLine: { show: false } },
    ],
    series: [
      {
        name: "Equity", type: "line", xAxisIndex: 0, yAxisIndex: 0,
        showSymbol: false, smooth: false, lineStyle: { color: p.gold, width: 2 },
        areaStyle: {
          color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
            { offset: 0, color: p.gold + "55" },
            { offset: 1, color: p.gold + "05" },
          ]),
        },
        data: eq.map((d) => [d.t, d.cum]),
      },
      {
        name: "Drawdown", type: "line", xAxisIndex: 1, yAxisIndex: 1,
        showSymbol: false, lineStyle: { color: p.red, width: 1.5 },
        areaStyle: { color: p.red + "33" },
        data: eq.map((d) => [d.t, d.dd]),
      },
    ],
  });
}

/* ───────────────────────── monthly P&L ───────────────────────── */

function renderMonthly() {
  const p = palette();
  const monthly = currentWindow().monthly;
  const chart = makeChart("chart-monthly");

  chart.setOption({
    tooltip: { ...baseTooltip(p), valueFormatter: (v) => fmt(v, 1) + " pts" },
    grid: { left: 48, right: 12, top: 16, bottom: 40 },
    xAxis: {
      type: "category",
      data: monthly.map((d) => d.month),
      axisLine: { lineStyle: { color: p.border } },
      axisLabel: { color: p.muted, fontSize: 10, rotate: monthly.length > 14 ? 45 : 0 },
    },
    yAxis: {
      type: "value",
      axisLabel: { color: p.muted, fontSize: 11 },
      splitLine: { lineStyle: { color: p.border, opacity: 0.6 } },
    },
    series: [{
      name: "P&L", type: "bar",
      data: monthly.map((d) => ({
        value: d.pnl,
        itemStyle: { color: d.pnl >= 0 ? p.green : p.red, borderRadius: [3, 3, 0, 0] },
      })),
    }],
  });
}

/* ───────────────────────── P&L histogram ───────────────────────── */

function renderHist() {
  const p = palette();
  const profits = currentWindow().trades.map((t) => t.profit_pts).filter((v) => v !== null);
  const chart = makeChart("chart-hist");
  if (!profits.length) { chart.clear(); return; }

  const lo = Math.min(...profits), hi = Math.max(...profits);
  const nBins = Math.min(24, Math.max(8, Math.round(Math.sqrt(profits.length) * 2)));
  const width = (hi - lo) / nBins || 1;
  const bins = Array.from({ length: nBins }, (_, i) => ({
    x0: lo + i * width, x1: lo + (i + 1) * width, n: 0,
  }));
  profits.forEach((v) => {
    const i = Math.min(nBins - 1, Math.floor((v - lo) / width));
    bins[i].n += 1;
  });

  chart.setOption({
    tooltip: {
      ...baseTooltip(p), trigger: "item",
      formatter: (d) => `${d.name}<br/>${d.value} trade(s)`,
    },
    grid: { left: 40, right: 12, top: 16, bottom: 40 },
    xAxis: {
      type: "category",
      data: bins.map((b) => `${fmt(b.x0, 0)}…${fmt(b.x1, 0)}`),
      axisLine: { lineStyle: { color: p.border } },
      axisLabel: { color: p.muted, fontSize: 10, rotate: 45 },
    },
    yAxis: {
      type: "value", minInterval: 1,
      axisLabel: { color: p.muted, fontSize: 11 },
      splitLine: { lineStyle: { color: p.border, opacity: 0.6 } },
    },
    series: [{
      type: "bar", barCategoryGap: "12%",
      data: bins.map((b) => ({
        value: b.n,
        itemStyle: {
          color: b.x1 <= 0 ? p.red : b.x0 >= 0 ? p.green : p.muted,
          borderRadius: [3, 3, 0, 0],
        },
      })),
    }],
  });
}

/* ───────────────────────── win/loss donut ───────────────────────── */

function renderDonut() {
  const p = palette();
  const trades = currentWindow().trades;
  const wins = trades.filter((t) => t.profit_pts > 0).length;
  const losses = trades.length - wins;
  const chart = makeChart("chart-donut");

  chart.setOption({
    tooltip: { ...baseTooltip(p), trigger: "item" },
    legend: { bottom: 0, textStyle: { color: p.muted, fontSize: 12 } },
    series: [{
      type: "pie",
      radius: ["52%", "76%"],
      center: ["50%", "44%"],
      label: {
        show: true, position: "center",
        formatter: () => `${trades.length ? ((wins / trades.length) * 100).toFixed(1) : 0}%\nwin rate`,
        color: p.text, fontSize: 18, fontWeight: 700, lineHeight: 22,
      },
      itemStyle: { borderColor: css("--panel"), borderWidth: 3 },
      data: [
        { name: `Wins (${wins})`, value: wins, itemStyle: { color: p.green } },
        { name: `Losses (${losses})`, value: losses, itemStyle: { color: p.red } },
      ],
    }],
  });
}

/* ───────────────────────── trade table ───────────────────────── */

function filteredTrades() {
  const trades = currentWindow().trades.slice();
  const f = state.filter;
  let out = trades;
  if (f === "wins") out = trades.filter((t) => t.profit_pts > 0);
  else if (f === "losses") out = trades.filter((t) => t.profit_pts <= 0);
  else if (f === "buy" || f === "sell") out = trades.filter((t) => t.direction === f);

  const k = state.sortKey, dir = state.sortDir;
  out.sort((a, b) => {
    const av = a[k], bv = b[k];
    if (av === bv) return 0;
    if (av === null) return 1;
    if (bv === null) return -1;
    return (av > bv ? 1 : -1) * dir;
  });
  return out;
}

function renderTrades() {
  const rows = filteredTrades();
  const tbody = document.querySelector("#trade-table tbody");
  const total = currentWindow().trades.length;

  tbody.innerHTML = rows
    .map((t) => {
      const pnlCls = t.profit_pts > 0 ? "pos" : "neg";
      return `<tr>
        <td>${t.entry_time.replace("T", " ").slice(0, 16)}</td>
        <td><span class="dir-badge ${t.direction}">${t.direction}</span></td>
        <td class="num">${fmt(t.entry)}</td>
        <td class="num">${fmt(t.exit)}</td>
        <td class="num">${fmt(t.sl)}</td>
        <td class="num">${fmt(t.tp)}</td>
        <td>${t.exit_time ? t.exit_time.replace("T", " ").slice(0, 16) : "—"}</td>
        <td class="num ${pnlCls}">${t.profit_pts > 0 ? "+" : ""}${fmt(t.profit_pts)}${t.partial ? " ◐" : ""}</td>
      </tr>`;
    })
    .join("");

  document.getElementById("trade-count-foot").textContent =
    `${rows.length} of ${total} trades shown · ◐ = partial TP filled · sorted by ` +
    `${state.sortKey} ${state.sortDir > 0 ? "↑" : "↓"}`;
}

/* ───────────────────────── comparison charts + master table ───────────────────────── */

function cmpBarChart(id, rows, key, color, refLine) {
  const p = palette();
  const chart = makeChart(id);
  chart.setOption({
    tooltip: { ...baseTooltip(p), trigger: "item" },
    grid: { left: 130, right: 30, top: 8, bottom: 24 },
    xAxis: {
      type: "value",
      axisLabel: { color: p.muted, fontSize: 10 },
      splitLine: { lineStyle: { color: p.border, opacity: 0.6 } },
    },
    yAxis: {
      type: "category",
      inverse: true,
      data: rows.map((r) => r.name),
      axisLine: { lineStyle: { color: p.border } },
      axisLabel: { color: p.muted, fontSize: 10 },
    },
    series: [{
      type: "bar",
      barCategoryGap: "28%",
      data: rows.map((r) => ({
        value: r[key],
        itemStyle: {
          color: r.verdict === "BEST" ? p.gold : color,
          opacity: r.verdict === "REJECTED" || r.verdict === "FAIL" ? 0.45 : 1,
          borderRadius: [0, 3, 3, 0],
        },
      })),
      markLine: refLine
        ? {
            symbol: "none",
            lineStyle: { color: p.muted, type: "dashed" },
            label: { color: p.muted, fontSize: 10, formatter: refLine.label },
            data: [{ xAxis: refLine.value }],
          }
        : undefined,
      label: {
        show: true, position: "right", color: p.muted, fontSize: 10,
        formatter: (d) => fmt(d.value, key === "oos_trades" ? 0 : key === "oos_wr" ? 1 : 2),
      },
    }],
  });
}

function renderComparison() {
  const rows = DATA.master_table;
  const p = palette();

  cmpBarChart("chart-cmp-wr", rows, "oos_wr", p.gold, { value: 50, label: "50%" });
  cmpBarChart("chart-cmp-exp", rows, "oos_exp", p.green, { value: 0, label: "0" });
  cmpBarChart("chart-cmp-pf", rows, "oos_pf", "#60a5fa",
    { value: DATA.meta.gate.profit_factor_min, label: `gate ${DATA.meta.gate.profit_factor_min}` });

  const tbody = document.querySelector("#master-table tbody");
  tbody.innerHTML = rows
    .map((r) => {
      const cls = r.verdict.toLowerCase();
      return `<tr class="${r.verdict === "BEST" ? "row-highlight" : ""}">
        <td><strong>${r.name}</strong></td>
        <td style="white-space:normal">${r.desc}</td>
        <td class="num">${r.oos_trades}</td>
        <td class="num">${fmt(r.oos_wr, 1)}%</td>
        <td class="num ${r.oos_exp > 0 ? "pos" : "neg"}">${r.oos_exp > 0 ? "+" : ""}${fmt(r.oos_exp, 3)}</td>
        <td class="num">${fmt(r.oos_pf, 3)}</td>
        <td class="num">${fmt(r.oos_dd, 1)}</td>
        <td><span class="verdict-badge ${cls}">${r.verdict}</span></td>
      </tr>`;
    })
    .join("");
}

/* ───────────────────────── controls ───────────────────────── */

function renderControls() {
  const pills = document.getElementById("variant-pills");
  pills.innerHTML = DATA.variants
    .map((v) => `<button data-variant="${v.key}" class="${v.key === state.variant ? "active" : ""}">${v.label}</button>`)
    .join("");
  pills.querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => {
      state.variant = b.dataset.variant;
      renderControls();
      renderVariantViews();
    })
  );

  document.getElementById("variant-desc").textContent = currentVariant().desc;
  renderWindowToggle();
}

function renderWindowToggle() {
  const wins = Object.keys(currentVariant().windows);
  if (!wins.includes(state.window)) state.window = wins[0];
  const tog = document.getElementById("window-toggle");
  tog.innerHTML = wins
    .map((w) => `<button data-window="${w}" class="${w === state.window ? "active" : ""}">${WINDOW_LABELS[w] || w}</button>`)
    .join("");
  tog.querySelectorAll("button").forEach((b) =>
    b.addEventListener("click", () => {
      state.window = b.dataset.window;
      renderWindowToggle();
      renderVariantViews();
    })
  );
}

function renderMcNote() {
  const v = currentVariant();
  const el = document.getElementById("mc-note");
  if (!el) return;
  const mc = v.monte_carlo;
  if (v.walkforward && mc && mc.valid) {
    const b = mc.bootstrap;
    el.innerHTML = `Monte Carlo (1,000 resamples): worst-case PF (p5) <b>${b.profit_factor.p5}</b> · ` +
      `expectancy p5 <b>${b.expectancy_pts.p5}</b> pts · median PF ${b.profit_factor.p50} · ` +
      `p95 drawdown ${b.max_dd_pts.p95} pts`;
    el.style.display = "block";
  } else {
    el.style.display = "none";
  }
}

function renderVariantViews() {
  document.getElementById("variant-desc").textContent = currentVariant().desc;
  renderMcNote();
  renderKPIs();
  renderEquity();
  renderMonthly();
  renderHist();
  renderDonut();
  renderTrades();
}

function bindStaticControls() {
  // window toggle is rendered dynamically per variant (renderWindowToggle)
  document.querySelectorAll("#trade-filters button").forEach((b) =>
    b.addEventListener("click", () => {
      document.querySelectorAll("#trade-filters button").forEach((x) => x.classList.remove("active"));
      b.classList.add("active");
      state.filter = b.dataset.filter;
      renderTrades();
    })
  );

  document.querySelectorAll("#trade-table thead th").forEach((th) =>
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (state.sortKey === key) state.sortDir *= -1;
      else { state.sortKey = key; state.sortDir = 1; }
      renderTrades();
    })
  );

  document.getElementById("theme-toggle").addEventListener("click", () => {
    const root = document.documentElement;
    root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
    renderAllCharts();
  });

  window.addEventListener("resize", () =>
    Object.values(charts).forEach((c) => c.resize())
  );
}

function renderAllCharts() {
  renderEquity();
  renderMonthly();
  renderHist();
  renderDonut();
  renderComparison();
}

/* ───────────────────────── init ───────────────────────── */

async function init() {
  // cache-bust so a regenerated data.json is always picked up fresh
  const resp = await fetch("data.json?t=" + Date.now(), { cache: "no-store" });
  DATA = await resp.json();

  state.variant = DATA.variants[0].key;

  const gen = new Date(DATA.meta.generated_at);
  document.getElementById("generated-at").textContent =
    `${DATA.meta.symbol} · generated ${gen.toISOString().slice(0, 16).replace("T", " ")} UTC`;
  document.getElementById("footer-meta").textContent =
    `Data: ${DATA.meta.data_source} · ${DATA.meta.data_start.slice(0, 10)} → ` +
    `${DATA.meta.data_end.slice(0, 10)} · OOS from ${DATA.meta.oos_start} · ` +
    `Gate: PF ≥ ${DATA.meta.gate.profit_factor_min}, expectancy > ${DATA.meta.gate.expectancy_min}, ` +
    `≥ ${DATA.meta.gate.min_trades} trades`;

  renderControls();
  bindStaticControls();
  renderVariantViews();
  renderComparison();
}

init().catch((err) => {
  document.getElementById("kpi-grid").innerHTML =
    `<div class="kpi"><div class="kpi-label">Failed to load data.json</div>
     <div class="kpi-sub">${err}. Serve this directory over HTTP:
     <code>python -m http.server 8765 -d report</code></div></div>`;
  console.error(err);
});
