/* XAUUSD Bot — unified control center.
   Tabs: Overview · Performance · Optimize · Deploy.
   Data: /api/performance (results), /api/overview (live status),
         /api/reoptimize* + /api/proposal + /api/apply (controls). */

"use strict";

let PERF = null;     // performance data (variants, master_table, meta)
let OV = null;       // overview / live status
let optPoll = null;  // re-optimize polling timer
const charts = {};

const WINDOW_LABELS = { oos: "Out-of-sample (2025+)", full: "Full history (2022+)", walkforward: "Walk-forward OOS" };
const perfState = { variant: null, window: "walkforward", filter: "all", sortKey: "entry_time", sortDir: 1 };

/* ───────── helpers ───────── */
const $ = (id) => document.getElementById(id);
function css(n) { return getComputedStyle(document.documentElement).getPropertyValue(n).trim(); }
function palette() {
  return { text: css("--text"), muted: css("--muted"), border: css("--border"),
    gold: css("--gold"), green: css("--green"), red: css("--red"), panel2: css("--panel-2") };
}
function fmt(v, d = 2) {
  if (v === null || v === undefined) return "∞";
  return Number(v).toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });
}
function makeChart(id) {
  const el = $(id); if (!el) return null;
  if (charts[id]) charts[id].dispose();
  charts[id] = echarts.init(el, null, { renderer: "canvas" });
  return charts[id];
}
async function getJSON(url) { return (await fetch(url, { cache: "no-store" })).json(); }
async function postJSON(url, body) {
  const r = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}) });
  return r.json();
}

/* ───────── tab switching ───────── */
function switchTab(name) {
  if (location.hash !== "#" + name) location.hash = name;
  document.querySelectorAll(".tabs button").forEach((b) => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab-panel").forEach((p) => p.classList.toggle("active", p.id === "tab-" + name));
  if (name === "overview") renderOverview();
  if (name === "performance") renderPerformance();
  if (name === "optimize") renderOptimize();
  if (name === "deploy") renderDeploy();
  setTimeout(() => Object.values(charts).forEach((c) => c && c.resize()), 50);
}

/* ───────── shared equity chart ───────── */
function renderEquityInto(elId, equity) {
  const p = palette(); const chart = makeChart(elId); if (!chart) return;
  chart.setOption({
    tooltip: { trigger: "axis", backgroundColor: p.panel2, borderColor: p.border,
      textStyle: { color: p.text, fontSize: 12 }, valueFormatter: (v) => fmt(v, 1) + " pts" },
    grid: [{ left: 56, right: 20, top: 24, height: "52%" }, { left: 56, right: 20, top: "72%", height: "20%" }],
    xAxis: [{ type: "time", gridIndex: 0, axisLabel: { show: false }, axisLine: { lineStyle: { color: p.border } }, splitLine: { show: false } },
      { type: "time", gridIndex: 1, axisLabel: { color: p.muted, fontSize: 11 }, axisLine: { lineStyle: { color: p.border } }, splitLine: { show: false } }],
    yAxis: [{ type: "value", gridIndex: 0, name: "equity (pts)", nameTextStyle: { color: p.muted, fontSize: 11 },
        axisLabel: { color: p.muted, fontSize: 11 }, splitLine: { lineStyle: { color: p.border, opacity: 0.6 } } },
      { type: "value", gridIndex: 1, inverse: true, name: "drawdown", nameTextStyle: { color: p.muted, fontSize: 11 },
        axisLabel: { color: p.muted, fontSize: 11 }, splitLine: { show: false } }],
    series: [
      { name: "Equity", type: "line", xAxisIndex: 0, yAxisIndex: 0, showSymbol: false,
        lineStyle: { color: p.gold, width: 2 },
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [{ offset: 0, color: p.gold + "55" }, { offset: 1, color: p.gold + "05" }]) },
        data: equity.map((d) => [d.t, d.cum]) },
      { name: "Drawdown", type: "line", xAxisIndex: 1, yAxisIndex: 1, showSymbol: false,
        lineStyle: { color: p.red, width: 1.5 }, areaStyle: { color: p.red + "33" },
        data: equity.map((d) => [d.t, d.dd]) },
    ],
  });
}

