(() => {
  const root = document.getElementById("SuppliersV2App");
  if (!root) return;

  const authFetch = window.authFetch || fetch;
  const bundleUrl = root.dataset.bundleUrl || "/api/suppliers/bundle";
  const exportCsvUrl = root.dataset.exportCsvUrl || "/api/suppliers/export.csv";
  const exportXlsxUrl = root.dataset.exportXlsxUrl || "/api/suppliers/export.xlsx";
  const showCosts = (() => {
    try {
      return JSON.parse(root.dataset.showCosts || "true") !== false;
    } catch (_err) {
      return true;
    }
  })();

  const state = {
    page: 1,
    pageSize: 50,
    sortBy: "revenue_current",
    sortDir: "desc",
    search: "",
    quickFilter: "all",
    filterQs: (window.location.search || "").replace(/^\?/, ""),
    loading: false,
    totalRows: 0,
  };

  const els = {
    chips: document.getElementById("supplierHealthChips"),
    narrative: document.getElementById("supplierNarrative"),
    windowSummary: document.getElementById("suppliersWindowSummary"),
    kpiRevenue: document.getElementById("kpiRevenue"),
    kpiRevenueDelta: document.getElementById("kpiRevenueDelta"),
    kpiProfit: document.getElementById("kpiProfit"),
    kpiProfitDelta: document.getElementById("kpiProfitDelta"),
    kpiMargin: document.getElementById("kpiMargin"),
    kpiMarginDelta: document.getElementById("kpiMarginDelta"),
    kpiActiveSuppliers: document.getElementById("kpiActiveSuppliers"),
    kpiActiveSuppliersMeta: document.getElementById("kpiActiveSuppliersMeta"),
    kpiCostCoverage: document.getElementById("kpiCostCoverage"),
    kpiRevenueAtRisk: document.getElementById("kpiRevenueAtRisk"),
    concentrationSummary: document.getElementById("concentrationSummary"),
    marginLeakageRows: document.getElementById("marginLeakageRows"),
    dataRiskRows: document.getElementById("dataRiskRows"),
    moversRows: document.getElementById("moversRows"),
    segmentSummaryRows: document.getElementById("segmentSummaryRows"),
    tableBody: document.getElementById("supV2TableBody"),
    tableStatus: document.getElementById("supV2TableStatus"),
    loadMore: document.getElementById("supV2LoadMore"),
    pageSize: document.getElementById("supV2PageSize"),
    search: document.getElementById("supV2Search"),
    clearSearch: document.getElementById("supV2SearchClear"),
    exportTableCsv: document.getElementById("supV2ExportCsv"),
    exportTableXlsx: document.getElementById("supV2ExportXlsx"),
    exportMovers: document.getElementById("exportMovers"),
    exportRisk: document.getElementById("exportRisk"),
    exportSegments: document.getElementById("exportSegments"),
    exportConcentration: document.getElementById("exportConcentration"),
  };

  const nfInt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
  const nfMoney0 = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", maximumFractionDigits: 0 });
  const nfMoney2 = new Intl.NumberFormat(undefined, { style: "currency", currency: "USD", minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const nfPct1 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });

  const money0 = (v) => (v == null || Number.isNaN(Number(v)) ? "—" : nfMoney0.format(Number(v)));
  const money2 = (v) => (v == null || Number.isNaN(Number(v)) ? "—" : nfMoney2.format(Number(v)));
  const int0 = (v) => (v == null || Number.isNaN(Number(v)) ? "—" : nfInt.format(Number(v)));
  const pct1 = (v) => (v == null || Number.isNaN(Number(v)) ? "—" : `${nfPct1.format(Number(v))}%`);

  const escapeHtml = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

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

  const supplierPayload = (supplierId, supplierLabel, section, widget, metric, value, extra = {}) => {
    const cleanId = String(supplierId || "").trim();
    if (!cleanId) return null;
    return {
      source_page: "suppliers",
      source_section: section,
      source_widget: widget,
      requested_target: "supplier",
      clicked_entity_type: "supplier",
      clicked_entity_id: cleanId,
      clicked_entity_label: String(supplierLabel || cleanId),
      clicked_metric: metric,
      clicked_metric_value: value,
      active_filter_state: currentFilterState(),
      extra,
    };
  };

  const workspacePayload = (section, widget, metric, value, extra = {}) => ({
    source_page: "suppliers",
    source_section: section,
    source_widget: widget,
    requested_target: "workspace",
    clicked_metric: metric,
    clicked_metric_value: value,
    active_filter_state: currentFilterState(),
    extra,
  });

  const setText = (el, text) => {
    if (el) el.textContent = text;
  };

  const buildParams = ({ includePage = true } = {}) => {
    const params = new URLSearchParams(state.filterQs || "");
    params.set("suppliers_v2", "1");
    params.set("sort", state.sortBy);
    params.set("sort_dir", state.sortDir);
    params.set("quick_filter", state.quickFilter);
    if (state.search) params.set("search", state.search);
    if (includePage) {
      params.set("page", String(state.page));
      params.set("page_size", String(state.pageSize));
    }
    return params;
  };

  const updateExportLinks = () => {
    const base = buildParams({ includePage: false });
    const setHref = (el, url, scope) => {
      if (!el) return;
      const p = new URLSearchParams(base.toString());
      p.set("scope", scope);
      el.href = `${url}?${p.toString()}`;
    };
    setHref(els.exportTableCsv, exportCsvUrl, "table");
    setHref(els.exportTableXlsx, exportXlsxUrl, "table");
    setHref(els.exportMovers, exportCsvUrl, "movers");
    setHref(els.exportRisk, exportCsvUrl, "risk");
    setHref(els.exportSegments, exportCsvUrl, "segments");
    setHref(els.exportConcentration, exportCsvUrl, "concentration");
  };

  const renderChips = (kpis = {}, summary = {}) => {
    if (!els.chips) return;
    const chips = [
      `Active 30d: ${int0(summary.active_suppliers_30d)}`,
      `New/Lost Signals: ${int0((kpis.new_suppliers || 0) + (kpis.lost_suppliers || 0))}`,
      `At Risk >=90d: ${int0(summary.at_risk_suppliers)}`,
      `Revenue at Risk: ${money0(summary.revenue_at_risk)}`,
      `Cost Coverage: ${pct1(summary.cost_coverage_pct)}`,
    ];
    els.chips.innerHTML = chips.map((text) => `<span class="chip">${text}</span>`).join("");
  };

  const renderKpis = (kpis = {}, summary = {}) => {
    setText(els.kpiRevenue, money0(kpis.total_revenue));
    setText(els.kpiRevenueDelta, `vs prior: ${money0(kpis.revenue_delta)} (${pct1(kpis.revenue_delta_pct)})`);
    setText(els.kpiProfit, showCosts ? money0(kpis.total_profit) : "—");
    setText(els.kpiProfitDelta, showCosts ? `vs prior: ${money0(kpis.profit_delta)}` : "Costs hidden");
    setText(els.kpiMargin, showCosts ? pct1(kpis.margin_pct) : "—");
    setText(els.kpiMarginDelta, showCosts ? `vs prior: ${pct1(kpis.margin_delta_pp)} pp` : "Costs hidden");
    setText(els.kpiActiveSuppliers, int0(summary.active_suppliers));
    setText(els.kpiActiveSuppliersMeta, `${int0(summary.active_suppliers_30d)} active in last 30d`);
    setText(els.kpiCostCoverage, pct1(summary.cost_coverage_pct));
    setText(els.kpiRevenueAtRisk, `At risk: ${money0(summary.revenue_at_risk)}`);

    const w = kpis.window || {};
    if (w.start && w.end) {
      setText(els.windowSummary, `Computed using window ${w.start} to ${w.end} (prior ${w.prior_start || "—"} to ${w.prior_end || "—"}).`);
    }
    setText(els.narrative, summary.narrative || kpis.narrative || "No narrative available.");
    renderChips(kpis, summary);

    setDrillPayload(
      els.kpiRevenue?.closest(".card"),
      workspacePayload("Executive Scorecard", "Revenue", "Revenue", kpis.total_revenue, { workspace_kind: "fact_orders" })
    );
    setDrillPayload(
      els.kpiActiveSuppliers?.closest(".card"),
      workspacePayload("Executive Scorecard", "Active Suppliers", "Active suppliers", summary.active_suppliers, {
        workspace_kind: "narrative",
        detail: "Suppliers active under the current scoped window and inherited filters.",
      })
    );
  };

  const renderTrend = (trend = {}) => {
    const labels = Array.isArray(trend.labels) ? trend.labels : [];
    const revenue = Array.isArray(trend.revenue) ? trend.revenue : [];
    const profit = Array.isArray(trend.profit) ? trend.profit : [];
    const margin = Array.isArray(trend.margin_pct) ? trend.margin_pct : [];
    if (!window.Plotly) return;
    if (!labels.length) {
      window.Plotly.purge("supTrendChart");
      return;
    }
    const traces = [
      { x: labels, y: revenue, type: "bar", name: "Revenue", hovertemplate: "%{x}<br>%{y:$,.0f}<extra></extra>" },
    ];
    if (showCosts && profit.some((v) => Number.isFinite(Number(v)))) {
      traces.push({ x: labels, y: profit, type: "scatter", mode: "lines+markers", name: "Profit", hovertemplate: "%{x}<br>%{y:$,.0f}<extra></extra>" });
    }
    const layout = {
      height: 330,
      margin: { t: 10, r: showCosts ? 60 : 20, b: 50, l: 55 },
      xaxis: { tickangle: -40, automargin: true },
      yaxis: { title: "Revenue", tickformat: "$,.0f" },
      hovermode: "x unified",
    };
    if (showCosts && margin.some((v) => Number.isFinite(Number(v)))) {
      traces.push({
        x: labels,
        y: margin,
        type: "scatter",
        mode: "lines",
        name: "Margin %",
        yaxis: "y2",
        hovertemplate: "%{x}<br>%{y:.1f}%<extra></extra>",
      });
      layout.yaxis2 = { overlaying: "y", side: "right", ticksuffix: "%", title: "Margin %" };
    }
    window.Plotly.newPlot("supTrendChart", traces, layout, { displayModeBar: false, responsive: true });
    const chartEl = document.getElementById("supTrendChart");
    if (chartEl && typeof chartEl.on === "function") {
      if (chartEl.removeAllListeners) chartEl.removeAllListeners("plotly_click");
      chartEl.on("plotly_click", (event) => {
        const point = event?.points?.[0];
        if (!point?.x) return;
        openUniversal(
          {
            source_page: "suppliers",
            source_section: "Revenue & Profit Trend",
            source_widget: "Monthly Trend",
            requested_target: "workspace",
            clicked_metric: point.data?.name || "Revenue",
            clicked_metric_value: point.y,
            clicked_time_grain: "month",
            clicked_time_value: point.x,
            active_filter_state: currentFilterState(),
            extra: { workspace_kind: "fact_orders" },
          },
          chartEl
        );
      });
    }
  };

  const renderPareto = (rows = [], kpis = {}) => {
    const list = Array.isArray(rows) ? rows : [];
    if (!window.Plotly) return;
    if (!list.length) {
      window.Plotly.purge("supParetoChart");
      setText(els.concentrationSummary, "No concentration data for current filters.");
      return;
    }
    const x = list.map((r) => r.supplier_name || r.supplier_id);
    const share = list.map((r) => Number(r.share_pct || 0));
    const cumulative = list.map((r) => Number(r.cumulative_share_pct || 0));
    const traces = [
      { x, y: share, type: "bar", name: "Share %", hovertemplate: "%{x}<br>%{y:.1f}% share<extra></extra>" },
      { x, y: cumulative, type: "scatter", mode: "lines+markers", name: "Cumulative %", yaxis: "y2", hovertemplate: "%{x}<br>%{y:.1f}% cumulative<extra></extra>" },
    ];
    const layout = {
      height: 330,
      margin: { t: 10, r: 55, b: 80, l: 40 },
      xaxis: { tickangle: -45, automargin: true },
      yaxis: { title: "Share %", ticksuffix: "%" },
      yaxis2: { overlaying: "y", side: "right", title: "Cumulative %", ticksuffix: "%" },
      hovermode: "x unified",
    };
    window.Plotly.newPlot("supParetoChart", traces, layout, { displayModeBar: false, responsive: true });
    const chartEl = document.getElementById("supParetoChart");
    if (chartEl && typeof chartEl.on === "function") {
      if (chartEl.removeAllListeners) chartEl.removeAllListeners("plotly_click");
      chartEl.on("plotly_click", (event) => {
        const point = event?.points?.[0];
        const idx = point?.pointIndex;
        if (idx == null) return;
        const row = list[idx];
        if (!row?.supplier_id) return;
        openUniversal(
          supplierPayload(row.supplier_id, row.supplier_name || row.supplier_id, "Concentration", "Supplier Pareto", "Share %", row.share_pct),
          chartEl
        );
      });
    }
    setText(
      els.concentrationSummary,
      `HHI ${int0(kpis.concentration_hhi)} | Top1 ${pct1(kpis.concentration_top1_share)} | Top5 ${pct1(kpis.concentration_top5_share)}`
    );
  };

  const renderSmallRows = (target, rows, fn) => {
    if (!target) return;
    const safeRows = Array.isArray(rows) ? rows : [];
    if (!safeRows.length) {
      target.innerHTML = '<tr><td colspan="3" class="text-muted">No data</td></tr>';
      return;
    }
    target.innerHTML = safeRows.slice(0, 8).map(fn).join("");
  };

  const riskClass = (riskBand) => {
    const token = String(riskBand || "").toLowerCase();
    if (token === "high") return "risk-high";
    if (token === "medium") return "risk-medium";
    if (token === "low") return "risk-low";
    return "";
  };

  const buildDrilldownHref = (supplierId) => {
    const params = new URLSearchParams(state.filterQs || "");
    params.set("suppliers_v2", "1");
    return `/suppliers/${encodeURIComponent(String(supplierId || ""))}?${params.toString()}`;
  };

  const renderCommandTable = (table = {}, { append = false } = {}) => {
    const rows = Array.isArray(table.rows) ? table.rows : [];
    state.totalRows = Number(table.total_rows || rows.length || 0);
    if (!append) els.tableBody.innerHTML = "";
    if (!rows.length && !append) {
      els.tableBody.innerHTML = '<tr><td colspan="13" class="text-center text-muted py-4">No suppliers for current selection.</td></tr>';
    } else if (rows.length) {
      const html = rows.map((r) => {
        const href = buildDrilldownHref(r.supplier_id);
        const risk = r.risk_band || "Unknown";
        const riskCls = riskClass(risk);
        const deltaPct = r.low_base_warning ? "low base" : pct1(r.delta_revenue_pct);
        const payload = supplierPayload(r.supplier_id, r.supplier_name || r.supplier_id, "Supplier Command Center", "Supplier Table", "Revenue", r.revenue_current);
        return `
          <tr data-row="supplier" data-id="${r.supplier_id || ""}" tabindex="0"${drillAttr(payload)}>
            <td><a class="text-decoration-none" href="${href}">${r.supplier_name || r.supplier_id || "Unknown"}</a></td>
            <td class="text-end">${r.segment_label || "Long tail"}</td>
            <td class="text-end ${riskCls}">${risk}</td>
            <td class="text-end">${money0(r.revenue_current)}</td>
            <td class="text-end">${money0(r.revenue_prior)}</td>
            <td class="text-end">${money0(r.delta_revenue)}</td>
            <td class="text-end">${deltaPct}</td>
            <td class="text-end">${showCosts ? money0(r.profit) : "—"}</td>
            <td class="text-end">${showCosts ? pct1(r.margin_pct) : "—"}</td>
            <td class="text-end">${int0(r.orders)}</td>
            <td class="text-end">${int0(r.days_since_last_order)}</td>
            <td class="text-end">${pct1(r.missing_cost_pct)}</td>
            <td><a class="btn btn-sm btn-outline-primary" href="${href}">View</a></td>
          </tr>
        `;
      }).join("");
      els.tableBody.insertAdjacentHTML("beforeend", html);
    }

    const shown = els.tableBody.querySelectorAll("tr[data-row='supplier']").length;
    setText(els.tableStatus, `${int0(shown)} of ${int0(state.totalRows)} shown`);
    if (els.loadMore) els.loadMore.disabled = shown >= state.totalRows;

    els.tableBody.querySelectorAll("tr[data-row='supplier']").forEach((tr) => {
      if (tr.dataset.drillBound === "1") return;
      tr.dataset.drillBound = "1";
      tr.addEventListener("click", (evt) => {
        if (evt.target && evt.target.closest("a,button")) return;
        if (window.universalDrilldown) return;
        const sid = tr.dataset.id;
        if (!sid) return;
        window.location.href = buildDrilldownHref(sid);
      });
      tr.addEventListener("keydown", (evt) => {
        if (evt.key !== "Enter" && evt.key !== " ") return;
        evt.preventDefault();
        if (window.universalDrilldown) return;
        const sid = tr.dataset.id;
        if (!sid) return;
        window.location.href = buildDrilldownHref(sid);
      });
    });
  };

  const renderPayload = (payload, { append = false } = {}) => {
    const kpis = payload.kpis || {};
    const charts = payload.charts || {};
    const summary = payload.executive_summary || {};
    const risk = payload.risk_opportunities || {};
    const movers = payload.movers || {};
    const segments = payload.segments || {};

    renderKpis(kpis, summary);
    renderTrend(charts.revenue_profit_trend || charts.trend_12m || payload.trend || {});
    renderPareto(charts.concentration_pareto || [], kpis);

    renderSmallRows(els.marginLeakageRows, risk.margin_leakage || [], (r) => `
      <tr${drillAttr(supplierPayload(r.supplier_id, r.supplier_name || r.supplier_id, "Margin Leakage", "Below Target Suppliers", "Profit uplift", r.profit_uplift_target))}><td>${r.supplier_name || r.supplier_id || ""}</td><td class="text-end">${pct1(r.margin_pct)}</td><td class="text-end">${money0(r.profit_uplift_target)}</td></tr>
    `);
    renderSmallRows(els.dataRiskRows, risk.data_risk || [], (r) => `
      <tr${drillAttr(supplierPayload(r.supplier_id, r.supplier_name || r.supplier_id, "Data Quality Risk", "Missing Cost Exposure", "Missing cost %", r.missing_cost_pct))}><td>${r.supplier_name || r.supplier_id || ""}</td><td class="text-end">${pct1(r.missing_cost_pct)}</td><td class="text-end">${money0(r.revenue)}</td></tr>
    `);

    const moverRows = []
      .concat((movers.top_gainers || []).slice(0, 4))
      .concat((movers.top_decliners || []).slice(0, 4));
    renderSmallRows(els.moversRows, moverRows, (r) => `
      <tr${drillAttr(supplierPayload(r.supplier_id, r.supplier_name || r.supplier_id, "Supplier Movers", "Revenue Delta Movers", "Delta revenue", r.delta_revenue))}><td>${r.supplier_name || r.supplier_id || ""}</td><td class="text-end">${money0(r.delta_revenue)}</td><td>${r.delta_revenue_label || ""}</td></tr>
    `);
    renderSmallRows(els.segmentSummaryRows, segments.summary || [], (r) => `
      <tr${drillAttr(workspacePayload("Supplier Segments", "Segment Summary", "Segment revenue", r.revenue, {
        workspace_kind: "narrative",
        detail: `Segment ${r.segment || "Unknown"} represents ${pct1(r.share_pct)} of supplier revenue in the current window.`,
      }))}>
        <td>${r.segment || ""}</td>
        <td class="text-end">${int0(r.suppliers)}</td>
        <td class="text-end">${money0(r.revenue)}</td>
        <td class="text-end">${showCosts ? money0(r.profit) : "—"}</td>
        <td class="text-end">${showCosts ? pct1(r.avg_margin_pct) : "—"}</td>
        <td class="text-end">${pct1(r.share_pct)}</td>
      </tr>
    `);

    renderCommandTable(payload.table || {}, { append });
    updateExportLinks();
    if (window.universalDrilldown && typeof window.universalDrilldown.enhanceAll === "function") {
      window.universalDrilldown.enhanceAll();
    }
  };

  let inflight = null;
  const fetchBundle = async ({ append = false } = {}) => {
    if (state.loading) return;
    state.loading = true;
    if (inflight) inflight.abort();
    inflight = new AbortController();
    setText(els.tableStatus, append ? "Loading more..." : "Loading...");
    const params = buildParams({ includePage: true });
    try {
      const res = await authFetch(`${bundleUrl}?${params.toString()}`, {
        signal: inflight.signal,
        headers: { Accept: "application/json" },
      });
      if (!res.ok) {
        throw new Error(`Bundle request failed (${res.status})`);
      }
      const raw = await res.json();
      const payload = window.normalizeBundlePayload ? window.normalizeBundlePayload(raw) : raw;
      renderPayload(payload || {}, { append });
      setText(els.tableStatus, "Loaded");
    } catch (err) {
      console.error("[suppliers-v2] bundle fetch failed", err);
      if (!append) {
        els.tableBody.innerHTML = '<tr><td colspan="13" class="text-center text-danger py-4">Failed to load data.</td></tr>';
      }
      setText(els.tableStatus, "Failed to load");
    } finally {
      state.loading = false;
    }
  };

  const resetAndFetch = () => {
    state.page = 1;
    fetchBundle({ append: false });
  };

  const wireControls = () => {
    if (els.pageSize) {
      els.pageSize.value = String(state.pageSize);
      els.pageSize.addEventListener("change", () => {
        state.pageSize = Math.max(1, Number.parseInt(els.pageSize.value || "50", 10) || 50);
        resetAndFetch();
      });
    }
    if (els.search) {
      let t = null;
      els.search.addEventListener("input", () => {
        window.clearTimeout(t);
        t = window.setTimeout(() => {
          state.search = (els.search.value || "").trim();
          resetAndFetch();
        }, 250);
      });
    }
    if (els.clearSearch) {
      els.clearSearch.addEventListener("click", () => {
        if (els.search) els.search.value = "";
        state.search = "";
        resetAndFetch();
      });
    }
    if (els.loadMore) {
      els.loadMore.addEventListener("click", () => {
        if (state.loading) return;
        const shown = els.tableBody.querySelectorAll("tr[data-row='supplier']").length;
        if (shown >= state.totalRows) return;
        state.page += 1;
        fetchBundle({ append: true });
      });
    }
    root.querySelectorAll(".segment-chip").forEach((btn) => {
      btn.addEventListener("click", () => {
        root.querySelectorAll(".segment-chip").forEach((el) => el.classList.remove("active"));
        btn.classList.add("active");
        state.quickFilter = btn.dataset.quick || "all";
        resetAndFetch();
      });
    });
    root.querySelectorAll("#supV2Table thead th.sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const sort = th.dataset.sort;
        if (!sort) return;
        if (state.sortBy === sort) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortBy = sort;
          state.sortDir = "desc";
        }
        resetAndFetch();
      });
    });
  };

  const onGlobalApply = (evt) => {
    const qs = (evt && evt.detail && evt.detail.qs) || "";
    state.filterQs = (qs || "").replace(/^\?/, "");
    resetAndFetch();
  };

  window.addEventListener("globalFilters:apply", onGlobalApply);
  wireControls();
  updateExportLinks();
  fetchBundle({ append: false });
})();
