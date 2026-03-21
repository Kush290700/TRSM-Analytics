(function () {
  const root = document.getElementById("LaborPage");
  const dataNode = document.getElementById("LaborPageData");
  if (!root || !dataNode) return;

  let payload = {};
  try {
    payload = JSON.parse(dataNode.textContent || "{}");
  } catch (_err) {
    payload = {};
  }

  const filters = (payload && payload.filters) || {};

  function number(value) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  function hasRows(rows) {
    return Array.isArray(rows) && rows.length > 0;
  }

  function renderEmpty(target, message) {
    if (!target) return;
    target.innerHTML = `<div class="labor-empty">${message}</div>`;
  }

  function updateUrl(mutator) {
    const url = new URL(window.location.href);
    const params = url.searchParams;
    mutator(params);
    window.location.assign(url.toString());
  }

  function applyFilters(updates, clearKeys = []) {
    updateUrl((params) => {
      params.delete("page");
      clearKeys.forEach((key) => params.delete(key));
      Object.entries(updates || {}).forEach(([key, value]) => {
        params.delete(key);
        if (Array.isArray(value)) {
          value.filter((item) => item !== null && item !== undefined && item !== "").forEach((item) => params.append(key, String(item)));
          return;
        }
        if (value !== null && value !== undefined && value !== "") {
          params.append(key, String(value));
        }
      });
    });
  }

  function setSingleFilter(key, value) {
    applyFilters({ [key]: value });
  }

  function setComboFilter(department, category) {
    applyFilters({ department, time_category: category }, ["department", "time_category"]);
  }

  function setDateWindow(start, end) {
    applyFilters({ start, end });
  }

  function setSort(sortKey) {
    updateUrl((params) => {
      const currentSort = params.get("sort") || filters.sort_by || "labor_cost";
      const currentDir = params.get("sort_dir") || filters.sort_dir || "desc";
      const nextDir = currentSort === sortKey && currentDir === "desc" ? "asc" : "desc";
      params.set("sort", sortKey);
      params.set("sort_dir", nextDir);
      params.delete("page");
    });
  }

  function setPage(page) {
    if (!page || page < 1) return;
    updateUrl((params) => {
      params.set("page", String(page));
    });
  }

  function bindInteractions() {
    document.addEventListener("click", (event) => {
      const filterTarget = event.target.closest(".js-filter-link");
      if (filterTarget) {
        event.preventDefault();
        const key = filterTarget.getAttribute("data-param");
        const value = filterTarget.getAttribute("data-value");
        if (key && value) setSingleFilter(key, value);
        return;
      }

      const comboTarget = event.target.closest(".js-filter-combo");
      if (comboTarget) {
        event.preventDefault();
        setComboFilter(comboTarget.getAttribute("data-department"), comboTarget.getAttribute("data-category"));
        return;
      }

      const sortTarget = event.target.closest(".js-sort");
      if (sortTarget) {
        event.preventDefault();
        const sortKey = sortTarget.getAttribute("data-sort");
        if (sortKey) setSort(sortKey);
        return;
      }

      const pageTarget = event.target.closest(".js-page");
      if (pageTarget) {
        event.preventDefault();
        const page = Number(pageTarget.getAttribute("data-page") || "0");
        if (page > 0) setPage(page);
      }
    });
  }

  function axisConfig(format) {
    if (format === "currency") return { tickprefix: "$", gridcolor: "#e8eff3" };
    if (format === "percent") return { ticksuffix: "%", gridcolor: "#e8eff3" };
    return { gridcolor: "#e8eff3" };
  }

  function renderBarChart(
    targetId,
    rows,
    { valueKey, labelKey, clickKey = null, clickParam = null, color = "#0f766e", orientation = "h", format = "number", multiplier = 1 } = {}
  ) {
    const target = document.getElementById(targetId);
    if (!target || !window.Plotly) return;
    if (!hasRows(rows)) {
      renderEmpty(target, "No data for this chart.");
      return;
    }

    const dataRows = rows.slice();
    const labels = dataRows.map((row) => row[labelKey] || "Unknown");
    const values = dataRows.map((row) => number(row[valueKey]) * multiplier);
    const customdata = dataRows.map((row) => row[clickKey || labelKey] || "Unknown");
    const reversed = orientation === "h";
    const x = reversed ? values.slice().reverse() : labels;
    const y = reversed ? labels.slice().reverse() : values;
    const custom = reversed ? customdata.slice().reverse() : customdata;

    Plotly.newPlot(
      target,
      [
        {
          type: "bar",
          orientation,
          x,
          y,
          customdata: custom,
          marker: { color, line: { color: "rgba(13, 38, 45, 0.12)", width: 1 } },
          hovertemplate:
            orientation === "h"
              ? "%{y}<br>%{x:,.2f}<extra></extra>"
              : "%{x}<br>%{y:,.2f}<extra></extra>",
        },
      ],
      {
        margin: orientation === "h" ? { l: 170, r: 20, t: 14, b: 36 } : { l: 50, r: 20, t: 14, b: 90 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        xaxis: orientation === "h" ? axisConfig(format) : { tickangle: -28 },
        yaxis: orientation === "h" ? { automargin: true } : axisConfig(format),
      },
      { displayModeBar: false, responsive: true }
    );

    if (clickParam) {
      target.on("plotly_click", (event) => {
        const point = event.points && event.points[0];
        if (!point || !point.customdata) return;
        setSingleFilter(clickParam, point.customdata);
      });
    }
  }

  function renderGroupedShareChart(targetId, rows, labelKey, clickParam, clickKey = null) {
    const target = document.getElementById(targetId);
    if (!target || !window.Plotly) return;
    if (!hasRows(rows)) {
      renderEmpty(target, "No risk rows for this chart.");
      return;
    }
    const limited = rows.slice(0, 12);
    Plotly.newPlot(
      target,
      [
        {
          type: "bar",
          x: limited.map((row) => row[labelKey] || "Unknown"),
          y: limited.map((row) => number(row.premium_share_pct) * 100),
          name: "Premium %",
          customdata: limited.map((row) => row[clickKey || labelKey] || "Unknown"),
          marker: { color: "#bf6d1d" },
          hovertemplate: "%{x}<br>Premium %{y:.1f}%<extra></extra>",
        },
        {
          type: "bar",
          x: limited.map((row) => row[labelKey] || "Unknown"),
          y: limited.map((row) => number(row.absence_share_pct) * 100),
          name: "Absence %",
          customdata: limited.map((row) => row[clickKey || labelKey] || "Unknown"),
          marker: { color: "#b53a2b" },
          hovertemplate: "%{x}<br>Absence %{y:.1f}%<extra></extra>",
        },
      ],
      {
        barmode: "group",
        margin: { l: 50, r: 20, t: 14, b: 90 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        xaxis: { tickangle: -28 },
        yaxis: axisConfig("percent"),
        legend: { orientation: "h" },
      },
      { displayModeBar: false, responsive: true }
    );
    if (clickParam) {
      target.on("plotly_click", (event) => {
        const point = event.points && event.points[0];
        if (!point || !point.customdata) return;
        setSingleFilter(clickParam, point.customdata);
      });
    }
  }

  function renderScatterChart(targetId, rows) {
    const target = document.getElementById(targetId);
    if (!target || !window.Plotly) return;
    if (!hasRows(rows)) {
      renderEmpty(target, "No department comparison is available.");
      return;
    }

    const sized = rows.map((row) => Math.max(12, Math.min(34, number(row.active_employee_count) * 4 || 14)));
    Plotly.newPlot(
      target,
      [
        {
          type: "scatter",
          mode: "markers+text",
          x: rows.map((row) => number(row.paid_hours)),
          y: rows.map((row) => number(row.labor_cost)),
          text: rows.map((row) => row.department_name || "Unknown"),
          textposition: "top center",
          customdata: rows.map((row) => row.department_name || "Unknown"),
          marker: {
            size: sized,
            color: rows.map((row) => number(row.blended_rate)),
            colorscale: "Tealgrn",
            line: { color: "rgba(12, 39, 45, 0.15)", width: 1 },
            showscale: false,
          },
          hovertemplate: "%{text}<br>Hours %{x:,.1f}<br>Cost %{y:$,.2f}<extra></extra>",
        },
      ],
      {
        margin: { l: 60, r: 20, t: 14, b: 46 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        xaxis: { title: "Paid Hours", gridcolor: "#e8eff3" },
        yaxis: { title: "Labor Cost", tickprefix: "$", gridcolor: "#e8eff3" },
      },
      { displayModeBar: false, responsive: true }
    );
    target.on("plotly_click", (event) => {
      const point = event.points && event.points[0];
      if (!point || !point.customdata) return;
      setSingleFilter("department", point.customdata);
    });
  }

  function renderTrendChart(targetId, rows) {
    const target = document.getElementById(targetId);
    if (!target || !window.Plotly) return;
    if (!hasRows(rows)) {
      renderEmpty(target, "No trend data for the active filters.");
      return;
    }

    const dates = rows.map((row) => row.labor_date);
    Plotly.newPlot(
      target,
      [
        {
          type: "scatter",
          mode: "lines+markers",
          name: "Labor Cost",
          x: dates,
          y: rows.map((row) => number(row.labor_cost)),
          customdata: dates,
          line: { color: "#0f766e", width: 3 },
          hovertemplate: "%{x}<br>Cost %{y:$,.2f}<extra></extra>",
        },
        {
          type: "scatter",
          mode: "lines",
          name: "Paid Hours",
          x: dates,
          y: rows.map((row) => number(row.paid_hours)),
          yaxis: "y2",
          line: { color: "#c98a2a", width: 2 },
          hovertemplate: "%{x}<br>Hours %{y:,.1f}<extra></extra>",
        },
        {
          type: "scatter",
          mode: "lines",
          name: "Premium Cost",
          x: dates,
          y: rows.map((row) => number(row.premium_cost)),
          line: { color: "#bf6d1d", width: 1.5, dash: "dot" },
          hovertemplate: "%{x}<br>Premium %{y:$,.2f}<extra></extra>",
        },
        {
          type: "scatter",
          mode: "lines",
          name: "Absence Cost",
          x: dates,
          y: rows.map((row) => number(row.absence_cost)),
          line: { color: "#b53a2b", width: 1.5, dash: "dash" },
          hovertemplate: "%{x}<br>Absence %{y:$,.2f}<extra></extra>",
        },
      ],
      {
        margin: { l: 58, r: 58, t: 14, b: 42 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        xaxis: { gridcolor: "#e8eff3" },
        yaxis: { title: "Cost", tickprefix: "$", gridcolor: "#e8eff3" },
        yaxis2: { title: "Hours", overlaying: "y", side: "right", showgrid: false },
        legend: { orientation: "h" },
      },
      { displayModeBar: false, responsive: true }
    );
    target.on("plotly_click", (event) => {
      const point = event.points && event.points[0];
      if (!point || !point.customdata) return;
      setDateWindow(point.customdata, point.customdata);
    });
  }

  function renderGroupedLineChart(targetId, rows, { groupKey, dateKey, valueKey, clickParam = null, format = "currency" } = {}) {
    const target = document.getElementById(targetId);
    if (!target || !window.Plotly) return;
    if (!hasRows(rows)) {
      renderEmpty(target, "No grouped trend is available.");
      return;
    }

    const groups = {};
    rows.forEach((row) => {
      const key = row[groupKey] || "Unknown";
      groups[key] = groups[key] || [];
      groups[key].push(row);
    });

    const traces = Object.entries(groups).map(([name, points]) => ({
      type: "scatter",
      mode: "lines+markers",
      name,
      x: points.map((row) => row[dateKey]),
      y: points.map((row) => number(row[valueKey])),
      customdata: points.map(() => name),
      hovertemplate:
        format === "currency"
          ? `${name}<br>%{x}<br>%{y:$,.2f}<extra></extra>`
          : `${name}<br>%{x}<br>%{y:,.1f}<extra></extra>`,
    }));

    Plotly.newPlot(
      target,
      traces,
      {
        margin: { l: 58, r: 20, t: 14, b: 42 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        xaxis: { gridcolor: "#e8eff3" },
        yaxis: format === "currency" ? { tickprefix: "$", gridcolor: "#e8eff3" } : { gridcolor: "#e8eff3" },
        legend: { orientation: "h" },
      },
      { displayModeBar: false, responsive: true }
    );

    if (clickParam) {
      target.on("plotly_click", (event) => {
        const point = event.points && event.points[0];
        if (!point || !point.data || !point.data.name) return;
        setSingleFilter(clickParam, point.data.name);
      });
    }
  }

  function renderWeekdayChart(targetId, rows) {
    const target = document.getElementById(targetId);
    if (!target || !window.Plotly) return;
    if (!hasRows(rows)) {
      renderEmpty(target, "No weekday pattern is available.");
      return;
    }

    Plotly.newPlot(
      target,
      [
        {
          type: "bar",
          x: rows.map((row) => row.weekday_name),
          y: rows.map((row) => number(row.avg_daily_labor_cost)),
          marker: { color: "#2c8b84" },
          hovertemplate: "%{x}<br>Avg daily cost %{y:$,.2f}<extra></extra>",
        },
      ],
      {
        margin: { l: 50, r: 20, t: 14, b: 40 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        yaxis: { tickprefix: "$", gridcolor: "#e8eff3" },
      },
      { displayModeBar: false, responsive: true }
    );
  }

  function renderPieChart(targetId, rows, { labelKey, valueKey, clickParam = null } = {}) {
    const target = document.getElementById(targetId);
    if (!target || !window.Plotly) return;
    if (!hasRows(rows)) {
      renderEmpty(target, "No category mix is available.");
      return;
    }

    Plotly.newPlot(
      target,
      [
        {
          type: "pie",
          labels: rows.map((row) => row[labelKey] || "Unknown"),
          values: rows.map((row) => number(row[valueKey])),
          customdata: rows.map((row) => row[labelKey] || "Unknown"),
          hole: 0.48,
          hovertemplate: "%{label}<br>%{value:$,.2f}<br>%{percent}<extra></extra>",
        },
      ],
      {
        margin: { l: 20, r: 20, t: 14, b: 14 },
        paper_bgcolor: "transparent",
      },
      { displayModeBar: false, responsive: true }
    );

    if (clickParam) {
      target.on("plotly_click", (event) => {
        const point = event.points && event.points[0];
        if (!point || !point.customdata) return;
        setSingleFilter(clickParam, point.customdata);
      });
    }
  }

  function renderMonthlyPatternChart(targetId, rows) {
    const target = document.getElementById(targetId);
    if (!target || !window.Plotly) return;
    if (!hasRows(rows)) {
      renderEmpty(target, "No monthly pattern is available.");
      return;
    }

    Plotly.newPlot(
      target,
      [
        {
          type: "scatter",
          mode: "lines+markers",
          name: "Labor Cost",
          x: rows.map((row) => row.labor_month),
          y: rows.map((row) => number(row.labor_cost)),
          line: { color: "#0f766e", width: 3 },
          hovertemplate: "%{x}<br>Cost %{y:$,.2f}<extra></extra>",
        },
        {
          type: "scatter",
          mode: "lines+markers",
          name: "Paid Hours",
          x: rows.map((row) => row.labor_month),
          y: rows.map((row) => number(row.paid_hours)),
          yaxis: "y2",
          line: { color: "#c98a2a", width: 2 },
          hovertemplate: "%{x}<br>Hours %{y:,.1f}<extra></extra>",
        },
      ],
      {
        margin: { l: 52, r: 52, t: 14, b: 40 },
        paper_bgcolor: "transparent",
        plot_bgcolor: "transparent",
        xaxis: { gridcolor: "#e8eff3" },
        yaxis: { tickprefix: "$", gridcolor: "#e8eff3" },
        yaxis2: { overlaying: "y", side: "right", showgrid: false },
        legend: { orientation: "h" },
      },
      { displayModeBar: false, responsive: true }
    );
  }

  function renderCharts() {
    const charts = (payload && payload.charts) || {};
    const focus = (payload && payload.focus) || {};

    renderBarChart("laborDeptCostChart", charts.department_cost || [], {
      valueKey: "labor_cost",
      labelKey: "department_name",
      clickKey: "department_name",
      clickParam: "department",
      color: "#0f766e",
      format: "currency",
    });
    renderScatterChart("laborDeptScatterChart", charts.department_scatter || []);
    renderBarChart("laborDeptRateChart", charts.department_rate || [], {
      valueKey: "blended_rate",
      labelKey: "department_name",
      clickKey: "department_name",
      clickParam: "department",
      color: "#2f6fce",
      format: "currency",
    });
    renderGroupedShareChart("laborDeptRiskChart", charts.department_cost || [], "department_name", "department");
    renderBarChart("laborDeptVolatilityChart", charts.department_volatility || [], {
      valueKey: "cost_volatility",
      labelKey: "department_name",
      clickKey: "department_name",
      clickParam: "department",
      color: "#8b5cf6",
      format: "percent",
      multiplier: 100,
    });

    renderTrendChart("laborDepartmentFocusTrendChart", ((focus.department || {}).trend_rows) || []);
    renderPieChart("laborCategoryMixChart", charts.category_mix || [], {
      labelKey: "time_category",
      valueKey: "labor_cost",
      clickParam: "time_category",
    });
    renderGroupedLineChart("laborCategoryTrendChart", charts.category_trend || [], {
      groupKey: "time_category",
      dateKey: "labor_date",
      valueKey: "labor_cost",
      clickParam: "time_category",
      format: "currency",
    });
    renderTrendChart("laborCategoryFocusTrendChart", ((focus.category || {}).trend_rows) || []);

    renderBarChart("laborWorkerCostChart", charts.worker_cost || [], {
      valueKey: "labor_cost",
      labelKey: "employee_name",
      clickKey: "employee_code",
      clickParam: "employee",
      color: "#0f766e",
      format: "currency",
    });
    renderBarChart("laborWorkerHoursChart", charts.worker_hours || [], {
      valueKey: "paid_hours",
      labelKey: "employee_name",
      clickKey: "employee_code",
      clickParam: "employee",
      color: "#c98a2a",
      format: "number",
    });
    renderGroupedShareChart("laborWorkerRiskChart", charts.worker_cost || [], "employee_name", "employee", "employee_code");
    renderTrendChart("laborWorkerFocusTrendChart", ((focus.worker || {}).trend_rows) || []);

    renderTrendChart("laborTrendChart", charts.daily_trend || []);
    renderWeekdayChart("laborWeekdayChart", charts.weekday_pattern || []);
    renderMonthlyPatternChart("laborMonthlyPatternChart", charts.monthly_pattern || []);
    renderGroupedLineChart("laborDeptTrendChart", charts.monthly_department_trend || [], {
      groupKey: "department_name",
      dateKey: "labor_month",
      valueKey: "labor_cost",
      clickParam: "department",
      format: "currency",
    });
  }

  bindInteractions();
  renderCharts();
})();