function kpiCard(label, value, cls, sub) {
  return `<div class="kpi"><div class="kpi-label">${label}</div>
    <div class="kpi-value ${cls || ""}">${value}</div><div class="kpi-sub">${sub || ""}</div></div>`;
}

/* ───────── OVERVIEW ───────── */
function regimeVariant() {
  return (PERF.variants || []).find((v) => v.key.includes("regime"));
}
function renderOverview() {
  if (!OV || !PERF) return;
  const gate = PERF.meta.gate;
  const chips = [
    `<div class="status-chip gold"><span class="lbl">Strategy</span><b>${OV.active_strategy}</b></div>`,
    `<div class="status-chip ${OV.override_active ? "green" : ""}"><span class="lbl">Params</span><b>${OV.override_active ? "re-optimized (override)" : "default"}</b></div>`,
    OV.data_range ? `<div class="status-chip"><span class="lbl">Data</span><b>${OV.data_range.start} → ${OV.data_range.end}</b></div>` : "",
    `<div class="status-chip"><span class="lbl">Re-opt</span><b>${OV.reoptimize.running ? "running…" : OV.reoptimize.proposal_ready ? "proposal ready" : "idle"}</b></div>`,
  ];
  $("ov-status").innerHTML = chips.join("");

  const m = OV.headline_metrics;
  if (m) {
    const pf = m.profit_factor;
    $("ov-kpi").innerHTML = [
      kpiCard("Profit factor", fmt(pf, 2), pf >= gate.profit_factor_min ? "good" : "bad", "walk-forward OOS"),
      kpiCard("Win rate", fmt(m["win_rate_%"], 1) + "%", "", `${m.trade_count} trades`),
      kpiCard("Expectancy", fmt(m.expectancy_pts, 2), m.expectancy_pts > 0 ? "good" : "bad", "pts / trade"),
      kpiCard("Sharpe", fmt(m.sharpe, 2), m.sharpe > 0 ? "good" : "bad", ""),
      kpiCard("Total profit", fmt(m.total_profit_pts, 0), m.total_profit_pts > 0 ? "good" : "bad", "points"),
      kpiCard("Max drawdown", fmt(m.max_dd_pts, 0), "", "points"),
    ].join("");
  }
  const rv = regimeVariant();
  if (rv) renderEquityInto("ov-equity", rv.windows.walkforward.equity);
}

/* ───────── PERFORMANCE ───────── */
function currentVariant() { return PERF.variants.find((v) => v.key === perfState.variant); }
function currentWindow() { return currentVariant().windows[perfState.window]; }

