(() => {
  const root = document.getElementById("products-main");
  if (!root) return;
  if (document?.body?.dataset) {
    document.body.dataset.filtersHandler = "ajax";
  }
  const authFetch = window.authFetch || fetch;

  const bundleUrl = root.dataset.bundleUrl || "/api/products/bundle";
  const drilldownTemplate = root.dataset.drilldownTemplate || "";
  const currency = root.dataset.currency || "USD";
  const isV2 = root.dataset.productsV2 === "1";
  const isV3 = root.dataset.productsV3 === "1";
  const isV4 = root.dataset.productsV4 === "1";
  const WORKSPACE_STORAGE_KEY = isV4 ? "amw:products:v4:workspace" : "";
  const COLUMN_STORAGE_KEY = isV4
    ? "amw:products:v4:columns"
    : isV3
      ? "amw:products:v3:columns"
      : "amw:products:v2:columns";
  const V2_COLUMN_DEFS = [
    { key: "sku", label: "SKU", locked: true, visible: true, exportable: true },
    { key: "product", label: "Product", locked: true, visible: true, exportable: true },
    { key: "segment", label: "Segment", visible: true, exportable: true },
    { key: "revenue", label: "Revenue", visible: true, exportable: true },
    { key: "revenue_share", label: "Rev Share", visible: true, exportable: true },
    { key: "orders", label: "Orders", visible: true, exportable: true },
    { key: "qty", label: "Quantity", visible: true, exportable: true },
    { key: "weight", label: "Weight", visible: false, exportable: true },
    { key: "current_unit_price", label: "Current Price", visible: true, exportable: true },
    { key: "target_price", label: "Target Price", visible: true, exportable: true },
    { key: "uplift_pct", label: "Uplift %", visible: true, exportable: true },
    { key: "cost", label: "Cost", visible: false, exportable: true },
    { key: "profit", label: "Profit", visible: true, exportable: true },
    { key: "profit_share", label: "Profit Share", visible: false, exportable: true },
    { key: "contribution_margin_lb", label: "CM / lb", visible: false, exportable: true },
    { key: "margin_pct", label: "Margin %", visible: true, exportable: true },
    { key: "price_variance_vs_median", label: "vs Median", visible: false, exportable: true },
    { key: "volatility_score", label: "Volatility", visible: false, exportable: true },
    { key: "margin_risk", label: "Margin Risk", visible: true, exportable: true },
    { key: "recommendation", label: "Recommendation", visible: true, exportable: true },
    { key: "first_sold", label: "First Sold", visible: false, exportable: true },
    { key: "last_sold", label: "Last Sold", visible: false, exportable: true },
    { key: "quick_rec", label: "Quick Rec", visible: false, exportable: true },
  ];
  const V3_COLUMN_DEFS = [
    { key: "sku", label: "SKU", locked: true, visible: true, exportable: true },
    { key: "product", label: "Product", locked: true, visible: true, exportable: true },
    { key: "segment", label: "Segment", visible: true, exportable: true },
    { key: "revenue", label: "Revenue", visible: true, exportable: true },
    { key: "revenue_current", label: "Revenue current", visible: true, exportable: true },
    { key: "revenue_prior", label: "Revenue prior", visible: true, exportable: true },
    { key: "revenue_delta", label: "Delta Revenue $", visible: true, exportable: true },
    { key: "revenue_delta_pct", label: "Delta Revenue %", visible: true, exportable: true },
    { key: "revenue_share", label: "Rev Share", visible: true, exportable: true },
    { key: "orders", label: "Orders", visible: true, exportable: true },
    { key: "orders_current", label: "Orders current", visible: false, exportable: true },
    { key: "orders_prior", label: "Orders prior", visible: false, exportable: true },
    { key: "qty", label: "Quantity", visible: true, exportable: true },
    { key: "weight", label: "Weight", visible: false, exportable: true },
    { key: "current_unit_price", label: "Current Price", visible: true, exportable: true },
    { key: "target_price", label: "Target Price", visible: false, exportable: true },
    { key: "uplift_pct", label: "Uplift %", visible: false, exportable: true },
    { key: "cost", label: "Cost", visible: false, exportable: true },
    { key: "profit", label: "Profit", visible: true, exportable: true },
    { key: "profit_current", label: "Profit current", visible: false, exportable: true },
    { key: "profit_prior", label: "Profit prior", visible: false, exportable: true },
    { key: "profit_delta", label: "Delta Profit $", visible: true, exportable: true },
    { key: "profit_share", label: "Profit Share", visible: false, exportable: true },
    { key: "contribution_margin_lb", label: "CM / lb", visible: false, exportable: true },
    { key: "margin_pct", label: "Margin %", visible: true, exportable: true },
    { key: "margin_pct_prior", label: "Margin % Prior", visible: false, exportable: true },
    { key: "margin_delta_pp", label: "Delta Margin pp", visible: true, exportable: true },
    { key: "price_variance_vs_median", label: "vs Median", visible: false, exportable: true },
    { key: "volatility_score", label: "Volatility", visible: false, exportable: true },
    { key: "margin_risk", label: "Margin Risk", visible: true, exportable: true },
    { key: "recommendation", label: "Recommendation", visible: true, exportable: true },
    { key: "first_sold", label: "First Sold", visible: false, exportable: true },
    { key: "last_sold", label: "Last Sold", visible: false, exportable: true },
    { key: "quick_rec", label: "Quick Rec", visible: false, exportable: true },
  ];
  const V4_COLUMN_DEFS = [
    { key: "sku", label: "SKU", locked: true, visible: true, exportable: true },
    { key: "product", label: "Product", locked: true, visible: true, exportable: true },
    { key: "segment", label: "Segment", visible: true, exportable: true },
    { key: "supplier", label: "Supplier", visible: false, exportable: true },
    { key: "customer_count", label: "Customer Ct", visible: true, exportable: true },
    { key: "supplier_count", label: "Supplier Ct", visible: false, exportable: true },
    { key: "region_breadth", label: "Region Ct", visible: false, exportable: true },
    { key: "top_customer_share", label: "Top Cust Share", visible: true, exportable: true },
    { key: "customer_hhi", label: "Cust HHI", visible: false, exportable: true },
    { key: "revenue", label: "Revenue", visible: true, exportable: true },
    { key: "revenue_current", label: "Revenue current", visible: true, exportable: true },
    { key: "revenue_prior", label: "Revenue prior", visible: false, exportable: true },
    { key: "revenue_delta", label: "Delta Revenue $", visible: true, exportable: true },
    { key: "revenue_delta_pct", label: "Delta Revenue %", visible: true, exportable: true },
    { key: "revenue_share", label: "Rev Share", visible: true, exportable: true },
    { key: "orders", label: "Orders", visible: true, exportable: true },
    { key: "orders_current", label: "Orders current", visible: false, exportable: true },
    { key: "orders_prior", label: "Orders prior", visible: false, exportable: true },
    { key: "velocity_per_month", label: "Velocity/mo", visible: true, exportable: true },
    { key: "qty", label: "Quantity", visible: true, exportable: true },
    { key: "weight", label: "Weight", visible: false, exportable: true },
    { key: "current_unit_price", label: "Current Price", visible: true, exportable: true },
    { key: "asp_lb", label: "ASP/lb", visible: true, exportable: true },
    { key: "cost_lb", label: "Cost/lb", visible: true, exportable: true },
    { key: "target_price", label: "Target Price", visible: false, exportable: true },
    { key: "uplift_pct", label: "Uplift %", visible: false, exportable: true },
    { key: "cost", label: "Cost", visible: false, exportable: true },
    { key: "profit", label: "Profit", visible: true, exportable: true },
    { key: "profit_current", label: "Profit current", visible: false, exportable: true },
    { key: "profit_prior", label: "Profit prior", visible: false, exportable: true },
    { key: "profit_delta", label: "Delta Profit $", visible: true, exportable: true },
    { key: "profit_share", label: "Profit Share", visible: false, exportable: true },
    { key: "contribution_margin_lb", label: "Contribution/lb", visible: true, exportable: true },
    { key: "margin_pct", label: "Margin %", visible: true, exportable: true },
    { key: "margin_pct_prior", label: "Margin % Prior", visible: false, exportable: true },
    { key: "margin_delta_pp", label: "Delta Margin pp", visible: true, exportable: true },
    { key: "price_variance_vs_median", label: "vs Median", visible: false, exportable: true },
    { key: "volatility_score", label: "Price CV %", visible: false, exportable: true },
    { key: "margin_risk", label: "Margin Risk", visible: true, exportable: true },
    { key: "recommendation", label: "Recommendation", visible: true, exportable: true },
    { key: "first_sold", label: "First Sold", visible: false, exportable: true },
    { key: "last_sold", label: "Last Sold", visible: false, exportable: true },
    { key: "quick_rec", label: "Quick Rec", visible: false, exportable: true },
  ];
  const ACTIVE_COLUMN_DEFS = isV4 ? V4_COLUMN_DEFS : (isV3 ? V3_COLUMN_DEFS : V2_COLUMN_DEFS);
  const V2_TOOLTIP_TEXT = {
    heroTitle: "This page keeps existing filters, RBAC scope, and exports intact while surfacing pricing, velocity, and margin actions in one place.",
    velocityPulse: "Velocity pulse summarizes weekly movement from the current window. Average weekly and weekly revenue are total filtered activity divided by elapsed weeks.",
    momentum: "Revenue comparison uses the active filtered window against its prior comparable window. Partial months are treated explicitly and not compared against a full prior month.",
    topProduct: "Top product is the highest-revenue SKU in the current window. Use it as a share anchor, not a recommendation on its own.",
    momDelta: "Comparison delta uses the current filtered window and its prior comparable window, with month-to-date safeguards when the latest month is incomplete.",
    projectedNextMonth: "Projected next month is pace-normalized when the current month is incomplete; otherwise it uses recent completed periods.",
    totalRevenue: "Total shipped revenue in the active filter window, after RBAC scope is applied.",
    totalQuantity: "Total shipped quantity in the active filter window. Quantity follows the same unit basis already used by the page.",
    totalWeight: "Total shipped weight in pounds for the filtered window when weight is available.",
    activeProducts: "Distinct SKUs with activity in the current filter window.",
    activeCustomers: "Distinct customers purchasing the visible product set in the current filter window.",
    avgMargin: "Average gross margin percentage where cost is available. Missing-cost rows are excluded from the percentage.",
    avgUnitPrice: "Average realized selling price per pound or per unit, based on the same pricing basis used across the page.",
    medianUnitPrice: "Median realized unit price. This is a sturdier pricing baseline than the average when outliers exist.",
    revenuePerProduct: "Total revenue divided by active SKUs. Use it to compare assortment productivity across filter slices.",
    revenuePerCustomer: "Total revenue divided by active customers in the current filter window.",
    aiSignals: "AI signals are lightweight heuristics from margin coverage, recent momentum, and pricing dispersion. They do not override raw metrics.",
    trajectory: "Performance trajectory plots realized revenue and demand trend. Granularity switches between month and week based on window length.",
    priceVelocity: "Price vs velocity compares realized price against average monthly order velocity. Bubble size reflects revenue share, so large low-margin points stand out quickly.",
    recommendations: "Recommendations rank SKUs using revenue share, recent momentum, and pricing dispersion. They are guidance, not automatic changes.",
    performanceBubble: "Performance bubble compares current price, target price, revenue share, and velocity. Uplift % is (target price - current price) / current price.",
    priceDistribution: "Unit price distribution shows where most transactions land. P10, P50, and P90 define the practical guardrail band.",
    topMovers: "Top movers compares the current filtered window against the prior comparable window and highlights the biggest absolute change.",
    segmentSummary: "Segment summary groups SKUs using the existing revenue and order heuristics already used elsewhere in Product Intelligence.",
    segmentMovers: "Segment movers shows which SKUs are driving the biggest revenue swings inside each current segment.",
    topProducts: "Top products re-ranks the current dataset by the selected metric without changing the underlying filters.",
    pareto: "Pareto shows how quickly revenue accumulates across the top SKUs. The cumulative line helps identify concentration risk.",
    healthMatrix: "Portfolio matrix classifies SKUs by percentile bands for velocity and profitability, then assigns Protect, Fix Margin, Grow, and Rationalize quadrants.",
    table: "The products table is still backed by the existing server-side table payload. Quick filters and sorting stay on the server so exports match the visible slice.",
  };

  const fmtMoney0 = new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 0 });
  const fmtMoney2 = new Intl.NumberFormat(undefined, { style: "currency", currency, maximumFractionDigits: 2 });
  const fmtInt = new Intl.NumberFormat(undefined, { maximumFractionDigits: 0 });
  const fmtPct1 = new Intl.NumberFormat(undefined, { maximumFractionDigits: 1 });
  const EM_DASH = "\u2014";
  const MIDDLE_DOT = "\u00b7";
  const ARROW = "\u2192";
  const ELLIPSIS = "\u2026";
  const DELTA = "\u0394";
  const WORKSPACE_SECTION_KEYS = ["overview", "strategy", "demand", "pricing", "execution", "assortment", "table"];
  const WATCHLIST_PRESETS = {
    clear: { quickFilters: [], emphasis: "revenue" },
    recover_margin: { quickFilters: ["recover_margin"], emphasis: "profit", section: "pricing" },
    protect_core: { quickFilters: ["protect_core"], emphasis: "revenue", section: "strategy" },
    promote: { quickFilters: ["promote_candidate"], emphasis: "profit", section: "execution" },
    rationalize: { quickFilters: ["rationalize_candidate"], emphasis: "profit", section: "assortment", mode: "analyst" },
  };

  const waitForFiltersReady = async () => {
    const fallbackState = () => {
      try {
        return (window.getGlobalFilterState && window.getGlobalFilterState()) || {};
      } catch (err) {
        return {};
      }
    };
    if (window.filtersReady && typeof window.filtersReady.then === "function") {
      try {
        const timeout = new Promise((resolve) => setTimeout(() => resolve(fallbackState()), 1500));
        return await Promise.race([window.filtersReady, timeout]);
      } catch (err) {
        console.warn("[products] filtersReady rejected", err);
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

  const state = {
    qs: "",
    page: 1,
    pageSize: 25,
    sortBy: "revenue",
    sortDir: "desc",
    search: "",
    segments: [],
    quickFilters: [],
    visibleColumns: [],
    bubbleTopN: 250,
    bubbleColorBy: "uplift_pct",
    bubbleYMetric: "velocity",
    showForecast: false,
    workspaceMode: isV4 ? "executive" : "analyst",
    workspaceDensity: "comfortable",
    workspaceEmphasis: "revenue",
    visibleSections: [...WORKSPACE_SECTION_KEYS],
  };

  let currentAbort = null;
  let currentReqId = 0;
  let lastPayload = null;
  let hasBootstrapped = false;
  let activeProductIntel = null;
  let productIntelOffcanvas = null;
  const charts = {};

  const safeNum = (v) => (Number.isFinite(+v) ? +v : 0);
  const nullish = (v, fallback = EM_DASH) => (v === null || v === undefined ? fallback : v);
  const displayName = (row) => {
    if (!row || typeof row !== "object") return EM_DASH;
    if (row.display_name) return row.display_name;
    const sku = row.sku || row.product_id || row.key;
    const name = row.product_name || row.name || row.label;
    if (sku && name) return `${sku}  ${name}`;
    return sku || name || EM_DASH;
  };

  const getSku = (row) => {
    if (!row || typeof row !== "object") return "";
    return row.sku || row.product_id || row.key || "";
  };

  const escapeHtml = (value) =>
    String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");

  const readStoredColumns = () => {
    if (!isV2 || !window.localStorage) return [];
    try {
      const raw = window.localStorage.getItem(COLUMN_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : [];
      return Array.isArray(parsed) ? parsed.filter(Boolean) : [];
    } catch (err) {
      return [];
    }
  };

  const writeStoredColumns = (columns) => {
    if (!isV2 || !window.localStorage) return;
    try {
      window.localStorage.setItem(COLUMN_STORAGE_KEY, JSON.stringify(columns || []));
    } catch (err) {
      /* ignore storage failures */
    }
  };

  const readWorkspaceState = () => {
    if (!isV4 || !window.localStorage || !WORKSPACE_STORAGE_KEY) return null;
    try {
      const raw = window.localStorage.getItem(WORKSPACE_STORAGE_KEY);
      const parsed = raw ? JSON.parse(raw) : null;
      if (!parsed || typeof parsed !== "object") return null;
      return {
        mode: parsed.mode === "analyst" ? "analyst" : "executive",
        density: parsed.density === "compact" ? "compact" : "comfortable",
        emphasis: ["revenue", "profit", "weight"].includes(parsed.emphasis) ? parsed.emphasis : "revenue",
        visibleSections: Array.isArray(parsed.visibleSections)
          ? parsed.visibleSections.filter((key) => WORKSPACE_SECTION_KEYS.includes(key))
          : [...WORKSPACE_SECTION_KEYS],
      };
    } catch (err) {
      return null;
    }
  };

  const writeWorkspaceState = () => {
    if (!isV4 || !window.localStorage || !WORKSPACE_STORAGE_KEY) return;
    try {
      window.localStorage.setItem(
        WORKSPACE_STORAGE_KEY,
        JSON.stringify({
          mode: state.workspaceMode,
          density: state.workspaceDensity,
          emphasis: state.workspaceEmphasis,
          visibleSections: state.visibleSections,
        })
      );
    } catch (err) {
      /* ignore storage failures */
    }
  };

  const defaultVisibleColumns = () => ACTIVE_COLUMN_DEFS.filter((col) => col.visible).map((col) => col.key);
  const COLUMN_GROUPS = {
    performance: ["sku", "product", "segment", "revenue", "revenue_current", "revenue_delta", "revenue_delta_pct", "orders", "qty", "weight", "revenue_share"],
    unit_econ: ["sku", "product", "segment", "profit", "margin_pct", "contribution_margin_lb", "asp_lb", "cost_lb", "target_price", "uplift_pct"],
    pricing: ["sku", "product", "segment", "current_unit_price", "asp_lb", "target_price", "uplift_pct", "price_variance_vs_median", "volatility_score"],
    risk: ["sku", "product", "segment", "margin_risk", "recommendation", "revenue", "profit", "margin_pct", "top_customer_share", "customer_hhi"],
    breadth: ["sku", "product", "segment", "supplier", "customer_count", "supplier_count", "region_breadth", "top_customer_share", "customer_hhi", "revenue"],
  };

  if (isV2) {
    const stored = readStoredColumns();
    state.visibleColumns = stored.length ? stored : defaultVisibleColumns();
  }
  if (isV4) {
    const workspaceState = readWorkspaceState();
    if (workspaceState) {
      state.workspaceMode = workspaceState.mode;
      state.workspaceDensity = workspaceState.density;
      state.workspaceEmphasis = workspaceState.emphasis;
      state.visibleSections = workspaceState.visibleSections.length ? workspaceState.visibleSections : [...WORKSPACE_SECTION_KEYS];
    }
  }

  const setText = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.textContent = value ?? EM_DASH;
  };

  const setHtml = (id, value) => {
    const el = document.getElementById(id);
    if (el) el.innerHTML = value ?? "";
  };

  const scrollToSection = (sectionKey) => {
    if (!sectionKey) return;
    const selectorMap = {
      overview: "#products-overview",
      strategy: "#products-strategy-brief, #products-health",
      demand: "#products-trajectory",
      pricing: "#products-pricing",
      execution: "#products-risk-opportunity",
      assortment: "#products-segments",
      table: "#products-table",
    };
    const target = document.querySelector(selectorMap[sectionKey] || "");
    if (!target || typeof target.scrollIntoView !== "function") return;
    target.scrollIntoView({ behavior: "smooth", block: "start" });
  };

  const hasOwn = (obj, key) => Object.prototype.hasOwnProperty.call(obj || {}, key);

  const makeInteractiveCard = (node, onClick) => {
    if (!node || typeof onClick !== "function") return;
    node.classList.add("is-clickable-card");
    node.setAttribute("role", "button");
    if (!node.hasAttribute("tabindex")) node.tabIndex = 0;
    if (node.dataset.clickBound === "1") return;
    node.dataset.clickBound = "1";
    node.addEventListener("click", (evt) => {
      if (evt.target.closest("a,button,input,select,label,summary")) return;
      onClick(evt);
    });
    node.addEventListener("keydown", (evt) => {
      if (evt.key !== "Enter" && evt.key !== " ") return;
      evt.preventDefault();
      onClick(evt);
    });
  };

  const applyDetailView = (options = {}) => {
    if (hasOwn(options, "quickFilters")) state.quickFilters = [...(options.quickFilters || [])];
    if (hasOwn(options, "segments")) state.segments = [...(options.segments || [])];
    if (hasOwn(options, "search")) state.search = options.search || "";
    if (options.sortBy) state.sortBy = options.sortBy;
    if (options.sortDir) state.sortDir = options.sortDir;
    if (options.mode) state.workspaceMode = options.mode;
    if (options.emphasis && options.emphasis !== state.workspaceEmphasis) {
      applyEmphasisPreset(options.emphasis);
    } else {
      applyWorkspaceSettings();
    }
    const searchEl = document.getElementById("tableSearch");
    if (searchEl && hasOwn(options, "search")) searchEl.value = state.search || "";
    const segmentSelect = document.getElementById("segmentFilter");
    if (segmentSelect && hasOwn(options, "segments")) {
      Array.from(segmentSelect.options || []).forEach((option) => {
        option.selected = state.segments.includes(option.value);
      });
    }
    state.page = 1;
    syncWatchlistButtons();
    syncQuickFilterButtons();
    fetchBundle();
    if (options.section) {
      setTimeout(() => scrollToSection(options.section), 120);
    }
  };

  const applySignalAction = (action = {}) => {
    if (!action || typeof action !== "object") return;
    applyDetailView({
      quickFilters: action.quickFilters || action.quick_filters,
      segments: action.segments,
      search: action.search,
      sortBy: action.sortBy || action.sort_by,
      sortDir: action.sortDir || action.sort_dir,
      mode: action.mode,
      emphasis: action.emphasis,
      section: action.section,
    });
  };

  const syncWorkspaceControls = () => {
    if (!isV4) return;
    document.getElementById("workspaceModeExecutive")?.classList.toggle("active", state.workspaceMode === "executive");
    document.getElementById("workspaceModeAnalyst")?.classList.toggle("active", state.workspaceMode === "analyst");
    document.getElementById("workspaceDensityComfortable")?.classList.toggle("active", state.workspaceDensity === "comfortable");
    document.getElementById("workspaceDensityCompact")?.classList.toggle("active", state.workspaceDensity === "compact");
    const emphasis = document.getElementById("workspaceEmphasis");
    if (emphasis && emphasis.value !== state.workspaceEmphasis) emphasis.value = state.workspaceEmphasis;
    document.querySelectorAll("[data-section-toggle]").forEach((input) => {
      const key = input.getAttribute("data-section-toggle");
      if (!key) return;
      input.checked = state.visibleSections.includes(key);
    });
  };

  const applyWorkspaceSettings = () => {
    if (!isV4) return;
    root.dataset.workspaceMode = state.workspaceMode;
    root.dataset.workspaceDensity = state.workspaceDensity;
    root.dataset.workspaceEmphasis = state.workspaceEmphasis;
    const allowed = new Set(state.visibleSections || WORKSPACE_SECTION_KEYS);
    document.querySelectorAll("[data-workspace-section]").forEach((section) => {
      const key = section.getAttribute("data-workspace-section");
      if (!key) return;
      section.classList.toggle("is-hidden-by-workspace", !allowed.has(key));
    });
    syncWorkspaceControls();
    writeWorkspaceState();
  };

  const removeSkeleton = (targetId) => {
    document.querySelectorAll(`.skeleton[data-for="${targetId}"]`).forEach((el) => el.remove());
  };

  const destroyChart = (key) => {
    if (charts[key]?.destroy) {
      charts[key].destroy();
    }
    charts[key] = null;
  };

  const buildQS = () => {
    const params = new URLSearchParams(state.qs || "");
    params.set("page", String(state.page));
    params.set("page_size", String(state.pageSize));
    params.set("sort_by", state.sortBy);
    params.set("sort_dir", state.sortDir);
    if (state.search) params.set("search", state.search);
    else params.delete("search");
    if (state.segments?.length) params.set("segments", state.segments.join(","));
    else params.delete("segments");
    if (state.quickFilters?.length) params.set("quick_filters", state.quickFilters.join(","));
    else params.delete("quick_filters");
    params.set("bubble_top_n", String(state.bubbleTopN));
    params.set("bubble_color", state.bubbleColorBy);
    params.set("bubble_y", state.bubbleYMetric);
    if (!isV3 && state.showForecast) params.set("forecast", "1");
    else params.delete("forecast");
    return params.toString();
  };

  const syncStateFromQS = (qs) => {
    const params = new URLSearchParams(qs || "");
    const page = Number(params.get("page") || state.page);
    const pageSize = Number(params.get("page_size") || params.get("per_page") || state.pageSize);
    state.page = Number.isFinite(page) && page > 0 ? page : 1;
    state.pageSize = Number.isFinite(pageSize) && pageSize > 0 ? pageSize : state.pageSize;
    state.sortBy = params.get("sort_by") || state.sortBy;
    state.sortDir = params.get("sort_dir") || state.sortDir;
    state.search = params.get("search") || "";
    state.segments = (params.get("segments") || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
    state.quickFilters = (params.get("quick_filters") || "")
      .split(",")
      .map((item) => item.trim())
      .filter(Boolean);
  };

  const currentExportColumns = () => {
    if (!isV2) return [];
    return ACTIVE_COLUMN_DEFS.filter((col) => col.exportable && (col.locked || state.visibleColumns.includes(col.key))).map((col) => col.key);
  };

  const buildExportQS = () => {
    const params = new URLSearchParams(state.qs || resolveInitialQS() || "");
    params.set("sort_by", state.sortBy);
    params.set("sort_dir", state.sortDir);
    if (state.search) params.set("search", state.search);
    else params.delete("search");
    if (state.segments?.length) params.set("segments", state.segments.join(","));
    else params.delete("segments");
    if (state.quickFilters?.length) params.set("quick_filters", state.quickFilters.join(","));
    else params.delete("quick_filters");
    const columns = currentExportColumns();
    if (columns.length) params.set("columns", columns.join(","));
    else params.delete("columns");
    return params.toString();
  };

  const syncExportLinks = () => {
    if (!isV2) return;
    const qs = buildExportQS();
    const targets = [
      ["productsHeroExportExcel", root.dataset.exportXlsx],
      ["productsHeroExportCsv", root.dataset.exportCsv],
      ["productsTableExportExcel", root.dataset.exportXlsx],
      ["productsTableExportCsv", root.dataset.exportCsv],
      ["priceExportCsv", root.dataset.exportCsv],
      ["topProductsExportCsv", root.dataset.exportCsv],
      ["paretoExportCsv", root.dataset.exportCsv],
      ["topMoversCsv", root.dataset.exportMoversCsv || root.dataset.exportCsv],
      ["segmentMixExportCsv", root.dataset.exportSegmentMixCsv || root.dataset.exportCsv],
      ["pricingActionsExport", root.dataset.exportExecutionCsv || root.dataset.exportCsv],
      ["execPricingExport", root.dataset.exportExecutionCsv || root.dataset.exportCsv],
      ["execCostExport", root.dataset.exportExecutionCsv || root.dataset.exportCsv],
      ["execPromoteExport", root.dataset.exportExecutionCsv || root.dataset.exportCsv],
    ];
    targets.forEach(([id, baseUrl]) => {
      const el = document.getElementById(id);
      if (!el || !baseUrl) return;
      const extra = new URLSearchParams();
      if (id === "execPricingExport" || id === "pricingActionsExport") extra.set("list", "pricing_fixes");
      if (id === "execCostExport") extra.set("list", "cost_fixes");
      if (id === "execPromoteExport") extra.set("list", "promote_candidates");
      const extraQs = extra.toString();
      const merged = [extraQs, qs].filter(Boolean).join("&");
      el.href = merged ? `${baseUrl}?${merged}` : baseUrl;
    });
  };

  const appendFiltersToUrl = (url) => {
    if (!url) return "#";
    const qs = state.qs;
    if (!qs) return url;
    const suffix = qs.startsWith("?") ? qs.slice(1) : qs;
    return url.includes("?") ? `${url}&${suffix}` : `${url}?${suffix}`;
  };

  const currentFilterState = () => {
    try {
      const globalState = window.getGlobalFilterState ? window.getGlobalFilterState() : {};
      if (globalState?.filters && typeof globalState.filters === "object") {
        return globalState.filters;
      }
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

  const productDrilldownPayload = (row, section, widget, metric, value, extra = {}) => {
    const sku = getSku(row);
    if (!sku) return null;
    return {
      source_page: "products",
      source_section: section,
      source_widget: widget,
      requested_target: "product",
      clicked_entity_type: "product",
      clicked_entity_id: sku,
      clicked_entity_label: displayName(row),
      clicked_metric: metric,
      clicked_metric_value: value,
      active_filter_state: currentFilterState(),
      comparison_context: lastPayload?.comparison || null,
      workspace_state: {
        mode: state.workspaceMode,
        density: state.workspaceDensity,
        emphasis: state.workspaceEmphasis,
        quick_filters: [...(state.quickFilters || [])],
        segments: [...(state.segments || [])],
        search: state.search || "",
      },
      extra,
    };
  };

  const openProductDrilldown = (row, section, widget, metric, value, el = root, extra = {}) => {
    const payload = productDrilldownPayload(row, section, widget, metric, value, extra);
    if (!payload) return;
    if (openUniversal(payload, el)) return;
    if (!drilldownTemplate) return;
    const url = appendFiltersToUrl(drilldownTemplate.replace("__PID__", encodeURIComponent(payload.clicked_entity_id)));
    window.location.href = url;
  };

  const mergeDefined = (target, source) => {
    Object.entries(source || {}).forEach(([key, value]) => {
      if (value === null || value === undefined || value === "") return;
      target[key] = value;
    });
    return target;
  };

  const resolveProductContextRow = (seed = {}) => {
    const sku = getSku(seed);
    const merged = {};
    const sources = [
      seed,
      ...(lastPayload?.table?.rows || []),
      ...(lastPayload?.sku_metrics || []),
      ...(lastPayload?.price_vs_velocity || []),
      ...((lastPayload?.performance_bubble || {}).points || []),
      ...((lastPayload?.charts || {}).top_products || []),
      ...((lastPayload?.charts || {}).movers || []),
      ...((((lastPayload?.charts || {}).segments || {}).movers) || []),
      ...((lastPayload?.risk_opportunity || {}).margin_risk_top || []),
      ...((lastPayload?.risk_opportunity || {}).high_velocity_low_margin || []),
      ...((lastPayload?.risk_opportunity || {}).high_margin_low_velocity || []),
      ...((lastPayload?.recommendations) || []),
      ...((lastPayload?.pricing_guardrails || {}).rows || []),
      ...((lastPayload?.execution_lists || {}).pricing_fixes || []),
      ...((lastPayload?.execution_lists || {}).cost_fixes || []),
      ...((lastPayload?.execution_lists || {}).promote_candidates || []),
    ];
    sources.forEach((row) => {
      if (!row || getSku(row) !== sku) return;
      mergeDefined(merged, row);
    });
    return merged;
  };

  const percentText = (value, suffix = "%") =>
    value == null || Number.isNaN(Number(value)) ? EM_DASH : `${Number(value) > 0 ? "+" : ""}${fmtPct1.format(value)}${suffix}`;

  const countLabel = (count, singular, plural) => `${fmtInt.format(count || 0)} ${count === 1 ? singular : plural}`;

  const formatInsightValue = (label, value) => {
    const key = String(label || "").toLowerCase();
    if (value == null || Number.isNaN(Number(value))) return value == null ? EM_DASH : String(value);
    if (key.includes("margin") || key.includes("uplift")) return `${fmtPct1.format(value)}%`;
    if (key.includes("price") || key.includes("revenue") || key.includes("profit") || key.includes("cost") || key.includes("contribution")) {
      return fmtMoney0.format(value);
    }
    if (key.includes("share")) return `${fmtPct1.format(value)}%`;
    return fmtInt.format(value);
  };

  const deriveSuggestedAction = (row = {}) => {
    const actionText = String(row?.action || row?.recommendation || row?.quick_rec || "").toLowerCase();
    const marginPct = Number(row?.margin_pct);
    const topCustomerShare = Number(row?.top_customer_share);
    const velocity = Number(row?.velocity_per_month ?? row?.orders_per_month ?? 0);
    if (row?.unit_cost == null && row?.cost == null) {
      return {
        label: "Review cost coverage",
        note: "Cost is missing, so pricing and margin guidance are less trustworthy until coverage is repaired.",
        view: { quickFilters: ["missing_cost"], section: "execution", emphasis: "profit", mode: "analyst" },
      };
    }
    if (!Number.isNaN(marginPct) && marginPct < 27) {
      return {
        label: "Recover margin",
        note: "The SKU is below the 27% target margin inside the visible scope and should sit in the pricing queue.",
        view: { quickFilters: ["recover_margin"], section: "pricing", emphasis: "profit", mode: "analyst" },
      };
    }
    if (actionText.includes("promote") || (!Number.isNaN(marginPct) && marginPct >= 27 && velocity > 0 && velocity < 3)) {
      return {
        label: "Promote or expand distribution",
        note: "Margin looks healthy relative to demand, so commercial teams should test feature support or broader placement.",
        view: { quickFilters: ["promote_candidate"], section: "execution", emphasis: "profit", mode: "analyst" },
      };
    }
    if (actionText.includes("rationalize") || String(row?.segment || "").toLowerCase() === "long tail") {
      return {
        label: "Review assortment role",
        note: "Long-tail, low-priority SKUs should be checked for pack simplification, minimum viable coverage, or rationalization.",
        view: { quickFilters: ["rationalize_candidate"], section: "assortment", emphasis: "profit", mode: "analyst" },
      };
    }
    if (!Number.isNaN(topCustomerShare) && topCustomerShare >= 50) {
      return {
        label: "Review customer dependency",
        note: "A narrow customer base increases operational and commercial risk if one account softens.",
        view: { quickFilters: ["high_customer_dependency"], section: "table", emphasis: "revenue", mode: "analyst" },
      };
    }
    return {
      label: "Review in table workspace",
      note: "Use the table workspace to inspect customer breadth, price quality, and the full recommendation context.",
      view: { search: getSku(row), section: "table", mode: "analyst" },
    };
  };

  const buildProductWhyLines = (row = {}, section = "", widget = "", metric = "", value = null) => {
    const lines = [];
    if (widget) {
      const metricText = metric ? `${metric} ${MIDDLE_DOT} ${formatInsightValue(metric, value)}` : "portfolio interaction";
      lines.push(`Selected from ${widget} under ${section || "Product Intelligence"} using ${metricText}.`);
    }
    if (row?.revenue_delta_pct != null && !Number.isNaN(Number(row.revenue_delta_pct))) {
      const delta = Number(row.revenue_delta_pct);
      if (delta <= -8) lines.push(`Revenue is softening versus the prior comparable window (${percentText(delta)}).`);
      else if (delta >= 8) lines.push(`Revenue is accelerating versus the prior comparable window (${percentText(delta)}).`);
    }
    if (row?.margin_pct != null && !Number.isNaN(Number(row.margin_pct)) && Number(row.margin_pct) < 27) {
      lines.push(`Margin is below the 27% target, so price or cost recovery should be reviewed before broad promotion.`);
    }
    if (row?.uplift_pct != null && !Number.isNaN(Number(row.uplift_pct)) && Number(row.uplift_pct) > 0) {
      lines.push(`Target pricing implies roughly ${fmtPct1.format(row.uplift_pct)}% upside from the current realized price.`);
    }
    if (row?.top_customer_share != null && !Number.isNaN(Number(row.top_customer_share)) && Number(row.top_customer_share) >= 50) {
      lines.push(`Customer concentration is elevated: the top account contributes ${fmtPct1.format(row.top_customer_share)}% of SKU revenue.`);
    }
    if (row?.customer_count != null && Number(row.customer_count) > 0 && Number(row.customer_count) <= 2) {
      lines.push(`Customer breadth is narrow at ${countLabel(Number(row.customer_count), "customer", "customers")}.`);
    }
    if (row?.weight != null && !Number.isNaN(Number(row.weight)) && Number(row.weight) > 0) {
      lines.push(`Visible shipped weight is ${fmtInt.format(row.weight)} lb, which matters for meat production and purchasing planning.`);
    }
    if (row?.velocity_per_month != null && !Number.isNaN(Number(row.velocity_per_month)) && Number(row.velocity_per_month) > 0) {
      lines.push(`Repeat demand is running at about ${fmtPct1.format(row.velocity_per_month)} orders per month in the current visible scope.`);
    }
    return lines.length ? lines : ["Use the full drilldown to inspect demand, pricing, customer mix, and planning relevance in more detail."];
  };

  const renderActiveFilterSummary = () => {
    const host = document.getElementById("activeFilterSummary");
    if (!host) return;
    const filters = currentFilterState();
    const parts = [];
    Object.entries(filters || {}).forEach(([key, rawValue]) => {
      if (rawValue == null || rawValue === "") return;
      const values = Array.isArray(rawValue) ? rawValue.filter(Boolean) : [rawValue].filter(Boolean);
      if (!values.length) return;
      const label = key.replace(/_/g, " ").replace(/\b\w/g, (m) => m.toUpperCase());
      const named = typeof window.getFilterLabels === "function" ? window.getFilterLabels(key, values) : values;
      const preview = named.slice(0, 2).join(", ");
      const remainder = named.length > 2 ? ` +${named.length - 2} more` : "";
      parts.push(`${label}: ${preview}${remainder}`);
    });
    if (state.segments?.length) {
      parts.push(`Segments: ${state.segments.slice(0, 2).join(", ")}${state.segments.length > 2 ? ` +${state.segments.length - 2} more` : ""}`);
    }
    if (state.quickFilters?.length) {
      parts.push(`Watchlists: ${state.quickFilters.join(", ")}`);
    }
    if (state.search) {
      parts.push(`Search: ${state.search}`);
    }
    host.textContent = parts.length
      ? `Every KPI, chart, watchlist, and recommendation below uses this scope: ${parts.join(" | ")}`
      : "Every KPI, chart, watchlist, and recommendation below uses the current RBAC scope and visible filter window.";
  };

  const renderSectionBriefs = (payload = {}) => {
    const comparison = payload?.comparison || {};
    const concentration = payload?.concentration || {};
    const risk = payload?.risk_opportunity || {};
    const posture = payload?.portfolio_posture || {};
    const focusActions = Array.isArray(payload?.focus_actions) ? payload.focus_actions : [];
    const pricingRows = Array.isArray(payload?.pricing_guardrails?.rows) ? payload.pricing_guardrails.rows.length : 0;
    const movers = Array.isArray(payload?.charts?.movers) ? payload.charts.movers : [];
    const watchlistText = state.quickFilters?.length ? `Active watchlists: ${state.quickFilters.join(", ")}.` : "No extra watchlist filters are applied.";
    setText(
      "strategyLayerContext",
      `${posture?.headline || "Portfolio posture will appear here."} ${concentration?.top10_share != null ? `Top 10 SKUs represent ${fmtPct1.format(concentration.top10_share)}% of filtered revenue.` : ""}`.trim()
    );
    setText(
      "demandLayerContext",
      `${comparison?.note || "Demand comparisons follow the current filtered window."} ${movers.length ? `Top movers are ranked inside this exact scope.` : ""}`.trim()
    );
    setText(
      "pricingLayerContext",
      `${fmtInt.format(risk?.below_target_count ?? 0)} SKUs are below target margin across ${fmtMoney0.format(risk?.below_target_revenue ?? 0)} of visible revenue; ${fmtInt.format(pricingRows)} pricing actions are ready for review.`
    );
    setText(
      "executionLayerContext",
      focusActions[0]?.detail || "The execution layer ranks the next best pricing, commercial, and planning moves for the current scope."
    );
    setText(
      "assortmentLayerContext",
      `${concentration?.top10_share != null ? `Top 10 SKUs represent ${fmtPct1.format(concentration.top10_share)}% of visible revenue.` : "Assortment concentration is being calculated."} ${concentration?.skus_to_80 ? `${fmtInt.format(concentration.skus_to_80)} SKUs reach 80% of revenue.` : ""}`.trim()
    );
    setText(
      "tableLayerContext",
      `${comparison?.comparison_label || "Current vs prior comparable columns"} stay aligned with the current scope. ${watchlistText}`
    );
  };

  const renderProductIntel = (row, section, widget, metric, value) => {
    const panel = document.getElementById("productIntelPanel");
    if (!panel) return false;
    const contextRow = resolveProductContextRow(row);
    const sku = getSku(contextRow);
    if (!sku) return false;
    const suggestedAction = deriveSuggestedAction(contextRow);
    activeProductIntel = { row: contextRow, suggestedAction, section, widget, metric, value };

    setText("productIntelPanelLabel", displayName(contextRow));
    setText("productIntelSource", `${section || "Product Intelligence"} ${MIDDLE_DOT} ${widget || "Selected interaction"}`);
    setText("productIntelHeadline", `${displayName(contextRow)} under the current visible scope`);
    setText(
      "productIntelSubhead",
      `${(lastPayload?.comparison || {}).comparison_label || "Current vs prior comparable logic"} ${MIDDLE_DOT} ${contextRow?.segment || "Unclassified segment"}`
    );
    setText("productIntelContextNote", (lastPayload?.comparison || {}).note || "This panel inherits the current filter scope and comparable-period logic.");

    const stats = [
      ["Revenue", contextRow?.revenue != null ? fmtMoney0.format(contextRow.revenue) : EM_DASH],
      [String((lastPayload?.comparison || {}).current_short_label || "Current"), contextRow?.revenue_current != null ? fmtMoney0.format(contextRow.revenue_current) : EM_DASH],
      [String((lastPayload?.comparison || {}).prior_short_label || "Prior"), contextRow?.revenue_prior != null ? fmtMoney0.format(contextRow.revenue_prior) : EM_DASH],
      ["Margin %", contextRow?.margin_pct != null ? `${fmtPct1.format(contextRow.margin_pct)}%` : EM_DASH],
      ["Current price", contextRow?.current_unit_price != null ? fmtMoney2.format(contextRow.current_unit_price) : (contextRow?.unit_price != null ? fmtMoney2.format(contextRow.unit_price) : EM_DASH)],
      ["Target uplift", contextRow?.uplift_pct != null ? `${fmtPct1.format(contextRow.uplift_pct)}%` : EM_DASH],
      ["Velocity / mo", contextRow?.velocity_per_month != null ? fmtPct1.format(contextRow.velocity_per_month) : (contextRow?.orders_per_month != null ? fmtPct1.format(contextRow.orders_per_month) : EM_DASH)],
      ["Customers", contextRow?.customer_count != null ? fmtInt.format(contextRow.customer_count) : EM_DASH],
      ["Top cust share", contextRow?.top_customer_share != null ? `${fmtPct1.format(contextRow.top_customer_share)}%` : EM_DASH],
      ["Weight", contextRow?.weight != null ? `${fmtInt.format(contextRow.weight)} lb` : EM_DASH],
    ];
    setHtml(
      "productIntelStats",
      stats
        .map(
          ([label, statValue]) => `
            <div class="product-intel-stat">
              <div class="product-intel-stat-label">${escapeHtml(label)}</div>
              <div class="product-intel-stat-value">${escapeHtml(statValue)}</div>
            </div>
          `
        )
        .join("")
    );

    const whyLines = buildProductWhyLines(contextRow, section, widget, metric, value);
    setHtml("productIntelWhy", `<ul class="product-intel-list mb-0">${whyLines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul>`);
    setText("productIntelAction", `${suggestedAction.label}. ${suggestedAction.note}`);

    const drilldownHref = drilldownTemplate
      ? appendFiltersToUrl(drilldownTemplate.replace("__PID__", encodeURIComponent(sku)))
      : (contextRow?.intel_url ? appendFiltersToUrl(contextRow.intel_url) : "#");
    const drilldownBtn = document.getElementById("productIntelOpenDrilldown");
    if (drilldownBtn) {
      drilldownBtn.href = drilldownHref;
      drilldownBtn.classList.toggle("disabled", drilldownHref === "#");
      drilldownBtn.setAttribute("aria-disabled", drilldownHref === "#" ? "true" : "false");
    }
    const focusBtn = document.getElementById("productIntelFocusTable");
    if (focusBtn) focusBtn.disabled = !sku;
    const applyBtn = document.getElementById("productIntelApplyAction");
    if (applyBtn) applyBtn.disabled = !suggestedAction?.view;

    if (typeof bootstrap !== "undefined" && bootstrap?.Offcanvas && panel) {
      productIntelOffcanvas = productIntelOffcanvas || bootstrap.Offcanvas.getOrCreateInstance(panel);
      productIntelOffcanvas.show();
      return true;
    }
    panel.classList.add("show");
    panel.style.visibility = "visible";
    return true;
  };

  const tooltipInstanceKey = "__productsTooltipBound";
  const hydrateTooltips = (scope = document) => {
    if (typeof bootstrap === "undefined" || !bootstrap.Tooltip) return;
    scope.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => {
      if (el[tooltipInstanceKey]) return;
      el[tooltipInstanceKey] = true;
      new bootstrap.Tooltip(el);
    });
  };

  const appendInfoButton = (target, text) => {
    if (!target || !text || target.querySelector?.(".info-dot")) return;
    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "btn btn-link btn-sm p-0 border-0 info-dot";
    btn.setAttribute("data-bs-toggle", "tooltip");
    btn.setAttribute("data-bs-placement", "top");
    btn.setAttribute("title", text);
    btn.setAttribute("aria-label", "What this means");
    btn.innerHTML = '<i class="bi bi-info-circle"></i>';
    target.appendChild(document.createTextNode(" "));
    target.appendChild(btn);
  };

  const explainMetricValue = (valueId, text) => {
    const valueEl = document.getElementById(valueId);
    if (!valueEl || !valueEl.previousElementSibling) return;
    appendInfoButton(valueEl.previousElementSibling, text);
  };

  const initV2Help = () => {
    if (!isV2) return;
    appendInfoButton(root.querySelector(".products-hero h2"), V2_TOOLTIP_TEXT.heroTitle);
    [
      ["velAvgWeekly", V2_TOOLTIP_TEXT.velocityPulse],
      ["velW13", V2_TOOLTIP_TEXT.velocityPulse],
      ["velWeeklyRevenue", V2_TOOLTIP_TEXT.velocityPulse],
      ["velRevPerProduct", V2_TOOLTIP_TEXT.velocityPulse],
      ["velActive", V2_TOOLTIP_TEXT.velocityPulse],
      ["velRoi", V2_TOOLTIP_TEXT.velocityPulse],
      ["insightMomentum", V2_TOOLTIP_TEXT.momentum],
      ["insightTopProduct", V2_TOOLTIP_TEXT.topProduct],
      ["momDelta", V2_TOOLTIP_TEXT.momDelta],
      ["predictiveRev", V2_TOOLTIP_TEXT.projectedNextMonth],
      ["kpiRevenue", V2_TOOLTIP_TEXT.totalRevenue],
      ["kpiQty", V2_TOOLTIP_TEXT.totalQuantity],
      ["kpiWeight", V2_TOOLTIP_TEXT.totalWeight],
      ["kpiUnique", V2_TOOLTIP_TEXT.activeProducts],
      ["kpiCustomers", V2_TOOLTIP_TEXT.activeCustomers],
      ["kpiMargin", V2_TOOLTIP_TEXT.avgMargin],
      ["kpiAvgPrice", V2_TOOLTIP_TEXT.avgUnitPrice],
      ["kpiMedianPrice", V2_TOOLTIP_TEXT.medianUnitPrice],
      ["kpiRevPerProduct", V2_TOOLTIP_TEXT.revenuePerProduct],
      ["kpiRevPerCustomer", V2_TOOLTIP_TEXT.revenuePerCustomer],
      ["aiMarginRisk", V2_TOOLTIP_TEXT.aiSignals],
      ["aiPricing", V2_TOOLTIP_TEXT.aiSignals],
    ].forEach(([id, text]) => explainMetricValue(id, text));
    [
      ["#products-trajectory .col-xl-8 .card-title", V2_TOOLTIP_TEXT.trajectory],
      ["#products-trajectory .col-xl-4 .card:first-child .card-title", V2_TOOLTIP_TEXT.priceVelocity],
      ["#products-risk-opportunity .col-xl-5 .card-title", V2_TOOLTIP_TEXT.recommendations],
      ["#products-pricing .col-12 .card-title", V2_TOOLTIP_TEXT.performanceBubble],
      ["#products-pricing .col-lg-6 .card-title", V2_TOOLTIP_TEXT.priceDistribution],
      ["#products-pricing .col-lg-6 + .col-lg-6 .card-title", V2_TOOLTIP_TEXT.topMovers],
      ["#products-health .card-title", V2_TOOLTIP_TEXT.healthMatrix],
      ["#products-segments .col-xl-4:nth-child(1) .card-title", V2_TOOLTIP_TEXT.segmentSummary],
      ["#products-segments .col-xl-4:nth-child(2) .card-title", V2_TOOLTIP_TEXT.segmentMovers],
      ["#products-segments + section .col-xl-6:first-child .card-title", V2_TOOLTIP_TEXT.topProducts],
      ["#products-segments + section .col-xl-6:last-child .card-title", V2_TOOLTIP_TEXT.pareto],
      ["#products-table .card-title", V2_TOOLTIP_TEXT.table],
    ].forEach(([selector, text]) => {
      if (!text) return;
      appendInfoButton(document.querySelector(selector), text);
    });
    hydrateTooltips(document);
  };

  // ---------- Render helpers ----------
  const renderHero = (kpis = {}, meta = {}, comparison = {}) => {
    const windowLbl = comparison?.current_window_label
      || (meta.window && (meta.window.start || meta.window.end)
        ? `${meta.window.start || "?"} ${ARROW} ${meta.window.end || "?"}`
        : "Live filters");
    setText("heroDateRange", windowLbl);
    setText("kpiUniqueHero", fmtInt.format(kpis.products ?? kpis.rows ?? 0));
    setText("kpiCustomersHero", fmtInt.format(kpis.customers ?? 0));
  };

  const renderComparisonContext = (comparison = {}, story = {}) => {
    const currentLabel = comparison?.current_short_label || "Current";
    const priorLabel = comparison?.prior_short_label || "Prior";
    ACTIVE_COLUMN_DEFS.forEach((col) => {
      if (col.key === "revenue_current") col.label = `Revenue ${currentLabel}`;
      if (col.key === "revenue_prior") col.label = `Revenue ${priorLabel}`;
      if (col.key === "orders_current") col.label = `Orders ${currentLabel}`;
      if (col.key === "orders_prior") col.label = `Orders ${priorLabel}`;
      if (col.key === "profit_current") col.label = `Profit ${currentLabel}`;
      if (col.key === "profit_prior") col.label = `Profit ${priorLabel}`;
    });
    setText("comparisonContextNote", comparison?.note || "Current window and prior comparable logic will appear here.");
    setText("portfolioStoryNote", story?.headline || "");
    setText("insightDeltaLabel", comparison?.current_short_label ? `${comparison.current_short_label} revenue` : "Revenue comparison");
    setText("comparisonDeltaLabel", comparison?.comparison_label || "Comparison delta");
    setText("moversContextNote", comparison?.comparison_label || "Current window vs prior comparable window.");
    setText("thRevenueCurrent", `Revenue (${comparison?.current_short_label || "Current"})`);
    setText("thRevenuePrior", `Revenue (${comparison?.prior_short_label || "Prior"})`);
    setText("thRevenueDeltaPct", `Δ Revenue %`);
    setText("thOrdersCurrent", `Orders (${comparison?.current_short_label || "Current"})`);
    setText("thOrdersPrior", `Orders (${comparison?.prior_short_label || "Prior"})`);
    setText("thProfitCurrent", `Profit (${comparison?.current_short_label || "Current"})`);
    setText("thProfitPrior", `Profit (${comparison?.prior_short_label || "Prior"})`);
    renderColumnChooser();
  };

  const renderPortfolioPosture = (posture = {}, focusActions = []) => {
    const headline = posture?.headline || "Review portfolio posture";
    const detail = posture?.detail || "Signals will summarize the dominant portfolio stance here.";
    setText("heroPostureSummary", headline);
    setText("portfolioPostureTitle", headline);
    setText("portfolioPostureDetail", detail);
    const actionSummary = (Array.isArray(focusActions) && focusActions[0]?.title) || "Review the top execution queue";
    setText("heroActionSummary", actionSummary);

    const badge = document.getElementById("heroPostureBadge");
    if (badge) {
      const quadrant = posture?.quadrant || "";
      badge.textContent = quadrant || "";
      badge.classList.toggle("d-none", !quadrant);
    }

    const stats = [];
    if (posture?.quadrant) stats.push(`${posture.quadrant}`);
    if (posture?.revenue_share != null) stats.push(`${fmtPct1.format(posture.revenue_share)}% of revenue`);
    setHtml(
      "portfolioPostureStats",
      stats.map((item) => `<span class="brief-pill">${escapeHtml(item)}</span>`).join("")
    );
  };

  const renderDecisionSignals = (signals = []) => {
    const host = document.getElementById("decisionSignalsBand");
    if (!host) return;
    const rows = Array.isArray(signals) ? signals.slice(0, 5) : [];
    if (!rows.length) {
      host.innerHTML = `
        <div class="decision-signal-card tone-neutral">
          <div class="decision-signal-label">Signals</div>
          <div class="decision-signal-value">Unavailable</div>
          <div class="decision-signal-note">Decision signals will appear when the bundle loads.</div>
        </div>
      `;
      return;
    }
    host.innerHTML = rows
      .map(
        (signal, idx) => `
          <div class="decision-signal-card tone-${escapeHtml(signal?.tone || "neutral")} ${signal?.action ? "has-action" : ""}" data-signal-idx="${idx}">
            <div class="decision-signal-label">${escapeHtml(signal?.label || "Signal")}</div>
            <div class="decision-signal-value">${escapeHtml(signal?.value || EM_DASH)}</div>
            <div class="decision-signal-note">${escapeHtml(signal?.note || "")}</div>
            ${signal?.action ? '<div class="decision-signal-note fw-semibold mt-2">Open detail view</div>' : ""}
          </div>
        `
      )
      .join("");
    host.querySelectorAll("[data-signal-idx]").forEach((node) => {
      const idx = Number(node.getAttribute("data-signal-idx"));
      const signal = rows[idx];
      if (!signal?.action) return;
      makeInteractiveCard(node, () => applySignalAction(signal.action));
    });
  };

  const renderFocusActions = (actions = []) => {
    const summaryHost = document.getElementById("focusActionsBand");
    if (summaryHost) {
      const lead = Array.isArray(actions) && actions[0] ? actions[0] : null;
      summaryHost.innerHTML = `
        <div class="products-brief-card">
          <div class="products-brief-label">Action focus</div>
          <div class="products-brief-value">${escapeHtml(lead?.title || "Keep monitoring execution queues")}</div>
          <div class="products-brief-note">${escapeHtml(lead?.detail || "The highest-priority action will surface here when the bundle loads.")}</div>
        </div>
      `;
    }

    const host = document.getElementById("focusActionList");
    if (!host) return;
    const rows = Array.isArray(actions) ? actions.slice(0, 4) : [];
    if (!rows.length) {
      host.innerHTML = '<span class="text-muted small">No prioritized actions for current filters.</span>';
      return;
    }
    host.innerHTML = `<div class="focus-action-grid">${rows
      .map(
        (action, idx) => `
          <div class="focus-action-card tone-${escapeHtml(action?.tone || "neutral")} ${action?.section ? "has-action" : ""}" data-focus-idx="${idx}">
            <div class="focus-action-owner">${escapeHtml(action?.owner || "Owner")}</div>
            <div class="focus-action-title">${escapeHtml(action?.title || "Review queue")}</div>
            <div class="focus-action-detail">${escapeHtml(action?.detail || "")}</div>
            ${(action?.confidence || action?.upside)
              ? `<div class="focus-action-meta">${escapeHtml(action?.confidence ? `Confidence ${action.confidence}` : "")}${action?.confidence && action?.upside ? ` ${MIDDLE_DOT} ` : ""}${action?.upside ? `Upside ${fmtMoney0.format(action.upside)}` : ""}</div>`
              : ""}
          </div>
        `
      )
      .join("")}</div>`;
    host.querySelectorAll("[data-focus-idx]").forEach((node) => {
      const idx = Number(node.getAttribute("data-focus-idx"));
      const action = rows[idx];
      if (!action?.section && !action?.quick_filters && !action?.quickFilters) return;
      makeInteractiveCard(node, () => applySignalAction(action));
    });
  };

  const renderStrategyBrief = (segments = {}, concentration = {}) => {
    const summaryRows = Array.isArray(segments?.summary) ? segments.summary.slice(0, 4) : [];
    const mixRows = Array.isArray(segments?.mix_shift) ? segments.mix_shift.slice(0, 4) : [];
    setHtml(
      "strategySegmentSummary",
      summaryRows.length
        ? summaryRows
            .map(
              (row) =>
                `<div class="d-flex justify-content-between py-1"><span>${escapeHtml(row?.segment || EM_DASH)}</span><strong>${fmtMoney0.format(row?.revenue || 0)}</strong></div>`
            )
            .join("")
        : '<span class="text-muted small">No segment contribution data.</span>'
    );
    setHtml(
      "strategyMixShift",
      mixRows.length
        ? mixRows
            .map((row) => {
              const delta = row?.share_delta_pp;
              const deltaLabel = delta == null || Number.isNaN(Number(delta))
                ? EM_DASH
                : `${delta > 0 ? "+" : ""}${fmtPct1.format(delta)} pp`;
              return `<div class="d-flex justify-content-between py-1"><span>${escapeHtml(row?.segment || EM_DASH)}</span><strong>${escapeHtml(deltaLabel)}</strong></div>`;
            })
            .join("")
        : '<span class="text-muted small">No mix shift data.</span>'
    );
    setText("strategyTop1Share", concentration?.top1_share != null ? `${fmtPct1.format(concentration.top1_share)}%` : EM_DASH);
    setText("strategyTop10Share", concentration?.top10_share != null ? `${fmtPct1.format(concentration.top10_share)}%` : EM_DASH);
    setText("strategyPareto80", concentration?.skus_to_80 != null ? fmtInt.format(concentration.skus_to_80) : EM_DASH);
  };

  const renderKpis = (kpis = {}) => {
    setText("kpiRevenue", fmtMoney0.format(kpis.revenue ?? 0));
    setText("kpiQty", fmtInt.format(kpis.qty ?? 0));
    setText("kpiWeight", fmtInt.format(kpis.weight ?? 0));
    setText("kpiUnique", fmtInt.format(kpis.products ?? kpis.rows ?? 0));
    setText("kpiCustomers", fmtInt.format(kpis.customers ?? 0));
    setText("kpiMargin", kpis.margin_pct != null ? `${fmtPct1.format(kpis.margin_pct)}%` : EM_DASH);
    setText("kpiAvgPrice", kpis.avg_price != null ? fmtMoney2.format(kpis.avg_price) : EM_DASH);
    setText("kpiMedianPrice", kpis.median_price != null ? fmtMoney2.format(kpis.median_price) : EM_DASH);
    setText("kpiRevPerProduct", kpis.revenue_per_product != null ? fmtMoney0.format(kpis.revenue_per_product) : EM_DASH);
    setText("kpiRevPerCustomer", kpis.revenue_per_customer != null ? fmtMoney0.format(kpis.revenue_per_customer) : EM_DASH);
    setText("kpiCostCoverage", kpis.cost_coverage_pct != null ? `${fmtPct1.format(kpis.cost_coverage_pct)}%` : EM_DASH);
    setText("kpiMissingCostSkus", fmtInt.format(kpis.missing_cost_sku_count ?? 0));
    setText("kpiContributionP50", kpis.contribution_lb_p50 != null ? fmtMoney2.format(kpis.contribution_lb_p50) : EM_DASH);
    setText("kpiProfitAtRisk", fmtMoney0.format(kpis.profit_at_risk ?? 0));
    setText("kpiUpliftPotential", fmtMoney0.format(kpis.risk_profit_uplift_target ?? 0));
    setText("kpiProfit", fmtMoney0.format((kpis.profit ?? 0)));
    setText("kpiProfitNote", "");
    setText("upP10", kpis.unit_price_p10 != null ? fmtMoney2.format(kpis.unit_price_p10) : EM_DASH);
    setText("upP50", kpis.unit_price_p50 != null ? fmtMoney2.format(kpis.unit_price_p50) : EM_DASH);
    setText("upP90", kpis.unit_price_p90 != null ? fmtMoney2.format(kpis.unit_price_p90) : EM_DASH);
  };

  const bindKpiCards = () => {
    const cardMap = {
      kpiRevenue: { sortBy: "revenue", sortDir: "desc", section: "table", emphasis: "revenue" },
      kpiQty: { sortBy: "qty", sortDir: "desc", section: "table", emphasis: "weight" },
      kpiWeight: { sortBy: "weight", sortDir: "desc", section: "table", emphasis: "weight" },
      kpiUnique: { sortBy: "revenue", sortDir: "desc", section: "table" },
      kpiCustomers: { quickFilters: ["high_customer_dependency"], sortBy: "customer_count", sortDir: "desc", section: "table", mode: "analyst" },
      kpiMargin: { quickFilters: ["recover_margin"], section: "pricing", emphasis: "profit", mode: "analyst" },
      kpiAvgPrice: { sortBy: "current_unit_price", sortDir: "desc", section: "table" },
      kpiMedianPrice: { sortBy: "current_unit_price", sortDir: "desc", section: "table" },
      kpiRevPerProduct: { sortBy: "revenue", sortDir: "desc", section: "assortment" },
      kpiRevPerCustomer: { sortBy: "customer_count", sortDir: "desc", section: "table", mode: "analyst" },
      kpiCostCoverage: { quickFilters: ["missing_cost"], section: "execution", emphasis: "profit", mode: "analyst" },
      kpiMissingCostSkus: { quickFilters: ["missing_cost"], section: "execution", emphasis: "profit", mode: "analyst" },
      kpiContributionP50: { quickFilters: ["recover_margin"], section: "pricing", emphasis: "profit", mode: "analyst" },
      kpiProfitAtRisk: { quickFilters: ["recover_margin"], section: "pricing", emphasis: "profit", mode: "analyst" },
      kpiUpliftPotential: { quickFilters: ["recover_margin"], section: "pricing", emphasis: "profit", mode: "analyst" },
    };
    Object.entries(cardMap).forEach(([id, action]) => {
      const card = document.getElementById(id)?.closest(".metric-card");
      if (!card) return;
      makeInteractiveCard(card, () => applyDetailView(action));
    });
  };

  const bindInsightCards = () => {
    const cardActions = [
      ["insightMomentum", () => applyDetailView({ section: "demand", sortBy: "revenue_delta", sortDir: "desc", mode: "analyst" })],
      ["momDelta", () => {
        const comparisonMetric = ((lastPayload?.insights || []).find((row) => row?.metric === "comparison_delta")) || {};
        applyDetailView({ section: "demand", quickFilters: comparisonMetric?.delta_pct < 0 ? ["promote_candidate"] : ["protect_core"], mode: "analyst" });
      }],
      ["predictiveRev", () => applyDetailView({ section: "demand", sortBy: "revenue_delta", sortDir: "desc", mode: "analyst" })],
      ["insightTopProduct", () => {
        const topProduct = ((lastPayload?.insights || []).find((row) => row?.metric === "top_product")) || {};
        const row = resolveProductContextRow(topProduct);
        if (!getSku(row)) return;
        renderProductIntel(row, "Executive scorecard", "Top product", "Revenue", row.revenue ?? topProduct.revenue ?? null);
      }],
    ];
    cardActions.forEach(([id, handler]) => {
      const card = document.getElementById(id)?.closest(".insight-card");
      if (!card) return;
      makeInteractiveCard(card, handler);
    });
  };

  const renderVelocity = (velocity = {}) => {
    setText("velAvgWeekly", fmtInt.format(velocity.avg_weekly ?? 0));
    setText("velWeeklyRevenue", fmtMoney0.format(velocity.weekly_revenue ?? 0));
    setText("velRevPerProduct", fmtMoney0.format(velocity.rev_per_product ?? 0));
    setText("velActive", fmtInt.format(velocity.active_skus ?? 0));
    setText("velRoi", velocity.roi_pct != null ? `${fmtPct1.format(velocity.roi_pct)}%` : EM_DASH);
    setText("velRetail", EM_DASH);
    setText("velTopMover", EM_DASH);
    setText("velW13", EM_DASH);
  };

  const renderAISignals = (signals = {}) => {
    setText("aiMarginRisk", signals.margin_risk || EM_DASH);
    setText("aiMarginRiskNote", signals.notes || "");
    setText("aiPricing", signals.pricing_action || EM_DASH);
    const confidence = signals.confidence ? `Confidence: ${signals.confidence}` : "";
    setText("aiPricingNote", confidence);
  };

  const renderInsights = (insights = [], projected = null, comparison = {}) => {
    const map = {};
    insights.forEach((i) => { if (i?.metric) map[i.metric] = i; });
    const momentum = map.revenue_momentum || map.comparison_delta || map.mom_delta;
    if (momentum) {
      setText("insightMomentum", fmtMoney0.format(momentum.current ?? 0));
      const delta = momentum.delta_pct;
      setText("insightMomentumDelta", delta != null ? `${delta > 0 ? "+" : ""}${fmtPct1.format(delta)}%` : EM_DASH);
      const compareLabel = momentum.label || comparison?.comparison_label || "prior comparable window";
      setText(
        "insightMomentumNote",
        momentum.prev != null ? `${compareLabel} ${MIDDLE_DOT} ${fmtMoney0.format(momentum.prev)}` : compareLabel
      );
      setText("momDelta", delta != null ? `${delta > 0 ? "+" : ""}${fmtPct1.format(delta)}%` : EM_DASH);
      setText("momNote", momentum.prev != null ? `${compareLabel} ${MIDDLE_DOT} ${fmtMoney0.format(momentum.prev)}` : compareLabel);
    }
    const top = map.top_product;
    if (top) {
      setText("insightTopProduct", displayName(top));
      setText("insightTopProductShare", top.revenue != null ? fmtMoney0.format(top.revenue) : EM_DASH);
    }
    const proj = map.projected_next_month || projected;
    if (proj) {
      setText("predictiveRev", proj.value != null ? fmtMoney0.format(proj.value) : EM_DASH);
      setText("predictiveRevNote", proj.note || "");
    }
  };

  const renderTrajectory = (trajectory = {}, forecast = [], comparison = {}) => {
    const labels = trajectory.labels || [];
    const rev = trajectory.revenue || [];
    const qty = trajectory.qty || [];
    const ctx = document.getElementById("trendChart");
    if (!ctx) return;
    destroyChart("trajectory");
    if (!labels.length) {
      ctx.replaceWith(ctx.cloneNode(true));
      return;
    }
    const grain = String(trajectory.grain || "monthly").toLowerCase();
    const subnote = document.getElementById("trajectorySubnote");
    if (subnote) {
      subnote.textContent = comparison?.trajectory_note || (grain === "weekly"
        ? "Revenue and demand trend (weekly bins selected automatically for short windows)."
        : "Revenue and demand trend (monthly bins).");
    }

    const seriesLabels = [...labels];
    const revSeries = [...rev];
    const qtySeries = [...qty];
    const datasets = [
      { label: "Revenue", data: revSeries, backgroundColor: "#7a413a" },
      { label: "Demand", data: qtySeries, type: "line", yAxisID: "y1", borderColor: "#0d6efd", backgroundColor: "rgba(13,110,253,.3)", fill: false, tension: 0.2 },
    ];
    if (!isV4) {
      const forecastMap = new Map((forecast || []).map((p) => [p.month || p.label, p.revenue]));
      const allLabels = [...seriesLabels];
      (forecast || []).forEach((p) => {
        const label = p.month || p.label;
        if (label && !allLabels.includes(label)) allLabels.push(label);
      });
      if (allLabels.length !== seriesLabels.length) {
        const revMap = new Map(seriesLabels.map((label, idx) => [label, revSeries[idx]]));
        const qtyMap = new Map(seriesLabels.map((label, idx) => [label, qtySeries[idx]]));
        seriesLabels.splice(0, seriesLabels.length, ...allLabels);
        revSeries.splice(0, revSeries.length, ...allLabels.map((label) => (revMap.has(label) ? revMap.get(label) : null)));
        qtySeries.splice(0, qtySeries.length, ...allLabels.map((label) => (qtyMap.has(label) ? qtyMap.get(label) : null)));
      }
      const forecastSeries = seriesLabels.map((l) => (forecastMap.has(l) ? forecastMap.get(l) : null));
      if (forecastSeries.some((v) => v != null)) {
        datasets.push({ label: "Forecast", data: forecastSeries, type: "line", borderColor: "#198754", borderDash: [4, 4], fill: false });
      }
    }

    charts.trajectory = new Chart(ctx, {
      type: "bar",
      data: { labels: seriesLabels, datasets },
      options: {
        responsive: true,
        interaction: { mode: "index", intersect: false },
        onClick: (_evt, activeEls) => {
          const idx = activeEls?.[0]?.index;
          if (idx == null) return;
          const label = seriesLabels[idx];
          applyDetailView({
            section: "table",
            sortBy: "revenue_delta",
            sortDir: "desc",
            mode: "analyst",
            search: "",
          });
          setText("tableLayerContext", `${label || "Selected period"} was clicked from trajectory. The table is now sorted to inspect the biggest SKU-level changes inside the same visible scope.`);
        },
        scales: {
          x: {
            ticks: {
              autoSkip: true,
              maxRotation: 0,
              minRotation: 0,
              maxTicksLimit: 12,
            },
          },
          y: { beginAtZero: true, ticks: { callback: (v) => fmtMoney0.format(v) } },
          y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, ticks: { callback: (v) => fmtInt.format(v) } },
        },
      },
    });
    removeSkeleton("trendChart");
  };

  const renderPriceVelocity = (points = []) => {
    const el = document.getElementById("priceVelocityChart");
    if (!el) return;
    removeSkeleton("priceVelocityChart");
    const rows = Array.isArray(points) ? points : [];
    if (!rows.length) {
      el.innerHTML = '<p class="text-muted small">No data.</p>';
      return;
    }
    const filtered = rows
      .map((p) => ({
        ...p,
        velocity: p.velocity_per_month ?? p.orders_per_month,
      }))
      .filter((p) => p.unit_price != null && p.velocity != null);
    if (!filtered.length) {
      el.innerHTML = '<p class="text-muted small">No price/velocity data.</p>';
      return;
    }
    if (!window.Plotly) {
      el.innerHTML = '<p class="text-muted small">Plotly not loaded.</p>';
      return;
    }
    const sorted = [...filtered].sort((a, b) => (b.revenue || 0) - (a.revenue || 0));
    const topN = sorted.slice(0, 150);
    const x = topN.map((p) => p.unit_price ?? 0);
    const y = topN.map((p) => p.velocity ?? 0);
    const size = topN.map((p) => Math.max(5, Math.sqrt(Math.abs(p.revenue_share ?? 1)) * 3));
    const color = topN.map((p) => (p.margin_pct == null ? 0 : p.margin_pct));
    const text = topN.map((p) => `${displayName(p)}<br>Unit price: ${fmtMoney2.format(p.unit_price ?? 0)}<br>Velocity: ${fmtInt.format(p.velocity ?? 0)} /mo<br>Margin: ${p.margin_pct != null ? fmtPct1.format(p.margin_pct) + "%" : EM_DASH}`);
    Plotly.newPlot(
      el,
      [
        {
          x,
          y,
          mode: "markers",
          type: "scatter",
          marker: { size, sizemode: "area", sizeref: 2, color, colorscale: "RdYlGn", showscale: true },
          text,
          hoverinfo: "text",
        },
      ],
      {
        margin: { t: 10, l: 40, r: 20, b: 40 },
        height: 200,
        xaxis: { title: "Unit price" },
        yaxis: { title: "Velocity / month" },
      },
      { displayModeBar: false, responsive: true }
    );

    if (drilldownTemplate && typeof el.on === "function") {
      if (el.removeAllListeners) el.removeAllListeners("plotly_click");
      el.on("plotly_click", (ev) => {
        const idx = ev?.points?.[0]?.pointIndex;
        if (idx == null) return;
        const row = topN[idx];
        if (!row) return;
        renderProductIntel(row, "Pricing & Velocity", "Price vs Velocity", "Unit price", row.unit_price);
      });
    }
  };

  
  const renderPerformanceBubble = (bubble = {}) => {
    const el = document.getElementById("priceBubbleChart");
    if (!el) return;
    removeSkeleton("priceBubbleChart");
    const target = bubble.target_margin != null ? `${Math.round(bubble.target_margin * 100)}%` : EM_DASH;
    const floor = bubble.floor_margin != null ? `${Math.round(bubble.floor_margin * 100)}%` : EM_DASH;
    setText("priceTargetMargin", target);
    setText("priceBaseMargin", floor);

    const rows = Array.isArray(bubble.points) ? bubble.points : [];
    if (!rows.length) {
      el.innerHTML = '<p class="text-muted small">No data.</p>';
      return;
    }
    const includeMissing = document.getElementById("bubbleIncludeMissing")?.checked;
    const filtered = rows.filter((p) => includeMissing || p.has_cost || p.target_price != null);
    if (!filtered.length) {
      el.innerHTML = '<p class="text-muted small">No cost-qualified points.</p>';
      return;
    }
    if (!window.Plotly) {
      el.innerHTML = '<p class="text-muted small">Plotly not loaded.</p>';
      return;
    }
    const sorted = [...filtered].sort((a, b) => (b.revenue || 0) - (a.revenue || 0));
    const topN = state.bubbleTopN === "all" ? sorted : sorted.slice(0, Number(state.bubbleTopN) || 250);
    const yKey = state.bubbleYMetric === "revenue" ? "revenue" : "velocity_per_month";
    const colorKey = state.bubbleColorBy;

    const x = topN.map((p) => p.current_price ?? p.unit_price ?? 0);
    const y = topN.map((p) => (yKey === "revenue" ? (p.revenue ?? 0) : (p.velocity_per_month ?? p.orders_per_month ?? 0)));
    const size = topN.map((p) => Math.max(6, Math.sqrt(Math.abs(p.revenue_share ?? 1)) * 4));
    let marker = { size, sizemode: "area", sizeref: 2 };
    if (colorKey === "segment") {
      const segments = Array.from(new Set(topN.map((p) => p.segment || "Other")));
      const palette = ["#7a413a", "#0d6efd", "#198754", "#fd7e14", "#6f42c1", "#20c997", "#dc3545", "#6c757d"];
      const colorMap = new Map(segments.map((seg, idx) => [seg, palette[idx % palette.length]]));
      marker = { ...marker, color: topN.map((p) => colorMap.get(p.segment || "Other")), showscale: false };
    } else {
      marker = {
        ...marker,
        color: topN.map((p) => (p[colorKey] == null ? 0 : p[colorKey])),
        colorscale: "RdYlGn",
        showscale: true,
      };
    }
    const text = topN.map((p) => {
      const name = displayName(p);
      const uplift = p.uplift_pct != null ? `${fmtPct1.format(p.uplift_pct)}%` : EM_DASH;
      const tgt = p.target_price != null ? fmtMoney2.format(p.target_price) : EM_DASH;
      return `${name}<br>Current: ${fmtMoney2.format(p.current_price ?? p.unit_price ?? 0)}<br>Target: ${tgt}<br>Uplift: ${uplift}`;
    });

    Plotly.newPlot(
      el,
      [
        {
          x,
          y,
          mode: "markers",
          type: "scatter",
          marker,
          text,
          hoverinfo: "text",
        },
      ],
      {
        margin: { t: 10, l: 40, r: 20, b: 40 },
        height: 320,
        xaxis: { title: "Current price" },
        yaxis: { title: yKey === "revenue" ? "Revenue" : "Velocity / month" },
      },
      { displayModeBar: false, responsive: true }
    );

    if (drilldownTemplate && typeof el.on === "function") {
      if (el.removeAllListeners) el.removeAllListeners("plotly_click");
      el.on("plotly_click", (ev) => {
        const idx = ev?.points?.[0]?.pointIndex;
        if (idx == null) return;
        const row = topN[idx];
        if (!row) return;
        renderProductIntel(row, "Pricing & Margin Control", "Performance Bubble", "Current price", row.current_price ?? row.unit_price);
      });
    }
  };

  const renderPriceDist = (dist = []) => {
    const ctx = document.getElementById("priceDistChart");
    if (!ctx) return;
    destroyChart("priceDist");
    if (!dist.length) return;
    const labels = dist.map((b) => `B${b.bucket ?? ""}`);
    const values = dist.map((b) => b.count ?? 0);
    charts.priceDist = new Chart(ctx, {
      type: "bar",
      data: { labels, datasets: [{ label: "Unit price", data: values, backgroundColor: "#9b5f3d" }] },
      options: {
        responsive: true,
        plugins: { legend: { display: false } },
        onClick: (_evt, activeEls) => {
          const idx = activeEls?.[0]?.index;
          if (idx == null) return;
          const mid = Math.floor(labels.length / 2);
          applyDetailView({
            sortBy: "current_unit_price",
            sortDir: idx >= mid ? "desc" : "asc",
            section: "table",
          });
        },
      },
    });
    removeSkeleton("priceDistChart");
  };

  const renderMovers = (movers = []) => {
    const ctx = document.getElementById("moversChart");
    if (!ctx) return;
    destroyChart("movers");
    if (!movers.length) return;
    const metricSel = document.getElementById("moversMetric");
    const metric = (metricSel?.value || "revenue").toLowerCase();
    const deltaField = metric === "profit" ? "delta_profit" : (metric === "qty" ? "delta_qty" : "delta_revenue");
    const labelTitle = metric === "profit" ? `${DELTA} profit` : (metric === "qty" ? `${DELTA} units` : `${DELTA} revenue`);
    const labels = movers.map((m) => displayName(m));
    const delta = movers.map((m) => m[deltaField] ?? m.delta ?? 0);
    const colors = movers.map((m) => (((m[deltaField] ?? m.delta ?? 0) >= 0) ? "#0d6efd" : "#dc3545"));
    charts.movers = new Chart(ctx, {
      type: "bar",
      data: { labels, datasets: [{ label: labelTitle, data: delta, backgroundColor: colors }] },
      options: {
        indexAxis: "y",
        responsive: true,
        plugins: { legend: { display: false } },
        onClick: (_evt, activeEls) => {
          const idx = activeEls?.[0]?.index;
          if (idx == null) return;
          const row = movers[idx];
          if (!row) return;
          renderProductIntel(row, "Trajectory & Movers", "Top Movers", labelTitle, row[deltaField] ?? row.delta);
        },
      },
    });
    removeSkeleton("moversChart");
  };

  const renderTopProducts = (products = []) => {
    const rawMetric = (document.getElementById("topMetric")?.value || "revenue").toLowerCase();
    const metric = rawMetric === "margin" ? "margin_pct" : rawMetric === "avg_price" ? "unit_price" : rawMetric;
    const topN = Number(document.getElementById("topN")?.value || 15);
    const sorted = [...products].sort((a, b) => (b[metric] || 0) - (a[metric] || 0)).slice(0, topN);
    const labels = sorted.map((p) => displayName(p));
    const shortLabels = labels.map((name) => (String(name).length > 34 ? `${String(name).slice(0, 34)}${ELLIPSIS}` : name));
    const values = sorted.map((p) => p[metric] || 0);
    const ctx = document.getElementById("topChart");
    if (!ctx) return;
    destroyChart("top");
    const label = rawMetric === "margin" ? "Margin %" : rawMetric === "avg_price" ? "Avg price" : rawMetric;
    charts.top = new Chart(ctx, {
      type: "bar",
      data: { labels: shortLabels, datasets: [{ label, data: values, backgroundColor: "#7a413a" }] },
      options: {
        indexAxis: "y",
        responsive: true,
        onClick: (_evt, activeEls) => {
          const idx = activeEls?.[0]?.index;
          if (idx == null) return;
          const row = sorted[idx];
          if (!row) return;
          renderProductIntel(row, "Portfolio Ranking", "Top Products", label, row[metric] || 0);
        },
        plugins: {
          legend: { display: false },
          tooltip: {
            callbacks: {
              title: (items) => {
                const idx = items?.[0]?.dataIndex ?? 0;
                return labels[idx] || "";
              },
            },
          },
        },
      },
    });
    removeSkeleton("topChart");
  };

  const renderPareto = (pareto = []) => {
    const ctx = document.getElementById("paretoChart");
    if (!ctx) return;
    destroyChart("pareto");
    if (!pareto.length) return;
    const names = pareto.map((p) => p.label || p.display_name || p.product_name || EM_DASH);
    const labels = pareto.map((_, idx) => String(idx + 1));
    const values = pareto.map((p) => p.revenue);
    const cum = pareto.map((p) => p.cumulative);
    let pareto80Rank = null;
    for (let i = 0; i < cum.length; i += 1) {
      if ((cum[i] ?? 0) >= 80) {
        pareto80Rank = i + 1;
        break;
      }
    }
    charts.pareto = new Chart(ctx, {
      data: {
        labels,
        datasets: [
          { type: "bar", label: "Revenue", data: values, backgroundColor: "#9b5f3d" },
          { type: "line", label: "Cumulative %", data: cum, borderColor: "#0d6efd", yAxisID: "y1", tension: 0.2 },
          { type: "line", label: "80% threshold", data: labels.map(() => 80), borderColor: "#6c757d", borderDash: [4, 4], yAxisID: "y1", pointRadius: 0 },
        ],
      },
      options: {
        responsive: true,
        onClick: (_evt, activeEls) => {
          const idx = activeEls?.[0]?.index;
          if (idx == null) return;
          const row = pareto[idx];
          if (!row) return;
          renderProductIntel(row, "Portfolio Ranking", "Pareto", "Revenue", row.revenue);
        },
        plugins: {
          tooltip: {
            callbacks: {
              title: (items) => {
                const idx = items?.[0]?.dataIndex ?? 0;
                return `Rank ${idx + 1}: ${names[idx] || EM_DASH}`;
              },
            },
          },
        },
        scales: {
          y: { beginAtZero: true, ticks: { callback: (v) => fmtMoney0.format(v) } },
          y1: { beginAtZero: true, position: "right", grid: { drawOnChartArea: false }, ticks: { callback: (v) => `${fmtPct1.format(v)}%` } },
        },
      },
    });
    setText("concPareto80", pareto80Rank != null ? fmtInt.format(pareto80Rank) : EM_DASH);
    removeSkeleton("paretoChart");
  };

  const renderSegmentSummary = (summary = []) => {
    const list = document.getElementById("segmentSummaryList");
    if (list) {
      if (!summary.length) {
        list.innerHTML = '<span class="text-muted small">No segment data.</span>';
      } else {
        list.innerHTML = summary
          .map(
            (s, idx) =>
              `<button type="button" class="btn btn-link p-0 text-start text-decoration-none w-100 d-flex justify-content-between segment-summary-link" data-segment-summary="${idx}"><span>${s.segment || EM_DASH}</span><span>${fmtInt.format(s.sku_count || 0)} ${MIDDLE_DOT} ${fmtMoney0.format(
                s.revenue || 0
              )}</span></button>`
          )
          .join("");
        list.querySelectorAll("[data-segment-summary]").forEach((node) => {
          const idx = Number(node.getAttribute("data-segment-summary"));
          const row = summary[idx];
          if (!row?.segment) return;
          node.addEventListener("click", () => applyDetailView({ segments: [row.segment], section: "table", mode: "analyst" }));
        });
      }
    }
    const select = document.getElementById("segmentFilter");
    if (select) {
      select.innerHTML = "";
      summary.forEach((s) => {
        const opt = document.createElement("option");
        opt.value = s.segment;
        opt.textContent = `${s.segment || EM_DASH} (${fmtInt.format(s.sku_count || 0)})`;
        opt.selected = state.segments.includes(s.segment);
        select.appendChild(opt);
      });
    }
  };

  const renderSegmentMovers = (movers = []) => {
    const list = document.getElementById("segmentMoversList");
    if (!list) return;
    if (!movers.length) {
      list.innerHTML = '<span class="text-muted small">No movers.</span>';
      return;
    }
    list.innerHTML = movers
      .map(
        (m, idx) =>
          `<button type="button" class="btn btn-link p-0 text-start text-decoration-none w-100 d-flex justify-content-between border-bottom py-1" data-segment-mover="${idx}"><span>${displayName(m)} (${m.segment || EM_DASH})</span><span>${formatSignedMoney(
            m.delta || 0
          )} ${MIDDLE_DOT} ${escapeHtml(m.status || "")}</span></button>`
      )
      .join("");
    list.querySelectorAll("[data-segment-mover]").forEach((node) => {
      const idx = Number(node.getAttribute("data-segment-mover"));
      const row = movers[idx];
      if (!row) return;
      node.addEventListener("click", () => renderProductIntel(row, "Segments", "Segment Movers", "Revenue delta", row.delta || 0));
    });
  };

  const renderSegmentMixShift = (rows = []) => {
    const host = document.getElementById("segmentMixShiftList");
    if (!host) return;
    const data = Array.isArray(rows) ? rows : [];
    if (!data.length) {
      host.innerHTML = '<span class="text-muted small">No mix shift data for current filters.</span>';
      return;
    }
    host.innerHTML = data
      .slice(0, 8)
      .map((row, idx) => {
        const delta = row?.share_delta_pp;
        const deltaLabel = delta == null || Number.isNaN(Number(delta))
          ? EM_DASH
          : `${delta > 0 ? "+" : ""}${fmtPct1.format(delta)} pp`;
        const cur = row?.share_current != null ? `${fmtPct1.format(row.share_current)}%` : EM_DASH;
        const prev = row?.share_prior != null ? `${fmtPct1.format(row.share_prior)}%` : EM_DASH;
        return `<button type="button" class="btn btn-link p-0 text-start text-decoration-none w-100 d-flex justify-content-between border-bottom py-1" data-segment-mix="${idx}"><span>${escapeHtml(row?.segment || EM_DASH)}</span><span>${escapeHtml(deltaLabel)} ${MIDDLE_DOT} ${escapeHtml(prev)} ${ARROW} ${escapeHtml(cur)}</span></button>`;
      })
      .join("");
    host.querySelectorAll("[data-segment-mix]").forEach((node) => {
      const idx = Number(node.getAttribute("data-segment-mix"));
      const row = data[idx];
      if (!row?.segment) return;
      node.addEventListener("click", () => applyDetailView({ segments: [row.segment], section: "table", mode: "analyst" }));
    });
  };

  const renderRecommendations = (recs = []) => {
    const el = document.getElementById("recPanel");
    if (!el) return;
    const rows = Array.isArray(recs) ? recs : [];
    if (!rows.length) {
      el.textContent = "No recommendations for current filters.";
      return;
    }
    el.innerHTML = rows
      .slice(0, 5)
      .map((r, idx) => {
        const name = displayName(r);
        const action = r.action || r.recommendation || "Review";
        const uplift = r.uplift_pct_est != null ? `${fmtPct1.format(r.uplift_pct_est)}%` : "";
        const note = r.rationale ? `<div class="text-muted small">${r.rationale}</div>` : "";
        const actionHtml = isV2
          ? `<span class="recommendation-badge">${escapeHtml(action)}${uplift ? ` ${MIDDLE_DOT} ${escapeHtml(uplift)}` : ""}</span>`
          : `<span>${escapeHtml(action)}${uplift ? ` ${MIDDLE_DOT} ${escapeHtml(uplift)}` : ""}</span>`;
        return `<button type="button" class="btn btn-link p-0 text-start text-decoration-none w-100 mb-2" data-recommendation-idx="${idx}"><div class="d-flex justify-content-between gap-2"><span>${escapeHtml(name)}</span>${actionHtml}</div>${note}</button>`;
      })
      .join("");
    el.querySelectorAll("[data-recommendation-idx]").forEach((node) => {
      const idx = Number(node.getAttribute("data-recommendation-idx"));
      const row = rows[idx];
      if (!row) return;
      node.addEventListener("click", () => renderProductIntel(row, "Execution", "Recommendations", row.action || "Recommendation", row.uplift_pct_est || 0));
    });
  };

  const riskTone = (value) => {
    const raw = String(value || "").toLowerCase();
    if (raw.includes("floor") || raw.includes("negative")) return "danger";
    if (raw.includes("target")) return "warning";
    return "neutral";
  };

  const formatSignedMoney = (value) => {
    if (value == null || Number.isNaN(Number(value))) return EM_DASH;
    const amount = Number(value);
    const sign = amount > 0 ? "+" : "";
    return `${sign}${fmtMoney0.format(amount)}`;
  };

  const formatRevenueDeltaPct = (row) => {
    const current = Number(row?.revenue_current ?? 0);
    const prior = Number(row?.revenue_prior ?? 0);
    if (prior <= 0 && current > 0) return "New";
    if (current <= 0 && prior > 0) return "Lost";
    if (row?.revenue_low_base) return "Low base";
    if (row?.revenue_delta_pct == null || Number.isNaN(Number(row.revenue_delta_pct))) return EM_DASH;
    const val = Number(row.revenue_delta_pct);
    return `${val > 0 ? "+" : ""}${fmtPct1.format(val)}%`;
  };

  const renderSegmentBadge = (value) => `<span class="tag-badge">${escapeHtml(value || EM_DASH)}</span>`;
  const renderRiskBadge = (value) =>
    `<span class="risk-badge tone-${riskTone(value)}">${escapeHtml(value || EM_DASH)}</span>`;
  const renderRecommendationBadge = (value) =>
    `<span class="recommendation-badge">${escapeHtml(value || EM_DASH)}</span>`;

  const applyColumnVisibility = () => {
    if (!isV2) return;
    const visible = new Set((state.visibleColumns || []).concat(["sku", "product"]));
    document.querySelectorAll("#productTable [data-column]").forEach((cell) => {
      const key = cell.getAttribute("data-column");
      if (!key) return;
      cell.classList.toggle("d-none", !visible.has(key));
    });
  };

  const renderColumnChooser = () => {
    if (!isV2) return;
    const host = document.getElementById("productsColumnChooser");
    if (!host) return;
    const visible = new Set((state.visibleColumns || []).concat(["sku", "product"]));
    host.innerHTML = `
      <div class="products-column-chooser-grid">
        ${ACTIVE_COLUMN_DEFS.map((col) => {
          const checked = visible.has(col.key) ? "checked" : "";
          const disabled = col.locked ? "disabled" : "";
          return `
            <label>
              <input type="checkbox" data-column-toggle="${col.key}" ${checked} ${disabled}>
              <span>${escapeHtml(col.label)}</span>
            </label>
          `;
        }).join("")}
      </div>
    `;
    host.querySelectorAll("[data-column-toggle]").forEach((input) => {
      input.addEventListener("change", (evt) => {
        const key = evt.target.getAttribute("data-column-toggle");
        if (!key) return;
        const next = new Set((state.visibleColumns || []).concat(["sku", "product"]));
        if (evt.target.checked) next.add(key);
        else next.delete(key);
        state.visibleColumns = ACTIVE_COLUMN_DEFS.map((col) => col.key).filter((col) => next.has(col));
        writeStoredColumns(state.visibleColumns);
        applyColumnVisibility();
        syncExportLinks();
      });
    });
  };

  const applyColumnGroup = (groupKey) => {
    if (!isV2) return;
    const nextGroup = COLUMN_GROUPS[groupKey];
    if (!Array.isArray(nextGroup) || !nextGroup.length) return;
    const keys = new Set(["sku", "product", ...nextGroup]);
    state.visibleColumns = ACTIVE_COLUMN_DEFS.map((col) => col.key).filter((key) => keys.has(key));
    writeStoredColumns(state.visibleColumns);
    renderColumnChooser();
    applyColumnVisibility();
    syncExportLinks();
  };

  const syncWatchlistButtons = () => {
    if (!isV4) return;
    document.querySelectorAll("[data-watchlist-preset]").forEach((btn) => {
      const key = btn.getAttribute("data-watchlist-preset") || "";
      const preset = WATCHLIST_PRESETS[key];
      const current = JSON.stringify((state.quickFilters || []).slice().sort());
      const target = JSON.stringify(((preset?.quickFilters || [])).slice().sort());
      btn.classList.toggle("is-active", current === target);
    });
  };

  const syncQuickFilterButtons = () => {
    document.querySelectorAll("#tableQuickFilters [data-quick-filter]").forEach((chip) => {
      const active = state.quickFilters.includes(chip.getAttribute("data-quick-filter"));
      chip.classList.toggle("is-active", active);
    });
  };

  const applyEmphasisPreset = (emphasis) => {
    const next = ["revenue", "profit", "weight"].includes(emphasis) ? emphasis : "revenue";
    state.workspaceEmphasis = next;
    const topMetric = document.getElementById("topMetric");
    const moversMetric = document.getElementById("moversMetric");
    const bubbleColor = document.getElementById("bubbleColorBy");
    const bubbleY = document.getElementById("bubbleYMetric");
    if (next === "profit") {
      if (topMetric) topMetric.value = "profit";
      if (moversMetric) moversMetric.value = "profit";
      if (bubbleColor) bubbleColor.value = "margin_pct";
      if (bubbleY) bubbleY.value = "revenue";
      state.bubbleColorBy = "margin_pct";
      state.bubbleYMetric = "revenue";
    } else if (next === "weight") {
      if (topMetric) topMetric.value = "weight";
      if (moversMetric) moversMetric.value = "qty";
      if (bubbleColor) bubbleColor.value = "segment";
      if (bubbleY) bubbleY.value = "velocity";
      state.bubbleColorBy = "segment";
      state.bubbleYMetric = "velocity";
    } else {
      if (topMetric) topMetric.value = "revenue";
      if (moversMetric) moversMetric.value = "revenue";
      if (bubbleColor) bubbleColor.value = "uplift_pct";
      if (bubbleY) bubbleY.value = "velocity";
      state.bubbleColorBy = "uplift_pct";
      state.bubbleYMetric = "velocity";
    }
    applyWorkspaceSettings();
    if (lastPayload) {
      renderTopProducts(lastPayload?.charts?.top_products || []);
      renderMovers(lastPayload?.charts?.movers || []);
      renderPerformanceBubble(lastPayload?.performance_bubble || {});
    }
  };

  const applyWatchlistPreset = (presetKey) => {
    const preset = WATCHLIST_PRESETS[presetKey];
    if (!preset) return;
    state.quickFilters = [...(preset.quickFilters || [])];
    state.segments = [];
    state.search = "";
    const searchEl = document.getElementById("tableSearch");
    if (searchEl) searchEl.value = "";
    const segmentSelect = document.getElementById("segmentFilter");
    if (segmentSelect) {
      Array.from(segmentSelect.options || []).forEach((option) => {
        option.selected = false;
      });
    }
    state.page = 1;
    if (preset.emphasis) {
      applyEmphasisPreset(preset.emphasis);
    }
    if (preset.mode) {
      state.workspaceMode = preset.mode;
    }
    if (preset.section && !state.visibleSections.includes(preset.section)) {
      state.visibleSections = [...state.visibleSections, preset.section];
    }
    applyWorkspaceSettings();
    syncWatchlistButtons();
    fetchBundle();
    if (preset.section) {
      setTimeout(() => scrollToSection(preset.section), 100);
    }
  };

  const ensureQuadrantModal = () => {
    if (document.getElementById("healthQuadrantModal")) return;
    const wrapper = document.createElement("div");
    wrapper.innerHTML = `
      <div class="modal fade" id="healthQuadrantModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-lg modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title" id="healthQuadrantTitle">Quadrant items</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
              <div id="healthQuadrantBody" class="small text-muted">Loading${ELLIPSIS}</div>
            </div>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(wrapper.firstElementChild);
  };

  const openQuadrantModal = (quadrantLabel, topItems = [], quadrantKey = "") => {
    ensureQuadrantModal();
    const title = document.getElementById("healthQuadrantTitle");
    const body = document.getElementById("healthQuadrantBody");
    if (!title || !body) return;
    title.textContent = `${quadrantLabel || "Quadrant"} ${MIDDLE_DOT} Top items`;
    const rows = (Array.isArray(topItems) ? topItems : []).slice(0, 10);
    const tableRows = rows.length
      ? rows.map((item) => {
          const sku = item?.product_id || "";
          const link = sku ? appendFiltersToUrl(drilldownTemplate.replace("__PID__", encodeURIComponent(sku))) : "#";
          return `<tr><td><a href="${link}" class="text-decoration-none">${escapeHtml(item?.display_name || sku || EM_DASH)}</a></td><td class="text-end">${fmtMoney0.format(item?.revenue || 0)}</td><td class="text-end">${item?.margin_pct != null ? `${fmtPct1.format(item.margin_pct)}%` : EM_DASH}</td><td class="text-end">${item?.velocity_per_month != null ? fmtInt.format(item.velocity_per_month) : EM_DASH}</td></tr>`;
        }).join("")
      : '<tr><td colspan="4" class="text-muted text-center">No items.</td></tr>';
    const exportBase = root.dataset.exportQuadrantCsv || "";
    const exportHref = exportBase ? appendFiltersToUrl(`${exportBase}?quadrant=${encodeURIComponent(quadrantKey || "")}`) : "#";
    body.innerHTML = `
      <div class="d-flex justify-content-end mb-2"><a class="btn btn-sm btn-outline-secondary" href="${exportHref}"><i class="bi bi-download me-1"></i>Export full quadrant</a></div>
      <div class="table-responsive">
        <table class="table table-sm">
          <thead><tr><th>SKU</th><th class="text-end">Revenue</th><th class="text-end">Margin %</th><th class="text-end">Velocity/mo</th></tr></thead>
          <tbody>${tableRows}</tbody>
        </table>
      </div>
    `;
    try {
      const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById("healthQuadrantModal"));
      modal.show();
    } catch (err) {
      console.error("quadrant modal", err);
    }
  };

  const quadrantActionMap = {
    protect: { quickFilters: ["protect_core"], section: "table", mode: "analyst" },
    fix_margin: { quickFilters: ["recover_margin"], section: "pricing", mode: "analyst" },
    grow: { quickFilters: ["promote_candidate"], section: "execution", mode: "analyst" },
    rationalize: { quickFilters: ["rationalize_candidate"], section: "assortment", mode: "analyst" },
  };

  const renderHealthMatrix = (matrix = {}) => {
    const host = document.getElementById("healthMatrixPanel");
    if (!host) return;
    const quadrants = Array.isArray(matrix?.quadrants) ? matrix.quadrants : [];
    if (!quadrants.length) {
      host.innerHTML = '<div class="text-muted small">No product health data for the current filters.</div>';
      return;
    }
    const velocityLow = matrix.velocity_cutoff_low != null ? fmtInt.format(matrix.velocity_cutoff_low) : EM_DASH;
    const velocityHigh = matrix.velocity_cutoff_high != null ? fmtInt.format(matrix.velocity_cutoff_high) : EM_DASH;
    const profitabilityLow = matrix.profitability_cutoff_low != null ? `${fmtPct1.format(matrix.profitability_cutoff_low)}%` : EM_DASH;
    const profitabilityHigh = matrix.profitability_cutoff_high != null ? `${fmtPct1.format(matrix.profitability_cutoff_high)}%` : EM_DASH;
    host.innerHTML = quadrants
      .map((quadrant) => {
        const key = quadrant?.key || "";
        const topItems = Array.isArray(quadrant?.top_items) ? quadrant.top_items : [];
        return `
          <div class="health-card tone-${escapeHtml(quadrant.tone || "neutral")}">
            <div class="health-kicker">${escapeHtml(quadrant.label || EM_DASH)}</div>
            <div class="health-value">${fmtInt.format(quadrant.sku_count || 0)}</div>
            <div class="health-meta">${fmtPct1.format(quadrant.revenue_share || 0)}% revenue ${MIDDLE_DOT} ${fmtPct1.format(quadrant.profit_share || 0)}% profit</div>
            <div class="health-meta">${fmtMoney0.format(quadrant.revenue || 0)} revenue ${MIDDLE_DOT} ${fmtMoney0.format(quadrant.profit || 0)} profit</div>
            <div class="health-meta mt-2">${escapeHtml(quadrant.description || "")}</div>
            <div class="health-meta mt-2">Velocity bands: low <= ${escapeHtml(velocityLow)}, high >= ${escapeHtml(velocityHigh)} ${MIDDLE_DOT} Profitability bands: low <= ${escapeHtml(profitabilityLow)}, high >= ${escapeHtml(profitabilityHigh)}</div>
            <div class="d-flex gap-2 mt-3">
              <button type="button" class="btn btn-sm btn-outline-secondary" data-health-open="${escapeHtml(key)}">Top 10 items</button>
              <button type="button" class="btn btn-sm btn-outline-primary" data-health-view="${escapeHtml(key)}">Open view</button>
            </div>
          </div>
        `;
      })
      .join("");

    host.querySelectorAll("[data-health-open]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-health-open") || "";
        const rows = (quadrants.find((q) => (q?.key || "") === key)?.top_items || []);
        const label = quadrants.find((q) => (q?.key || "") === key)?.label || "Quadrant";
        openQuadrantModal(label, rows, key);
      });
    });
    host.querySelectorAll("[data-health-view]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const key = btn.getAttribute("data-health-view") || "";
        const action = quadrantActionMap[key];
        if (action) applySignalAction(action);
      });
    });
  };

  const renderRiskOpportunity = (concentration = {}, risk = {}) => {
    setText(
      "concTop1Share",
      concentration?.top1_share != null ? `${fmtPct1.format(concentration.top1_share)}%` : EM_DASH
    );
    setText(
      "concTop10Share",
      concentration?.top10_share != null ? `${fmtPct1.format(concentration.top10_share)}%` : EM_DASH
    );
    setText(
      "concHhi",
      concentration?.hhi != null ? fmtInt.format(concentration.hhi) : EM_DASH
    );
    setText("concPareto80", concentration?.skus_to_80 ? fmtInt.format(concentration.skus_to_80) : EM_DASH);

    setText("riskBelowTargetCount", fmtInt.format(risk?.below_target_count ?? 0));
    setText("riskBelowTargetRevenue", fmtMoney0.format(risk?.below_target_revenue ?? 0));
    setText("riskNegativeCount", fmtInt.format(risk?.negative_margin_count ?? 0));
    setText("riskProfitUplift", fmtMoney0.format(risk?.profit_uplift_target ?? 0));

    const marginHost = document.getElementById("marginRiskList");
    if (marginHost) {
      const rows = Array.isArray(risk?.margin_risk_top) ? risk.margin_risk_top : [];
      if (!rows.length) {
        marginHost.innerHTML = '<span class="text-muted small">No below-target SKUs for current filters.</span>';
      } else {
        marginHost.innerHTML = rows
          .map((row, idx) => {
            const label = displayName(row);
            const margin = row?.margin_pct != null ? `${fmtPct1.format(row.margin_pct)}%` : EM_DASH;
            const revenue = fmtMoney0.format(row?.revenue ?? 0);
            return `<button type="button" class="btn btn-link p-0 text-start text-decoration-none w-100 d-flex justify-content-between border-bottom py-1" data-margin-risk-idx="${idx}"><span>${escapeHtml(label)}</span><span>${revenue} ${MIDDLE_DOT} ${margin}</span></button>`;
          })
          .join("");
        marginHost.querySelectorAll("[data-margin-risk-idx]").forEach((node) => {
          const idx = Number(node.getAttribute("data-margin-risk-idx"));
          const row = rows[idx];
          if (!row) return;
          node.addEventListener("click", () => renderProductIntel(row, "Pricing & Margin", "Margin risk", "Revenue", row.revenue || 0));
        });
      }
    }

    const oppHost = document.getElementById("velocityOpportunityList");
    if (oppHost) {
      const hvlm = Array.isArray(risk?.high_velocity_low_margin) ? risk.high_velocity_low_margin.slice(0, 5) : [];
      const hmlv = Array.isArray(risk?.high_margin_low_velocity) ? risk.high_margin_low_velocity.slice(0, 5) : [];
      const build = (title, rows) => {
        if (!rows.length) return `<div class="text-muted">${escapeHtml(title)}: no matches.</div>`;
        const items = rows
          .map((row, idx) => {
            const label = displayName(row);
            const velocity = row?.orders_per_month != null ? fmtInt.format(row.orders_per_month) : EM_DASH;
            const margin = row?.margin_pct != null ? `${fmtPct1.format(row.margin_pct)}%` : EM_DASH;
            const revenue = fmtMoney0.format(row?.revenue ?? 0);
            return `<li><button type="button" class="btn btn-link p-0 text-start text-decoration-none velocity-opportunity-link" data-opportunity-row="${idx}" data-opportunity-title="${escapeHtml(title)}"><strong>${escapeHtml(label)}</strong> ${MIDDLE_DOT} ${revenue} ${MIDDLE_DOT} ${margin} ${MIDDLE_DOT} ${velocity}/mo</button></li>`;
          })
          .join("");
        return `<div class="mb-3"><div class="fw-semibold mb-1">${escapeHtml(title)}</div><ul class="mb-0">${items}</ul></div>`;
      };
      oppHost.innerHTML = `${build("High velocity, low margin", hvlm)}${build("High margin, low velocity", hmlv)}`;
      oppHost.querySelectorAll("[data-opportunity-row]").forEach((node) => {
        node.addEventListener("click", () => {
          const idx = Number(node.getAttribute("data-opportunity-row"));
          const title = node.getAttribute("data-opportunity-title") || "Opportunity";
          const sourceRows = title.includes("low margin") ? hvlm : hmlv;
          const row = sourceRows[idx];
          if (!row) return;
          renderProductIntel(row, "Execution", title, "Revenue", row.revenue || 0);
        });
      });
    }
  };

  const renderPricingGuardrails = (guardrails = {}) => {
    setText("guardrailHighOutliers", fmtInt.format(guardrails?.high_outlier_count ?? 0));
    setText("guardrailLowOutliers", fmtInt.format(guardrails?.low_outlier_count ?? 0));
    const outsidePct = guardrails?.outside_pct;
    setText(
      "guardrailOutsidePct",
      outsidePct != null ? `${fmtPct1.format(outsidePct)}% (${fmtInt.format(guardrails?.outside_count ?? 0)})` : EM_DASH
    );
    const host = document.getElementById("guardrailActionList");
    if (!host) return;
    const rows = Array.isArray(guardrails?.rows) ? guardrails.rows.slice(0, 12) : [];
    if (!rows.length) {
      host.innerHTML = '<span class="text-muted small">No pricing guardrail actions for current filters.</span>';
      return;
    }
    host.innerHTML = rows
      .map((row, idx) => {
        const asp = row?.unit_price != null ? fmtMoney2.format(row.unit_price) : EM_DASH;
        const p10 = row?.p10 != null ? fmtMoney2.format(row.p10) : EM_DASH;
        const p50 = row?.p50 != null ? fmtMoney2.format(row.p50) : EM_DASH;
        const p90 = row?.p90 != null ? fmtMoney2.format(row.p90) : EM_DASH;
        const cv = row?.price_cv_pct != null ? `${fmtPct1.format(row.price_cv_pct)}%` : EM_DASH;
        return `
          <button type="button" class="btn btn-link p-0 text-start text-decoration-none w-100 border-bottom py-2 pricing-action-link" data-pricing-action-idx="${idx}">
            <div class="d-flex justify-content-between gap-2">
              <span class="fw-semibold">${escapeHtml(row?.display_name || row?.product_id || EM_DASH)}</span>
              <span class="recommendation-badge">${escapeHtml(row?.action || "Hold")}</span>
            </div>
            <div class="text-muted small">ASP ${asp} ${MIDDLE_DOT} P10 ${p10} ${MIDDLE_DOT} P50 ${p50} ${MIDDLE_DOT} P90 ${p90} ${MIDDLE_DOT} CV ${cv}</div>
            <div class="text-muted small">${escapeHtml(row?.reason || "")}</div>
          </button>
        `;
      })
      .join("");
    host.querySelectorAll("[data-pricing-action-idx]").forEach((node) => {
      const idx = Number(node.getAttribute("data-pricing-action-idx"));
      const row = rows[idx];
      if (!row) return;
      node.addEventListener("click", () => renderProductIntel(row, "Pricing & Margin", "Pricing actions", row.action || "Pricing action", row.unit_price ?? row.revenue ?? 0));
    });
  };

  const renderExecutionListBlock = (hostId, rows = []) => {
    const host = document.getElementById(hostId);
    if (!host) return;
    const data = Array.isArray(rows) ? rows.slice(0, 10) : [];
    if (!data.length) {
      host.innerHTML = '<span class="text-muted small">No matches.</span>';
      return;
    }
    host.innerHTML = data
      .map((row, idx) => {
        const revenue = fmtMoney0.format(row?.revenue ?? 0);
        const margin = row?.margin_pct != null ? `${fmtPct1.format(row.margin_pct)}%` : EM_DASH;
        const velocity = row?.orders_per_month != null ? fmtInt.format(row.orders_per_month) : EM_DASH;
        return `
          <button type="button" class="btn btn-link p-0 text-start text-decoration-none w-100 border-bottom py-2" data-execution-row="${idx}" data-execution-host="${hostId}">
            <div class="d-flex justify-content-between gap-2">
              <span>${escapeHtml(row?.display_name || row?.product_id || EM_DASH)}</span>
              <span class="recommendation-badge">${escapeHtml(row?.action || "Review")}</span>
            </div>
            <div class="text-muted small">${revenue} ${MIDDLE_DOT} ${margin} ${MIDDLE_DOT} ${velocity}/mo</div>
            <div class="text-muted small">${escapeHtml(row?.reason || "")}</div>
          </button>
        `;
      })
      .join("");
    host.querySelectorAll("[data-execution-row]").forEach((node) => {
      const idx = Number(node.getAttribute("data-execution-row"));
      const row = data[idx];
      if (!row) return;
      node.addEventListener("click", () => renderProductIntel(row, "Execution", hostId.replace(/^execution/, ""), row.action || "Execution", row.revenue || 0));
    });
  };

  const renderExecutionLists = (execution = {}) => {
    renderExecutionListBlock("executionPricingFixes", execution?.pricing_fixes || []);
    renderExecutionListBlock("executionCostFixes", execution?.cost_fixes || []);
    renderExecutionListBlock("executionPromoteCandidates", execution?.promote_candidates || []);
  };

  const renderTableV1 = (tbody, rows, table, statusEl) => {
    rows.forEach((r) => {
      const sku = getSku(r);
      const intelUrl = drilldownTemplate
        ? drilldownTemplate.replace("__PID__", encodeURIComponent(sku))
        : (r.intel_url || "#");
      const link = appendFiltersToUrl(intelUrl);
      const recLabel = r.recommendation || EM_DASH;
      const quickRec = r.quick_rec || EM_DASH;
      const marginVal = r.margin != null ? fmtMoney2.format(r.margin) : EM_DASH;
      const tr = document.createElement("tr");
      tr.classList.add("table-row-clickable");
      tr.innerHTML = `
        <td>${escapeHtml(displayName(r))}</td>
        <td>${escapeHtml(r.segment ?? EM_DASH)}</td>
        <td class="text-end">${fmtMoney0.format(r.revenue ?? 0)}</td>
        <td class="text-end">${r.revenue_share != null ? `${fmtPct1.format(r.revenue_share)}%` : EM_DASH}</td>
        <td class="text-end">${fmtInt.format(r.qty ?? 0)}</td>
        <td class="text-end">${r.qty_share != null ? `${fmtPct1.format(r.qty_share)}%` : EM_DASH}</td>
        <td class="text-end">${r.unit_price != null ? fmtMoney2.format(r.unit_price) : EM_DASH}</td>
        <td class="text-end">${r.cost != null ? fmtMoney2.format(r.cost) : EM_DASH}</td>
        <td class="text-end">${r.profit != null ? fmtMoney2.format(r.profit) : EM_DASH}</td>
        <td class="text-end">${r.target_price != null ? fmtMoney2.format(r.target_price) : EM_DASH}</td>
        <td class="text-end">${r.uplift_pct != null ? `${fmtPct1.format(r.uplift_pct)}%` : EM_DASH}</td>
        <td class="text-end">${r.margin_pct != null ? `${fmtPct1.format(r.margin_pct)}%` : EM_DASH}</td>
        <td class="text-end">${marginVal}</td>
        <td>${escapeHtml(recLabel)}</td>
        <td>${escapeHtml(r.first_sold || EM_DASH)}</td>
        <td>${escapeHtml(r.last_sold || EM_DASH)}</td>
        <td>${escapeHtml(quickRec)}</td>
        <td class="text-center"><a class="btn btn-sm btn-outline-primary intel-btn" href="${link}" data-link="${link}" data-sku="${escapeHtml(sku)}">Intel</a></td>
      `;
      tr.addEventListener("click", (evt) => {
        if (evt.target.closest("a,button,input,select,label")) return;
        window.location.href = link;
      });
      tbody.appendChild(tr);
    });
    if (statusEl) statusEl.textContent = `Page ${table.page || 1} ${MIDDLE_DOT} ${rows.length} rows (of ${table.total ?? rows.length})`;
  };

  const renderTableV2 = (tbody, rows, table, statusEl) => {
    rows.forEach((r) => {
      const sku = getSku(r);
      const intelUrl = drilldownTemplate
        ? drilldownTemplate.replace("__PID__", encodeURIComponent(sku))
        : (r.intel_url || "#");
      const link = appendFiltersToUrl(intelUrl);
      const productLabel = r.product_name || r.label || r.display_name || sku || EM_DASH;
      const tr = document.createElement("tr");
      tr.classList.add("table-row-clickable");
      tr.innerHTML = `
        <td class="sticky-col sticky-col-1" data-column="sku">${escapeHtml(r.sku || sku || EM_DASH)}</td>
        <td class="sticky-col sticky-col-2" data-column="product"><span class="product-name-cell" title="${escapeHtml(productLabel)}">${escapeHtml(productLabel)}</span></td>
        <td data-column="segment">${renderSegmentBadge(r.segment)}</td>
        <td data-column="supplier">${escapeHtml(r.supplier || EM_DASH)}</td>
        <td class="text-end" data-column="customer_count">${fmtInt.format(r.customer_count ?? 0)}</td>
        <td class="text-end" data-column="supplier_count">${fmtInt.format(r.supplier_count ?? 0)}</td>
        <td class="text-end" data-column="region_breadth">${fmtInt.format(r.region_breadth ?? 0)}</td>
        <td class="text-end" data-column="top_customer_share">${r.top_customer_share != null ? `${fmtPct1.format(r.top_customer_share)}%` : EM_DASH}</td>
        <td class="text-end" data-column="customer_hhi">${r.customer_hhi != null ? fmtInt.format(r.customer_hhi) : EM_DASH}</td>
        <td class="text-end" data-column="revenue">${fmtMoney0.format(r.revenue ?? 0)}</td>
        <td class="text-end" data-column="revenue_current">${fmtMoney0.format(r.revenue_current ?? 0)}</td>
        <td class="text-end" data-column="revenue_prior">${fmtMoney0.format(r.revenue_prior ?? 0)}</td>
        <td class="text-end" data-column="revenue_delta">${formatSignedMoney(r.revenue_delta)}</td>
        <td class="text-end" data-column="revenue_delta_pct">${formatRevenueDeltaPct(r)}</td>
        <td class="text-end" data-column="revenue_share">${r.revenue_share != null ? `${fmtPct1.format(r.revenue_share)}%` : EM_DASH}</td>
        <td class="text-end" data-column="orders">${fmtInt.format(r.orders ?? 0)}</td>
        <td class="text-end" data-column="orders_current">${fmtInt.format(r.orders_current ?? 0)}</td>
        <td class="text-end" data-column="orders_prior">${fmtInt.format(r.orders_prior ?? 0)}</td>
        <td class="text-end" data-column="qty">${fmtInt.format(r.qty ?? 0)}</td>
        <td class="text-end" data-column="weight">${fmtInt.format(r.weight ?? 0)}</td>
        <td class="text-end" data-column="current_unit_price">${r.current_unit_price != null ? fmtMoney2.format(r.current_unit_price) : EM_DASH}</td>
        <td class="text-end" data-column="target_price">${r.target_price != null ? fmtMoney2.format(r.target_price) : EM_DASH}</td>
        <td class="text-end" data-column="uplift_pct">${r.uplift_pct != null ? `${fmtPct1.format(r.uplift_pct)}%` : EM_DASH}</td>
        <td class="text-end" data-column="cost">${r.cost != null ? fmtMoney2.format(r.cost) : EM_DASH}</td>
        <td class="text-end" data-column="profit">${r.profit != null ? fmtMoney2.format(r.profit) : EM_DASH}</td>
        <td class="text-end" data-column="profit_current">${r.profit_current != null ? fmtMoney2.format(r.profit_current) : EM_DASH}</td>
        <td class="text-end" data-column="profit_prior">${r.profit_prior != null ? fmtMoney2.format(r.profit_prior) : EM_DASH}</td>
        <td class="text-end" data-column="profit_delta">${formatSignedMoney(r.profit_delta)}</td>
        <td class="text-end" data-column="profit_share">${r.profit_share != null ? `${fmtPct1.format(r.profit_share)}%` : EM_DASH}</td>
        <td class="text-end" data-column="contribution_margin_lb">${r.contribution_margin_lb != null ? fmtMoney2.format(r.contribution_margin_lb) : EM_DASH}</td>
        <td class="text-end" data-column="asp_lb">${r.asp_lb != null ? fmtMoney2.format(r.asp_lb) : EM_DASH}</td>
        <td class="text-end" data-column="cost_lb">${r.cost_lb != null ? fmtMoney2.format(r.cost_lb) : EM_DASH}</td>
        <td class="text-end" data-column="margin_pct">${r.margin_pct != null ? `${fmtPct1.format(r.margin_pct)}%` : EM_DASH}</td>
        <td class="text-end" data-column="margin_pct_prior">${r.margin_pct_prior != null ? `${fmtPct1.format(r.margin_pct_prior)}%` : EM_DASH}</td>
        <td class="text-end" data-column="margin_delta_pp">${r.margin_delta_pp != null ? `${r.margin_delta_pp > 0 ? "+" : ""}${fmtPct1.format(r.margin_delta_pp)} pp` : EM_DASH}</td>
        <td class="text-end" data-column="price_variance_vs_median">${r.price_variance_vs_median != null ? fmtMoney2.format(r.price_variance_vs_median) : EM_DASH}</td>
        <td class="text-end" data-column="volatility_score">${r.volatility_score != null ? `${fmtPct1.format(r.volatility_score)}%` : EM_DASH}</td>
        <td data-column="margin_risk">${renderRiskBadge(r.margin_risk)}</td>
        <td data-column="recommendation">${renderRecommendationBadge(r.recommendation || r.quick_rec || "Review")}</td>
        <td data-column="first_sold">${escapeHtml(r.first_sold || EM_DASH)}</td>
        <td data-column="last_sold">${escapeHtml(r.last_sold || EM_DASH)}</td>
        <td data-column="quick_rec">${escapeHtml(r.quick_rec || EM_DASH)}</td>
        <td class="text-center"><a class="btn btn-sm btn-outline-primary intel-btn" href="${link}" data-link="${link}" data-sku="${escapeHtml(sku)}">Intel</a></td>
      `;
      tr.addEventListener("click", (evt) => {
        if (evt.target.closest("a,button,input,select,label")) return;
        window.location.href = link;
      });
      tbody.appendChild(tr);
    });
    applyColumnVisibility();
    if (statusEl) {
      const quick = state.quickFilters?.length ? ` ${MIDDLE_DOT} ${state.quickFilters.length} quick filter${state.quickFilters.length > 1 ? "s" : ""}` : "";
      statusEl.textContent = `Page ${table.page || 1} ${MIDDLE_DOT} ${rows.length} rows (of ${table.total ?? rows.length})${quick}`;
    }
  };

  const renderTable = (table = {}) => {
    const tbody = document.getElementById("productTbody");
    const statusEl = document.getElementById("tableStatus");
    if (!tbody) return;
    tbody.innerHTML = "";
    const rows = table.rows || [];
    if (!rows.length) {
      const colspan = isV4 ? 45 : (isV3 ? 34 : (isV2 ? 24 : 18));
      tbody.innerHTML = `<tr><td colspan="${colspan}" class="text-center text-muted">No data for current filters.</td></tr>`;
      if (isV2) applyColumnVisibility();
      if (statusEl) statusEl.textContent = "0 rows";
      return;
    }
    if (isV2) renderTableV2(tbody, rows, table, statusEl);
    else renderTableV1(tbody, rows, table, statusEl);
    const prev = document.getElementById("tablePrev");
    const next = document.getElementById("tableNext");
    if (prev) prev.disabled = (table.page || 1) <= 1;
    if (next) next.disabled = (table.page || 1) * (table.page_size || state.pageSize) >= (table.total || 0);
    removeSkeleton("productTbody");
  };

  // ---------- Fetch + orchestrate ----------
  const fetchBundle = async () => {
    const reqId = ++currentReqId;
    if (currentAbort) currentAbort.abort();
    const controller = new AbortController();
    currentAbort = controller;
    const qs = buildQS();
    state.qs = qs;
    replaceHistory(qs);
    const url = `${bundleUrl}?${qs}`;
    const box = document.getElementById("productsError");
    if (box) box.classList.add("d-none");
    try {
      const res = await authFetch(url, { signal: controller.signal, credentials: "same-origin", headers: { Accept: "application/json" } });
      const raw = await res.json();
      if (reqId !== currentReqId) return;
      const payload = window.normalizeBundlePayload ? window.normalizeBundlePayload(raw) : raw;
      if (!res.ok) throw new Error(payload?.error?.message || `HTTP ${res.status}`);
      lastPayload = payload;

      renderHero(payload.kpis || {}, payload.meta || {}, payload.comparison || {});
      renderComparisonContext(payload.comparison || {}, payload.story || {});
      renderActiveFilterSummary();
      renderSectionBriefs(payload);
      renderPortfolioPosture(payload.portfolio_posture || {}, payload.focus_actions || []);
      renderDecisionSignals(payload.decision_signals || []);
      renderFocusActions(payload.focus_actions || []);
      renderKpis(payload.kpis || {});
      bindKpiCards();
      renderVelocity(payload.velocity || {});
      renderInsights(payload.insights || [], payload.projected_next_month || null, payload.comparison || {});
      bindInsightCards();
      renderAISignals(payload.ai_signals || {});

      const chartsPayload = payload.charts || {};
      renderStrategyBrief(chartsPayload.segments || {}, payload.concentration || {});
      renderTrajectory(chartsPayload.trajectory || {}, payload.forecast_overlay || [], payload.comparison || {});
      renderPriceVelocity(payload.price_vs_velocity || chartsPayload.price_velocity || []);
      renderPerformanceBubble(payload.performance_bubble || {});
      renderPriceDist(chartsPayload.unit_price_dist || []);
      renderMovers(chartsPayload.movers || []);
      renderTopProducts(chartsPayload.top_products || []);
      renderPareto(chartsPayload.pareto || []);
      const segments = chartsPayload.segments || {};
      renderSegmentSummary(segments.summary || []);
      renderSegmentMovers(segments.movers || []);
      renderSegmentMixShift(segments.mix_shift || []);
      renderRecommendations(payload.recommendations || []);
      renderHealthMatrix(payload.health_matrix || {});
      renderRiskOpportunity(payload.concentration || {}, payload.risk_opportunity || {});
      renderPricingGuardrails(payload.pricing_guardrails || {});
      renderExecutionLists(payload.execution_lists || {});
      renderTable(payload.table || {});
      applyWorkspaceSettings();
      syncWatchlistButtons();
      syncQuickFilterButtons();
      syncExportLinks();
      hydrateTooltips(document);

      if (payload.meta?.cached !== undefined) {
        console.debug("[products bundle]", {
          cached: payload.meta.cached,
          duckdb_query_count: payload.meta.duckdb_query_count,
          duckdb_ms: payload.meta.duckdb_ms,
          total_ms: payload.meta.total_ms || payload.meta.duration_ms,
          dataset_version: payload.meta.dataset_version,
        });
      }
    } catch (err) {
      if (err?.name === "AbortError") return;
      if (reqId !== currentReqId) return;
      console.error("products bundle failed", err);
      if (box) {
        box.classList.remove("d-none");
        box.textContent = err?.message || "Unable to load products.";
      }
    } finally {
      if (reqId === currentReqId) {
        try {
          window.dispatchEvent(new CustomEvent("globalFilters:applied", { detail: { qs: state.qs } }));
        } catch (err) {
          /* ignore */
        }
      }
    }
  };

  // ---------- Drilldown modal ----------
  const ensureIntelModal = () => {
    if (document.getElementById("intelModal")) return;
    const modal = document.createElement("div");
    modal.innerHTML = `
      <div class="modal fade" id="intelModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-lg modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title" id="intelTitle">Product Intel</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
              <div id="intelBody">Loading${ELLIPSIS}</div>
            </div>
          </div>
        </div>
      </div>`;
    document.body.appendChild(modal.firstElementChild);
  };

  const renderIntelModal = (payload) => {
    ensureIntelModal();
    const body = document.getElementById("intelBody");
    const title = document.getElementById("intelTitle");
    if (!body || !title) return;
    const k = payload.kpis || {};
    const entityName = payload.meta?.entity_display_name || payload.meta?.entity_label || payload.meta?.entity_id || k.product_id || "Product";
    title.textContent = `Intel ${EM_DASH} ${entityName}`;
    const rows = (payload.table && payload.table.rows) || [];
    const list = rows
      .map(
        (r) =>
          `<tr><td>${r.label || r.key}</td><td class="text-end">${fmtMoney0.format(r.revenue || 0)}</td><td class="text-end">${fmtInt.format(
            r.qty || 0
          )}</td></tr>`
      )
      .join("");
    body.innerHTML = `
      <div class="row g-2 mb-3">
        <div class="col-6"><div class="mini-kpi-label">Revenue</div><div class="mini-kpi-value">${fmtMoney0.format(k.revenue || 0)}</div></div>
        <div class="col-6"><div class="mini-kpi-label">Quantity</div><div class="mini-kpi-value">${fmtInt.format(k.qty || 0)}</div></div>
        <div class="col-6"><div class="mini-kpi-label">Customers</div><div class="mini-kpi-value">${fmtInt.format(k.customers || 0)}</div></div>
        <div class="col-6"><div class="mini-kpi-label">Orders</div><div class="mini-kpi-value">${fmtInt.format(k.orders || 0)}</div></div>
      </div>
      <h6 class="mt-2">Top customers</h6>
      <div class="table-responsive">
        <table class="table table-sm">
          <thead><tr><th>Customer</th><th class="text-end">Revenue</th><th class="text-end">Qty</th></tr></thead>
          <tbody>${list || '<tr><td colspan="3" class="text-muted text-center">No customer data</td></tr>'}</tbody>
        </table>
      </div>
    `;
    try {
      const modal = bootstrap.Modal.getOrCreateInstance(document.getElementById("intelModal"));
      modal.show();
    } catch (err) {
      console.error("intel modal", err);
    }
  };

  const fetchDrilldown = async (sku, fallbackLink) => {
    if (!sku) {
      if (fallbackLink) window.location.href = fallbackLink;
      return;
    }
    ensureIntelModal();
    const body = document.getElementById("intelBody");
    if (body) body.textContent = `Loading${ELLIPSIS}`;
    const qs = state.qs ? `${state.qs.replace(/^[?]/, "")}&` : "";
    const url = `/api/products/drilldown/bundle?sku=${encodeURIComponent(sku)}${qs}`;
    try {
    const res = await authFetch(url, { headers: { Accept: "application/json" }, credentials: "same-origin" });
      const payload = await res.json();
      if (!res.ok) throw new Error(payload?.error?.message || `HTTP ${res.status}`);
      renderIntelModal(payload);
    } catch (err) {
      console.error("drilldown fetch failed", err);
      if (fallbackLink) window.location.href = fallbackLink;
    }
  };

  // ---------- Event wiring ----------
  const wireSorting = () => {
    document.querySelectorAll("#productTable th.sortable").forEach((th) => {
      th.addEventListener("click", () => {
        const key = th.dataset.key || "revenue";
        if (state.sortBy === key) {
          state.sortDir = state.sortDir === "asc" ? "desc" : "asc";
        } else {
          state.sortBy = key;
          state.sortDir = "desc";
        }
        state.page = 1;
        fetchBundle();
        document.querySelectorAll("#productTable th.sortable").forEach((t) => t.classList.remove("asc", "desc"));
        th.classList.add(state.sortDir);
      });
    });
  };

  const wireControls = () => {
    if (isV4) {
      document.getElementById("workspaceModeExecutive")?.addEventListener("click", () => {
        state.workspaceMode = "executive";
        applyWorkspaceSettings();
      });
      document.getElementById("workspaceModeAnalyst")?.addEventListener("click", () => {
        state.workspaceMode = "analyst";
        applyWorkspaceSettings();
      });
      document.getElementById("workspaceDensityComfortable")?.addEventListener("click", () => {
        state.workspaceDensity = "comfortable";
        applyWorkspaceSettings();
      });
      document.getElementById("workspaceDensityCompact")?.addEventListener("click", () => {
        state.workspaceDensity = "compact";
        applyWorkspaceSettings();
      });
      document.getElementById("workspaceEmphasis")?.addEventListener("change", (evt) => {
        applyEmphasisPreset(evt.target.value);
      });
      document.querySelectorAll("[data-section-toggle]").forEach((input) => {
        input.addEventListener("change", (evt) => {
          const key = evt.target.getAttribute("data-section-toggle");
          if (!key) return;
          const next = new Set(state.visibleSections || []);
          if (evt.target.checked) next.add(key);
          else next.delete(key);
          state.visibleSections = WORKSPACE_SECTION_KEYS.filter((sectionKey) => next.has(sectionKey));
          applyWorkspaceSettings();
        });
      });
      document.querySelectorAll("[data-watchlist-preset]").forEach((btn) => {
        btn.addEventListener("click", () => {
          applyWatchlistPreset(btn.getAttribute("data-watchlist-preset") || "");
        });
      });
    }

    const searchEl = document.getElementById("tableSearch");
    if (searchEl) {
      let timer = null;
      searchEl.addEventListener("input", (e) => {
        clearTimeout(timer);
        timer = setTimeout(() => {
          state.search = e.target.value.trim();
          state.page = 1;
          fetchBundle();
        }, 300);
      });
    }

    const pageSizeEl = document.getElementById("tablePageSize");
    if (pageSizeEl) {
      pageSizeEl.addEventListener("change", (e) => {
        state.pageSize = Number(e.target.value || 25);
        state.page = 1;
        fetchBundle();
      });
    }

    const prev = document.getElementById("tablePrev");
    const next = document.getElementById("tableNext");
    if (prev) prev.addEventListener("click", () => { state.page = Math.max(1, state.page - 1); fetchBundle(); });
    if (next) next.addEventListener("click", () => { state.page += 1; fetchBundle(); });

    const topMetric = document.getElementById("topMetric");
    const topN = document.getElementById("topN");
    [topMetric, topN].forEach((el) => el && el.addEventListener("change", () => renderTopProducts(lastPayload?.charts?.top_products || [])));
    const moversMetric = document.getElementById("moversMetric");
    if (moversMetric) {
      moversMetric.addEventListener("change", () => renderMovers(lastPayload?.charts?.movers || []));
    }

    const segmentSelect = document.getElementById("segmentFilter");
    if (segmentSelect) {
      segmentSelect.addEventListener("change", () => {
        const chosen = Array.from(segmentSelect.selectedOptions || []).map((o) => o.value).filter(Boolean);
        state.segments = chosen;
        state.page = 1;
        fetchBundle();
      });
    }

    if (isV2) {
      document.querySelectorAll("#tableQuickFilters [data-quick-filter]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const key = btn.getAttribute("data-quick-filter");
          if (!key) return;
          const next = new Set(state.quickFilters || []);
          if (next.has(key)) next.delete(key);
          else next.add(key);
          state.quickFilters = Array.from(next);
          state.page = 1;
          syncQuickFilterButtons();
          syncWatchlistButtons();
          fetchBundle();
        });
      });
      document.querySelectorAll("#columnGroups [data-col-group]").forEach((btn) => {
        btn.addEventListener("click", () => {
          const group = btn.getAttribute("data-col-group");
          if (!group) return;
          applyColumnGroup(group);
          document.querySelectorAll("#columnGroups [data-col-group]").forEach((chip) => {
            chip.classList.toggle("active", chip.getAttribute("data-col-group") === group);
          });
        });
      });
    }

    const forecastToggle = document.getElementById("toggleForecast");
    if (forecastToggle) {
      forecastToggle.addEventListener("change", (e) => {
        state.showForecast = Boolean(e.target.checked);
        fetchBundle();
      });
    }

    const bubbleTop = document.getElementById("bubbleTopN");
    const bubbleColor = document.getElementById("bubbleColorBy");
    const bubbleY = document.getElementById("bubbleYMetric");
    const bubbleReset = document.getElementById("bubbleResetZoom");
    const bubbleInclude = document.getElementById("bubbleIncludeMissing");
    [bubbleTop, bubbleColor, bubbleY].forEach((el) =>
      el &&
      el.addEventListener("change", (e) => {
        const id = e.target.id;
        if (id === "bubbleTopN") state.bubbleTopN = e.target.value;
        if (id === "bubbleColorBy") state.bubbleColorBy = e.target.value;
        if (id === "bubbleYMetric") state.bubbleYMetric = e.target.value;
        renderPerformanceBubble(lastPayload?.performance_bubble || {});
      })
    );
    if (bubbleInclude) {
      bubbleInclude.addEventListener("change", () => renderPerformanceBubble(lastPayload?.performance_bubble || {}));
    }
    if (bubbleReset) {
      bubbleReset.addEventListener("click", () => {
        renderPerformanceBubble(lastPayload?.performance_bubble || {});
      });
    }

    document.getElementById("productIntelFocusTable")?.addEventListener("click", () => {
      const sku = getSku(activeProductIntel?.row);
      if (!sku) return;
      applyDetailView({ search: sku, section: "table", mode: "analyst" });
    });
    document.getElementById("productIntelOpenDrilldown")?.addEventListener("click", (evt) => {
      if (!evt.currentTarget.classList.contains("disabled")) return;
      evt.preventDefault();
    });
    document.getElementById("productIntelApplyAction")?.addEventListener("click", () => {
      const view = activeProductIntel?.suggestedAction?.view;
      if (!view) return;
      applySignalAction(view);
    });
  };

  const replaceHistory = (qs) => {
    if (!window.history || typeof window.history.replaceState !== "function") return;
    const nextUrl = qs ? `${window.location.pathname}?${qs}` : window.location.pathname;
    window.history.replaceState({}, "", nextUrl);
  };

  const triggerFetch = () => {
    fetchBundle();
  };

  const applyFilters = (qs) => {
    state.qs = qs || "";
    state.page = 1;
    syncStateFromQS(state.qs);
    replaceHistory(state.qs);
    triggerFetch();
  };

  const resolveInitialQS = () => {
    if (state.qs) return state.qs;
    try {
      if (window.getGlobalFilterState) {
        const gs = window.getGlobalFilterState();
        if (gs?.qs) return gs.qs;
      }
    } catch (err) { /* noop */ }
    try {
      if (window.FilterState && typeof window.FilterState.get === "function" && typeof window.FilterState.toQueryString === "function") {
        const filters = window.FilterState.get();
        const qs = window.FilterState.toQueryString(filters);
        if (qs) return qs;
      }
    } catch (err) { /* noop */ }
    return window.location.search ? window.location.search.replace(/^\?/, "") : "";
  };

  const syncFiltersFromState = () => {
    if (state.qs) return;
    state.qs = resolveInitialQS();
  };

  const bootstrap = async (qsHint) => {
    if (hasBootstrapped) return;
    hasBootstrapped = true;
    let qs = qsHint || "";
    if (!qs) {
      const readyDetail = await waitForFiltersReady();
      qs = (readyDetail && readyDetail.qs) || "";
    }
    if (qs) {
      state.qs = qs;
      syncStateFromQS(state.qs);
      replaceHistory(qs);
    } else {
      syncFiltersFromState();
      syncStateFromQS(state.qs);
    }
    triggerFetch();
  };

  const onApply = (evt) => {
    const qs = (evt?.detail && evt.detail.qs) || "";
    applyFilters(qs);
  };

  const onReady = (evt) => {
    const qs = (evt?.detail && evt.detail.qs) || "";
    bootstrap(qs);
  };

  window.addEventListener("globalFilters:apply", onApply);
  window.addEventListener("globalFilters:ready", onReady);

  wireSorting();
  wireControls();
  renderColumnChooser();
  initV2Help();
  applyWorkspaceSettings();
  if (isV4) applyEmphasisPreset(state.workspaceEmphasis);
  syncWatchlistButtons();
  syncQuickFilterButtons();
  syncExportLinks();
  // Intel buttons use plain navigation via their hrefs.

  // Boot when filters are already ready (or fall back after delay).
  bootstrap();
  setTimeout(() => {
    if (!hasBootstrapped) bootstrap(resolveInitialQS());
  }, 900);
})();
