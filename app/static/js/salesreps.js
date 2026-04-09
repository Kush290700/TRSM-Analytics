(() => {
  const root = document.getElementById("SalesRepsApp");
  if (!root) return;

  const authFetch = window.authFetch || window.fetch.bind(window);
  const pageCache = window.analyticsPageCache || null;
  const bundleUrl = root.dataset.bundleUrl || "/api/salesreps/bundle";
  const exportXlsx = document.getElementById("salesrepsExportXlsx");
  const exportCsv = document.getElementById("salesrepsExportCsv");
  const actionCrm = document.getElementById("salesrepsActionCrm");
  const actionSlack = document.getElementById("salesrepsActionSlack");
  const drilldownTemplate = root.dataset.drilldownTemplate || "";
  const ChartLib = window.Chart;
  const PAGE_CACHE_ID = "salesreps";
  const PAGE_CACHE_POLICY = { freshMs: 90 * 1000, maxAgeMs: 20 * 60 * 1000 };
  const LOCALE = "en-CA";
  const CURRENCY = "CAD";

  const NA = "N/A";
  const fmtMoney0 = new Intl.NumberFormat(LOCALE, { style: "currency", currency: CURRENCY, maximumFractionDigits: 0 });
  const fmtMoney2 = new Intl.NumberFormat(LOCALE, { style: "currency", currency: CURRENCY, minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const fmtInt = new Intl.NumberFormat(LOCALE, { maximumFractionDigits: 0 });
  const fmtPct = new Intl.NumberFormat(LOCALE, { minimumFractionDigits: 1, maximumFractionDigits: 1 });
  const READABLE_REP_FALLBACK = "Needs Review";
  const UNASSIGNED_REP_FALLBACK = "Unassigned / Needs Review";
  const CHART_IDS = [
    "trendChart",
    "topRepsChart",
    "monthlyCompareChart",
    "transferChart",
    "srProteinChart",
    "concentrationChart",
    "effChart",
    "profitRevenueChart",
    "revenueShareChart",
    "aspChart",
    "srTerritoryChart",
  ];
  const COLUMN_STORAGE_KEY = "salesreps.columnVisibility.v1";
  const DEFAULT_COLUMN_VISIBILITY = {
    revenue: true,
    profit: true,
    margin_pct: true,
    weight_lb: true,
    active_customers: true,
    current_owned_customers: true,
    inherited_customers: true,
    transferred_in_revenue: true,
    transferred_out_revenue: true,
    yoy_revenue_pct: true,
    territory_count: true,
    replaced_reps: false,
    top_territory: false,
    top_customer: true,
    top_protein: true,
    flags: true,
  };
  const SAFE_REP_BUCKET_ALIASES = new Map([
    ["unassigned", UNASSIGNED_REP_FALLBACK],
    ["unassigned / needs review", UNASSIGNED_REP_FALLBACK],
    ["unknown rep", READABLE_REP_FALLBACK],
    ["needs mapping", READABLE_REP_FALLBACK],
    ["needs review", READABLE_REP_FALLBACK],
  ]);
  const SAFE_REP_BUCKETS = new Set(Array.from(SAFE_REP_BUCKET_ALIASES.values()).map((value) => value.toLowerCase()));
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
    trendMetric: "revenue",
    trendGrain: "monthly",
    trendView: "absolute",
    trendSelectedReps: [],
    trendFocusMode: false,
    topN: 10,
    topCustomersSortBy: "revenue",
    topCustomersSortDir: "desc",
    proteinSortBy: "revenue",
    proteinSortDir: "desc",
    attributionMode: "current_owner",
    rosterMode: "current_only",
    transferOnly: false,
    focusedRepIds: [],
    focusedRepLabels: [],
    scrollToFocusedRep: false,
  };

  // ── 4D: Rep comparison state ──
  let selectedRepIds = new Set();
  let selectedRepRows = new Map();

  const charts = {};
  let currentAbort = null;
  let reqId = 0;
  let currentApplyId = "";
  let bootstrapped = false;
  let lastPayload = null;
  let deferredChartToken = 0;
  const deferredChartTimers = new Set();
  const renderMemo = new Map();
  const virtualTable = {
    wrapper: null,
    tbody: null,
    rows: [],
    rowHeight: 88,
    overscan: 6,
    lastRange: "",
    scheduled: false,
  };

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

  const fmtSignedPoints = (value) => {
    const numeric = opt(value);
    if (numeric === null) return "";
    return `${numeric > 0 ? "+" : ""}${fmtPct.format(numeric)} pts`;
  };

  const money = (v, compact = true) => {
    const n = opt(v);
    if (n === null) return NA;
    return compact ? fmtMoney0.format(n) : fmtMoney2.format(n);
  };

  const setScorecardLoading = (loading) => {
    document.getElementById("srKpiGrid")?.classList.toggle("sr-kpi-grid--loading", !!loading);
  };

  const setSummaryNarrativeLoading = (loading) => {
    document.getElementById("srSummaryNarrative")?.classList.toggle("sr-summary-narrative--loading", !!loading);
  };

  const chartShellFor = (canvasId) => document.getElementById(canvasId)?.parentElement || null;

  const setChartShellLoading = (canvasId, loading) => {
    const shell = chartShellFor(canvasId);
    if (shell) shell.classList.toggle("sr-chart-shell--loading", !!loading);
  };

  const setAllChartsLoading = (loading) => {
    CHART_IDS.forEach((canvasId) => setChartShellLoading(canvasId, loading));
  };

  const clearDeferredChartWork = () => {
    deferredChartToken += 1;
    deferredChartTimers.forEach((entry) => {
      if (entry?.idle && typeof window.cancelIdleCallback === "function") {
        window.cancelIdleCallback(entry.handle);
        return;
      }
      window.clearTimeout(entry?.handle);
    });
    deferredChartTimers.clear();
  };

  const scheduleDeferredChartWork = (fn, { delay = 0, idle = false } = {}) => {
    const token = deferredChartToken;
    const entry = { handle: null, idle: false };
    const run = () => {
      deferredChartTimers.delete(entry);
      if (token !== deferredChartToken) return;
      fn();
    };
    if (idle && typeof window.requestIdleCallback === "function") {
      entry.handle = window.requestIdleCallback(run, { timeout: 800 });
      entry.idle = true;
      deferredChartTimers.add(entry);
      return;
    }
    entry.handle = window.setTimeout(run, delay);
    deferredChartTimers.add(entry);
  };

  const signatureForRows = (rows = [], keys = []) =>
    JSON.stringify(
      (Array.isArray(rows) ? rows : []).map((row) => keys.map((key) => row?.[key] ?? null))
    );

  const memoizedRender = (key, signature, renderFn) => {
    if (renderMemo.get(key) === signature) return false;
    renderMemo.set(key, signature);
    renderFn();
    return true;
  };

  const readColumnVisibility = () => {
    try {
      const raw = window.localStorage?.getItem(COLUMN_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : {};
      return { ...DEFAULT_COLUMN_VISIBILITY, ...(parsed || {}) };
    } catch (_err) {
      return { ...DEFAULT_COLUMN_VISIBILITY };
    }
  };

  const persistColumnVisibility = (visibility) => {
    try {
      window.localStorage?.setItem(COLUMN_STORAGE_KEY, JSON.stringify(visibility || DEFAULT_COLUMN_VISIBILITY));
    } catch (_err) {
      /* ignore */
    }
  };

  let columnVisibility = readColumnVisibility();

  const cleanText = (value) => {
    const text = String(value ?? "").trim();
    if (!text || ["none", "null", "nan"].includes(text.toLowerCase())) return "";
    return text;
  };

  const normalizeRepBucket = (value) => {
    const text = cleanText(value);
    if (!text) return "";
    return SAFE_REP_BUCKET_ALIASES.get(text.toLowerCase()) || "";
  };

  const marginStatusKey = (value) => String(value || "").trim().toLowerCase();
  const marginStatusClass = (value) => {
    const key = marginStatusKey(value);
    if (key === "red") return "is-red";
    if (key === "orange") return "is-orange";
    if (key === "yellow") return "is-yellow";
    if (key === "light_green") return "is-light-green";
    if (key === "green") return "is-green";
    return "is-neutral";
  };
  const marginStatusLabel = (row = {}) => row?.target_status || row?.profitability_band || "Needs review";
  const isCriticalMargin = (row = {}) => {
    const actual = opt(row.margin_pct);
    const minimum = opt(row.minimum_margin_pct);
    return actual !== null && minimum !== null && actual < minimum;
  };
  const marginContextText = (row = {}) => {
    const parts = [];
    if (row.target_margin_pct != null) parts.push(`Target ${pct(row.target_margin_pct)}`);
    if (row.minimum_margin_pct != null) parts.push(`Min ${pct(row.minimum_margin_pct)}`);
    if (row.target_gap_pct_points != null) {
      parts.push(`${fmtSignedPoints(row.target_gap_pct_points)} vs target`);
    } else if (row.target_status) {
      parts.push(row.target_status);
    }
    return parts.join(" · ");
  };
  const marginCellHtml = (row = {}) => {
    const marginPct   = opt(row.margin_pct);
    const targetMgn   = opt(row.target_margin_pct);
    const minMgn      = opt(row.minimum_margin_pct);
    const context     = marginContextText(row);
    const critical    = isCriticalMargin(row);

    // ── Phase 4A: threshold-based pill (replaces generic "Needs review") ──
    let pill = "";
    if (marginPct != null && (targetMgn != null || minMgn != null)) {
      const t = targetMgn ?? Infinity;
      const m = minMgn  ?? -Infinity;
      if (marginPct >= t) {
        pill = '<span class="sr-margin-pill sr-margin-above">&#10003; On target</span>';
      } else if (marginPct >= m) {
        pill = '<span class="sr-margin-pill sr-margin-mid">&#9888; Below target</span>';
      } else {
        pill = '<span class="sr-margin-pill sr-margin-low">&#10007; Below min</span>';
      }
    } else if (critical) {
      pill = '<span class="sr-margin-pill sr-margin-low">&#10007; Critical</span>';
    } else {
      const status = marginStatusLabel(row);
      if (status && status !== "Needs review") {
        pill = `<span class="sr-status-pill ${marginStatusClass(row.status_key)}">${escapeHtml(status)}</span>`;
      }
    }

    return `
      <div class="sr-metric-stack sr-metric-stack-end">
        <div>${pct(marginPct, false)}</div>
        ${context || pill ? `<div class="sr-metric-sub">${pill}${context ? `${pill ? " " : ""}<span>${escapeHtml(context)}</span>` : ""}</div>` : ""}
      </div>
    `;
  };

  const isTechnicalRepId = (value) => {
    const text = cleanText(value);
    if (!text) return false;
    if (normalizeRepBucket(text)) return false;
    const lower = text.toLowerCase();
    if (SAFE_REP_BUCKETS.has(lower)) return false;
    if (/@|\/|\\/.test(text)) return true;
    if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(text)) return true;
    if (!/\s/.test(text) && /\d/.test(text) && /^[A-Za-z]{1,6}[-_ ]?\d[\w-]*$/.test(text)) return true;
    return !/\s/.test(text) && text.length >= 12 && /^[A-Za-z0-9_-]+$/.test(text);
  };

  const businessRepName = (name, fallbackId = null, defaultLabel = READABLE_REP_FALLBACK) => {
    const primary = cleanText(name);
    const fallback = cleanText(fallbackId);
    for (const candidate of [primary, fallback]) {
      if (!candidate) continue;
      const normalized = normalizeRepBucket(candidate);
      if (normalized) return normalized;
      if (!isTechnicalRepId(candidate)) return candidate;
    }
    return defaultLabel;
  };

  const repDisplayName = (row, defaultLabel = READABLE_REP_FALLBACK) =>
    businessRepName(row?.rep_name || row?.repName || row?.label, row?.rep_id || row?.repId || row?.key, defaultLabel);

  const currentFilterState = () => {
    try {
      const globalState = window.getGlobalFilterState ? window.getGlobalFilterState() : {};
      if (globalState?.filters && typeof globalState.filters === "object") return globalState.filters;
    } catch (_err) {
      /* ignore */
    }
    return {};
  };

  const focusedRepIdsFromFilters = (filters = {}) =>
    Array.from(
      new Set(
        (Array.isArray(filters?.sales_reps) ? filters.sales_reps : [])
          .map((value) => String(value || "").trim())
          .filter(Boolean)
      )
    );

  const focusedRepLabelsFromIds = (repIds = []) => {
    if (typeof window.getFilterLabels === "function") {
      const labels = window.getFilterLabels("sales_reps", repIds) || [];
      const cleaned = labels.map((value) => String(value || "").trim()).filter(Boolean);
      if (cleaned.length) return cleaned;
    }
    return repIds;
  };

  const syncFocusedReps = (filters = {}, { scroll = false } = {}) => {
    state.focusedRepIds = focusedRepIdsFromFilters(filters);
    state.focusedRepLabels = focusedRepLabelsFromIds(state.focusedRepIds);
    state.scrollToFocusedRep = !!scroll && state.focusedRepIds.length > 0;
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

  const currentTargetQuery = () => ({
    attribution_mode: state.attributionMode,
    roster_mode: state.rosterMode,
    transfer_only: !!state.transferOnly,
    metric: state.metric,
    leaderboard_metric: state.metric,
    trend_metric: state.trendMetric,
    trend_grain: state.trendGrain,
    trend_view: state.trendView,
    top_n: state.topN,
  });

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
      clicked_entity_label: repDisplayName(row, READABLE_REP_FALLBACK),
      clicked_metric: metric,
      clicked_metric_value: value,
      active_filter_state: currentFilterState(),
      target_query: currentTargetQuery(),
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
    target_query: currentTargetQuery(),
    extra,
  });

  const entityPayload = (target, section, widget, entityType, entityId, label, metric, value, extra = {}) => {
    if (!entityId) return null;
    return {
      source_page: "salesreps",
      source_section: section,
      source_widget: widget,
      requested_target: target,
      clicked_entity_type: entityType,
      clicked_entity_id: String(entityId),
      clicked_entity_label: cleanText(label) || String(entityId),
      clicked_metric: metric,
      clicked_metric_value: value,
      active_filter_state: currentFilterState(),
      target_query: currentTargetQuery(),
      extra,
    };
  };

  const customerPayload = (row, section, widget, metric, value, extra = {}) =>
    entityPayload(
      "customer",
      section,
      widget,
      "customer",
      row?.customer_id || row?.key || row?.customer_name,
      row?.customer_name || row?.label || row?.customer_id,
      metric,
      value,
      extra
    );

  const attributedWorkspacePayload = (section, widget, metric, value, extra = {}) =>
    workspacePayload(section, widget, metric, value, { workspace_kind: "salesreps_attributed", ...extra });

  const territoryPayload = (territoryName, section, widget, metric, value, extra = {}) =>
    cleanText(territoryName)
      ? attributedWorkspacePayload(section, widget, metric, value, {
        bucket_type: "territory",
        territory_name: territoryName,
        ...extra,
      })
      : null;

  const proteinPayload = (proteinFamily, section, widget, metric, value, extra = {}) =>
    cleanText(proteinFamily)
      ? attributedWorkspacePayload(section, widget, metric, value, {
        bucket_type: "protein",
        protein_family: proteinFamily,
        ...extra,
      })
      : null;

  const repWorkspacePayload = (row, section, widget, metric, value, extra = {}) =>
    attributedWorkspacePayload(section, widget, metric, value, {
      rep_id: row?.rep_id || row?.repId || row?.key || row?.rep_name,
      ...extra,
    });

  const sortRows = (rows, key, dir = "desc", valueFn = null) => {
    const list = Array.isArray(rows) ? [...rows] : [];
    const direction = dir === "asc" ? 1 : -1;
    return list.sort((a, b) => {
      const aRaw = valueFn ? valueFn(a, key) : a?.[key];
      const bRaw = valueFn ? valueFn(b, key) : b?.[key];
      const aNum = opt(aRaw);
      const bNum = opt(bRaw);
      if (aNum !== null || bNum !== null) return (aNum ?? -Infinity) > (bNum ?? -Infinity) ? direction : (aNum ?? -Infinity) < (bNum ?? -Infinity) ? -direction : 0;
      const aText = cleanText(aRaw).toLowerCase();
      const bText = cleanText(bRaw).toLowerCase();
      if (aText === bText) return 0;
      return aText > bText ? direction : -direction;
    });
  };

  const bucketLabelFromKey = (bucket, grain = "monthly", ttm = false) => {
    const raw = cleanText(bucket);
    if (!raw) return "--";
    if (ttm) return `TTM End ${raw}`;
    if (grain === "quarterly") return raw;
    if (grain === "yearly") return raw;
    if (/^\d{4}-\d{2}$/.test(raw)) {
      const [year, month] = raw.split("-");
      const dt = new Date(Number(year), Number(month) - 1, 1);
      return dt.toLocaleDateString(LOCALE, { month: "short", year: "numeric" });
    }
    return raw;
  };

  const stableColor = (index) => {
    // ── Phase 2: brand-aligned palette (top rep = brand primary) ──
    const palette = [
      "#965951",  // brand primary  (top rep by revenue)
      "#d39c5f",  // brand gold     (2nd)
      "#2563eb",  // blue
      "#16a34a",  // green
      "#9333ea",  // purple
      "#0891b2",  // cyan
      "#ea580c",  // orange
      "#be123c",  // rose
      "#4f46e5",  // indigo
      "#0d9488",  // teal
    ];
    return palette[index % palette.length];
  };

  const monthKeyToDate = (bucket) => {
    const raw = cleanText(bucket);
    if (!/^\d{4}-\d{2}$/.test(raw)) return null;
    const [year, month] = raw.split("-").map((v) => Number(v));
    const dt = new Date(year, month - 1, 1);
    return Number.isNaN(dt.valueOf()) ? null : dt;
  };

  const monthKeyFromDate = (dt) => {
    if (!(dt instanceof Date) || Number.isNaN(dt.valueOf())) return "";
    return `${dt.getFullYear()}-${String(dt.getMonth() + 1).padStart(2, "0")}`;
  };

  const periodKey = (bucket, grain) => {
    const dt = monthKeyToDate(bucket);
    if (!dt) return bucket;
    if (grain === "yearly") return String(dt.getFullYear());
    if (grain === "quarterly") return `${dt.getFullYear()}-Q${Math.floor(dt.getMonth() / 3) + 1}`;
    return bucket;
  };

  const aggregateRepTrendDetail = (rows = [], grain = "monthly") => {
    const monthlyByRep = new Map();
    (Array.isArray(rows) ? rows : []).forEach((row) => {
      const repId = cleanText(row.rep_id || row.rep_name);
      const bucket = cleanText(row.bucket);
      if (!repId || !bucket) return;
      if (!monthlyByRep.has(repId)) monthlyByRep.set(repId, { rep_id: repId, rep_name: repDisplayName(row), points: [] });
      monthlyByRep.get(repId).points.push({
        bucket,
        rep_id: repId,
        rep_name: repDisplayName(row),
        revenue: num(row.revenue),
        revenue_yoy: opt(row.revenue_yoy),
        profit: opt(row.profit),
        profit_yoy: opt(row.profit_yoy),
        weight_lb: num(row.weight_lb),
        weight_lb_yoy: opt(row.weight_lb_yoy),
        customers: num(row.customers),
        customers_yoy: opt(row.customers_yoy),
        direct_revenue: opt(row.direct_revenue),
        inherited_revenue: opt(row.inherited_revenue),
        direct_customers: opt(row.direct_customers),
        inherited_customers: opt(row.inherited_customers),
        observed_days: opt(row.observed_days),
        observed_days_yoy: opt(row.observed_days_yoy),
      });
    });

    const aggregatePoints = (points, nextBucket) => {
      const revenue = points.reduce((acc, p) => acc + num(p.revenue), 0);
      const revenueYoY = points.reduce((acc, p) => acc + num(p.revenue_yoy), 0);
      const profit = points.some((p) => opt(p.profit) !== null) ? points.reduce((acc, p) => acc + num(p.profit), 0) : null;
      const profitYoY = points.some((p) => opt(p.profit_yoy) !== null) ? points.reduce((acc, p) => acc + num(p.profit_yoy), 0) : null;
      const weight = points.reduce((acc, p) => acc + num(p.weight_lb), 0);
      const weightYoY = points.some((p) => opt(p.weight_lb_yoy) !== null) ? points.reduce((acc, p) => acc + num(p.weight_lb_yoy), 0) : null;
      const customers = points.some((p) => opt(p.customers) !== null) ? points.reduce((acc, p) => acc + num(p.customers), 0) : 0;
      const customersYoY = points.some((p) => opt(p.customers_yoy) !== null) ? points.reduce((acc, p) => acc + num(p.customers_yoy), 0) : null;
      const directRevenue = points.some((p) => opt(p.direct_revenue) !== null) ? points.reduce((acc, p) => acc + num(p.direct_revenue), 0) : null;
      const inheritedRevenue = points.some((p) => opt(p.inherited_revenue) !== null) ? points.reduce((acc, p) => acc + num(p.inherited_revenue), 0) : null;
      const directCustomers = points.some((p) => opt(p.direct_customers) !== null) ? points.reduce((acc, p) => acc + num(p.direct_customers), 0) : null;
      const inheritedCustomers = points.some((p) => opt(p.inherited_customers) !== null) ? points.reduce((acc, p) => acc + num(p.inherited_customers), 0) : null;
      const observedDays = points.some((p) => opt(p.observed_days) !== null) ? points.reduce((acc, p) => acc + num(p.observed_days), 0) : null;
      const observedDaysYoY = points.some((p) => opt(p.observed_days_yoy) !== null) ? points.reduce((acc, p) => acc + num(p.observed_days_yoy), 0) : null;
      return {
        bucket: nextBucket,
        rep_id: points[0]?.rep_id,
        rep_name: points[0]?.rep_name,
        revenue,
        revenue_yoy: revenueYoY,
        profit,
        profit_yoy: profitYoY,
        margin_pct: revenue > 0 && profit !== null ? (profit / revenue) * 100 : null,
        margin_pct_yoy: revenueYoY > 0 && profitYoY !== null ? (profitYoY / revenueYoY) * 100 : null,
        weight_lb: weight,
        weight_lb_yoy: weightYoY,
        customers,
        customers_yoy: customersYoY,
        direct_revenue: directRevenue,
        inherited_revenue: inheritedRevenue,
        direct_customers: directCustomers,
        inherited_customers: inheritedCustomers,
        observed_days: observedDays,
        observed_days_yoy: observedDaysYoY,
      };
    };

    const aggregated = [];
    monthlyByRep.forEach((entry) => {
      const sorted = entry.points.sort((a, b) => cleanText(a.bucket).localeCompare(cleanText(b.bucket)));
      if (grain === "monthly") {
        sorted.forEach((point) => aggregated.push({ ...point, margin_pct: point.revenue && point.profit != null ? (num(point.profit) / point.revenue) * 100 : null, margin_pct_yoy: num(point.revenue_yoy) && point.profit_yoy != null ? (num(point.profit_yoy) / num(point.revenue_yoy)) * 100 : null }));
        return;
      }
      if (grain === "ttm") {
        if (sorted.length < 12) return;
        for (let idx = 11; idx < sorted.length; idx += 1) {
          const windowPoints = sorted.slice(idx - 11, idx + 1);
          aggregated.push(aggregatePoints(windowPoints, sorted[idx].bucket));
        }
        return;
      }
      const groups = new Map();
      sorted.forEach((point) => {
        const key = periodKey(point.bucket, grain);
        if (!groups.has(key)) groups.set(key, []);
        groups.get(key).push(point);
      });
      Array.from(groups.entries())
        .sort((a, b) => a[0].localeCompare(b[0]))
        .forEach(([key, bucketRows]) => aggregated.push(aggregatePoints(bucketRows, key)));
    });

    return aggregated.sort((a, b) => {
      if (a.rep_id === b.rep_id) return cleanText(a.bucket).localeCompare(cleanText(b.bucket));
      return cleanText(a.rep_name).localeCompare(cleanText(b.rep_name));
    });
  };

  const trendMetricValue = (point, metric) => {
    if (!point) return 0;
    if (metric === "profit") return opt(point.profit) ?? 0;
    if (metric === "margin_pct") return opt(point.margin_pct) ?? 0;
    if (metric === "customers") return num(point.customers);
    if (metric === "weight_lb") return num(point.weight_lb);
    return num(point.revenue);
  };

  const trendMetricPriorValue = (point, metric) => {
    if (!point) return null;
    if (metric === "profit") return opt(point.profit_yoy);
    if (metric === "margin_pct") return opt(point.margin_pct_yoy);
    if (metric === "customers") return opt(point.customers_yoy);
    if (metric === "weight_lb") return opt(point.weight_lb_yoy);
    return opt(point.revenue_yoy);
  };

  const trendMetricFormatter = (metric, value) => {
    if (metric === "margin_pct") return `${fmtPct.format(num(value))}%`;
    if (metric === "customers") return fmtInt.format(num(value));
    if (metric === "weight_lb") return fmtInt.format(num(value));
    return money(value);
  };

  const comparableObservedDays = (currentDays, priorDays) => {
    const current = opt(currentDays);
    const prior = opt(priorDays);
    if (current == null || prior == null || current <= 0 || prior <= 0) return false;
    return Math.abs(current - prior) <= 2;
  };

  const trendMoM = (points, idx, metric) => {
    if (!Array.isArray(points) || idx <= 0) return null;
    const current = trendMetricValue(points[idx], metric);
    const previous = trendMetricValue(points[idx - 1], metric);
    if (!Number.isFinite(current) || !Number.isFinite(previous) || previous === 0) return null;
    return ((current - previous) / Math.abs(previous)) * 100;
  };

  const isoDateLabel = (raw) => {
    if (!raw) return "--";
    const dt = new Date(raw);
    if (Number.isNaN(dt.valueOf())) return String(raw);
    return dt.toLocaleString(LOCALE);
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
    setChartShellLoading(canvasId, false);
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

  const syncStateFromQS = (qs) => {
    const params = new URLSearchParams(String(qs || "").replace(/^\?/, ""));
    const mode = params.get("attribution_mode");
    if (mode) state.attributionMode = mode;
    const roster = params.get("roster_mode");
    if (roster) state.rosterMode = roster;
    const transferOnly = params.get("transfer_only");
    if (transferOnly != null) state.transferOnly = ["1", "true", "yes", "on"].includes(String(transferOnly).toLowerCase());
    const metric = params.get("metric");
    if (metric && metricConfig[metric]) state.metric = metric;
    const trendMetric = params.get("trend_metric");
    if (trendMetric && metricConfig[trendMetric]) state.trendMetric = trendMetric;
    const trendGrain = params.get("trend_grain");
    if (trendGrain && ["monthly", "quarterly", "yearly", "ttm"].includes(trendGrain)) state.trendGrain = trendGrain;
    const trendView = params.get("trend_view");
    if (trendView && ["absolute", "yoy_delta", "index"].includes(trendView)) state.trendView = trendView;
    const topN = Number(params.get("top_n") || params.get("topN"));
    if (Number.isFinite(topN) && topN > 0) state.topN = topN;
  };

  const baseQuery = () => {
    const params = new URLSearchParams(state.qs || "");
    params.set("page", String(state.page));
    params.set("page_size", String(state.pageSize));
    params.set("sort", state.sortBy);
    params.set("dir", state.sortDir);
    params.set("metric", state.metric);
    params.set("trend_metric", state.trendMetric);
    params.set("trend_grain", state.trendGrain);
    params.set("trend_view", state.trendView);
    params.set("top_n", String(state.topN));
    params.set("attribution_mode", state.attributionMode);
    params.set("roster_mode", state.rosterMode);
    if (state.transferOnly) params.set("transfer_only", "1");
    else params.delete("transfer_only");
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

  const syncControlsFromState = () => {
    const metricToggle = document.getElementById("srMetricToggle");
    const trendMetric = document.getElementById("srTrendMetric");
    const trendGrain = document.getElementById("srTrendGrain");
    const trendView = document.getElementById("srTrendView");
    const topN = document.getElementById("srTopN");
    const pageSize = document.getElementById("srPageSize");
    const search = document.getElementById("srSearchInput");
    const attributionMode = document.getElementById("srAttributionMode");
    const includeFormer = document.getElementById("srIncludeFormerReps");
    const transferOnly = document.getElementById("srTransferOnly");

    if (metricToggle) metricToggle.value = state.metric;
    if (trendMetric) trendMetric.value = state.trendMetric;
    if (trendGrain) trendGrain.value = state.trendGrain;
    if (trendView) trendView.value = state.trendView;
    if (topN) topN.value = String(state.topN);
    if (pageSize) pageSize.value = String(state.pageSize);
    if (search) search.value = state.search || "";
    if (attributionMode) attributionMode.value = state.attributionMode;
    if (includeFormer) includeFormer.checked = state.rosterMode === "include_former";
    if (transferOnly) transferOnly.checked = !!state.transferOnly;
  };

  const snapshotUiState = () => ({
    page: state.page,
    pageSize: state.pageSize,
    sortBy: state.sortBy,
    sortDir: state.sortDir,
    search: state.search,
    metric: state.metric,
    trendMetric: state.trendMetric,
    trendGrain: state.trendGrain,
    trendView: state.trendView,
    trendSelectedReps: Array.isArray(state.trendSelectedReps) ? [...state.trendSelectedReps] : [],
    trendFocusMode: !!state.trendFocusMode,
    topN: state.topN,
    topCustomersSortBy: state.topCustomersSortBy,
    topCustomersSortDir: state.topCustomersSortDir,
    proteinSortBy: state.proteinSortBy,
    proteinSortDir: state.proteinSortDir,
    attributionMode: state.attributionMode,
    rosterMode: state.rosterMode,
    transferOnly: !!state.transferOnly,
  });

  const applySnapshotUiState = (uiState = {}) => {
    if (!uiState || typeof uiState !== "object") return;
    if (Number.isFinite(Number(uiState.page)) && Number(uiState.page) > 0) state.page = Number(uiState.page);
    if (Number.isFinite(Number(uiState.pageSize)) && Number(uiState.pageSize) > 0) state.pageSize = Number(uiState.pageSize);
    if (uiState.sortBy) state.sortBy = String(uiState.sortBy);
    if (uiState.sortDir) state.sortDir = String(uiState.sortDir) === "asc" ? "asc" : "desc";
    if (uiState.search != null) state.search = String(uiState.search);
    if (uiState.metric && metricConfig[uiState.metric]) state.metric = uiState.metric;
    if (uiState.trendMetric && metricConfig[uiState.trendMetric]) state.trendMetric = uiState.trendMetric;
    if (uiState.trendGrain && ["monthly", "quarterly", "yearly", "ttm"].includes(uiState.trendGrain)) state.trendGrain = uiState.trendGrain;
    if (uiState.trendView && ["absolute", "yoy_delta", "index"].includes(uiState.trendView)) state.trendView = uiState.trendView;
    if (Array.isArray(uiState.trendSelectedReps)) state.trendSelectedReps = [...uiState.trendSelectedReps];
    state.trendFocusMode = !!uiState.trendFocusMode;
    if (Number.isFinite(Number(uiState.topN)) && Number(uiState.topN) > 0) state.topN = Number(uiState.topN);
    if (uiState.topCustomersSortBy) state.topCustomersSortBy = String(uiState.topCustomersSortBy);
    if (uiState.topCustomersSortDir) state.topCustomersSortDir = String(uiState.topCustomersSortDir) === "asc" ? "asc" : "desc";
    if (uiState.proteinSortBy) state.proteinSortBy = String(uiState.proteinSortBy);
    if (uiState.proteinSortDir) state.proteinSortDir = String(uiState.proteinSortDir) === "asc" ? "asc" : "desc";
    if (uiState.attributionMode) state.attributionMode = String(uiState.attributionMode);
    if (uiState.rosterMode) state.rosterMode = String(uiState.rosterMode);
    state.transferOnly = !!uiState.transferOnly;
  };

  const persistSnapshot = (payload = lastPayload) => {
    if (!pageCache || !payload || !state.qs) return false;
    return pageCache.saveSnapshot(PAGE_CACHE_ID, {
      qs: state.qs,
      payload,
      uiState: snapshotUiState(),
      scrollY: window.scrollY || 0,
      meta: {
        datasetVersion: payload?.meta?.dataset_version || null,
        cacheTtl: payload?.meta?.cache_ttl || null,
      },
    });
  };

  const restoreSnapshot = (qs, { restoreScroll = false } = {}) => {
    if (!pageCache) return null;
    const snapshot = pageCache.loadSnapshot(PAGE_CACHE_ID, { qs, ...PAGE_CACHE_POLICY });
    if (!snapshot?.payload) return null;
    applySnapshotUiState(snapshot.ui_state || {});
    syncControlsFromState();
    renderBundle(snapshot.payload);
    if (restoreScroll) {
      pageCache.restoreScroll(PAGE_CACHE_ID, { qs, ...PAGE_CACHE_POLICY, delayMs: 40 });
    }
    return snapshot;
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
    const attribution = meta.attribution || {};
    const bridge = meta.ownership_bridge || {};
    const succession = meta.ownership_succession || {};
    const snapshot = meta.ownership_snapshot || {};
    const analysis = payload.analysis || {};
    const portfolio = analysis.portfolio || {};

    setText("kpiRevenue", money(k.revenue));
    setText("kpiProfit", k.profit == null ? NA : money(k.profit));
    setText("kpiMargin", k.margin_pct == null ? NA : `${fmtPct.format(num(k.margin_pct))}%`);
    setText("kpiOrders", fmtInt.format(num(k.orders)));
    setText("kpiCustomers", fmtInt.format(num(k.customers)));
    setText("kpiWeight", fmtInt.format(num(k.weight_lb)));
    setText("kpiUnits", fmtInt.format(num(k.units)));
    setText("kpiAspLb", k.asp_lb == null ? NA : money(k.asp_lb, false));
    setText("kpiAsp", k.asp == null ? NA : money(k.asp, false));
    setText("kpiActiveCustomers", fmtInt.format(num(k.active_customers)));
    setText("kpiAvgOrderValue", k.avg_order_value == null ? NA : money(k.avg_order_value, false));
    setText("kpiRevenuePerCustomer", k.revenue_per_customer == null ? NA : money(k.revenue_per_customer, false));
    setText("kpiInheritedRevenue", k.inherited_revenue == null ? NA : money(k.inherited_revenue));
    setText("srTransferredAccounts", fmtInt.format(num(k.transferred_accounts_count)));
    setText("srTransferredRevenue", `${money(k.transferred_in_revenue)} in | ${money(k.transferred_out_revenue)} out`);

    setDelta("kpiRevenueDelta", k.revenue_mom_pct);
    setDelta("kpiProfitDelta", k.profit_mom_pct);
    setText("kpiMarginDelta", marginContextText(k) || (k.margin_mom_pct == null ? NA : fmtSignedPoints(k.margin_mom_pct)));

    // ── 2C: Margin guardrail progress bar ──
    (function () {
      const marginCard = document.getElementById("kpiMargin")?.closest(".sr-kpi");
      if (!marginCard) return;
      const current  = opt(k.margin_pct);
      const minMgn   = opt(k.minimum_margin_pct);
      const targetMgn = opt(k.target_margin_pct);
      if (current === null || minMgn === null || targetMgn === null) return;
      const existingBar = marginCard.querySelector(".sr-margin-bar-wrap");
      if (existingBar) existingBar.remove();
      const scaleMax  = targetMgn + 5;
      const fillPct   = Math.min((current / scaleMax) * 100, 100);
      const colour    = current >= targetMgn ? "#198754" : current >= minMgn ? "#ffc107" : "#dc3545";
      const bar = document.createElement("div");
      bar.className = "sr-margin-bar-wrap";
      bar.title = `Current: ${fmtPct.format(current)}% | Min: ${fmtPct.format(minMgn)}% | Target: ${fmtPct.format(targetMgn)}%`;
      bar.innerHTML = `
        <div class="sr-margin-bar-track">
          <div class="sr-margin-bar-fill" style="width:${fillPct}%;background:${colour}"></div>
        </div>
        <div class="sr-margin-bar-labels">
          <span>Min: ${fmtPct.format(minMgn)}%</span>
          <span>Target: ${fmtPct.format(targetMgn)}%</span>
        </div>
      `;
      marginCard.appendChild(bar);
    })();

    setText("kpiActiveCustomersDelta", `${fmtInt.format(num(k.inherited_customers))} inherited`);
    setText("kpiInheritedRevenueDelta", `${fmtInt.format(num(k.unassigned_customers))} unassigned cust.`);

    const activeReps = k.active_reps || payload.table?.total_rows || 0;
    setText("srActiveRepsChip", `Visible reps: ${fmtInt.format(num(activeReps))}`);
    setText(
      "srModeChip",
      `Mode: ${attribution.attribution_mode === "current_owner" ? "Current Owner Roll-Up" : "Historical Rep View"}`
    );
    setText(
      "srBridgeChip",
      bridge.available && succession.available
        ? `Owner mapping: ${fmtInt.format(num(bridge.rows))} assignments + ${fmtInt.format(num(succession.rows))} successor rules`
        : bridge.available
          ? `Owner mapping: ${fmtInt.format(num(bridge.rows))} assignments`
          : snapshot.available
            ? `Owner mapping: ${fmtInt.format(num(snapshot.rows))} customer owner snapshots`
          : succession.available
            ? `Owner mapping: ${fmtInt.format(num(succession.rows))} successor rules`
            : "Owner mapping: Needs review"
    );

    const coverage = opt(k.ownership_coverage_pct);
    setText("srCoverageChip", coverage == null ? "Coverage: N/A" : `Coverage: ${fmtPct.format(coverage)}%`);

    setText("srLastRefresh", `Last refresh: ${isoDateLabel(meta.last_refresh || k.last_refresh || meta.dataset_version)}`);
    setText("srWhatChanged", `What changed: ${k.what_changed || "No major change detected."}`);
    const attributionSelect = document.getElementById("srAttributionMode");
    if (attributionSelect) attributionSelect.value = state.attributionMode;
    const metricToggle = document.getElementById("srMetricToggle");
    if (metricToggle) metricToggle.value = state.metric;
    const trendMetric = document.getElementById("srTrendMetric");
    if (trendMetric) trendMetric.value = state.trendMetric;
    const trendGrain = document.getElementById("srTrendGrain");
    if (trendGrain) trendGrain.value = state.trendGrain;
    const trendView = document.getElementById("srTrendView");
    if (trendView) trendView.value = state.trendView;
    const topNSelect = document.getElementById("srTopN");
    if (topNSelect) topNSelect.value = String(state.topN);
    const formerWrap = document.getElementById("srFormerToggleWrap");
    if (formerWrap) formerWrap.classList.toggle("d-none", state.attributionMode !== "historical_rep");
    const includeFormer = document.getElementById("srIncludeFormerReps");
    if (includeFormer) includeFormer.checked = state.rosterMode === "include_former";
    setText("srInheritedCustomers", fmtInt.format(num(k.inherited_customers)));
    setText(
      "srInheritedCustomersNote",
      `${fmtInt.format(num(k.gained_customers))} gained | ${fmtInt.format(num(k.lost_customers))} lost`
    );
    setText("srUnassignedCustomers", fmtInt.format(num(k.unassigned_customers)));
    setText("srUnassignedRevenueNote", k.unassigned_revenue == null ? NA : money(k.unassigned_revenue));
    setText("srYoyRevenue", k.revenue_yoy_pct == null ? NA : `${fmtPct.format(num(k.revenue_yoy_pct))}%`);
    setText("srYoyProfit", k.profit_yoy_pct == null ? "Profit YoY: N/A" : `Profit YoY: ${fmtPct.format(num(k.profit_yoy_pct))}%`);
    setText("srYoyMargin", k.margin_yoy_delta == null ? NA : `${fmtPct.format(num(k.margin_yoy_delta))} pts`);
    setText(
      "srModeNarrative",
      attribution.attribution_mode === "current_owner"
        ? snapshot.available
          ? "Main view rolls inherited history under the current customer owner"
          : "Main view rolls inherited history forward to the current owner"
        : "Performance by rep at time of sale"
    );
    setText(
      "srPortfolioFocus",
      portfolio.visible_rep_count === 1
        ? `Focused owner: ${portfolio.top_rep_name || NA}`
        : `Visible portfolio: ${fmtInt.format(num(portfolio.visible_rep_count || activeReps))} reps`
    );
    setText("srPortfolioTerritoryCount", fmtInt.format(num(k.territory_count)));
    setText(
      "srPortfolioTopTerritory",
      portfolio.territories?.[0]?.territory_name
        ? `${portfolio.territories[0].territory_name} · ${money(portfolio.territories[0].revenue)}`
        : "No active territory mix"
    );
    setText("srPortfolioReplacedCount", fmtInt.format(num(k.replaced_rep_count)));
    setText(
      "srPortfolioReplacedNames",
      portfolio.replacement_names?.length ? portfolio.replacement_names.slice(0, 3).join(", ") : "No inherited predecessor reps"
    );

    setText("srDirectRevenue", k.direct_revenue == null ? NA : money(k.direct_revenue));
    setText(
      "srDirectRevenueNote",
      k.revenue ? `${fmtPct.format((num(k.direct_revenue) / Math.max(num(k.revenue), 1)) * 100)}% of visible revenue` : "No direct book in scope"
    );
    setText("srDirectCustomers", fmtInt.format(num(k.direct_customers)));
    setText("srDirectCustomersNote", `${fmtInt.format(num(k.inherited_customers))} inherited cust.`);

    const concentrationChip = (analysis.insights?.chips || []).find((chip) => chip.key === "largest_concentration_risk");
    setText("srConcentrationSummary", concentrationChip?.rep_name || "No outsized risk");
    setText(
      "srConcentrationNote",
      concentrationChip?.display_value ? `Top customer share ${concentrationChip.display_value}` : "Largest books remain reasonably diversified"
    );
    setText(
      "srAccountMovesSummary",
      `${fmtInt.format(num(k.largest_gained_accounts_count))} / ${fmtInt.format(num(k.largest_lost_accounts_count))}`
    );
    setText(
      "srAccountMovesNote",
      `${fmtInt.format(num(k.gained_customers))} gained | ${fmtInt.format(num(k.lost_customers))} lost`
    );

    setDrillPayload(
      document.getElementById("kpiRevenue")?.closest(".sr-kpi"),
      attributedWorkspacePayload("Executive Scorecard", "Revenue", "Revenue", k.revenue, {
        filter_mode: "current_window",
        detail: "Attributed current-window revenue under the visible owner portfolio.",
      })
    );
    setDrillPayload(
      document.getElementById("kpiProfit")?.closest(".sr-kpi"),
      attributedWorkspacePayload("Executive Scorecard", "Profit", "Profit", k.profit, {
        filter_mode: "current_window",
        detail: "Attributed current-window profit under the visible owner portfolio.",
      })
    );
    setDrillPayload(
      document.getElementById("kpiCustomers")?.closest(".sr-kpi"),
      attributedWorkspacePayload("Executive Scorecard", "Customers", "Customers", k.customers, {
        filter_mode: "current_window",
        detail: "Distinct customers covered by visible sales reps under the active filter window.",
      })
    );
    setDrillPayload(
      document.getElementById("kpiActiveCustomers")?.closest(".sr-kpi"),
      attributedWorkspacePayload("Executive Scorecard", "Active Customers", "Active Customers", k.active_customers, {
        filter_mode: "current_window",
        detail: "Active customers in the visible owner portfolio.",
      })
    );
    setDrillPayload(
      document.getElementById("kpiInheritedRevenue")?.closest(".sr-kpi"),
      attributedWorkspacePayload("Executive Scorecard", "Inherited Revenue", "Inherited Revenue", k.inherited_revenue, {
        filter_mode: "current_window",
        inherited_only: true,
        detail: "Orders attributed to inherited customers under the current-owner roll-up.",
      })
    );
    setDrillPayload(
      document.getElementById("srTransferredAccounts")?.closest(".sr-kpi"),
      attributedWorkspacePayload("Executive Scorecard", "Transferred Accounts", "Transferred Accounts", k.transferred_accounts_count, {
        filter_mode: "current_window",
        transfer_activity_only: true,
        detail: "Transferred account activity in the current owner portfolio.",
      })
    );
    setDrillPayload(
      document.getElementById("srDirectRevenueCard"),
      attributedWorkspacePayload("Insight Strip", "Direct Revenue", "Direct Revenue", k.direct_revenue, {
        filter_mode: "current_window",
        direct_only: true,
      })
    );
    setDrillPayload(
      document.getElementById("srDirectCustomersCard"),
      attributedWorkspacePayload("Insight Strip", "Direct Customers", "Direct Customers", k.direct_customers, {
        filter_mode: "current_window",
        direct_only: true,
      })
    );
    setDrillPayload(
      document.getElementById("srConcentrationCard"),
      concentrationChip?.rep_id
        ? salesrepPayload({ rep_id: concentrationChip.rep_id, rep_name: concentrationChip.rep_name }, "Insight Strip", "Concentration Risk", "Top customer share", concentrationChip.metric_value)
        : null
    );
    setDrillPayload(
      document.getElementById("srAccountMovesCard"),
      attributedWorkspacePayload("Insight Strip", "Largest Moves", "Customer Moves", k.gained_customers, {
        filter_mode: "current_window",
        detail: "Customers with the largest period-over-period movement in the visible portfolio.",
      })
    );
    setScorecardLoading(false);

    // ── 6D: Dynamic section subtitles ──
    (function () {
      const activeRepsN = num(k.active_reps || payload.table?.total_rows || 0);
      const periodLabel = meta.date_range_label || meta.period_label || "";
      const repScope = `${fmtInt.format(activeRepsN)} rep${activeRepsN !== 1 ? "s" : ""} in scope`;
      if (periodLabel) {
        setText("srSectionLeadershipSubtitle", `${periodLabel} · ${repScope} · ${money(k.revenue)} total revenue`);
      }
      const coverage = opt(k.ownership_coverage_pct);
      if (coverage != null) {
        setText("srSectionOwnershipSubtitle", `${fmtPct.format(coverage)}% owner coverage · ${fmtInt.format(num(k.inherited_customers))} inherited customers · ${fmtInt.format(num(k.territory_count))} territories`);
      }
      const mc = payload.charts?.monthly_compare ?? payload.trend?.monthly_compare ?? {};
      const periodCount = (mc.labels || []).length;
      if (periodCount) {
        setText("srSectionTrendSubtitle", `${periodCount} comparable periods · rep-level momentum and YoY overlap · click any series to focus`);
      }
      if (k.active_customers) {
        setText("srSectionCustomerSubtitle", `${fmtInt.format(num(k.active_customers))} active customers · click Best / At-Risk to filter by health`);
      }
    })();

    // ── Phase 5: populate sticky context bar ──
    (function () {
      const stickyRev    = document.getElementById("sStickyRev");
      const stickyMargin = document.getElementById("sStickyMargin");
      const stickyReps   = document.getElementById("sStickyReps");
      if (stickyRev)    stickyRev.textContent    = money(k.revenue);
      if (stickyMargin) stickyMargin.textContent  = k.margin_pct == null ? "—" : `${fmtPct.format(num(k.margin_pct))}%`;
      if (stickyReps)   stickyReps.textContent    = `${fmtInt.format(num(k.active_reps || payload.table?.total_rows || 0))} reps`;
    })();

    // ── Phase 5: show/hide sticky bar on scroll past KPI grid ──
    (function () {
      const stickyBar = document.getElementById("srStickyBar");
      const kpiGrid   = document.getElementById("srKpiGrid");
      if (stickyBar && kpiGrid) {
        new IntersectionObserver(([entry]) => {
          stickyBar.style.transform = entry.isIntersecting ? "translateY(-100%)" : "translateY(0)";
        }, { threshold: 0 }).observe(kpiGrid);
      }
    })();

    // ── 2A: KPI micro-sparklines ──
    (function () {
      const mc = payload.charts?.monthly_compare ?? payload.trend?.monthly_compare ?? {};
      const sparkDefs = [
        { kpiId: "kpiRevenue",  data: mc.revenue  ?? [] },
        { kpiId: "kpiProfit",   data: mc.profit   ?? [] },
        { kpiId: "kpiWeight",   data: mc.weight_lb ?? [] },
      ];
      sparkDefs.forEach(({ kpiId, data }) => {
        const card = document.getElementById(kpiId)?.closest(".sr-kpi");
        if (!card) return;
        card.querySelector(".sr-kpi-sparkline")?.remove();
        const vals = data.filter((v) => v != null).slice(-12);
        if (vals.length < 3) return;
        const W = 72, H = 22, pad = 2;
        const lo = Math.min(...vals), hi = Math.max(...vals);
        const range = hi - lo || 1;
        const toX = (i) => pad + ((i / (vals.length - 1)) * (W - pad * 2));
        const toY = (v) => H - pad - ((v - lo) / range) * (H - pad * 2);
        const pts = vals.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`).join(" ");
        const trend = vals[vals.length - 1] >= vals[0];
        const lineColor = trend ? "#965951" : "#d39c5f";
        const polyFill = [
          `${toX(0).toFixed(1)},${H - pad}`,
          ...vals.map((v, i) => `${toX(i).toFixed(1)},${toY(v).toFixed(1)}`),
          `${toX(vals.length - 1).toFixed(1)},${H - pad}`,
        ].join(" ");
        const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
        svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
        svg.setAttribute("width", W);
        svg.setAttribute("height", H);
        svg.classList.add("sr-kpi-sparkline");
        svg.setAttribute("aria-hidden", "true");
        svg.innerHTML = `
          <polygon points="${polyFill}" fill="${lineColor}" fill-opacity="0.12"/>
          <polyline points="${pts}" fill="none" stroke="${lineColor}" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>
        `;
        card.appendChild(svg);
      });
    })();
  };

  const renderWarnings = (warnings = [], payload = {}) => {
    const holder = document.getElementById("srWarnings");
    if (!holder) return;
    const rows = Array.isArray(warnings) ? warnings.filter(Boolean) : [];
    if (!rows.length) {
      holder.innerHTML = "";
      return;
    }
    const attribution = payload?.meta?.attribution || {};
    const header = attribution.attribution_mode === "current_owner" ? "Current owner roll-up notes" : "Historical attribution notes";
    holder.innerHTML = `
      <div class="alert alert-warning border-0 mb-0" role="status">
        <div class="fw-semibold mb-1">${header}</div>
        <ul class="mb-0 ps-3">
          ${rows.slice(0, 4).map((msg) => `<li>${escapeHtml(msg)}</li>`).join("")}
        </ul>
      </div>
    `;
  };

  const renderInsights = (payload = {}) => {
    const analysis = payload.analysis || {};
    const insights = analysis.insights || {};
    const chipsHolder = document.getElementById("srInsightChips");
    const narrativeEl = document.getElementById("srInsightNarrative");
    if (narrativeEl) {
      narrativeEl.textContent = cleanText(insights.narrative) || cleanText(payload.kpis?.what_changed) || "No standout signal detected in the visible slice.";
    }
    if (!chipsHolder) return;
    const chips = Array.isArray(insights.chips) ? insights.chips : [];
    if (!chips.length) {
      chipsHolder.innerHTML = '<span class="sr-empty-list">No major directional signals are active in the current slice.</span>';
      return;
    }
    chipsHolder.innerHTML = chips.map((chip) => {
      const chipPayload = chip?.rep_id
        ? salesrepPayload({ rep_id: chip.rep_id, rep_name: chip.rep_name }, "Insight Strip", chip.label, chip.metric_key || chip.label, chip.metric_value)
        : null;
      const repName = chip.rep_name;
      const clickable = !!repName;
      const clickAttr = clickable
        ? ` onclick="srChipClick(${JSON.stringify(escapeHtml(repName))})" title="Click to find ${escapeHtml(repName)} in the table below"`
        : "";
      return `
        <span class="sr-chip${clickable ? " is-clickable" : ""}"${drillAttr(chipPayload)}${clickAttr}>
          <span class="sr-chip-label">${escapeHtml(chip.label || "Signal")}</span>
          <span class="sr-chip-value">${escapeHtml(repName || "--")} ${escapeHtml(chip.display_value || "")}</span>
        </span>
      `;
    }).join("");
  };

  const buildSummaryNarrative = (payload = {}) => {
    const kpis = payload.kpis || {};
    const insights = payload.analysis?.insights || {};
    const proteins = Array.isArray(payload.analysis?.proteins) ? payload.analysis.proteins : [];
    const revenueMoM = opt(kpis.revenue_mom_pct);
    const highestGrowth = (insights.chips || []).find((chip) => chip.key === "highest_growth_rep");
    const biggestDrag = (insights.chips || []).find((chip) => chip.key === "biggest_yoy_drag");
    const criticalProtein = proteins
      .filter((row) => isCriticalMargin(row))
      .sort((a, b) => num(b.revenue) - num(a.revenue))[0];

    const parts = [];
    if (revenueMoM !== null) {
      parts.push(`Revenue is ${revenueMoM >= 0 ? "up" : "down"} ${fmtPct.format(Math.abs(revenueMoM))}% MoM`);
    } else {
      parts.push("Comparable MoM revenue is unavailable for the current window");
    }

    if (criticalProtein?.protein_family) {
      parts.push(
        `${criticalProtein.protein_family} is below the minimum margin guardrail at ${pct(criticalProtein.margin_pct)} versus ${pct(criticalProtein.minimum_margin_pct)} min`
      );
    } else if (revenueMoM !== null && revenueMoM < 0 && biggestDrag?.rep_name) {
      parts.push(`${biggestDrag.rep_name} is the sharpest YoY drag at ${biggestDrag.display_value || NA}`);
    }

    if (highestGrowth?.rep_name) {
      parts.push(`${highestGrowth.rep_name} is the strongest growth rep at ${highestGrowth.display_value || NA}`);
    }

    parts.push(
      revenueMoM !== null && revenueMoM < 0
        ? "Recommend reviewing pricing guardrails and near-term recovery plays."
        : "Use the leading rep and protein mix as the template for the next action."
    );

    return `${parts.filter(Boolean).join(". ")}.`;
  };

  const renderSummaryNarrative = (payload = {}) => {
    const el = document.getElementById("srSummaryNarrative");
    if (!el) return;
    el.textContent = buildSummaryNarrative(payload);
    setSummaryNarrativeLoading(false);
  };

  // ── 2B: Signal chip → anchor-jump to rep table ──
  window.srChipClick = (repName) => {
    const tableSection = document.getElementById("srTableSection");
    tableSection?.scrollIntoView({ behavior: "smooth", block: "start" });
    const searchInput = document.getElementById("srSearchInput");
    if (searchInput) {
      searchInput.value = repName;
      searchInput.dispatchEvent(new Event("input", { bubbles: true }));
    }
    setTimeout(() => {
      document.querySelectorAll("#srTable tbody tr").forEach((row) => {
        if (row.textContent.includes(repName)) {
          row.style.background = "#fef9c3";
          setTimeout(() => { row.style.background = ""; }, 1000);
        }
      });
    }, 300);
  };

  const renderTrend = (trend = {}) => {
    const canvasId = "trendChart";
    const detailRows = aggregateRepTrendDetail(trend.detail || [], state.trendGrain);
    const chartMetric = state.trendMetric;
    const selectionEl = document.getElementById("srTrendSelectionSummary");
    const resetEl = document.getElementById("srTrendReset");
    const topList = new Set(
      sortRows(
        Array.from(new Set(detailRows.map((row) => row.rep_id))).map((repId) => {
          const repRows = detailRows.filter((row) => row.rep_id === repId);
          return {
            rep_id: repId,
            rep_name: repRows[0]?.rep_name,
            total: repRows.reduce((acc, row) => acc + Math.abs(trendMetricValue(row, chartMetric)), 0),
          };
        }),
        "total",
        "desc"
      ).slice(0, state.topN).map((row) => row.rep_id)
    );

    state.trendSelectedReps = state.trendSelectedReps.filter((repId) => detailRows.some((row) => row.rep_id === repId));
    const visibleRepIds = state.trendFocusMode && state.trendSelectedReps.length
      ? state.trendSelectedReps
      : Array.from(new Set([...topList, ...state.trendSelectedReps]));

    const repSeries = visibleRepIds.map((repId) => {
      const points = detailRows.filter((row) => row.rep_id === repId).sort((a, b) => cleanText(a.bucket).localeCompare(cleanText(b.bucket)));
      return { rep_id: repId, rep_name: businessRepName(points[0]?.rep_name, repId, READABLE_REP_FALLBACK), points };
    }).filter((row) => row.points.length);

    const allBuckets = Array.from(new Set(repSeries.flatMap((row) => row.points.map((point) => point.bucket))))
      .sort((a, b) => cleanText(a).localeCompare(cleanText(b)));

    const hasData = repSeries.length > 0 && allBuckets.length > 0;
    const emptyMessage = state.trendGrain === "ttm"
      ? "Need at least 12 monthly periods to render trailing 12M rep trends."
      : "No rep trend detail is available for the selected filters.";
    toggleEmpty(canvasId, !hasData, emptyMessage);
    if (selectionEl) {
      if (state.trendFocusMode && state.trendSelectedReps.length) {
        selectionEl.textContent = `Focus mode: ${state.trendSelectedReps.map((repId) => businessRepName(repSeries.find((row) => row.rep_id === repId)?.rep_name, repId, READABLE_REP_FALLBACK)).join(", ")}.`;
      } else if (state.trendSelectedReps.length) {
        selectionEl.textContent = `Showing Top ${state.topN} plus selected reps: ${state.trendSelectedReps.map((repId) => businessRepName(repSeries.find((row) => row.rep_id === repId)?.rep_name, repId, READABLE_REP_FALLBACK)).join(", ")}.`;
      } else {
        selectionEl.textContent = `Showing Top ${state.topN} visible reps using ${state.trendGrain === "ttm" ? "trailing 12M" : state.trendGrain} ${state.trendView === "absolute" ? "value" : state.trendView === "yoy_delta" ? "YoY %" : "index"} mode.`;
      }
    }
    if (resetEl) resetEl.classList.toggle("d-none", !state.trendSelectedReps.length);
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("trend");
      return;
    }

    const conf = metricConfig[chartMetric] || metricConfig.revenue;
    const viewLabel = state.trendView === "absolute" ? conf.label : state.trendView === "yoy_delta" ? `${conf.label} YoY %` : `${conf.label} Index`;
    const datasets = repSeries.map((series, idx) => {
      const pointMap = new Map(series.points.map((point) => [point.bucket, point]));
      const alignedPoints = allBuckets.map((bucket) => pointMap.get(bucket) || null);
      const basePoint = alignedPoints.find((point) => point && trendMetricValue(point, chartMetric) > 0);
      const baseValue = basePoint ? trendMetricValue(basePoint, chartMetric) : null;
      const metaPoints = alignedPoints.map((point, pointIdx) => {
        const current = point ? trendMetricValue(point, chartMetric) : null;
        const prior = point ? trendMetricPriorValue(point, chartMetric) : null;
        const comparableYoY = comparableObservedDays(point?.observed_days, point?.observed_days_yoy);
        const yoyPct = current != null && prior != null && prior !== 0 && comparableYoY ? ((current - prior) / Math.abs(prior)) * 100 : null;
        const displayValue = state.trendView === "absolute"
          ? current
          : state.trendView === "yoy_delta"
            ? yoyPct
            : baseValue && current != null
              ? (current / baseValue) * 100
              : null;
        return {
          ...point,
          current,
          prior,
          yoyPct,
          comparableYoY,
          momPct: trendMoM(alignedPoints, pointIdx, chartMetric),
          displayValue,
          label: bucketLabelFromKey(allBuckets[pointIdx], state.trendGrain, state.trendGrain === "ttm"),
          rawBucket: allBuckets[pointIdx],
        };
      });
      return {
        label: series.rep_name,
        repId: series.rep_id,
        metricLabel: viewLabel,
        metaPoints,
        data: metaPoints.map((point) => point.displayValue),
        borderColor: stableColor(idx),
        backgroundColor: `${stableColor(idx)}22`,
        // ── Phase 2: top rep gets thicker line and larger points ──
        borderWidth: state.trendFocusMode ? 3 : (idx === 0 ? 2.5 : 1.5),
        tension: 0.28,
        spanGaps: true,
        pointRadius: state.trendFocusMode ? 3 : (idx === 0 ? 5 : 3),
        pointHoverRadius: 5,
        fill: false,
      };
    });

    const chart = createChart("trend", canvasId, {
      type: "line",
      data: {
        labels: allBuckets.map((bucket) => bucketLabelFromKey(bucket, state.trendGrain, state.trendGrain === "ttm")),
        datasets,
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "nearest", intersect: false },
        onClick: (_evt, activeEls, chartInstance) => {
          const hit = activeEls?.[0];
          if (!hit) return;
          const ds = chartInstance?.data?.datasets?.[hit.datasetIndex];
          const metaPoint = ds?.metaPoints?.[hit.index];
          if (!ds?.repId || !metaPoint) return;
          const payload = repWorkspacePayload(
            { rep_id: ds.repId, rep_name: ds.label },
            "Trend Intelligence",
            "Revenue Trend by Rep",
            ds.metricLabel,
            metaPoint.displayValue,
            {
              filter_mode: metaPoint.yoyPct != null && state.trendView === "yoy_delta" ? "comparison_window" : "current_window",
              include_yoy_window: metaPoint.yoyPct != null && state.trendView === "yoy_delta",
            }
          );
          payload.clicked_time_grain = state.trendGrain === "quarterly" ? "quarter" : state.trendGrain === "yearly" ? "year" : "month";
          payload.clicked_time_value = metaPoint.rawBucket;
          openUniversal(payload, document.getElementById(canvasId));
        },
        plugins: {
          legend: {
            position: "bottom",
            onClick: (evt, item, legend) => {
              const ds = legend?.chart?.data?.datasets?.[item.datasetIndex];
              const repId = ds?.repId;
              if (!repId) return;
              const multi = !!(evt?.native?.ctrlKey || evt?.native?.metaKey || evt?.native?.shiftKey);
              if (multi) {
                state.trendFocusMode = false;
                state.trendSelectedReps = state.trendSelectedReps.includes(repId)
                  ? state.trendSelectedReps.filter((value) => value !== repId)
                  : [...state.trendSelectedReps, repId];
              } else {
                const alreadyFocused = state.trendFocusMode && state.trendSelectedReps.length === 1 && state.trendSelectedReps[0] === repId;
                state.trendFocusMode = !alreadyFocused;
                state.trendSelectedReps = alreadyFocused ? [] : [repId];
              }
              renderTrend(lastPayload?.charts?.trend || lastPayload?.trend || {});
            },
          },
          tooltip: {
            callbacks: {
              title: (items) => items?.[0]?.dataset?.metaPoints?.[items?.[0]?.dataIndex]?.label || items?.[0]?.label || "",
              label: (ctx) => {
                const point = ctx.dataset?.metaPoints?.[ctx.dataIndex];
                if (!point) return `${ctx.dataset.label}: ${ctx.formattedValue}`;
                if (state.trendView === "yoy_delta") return `${ctx.dataset.label}: ${point.displayValue == null ? NA : `${fmtPct.format(num(point.displayValue))}%`}`;
                if (state.trendView === "index") return `${ctx.dataset.label}: ${point.displayValue == null ? NA : fmtInt.format(num(point.displayValue))}`;
                // ── 5B: enhanced tooltip: rep — value · ±X% vs prior month ──
                const valStr = trendMetricFormatter(chartMetric, point.displayValue);
                const momStr = point.momPct != null ? ` · ${point.momPct >= 0 ? "+" : ""}${fmtPct.format(point.momPct)}% vs prior month` : "";
                return `${ctx.dataset.label} \u2014 ${valStr} revenue${momStr}`;
              },
              afterLabel: (ctx) => {
                const point = ctx.dataset?.metaPoints?.[ctx.dataIndex];
                if (!point) return [];
                const lines = [];
                if (point.current != null && state.trendView !== "absolute") lines.push(`Current: ${trendMetricFormatter(chartMetric, point.current)}`);
                if (point.prior != null) lines.push(`Prior year: ${trendMetricFormatter(chartMetric, point.prior)}`);
                if (point.yoyPct != null) lines.push(`YoY: ${point.yoyPct >= 0 ? "+" : ""}${fmtPct.format(point.yoyPct)}%`);
                if (point.momPct != null) lines.push(`MoM: ${point.momPct >= 0 ? "+" : ""}${fmtPct.format(point.momPct)}%`);
                if (point.direct_revenue != null || point.inherited_revenue != null) {
                  lines.push(`Direct / Inherited: ${money(point.direct_revenue)} / ${money(point.inherited_revenue)}`);
                }
                if (point.customers != null) lines.push(`Customers: ${fmtInt.format(num(point.customers))}`);
                if (point.observed_days != null || point.observed_days_yoy != null) {
                  lines.push(`Observed days: ${fmtInt.format(num(point.observed_days))} / ${fmtInt.format(num(point.observed_days_yoy))}`);
                }
                if (point.prior != null && !point.comparableYoY) lines.push("YoY withheld due to incomplete prior-year coverage.");
                return lines;
              },
            },
          },
        },
        scales: {
          y: {
            ticks: {
              callback: (value) => {
                if (state.trendView === "yoy_delta") return `${fmtPct.format(value)}%`;
                if (state.trendView === "index") return fmtInt.format(value);
                return conf.fmt(value);
              },
            },
          },
        },
      },
    });
    if (!chart) toggleEmpty(canvasId, true, "Chart unavailable.");
  };

  const renderMonthlyCompare = (chartData = {}) => {
    const canvasId = "monthlyCompareChart";
    const detail = Array.isArray(chartData.detail) ? chartData.detail : [];
    const rows = detail.length
      ? detail
      : (Array.isArray(chartData.labels) ? chartData.labels.map((label, idx) => ({
        bucket: label,
        revenue: chartData.revenue?.[idx],
        revenue_yoy: chartData.revenue_yoy?.[idx],
        profit: chartData.profit?.[idx],
        profit_yoy: chartData.profit_yoy?.[idx],
        weight_lb: chartData.weight_lb?.[idx],
        weight_lb_yoy: chartData.weight_lb_yoy?.[idx],
      })) : []);
    const labels = rows.map((row) => bucketLabelFromKey(row.bucket, "monthly"));
    const revenue = rows.map((row) => num(row.revenue));
    const revenueYoY = rows.map((row) => opt(row.revenue_yoy));
    const yoyPct = rows.map((row) => {
      const current = num(row.revenue);
      const prior = opt(row.revenue_yoy);
      return comparableObservedDays(row.observed_days, row.observed_days_yoy) && prior && prior !== 0
        ? ((current - prior) / Math.abs(prior)) * 100
        : null;
    });
    const hasData = rows.length > 0 && rows.some((row) => num(row.revenue) !== 0 || opt(row.revenue_yoy) !== null);

    toggleEmpty(canvasId, !hasData);
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("monthlyCompare");
      return;
    }

    // ── Phase 1 fix: calibrate y1 (right axis) from actual YoY values ──
    const validYoy = yoyPct.filter((v) => v != null);
    const y1Min = validYoy.length ? Math.floor(Math.min(...validYoy) - 3) : -25;
    const y1Max = validYoy.length ? Math.ceil(Math.max(...validYoy) + 3) : 5;

    // "Today" marker: find current month bucket in labels array
    const todayBucket = new Date().toISOString().slice(0, 7);  // "YYYY-MM"
    const rawBuckets = rows.map((r) => r.bucket || "");
    const todayIndex = rawBuckets.findIndex((b) => String(b).slice(0, 7) === todayBucket);

    const chart = createChart("monthlyCompare", canvasId, {
      type: "line",
      data: {
        labels,
        datasets: [
          {
            type: "bar",
            label: "Current Revenue",
            data: revenue,
            yAxisID: "y",                              // ← explicit left axis
            borderColor: "#965951",                    // ← brand primary
            backgroundColor: "rgba(150,89,81,0.60)",
            borderWidth: 1,
            borderRadius: 4,
          },
          {
            type: "bar",
            label: "Prior-Year Revenue",
            data: revenueYoY,
            yAxisID: "y",                              // ← explicit left axis
            borderColor: "#d39c5f",                    // ← brand gold
            backgroundColor: "rgba(211,156,95,0.40)",
            borderWidth: 1,
            borderRadius: 4,
          },
          {
            type: "line",
            label: "YoY %",
            data: yoyPct,
            yAxisID: "y1",                             // ← RIGHT axis (was missing type)
            borderColor: "#198754",
            backgroundColor: "rgba(25,135,84,0.10)",
            borderWidth: 2,
            tension: 0.25,
            pointRadius: 4,
            pointBackgroundColor: "#198754",
            fill: false,
            spanGaps: true,
          },
        ],
      },
      plugins: [
        {
          id: "mcTodayMarker",
          afterDraw: (chartInst) => {
            if (todayIndex < 0) return;
            const xScale = chartInst.scales.x;
            const yScale = chartInst.scales.y;
            if (!xScale || !yScale) return;
            const x = xScale.getPixelForIndex(todayIndex);
            const ctx2 = chartInst.ctx;
            ctx2.save();
            ctx2.beginPath();
            ctx2.moveTo(x, yScale.top);
            ctx2.lineTo(x, yScale.bottom);
            ctx2.strokeStyle = "#965951";
            ctx2.lineWidth = 1.5;
            ctx2.setLineDash([4, 3]);
            ctx2.stroke();
            ctx2.setLineDash([]);
            ctx2.fillStyle = "#965951";
            ctx2.font = "10px Inter, sans-serif";
            ctx2.fillText("Today", x + 4, yScale.top + 12);
            ctx2.restore();
          },
        },
      ],
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        onClick: (_evt, activeEls) => {
          const idx = activeEls?.[0]?.index;
          if (idx == null) return;
          const row = rows[idx];
          if (!row) return;
          const payload = attributedWorkspacePayload("Trend Intelligence", "Current vs Prior-Year Trend", "Revenue", row.revenue, {
            filter_mode: "comparison_window",
            include_yoy_window: true,
          });
          payload.clicked_time_grain = "month";
          payload.clicked_time_value = row.bucket;
          openUniversal(payload, document.getElementById(canvasId));
        },
        plugins: {
          legend: {
            position: "top",
            labels: { font: { size: 12, family: "Inter, sans-serif" } },
          },
          tooltip: {
            callbacks: {
              title: (items) => items?.[0]?.label || "",
              label: (ctx) => {
                if (ctx.dataset.label === "YoY %") {
                  const v = ctx.parsed.y;
                  return `YoY Change: ${v == null ? "N/A" : (v >= 0 ? "+" : "") + fmtPct.format(v) + "%"}`;
                }
                return `${ctx.dataset.label}: ${fmtMoney0.format(ctx.parsed.y ?? 0)}`;
              },
              afterBody: (items) => {
                const idx = items?.[0]?.dataIndex;
                const row = idx == null ? null : rows[idx];
                if (!row) return [];
                const lines = [];
                if (row.direct_revenue != null || row.inherited_revenue != null) {
                  lines.push(`Direct / Inherited: ${money(row.direct_revenue)} / ${money(row.inherited_revenue)}`);
                }
                if (row.customers != null || row.customers_yoy != null) {
                  lines.push(`Customers: ${fmtInt.format(num(row.customers))} / ${fmtInt.format(num(row.customers_yoy))}`);
                }
                if (row.observed_days != null || row.observed_days_yoy != null) {
                  lines.push(`Observed days: ${fmtInt.format(num(row.observed_days))} / ${fmtInt.format(num(row.observed_days_yoy))}`);
                }
                if (opt(row.revenue_yoy) != null && !comparableObservedDays(row.observed_days, row.observed_days_yoy)) {
                  lines.push("YoY withheld due to incomplete prior-year coverage.");
                }
                return lines;
              },
            },
          },
        },
        scales: {
          x: {
            type: "category",
            stacked: false,
            grid: { display: false },
            ticks: { maxRotation: 45, font: { size: 11 } },
          },
          y: {
            type: "linear",
            position: "left",
            stacked: false,
            beginAtZero: true,
            ticks: { callback: (v) => fmtMoney0.format(v) },
            grid: { color: "rgba(0,0,0,0.06)" },
          },
          y1: {
            // ── RIGHT axis — YoY % only ──
            type: "linear",
            position: "right",
            stacked: false,
            min: y1Min,                              // ← calibrated to data range
            max: y1Max,
            grid: { drawOnChartArea: false },
            ticks: {
              callback: (v) => `${fmtPct.format(v)}%`,
              color: "#198754",
            },
          },
        },
      },
    });
    if (!chart) toggleEmpty(canvasId, true, "Chart unavailable.");

    // ── Phase 1: wire PNG download button ──
    const dlBtn = document.getElementById("btnMonthlyComparePng");
    const chartContainer = dlBtn?.parentElement;
    if (dlBtn && chartContainer) {
      dlBtn.onclick = () => {
        const img = chart?.toBase64Image?.();
        if (!img) return;
        const a = document.createElement("a");
        a.href = img;
        a.download = "trsm_trend_compare.png";
        a.click();
      };
      chartContainer.addEventListener("mouseenter", () => { dlBtn.style.display = "block"; });
      chartContainer.addEventListener("mouseleave", () => { dlBtn.style.display = "none"; });
    }
  };

  const renderOwnershipDelta = (rows = []) => {
    const canvasId = "ownershipDeltaChart";
    const ranked = (Array.isArray(rows) ? rows : []).slice(0, 10);
    const hasData = ranked.length > 0;

    toggleEmpty(canvasId, !hasData);
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("ownershipDelta");
      return;
    }

    const chart = createChart("ownershipDelta", canvasId, {
      type: "bar",
      data: {
        labels: ranked.map((r) => repDisplayName(r)),
        datasets: [
          {
            label: "Historical Revenue",
            data: ranked.map((r) => num(r.historical_revenue)),
            backgroundColor: "#adb5bd",
          },
          {
            label: "Current Owner Revenue",
            data: ranked.map((r) => num(r.current_owner_revenue)),
            backgroundColor: "#0d6efd",
          },
        ],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          tooltip: {
            callbacks: {
              afterBody: (items) => {
                const idx = items?.[0]?.dataIndex;
                const row = idx == null ? null : ranked[idx];
                return row ? `Delta: ${money(row.ownership_delta_revenue)}` : "";
              },
            },
          },
        },
      },
    });
    if (!chart) toggleEmpty(canvasId, true, "Chart unavailable.");
  };

  const renderTransfers = (rows = []) => {
    const canvasId = "transferChart";
    const ranked = (Array.isArray(rows) ? rows : []).slice(0, 10);
    const hasData = ranked.length > 0;

    toggleEmpty(canvasId, !hasData);
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("transfer");
      return;
    }

    const chart = createChart("transfer", canvasId, {
      type: "bar",
      data: {
        labels: ranked.map((r) => repDisplayName(r)),
        datasets: [
          {
            label: "Transferred In",
            data: ranked.map((r) => num(r.transferred_in_revenue)),
            backgroundColor: "#198754",
          },
          {
            label: "Transferred Out",
            data: ranked.map((r) => num(r.transferred_out_revenue) * -1),
            backgroundColor: "#dc3545",
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
          openUniversal(
            repWorkspacePayload(row, "Trend Intelligence", "Transferred Revenue", "Transferred Revenue", num(row.transferred_in_revenue) - num(row.transferred_out_revenue), {
              filter_mode: "current_window",
              transfer_activity_only: true,
              detail: "Transferred account activity for the selected current owner.",
            }),
            document.getElementById(canvasId)
          );
        },
        scales: {
          y: { ticks: { callback: (v) => fmtMoney0.format(v) } },
        },
        plugins: {
          tooltip: {
            callbacks: {
              afterBody: (items) => {
                const idx = items?.[0]?.dataIndex;
                const row = idx == null ? null : ranked[idx];
                if (!row) return [];
                return [
                  `Direct revenue: ${money(row.direct_revenue)}`,
                  `Inherited customers: ${fmtInt.format(num(row.inherited_customers))}`,
                  `Gained / Lost: ${fmtInt.format(num(row.gained_customers))} / ${fmtInt.format(num(row.lost_customers))}`,
                ];
              },
            },
          },
        },
      },
    });
    if (!chart) toggleEmpty(canvasId, true, "Chart unavailable.");
  };

  const renderOwnershipHighlights = (payload = {}) => {
    const holder = document.getElementById("srOwnershipHighlights");
    if (!holder) return;
    const k = payload.kpis || {};
    const meta = payload.meta || {};
    const bridge = meta.ownership_bridge || {};
    const ownership = payload.analysis?.ownership_breakdown || {};
    const items = [
      {
        label: "Direct vs inherited revenue",
        value: `${money(ownership.direct_revenue)} / ${money(ownership.inherited_revenue)}`,
        payload: attributedWorkspacePayload("Insight Strip", "Ownership Highlights", "Revenue Split", ownership.direct_revenue, { filter_mode: "current_window" }),
      },
      {
        label: "Direct vs inherited customers",
        value: `${fmtInt.format(num(ownership.direct_customers))} / ${fmtInt.format(num(ownership.inherited_customers))}`,
        payload: attributedWorkspacePayload("Insight Strip", "Ownership Highlights", "Customer Split", ownership.direct_customers, { filter_mode: "current_window" }),
      },
      {
        label: "Transferred-in customers",
        value: fmtInt.format(num(ownership.transferred_in_customers)),
        payload: attributedWorkspacePayload("Insight Strip", "Ownership Highlights", "Transferred Customers", ownership.transferred_in_customers, {
          filter_mode: "current_window",
          inherited_only: true,
        }),
      },
      {
        label: "Ownership mapping coverage",
        value: bridge.available ? `${fmtInt.format(num(bridge.rows))} bridge assignments` : "Fact fallback visible",
        payload: null,
      },
    ];
    holder.innerHTML = items
      .map((item) => `
        <li class="risk-item"${drillAttr(item.payload)}>
          <span>${escapeHtml(item.label)}</span>
          <span class="sr-badge-neutral">${escapeHtml(item.value)}</span>
        </li>
      `)
      .join("");
  };

  const renderSimpleList = (id, rows = [], renderItem) => {
    const holder = document.getElementById(id);
    if (!holder) return;
    if (!Array.isArray(rows) || !rows.length) {
      holder.innerHTML = '<li class="sr-empty-list">No visible activity in the selected window.</li>';
      return;
    }
    holder.innerHTML = rows.map(renderItem).join("");
  };

  // ── 3A+3B: Territory bar chart & summary chips ──
  const renderTerritoryChart = (territories = []) => {
    const chips = document.getElementById("srTerritorySummaryChips");
    if (chips && territories.length) {
      const topT = territories[0] || {};
      const mostReps = [...territories].sort((a, b) => num(b.rep_count ?? b.reps) - num(a.rep_count ?? a.reps))[0] || {};
      chips.innerHTML = [
        `<span class="sr-badge-neutral">Territories: ${territories.length}</span>`,
        topT.territory_name ? `<span class="sr-badge-neutral">Top: ${escapeHtml(topT.territory_name)}</span>` : "",
        topT.revenue ? `<span class="sr-badge-neutral">Largest: ${money(topT.revenue)}</span>` : "",
        mostReps.territory_name ? `<span class="sr-badge-neutral">Most reps: ${escapeHtml(mostReps.territory_name)} (${fmtInt.format(num(mostReps.rep_count ?? mostReps.reps))})</span>` : "",
      ].filter(Boolean).join("");
    }

    if (!ChartLib || !territories.length) return;
    const sorted = [...territories].sort((a, b) => num(b.revenue) - num(a.revenue)).slice(0, 10);
    const maxRev = Math.max(...sorted.map((t) => num(t.revenue)));
    const resolved = resolveChartCanvas("srTerritoryChart");
    if (!resolved) return;
    destroyChart("territory");
    charts["territory"] = new ChartLib(resolved.ctx, {
      type: "bar",
      data: {
        labels: sorted.map((t) => t.territory_name || NA),
        datasets: [{
          label: "Revenue",
          data: sorted.map((t) => num(t.revenue)),
          backgroundColor: sorted.map((t) => num(t.revenue) === maxRev ? "rgba(150,89,81,1.0)" : "rgba(150,89,81,0.65)"),
          borderRadius: 3,
        }],
      },
      options: {
        indexAxis: "y",
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              label: (ctx) => {
                const t = sorted[ctx.dataIndex] || {};
                const reps = t.rep_count ?? t.reps ?? 0;
                const custs = t.customer_count ?? 0;
                return `${money(ctx.parsed.x)} · ${reps} rep${reps !== 1 ? "s" : ""} · ${fmtInt.format(num(custs))} customers`;
              },
            },
          },
        },
        scales: {
          x: { ticks: { callback: (v) => fmtMoney0.format(v), maxTicksLimit: 4 } },
          y: { ticks: { font: { size: 11 } } },
        },
      },
    });
    // Hide fallback list since chart is rendering
    const list = document.getElementById("srTerritoryList");
    if (list) list.classList.add("d-none");
  };

  const renderPortfolioSection = (payload = {}) => {
    const analysis = payload.analysis || {};
    renderTerritoryChart(analysis.territories || []);
    // Keep fallback list for no-chart scenarios
    renderSimpleList("srTerritoryList", analysis.territories || [], (row) => `
      <li${drillAttr(territoryPayload(row.territory_name, "Ownership & Portfolio", "Top Territories", "Revenue", row.revenue, {
        filter_mode: "current_window",
        detail: "Territory-specific attributed detail from the current owner portfolio.",
      }))}>
        <div>
          <div class="sr-list-main">${escapeHtml(row.territory_name || NA)}</div>
          <div class="sr-list-sub">${fmtInt.format(num(row.customer_count))} customers · ${pct(row.revenue_share_pct, true)} share · ${money(row.inherited_revenue)} inherited</div>
        </div>
        <div class="sr-list-metric">${money(row.revenue)}</div>
      </li>
    `);
    renderSimpleList("srReplacementPairs", analysis.replacement_pairs || [], (row) => `
      <li${drillAttr(attributedWorkspacePayload("Ownership & Portfolio", "Replacement / Transfer Audit", "Inherited Revenue", row.inherited_revenue, {
        filter_mode: "current_window",
        inherited_only: true,
        current_owner_id: row.current_owner_key,
        current_owner_name: row.current_owner_name,
        prior_rep_name: row.prior_rep_name,
        detail: "Attributed replacement-pair detail including inherited customers and territories.",
      }))}>
        <div>
          <div class="sr-list-main">${escapeHtml(businessRepName(row.current_owner_name, row.current_owner_key, UNASSIGNED_REP_FALLBACK))}</div>
          <div class="sr-list-sub">Inherited from ${escapeHtml(businessRepName(row.prior_rep_name, row.prior_rep_key, READABLE_REP_FALLBACK))}${row.territories ? ` · ${escapeHtml(row.territories)}` : ""}${row.time_window ? ` · ${escapeHtml(row.time_window)}` : ""}</div>
        </div>
        <div class="sr-list-metric">${money(row.inherited_revenue)} · ${fmtInt.format(num(row.customer_count))} cust.</div>
      </li>
    `);

    setDrillPayload(
      document.getElementById("srInheritedCustomers")?.closest(".sr-highlight-card"),
      attributedWorkspacePayload("Ownership & Portfolio", "Inherited Customers", "Inherited Customers", payload.kpis?.inherited_customers, {
        filter_mode: "current_window",
        inherited_only: true,
      })
    );
    setDrillPayload(
      document.getElementById("srPortfolioTerritoryCount")?.closest(".sr-highlight-card"),
      territoryPayload(analysis.territories?.[0]?.territory_name, "Ownership & Portfolio", "Top Territories", "Revenue", analysis.territories?.[0]?.revenue, {
        filter_mode: "current_window",
      })
    );
    setDrillPayload(
      document.getElementById("srPortfolioReplacedCount")?.closest(".sr-highlight-card"),
      attributedWorkspacePayload("Ownership & Portfolio", "Replaced Reps", "Replaced Reps", payload.kpis?.replaced_rep_count, {
        filter_mode: "current_window",
        inherited_only: true,
        detail: "Visible inherited-book activity grouped by prior rep and current owner.",
      })
    );
    setDrillPayload(
      document.getElementById("srUnassignedCustomers")?.closest(".sr-highlight-card"),
      attributedWorkspacePayload("Ownership & Portfolio", "Unassigned Customers", "Unassigned Customers", payload.kpis?.unassigned_customers, {
        filter_mode: "current_window",
        dq_bucket: "unassigned",
      })
    );
  };

  const renderDataQuality = (rows = []) => {
    const tbody = document.getElementById("srDataQualityBody");
    if (!tbody) return;
    const bucketLabel = (bucket) => {
      const normalized = String(bucket || "").trim().toLowerCase();
      const labels = {
        fact_fallback: "Fact owner fallback",
        fact_owner_only: "Fact owner fallback",
        inactive_current_owner: "Inactive current owner",
        needs_review: "Needs review",
        unassigned: "Unassigned / needs review",
      };
      if (labels[normalized]) return labels[normalized];
      return String(bucket || NA)
        .replace(/_/g, " ")
        .replace(/\b\w/g, (ch) => ch.toUpperCase());
    };
    if (!Array.isArray(rows) || !rows.length) {
      tbody.innerHTML = '<tr><td colspan="3" class="text-muted">No mapping exceptions detected in the visible scope.</td></tr>';
      return;
    }
    tbody.innerHTML = rows
      .map((row) => `
        <tr${drillAttr(attributedWorkspacePayload("Ownership & Portfolio", "Coverage & Exceptions", "Customers", row.customer_count, {
          filter_mode: "current_window",
          dq_bucket: row.bucket,
          detail: "Attributed ownership exception detail for the selected data-quality bucket.",
        }))}>
          <td>${escapeHtml(bucketLabel(row.bucket))}</td>
          <td class="text-end">${fmtInt.format(num(row.customer_count))}</td>
          <td class="text-end">${money(row.revenue)}</td>
        </tr>
      `)
      .join("");
  };

  // ── Phase 3A: customer risk signal ──
  const computeCustomerRisk = (row) => {
    if ((row.revenue_last_30 ?? row.revenue ?? 0) === 0 && (row.revenue_prev_30 ?? 0) > 0)
      return { signal: "lost",    label: "Lost",     score: 4 };
    let neg = 0;
    if ((row.mom_revenue_pct ?? row.vs_prior_pct ?? 0) < -5)  neg++;
    if ((row.yoy_revenue_pct ?? row.yoy_pct ?? 0) < -10)      neg++;
    if ((row.days_since_order ?? 0) > 45)                     neg++;
    if (neg === 0) return { signal: "healthy", label: "Healthy", score: 0 };
    if (neg === 1) return { signal: "watch",   label: "Watch",   score: 1 };
    return           { signal: "atrisk",  label: "At Risk", score: 2 };
  };

  const _riskPillHtml = (risk) => {
    const cls = { healthy: "sr-risk-healthy", watch: "sr-risk-watch", atrisk: "sr-risk-atrisk", lost: "sr-risk-lost" }[risk.signal] || "";
    return `<span class="sr-risk-pill ${cls}">${escapeHtml(risk.label)}</span>`;
  };

  // ── Phase 3B: customer search + owner pill state ──
  let _customerSearchQ  = "";
  let _activeOwnerFilter = "";

  // ── Customer view toggle state (1A) ──
  let _customerViewMode = "all";
  let _allCustomerRows = [];

  const _computeCustomerScores = (rows) => {
    // Composite score: revenue_rank * 0.40 + profit_rank * 0.35 + mom_rank * 0.25
    // Uses vs_prior_pct (prior-period MoM equivalent) as the momentum signal
    const n = rows.length;
    if (n === 0) return [];

    const hasProfitData = rows.some((r) => opt(r.profit) !== null && opt(r.profit) !== 0);
    const weights = hasProfitData ? { rev: 0.40, profit: 0.35, mom: 0.25 } : { rev: 0.60, profit: 0, mom: 0.40 };

    const ranked = [...rows].map((r, origIdx) => ({ ...r, _origIdx: origIdx }));

    const rankBy = (arr, fn) => {
      const sorted = [...arr].sort((a, b) => fn(a) - fn(b));
      const rankMap = new Map();
      sorted.forEach((r, i) => rankMap.set(r._origIdx, i + 1));
      return rankMap;
    };

    const revRanks   = rankBy(ranked, (r) => num(r.revenue));
    const profitRanks = hasProfitData ? rankBy(ranked, (r) => num(r.profit)) : null;
    // vs_prior_pct is the prior-period % change (MoM equivalent from the bundle)
    const momRanks   = rankBy(ranked, (r) => num(r.vs_prior_pct ?? r.yoy_revenue_pct));

    return rows.map((r, i) => {
      const score =
        revRanks.get(i) * weights.rev +
        (profitRanks ? profitRanks.get(i) * weights.profit : 0) +
        momRanks.get(i) * weights.mom;
      return { ...r, _score: score };
    });
  };

  const _buildCustomerRowHtml = (row, badge = null) => {
    const badgeHtml = badge
      ? `<span class="sr-cust-badge ${badge.cls}">${badge.text}</span>`
      : "";
    const yoyBadge = badge && badge.showYoyDrag && opt(row.yoy_revenue_pct) !== null && num(row.yoy_revenue_pct) < -20
      ? `<span class="sr-cust-badge sr-cust-badge-yoy">YoY Drag</span>`
      : "";
    const rowClass = badge
      ? badge.view === "best" ? "sr-cust-best-row" : (num(row.vs_prior_pct ?? row.yoy_revenue_pct) < -15 ? "sr-cust-risk-row" : "")
      : "";

    // ── Phase 3A: risk column ──
    const risk = computeCustomerRisk(row);
    const riskHtml = _riskPillHtml(risk);

    // ── Phase 3C: YoY % with colour + icon ──
    const yoyVal = row.yoy_revenue_pct;
    let yoyCellHtml = NA;
    if (yoyVal != null) {
      const v = num(yoyVal);
      if (v > 2)       yoyCellHtml = `<span style="color:#198754">&#9650; ${fmtPct.format(v)}%</span>`;
      else if (v < -2) yoyCellHtml = `<span style="color:#dc3545">&#9660; ${fmtPct.format(Math.abs(v))}%</span>`;
      else             yoyCellHtml = `<span class="text-muted">&#8776; ${fmtPct.format(v)}%</span>`;
    }

    // ── Phase 3C: revenue inline mini bar (computed by caller via maxRevenue) ──
    const rev = num(row.revenue);
    const maxRev = row._maxRevenue || rev || 1;
    const barPct = Math.min(100, Math.round((rev / maxRev) * 100));
    const revBarHtml = `<div style="height:3px;width:${barPct}%;background:rgba(150,89,81,0.35);border-radius:2px;margin-top:2px"></div>`;

    return `
      <tr class="${rowClass}"${drillAttr(customerPayload(row, "Customer Intelligence", "Top Customers", "Revenue", row.revenue))}>
        <td>
          ${badgeHtml}${yoyBadge}
          <span class="sr-link"${drillAttr(customerPayload(row, "Customer Intelligence", "Top Customers", "Revenue", row.revenue))}>${escapeHtml(row.customer_name || row.customer_id || NA)}</span>
        </td>
        <td>${riskHtml}</td>
        <td><span class="sr-link"${drillAttr(salesrepPayload({ rep_id: row.account_owner_id || row.account_owner_name, rep_name: row.account_owner_name }, "Customer Intelligence", "Top Customers", "Revenue", row.revenue))}>${escapeHtml(businessRepName(row.account_owner_name, row.account_owner_id, READABLE_REP_FALLBACK))}</span></td>
        <td><span class="sr-link"${drillAttr(territoryPayload(row.territory_name, "Customer Intelligence", "Top Customers", "Revenue", row.revenue, { filter_mode: "current_window" }))}>${escapeHtml(row.territory_name || NA)}</span></td>
        <td class="text-end">${money(rev)}${revBarHtml}</td>
        <td class="text-end">${row.profit == null ? NA : money(row.profit)}</td>
        <td class="text-end">${yoyCellHtml}</td>
      </tr>
    `;
  };

  const _applyCustomerView = (rows, viewMode) => {
    const tbody = document.getElementById("srTopCustomersBody");
    if (!tbody) return;

    // Fade out
    tbody.querySelectorAll("tr").forEach((tr) => { tr.style.opacity = "0"; });

    const render = () => {
      if (!Array.isArray(rows) || !rows.length) {
        tbody.innerHTML = '<tr><td colspan="7" class="text-muted">No customer activity for the selected filters.</td></tr>';
        return;
      }

      // ── Phase 3B: apply owner filter then search ──
      let filtered = rows;
      if (_activeOwnerFilter) {
        filtered = filtered.filter((r) => (r.account_owner_name || "") === _activeOwnerFilter);
      }
      const q = (_customerSearchQ || "").trim().toLowerCase();
      if (q) {
        filtered = filtered.filter((r) =>
          (r.customer_name || "").toLowerCase().includes(q) ||
          (r.account_owner_name || "").toLowerCase().includes(q) ||
          (r.territory_name || "").toLowerCase().includes(q)
        );
      }

      if (!filtered.length) {
        const msg = q
          ? `No customers match &ldquo;${escapeHtml(q)}&rdquo;. Try a shorter search term.`
          : "No customers match the current filter.";
        tbody.innerHTML = `<tr><td colspan="7" class="text-muted">${msg}</td></tr>`;
        tbody.querySelectorAll("tr").forEach((tr) => { tr.style.opacity = "1"; });
        return;
      }

      // ── Phase 3C: compute maxRevenue for inline bars ──
      const maxRevenue = Math.max(...filtered.map((r) => num(r.revenue)), 1);

      if (viewMode === "all") {
        const ranked = sortRows(filtered, state.topCustomersSortBy, state.topCustomersSortDir, (row, key) => {
          if (key === "customer_name") return row.customer_name || row.customer_id;
          if (key === "_risk_score")   return computeCustomerRisk(row).score;
          return row[key];
        });
        tbody.innerHTML = ranked.map((r) => _buildCustomerRowHtml({ ...r, _maxRevenue: maxRevenue }, null)).join("");
      } else {
        const scored = _computeCustomerScores(filtered);
        if (viewMode === "best") {
          const top10 = [...scored].sort((a, b) => b._score - a._score).slice(0, 10);
          tbody.innerHTML = top10.map((r) => _buildCustomerRowHtml({ ...r, _maxRevenue: maxRevenue }, { cls: "sr-cust-badge-best", text: "\u2605 Top Performer", view: "best", showYoyDrag: false })).join("");
        } else {
          const bottom10 = [...scored].sort((a, b) => a._score - b._score).slice(0, 10);
          tbody.innerHTML = bottom10.map((r) => _buildCustomerRowHtml({ ...r, _maxRevenue: maxRevenue }, { cls: "sr-cust-badge-risk", text: "\u26A0 At-Risk", view: "atrisk", showYoyDrag: true })).join("");
        }
      }
      // Fade in
      tbody.querySelectorAll("tr").forEach((tr) => { tr.style.opacity = "1"; });
    };

    setTimeout(render, 150);
  };

  const renderTopCustomers = (rows = [], lostAccounts = []) => {
    _allCustomerRows = Array.isArray(rows) ? rows : [];
    buildOwnerPills(_allCustomerRows);
    _applyCustomerView(_allCustomerRows, _customerViewMode);

    // ── Phase 3F: customer summary line ──
    const summaryEl = document.getElementById("srCustSummaryLine");
    if (summaryEl) {
      const totalActive = _allCustomerRows.filter((r) => num(r.revenue ?? r.revenue_last_30) > 0).length;
      const gained      = _allCustomerRows.filter((r) => (r.revenue_prev_30 ?? 0) === 0 && num(r.revenue_last_30 ?? r.revenue) > 0).length;
      const lost        = lostAccounts.length;
      summaryEl.textContent = `${fmtInt.format(totalActive)} active customers · ${gained} gained · ${lost} lost · click Best / At-Risk to filter`;
    }
  };

  // Wire up toggle buttons once DOM is ready (called after renderBundle)
  const initCustomerViewToggle = () => {
    document.querySelectorAll("[data-customer-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        _customerViewMode = btn.dataset.customerView;
        document.querySelectorAll("[data-customer-view]").forEach((b) => b.classList.toggle("active", b === btn));
        _applyCustomerView(_allCustomerRows, _customerViewMode);
      });
    });

    // ── Phase 3B: search input (debounced 200ms) ──
    const searchInput = document.getElementById("srCustomerSearch");
    if (searchInput) {
      let searchTimer;
      searchInput.addEventListener("input", () => {
        clearTimeout(searchTimer);
        searchTimer = setTimeout(() => {
          _customerSearchQ = searchInput.value;
          _applyCustomerView(_allCustomerRows, _customerViewMode);
        }, 200);
      });
    }

    // ── Phase 3B: export view CSV ──
    const btnExportCust = document.getElementById("btnExportCustCSV");
    if (btnExportCust) {
      btnExportCust.addEventListener("click", () => {
        const today = new Date().toISOString().slice(0, 10);
        const filename = `trsm_customers_${_customerViewMode}_${today}.csv`;
        const rows = _allCustomerRows
          .filter((r) => {
            const q = (_customerSearchQ || "").trim().toLowerCase();
            if (_activeOwnerFilter && (r.account_owner_name || "") !== _activeOwnerFilter) return false;
            if (!q) return true;
            return (r.customer_name || "").toLowerCase().includes(q) ||
                   (r.account_owner_name || "").toLowerCase().includes(q) ||
                   (r.territory_name || "").toLowerCase().includes(q);
          });
        const header = ["Customer", "Owner", "Territory", "Revenue (30d)", "YoY %", "Risk Signal"];
        const csvLines = [header.join(","), ...rows.map((r) => {
          const risk = computeCustomerRisk(r);
          return [
            `"${(r.customer_name || r.customer_id || "").replace(/"/g, '""')}"`,
            `"${(r.account_owner_name || "").replace(/"/g, '""')}"`,
            `"${(r.territory_name || "").replace(/"/g, '""')}"`,
            fmtMoney0.format(num(r.revenue)),
            r.yoy_revenue_pct != null ? `${fmtPct.format(num(r.yoy_revenue_pct))}%` : "",
            risk.label,
          ].join(",");
        })];
        const blob = new Blob([csvLines.join("\n")], { type: "text/csv" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = filename;
        a.click();
      });
    }
  };

  // ── Phase 3B: owner pills builder (call after customer data loads) ──
  const buildOwnerPills = (rows) => {
    const container = document.getElementById("srOwnerPills");
    if (!container || !Array.isArray(rows)) return;
    const owners = Array.from(new Set(rows.map((r) => r.account_owner_name || "").filter(Boolean))).sort();
    if (!owners.length) { container.innerHTML = ""; return; }

    const truncate = (s, n) => s.length > n ? s.slice(0, n) + "…" : s;
    const allBtn = `<button class="sr-grain-pill active" data-owner-filter="" style="margin-right:4px">All Owners</button>`;
    const ownerBtns = owners.map((o) =>
      `<button class="sr-grain-pill" data-owner-filter="${escapeHtml(o)}" title="${escapeHtml(o)}">${escapeHtml(truncate(o, 18))}</button>`
    ).join("");
    container.innerHTML = allBtn + ownerBtns;

    container.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-owner-filter]");
      if (!btn) return;
      _activeOwnerFilter = btn.dataset.ownerFilter;
      container.querySelectorAll("[data-owner-filter]").forEach((b) =>
        b.classList.toggle("active", b === btn)
      );
      _applyCustomerView(_allCustomerRows, _customerViewMode);
    });
  };

  // ── Phase 3B: Follow-Up List CSV export (global so header button can call it) ──
  window.exportFollowUpList = () => {
    const atRisk = _allCustomerRows.filter((r) => {
      const sig = computeCustomerRisk(r).signal;
      return sig === "atrisk" || sig === "lost";
    });
    const toast = document.getElementById("srFollowUpToast");
    if (!atRisk.length) {
      if (toast) { toast.textContent = "✓ No at-risk customers to export"; toast.style.display = "block"; setTimeout(() => { toast.style.display = "none"; }, 3000); }
      return;
    }
    const today = new Date().toISOString().slice(0, 10);
    const header = ["Customer", "Owner", "Territory", "Last Revenue (prior 30d)", "Risk Signal", "Days Silent", "Suggested Action"];
    const csvLines = [header.join(","), ...atRisk.map((r) => {
      const risk = computeCustomerRisk(r);
      const days = r.days_since_order ?? "";
      const action = risk.signal === "lost"
        ? `Re-engagement call — no orders in ${days || "?"} days`
        : "Account review — declining trend";
      return [
        `"${(r.customer_name || r.customer_id || "").replace(/"/g, '""')}"`,
        `"${(r.account_owner_name || "").replace(/"/g, '""')}"`,
        `"${(r.territory_name || "").replace(/"/g, '""')}"`,
        fmtMoney0.format(num(r.revenue_prev_30 ?? r.revenue)),
        risk.label,
        days,
        `"${action}"`,
      ].join(",");
    })];
    const blob = new Blob([csvLines.join("\n")], { type: "text/csv" });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = `trsm_followup_${today}.csv`;
    a.click();
  };

  // ── 4D: Rep Comparison Modal ──
  const toggleRepSelect = (repId, rowData) => {
    const id = String(repId);
    if (selectedRepIds.has(id)) {
      selectedRepIds.delete(id);
      selectedRepRows.delete(id);
    } else if (selectedRepIds.size < 4) {
      selectedRepIds.add(id);
      if (rowData) selectedRepRows.set(id, rowData);
    }
    renderCompareToolbar();
    renderVirtualTableRows({ force: true });
  };

  const renderCompareToolbar = () => {
    const toolbar = document.getElementById("srCompareToolbar");
    const countEl = document.getElementById("srCompareCount");
    const compareBtn = document.getElementById("srCompareBtn");
    if (!toolbar) return;
    const count = selectedRepIds.size;
    if (count === 0) {
      toolbar.classList.add("d-none");
      return;
    }
    toolbar.classList.remove("d-none");
    if (countEl) countEl.textContent = `${count} rep${count !== 1 ? "s" : ""} selected`;
    if (compareBtn) compareBtn.disabled = count < 2;
  };

  const renderCompareModal = () => {
    const body = document.getElementById("srCompareModalBody");
    if (!body) return;
    const reps = Array.from(selectedRepIds).map(id => selectedRepRows.get(id)).filter(Boolean);
    if (reps.length < 2) return;

    const findBest = (vals, higher = true) => {
      const nums = vals.map(v => (v == null ? null : num(v)));
      const valid = nums.filter(v => v !== null);
      if (!valid.length) return -1;
      const target = higher ? Math.max(...valid) : Math.min(...valid);
      return nums.findIndex(v => v !== null && Math.abs(v - target) < 0.00001);
    };

    const metrics = [
      { label: "Revenue",          key: r => num(r.revenue),            fmt: r => money(r.revenue),                                            higher: true  },
      { label: "Profit",           key: r => r.profit == null ? null : num(r.profit),    fmt: r => r.profit == null ? NA : money(r.profit),  higher: true  },
      { label: "Margin %",         key: r => r.margin_pct == null ? null : num(r.margin_pct),  fmt: r => r.margin_pct == null ? NA : `${fmtPct.format(num(r.margin_pct))}%`, higher: true },
      { label: "YoY Revenue %",    key: r => r.yoy_revenue_pct == null ? null : num(r.yoy_revenue_pct), fmt: r => pct(r.yoy_revenue_pct, false), higher: true },
      { label: "Health Score",     key: r => r.health_score == null ? null : num(r.health_score), fmt: r => r.health_label ? `<span class="badge" style="background:${escapeHtml(r.health_color||'#6c757d')};color:#fff;font-size:0.7rem">${escapeHtml(r.health_label)}</span>&nbsp;${r.health_score ?? ""}/100` : NA, higher: true, raw: true },
      { label: "Active Customers", key: r => num(r.active_customers),   fmt: r => fmtInt.format(num(r.active_customers)),                     higher: true  },
      { label: "Orders",           key: r => num(r.orders),             fmt: r => fmtInt.format(num(r.orders)),                               higher: true  },
      { label: "Shipped LB",       key: r => num(r.weight_lb),          fmt: r => fmtInt.format(num(r.weight_lb)),                            higher: true  },
      { label: "Revenue Rank",     key: null, fmt: r => escapeHtml(r.quartile_label || NA) },
      { label: "Top Customer",     key: null, fmt: r => escapeHtml(r.top_customer_name || NA) },
      { label: "Top Territory",    key: null, fmt: r => escapeHtml(r.top_territory_name || NA) },
      { label: "Top Protein",      key: null, fmt: r => escapeHtml(r.top_protein_family || NA) },
    ];

    const headerCells = reps.map(r => `<th class="text-center align-middle" style="min-width:150px">${escapeHtml(repDisplayName(r, READABLE_REP_FALLBACK))}</th>`).join("");
    const metricRows = metrics.map(m => {
      const vals = reps.map(r => m.key ? m.key(r) : null);
      const winnerIdx = m.key ? findBest(vals, m.higher !== false) : -1;
      const cells = reps.map((r, idx) => {
        const display = m.raw ? m.fmt(r) : escapeHtml(m.fmt(r));
        const highlight = (winnerIdx === idx && m.key) ? " fw-semibold text-success" : "";
        return `<td class="text-center${highlight}">${display}</td>`;
      }).join("");
      return `<tr><th scope="row" class="text-muted small fw-normal py-2">${m.label}</th>${cells}</tr>`;
    }).join("");

    body.innerHTML = `<div class="table-responsive"><table class="table table-sm table-hover align-middle sr-compare-table mb-0"><thead class="table-light sticky-top"><tr><th scope="col" style="width:140px" class="text-muted">Metric</th>${headerCells}</tr></thead><tbody>${metricRows}</tbody></table></div>`;
  };

  const wireCompare = () => {
    // Checkbox delegation
    document.getElementById("salesreps-table-body")?.addEventListener("change", (evt) => {
      const cb = evt.target.closest(".sr-rep-select-cb");
      if (!cb) return;
      const repId = cb.dataset.repId;
      if (!repId) return;
      const row = (virtualTable.rows || []).find(r => String(r.rep_id || r.key || r.rep_name) === repId);
      toggleRepSelect(repId, row);
    });

    document.getElementById("srSelectAll")?.addEventListener("change", (evt) => {
      if (evt.target.checked) {
        (virtualTable.rows || []).slice(0, 4).forEach(r => {
          const id = String(r.rep_id || r.key || r.rep_name);
          selectedRepIds.add(id);
          selectedRepRows.set(id, r);
        });
      } else {
        selectedRepIds.clear();
        selectedRepRows.clear();
      }
      renderCompareToolbar();
      renderVirtualTableRows({ force: true });
    });

    document.getElementById("srCompareBtn")?.addEventListener("click", () => {
      renderCompareModal();
      const modalEl = document.getElementById("srCompareModal");
      if (modalEl && window.bootstrap?.Modal) {
        window.bootstrap.Modal.getOrCreateInstance(modalEl).show();
      }
    });

    document.getElementById("srClearCompare")?.addEventListener("click", () => {
      selectedRepIds.clear();
      selectedRepRows.clear();
      const sel = document.getElementById("srSelectAll");
      if (sel) sel.checked = false;
      renderCompareToolbar();
      renderVirtualTableRows({ force: true });
    });
  };

  // ── Lost Accounts panel (1B) ──
  const renderLostAccountsPanel = (lostAccounts = []) => {
    const badge = document.getElementById("lostAccountsBadge");
    const body  = document.getElementById("lostAccountsBody");
    if (!badge || !body) return;

    const n = lostAccounts.length;
    badge.textContent = n;
    badge.className = `badge ${n > 0 ? "bg-danger" : "bg-success"}`;

    if (n === 0) {
      body.innerHTML = '<p class="text-success mb-0">\u2713 No lost accounts. Every prior customer placed an order this period.</p>';
      return;
    }

    const rows = lostAccounts.map((a) => {
      const days = a.days_since_order ?? null;
      const daysStr = days !== null ? String(days) : "\u2014";
      const daysClass = days === null ? "" : days > 60 ? "text-danger fw-bold" : days > 30 ? "text-warning fw-semibold" : "";
      const subject = encodeURIComponent(`Follow-up: ${a.customer_name} \u2014 Re-engagement Opportunity`);
      const bodyText = encodeURIComponent(
        `Hi,\n\nWanted to follow up on ${a.customer_name}, who last placed an order ${daysStr} days ago. ` +
        `Let me know if I can assist with re-engagement.`
      );
      return `<tr>
        <td>${escapeHtml(a.customer_name || a.customer_id || NA)}</td>
        <td class="text-end">${money(a.revenue_prev_30)}</td>
        <td>${escapeHtml(a.last_order_date || "\u2014")}</td>
        <td class="${daysClass}">${daysStr}</td>
        <td><a href="mailto:?subject=${subject}&body=${bodyText}" class="btn btn-outline-secondary btn-sm">Send Follow-up &rarr;</a></td>
      </tr>`;
    }).join("");

    body.innerHTML = `
      <div class="table-responsive">
        <table class="table table-sm table-hover mb-0">
          <thead class="table-light">
            <tr>
              <th>Customer</th>
              <th class="text-end">Last Revenue</th>
              <th>Last Order</th>
              <th>Days Silent</th>
              <th>Action</th>
            </tr>
          </thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    `;
  };

  // Toggle lost accounts panel open/closed
  window.srToggleLostPanel = () => {
    const body    = document.getElementById("lostAccountsBody");
    const chevron = document.getElementById("lostPanelChevron");
    const header  = body?.previousElementSibling;
    if (!body) return;
    const isOpen = body.style.display !== "none";
    body.style.display = isOpen ? "none" : "block";
    if (chevron) chevron.style.transform = isOpen ? "" : "rotate(180deg)";
    if (header) header.setAttribute("aria-expanded", String(!isOpen));
  };

  const renderCustomerMovers = (analysis = {}) => {
    const movers = analysis.customer_movers || {};

    const moverItemHtml = (row, isDown = false) => {
      const revNow  = opt(row.revenue) ?? 0;
      const delta   = opt(row.delta_revenue) ?? 0;
      const revPrev = revNow - delta;
      const pctVal  = opt(row.delta_pct);
      let pctStr;
      if (revPrev === 0) {
        pctStr = "(new)";
      } else if (pctVal !== null) {
        pctStr = `(${pctVal >= 0 ? "+" : ""}${fmtPct.format(pctVal)}%)`;
      } else {
        pctStr = "";
      }
      const deltaClass = isDown ? "delta-down" : "delta-up";
      const isFullyLost = isDown && revNow === 0;
      const lostBadge = isFullyLost
        ? `<span class="badge bg-danger ms-1" style="font-size:0.65rem">LOST</span>`
        : "";
      const subline = `<div class="sr-mover-subline">Prior: ${money(revPrev)} &rarr; Now: ${money(revNow)}</div>`;
      return `
        <li${drillAttr(customerPayload(row, "Customer Intelligence", "Customer Movers", "Revenue Delta", row.delta_revenue))}>
          <div>
            <div class="sr-list-main">${escapeHtml(row.customer_name || row.customer_id || NA)}${lostBadge}</div>
            <div class="sr-list-sub">${escapeHtml(businessRepName(row.account_owner_name, row.account_owner_id, READABLE_REP_FALLBACK))}${row.territory_name ? ` · ${escapeHtml(row.territory_name)}` : ""}${row.yoy_revenue != null ? ` · PY ${money(row.yoy_revenue)}` : ""}</div>
            ${subline}
          </div>
          <div class="sr-list-metric ${deltaClass}">${money(row.delta_revenue)} ${pctStr ? `<span style="font-weight:400;font-size:0.8em">${pctStr}</span>` : ""}</div>
        </li>
      `;
    };

    renderSimpleList("srCustomerMoversUp",   movers.up   || [], (row) => moverItemHtml(row, false));
    renderSimpleList("srCustomerMoversDown", movers.down || [], (row) => moverItemHtml(row, true));

    // Update header stat line (1C-4): "N gained · N lost ↓"
    const gained = (movers.up   || []).length;
    const lostN  = (movers.down || []).filter((r) => (opt(r.revenue) ?? 0) === 0).length;
    const statEl = document.getElementById("srMoversStatLine");
    if (statEl) {
      const lostLink = lostN > 0
        ? `<a href="#lostAccountsPanel" class="text-danger fw-semibold" onclick="document.getElementById('lostAccountsBody')?.style.display==='none'&&srToggleLostPanel();setTimeout(()=>document.getElementById('lostAccountsPanel')?.scrollIntoView({behavior:'smooth'}),80);return false;">${lostN} lost &darr;</a>`
        : `<span>${lostN} lost</span>`;
      statEl.innerHTML = `${gained} gained &middot; ${lostLink}`;
    }
  };

  const renderProteinTable = (rows = []) => {
    const tbody = document.getElementById("srProteinTableBody");
    if (!tbody) return;
    const totalRevenue = (Array.isArray(rows) ? rows : []).reduce((acc, row) => acc + num(row.revenue), 0);
    const enriched = (Array.isArray(rows) ? rows : []).map((row) => ({ ...row, share_pct: totalRevenue > 0 ? (num(row.revenue) / totalRevenue) * 100 : null }));
    const ranked = sortRows(enriched, state.proteinSortBy, state.proteinSortDir);
    if (!ranked.length) {
      tbody.innerHTML = '<tr><td colspan="6" class="text-muted">No protein mix is available for the selected filters.</td></tr>';
      return;
    }
    tbody.innerHTML = ranked
      .map((row) => `
        <tr${drillAttr(proteinPayload(row.protein_family, "Protein Intelligence", "Protein Performance", "Revenue", row.revenue, { filter_mode: "current_window" }))}>
          <td><span class="sr-link"${drillAttr(proteinPayload(row.protein_family, "Protein Intelligence", "Protein Performance", "Revenue", row.revenue, { filter_mode: "current_window" }))}>${escapeHtml(row.protein_family || NA)}</span></td>
          <td class="text-end">${money(row.revenue)}</td>
          <td class="text-end">${row.profit == null ? NA : money(row.profit)}</td>
          <td class="text-end">${marginCellHtml(row)}</td>
          <td class="text-end">${row.share_pct == null ? NA : `${fmtPct.format(num(row.share_pct))}%`}</td>
          <td class="text-end">${row.yoy_delta_revenue == null ? NA : money(row.yoy_delta_revenue)}</td>
        </tr>
      `)
      .join("");
  };

  const renderProteinChart = (rows = []) => {
    const canvasId = "srProteinChart";
    const ranked = (Array.isArray(rows) ? rows : []).slice(0, 8);
    const hasData = ranked.length > 0;
    toggleEmpty(canvasId, !hasData);
    if (!ChartLib) return;
    if (!hasData) {
      destroyChart("protein");
      return;
    }
    const chart = createChart("protein", canvasId, {
      type: "bar",
      data: {
        labels: ranked.map((row) => row.protein_family || NA),
        datasets: [
          {
            label: "Revenue",
            data: ranked.map((row) => num(row.revenue)),
            backgroundColor: "#1f5f9a",
          },
          {
            label: "YoY Δ Revenue",
            data: ranked.map((row) => num(row.yoy_delta_revenue)),
            backgroundColor: "#d88b2a",
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
          openUniversal(
            proteinPayload(row.protein_family, "Protein Intelligence", "Protein / Category Mix", "Revenue", row.revenue, {
              filter_mode: "current_window",
            }),
            document.getElementById(canvasId)
          );
        },
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

    // ── 5A: team average reference line ──
    const avgLinePlugin = {
      id: "avgLine_topReps",
      afterDraw(chartInst) {
        const benchmarks = lastPayload?.benchmarks || {};
        const avgKey = metric === "revenue" ? "avg_revenue" : metric === "profit" ? "avg_profit" : metric === "margin_pct" ? "avg_margin_pct" : null;
        const avg = avgKey ? opt(benchmarks[avgKey]) : null;
        if (!avg) return;
        const ctx2 = chartInst.ctx;
        const xAxis = chartInst.scales.x;
        const yAxis = chartInst.scales.y;
        if (!xAxis || !yAxis) return;
        const x = xAxis.getPixelForValue(avg);
        if (x < xAxis.left || x > xAxis.right) return;
        ctx2.save();
        ctx2.setLineDash([6, 4]);
        ctx2.strokeStyle = "rgba(150,89,81,0.55)";
        ctx2.lineWidth = 1.5;
        ctx2.beginPath();
        ctx2.moveTo(x, yAxis.top);
        ctx2.lineTo(x, yAxis.bottom);
        ctx2.stroke();
        ctx2.fillStyle = "#965951";
        ctx2.font = "11px Inter, system-ui";
        ctx2.textAlign = "right";
        ctx2.fillText(`Avg: ${conf.fmt(avg)}`, xAxis.right - 4, yAxis.top + 14);
        ctx2.restore();
      },
    };

    const chart = createChart("topReps", canvasId, {
      type: "bar",
      plugins: [avgLinePlugin],
      data: {
        labels: topRows.map((r) => repDisplayName(r)),
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
              afterBody: (items) => {
                const idx = items?.[0]?.dataIndex;
                const row = idx == null ? null : topRows[idx];
                if (!row) return [];
                const rankChange = opt(row.rank_change);
                const rankLine = rankChange == null ? "Rank movement: N/A" : `Rank movement: ${rankChange > 0 ? "+" : ""}${fmtInt.format(rankChange)}`;
                return [
                  `Direct / Inherited: ${money(row.direct_revenue)} / ${money(row.inherited_revenue)}`,
                  rankLine,
                ];
              },
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
        labels: sorted.map((r) => repDisplayName(r)),
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
      rep_name: repDisplayName(r),
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
        labels: ranked.map((r) => repDisplayName(r)),
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
        rep_name: repDisplayName(r),
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
        labels: sorted.map((r) => repDisplayName(r)),
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
      const payload = f.key === "top_customer_concentration"
        ? attributedWorkspacePayload("Insight Strip", "Risk Watch", f.label, f.count, { filter_mode: "current_window" })
        : f.key === "low_margin"
          ? attributedWorkspacePayload("Insight Strip", "Risk Watch", f.label, f.count, { filter_mode: "current_window" })
          : f.key === "profit_decline"
            ? attributedWorkspacePayload("Insight Strip", "Risk Watch", f.label, f.count, { filter_mode: "current_window" })
            : f.key === "unassigned_customers"
              ? attributedWorkspacePayload("Insight Strip", "Risk Watch", f.label, f.count, { filter_mode: "current_window", dq_bucket: "unassigned" })
              : null;
      if (payload) li.setAttribute("data-drilldown-payload", JSON.stringify(payload));
      li.innerHTML = `<span>${f.label || f.key || "Risk"}</span><span class="badge ${riskBadgeClass(f.severity)}">${fmtInt.format(num(f.count))}</span>`;
      holder.appendChild(li);
    });
  };

  const appendFilterQS = (url) => {
    if (!url) return "#";
    const params = baseQuery();
    params.delete("page");
    params.delete("page_size");
    params.delete("sort");
    params.delete("dir");
    params.delete("q");
    const q = params.toString();
    if (!q) return url;
    return url.includes("?") ? `${url}&${q}` : `${url}?${q}`;
  };

  const rowSignalChip = (row) => {
    const chips = [];
    const targetMargin = opt(row.target_margin_pct);
    const statusKey = marginStatusKey(row.status_key);
    if (["red", "orange"].includes(statusKey)) {
      chips.push('<span class="chip-danger">Below min</span>');
    } else if (statusKey === "yellow" || (opt(row.margin_pct) !== null && targetMargin !== null && num(row.margin_pct) < targetMargin)) {
      chips.push('<span class="chip-warn">Below target</span>');
    }
    if (opt(row.top_5_customer_share) !== null && num(row.top_5_customer_share) > 0.65) chips.push('<span class="chip-warn">High concentration</span>');
    return chips.join(" ");
  };

  const rankChangeChip = (value) => {
    const change = opt(value);
    if (change == null || change === 0) return '<span class="sr-badge-neutral">Flat</span>';
    if (change > 0) return `<span class="sr-badge-neutral sr-badge-up">+${fmtInt.format(change)}</span>`;
    return `<span class="sr-badge-neutral sr-badge-down">${fmtInt.format(change)}</span>`;
  };

  const focusedRepSummary = () => {
    const labels = (Array.isArray(state.focusedRepLabels) ? state.focusedRepLabels : []).filter(Boolean);
    if (!labels.length) return "";
    if (labels.length === 1) return labels[0];
    if (labels.length === 2) return labels.join(", ");
    return `${labels.slice(0, 2).join(", ")} +${labels.length - 2}`;
  };

  const buildTableRowHtml = (row, rowIndex) => {
    const repId = row.rep_id || row.key || row.rep_name || "";
    const repName = repDisplayName(row, READABLE_REP_FALLBACK);
    const baseUrl = drilldownTemplate ? drilldownTemplate.replace("__ID__", encodeURIComponent(repId)) : "#";
    const href = appendFilterQS(baseUrl);
    const payload = salesrepPayload(row, "Detailed Table", "Sales Rep Table", "Revenue", row.revenue);
    const signals = rowSignalChip(row);
    const focused = state.focusedRepIds.includes(String(repId));
    const selected = selectedRepIds.has(String(repId));
    return `
      <tr class="sr-virtual-row${focused ? " is-rep-focus" : ""}${row.revenue_quartile === 4 ? " sr-row-q4" : row.revenue_quartile === 1 ? " sr-row-q1" : ""}${selected ? " sr-row-selected" : ""}" tabindex="0" data-row-index="${rowIndex}" data-rep-id="${escapeHtml(repId)}" data-href="${escapeHtml(href)}"${payload ? ` data-drilldown-payload="${escapeHtml(JSON.stringify(payload))}"` : ""}>
        <td class="col-select text-center" onclick="event.stopPropagation()">
          <input type="checkbox" class="form-check-input sr-rep-select-cb" data-rep-id="${escapeHtml(String(repId))}" ${selected ? "checked" : ""} aria-label="Select ${escapeHtml(repName)} for comparison">
        </td>
        <td class="sticky-col" title="${escapeHtml(repName)}">
          <div class="d-flex align-items-center justify-content-between gap-2">
            <span class="sr-link"${drillAttr(payload)}>${escapeHtml(repName)}</span>
            ${rankChangeChip(row.rank_change)}
          </div>
          <div class="sr-secondary-metric">${fmtInt.format(num(row.current_owned_customers))} current owned · ${fmtInt.format(num(row.inherited_customers))} inherited</div>
        </td>
        <td class="col-health text-center">
          ${row.health_label ? `<span class="badge" style="background:${escapeHtml(row.health_color || '#6c757d')};color:#fff;font-size:0.72rem;" title="Score: ${row.health_score}/100 | Momentum: ${(row.health_components||{}).momentum||0} | Margin: ${(row.health_components||{}).margin||0} | Retention: ${(row.health_components||{}).retention||0} | Concentration: ${(row.health_components||{}).concentration||0}">${escapeHtml(row.health_label)}</span>` : NA}
        </td>
        <td class="col-quartile text-center">
          ${row.quartile_label === "Top 25%" ? `<span title="${escapeHtml(row.quartile_label)}">★ ${escapeHtml(row.quartile_label)}</span>` : row.quartile_label === "Bottom 25%" ? `<span title="${escapeHtml(row.quartile_label)}">⚑ ${escapeHtml(row.quartile_label)}</span>` : `<span class="text-muted small">${escapeHtml(row.quartile_label || NA)}</span>`}
        </td>
        <td class="text-end col-revenue">
          <div>${money(row.revenue)}</div>
          <div class="sr-secondary-metric">${money(row.direct_revenue)} direct · ${money(row.transferred_in_revenue)} inherited</div>
        </td>
        <td class="text-end col-profit">${row.profit == null ? NA : money(row.profit)}</td>
        <td class="text-end col-margin_pct">${marginCellHtml(row)}</td>
        <td class="text-end col-weight_lb">${fmtInt.format(num(row.weight_lb))}</td>
        <td class="text-end col-active_customers">${fmtInt.format(num(row.active_customers))}</td>
        <td class="text-end col-current_owned_customers">${fmtInt.format(num(row.current_owned_customers))}</td>
        <td class="text-end col-inherited_customers">${fmtInt.format(num(row.inherited_customers))}</td>
        <td class="text-end col-transferred_in_revenue">${row.transferred_in_revenue == null ? NA : money(row.transferred_in_revenue)}</td>
        <td class="text-end col-transferred_out_revenue">${row.transferred_out_revenue == null ? NA : money(row.transferred_out_revenue)}</td>
        <td class="text-end col-yoy_revenue_pct">${pct(row.yoy_revenue_pct, false)}</td>
        <td class="text-end col-territory_count">${fmtInt.format(num(row.territory_count))}</td>
        <td class="col-replaced_reps" title="${escapeHtml(row.replaced_rep_names || "")}">${row.replaced_rep_count ? `${fmtInt.format(num(row.replaced_rep_count))} · ${escapeHtml(row.replaced_rep_names || "")}` : NA}</td>
        <td class="col-top_territory" title="${escapeHtml(row.top_territory_name || NA)}"><span class="sr-link"${drillAttr(territoryPayload(row.top_territory_name, "Detailed Table", "Top Territory", "Revenue", row.top_territory_revenue, { filter_mode: "current_window" }))}>${escapeHtml(row.top_territory_name || NA)}</span></td>
        <td class="col-top_customer" title="${escapeHtml(row.top_customer_name || NA)}"><span class="sr-link"${drillAttr(repWorkspacePayload(row, "Detailed Table", "Top Customer", "Revenue", row.top_customer_revenue, { filter_mode: "current_window" }))}>${escapeHtml(row.top_customer_name || NA)}</span></td>
        <td class="col-top_protein"><span class="sr-link"${drillAttr(proteinPayload(row.top_protein_family, "Detailed Table", "Top Protein", "Revenue", row.top_protein_revenue, { filter_mode: "current_window" }))}>${escapeHtml(row.top_protein_family || NA)}</span></td>
        <td class="col-flags">${signals || '<span class="text-muted small">--</span>'}</td>
        <td class="text-end"><a class="btn btn-sm btn-outline-primary" href="${href}" aria-label="Open drilldown for ${repName}">View</a></td>
      </tr>
    `;
  };

  const renderVirtualTableRows = ({ force = false } = {}) => {
    const tbody = virtualTable.tbody || document.getElementById("salesreps-table-body");
    const wrapper = virtualTable.wrapper || document.getElementById("srTableWrap");
    virtualTable.tbody = tbody;
    virtualTable.wrapper = wrapper;
    if (!tbody || !wrapper) return;

    const rows = Array.isArray(virtualTable.rows) ? virtualTable.rows : [];
    if (!rows.length) {
      virtualTable.lastRange = "";
      return;
    }

    const viewportHeight = Math.max(wrapper.clientHeight || 0, 320);
    const rowHeight = Math.max(virtualTable.rowHeight || 88, 64);
    const scrollTop = Math.max(wrapper.scrollTop || 0, 0);
    const startIndex = Math.max(0, Math.floor(scrollTop / rowHeight) - virtualTable.overscan);
    const visibleCount = Math.ceil(viewportHeight / rowHeight) + (virtualTable.overscan * 2);
    const endIndex = Math.min(rows.length, startIndex + visibleCount);
    const rangeKey = `${startIndex}:${endIndex}:${rows.length}`;
    if (!force && virtualTable.lastRange === rangeKey) return;
    virtualTable.lastRange = rangeKey;

    const topSpacer = startIndex * rowHeight;
    const bottomSpacer = Math.max((rows.length - endIndex) * rowHeight, 0);
    const colSpan = Math.max(document.querySelectorAll("#srTable thead th").length, 1);
    const parts = [];
    if (topSpacer > 0) {
      parts.push(`<tr class="sr-virtual-spacer" aria-hidden="true"><td colspan="${colSpan}" style="height:${topSpacer}px"></td></tr>`);
    }
    rows.slice(startIndex, endIndex).forEach((row, idx) => {
      parts.push(buildTableRowHtml(row, startIndex + idx));
    });
    if (bottomSpacer > 0) {
      parts.push(`<tr class="sr-virtual-spacer" aria-hidden="true"><td colspan="${colSpan}" style="height:${bottomSpacer}px"></td></tr>`);
    }
    tbody.innerHTML = parts.join("");

    const measuredRow = tbody.querySelector("tr.sr-virtual-row");
    if (measuredRow && !force) {
      const measuredHeight = Math.round(measuredRow.getBoundingClientRect().height);
      if (measuredHeight >= 64 && Math.abs(measuredHeight - virtualTable.rowHeight) > 6) {
        virtualTable.rowHeight = measuredHeight;
        renderVirtualTableRows({ force: true });
        return;
      }
    }

    applyColumnVisibility();
    if (window.universalDrilldown && typeof window.universalDrilldown.enhanceAll === "function") {
      window.universalDrilldown.enhanceAll();
    }
  };

  const scheduleVirtualTableRender = ({ force = false } = {}) => {
    if (force) {
      virtualTable.scheduled = false;
      renderVirtualTableRows({ force: true });
      return;
    }
    if (virtualTable.scheduled) return;
    virtualTable.scheduled = true;
    window.requestAnimationFrame(() => {
      virtualTable.scheduled = false;
      renderVirtualTableRows();
    });
  };

  const scrollFocusedRepIntoView = () => {
    if (!state.scrollToFocusedRep || !state.focusedRepIds.length || !virtualTable.wrapper || !virtualTable.rows.length) return;
    const targetIndex = virtualTable.rows.findIndex((row) => state.focusedRepIds.includes(String(row.rep_id || row.key || row.rep_name || "")));
    state.scrollToFocusedRep = false;
    if (targetIndex < 0) return;
    document.getElementById("srTableSection")?.scrollIntoView({ behavior: "smooth", block: "start" });
    const nextScrollTop = Math.max((targetIndex * virtualTable.rowHeight) - (virtualTable.wrapper.clientHeight * 0.14), 0);
    virtualTable.wrapper.scrollTop = nextScrollTop;
    renderVirtualTableRows({ force: true });
  };

  const renderTable = (table = {}) => {
    const tbody = document.getElementById("salesreps-table-body");
    if (!tbody) return;
    virtualTable.tbody = tbody;
    virtualTable.wrapper = document.getElementById("srTableWrap");
    tbody.innerHTML = "";

    const rows = Array.isArray(table.rows) ? table.rows : [];
    virtualTable.rows = rows;
    virtualTable.lastRange = "";
    if (!rows.length) {
      tbody.innerHTML = '<tr><td colspan="18" class="text-center text-muted">No data for current filters.</td></tr>';
      if (virtualTable.wrapper) virtualTable.wrapper.scrollTop = 0;
    } else {
      if (virtualTable.wrapper) virtualTable.wrapper.scrollTop = 0;
      renderVirtualTableRows({ force: true });
    }

    const page = num(table.page || state.page, 1);
    const pageSize = num(table.page_size || state.pageSize, state.pageSize);
    const total = num(table.total_rows || table.total || table.all_rows, 0);
    const totalPages = Math.max(1, num(table.total_pages || Math.ceil(total / Math.max(pageSize, 1)), 1));

    const start = total > 0 ? (page - 1) * pageSize + 1 : 0;
    const end = total > 0 ? Math.min(page * pageSize, total) : 0;

    const focusedText = focusedRepSummary();
    let summaryText = total > 0 ? `Showing ${start}-${end} of ${fmtInt.format(total)} reps` : "No rows";
    if (total > 0 && rows.length) {
      const totalRev = rows.reduce((s, r) => s + num(r.revenue), 0);
      const marginRows = rows.filter(r => r.margin_pct != null);
      const wMarginNum = marginRows.reduce((s, r) => s + num(r.revenue) * num(r.margin_pct), 0);
      const wMarginRev = marginRows.reduce((s, r) => s + num(r.revenue), 0);
      const weightedMargin = wMarginRev > 0 ? wMarginNum / wMarginRev : null;
      // ── Phase 4C: add avg health score (revenue-weighted) ──
      const healthRows = rows.filter(r => r.health_score != null);
      const avgHealth = healthRows.length
        ? Math.round(healthRows.reduce((s, r) => s + num(r.health_score), 0) / healthRows.length)
        : null;
      summaryText += ` · Total Rev: ${fmtMoney0.format(totalRev)}`;
      if (weightedMargin !== null) summaryText += ` · Avg Margin: ${fmtPct.format(weightedMargin)}%`;
      if (avgHealth !== null)      summaryText += ` · Avg Health: ${avgHealth}/100`;
    }
    setText("salesrepsPagerSummary", focusedText ? `Sales rep focus: ${focusedText} · ${summaryText}` : summaryText);
    setText("salesrepsPagerIndicator", `Page ${page} of ${totalPages}`);

    const prev = document.getElementById("salesrepsPrev");
    const next = document.getElementById("salesrepsNext");
    if (prev) prev.disabled = page <= 1;
    if (next) next.disabled = page >= totalPages;
    scrollFocusedRepIntoView();
  };

  const applyColumnVisibility = () => {
    document.querySelectorAll("[data-col-toggle]").forEach((cb) => {
      const key = cb.dataset.colToggle;
      if (!key) return;
      const visible = columnVisibility[key] !== false;
      cb.checked = visible;
      document.querySelectorAll(`.col-${key}`).forEach((el) => {
        el.classList.toggle("sr-hidden-col", !visible);
      });
    });
  };

  // ── Phase 4D: column presets ──
  const COLUMN_PRESETS = {
    "Full View":    null,   // all visible
    "Executive":    ["revenue", "profit", "margin_pct", "active_customers", "health", "quartile"],
    "Risk View":    ["health", "quartile", "revenue", "yoy_revenue_pct", "margin_pct", "flags"],
    "Scott's View": ["revenue", "active_customers", "yoy_revenue_pct", "margin_pct", "top_customer"],
  };
  const ALL_COLUMN_KEYS = Object.keys(DEFAULT_COLUMN_VISIBILITY);

  const applyColumnPreset = (presetName) => {
    const cols = COLUMN_PRESETS[presetName];
    const labelEl = document.getElementById("srColumnPresetLabel");
    if (labelEl) labelEl.textContent = `${presetName} ▾`;
    sessionStorage.setItem("trsm_col_preset", presetName);
    ALL_COLUMN_KEYS.forEach((key) => {
      columnVisibility[key] = cols === null ? (DEFAULT_COLUMN_VISIBILITY[key] ?? true) : cols.includes(key);
    });
    applyColumnVisibility();
    renderVirtualTableRows({ force: true });
  };

  document.querySelectorAll("[data-col-preset]").forEach((btn) => {
    btn.addEventListener("click", () => applyColumnPreset(btn.dataset.colPreset));
  });

  const syncSortClasses = () => {
    document.querySelectorAll("#srTable .sortable").forEach((th) => {
      th.classList.remove("asc", "desc");
      if (th.dataset.sortKey === state.sortBy) th.classList.add(state.sortDir);
    });
  };

  const renderBundle = (rawPayload = {}) => {
    const payload = window.normalizeBundlePayload ? window.normalizeBundlePayload(rawPayload) : rawPayload;
    lastPayload = payload;
    clearDeferredChartWork();
    updateColumnLabels(payload.meta || {});
    renderExecutive(payload);
    renderSummaryNarrative(payload);
    renderWarnings(payload.warnings, payload);
    renderInsights(payload);
    renderOwnershipHighlights(payload);
    const analysis = payload.analysis || {};
    renderPortfolioSection(payload);
    renderTopCustomers(analysis.top_customers || [], payload.lost_accounts ?? []);
    renderCustomerMovers(analysis);
    renderLostAccountsPanel(payload.lost_accounts ?? []);
    renderProteinTable(analysis.proteins || []);
    // 6D: Protein section subtitle
    (() => {
      const proteins = analysis.proteins || [];
      if (proteins.length) {
        setText("srSectionProteinSubtitle", `${proteins.length} protein famil${proteins.length !== 1 ? "ies" : "y"} in scope · margin benchmarks applied where available`);
      }
    })();
    renderDataQuality(analysis.data_quality || []);
    renderTable(payload.table || {});
    renderRiskFlags(payload.risk_flags || []);
    if (window.universalDrilldown && typeof window.universalDrilldown.enhanceAll === "function") {
      window.universalDrilldown.enhanceAll();
    }
    applyColumnVisibility();
    syncSortClasses();
    const tableRows = payload.table?.rows || [];
    const topRepRows = payload.charts?.top_reps || tableRows;
    scheduleDeferredChartWork(() => {
      const proteinSignature = signatureForRows(analysis.proteins || [], ["protein_family", "revenue", "profit", "margin_pct", "minimum_margin_pct", "target_margin_pct", "status_key"]);
      memoizedRender("protein-chart", proteinSignature, () => renderProteinChart(analysis.proteins || []));
      renderTopReps(topRepRows);
      // 6D: Comparison section subtitle
      (() => {
        const n = topRepRows.length;
        if (n) setText("srSectionComparisonSubtitle", `${n} rep${n !== 1 ? "s" : ""} · select checkboxes in the table below to compare side-by-side`);
      })();
      renderPareto(topRepRows);
      renderAspLeaders(payload.charts?.asp_leaders || tableRows);
    }, { delay: 0 });
    scheduleDeferredChartWork(() => {
      renderMonthlyCompare(payload.charts?.monthly_compare || payload.trend?.monthly_compare || {});
      renderTransfers(payload.charts?.transfers || []);
      renderTrend(payload.charts?.trend || payload.trend || {});
      renderConcentration(payload.charts?.concentration || []);
      const efficiencySignature = signatureForRows(payload.charts?.scatter || tableRows, ["rep_id", "customers", "revenue", "profit", "margin_pct"]);
      memoizedRender("efficiency-chart", efficiencySignature, () => renderEfficiency(payload.charts?.scatter || tableRows));
      renderProfitRevenue(payload.charts?.profit_vs_revenue || []);
    }, { delay: 60, idle: true });
    persistSnapshot(payload);
  };

  const fetchBundle = async (options = {}) => {
    reqId += 1;
    const thisReq = reqId;
    if (currentAbort) currentAbort.abort();
    currentAbort = new AbortController();
    if (!lastPayload && !options?.snapshot?.payload) {
      setScorecardLoading(true);
      setSummaryNarrativeLoading(true);
      setAllChartsLoading(true);
    }

    updateExportLinks();
    const qs = buildQueryString();
    const url = qs ? `${bundleUrl}?${qs}` : bundleUrl;
    const snapshot = options.snapshot || null;

    try {
      const headers = pageCache ? pageCache.prepareHeaders(url, { Accept: "application/json" }) : { Accept: "application/json" };
      const res = await authFetch(url, {
        method: "GET",
        credentials: "same-origin",
        signal: currentAbort.signal,
        headers,
      });
      if (pageCache) pageCache.rememberResponse(url, res);
      if (res.status === 304) {
        if (!lastPayload && snapshot?.payload) renderBundle(snapshot.payload);
        return;
      }
      const payload = await res.json();
      if (thisReq !== reqId) return;
      if (!res.ok) throw new Error(payload?.error?.message || `HTTP ${res.status}`);
      renderBundle(payload);
    } catch (err) {
      if (err?.name === "AbortError") return;
      console.error("salesreps bundle failed", err);
      if (!lastPayload) {
        ["trendChart", "topRepsChart", "monthlyCompareChart", "transferChart", "srProteinChart", "concentrationChart", "effChart", "profitRevenueChart", "revenueShareChart", "aspChart"].forEach((id) => toggleEmpty(id, true));
        setScorecardLoading(false);
        setSummaryNarrativeLoading(false);
      }
      setText("srWhatChanged", lastPayload ? "What changed: refresh failed. Displaying the last successful snapshot." : "What changed: failed to load bundle.");
    } finally {
      if (thisReq !== reqId) return;
      const detail = { qs: state.qs };
      if (currentApplyId) {
        detail.applyId = currentApplyId;
        currentApplyId = "";
      }
      try {
        if (typeof window.dispatchGlobalFiltersApplied === "function") {
          window.dispatchGlobalFiltersApplied(detail);
        } else {
          window.dispatchEvent(new CustomEvent("globalFilters:applied", { detail }));
        }
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

  const applyFilters = (qs, filters = null, { scroll = false } = {}) => {
    state.qs = String(qs || "").replace(/^\?/, "");
    syncStateFromQS(state.qs);
    syncFocusedReps(filters || currentFilterState(), { scroll });
    state.page = 1;
    syncControlsFromState();
    fetchBundle();
  };

  const debounce = (fn, delay = 250) => {
    let timer = null;
    return (...args) => {
      if (timer) clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  };

  const rerenderLocalState = () => {
    if (!lastPayload) return;
    updateExportLinks();
    renderBundle(lastPayload);
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

  const showActionPlaceholder = (message) => {
    const holder = document.getElementById("srWarnings");
    if (!holder) return;
    holder.innerHTML = `
      <div class="alert alert-info border-0 mb-0" role="status">
        <div class="fw-semibold mb-1">Action Placeholder</div>
        <div>${escapeHtml(message)}</div>
      </div>
    `;
  };

  const wireVirtualTable = () => {
    const wrapper = document.getElementById("srTableWrap");
    if (!wrapper || wrapper.dataset.virtualized === "1") return;
    wrapper.dataset.virtualized = "1";
    virtualTable.wrapper = wrapper;
    wrapper.addEventListener("scroll", () => scheduleVirtualTableRender(), { passive: true });
    window.addEventListener("resize", () => scheduleVirtualTableRender(), { passive: true });
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

  const wireMiniSorts = () => {
    document.querySelectorAll("[data-top-customers-sort]").forEach((th) => {
      const applySort = () => {
        const key = th.dataset.topCustomersSort || "revenue";
        if (state.topCustomersSortBy === key) state.topCustomersSortDir = state.topCustomersSortDir === "asc" ? "desc" : "asc";
        else {
          state.topCustomersSortBy = key;
          state.topCustomersSortDir = key === "customer_name" || key === "account_owner_name" || key === "territory_name" ? "asc" : "desc";
        }
        rerenderLocalState();
      };
      th.addEventListener("click", applySort);
      th.addEventListener("keydown", (evt) => {
        if (evt.key === "Enter" || evt.key === " ") {
          evt.preventDefault();
          applySort();
        }
      });
    });

    document.querySelectorAll("[data-protein-sort]").forEach((th) => {
      const applySort = () => {
        const key = th.dataset.proteinSort || "revenue";
        if (state.proteinSortBy === key) state.proteinSortDir = state.proteinSortDir === "asc" ? "desc" : "asc";
        else {
          state.proteinSortBy = key;
          state.proteinSortDir = key === "protein_family" ? "asc" : "desc";
        }
        rerenderLocalState();
      };
      th.addEventListener("click", applySort);
      th.addEventListener("keydown", (evt) => {
        if (evt.key === "Enter" || evt.key === " ") {
          evt.preventDefault();
          applySort();
        }
      });
    });
  };

  const wireControls = () => {
    const metricToggle = document.getElementById("srMetricToggle");
    const trendMetric = document.getElementById("srTrendMetric");
    const trendGrain = document.getElementById("srTrendGrain");
    const trendView = document.getElementById("srTrendView");
    const topN = document.getElementById("srTopN");
    const trendReset = document.getElementById("srTrendReset");
    const pageSize = document.getElementById("srPageSize");
    const search = document.getElementById("srSearchInput");
    const attributionMode = document.getElementById("srAttributionMode");
    const includeFormer = document.getElementById("srIncludeFormerReps");
    const transferOnly = document.getElementById("srTransferOnly");

    if (metricToggle) {
      metricToggle.value = state.metric;
      metricToggle.addEventListener("change", () => {
        state.metric = metricToggle.value;
        state.page = 1;
        rerenderLocalState();
      });
    }

    if (trendMetric) {
      trendMetric.value = state.trendMetric;
      trendMetric.addEventListener("change", () => {
        state.trendMetric = trendMetric.value || "revenue";
        rerenderLocalState();
      });
    }

    if (trendGrain) {
      trendGrain.value = state.trendGrain;
      trendGrain.addEventListener("change", () => {
        state.trendGrain = trendGrain.value || "monthly";
        state.trendSelectedReps = [];
        state.trendFocusMode = false;
        // ── Phase 2: sync grain pills with hidden select ──
        document.querySelectorAll("#srGrainPills .sr-grain-pill").forEach((btn) => {
          btn.classList.toggle("active", btn.dataset.grain === state.trendGrain);
        });
        rerenderLocalState();
      });
    }

    // ── Phase 2: grain pill buttons sync to hidden srTrendGrain select ──
    document.querySelectorAll("#srGrainPills .sr-grain-pill").forEach((btn) => {
      btn.addEventListener("click", () => {
        const grain = btn.dataset.grain;
        if (!grain) return;
        if (trendGrain) {
          trendGrain.value = grain;
          trendGrain.dispatchEvent(new Event("change", { bubbles: true }));
        }
      });
    });

    if (trendView) {
      trendView.value = state.trendView;
      trendView.addEventListener("change", () => {
        state.trendView = trendView.value || "absolute";
        rerenderLocalState();
      });
    }

    if (topN) {
      topN.value = String(state.topN);
      topN.addEventListener("change", () => {
        state.topN = num(topN.value, 10);
        fetchBundle();
      });
    }

    if (trendReset) {
      trendReset.addEventListener("click", () => {
        state.trendSelectedReps = [];
        state.trendFocusMode = false;
        renderTrend(lastPayload?.charts?.trend || lastPayload?.trend || {});
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
      }, 300);
      search.addEventListener("input", debounced);
    }

    if (attributionMode) {
      attributionMode.value = state.attributionMode;
      attributionMode.addEventListener("change", () => {
        state.attributionMode = attributionMode.value || "current_owner";
        if (state.attributionMode !== "historical_rep") {
          state.rosterMode = "current_only";
          if (includeFormer) includeFormer.checked = false;
        }
        state.page = 1;
        fetchBundle();
      });
    }

    if (includeFormer) {
      includeFormer.checked = state.rosterMode === "include_former";
      includeFormer.addEventListener("change", () => {
        state.rosterMode = includeFormer.checked ? "include_former" : "current_only";
        state.page = 1;
        fetchBundle();
      });
    }

    if (transferOnly) {
      transferOnly.checked = !!state.transferOnly;
      transferOnly.addEventListener("change", () => {
        state.transferOnly = !!transferOnly.checked;
        state.page = 1;
        fetchBundle();
      });
    }

    document.querySelectorAll("[data-col-toggle]").forEach((cb) => {
      const key = cb.dataset.colToggle;
      if (!key) return;
      cb.checked = columnVisibility[key] !== false;
      cb.addEventListener("change", () => {
        columnVisibility = { ...columnVisibility, [key]: !!cb.checked };
        persistColumnVisibility(columnVisibility);
        applyColumnVisibility();
        scheduleVirtualTableRender({ force: true });
        // ── Phase 4D: manual toggle resets preset label to "Custom" ──
        const labelEl = document.getElementById("srColumnPresetLabel");
        if (labelEl) labelEl.textContent = "Custom ▾";
        sessionStorage.removeItem("trsm_col_preset");
      });
    });

    if (actionCrm) {
      actionCrm.addEventListener("click", () => {
        showActionPlaceholder("Sync to CRM is a placeholder. Wire the destination integration and audit trail before enabling it.");
      });
    }

    if (actionSlack) {
      actionSlack.addEventListener("click", () => {
        showActionPlaceholder("Notify Rep via Slack is a placeholder. Connect the workspace and delivery rules before enabling it.");
      });
    }
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
    syncStateFromQS(qs);
    syncFocusedReps(detail?.filters || currentFilterState());
    syncControlsFromState();
    applyColumnVisibility();
    wireTooltips();
    const snapshot = restoreSnapshot(qs, { restoreScroll: true });
    if (snapshot?.fresh) {
      updateExportLinks();
      return;
    }
    fetchBundle({ snapshot });
  };

  wireSorting();
  wirePager();
  wireVirtualTable();
  wireRowClicks();
  wireMiniSorts();
  wireControls();
  wireCompare();
  initCustomerViewToggle();

  window.addEventListener("globalFilters:apply", (evt) => {
    currentApplyId = String(evt?.detail?.applyId || "");
    applyFilters(evt?.detail?.qs || "", evt?.detail?.filters || null, { scroll: focusedRepIdsFromFilters(evt?.detail?.filters || {}).length > 0 });
  });
  window.addEventListener("globalFilters:ready", (evt) => bootstrap(evt?.detail?.qs || ""));
  window.addEventListener("pagehide", () => {
    persistSnapshot();
  });
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState === "hidden") persistSnapshot();
  });

  bootstrap();
})();
