(() => {
  const root = document.getElementById("SalesRepsApp");
  if (!root) return;

  const authFetch = window.authFetch || window.fetch.bind(window);
  const bundleUrl = root.dataset.bundleUrl || "/api/salesreps/bundle";
  const exportXlsx = document.getElementById("salesrepsExportXlsx");
  const exportCsv = document.getElementById("salesrepsExportCsv");
  const drilldownTemplate = root.dataset.drilldownTemplate || "";
  const ChartLib = window.Chart;

  const NA = "N/A";
  const fmtMoney0 = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const fmtMoney2 = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtInt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
  const fmtPct = new Intl.NumberFormat(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const escapeHtml = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const state = {
    qs: "",
    page: 1,
    pageSize: 25,
    sortBy: "revenue",
    sortDir: "desc",
    search: "",
    metric: "revenue",
    topN: 10,
  };

  const charts = {};
  let currentAbort = null;
  let reqId = 0;
  let bootstrapped = false;
  let lastPayload = null;

  const emptyMessage = "No data for selected filters.";

  const metricConfig = {
    revenue: { label: "Revenue", fmt: (v) => fmtMoney0.format(num(v)), value: (r) => num(r.revenue) },
    profit: { label: "Profit", fmt: (v) => fmtMoney0.format(num(v)), value: (r) => num(r.profit) },
    margin_dollar: { label: "Margin $", fmt: (v) => fmtMoney0.format(num(v)), value: (r) => num(r.profit) },
    margin_pct: { label: "Margin %", fmt: (v) => `${fmtPct.format(num(v))}%`, value: (r) => num(r.margin_pct) },
    orders: { label: "Orders", fmt: (v) => fmtInt.format(num(v)), value: (r) => num(r.orders) },
    customers: { label: "Customers", fmt: (v) => fmtInt.format(num(v)), value: (r) => num(r.customers) },
    weight_lb: { label: "Weight (lb)", fmt: (v) => fmtInt.format(num(v)), value: (r) => num(r.weight_lb) },
  };

  const num = (v, fallback = 0) => {
    const n = Number(v);
    return Number.isFinite(n) ? n : fallback;
  };

  const opt = (v) => {
    if (v === null || v === undefined || v === "") return null;
    const n = Number(v);
    return Number.isFinite(n) ? n : null;
  };

  const pct = (v, fromShare = false) => {
    const n = opt(v);
    if (n === null) return NA;
    const val = fromShare && n <= 1.01 ? n * 100 : n;
    return `${fmtPct.format(val)}%`;
  };

  const money = (v, compact = true) => {
    const n = opt(v);
    if (n === null) return NA;
    return compact ? fmtMoney0.format(n) : fmtMoney2.format(n);
  };

  const currentFilterState = () => {
    try {
      const globalState = window.getGlobalFilterState ? window.getGlobalFilterState() : {};
      if (globalState?.filters && typeof globalState.filters === "object") return globalState.filters;
    } catch (_err) {
      /* ignore */
    }
    return {};
  };

  const openUniversal = (payload, el = root) => {
    if (!payload || !window.universalDrilldown || typeof window.universalDrilldown.open !== "function") return false;
    window.universalDrilldown.open(payload, {}, el || root);
    return true;
  };

  const setDrillPayload = (el, payload) => {
    if (!el || !window.universalDrilldown || typeof window.universalDrilldown.setPayload !== "function") return;
    window.universalDrilldown.setPayload(el, payload);
  };

  const drillAttr = (payload) => {
    if (!payload) return "";
    return ` data-drilldown-payload="${escapeHtml(JSON.stringify(payload))}"`;
  };

  const salesrepPayload = (row, section, widget, metric, value, extra = {}) => {
    const repId = row?.rep_id || row?.repId || row?.key || row?.rep_name;
    if (!repId) return null;
    return {
      source_page: "salesreps",
      source_section: section,
      source_widget: widget,
      requested_target: "salesrep",
      clicked_entity_type: "salesrep",
      clicked_entity_id: String(repId),
      clicked_entity_label: row?.rep_name || row?.label || String(repId),
      clicked_metric: metric,
      clicked_metric_value: value,
      active_filter_state: currentFilterState(),
      extra,
    };
  };

  const workspacePayload = (section, widget, metric, value, extra = {}) => ({
    source_page: "salesreps",
    source_section: section,
    source_widget: widget,
    requested_target: "workspace",
    clicked_metric: metric,
    clicked_metric_value: value,
    active_filter_state: currentFilterState(),
    extra,
  });

  const isoDateLabel = (raw) => {
    if (!raw) return "--";
    const dt = new Date(raw);
    if (Number.isNaN(dt.valueOf())) return String(raw);
    return dt.toLocaleString();
  };

  const destroyChart = (key) => {
    if (charts[key]?.destroy) charts[key].destroy();
    charts[key] = null;
  };

  const resolveChartCanvas = (canvasId) => {
    const el = document.getElementById(canvasId);
    if (!el) {
      console.warn(`[salesreps] missing chart canvas: #${canvasId}`);
      return null;
    }
    if (!(el instanceof HTMLCanvasElement)) {
      console.warn(`[salesreps] invalid chart element for #${canvasId}; expected <canvas>.`);
      return null;
    }
    const ctx = el.getContext("2d");
    if (!ctx) {
      console.warn(`[salesreps] unable to get 2d context for #${canvasId}`);
      return null;
    }
    return { el, ctx };
  };

  const createChart = (key, canvasId, config) => {
    if (!ChartLib) return null;
    destroyChart(key);
    const resolved = resolveChartCanvas(canvasId);
    if (!resolved) return null;
    try {
      charts[key] = new ChartLib(resolved.ctx, config);
      return charts[key];
    } catch (err) {
      console.error(`[salesreps] chart init failed: #${canvasId}`, err);
      return null;
    }
  };

  const toggleEmpty = (canvasId, show, message = emptyMessage) => {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;
    const holder = canvas.parentElement;
    if (!holder) return;
    holder.style.position = holder.style.position || "relative";

    let emptyEl = holder.querySelector("[data-empty-state]");
    if (!emptyEl) {
      emptyEl = document.createElement("div");
      emptyEl.dataset.emptyState = "true";
      emptyEl.className = "position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center text-muted small";
      emptyEl.style.background = "rgba(255,255,255,0.85)";
      emptyEl.style.pointerEvents = "none";
      holder.appendChild(emptyEl);
    }
    emptyEl.textContent = message;
    emptyEl.classList.toggle("d-none", !show);
    canvas.classList.toggle("d-none", !!show);
  };

  const setText = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
  };

  const setDelta = (id, value, suffix = "%") => {
    const el = document.getElementById(id);
    if (!el) return;
    const n = opt(value);
    el.classList.remove("delta-up", "delta-down");
    if (n === null) {
      el.textContent = "MoM: N/A";
      return;
    }
    el.classList.add(n >= 0 ? "delta-up" : "delta-down");
    el.textContent = `MoM ${n >= 0 ? "+" : ""}${fmtPct.format(n)}${suffix}`;
  };

  const updateColumnLabels = (meta = {}) => {
    const units = meta.units_label || root.dataset.unitsLabel || "Units";
    const asp = meta.asp_label || root.dataset.aspLabel || "ASP";
    const aspLb = meta.asp_lb_label || root.dataset.aspLbLabel || "ASP / lb";
    setText("kpiUnitsLabel", units);
    setText("kpiAspLabel", asp);
    setText("kpiAspLbLabel", aspLb);
    document.querySelectorAll("[data-column-label='units']").forEach((el) => { el.textContent = units; });
    document.querySelectorAll("[data-column-label='asp']").forEach((el) => { el.textContent = asp; });
    document.querySelectorAll("[data-column-label='asp_lb']").forEach((el) => { el.textContent = aspLb; });
  };

  const baseQuery = () => {
    const params = new URLSearchParams(state.qs || "");
    params.set("page", String(state.page));
    params.set("page_size", String(state.pageSize));
    params.set("sort", state.sortBy);
    params.set("dir", state.sortDir);
    params.set("metric", state.metric);
    params.set("top_n", String(state.topN));
    if (state.search) params.set("q", state.search);
    else params.delete("q");
    return params;
  };

  const buildQueryString = () => baseQuery().toString();

  const updateExportLinks = () => {
    const exportParams = baseQuery();
    exportParams.delete("page");
    exportParams.delete("page_size");
    const qs = exportParams.toString();
    if (exportXlsx) {
      const base = exportXlsx.dataset.baseHref || exportXlsx.getAttribute("href") || root.dataset.exportXlsx || "";
      exportXlsx.dataset.baseHref = base.split("?")[0];
      exportXlsx.setAttribute("href", exportXlsx.dataset.baseHref + (qs ? `?${qs}` : ""));
    }
    if (exportCsv) {
      const base = exportCsv.dataset.baseHref || exportCsv.getAttribute("href") || root.dataset.exportCsv || "";
      exportCsv.dataset.baseHref = base.split("?")[0];
      exportCsv.setAttribute("href", exportCsv.dataset.baseHref + (qs ? `?${qs}` : ""));
    }
  };

  const rowMetricValue = (row, metric) => {
    const conf = metricConfig[metric] || metricConfig.revenue;
    return conf.value(row);
  };

  const sortedByMetric = (rows, metric) => {
    const list = Array.isArray(rows) ? [...rows] : [];
    return list.sort((a, b) => rowMetricValue(b, metric) - rowMetricValue(a, metric));
  };

  const renderExecutive = (payload = {}) => {
    const k = payload.kpis || {};
    const meta = payload.meta || {};

    setText("kpiRevenue", money(k.revenue));
    setText("kpiProfit", k.profit == null ? NA : money(k.profit));
    setText("kpiMargin", k.margin_pct == null ? NA : `${fmtPct.format(num(k.margin_pct))}%`);
    setText("kpiOrders", fmtInt.format(num(k.orders)));
    setText("kpiCustomers", fmtInt.format(num(k.customers)));
    setText("kpiWeight", fmtInt.format(num(k.weight_lb)));
    setText("kpiUnits", fmtInt.format(num(k.units)));
    setText("kpiAspLb", k.asp_lb == null ? NA : money(k.asp_lb, false));
    setText("kpiAsp", k.asp == null ? NA : money(k.asp, false));

    setDelta("kpiRevenueDelta", k.revenue_mom_pct);
    setDelta("kpiProfitDelta", k.profit_mom_pct);
    setDelta("kpiMarginDelta", k.margin_mom_pct);

    const activeReps = k.active_reps || payload.table?.total_rows || 0;
    setText("srActiveRepsChip", `Active reps: ${fmtInt.format(num(activeReps))}`);

    const coverage = opt(k.cost_coverage_pct);
    setText("srCoverageChip", coverage == null ? "Coverage: N/A" : `Coverage: ${fmtPct.format(coverage)}%`);

    setText("srLastRefresh", `Last refresh: ${isoDateLabel(meta.last_refresh || k.last_refresh || meta.dataset_version)}`);
    setText("srWhatChanged", `What changed: ${k.what_changed || "No major change detected."}`);

    setDrillPayload(
      document.getElementById("kpiRevenue")?.closest(".sr-kpi"),
      workspacePayload("Executive Scorecard", "Revenue", "Revenue", k.revenue, { workspace_kind: "fact_orders" })
    );
    setDrillPayload(
      document.getElementById("kpiCustomers")?.closest(".sr-kpi"),
      workspacePayload("Executive Scorecard", "Customers", "Customers", k.customers, {
        workspace_kind: "narrative",
        detail: "Distinct customers covered by visible sales reps under the active filter window.",
      })
    );
  };

  const renderTrend = (trend = {}) => {
    const canvasId = "trendChart";
    const labels = Array.isArray(trend.labels) ? trend.labels : [];
    const series = Array.isArray(trend.series) ? trend.series : [];
    const ranked = series
      .map((s) => ({ ...s, total: (s.revenue || []).reduce((acc, v) => acc + num(v), 0) }))
      .sort((a, b) => b.total - a.total);

    const top = ranked.slice(0, 5);
    const rest = ranked.slice(5);

    if (rest.length) {
      const others = labels.map((_, idx) => rest.reduce((acc, rep) => acc + num(rep.revenue?.[idx]), 0));
      top.push({ rep_name: "Others", revenue: others, rep_id: "others" });
    }

    const hasData = labels.length > 0 && top.length > 0;
    toggleEmpty(canvasId, !hasData);
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("trend");
      return;
    }

    const palette = ["#0d6efd", "#198754", "#fd7e14", "#6c757d", "#20c997", "#6610f2"];
    const chart = createChart("trend", canvasId, {
      type: "line",
      data: {
        labels,
        datasets: top.map((s, idx) => ({
          label: s.rep_name || s.rep_id || `Rep ${idx + 1}`,
          data: s.revenue || [],
          borderColor: palette[idx % palette.length],
          backgroundColor: "rgba(13,110,253,0.08)",
          borderWidth: 2,
          tension: 0.3,
          fill: false,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: {
          y: { ticks: { callback: (v) => fmtMoney0.format(v) } },
        },
      },
    });
    if (!chart) toggleEmpty(canvasId, true, "Chart unavailable.");
  };

  const renderTopReps = (rows = []) => {
    const canvasId = "topRepsChart";
    const metric = state.metric;
    const conf = metricConfig[metric] || metricConfig.revenue;
    const topRows = sortedByMetric(rows, metric).slice(0, state.topN);
    const hasData = topRows.length > 0;

    toggleEmpty(canvasId, !hasData);
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("topReps");
      return;
    }

    const chart = createChart("topReps", canvasId, {
      type: "bar",
      data: {
        labels: topRows.map((r) => r.rep_name || r.rep_id || NA),
        datasets: [{
          label: conf.label,
          data: topRows.map((r) => rowMetricValue(r, metric)),
          backgroundColor: "#0d6efd",
          borderRadius: 4,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        onClick: (_evt, activeEls) => {
          const idx = activeEls?.[0]?.index;
          if (idx == null) return;
          const row = topRows[idx];
          if (!row) return;
          openUniversal(salesrepPayload(row, "Ranking & Performance", "Top Reps", conf.label, rowMetricValue(row, metric)), document.getElementById(canvasId));
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => `${conf.label}: ${conf.fmt(ctx.raw)}`,
            },
          },
        },
      },
    });
    if (!chart) toggleEmpty(canvasId, true, "Chart unavailable.");
  };

  const renderPareto = (rows = []) => {
    const canvasId = "revenueShareChart";
    const metric = state.metric;
    const conf = metricConfig[metric] || metricConfig.revenue;
    const sorted = sortedByMetric(rows, metric).slice(0, state.topN);
    const total = sorted.reduce((acc, r) => acc + Math.max(0, rowMetricValue(r, metric)), 0);
    let running = 0;
    const cumulative = sorted.map((r) => {
      running += Math.max(0, rowMetricValue(r, metric));
      return total > 0 ? (running / total) * 100 : 0;
    });
    const hasData = sorted.length > 0;

    toggleEmpty(canvasId, !hasData);
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("pareto");
      return;
    }

    const chart = createChart("pareto", canvasId, {
      data: {
        labels: sorted.map((r) => r.rep_name || r.rep_id || NA),
        datasets: [
          {
            type: "bar",
            label: conf.label,
            data: sorted.map((r) => rowMetricValue(r, metric)),
            backgroundColor: "#0dcaf0",
          },
          {
            type: "line",
            label: "Cumulative %",
            data: cumulative,
            borderColor: "#0d6efd",
            yAxisID: "y1",
            tension: 0.25,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (_evt, activeEls) => {
          const idx = activeEls?.[0]?.index;
          if (idx == null) return;
          const row = sorted[idx];
          if (!row) return;
          openUniversal(salesrepPayload(row, "Ranking & Performance", "Revenue Share", conf.label, rowMetricValue(row, metric)), document.getElementById(canvasId));
        },
        scales: {
          y: {
            ticks: {
              callback: (v) => conf.fmt(v),
            },
          },
          y1: {
            position: "right",
            grid: { drawOnChartArea: false },
            ticks: {
              callback: (v) => `${fmtPct.format(v)}%`,
            },
          },
        },
      },
    });
    if (!chart) toggleEmpty(canvasId, true, "Chart unavailable.");
  };

  const renderEfficiency = (rows = []) => {
    const canvasId = "effChart";
    const points = (Array.isArray(rows) ? rows : []).map((r) => ({
      x: num(r.customers),
      y: num(r.revenue),
      r: Math.max(4, Math.min(18, Math.sqrt(Math.abs(num(r.profit || 0))) / 45)),
      rep_name: r.rep_name,
      margin_pct: opt(r.margin_pct),
      profit: opt(r.profit),
    }));
    const hasData = points.length > 0;

    toggleEmpty(canvasId, !hasData);
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("eff");
      return;
    }

    const chart = createChart("eff", canvasId, {
      type: "bubble",
      data: { datasets: [{ data: points, backgroundColor: "rgba(25,135,84,0.55)" }] },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (_evt, activeEls) => {
          const idx = activeEls?.[0]?.index;
          if (idx == null) return;
          const row = rows[idx];
          if (!row) return;
          openUniversal(salesrepPayload(row, "Efficiency & Risk", "Rep Efficiency", "Revenue", row.revenue), document.getElementById(canvasId));
        },
        scales: {
          x: { title: { display: true, text: "Customers" }, ticks: { callback: (v) => fmtInt.format(v) } },
          y: { title: { display: true, text: "Revenue" }, ticks: { callback: (v) => fmtMoney0.format(v) } },
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const raw = ctx.raw || {};
                const margin = raw.margin_pct == null ? "N/A" : `${fmtPct.format(raw.margin_pct)}%`;
                const profit = raw.profit == null ? NA : fmtMoney0.format(raw.profit);
                return `${raw.rep_name || "Rep"}: ${fmtMoney0.format(raw.y || 0)} revenue, ${fmtInt.format(raw.x || 0)} customers, ${profit} profit, ${margin} margin`;
              },
            },
          },
        },
      },
    });
    if (!chart) toggleEmpty(canvasId, true, "Chart unavailable.");
  };

  const renderConcentration = (rows = []) => {
    const canvasId = "concentrationChart";
    const ranked = (Array.isArray(rows) ? [...rows] : [])
      .sort((a, b) => num(b.top_customer_share) - num(a.top_customer_share))
      .slice(0, state.topN);

    const hasData = ranked.length > 0;
    toggleEmpty(canvasId, !hasData);
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("concentration");
      return;
    }

    const chart = createChart("concentration", canvasId, {
      type: "bar",
      data: {
        labels: ranked.map((r) => r.rep_name || r.rep_id || NA),
        datasets: [
          {
            label: "Top 1 Share %",
            data: ranked.map((r) => num(r.top_customer_share) * 100),
            backgroundColor: "#fd7e14",
          },
          {
            label: "Top 5 Share %",
            data: ranked.map((r) => num(r.top_5_customer_share) * 100),
            backgroundColor: "#6f42c1",
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (_evt, activeEls) => {
          const idx = activeEls?.[0]?.index;
          if (idx == null) return;
          const row = ranked[idx];
          if (!row) return;
          openUniversal(salesrepPayload(row, "Efficiency & Risk", "Concentration Risk", "Top customer share", num(row.top_customer_share) * 100), document.getElementById(canvasId));
        },
        scales: {
          y: {
            ticks: { callback: (v) => `${fmtPct.format(v)}%` },
          },
        },
        plugins: {
          tooltip: {
            callbacks: {
              afterBody: (items) => {
                const i = items?.[0]?.dataIndex;
                if (i == null) return "";
                const row = ranked[i] || {};
                return `HHI: ${fmtPct.format(num(row.customer_hhi) * 100)} | Top customer: ${row.top_customer_name || NA}`;
              },
            },
          },
        },
      },
    });
    if (!chart) toggleEmpty(canvasId, true, "Chart unavailable.");
  };

  const renderProfitRevenue = (rows = []) => {
    const canvasId = "profitRevenueChart";
    const points = (Array.isArray(rows) ? rows : [])
      .map((r) => ({
        x: num(r.revenue),
        y: opt(r.profit),
        rep_name: r.rep_name || r.rep_id || NA,
        rep_id: r.rep_id || r.key || r.rep_name,
      }))
      .filter((r) => r.y !== null);

    const hasData = points.length > 0;
    toggleEmpty(canvasId, !hasData, "No profit data available.");
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("profitRevenue");
      return;
    }

    const midX = points.reduce((acc, p) => acc + p.x, 0) / points.length;
    const midY = points.reduce((acc, p) => acc + p.y, 0) / points.length;
    const maxX = Math.max(...points.map((p) => p.x), 0);
    const maxY = Math.max(...points.map((p) => p.y), 0);

    const chart = createChart("profitRevenue", canvasId, {
      type: "scatter",
      data: {
        datasets: [
          {
            label: "Reps",
            data: points,
            backgroundColor: "rgba(220,53,69,0.65)",
          },
          {
            type: "line",
            label: "Revenue midpoint",
            data: [{ x: midX, y: 0 }, { x: midX, y: maxY * 1.05 }],
            borderColor: "rgba(13,110,253,0.55)",
            borderDash: [6, 6],
            pointRadius: 0,
          },
          {
            type: "line",
            label: "Profit midpoint",
            data: [{ x: 0, y: midY }, { x: maxX * 1.05, y: midY }],
            borderColor: "rgba(25,135,84,0.55)",
            borderDash: [6, 6],
            pointRadius: 0,
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        onClick: (_evt, activeEls) => {
          const hit = activeEls?.[0];
          if (!hit || hit.datasetIndex !== 0) return;
          const point = points[hit.index];
          if (!point) return;
          openUniversal(
            salesrepPayload(point, "Efficiency & Risk", "Profit vs Revenue", "Profit", point.y),
            document.getElementById(canvasId)
          );
        },
        scales: {
          x: { title: { display: true, text: "Revenue" }, ticks: { callback: (v) => fmtMoney0.format(v) } },
          y: { title: { display: true, text: "Profit" }, ticks: { callback: (v) => fmtMoney0.format(v) } },
        },
        plugins: {
          tooltip: {
            callbacks: {
              label: (ctx) => {
                if (!ctx.raw || ctx.datasetIndex !== 0) return ctx.dataset.label;
                return `${ctx.raw.rep_name}: ${fmtMoney0.format(ctx.raw.y)} profit on ${fmtMoney0.format(ctx.raw.x)} revenue`;
              },
            },
          },
        },
      },
    });
    if (!chart) toggleEmpty(canvasId, true, "Chart unavailable.");
  };

  const renderAspLeaders = (rows = []) => {
    const canvasId = "aspChart";
    const sorted = (Array.isArray(rows) ? [...rows] : [])
      .filter((r) => opt(r.asp) !== null)
      .sort((a, b) => num(b.asp) - num(a.asp))
      .slice(0, 10);

    const hasData = sorted.length > 0;
    toggleEmpty(canvasId, !hasData);
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("asp");
      return;
    }

    const chart = createChart("asp", canvasId, {
      type: "bar",
      data: {
        labels: sorted.map((r) => r.rep_name || r.rep_id || NA),
        datasets: [{ label: "ASP", data: sorted.map((r) => num(r.asp)), backgroundColor: "#6f42c1" }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        onClick: (_evt, activeEls) => {
          const idx = activeEls?.[0]?.index;
          if (idx == null) return;
          const row = sorted[idx];
          if (!row) return;
          openUniversal(salesrepPayload(row, "Efficiency & Risk", "ASP Leaders", "ASP", row.asp), document.getElementById(canvasId));
        },
        plugins: { legend: { display: false } },
        scales: { x: { ticks: { callback: (v) => fmtMoney2.format(v) } } },
      },
    });
    if (!chart) toggleEmpty(canvasId, true, "Chart unavailable.");
  };

  const riskBadgeClass = (severity) => {
    if (severity === "high") return "text-bg-danger";
    if (severity === "medium") return "text-bg-warning";
    return "text-bg-secondary";
  };

  const renderRiskFlags = (flags = []) => {
    const holder = document.getElementById("srRiskFlags");
    if (!holder) return;
    holder.innerHTML = "";
    const rows = Array.isArray(flags) ? flags : [];
    if (!rows.length) {
      holder.innerHTML = '<li class="text-muted small">No active risk flags.</li>';
      return;
    }
    rows.forEach((f) => {
      const li = document.createElement("li");
      li.className = "risk-item";
      li.innerHTML = `<span>${f.label || f.key || "Risk"}</span><span class="badge ${riskBadgeClass(f.severity)}">${fmtInt.format(num(f.count))}</span>`;
      holder.appendChild(li);
    });
  };

  const appendFilterQS = (url) => {
    if (!url) return "#";
    const q = new URLSearchParams(state.qs || "").toString();
    if (!q) return url;
    return url.includes("?") ? `${url}&${q}` : `${url}?${q}`;
  };

  const rowSignalChip = (row) => {
    const chips = [];
    if (opt(row.margin_pct) !== null && num(row.margin_pct) < 27) chips.push('<span class="chip-danger">Low margin</span>');
    if (opt(row.top_5_customer_share) !== null && num(row.top_5_customer_share) > 0.65) chips.push('<span class="chip-warn">High concentration</span>');
    return chips.join(" ");
  };

  const renderTable = (table = {}) => {
    const tbody = document.getElementById("salesreps-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    const rows = Array.isArray(table.rows) ? table.rows : [];
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="18" class="text-center text-muted">No data for current filters.</td></tr>';
    } else {
      rows.forEach((r) => {
        const repId = r.rep_id || r.key || r.rep_name || "";
        const repName = r.rep_name || r.label || repId || NA;
        const baseUrl = drilldownTemplate ? drilldownTemplate.replace("__ID__", encodeURIComponent(repId)) : "#";
        const href = appendFilterQS(baseUrl);
        const payload = salesrepPayload(r, "Detailed Table", "Sales Rep Table", "Revenue", r.revenue);
        const tr = document.createElement("tr");
        tr.tabIndex = 0;
        tr.dataset.href = href;
        if (payload) tr.setAttribute("data-drilldown-payload", JSON.stringify(payload));

        tr.innerHTML = `
          <td class="sticky-col" title="${repName}">${repName}</td>
          <td class="text-end">${money(r.revenue)}</td>
          <td class="text-end">${r.profit == null ? NA : money(r.profit)}</td>
          <td class="text-end">${r.margin_pct == null ? NA : `${fmtPct.format(num(r.margin_pct))}%`}</td>
          <td class="text-end">${fmtInt.format(num(r.orders))}</td>
          <td class="text-end">${fmtInt.format(num(r.customers))}</td>
          <td class="text-end">${fmtInt.format(num(r.weight_lb))}</td>
          <td class="text-end">${fmtInt.format(num(r.units))}</td>
          <td class="text-end">${r.asp_lb == null ? NA : money(r.asp_lb, false)}</td>
          <td class="text-end">${r.asp == null ? NA : money(r.asp, false)}</td>
          <td class="text-end">${pct(r.top_customer_share, true)}</td>
          <td class="col-top_customer_name" title="${r.top_customer_name || NA}">${r.top_customer_name || NA}<div>${rowSignalChip(r)}</div></td>
          <td class="text-end col-top_customer_revenue">${r.top_customer_revenue == null ? NA : money(r.top_customer_revenue)}</td>
          <td class="text-end col-mom_revenue_pct">${pct(r.mom_revenue_pct, false)}</td>
          <td class="text-end col-mom_profit_pct">${pct(r.mom_profit_pct, false)}</td>
          <td class="text-end col-top_5_customer_share">${pct(r.top_5_customer_share, true)}</td>
          <td class="text-end col-customer_hhi">${r.customer_hhi == null ? NA : fmtPct.format(num(r.customer_hhi) * 100)}</td>
          <td class="text-end"><a class="btn btn-sm btn-outline-primary" href="${href}" aria-label="Open drilldown for ${repName}">View</a></td>
        `;
        tbody.appendChild(tr);
      });
    }

    const page = num(table.page || state.page, 1);
    const pageSize = num(table.page_size || state.pageSize, state.pageSize);
    const total = num(table.total_rows || table.total || table.all_rows, 0);
    const totalPages = Math.max(1, num(table.total_pages || Math.ceil(total / Math.max(pageSize, 1)), 1));

    const start = total > 0 ? (page - 1) * pageSize + 1 : 0;
    const end = total > 0 ? Math.min(page * pageSize, total) : 0;

    setText("salesrepsPagerSummary", total > 0 ? `Showing ${start}-${end} of ${fmtInt.format(total)}` : "No rows");
    setText("salesrepsPagerIndicator", `Page ${page} of ${totalPages}`);

    const prev = document.getElementById("salesrepsPrev");
    const next = document.getElementById("salesrepsNext");
    if (prev) prev.disabled = page <= 1;
    if (next) next.disabled = page >= totalPages;
  };

  const applyColumnVisibility = () => {
    document.querySelectorAll("[data-col-toggle]").forEach((cb) => {
      const key = cb.dataset.colToggle;
      if (!key) return;
      const cls = `.col-${key}`;
      document.querySelectorAll(cls).forEach((el) => {
        el.classList.toggle("sr-hidden-col", !cb.checked);
      });
    });
  };

  const syncSortClasses = () => {
    document.querySelectorAll("#srTable .sortable").forEach((th) => {
      th.classList.remove("asc", "desc");
      if (th.dataset.sortKey === state.sortBy) th.classList.add(state.sortDir);
    });
  };

  const renderBundle = (rawPayload = {}) => {
    const payload = window.normalizeBundlePayload ? window.normalizeBundlePayload(rawPayload) : rawPayload;
    lastPayload = payload;
    updateColumnLabels(payload.meta || {});
    renderExecutive(payload);

    const tableRows = payload.table?.rows || [];
    renderTopReps(tableRows);
    renderPareto(tableRows);
    renderEfficiency(payload.charts?.scatter || tableRows);
    renderConcentration(payload.charts?.concentration || tableRows);
    renderProfitRevenue(payload.charts?.profit_vs_revenue || tableRows);
    renderAspLeaders(tableRows);
    renderTrend(payload.charts?.trend || payload.trend || {});
    renderTable(payload.table || {});
    renderRiskFlags(payload.risk_flags || []);
    if (window.universalDrilldown && typeof window.universalDrilldown.enhanceAll === "function") {
      window.universalDrilldown.enhanceAll();
    }
    applyColumnVisibility();
    syncSortClasses();
  };

  const fetchBundle = async () => {
    reqId += 1;
    const thisReq = reqId;
    if (currentAbort) currentAbort.abort();
    currentAbort = new AbortController();

    updateExportLinks();
    const qs = buildQueryString();
    const url = qs ? `${bundleUrl}?${qs}` : bundleUrl;

    try {
      const res = await authFetch(url, {
        method: "GET",
        credentials: "same-origin",
        signal: currentAbort.signal,
        headers: { Accept: "application/json" },
      });
      const payload = await res.json();
      if (thisReq !== reqId) return;
      if (!res.ok) throw new Error(payload?.error?.message || `HTTP ${res.status}`);
      renderBundle(payload);
    } catch (err) {
      if (err?.name === "AbortError") return;
      console.error("salesreps bundle failed", err);
      ["trendChart", "topRepsChart", "revenueShareChart", "effChart", "concentrationChart", "profitRevenueChart", "aspChart"].forEach((id) => toggleEmpty(id, true));
      setText("srWhatChanged", "What changed: failed to load bundle.");
    } finally {
      try {
        window.dispatchEvent(new CustomEvent("globalFilters:applied", { detail: { qs: state.qs } }));
      } catch (_e) {
        // no-op
      }
    }
  };

  const waitForFiltersReady = async () => {
    const fallback = () => {
      try {
        return (window.getGlobalFilterState && window.getGlobalFilterState()) || {};
      } catch (_e) {
        return {};
      }
    };
    if (window.filtersReady && typeof window.filtersReady.then === "function") {
      try {
        const timeout = new Promise((resolve) => setTimeout(() => resolve(fallback()), 1500));
        return await Promise.race([window.filtersReady, timeout]);
      } catch (_e) {
        return fallback();
      }
    }
    return fallback();
  };

  const resolveInitialQS = () => {
    try {
      if (window.getGlobalFilterState) {
        const st = window.getGlobalFilterState();
        if (st?.qs) return String(st.qs).replace(/^\?/, "");
      }
    } catch (_e) {
      // ignore
    }
    return (window.location.search || "").replace(/^\?/, "");
  };

  const applyFilters = (qs) => {
    state.qs = String(qs || "").replace(/^\?/, "");
    state.page = 1;
    fetchBundle();
  };

  const debounce = (fn, delay = 250) => {
    let timer = null;
    return (...args) => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  };

  const wireSorting = () => {
    document.querySelectorAll("#srTable .sortable").forEach((th) => {
      const doSort = () => {
        const key = th.dataset.sortKey || "revenue";
        if (state.sortBy === key) state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        else {
          state.sortBy = key;
          state.sortDir = key === "rep_name" ? "asc" : "desc";
        }
        state.page = 1;
        fetchBundle();
      };
      th.addEventListener("click", doSort);
      th.addEventListener("keydown", (evt) => {
        if (evt.key === "Enter" || evt.key === " ") {
          evt.preventDefault();
          doSort();
        }
      });
    });
  };

  const wirePager = () => {
    const prev = document.getElementById("salesrepsPrev");
    const next = document.getElementById("salesrepsNext");
    if (prev) {
      prev.addEventListener("click", () => {
        state.page = Math.max(1, state.page - 1);
        fetchBundle();
      });
    }
    if (next) {
      next.addEventListener("click", () => {
        state.page += 1;
        fetchBundle();
      });
    }
  };

  const wireRowClicks = () => {
    const tbody = document.getElementById("salesreps-table-body");
    if (!tbody) return;
    const openRow = (row) => {
      if (!row?.dataset?.href) return;
      if (window.universalDrilldown) return;
      window.location.href = row.dataset.href;
    };
    tbody.addEventListener("click", (evt) => {
      const target = evt.target;
      if (target && target.closest("a")) return;
      const row = target?.closest("tr");
      if (row) openRow(row);
    });
    tbody.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter") return;
      const row = evt.target?.closest("tr");
      if (row) openRow(row);
    });
  };

  const wireControls = () => {
    const metricToggle = document.getElementById("srMetricToggle");
    const topN = document.getElementById("srTopN");
    const pageSize = document.getElementById("srPageSize");
    const search = document.getElementById("srSearchInput");

    if (metricToggle) {
      metricToggle.value = state.metric;
      metricToggle.addEventListener("change", () => {
        state.metric = metricToggle.value;
        state.page = 1;
        fetchBundle();
      });
    }

    if (topN) {
      topN.value = String(state.topN);
      topN.addEventListener("change", () => {
        state.topN = num(topN.value, 10);
        fetchBundle();
      });
    }

    if (pageSize) {
      pageSize.value = String(state.pageSize);
      pageSize.addEventListener("change", () => {
        const allowed = new Set([25, 50, 100]);
        const next = num(pageSize.value, 25);
        state.pageSize = allowed.has(next) ? next : 25;
        pageSize.value = String(state.pageSize);
        state.page = 1;
        fetchBundle();
      });
    }

    if (search) {
      const debounced = debounce(() => {
        state.search = search.value.trim();
        state.page = 1;
        fetchBundle();
      }, 280);
      search.addEventListener("input", debounced);
    }

    document.querySelectorAll("[data-col-toggle]").forEach((cb) => {
      cb.addEventListener("change", applyColumnVisibility);
    });
  };

  const wireTooltips = () => {
    if (!window.bootstrap || !window.bootstrap.Tooltip) return;
    document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => {
      if (el.dataset.tooltipReady === "1") return;
      el.dataset.tooltipReady = "1";
      new window.bootstrap.Tooltip(el);
    });
  };

  const bootstrap = async (qsHint) => {
    if (bootstrapped) return;
    bootstrapped = true;
    const detail = await waitForFiltersReady();
    const qs = (qsHint || detail?.qs || resolveInitialQS() || "").replace(/^\?/, "");
    state.qs = qs;
    wireTooltips();
    fetchBundle();
  };

  wireSorting();
  wirePager();
  wireRowClicks();
  wireControls();

  window.addEventListener("globalFilters:apply", (evt) => applyFilters(evt?.detail?.qs || ""));
  window.addEventListener("globalFilters:ready", (evt) => bootstrap(evt?.detail?.qs || ""));

  bootstrap();
})();