function renderPerformance() {
  if (!perfState.variant) perfState.variant = PERF.variants[0].key;
  renderPerfControls();
  renderPerfViews();
  renderComparison();
}
function renderPerfControls() {
  const pills = $("variant-pills");
  pills.innerHTML = PERF.variants.map((v) =>
    `<button data-variant="${v.key}" class="${v.key === perfState.variant ? "active" : ""}">${v.label}</button>`).join("");
  pills.querySelectorAll("button").forEach((b) => b.onclick = () => {
    perfState.variant = b.dataset.variant; renderPerfControls(); renderPerfViews();
  });
  $("variant-desc").textContent = currentVariant().desc;
  renderWindowToggle();
}
function renderWindowToggle() {
  const wins = Object.keys(currentVariant().windows);
  if (!wins.includes(perfState.window)) perfState.window = wins[0];
  const tog = $("window-toggle");
  tog.innerHTML = wins.map((w) => `<button data-window="${w}" class="${w === perfState.window ? "active" : ""}">${WINDOW_LABELS[w] || w}</button>`).join("");
  tog.querySelectorAll("button").forEach((b) => b.onclick = () => { perfState.window = b.dataset.window; renderWindowToggle(); renderPerfViews(); });
}
function renderMcNote() {
  const v = currentVariant(), el = $("mc-note"), mc = v.monte_carlo;
  if (v.walkforward && mc && mc.valid) {
    const b = mc.bootstrap;
    el.innerHTML = `Monte Carlo (1,000 resamples): worst-case PF (p5) <b>${b.profit_factor.p5}</b> · expectancy p5 <b>${b.expectancy_pts.p5}</b> pts · median PF ${b.profit_factor.p50} · p95 drawdown ${b.max_dd_pts.p95} pts`;
    el.style.display = "block";
  } else el.style.display = "none";
}
function renderPerfViews() {
  $("variant-desc").textContent = currentVariant().desc;
  renderMcNote(); renderKPIs();
  renderEquityInto("chart-equity", currentWindow().equity);
  renderMonthly(); renderHist(); renderDonut(); renderTrades();
}
function renderKPIs() {
  const m = currentWindow().metrics, gate = PERF.meta.gate, grid = $("kpi-grid");
  if (!m.trade_count) { grid.innerHTML = `<div class="kpi"><div class="kpi-label">No trades</div></div>`; return; }
  const pf = m.profit_factor;
  grid.innerHTML = [
    kpiCard("Trades", m.trade_count, "", `gate ≥ ${gate.min_trades}`),
    kpiCard("Win rate", fmt(m["win_rate_%"], 1) + "%", "", ""),
    kpiCard("Expectancy", fmt(m.expectancy_pts, 3) + " pts", m.expectancy_pts > 0 ? "good" : "bad", "gate > 0"),
    kpiCard("Profit factor", fmt(pf, 3), pf === null || pf >= gate.profit_factor_min ? "good" : "bad", `gate ≥ ${gate.profit_factor_min}`),
    kpiCard("Total profit", fmt(m.total_profit_pts, 1) + " pts", m.total_profit_pts > 0 ? "good" : "bad", ""),
    kpiCard("Max drawdown", fmt(m.max_dd_pts, 1) + " pts", "", ""),
    kpiCard("Avg win / loss", `${fmt(m.avg_win_pts, 1)} / ${fmt(m.avg_loss_pts, 1)}`, "", ""),
    kpiCard("Sharpe", fmt(m.sharpe, 2), m.sharpe > 0 ? "good" : "bad", ""),
  ].join("");
}
function renderMonthly() {
  const p = palette(), monthly = currentWindow().monthly, chart = makeChart("chart-monthly"); if (!chart) return;
  chart.setOption({
    tooltip: { trigger: "axis", backgroundColor: p.panel2, borderColor: p.border, textStyle: { color: p.text }, valueFormatter: (v) => fmt(v, 1) + " pts" },
    grid: { left: 48, right: 12, top: 16, bottom: 40 },
    xAxis: { type: "category", data: monthly.map((d) => d.month), axisLine: { lineStyle: { color: p.border } }, axisLabel: { color: p.muted, fontSize: 10, rotate: monthly.length > 14 ? 45 : 0 } },
    yAxis: { type: "value", axisLabel: { color: p.muted, fontSize: 11 }, splitLine: { lineStyle: { color: p.border, opacity: 0.6 } } },
    series: [{ type: "bar", data: monthly.map((d) => ({ value: d.pnl, itemStyle: { color: d.pnl >= 0 ? p.green : p.red, borderRadius: [3, 3, 0, 0] } })) }],
  });
}
function renderHist() {
  const p = palette(), profits = currentWindow().trades.map((t) => t.profit_pts).filter((v) => v !== null), chart = makeChart("chart-hist");
  if (!chart) return; if (!profits.length) { chart.clear(); return; }
  const lo = Math.min(...profits), hi = Math.max(...profits), n = Math.min(24, Math.max(8, Math.round(Math.sqrt(profits.length) * 2))), w = (hi - lo) / n || 1;
  const bins = Array.from({ length: n }, (_, i) => ({ x0: lo + i * w, x1: lo + (i + 1) * w, n: 0 }));
  profits.forEach((v) => { bins[Math.min(n - 1, Math.floor((v - lo) / w))].n += 1; });
  chart.setOption({
    tooltip: { trigger: "item", backgroundColor: p.panel2, borderColor: p.border, textStyle: { color: p.text }, formatter: (d) => `${d.name}<br/>${d.value} trade(s)` },
    grid: { left: 40, right: 12, top: 16, bottom: 40 },
    xAxis: { type: "category", data: bins.map((b) => `${fmt(b.x0, 0)}…${fmt(b.x1, 0)}`), axisLine: { lineStyle: { color: p.border } }, axisLabel: { color: p.muted, fontSize: 10, rotate: 45 } },
    yAxis: { type: "value", minInterval: 1, axisLabel: { color: p.muted, fontSize: 11 }, splitLine: { lineStyle: { color: p.border, opacity: 0.6 } } },
    series: [{ type: "bar", barCategoryGap: "12%", data: bins.map((b) => ({ value: b.n, itemStyle: { color: b.x1 <= 0 ? p.red : b.x0 >= 0 ? p.green : p.muted, borderRadius: [3, 3, 0, 0] } })) }],
  });
}
function renderDonut() {
  const p = palette(), trades = currentWindow().trades, wins = trades.filter((t) => t.profit_pts > 0).length, losses = trades.length - wins, chart = makeChart("chart-donut"); if (!chart) return;
  chart.setOption({
    tooltip: { trigger: "item", backgroundColor: p.panel2, borderColor: p.border, textStyle: { color: p.text } },
    legend: { bottom: 0, textStyle: { color: p.muted, fontSize: 12 } },
    series: [{ type: "pie", radius: ["52%", "76%"], center: ["50%", "44%"],
      label: { show: true, position: "center", formatter: () => `${trades.length ? ((wins / trades.length) * 100).toFixed(1) : 0}%\nwin rate`, color: p.text, fontSize: 18, fontWeight: 700, lineHeight: 22 },
      itemStyle: { borderColor: css("--panel"), borderWidth: 3 },
      data: [{ name: `Wins (${wins})`, value: wins, itemStyle: { color: p.green } }, { name: `Losses (${losses})`, value: losses, itemStyle: { color: p.red } }] }],
  });
}
function filteredTrades() {
  let out = currentWindow().trades.slice(); const f = perfState.filter;
  if (f === "wins") out = out.filter((t) => t.profit_pts > 0);
  else if (f === "losses") out = out.filter((t) => t.profit_pts <= 0);
  else if (f === "buy" || f === "sell") out = out.filter((t) => t.direction === f);
  const k = perfState.sortKey, dir = perfState.sortDir;
  out.sort((a, b) => { const av = a[k], bv = b[k]; if (av === bv) return 0; if (av === null) return 1; if (bv === null) return -1; return (av > bv ? 1 : -1) * dir; });
  return out;
}
function renderTrades() {
  const rows = filteredTrades(), tbody = document.querySelector("#trade-table tbody"), total = currentWindow().trades.length;
  tbody.innerHTML = rows.map((t) => {
    const c = t.profit_pts > 0 ? "pos" : "neg";
    return `<tr><td>${t.entry_time.replace("T", " ").slice(0, 16)}</td>
      <td><span class="dir-badge ${t.direction}">${t.direction}</span></td>
      <td class="num">${fmt(t.entry)}</td><td class="num">${fmt(t.exit)}</td>
      <td class="num">${fmt(t.sl)}</td><td class="num">${fmt(t.tp)}</td>
      <td>${t.exit_time ? t.exit_time.replace("T", " ").slice(0, 16) : "—"}</td>
      <td class="num ${c}">${t.profit_pts > 0 ? "+" : ""}${fmt(t.profit_pts)}${t.partial ? " ◐" : ""}</td></tr>`;
  }).join("");
  $("trade-count-foot").textContent = `${rows.length} of ${total} trades · ◐ = partial · sorted by ${perfState.sortKey} ${perfState.sortDir > 0 ? "↑" : "↓"}`;
}
function cmpBar(id, rows, key, color, ref) {
  const p = palette(), chart = makeChart(id); if (!chart) return;
  chart.setOption({
    tooltip: { trigger: "item", backgroundColor: p.panel2, borderColor: p.border, textStyle: { color: p.text } },
    grid: { left: 150, right: 36, top: 8, bottom: 24 },
    xAxis: { type: "value", axisLabel: { color: p.muted, fontSize: 10 }, splitLine: { lineStyle: { color: p.border, opacity: 0.6 } } },
    yAxis: { type: "category", inverse: true, data: rows.map((r) => r.name), axisLine: { lineStyle: { color: p.border } }, axisLabel: { color: p.muted, fontSize: 10 } },
    series: [{ type: "bar", barCategoryGap: "28%",
      data: rows.map((r) => ({ value: r[key], itemStyle: { color: /WALK|BEST/.test(r.verdict) ? p.gold : color, opacity: /REJECTED|FAIL/.test(r.verdict) ? 0.45 : 1, borderRadius: [0, 3, 3, 0] } })),
      markLine: ref ? { symbol: "none", lineStyle: { color: p.muted, type: "dashed" }, label: { color: p.muted, fontSize: 10, formatter: ref.label }, data: [{ xAxis: ref.value }] } : undefined,
      label: { show: true, position: "right", color: p.muted, fontSize: 10, formatter: (d) => fmt(d.value, key === "oos_trades" ? 0 : key === "oos_wr" ? 1 : 2) } }],
  });
}
function renderComparison() {
  const rows = PERF.master_table, p = palette();
  cmpBar("chart-cmp-wr", rows, "oos_wr", p.gold, { value: 50, label: "50%" });
  cmpBar("chart-cmp-exp", rows, "oos_exp", p.green, { value: 0, label: "0" });
  cmpBar("chart-cmp-pf", rows, "oos_pf", "#60a5fa", { value: PERF.meta.gate.profit_factor_min, label: `gate ${PERF.meta.gate.profit_factor_min}` });
  const tbody = document.querySelector("#master-table tbody");
  tbody.innerHTML = rows.map((r) => {
    const cls = r.verdict.toLowerCase().replace(/[^a-z]/g, "-");
    return `<tr class="${/WALK|BEST/.test(r.verdict) ? "row-highlight" : ""}">
      <td><strong>${r.name}</strong></td><td style="white-space:normal">${r.desc}</td>
      <td class="num">${r.oos_trades}</td><td class="num">${fmt(r.oos_wr, 1)}%</td>
      <td class="num ${r.oos_exp > 0 ? "pos" : "neg"}">${r.oos_exp > 0 ? "+" : ""}${fmt(r.oos_exp, 3)}</td>
      <td class="num">${fmt(r.oos_pf, 3)}</td><td class="num">${fmt(r.oos_dd, 1)}</td>
      <td><span class="verdict-badge ${cls}">${r.verdict}</span></td></tr>`;
  }).join("");
}

