(() => {
  const metaEl = document.getElementById("SalesRepDrilldownMeta");
  if (!metaEl) return;

  const authFetch = window.authFetch || fetch;
  const ChartLib = window.Chart;
  const bundleUrl = metaEl.dataset.bundleUrl || "/api/salesreps/drilldown/bundle";
  const repId = metaEl.dataset.entityId || "";
  const v2Enabled = metaEl.dataset.v2Enabled === "1";
  const charts = {};

  let controller = null;
  let filtersQS = window.location.search ? window.location.search.replace(/^\?/, "") : "";
  let bootstrapped = false;
  let currentReqId = 0;
  let trendGrain = "monthly";
  let trendRolling = false;
  let currentPayload = null;
  let customerRows = [];
  let productRows = [];

  if (document?.body?.dataset) {
    document.body.dataset.filtersHandler = "ajax";
  }

  const fmtMoney = new Intl.NumberFormat(undefined, {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 0,
  });
  const fmtInt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
  const fmtPct = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });
  const fmtFloat2 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
  const NA = "N/A";

  const waitForFiltersReady = async () => {
    const fallbackState = () => {
      try {
        return (window.getGlobalFilterState && window.getGlobalFilterState()) || {};
      } catch (_err) {
        return {};
      }
    };

    if (window.filtersReady && typeof window.filtersReady.then === "function") {
      try {
        const timeout = new Promise((resolve) => setTimeout(() => resolve(fallbackState()), 1500));
        return await Promise.race([window.filtersReady, timeout]);
      } catch (_err) {
        return fallbackState();
      }
    }

    return new Promise((resolve) => {
      const handler = (evt) => {
        cleanup();
        resolve(evt?.detail || {});
      };
      const cleanup = () => {
        document.removeEventListener("globalFilters:ready", handler);
        window.removeEventListener("globalFilters:ready", handler);
        clearTimeout(timer);
      };
      const timer = setTimeout(() => {
        cleanup();
        resolve(fallbackState());
      }, 1200);
      document.addEventListener("globalFilters:ready", handler, { once: true });
      window.addEventListener("globalFilters:ready", handler, { once: true });
    });
  };

  const safeNum = (value, fallback = 0) => {
    const num = Number(value);
    return Number.isFinite(num) ? num : fallback;
  };

  const safeOptional = (value) => {
    const num = Number(value);
    return Number.isFinite(num) ? num : null;
  };

  const formatCurrency = (value) => {
    const num = safeOptional(value);
    return num == null ? NA : fmtMoney.format(num);
  };

  const formatInt = (value) => fmtInt.format(safeNum(value));

  const formatPct = (value, scaleShare = false) => {
    const num = safeOptional(value);
    if (num == null) return NA;
    const display = scaleShare && num <= 1.01 ? num * 100 : num;
    return `${fmtPct.format(display)}%`;
  };

  const deltaClass = (value) => {
    const num = safeOptional(value);
    if (num == null) return "";
    if (num > 0) return "kpi-delta-positive";
    if (num < 0) return "kpi-delta-negative";
    return "";
  };

  const formatDelta = (value) => {
    const num = safeOptional(value);
    if (num == null) return "N/A";
    const sign = num > 0 ? "+" : "";
    return `${sign}${fmtPct.format(num)}%`;
  };

  const getCanvas = (id) => {
    const el = document.getElementById(id);
    if (!el || typeof el.getContext !== "function") return null;
    return el;
  };

  const destroyChart = (key) => {
    if (charts[key]?.destroy) {
      charts[key].destroy();
    }
    charts[key] = null;
  };

  const toggleEmpty = (canvasId, show, message = "No data for selected filters.") => {
    const canvas = getCanvas(canvasId);
    if (!canvas) return;
    const holder = canvas.parentElement;
    if (!holder) return;
    if (!holder.style.position) holder.style.position = "relative";

    let emptyEl = holder.querySelector("[data-empty-state]");
    if (!emptyEl) {
      emptyEl = document.createElement("div");
      emptyEl.dataset.emptyState = "1";
      emptyEl.className =
        "position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center text-muted small";
      emptyEl.style.background = "rgba(255,255,255,0.78)";
      emptyEl.style.pointerEvents = "none";
      holder.appendChild(emptyEl);
    }

    emptyEl.textContent = message;
    emptyEl.classList.toggle("d-none", !show);
    canvas.classList.toggle("d-none", !!show);
  };

  const setText = (id, text) => {
    const el = document.getElementById(id);
    if (el) el.textContent = text;
  };

  const csvList = (value) => {
    if (!value) return [];
    return String(value)
      .split(",")
      .map((v) => v.trim())
      .filter(Boolean);
  };

  const summarizeActiveFilters = (queryString) => {
    const params = new URLSearchParams(queryString || "");
    const ignore = new Set([
      "start",
      "end",
      "preset",
      "dataset",
      "format",
      "include_history",
      "rep_id",
      "salesrep_id",
      "sales_rep_id",
      "id",
      "export_type",
      "page",
      "page_size",
      "sort",
      "dir",
      "sort_dir",
    ]);
    const parts = [];
    params.forEach((rawValue, key) => {
      if (ignore.has(key)) return;
      const values = csvList(rawValue);
      if (!values.length) return;
      if (values.length === 1) {
        parts.push(`${key}: ${values[0]}`);
      } else {
        parts.push(`${key}: ${values.length} selected`);
      }
    });
    if (!parts.length) return "Filters: All";
    return `Filters: ${parts.slice(0, 4).join(" | ")}${parts.length > 4 ? " | ..." : ""}`;
  };

  const renderContext = (payload) => {
    const meta = payload?.meta || {};
    const kpis = payload?.kpis || {};
    const params = new URLSearchParams(filtersQS || "");

    const start = params.get("start") || meta.window_start || kpis.start || "--";
    const end = params.get("end") || meta.window_end || kpis.end || "--";
    setText("drDateChip", `Window: ${start} to ${end}`);
    setText("drFilterChip", summarizeActiveFilters(filtersQS));

    const lastRefresh = kpis.last_refresh || meta.last_refresh || "--";
    setText("drLastRefresh", `Last refresh: ${lastRefresh}`);

    const whatChanged = payload?.insights?.what_changed || kpis.what_changed || "No change summary available.";
    setText("drWhatChanged", whatChanged);
  };

  const renderKpis = (payload) => {
    const kpis = payload?.kpis || {};
    const meta = payload?.meta || {};

    const name = kpis.rep_name || meta.entity_label || repId || NA;
    setText("salesrepName", name);
    setText("salesrepId", kpis.rep_id || meta.entity_id || repId || NA);

    document.querySelectorAll("[data-kpi-key]").forEach((el) => {
      const key = el.dataset.kpiKey;
      if (!key) return;
      const value = kpis[key];
      if (["revenue", "profit", "cost", "asp", "asp_lb", "below_target_margin_revenue", "negative_margin_revenue"].includes(key)) {
        el.textContent = formatCurrency(value);
        return;
      }
      if (["margin_pct", "momentum_pct", "cost_coverage_pct"].includes(key)) {
        el.textContent = formatPct(value, false);
        return;
      }
      if (["top_customer_share", "top5_customer_share", "top_product_share"].includes(key)) {
        el.textContent = formatPct(value, true);
        return;
      }
      if (key === "customer_hhi") {
        const num = safeOptional(value);
        el.textContent = num == null ? NA : fmtFloat2.format(num);
        return;
      }
      if (["orders", "customers", "active_customers_curr", "active_customers_prev", "below_target_margin_skus", "negative_margin_skus", "weight_lb", "units"].includes(key)) {
        el.textContent = formatInt(value);
        return;
      }
      el.textContent = value == null || value === "" ? NA : String(value);
    });

    document.querySelectorAll("[data-kpi-delta]").forEach((el) => {
      const key = el.dataset.kpiDelta;
      if (!key) return;
      const value = kpis[key];
      if (key === "active_customers_delta") {
        const num = safeOptional(value);
        const text = num == null ? "Delta: N/A" : `Delta: ${num > 0 ? "+" : ""}${fmtInt.format(num)}`;
        el.textContent = text;
        el.className = `small mt-1 ${deltaClass(value)}`.trim();
        return;
      }
      const prefix = key.endsWith("_mom_pct") ? "MoM" : key.endsWith("_yoy_pct") ? "YoY" : "Delta";
      el.textContent = `${prefix}: ${formatDelta(value)}`;
      el.classList.remove("kpi-delta-positive", "kpi-delta-negative");
      const cls = deltaClass(value);
      if (cls) el.classList.add(cls);
    });

    setText("drBelowTargetCount", formatInt(kpis.below_target_margin_skus));
    setText("drNegativeMarginCount", formatInt(kpis.negative_margin_skus));
  };

  const latestTrendText = (labels, revenue, profit) => {
    if (!labels?.length) return "";
    const idx = labels.length - 1;
    const month = labels[idx] || "Latest";
    const revText = formatCurrency(revenue?.[idx]);
    const profitText = formatCurrency(profit?.[idx]);
    return `Latest ${month}: Revenue ${revText} | Profit ${profitText}`;
  };

  const renderTrend = () => {
    const canvasId = "drTrend";
    const canvas = getCanvas(canvasId);
    if (!canvas || !ChartLib) return;

    const trendRoot = currentPayload?.trend || {};
    const trend = trendRoot[trendGrain] || trendRoot.monthly || currentPayload?.charts?.trend || {};

    const labels = Array.isArray(trend.labels) ? trend.labels : [];
    const revenue = Array.isArray(trend.revenue) ? trend.revenue : [];
    const profit = Array.isArray(trend.profit) ? trend.profit : [];
    const margin = Array.isArray(trend.margin_pct) ? trend.margin_pct : [];
    const hasData = labels.length > 0;
    toggleEmpty(canvasId, !hasData);

    destroyChart("trend");
    if (!hasData) return;

    const datasets = [
      {
        label: "Revenue",
        data: revenue,
        borderColor: "#0d6efd",
        backgroundColor: "rgba(13,110,253,0.10)",
        borderWidth: 2,
        tension: 0.25,
      },
    ];

    if (profit.some((v) => safeOptional(v) != null)) {
      datasets.push({
        label: "Profit",
        data: profit,
        borderColor: "#198754",
        backgroundColor: "rgba(25,135,84,0.10)",
        borderWidth: 2,
        tension: 0.25,
      });
    }

    if (margin.some((v) => safeOptional(v) != null)) {
      datasets.push({
        label: "Margin %",
        data: margin,
        borderColor: "#fd7e14",
        backgroundColor: "rgba(253,126,20,0.10)",
        borderWidth: 2,
        tension: 0.25,
        yAxisID: "y1",
      });
    }

    if (trendRolling) {
      const rollingRevenue = trendGrain === "weekly" ? trend.rolling_revenue_4w : trend.rolling_revenue_3m;
      if (Array.isArray(rollingRevenue) && rollingRevenue.some((v) => safeOptional(v) != null)) {
        datasets.push({
          label: trendGrain === "weekly" ? "Revenue 4W Avg" : "Revenue 3M Avg",
          data: rollingRevenue,
          borderColor: "#6c757d",
          backgroundColor: "rgba(108,117,125,0.08)",
          borderWidth: 2,
          borderDash: [6, 4],
          tension: 0.25,
        });
      }
      const rollingProfit = trend.rolling_profit_3m;
      if (trendGrain === "monthly" && Array.isArray(rollingProfit) && rollingProfit.some((v) => safeOptional(v) != null)) {
        datasets.push({
          label: "Profit 3M Avg",
          data: rollingProfit,
          borderColor: "#20c997",
          backgroundColor: "rgba(32,201,151,0.08)",
          borderWidth: 2,
          borderDash: [6, 4],
          tension: 0.25,
        });
      }
    }

    const subtitle = latestTrendText(labels, revenue, profit);
    charts.trend = new ChartLib(canvas, {
      type: "line",
      data: {
        labels,
        datasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        plugins: {
          legend: { position: "bottom" },
          subtitle: { display: !!subtitle, text: subtitle },
        },
        scales: {
          y: { beginAtZero: true },
          y1: {
            beginAtZero: true,
            position: "right",
            grid: { drawOnChartArea: false },
          },
        },
      },
    });
  };

  const renderConcentration = () => {
    const canvasId = "drConcentration";
    const canvas = getCanvas(canvasId);
    if (!canvas || !ChartLib) return;

    const concentration = currentPayload?.charts?.concentration || {};
    const top1 = safeOptional(concentration.top_customer_share);
    const top5 = safeOptional(concentration.top5_customer_share);

    const labels = ["Top 1", "Top 5"];
    const data = [top1 == null ? null : top1 * 100, top5 == null ? null : top5 * 100];
    const hasData = data.some((v) => safeOptional(v) != null);

    toggleEmpty(canvasId, !hasData);
    destroyChart("concentration");
    if (!hasData) return;

    charts.concentration = new ChartLib(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [
          {
            label: "Share %",
            data,
            backgroundColor: ["#dc3545", "#fd7e14"],
          },
        ],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        plugins: { legend: { display: false } },
        scales: {
          y: {
            beginAtZero: true,
            ticks: {
              callback: (value) => `${value}%`,
            },
          },
        },
      },
    });

    const hhi = safeOptional(concentration.customer_hhi ?? currentPayload?.kpis?.customer_hhi);
    setText("drHHI", hhi == null ? NA : fmtFloat2.format(hhi));
  };

  const topNRows = (rows, n = 10) => (Array.isArray(rows) ? rows.slice(0, n) : []);

  const renderMix = () => {
    const products = topNRows(currentPayload?.charts?.mix || currentPayload?.charts?.top_products || currentPayload?.tables?.products || [], 10);

    const mixBarCanvas = getCanvas("drMixBar");
    if (mixBarCanvas && ChartLib) {
      destroyChart("mixBar");
      const labels = products.map((r) => r.product_name || r.product_id || "Product");
      const data = products.map((r) => safeNum(r.revenue));
      toggleEmpty("drMixBar", labels.length === 0);
      if (labels.length > 0) {
        charts.mixBar = new ChartLib(mixBarCanvas, {
          type: "bar",
          data: {
            labels,
            datasets: [{ label: "Revenue", data, backgroundColor: "#0d6efd" }],
          },
          options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: { legend: { display: false } },
            scales: { x: { beginAtZero: true } },
          },
        });
      }
    }

    const mixCanvas = getCanvas("drMix");
    if (mixCanvas && ChartLib) {
      destroyChart("mix");
      const labels = products.map((r) => r.product_name || r.product_id || "Product");
      const data = products.map((r) => safeNum(r.revenue));
      toggleEmpty("drMix", labels.length === 0);
      if (labels.length > 0) {
        charts.mix = new ChartLib(mixCanvas, {
          type: "doughnut",
          data: { labels, datasets: [{ data }] },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
              legend: {
                position: "bottom",
                labels: { boxWidth: 12 },
              },
            },
          },
        });
      }
    }
  };

  const renderCustomersChart = () => {
    const canvas = getCanvas("drCustomers");
    if (!canvas || !ChartLib) return;

    const rows = topNRows(currentPayload?.charts?.top_customers || currentPayload?.tables?.customers || [], 10);
    const labels = rows.map((r) => r.customer_name || r.customer_id || "Customer");
    const data = rows.map((r) => safeNum(r.revenue));

    toggleEmpty("drCustomers", labels.length === 0);
    destroyChart("customers");
    if (!labels.length) return;

    charts.customers = new ChartLib(canvas, {
      type: "bar",
      data: {
        labels,
        datasets: [{ label: "Revenue", data, backgroundColor: "#0d6efd" }],
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: { y: { beginAtZero: true } },
        plugins: { legend: { display: false } },
      },
    });
  };

  const rowDrillUrl = (type, idValue) => {
    const id = String(idValue || "").trim();
    if (!id) return "";
    const encoded = encodeURIComponent(id);
    let base;
    if (type === "customer") {
      base = `/customers/drilldown/${encoded}`;
    } else if (type === "product") {
      base = `/products/${encoded}/drilldown`;
    } else {
      return "";
    }

    const params = new URLSearchParams(filtersQS || "");
    if (repId) {
      params.set("salesrep_id", repId);
    }
    const qs = params.toString();
    return qs ? `${base}?${qs}` : base;
  };

  const attachRowLink = (tr, url) => {
    if (!tr || !url) return;
    tr.classList.add("drill-row-link");
    tr.setAttribute("role", "link");
    tr.tabIndex = 0;
    tr.addEventListener("click", () => {
      window.location.assign(url);
    });
    tr.addEventListener("keydown", (evt) => {
      if (evt.key === "Enter" || evt.key === " ") {
        evt.preventDefault();
        window.location.assign(url);
      }
    });
  };

  const renderDecomposition = () => {
    const tbody = document.getElementById("drDecompTable");
    if (!tbody) return;

    const decomp = currentPayload?.decomposition || {};
    const rows = [
      ["Price", decomp.price_impact],
      ["Volume", decomp.volume_impact],
      ["Mix", decomp.mix_impact],
      ["Total", decomp.total_change],
    ];

    tbody.innerHTML = "";
    if (!rows.some((r) => safeOptional(r[1]) != null)) {
      tbody.innerHTML = '<tr><td colspan="2" class="text-muted">Not enough data for decomposition.</td></tr>';
    } else {
      rows.forEach(([label, value]) => {
        const tr = document.createElement("tr");
        const cls = safeNum(value) < 0 ? "text-danger" : "text-success";
        tr.innerHTML = `<td>${label}</td><td class="text-end ${cls}">${formatCurrency(value)}</td>`;
        tbody.appendChild(tr);
      });
    }

    const method = decomp.methodology || "--";
    setText("drDecompMethod", `Method: ${method}`);
  };

  const renderMoversTable = (tbodyId, movers, nameKey) => {
    const tbody = document.getElementById(tbodyId);
    if (!tbody) return;

    const gainers = Array.isArray(movers?.gainers) ? movers.gainers.slice(0, 5) : [];
    const decliners = Array.isArray(movers?.decliners) ? movers.decliners.slice(0, 5) : [];
    const combined = [...gainers, ...decliners];

    tbody.innerHTML = "";
    if (!combined.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="text-muted">No movers for this period.</td></tr>';
      return;
    }

    combined.forEach((row) => {
      const name = row[nameKey] || row[`${nameKey.replace("_name", "")}_id`] || NA;
      const delta = safeOptional(row.mom_revenue_delta ?? row.delta_revenue);
      const pct = safeOptional(row.mom_revenue_pct ?? row.delta_revenue_pct);
      const cls = delta == null ? "" : delta >= 0 ? "text-success" : "text-danger";

      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${name}</td>
        <td class="text-end ${cls}">${formatCurrency(delta)}</td>
        <td class="text-end ${cls}">${formatPct(pct, false)}</td>
      `;
      tbody.appendChild(tr);
    });
  };

  const renderRiskFlags = () => {
    const list = document.getElementById("drRiskFlags");
    if (!list) return;

    const flags = Array.isArray(currentPayload?.risk_flags) ? currentPayload.risk_flags : [];
    const atRisk = Array.isArray(currentPayload?.tables?.at_risk_customers) ? currentPayload.tables.at_risk_customers.length : 0;
    setText("drAtRiskCount", formatInt(atRisk));

    list.innerHTML = "";
    if (!flags.length) {
      list.innerHTML = '<li class="list-group-item px-0 text-muted">No risk flags triggered.</li>';
      return;
    }

    flags.forEach((flag) => {
      const severity = String(flag.severity || "ok").toLowerCase();
      const badgeClass = severity === "high" ? "bg-danger" : severity === "medium" ? "bg-warning text-dark" : "bg-success";
      const label = flag.label || flag.key || "Risk";
      const count = formatInt(flag.count);

      const item = document.createElement("li");
      item.className = "list-group-item px-0 d-flex justify-content-between align-items-center";
      item.innerHTML = `
        <span>${label}</span>
        <span><span class="badge ${badgeClass}">${severity}</span> <span class="ms-1">${count}</span></span>
      `;
      list.appendChild(item);
    });
  };

  const renderMarginRiskTable = () => {
    const tbody = document.getElementById("drMarginRiskTable");
    if (!tbody) return;

    const rows = topNRows(currentPayload?.tables?.margin_risk_products || [], 10);
    tbody.innerHTML = "";
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="4" class="text-muted">No margin leakage products in scope.</td></tr>';
      return;
    }

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.product_name || row.product_id || NA}</td>
        <td class="text-end ${safeNum(row.margin_pct) < 0 ? "text-danger" : ""}">${formatPct(row.margin_pct, false)}</td>
        <td class="text-end">${formatCurrency(row.leakage_to_target)}</td>
        <td class="text-end">${formatCurrency(row.revenue)}</td>
      `;
      const url = rowDrillUrl("product", row.product_id || row.product_name);
      attachRowLink(tr, url);
      tbody.appendChild(tr);
    });
  };

  const normalizeRows = (rows) => (Array.isArray(rows) ? rows : []);

  const filterRowsByQuery = (rows, query, keys) => {
    const q = String(query || "").trim().toLowerCase();
    if (!q) return rows;
    return rows.filter((row) => keys.some((key) => String(row[key] || "").toLowerCase().includes(q)));
  };

  const renderCustomersTable = () => {
    const tbody = document.getElementById("drCustomersTable");
    if (!tbody) return;

    const query = document.getElementById("drCustomerSearch")?.value || "";
    const rows = filterRowsByQuery(customerRows, query, ["customer_name", "customer_id"]);
    const threshold = safeNum(currentPayload?.meta?.risk_thresholds?.margin_pct, 27);

    tbody.innerHTML = "";
    if (!rows.length) {
      const colspan = v2Enabled ? 10 : 3;
      tbody.innerHTML = `<tr><td colspan="${colspan}" class="text-muted">No customer data.</td></tr>`;
      return;
    }

    rows.slice(0, 250).forEach((row) => {
      const tr = document.createElement("tr");
      const margin = safeOptional(row.margin_pct);
      const marginBadgeClass = margin != null && margin < threshold ? "bg-danger" : "bg-success";

      if (v2Enabled) {
        tr.innerHTML = `
          <td>${row.customer_name || row.customer_id || NA}</td>
          <td class="text-end">${formatCurrency(row.revenue)}</td>
          <td class="text-end">${formatCurrency(row.profit)}</td>
          <td class="text-end"><span class="badge ${marginBadgeClass}">${formatPct(margin, false)}</span></td>
          <td class="text-end">${formatInt(row.orders)}</td>
          <td class="text-end">${formatInt(row.weight_lb)}</td>
          <td class="text-end">${formatCurrency(row.asp_lb)}</td>
          <td class="text-end">${formatCurrency(row.mom_revenue_delta)}</td>
          <td class="text-end">${formatPct(row.mom_revenue_pct, false)}</td>
          <td class="text-end">${row.last_order_date || NA}</td>
        `;
      } else {
        tr.innerHTML = `
          <td>${row.customer_name || row.customer_id || NA}</td>
          <td class="text-end">${formatCurrency(row.revenue)}</td>
          <td class="text-end">${formatInt(row.orders)}</td>
        `;
      }

      const url = rowDrillUrl("customer", row.customer_id || row.customer_name);
      attachRowLink(tr, url);
      tbody.appendChild(tr);
    });
  };

  const renderProductsTable = () => {
    const tbody = document.getElementById("drProductsTable");
    if (!tbody) return;

    const query = document.getElementById("drProductSearch")?.value || "";
    const rows = filterRowsByQuery(productRows, query, ["product_name", "product_id"]);
    const threshold = safeNum(currentPayload?.meta?.risk_thresholds?.margin_pct, 27);

    tbody.innerHTML = "";
    if (!rows.length) {
      const colspan = v2Enabled ? 11 : 3;
      tbody.innerHTML = `<tr><td colspan="${colspan}" class="text-muted">No product data.</td></tr>`;
      return;
    }

    rows.slice(0, 250).forEach((row) => {
      const tr = document.createElement("tr");
      const margin = safeOptional(row.margin_pct);
      const marginBadgeClass = margin != null && margin < threshold ? "bg-danger" : "bg-success";

      if (v2Enabled) {
        tr.innerHTML = `
          <td>${row.product_name || row.product_id || NA}</td>
          <td class="text-end">${formatCurrency(row.revenue)}</td>
          <td class="text-end">${formatCurrency(row.profit)}</td>
          <td class="text-end"><span class="badge ${marginBadgeClass}">${formatPct(margin, false)}</span></td>
          <td class="text-end">${formatInt(row.orders)}</td>
          <td class="text-end">${formatInt(row.weight_lb)}</td>
          <td class="text-end">${formatCurrency(row.asp_lb)}</td>
          <td class="text-end">${formatCurrency(row.mom_revenue_delta)}</td>
          <td class="text-end">${formatPct(row.mom_revenue_pct, false)}</td>
          <td class="text-end">${formatPct(row.price_change_pct, false)}</td>
          <td class="text-end">${row.last_order_date || NA}</td>
        `;
      } else {
        tr.innerHTML = `
          <td>${row.product_name || row.product_id || NA}</td>
          <td class="text-end">${formatCurrency(row.revenue)}</td>
          <td class="text-end">${formatInt(row.orders)}</td>
        `;
      }

      const url = rowDrillUrl("product", row.product_id || row.product_name);
      attachRowLink(tr, url);
      tbody.appendChild(tr);
    });
  };

  const renderAtRiskTable = () => {
    const tbody = document.getElementById("drAtRiskTable");
    if (!tbody) return;

    const rows = topNRows(currentPayload?.tables?.at_risk_customers || [], 100);
    tbody.innerHTML = "";

    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="text-muted">No at-risk customers in this window.</td></tr>';
      return;
    }

    rows.forEach((row) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${row.customer_name || row.customer_id || NA}</td>
        <td class="text-end">${formatInt(row.days_since_last_order)}</td>
        <td class="text-end">${formatCurrency(row.prior_period_revenue)}</td>
      `;
      const url = rowDrillUrl("customer", row.customer_id || row.customer_name);
      attachRowLink(tr, url);
      tbody.appendChild(tr);
    });
  };

  const initTrendControls = () => {
    document.querySelectorAll("[data-trend-grain]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const next = btn.dataset.trendGrain;
        if (!next || next === trendGrain) return;
        trendGrain = next;
        document.querySelectorAll("[data-trend-grain]").forEach((b) => {
          b.classList.toggle("active", b.dataset.trendGrain === trendGrain);
        });
        renderTrend();
      });
    });

    const toggle = document.getElementById("drTrendRollingToggle");
    if (toggle) {
      toggle.addEventListener("change", () => {
        trendRolling = !!toggle.checked;
        renderTrend();
      });
    }
  };

  const initSearchInputs = () => {
    const customerSearch = document.getElementById("drCustomerSearch");
    if (customerSearch) {
      customerSearch.addEventListener("input", () => renderCustomersTable());
    }

    const productSearch = document.getElementById("drProductSearch");
    if (productSearch) {
      productSearch.addEventListener("input", () => renderProductsTable());
    }
  };

  const initTooltips = () => {
    if (!window.bootstrap || !window.bootstrap.Tooltip) return;
    document.querySelectorAll('[title]').forEach((el) => {
      if (el.dataset.tooltipBound === "1") return;
      try {
        new window.bootstrap.Tooltip(el, { trigger: "hover focus" });
        el.dataset.tooltipBound = "1";
      } catch (_err) {
        // ignore tooltip init failures
      }
    });
  };

  const updateExportLink = () => {
    const links = Array.from(document.querySelectorAll("a[data-export-dataset]"));
    links.forEach((link) => {
      const base = link.dataset.baseHref || link.getAttribute("href") || "";
      const baseHref = base.split("?")[0];
      link.dataset.baseHref = baseHref;

      const params = new URLSearchParams(filtersQS || "");
      const dataset = link.dataset.exportDataset || "all";
      const format = link.dataset.exportFormat || "xlsx";
      params.set("dataset", dataset);
      params.set("export_type", dataset);
      params.set("format", format);
      if (link.dataset.includeHistory === "1") {
        params.set("include_history", "1");
      }
      const qs = params.toString();
      link.setAttribute("href", qs ? `${baseHref}?${qs}` : baseHref);
    });
  };

  const renderV2OnlyBlocks = () => {
    if (!v2Enabled) return;
    renderContext(currentPayload || {});
    renderDecomposition();
    renderMoversTable(
      "drMoversCustomersTable",
      currentPayload?.tables?.movers_customers,
      "customer_name"
    );
    renderMoversTable(
      "drMoversProductsTable",
      currentPayload?.tables?.movers_products,
      "product_name"
    );
    renderConcentration();
    renderRiskFlags();
    renderAtRiskTable();
    renderMarginRiskTable();
  };

  const hydrate = (payload) => {
    currentPayload = window.normalizeBundlePayload ? window.normalizeBundlePayload(payload) : payload;

    const tables = currentPayload?.tables || {};
    const chartsPayload = currentPayload?.charts || {};
    customerRows = normalizeRows(tables.customers || chartsPayload.top_customers || currentPayload?.table?.rows);
    productRows = normalizeRows(tables.products || chartsPayload.top_products || []);

    renderKpis(currentPayload);
    renderTrend();
    renderMix();
    renderCustomersChart();
    renderCustomersTable();
    renderProductsTable();
    renderV2OnlyBlocks();
  };

  const buildQS = () => {
    const params = new URLSearchParams(filtersQS || "");
    if (repId) params.set("salesrep_id", repId);
    return params.toString();
  };

  const fetchBundle = async () => {
    if (!bundleUrl) return;
    if (controller) controller.abort();
    controller = new AbortController();

    const qs = buildQS();
    const url = qs ? `${bundleUrl}?${qs}` : bundleUrl;
    const reqId = ++currentReqId;

    try {
      const res = await authFetch(url, {
        signal: controller.signal,
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      const payload = await res.json();
      if (reqId !== currentReqId) return;
      if (!res.ok) {
        throw new Error(payload?.error?.message || `HTTP ${res.status}`);
      }
      hydrate(payload);
    } catch (err) {
      if (err?.name === "AbortError") return;
      console.error("salesrep drilldown bundle failed", err);
      ["drTrend", "drMix", "drMixBar", "drCustomers", "drConcentration"].forEach((id) => {
        toggleEmpty(id, true);
      });
    } finally {
      if (reqId === currentReqId) {
        try {
          window.dispatchEvent(new CustomEvent("globalFilters:applied", { detail: { qs: filtersQS } }));
        } catch (_err) {
          // ignore
        }
      }
    }
  };

  const replaceHistory = () => {
    if (!window.history || typeof window.history.replaceState !== "function") return;
    const qs = filtersQS ? `?${filtersQS}` : "";
    window.history.replaceState({}, "", `${window.location.pathname}${qs}`);
  };

  const bootstrap = async (qsHint) => {
    if (bootstrapped) return;
    bootstrapped = true;

    let qs = qsHint || "";
    if (!qs) {
      const ready = await waitForFiltersReady();
      qs = ready?.qs || "";
    }
    filtersQS = (qs || filtersQS || "").replace(/^\?/, "");

    replaceHistory();
    updateExportLink();
    initTooltips();
    initTrendControls();
    initSearchInputs();
    fetchBundle();
  };

  const onApply = (evt) => {
    const qs = (evt?.detail && evt.detail.qs) || "";
    filtersQS = String(qs || "").replace(/^\?/, "");
    replaceHistory();
    updateExportLink();
    fetchBundle();
  };

  window.addEventListener("globalFilters:apply", onApply);
  window.addEventListener("globalFilters:ready", (evt) => bootstrap((evt?.detail && evt.detail.qs) || ""));

  bootstrap();
})();