/* ───────── OPTIMIZE ───────── */
function renderOptimize() {
  $("btn-reoptimize").onclick = runReoptimize;
  $("btn-apply").onclick = applyProposal;
  pollOptStatus();      // reflect any in-progress / finished run
  loadProposal();
}
async function runReoptimize() {
  const download = $("opt-download").checked;
  const r = await postJSON("/api/reoptimize", { download });
  if (!r.ok) { $("opt-running-hint").textContent = r.error === "already running" ? "already running…" : "failed to start"; return; }
  $("opt-progress").style.display = "block";
  $("btn-reoptimize").disabled = true;
  startOptPolling();
}
function startOptPolling() { if (optPoll) clearInterval(optPoll); optPoll = setInterval(pollOptStatus, 2000); }
async function pollOptStatus() {
  const st = await getJSON("/api/reoptimize/status");
  if (!st || st.stage === "idle") return;
  const running = st.running;
  $("opt-progress").style.display = "block";
  $("opt-bar").style.width = (st.pct || 0) + "%";
  $("opt-stage").textContent = `${st.stage} — ${st.message || ""}`;
  $("btn-reoptimize").disabled = running;
  $("opt-running-hint").textContent = running ? "running…" : "";
  if (!running) { if (optPoll) { clearInterval(optPoll); optPoll = null; } loadProposal(); }
}
async function loadProposal() {
  const p = await getJSON("/api/proposal");
  if (!p || !p.new_params) { $("proposal-card").style.display = "none"; return; }
  $("proposal-card").style.display = "block";
  const rec = p.recommend;
  $("proposal-verdict").innerHTML = `<span class="verdict-badge ${rec ? "walk-fwd" : "rejected"}">${rec ? "✓ RECOMMENDED" : "✗ NOT recommended"}</span>`;
  const m = p.walkforward_metrics || {};
  $("proposal-wf").innerHTML = [
    kpiCard("WF Profit factor", fmt(m.profit_factor, 2), (m.profit_factor || 0) > 1.2 ? "good" : "bad", "walk-forward check"),
    kpiCard("WF Win rate", fmt(m["win_rate_%"], 1) + "%", "", `${m.trade_count || 0} trades`),
    kpiCard("WF Expectancy", fmt(m.expectancy_pts, 2), (m.expectancy_pts || 0) > 0 ? "good" : "bad", "pts/trade"),
    kpiCard("WF Total", fmt(m.total_profit_pts, 0), (m.total_profit_pts || 0) > 0 ? "good" : "bad", "points"),
  ].join("");
  const cur = p.current_params || {}, nw = p.new_params || {};
  const keys = Object.keys(nw);
  document.querySelector("#proposal-table tbody").innerHTML = keys.map((k) => {
    const changed = String(cur[k]) !== String(nw[k]);
    return `<tr class="${changed ? "row-highlight" : ""}"><td>${k}</td><td class="num">${cur[k]}</td>
      <td class="num">${nw[k]}${changed ? " ◀" : ""}</td></tr>`;
  }).join("");
  $("proposal-card").dataset.optWindow = (p.optimize_window || []).join(" → ");
}
async function applyProposal() {
  $("btn-apply").disabled = true; $("apply-result").textContent = "applying…";
  const r = await postJSON("/api/apply", {});
  $("apply-result").textContent = r.ok ? "✓ applied — restart bot.py to pick up" : "✗ " + (r.error || r.stderr || "failed");
  $("btn-apply").disabled = false;
  if (r.ok) { OV = await getJSON("/api/overview"); }
}

/* ───────── DEPLOY ───────── */
function renderDeploy() {
  if (!OV) return;
  const p = OV.params;
  const rows = Object.entries(p).map(([k, v]) => `<span class="k">${k}</span><span class="v">${v}</span>`).join("");
  $("deploy-config").innerHTML = `
    <div class="kv-grid">
      <span class="k">ACTIVE_STRATEGY</span><span class="v">${OV.active_strategy}</span>
      <span class="k">params source</span><span class="v">${OV.override_active ? "re-optimized override" : "config.py default"}</span>
      ${rows}
    </div>`;
  const cmds = [
    ["Run the bot (Windows + MT5)", ".venv/bin/python3 bot.py"],
    ["Backtest current strategy", "see README / walkforward.py"],
    ["Walk-forward validation", ".venv/bin/python3 backtest/walkforward.py --family regime_switch --trials 40"],
    ["Re-optimize params (CLI)", ".venv/bin/python3 backtest/reoptimize.py"],
    ["Apply latest proposal (CLI)", ".venv/bin/python3 backtest/reoptimize.py --apply"],
    ["Install monthly schedule", ".venv/bin/python3 backtest/reoptimize.py --install-cron"],
  ];
  $("deploy-cmds").innerHTML = cmds.map(([label, cmd]) => `<div class="cmd"><span>${label}</span><code>${cmd}</code></div>`).join("");
}

/* ───────── init ───────── */
function bindStatic() {
  document.querySelectorAll(".tabs button").forEach((b) => b.onclick = () => switchTab(b.dataset.tab));
  document.querySelectorAll("#trade-filters button").forEach((b) => b.onclick = () => {
    document.querySelectorAll("#trade-filters button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active"); perfState.filter = b.dataset.filter; renderTrades();
  });
  document.querySelectorAll("#trade-table thead th").forEach((th) => th.onclick = () => {
    const k = th.dataset.sort; if (perfState.sortKey === k) perfState.sortDir *= -1; else { perfState.sortKey = k; perfState.sortDir = 1; } renderTrades();
  });
  $("theme-toggle").onclick = () => {
    const r = document.documentElement; r.dataset.theme = r.dataset.theme === "dark" ? "light" : "dark";
    const active = document.querySelector(".tabs button.active").dataset.tab; switchTab(active);
  };
  window.addEventListener("resize", () => Object.values(charts).forEach((c) => c && c.resize()));
}

const VALID_TABS = ["overview", "performance", "optimize", "deploy"];
async function init() {
  bindStatic();
  window.addEventListener("hashchange", () => {
    const t = location.hash.slice(1);
    if (VALID_TABS.includes(t)) switchTab(t);
  });
  [PERF, OV] = await Promise.all([getJSON("/api/performance"), getJSON("/api/overview")]);
  $("footer-meta").textContent = `${PERF.meta.symbol} · ${PERF.meta.data_source}`;
  const start = VALID_TABS.includes(location.hash.slice(1)) ? location.hash.slice(1) : "overview";
  switchTab(start);
}

init().catch((e) => { $("ov-status").innerHTML = `<div class="status-chip">Failed to load: ${e}. Run <code>python backtest/dashboard_server.py</code></div>`; console.error(e); });
