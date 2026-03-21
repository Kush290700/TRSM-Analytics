from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from calendar import monthrange
from typing import Any, Iterable, Optional

from app.services.filters import FilterParams


EPSILON = 1e-9


@dataclass(frozen=True)
class WindowContract:
    current_start: date
    current_end: date
    prior_month_start: date
    prior_month_end: date
    prior_year_start: date
    prior_year_end: date
    history_start: date
    defaulted: bool = False
    current_days: int = 0
    prior_days: int = 0
    method: str = "selected_window_vs_prior_matched_days"
    aligned_to_months: bool = False
    terminal_period_incomplete: bool = False
    is_partial_period: bool = False
    current_label: str = "Current filtered window"
    prior_label: str = "Prior comparable window"
    current_short_label: str = "Current window"
    prior_short_label: str = "Prior window"
    comparison_label: str = "Current window vs prior comparable window"
    delta_short_label: str = "Prior window"
    current_window_label: str = ""
    prior_window_label: str = ""
    yoy_label: str = "Same period last year"
    yoy_window_label: str = ""
    note: str = "Comparisons follow the active filtered window."
    trajectory_note: str = "Trajectory shows the active filtered window."

    @property
    def current_end_exclusive(self) -> date:
        return self.current_end + timedelta(days=1)

    def as_dict(self) -> dict[str, Any]:
        return {
            "start": self.current_start.isoformat(),
            "end": self.current_end.isoformat(),
            "prior_month_start": self.prior_month_start.isoformat(),
            "prior_month_end": self.prior_month_end.isoformat(),
            "prior_year_start": self.prior_year_start.isoformat(),
            "prior_year_end": self.prior_year_end.isoformat(),
            "history_start": self.history_start.isoformat(),
            "days": max(1, (self.current_end - self.current_start).days + 1),
            "current_days": self.current_days or max(1, (self.current_end - self.current_start).days + 1),
            "prior_days": self.prior_days or max(1, (self.prior_month_end - self.prior_month_start).days + 1),
            "defaulted": bool(self.defaulted),
            "method": self.method,
            "aligned_to_months": bool(self.aligned_to_months),
            "terminal_period_incomplete": bool(self.terminal_period_incomplete),
            "is_partial_period": bool(self.is_partial_period),
            "current_label": self.current_label,
            "prior_label": self.prior_label,
            "current_short_label": self.current_short_label,
            "prior_short_label": self.prior_short_label,
            "comparison_label": self.comparison_label,
            "delta_short_label": self.delta_short_label,
            "current_window_label": self.current_window_label,
            "prior_window_label": self.prior_window_label,
            "yoy_label": self.yoy_label,
            "yoy_window_label": self.yoy_window_label,
            "note": self.note,
            "trajectory_note": self.trajectory_note,
        }


def _to_date(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    try:
        return datetime.fromisoformat(str(value)).date()
    except Exception:
        return None


def _shift_months(d: date, months: int) -> date:
    idx = (d.month - 1) + months
    year = d.year + (idx // 12)
    month = (idx % 12) + 1
    day = min(d.day, monthrange(year, month)[1])
    return date(year, month, day)


def _shift_years(d: date, years: int) -> date:
    year = d.year + years
    day = min(d.day, monthrange(year, d.month)[1])
    return date(year, d.month, day)


def _month_start(d: date) -> date:
    return d.replace(day=1)


def _month_end(d: date) -> date:
    return date(d.year, d.month, monthrange(d.year, d.month)[1])


def _date_label(d: date) -> str:
    return d.strftime("%b %d, %Y").replace(" 0", " ")


def _window_label(start: date, end: date) -> str:
    if start == end:
        return _date_label(start)
    return f"{_date_label(start)} to {_date_label(end)}"


def resolve_window_contract(
    filters: FilterParams,
    *,
    include_current_month: bool = False,
    default_days: int = 180,
) -> WindowContract:
    today = datetime.utcnow().date()
    start = _to_date(getattr(filters, "start", None))
    end = _to_date(getattr(filters, "end", None))
    defaulted = False

    if start is None and end is None:
        end = today
        start = end - timedelta(days=max(1, int(default_days)))
        defaulted = True

    if end is None and start is not None:
        end = today
    if start is None and end is not None:
        start = date(end.year, end.month, 1)

    assert start is not None and end is not None

    if not include_current_month:
        month_start = date(today.year, today.month, 1)
        if end >= month_start:
            end = month_start - timedelta(days=1)
            if start > end:
                start = date(end.year, end.month, 1)

    if start > end:
        start, end = end, start

    current_days = max(1, (end - start).days + 1)
    terminal_period_incomplete = end != _month_end(end)
    single_month_to_date = start == _month_start(end) and terminal_period_incomplete
    completed_month_span = start == _month_start(start) and end == _month_end(end)
    month_span_count = ((end.year - start.year) * 12) + (end.month - start.month) + 1

    if single_month_to_date:
        prior_month_start = _shift_months(start, -1)
        prior_month_end = min(_month_end(prior_month_start), prior_month_start + timedelta(days=current_days - 1))
        method = "month_to_date_vs_prior_month_same_day"
        current_label = "Current month-to-date"
        prior_label = "Prior month same day"
        current_short = "Current MTD"
        prior_short = "Prior MTD"
        comparison_label = "Month-to-date vs prior month same day"
        delta_short_label = "MTD"
        note = (
            f"Current filtered window is month-to-date through {_date_label(end)}. "
            f"Comparisons use {_window_label(prior_month_start, prior_month_end)} to avoid misleading partial-month MoM."
        )
        trajectory_note = (
            f"Trajectory shows the active filtered window. The latest month is partial, so recent change is compared against "
            f"{_window_label(prior_month_start, prior_month_end)} rather than a full prior month."
        )
    elif completed_month_span:
        prior_month_start = _shift_months(start, -month_span_count)
        prior_month_end = start - timedelta(days=1)
        method = "completed_months_vs_prior_completed_months"
        current_label = "Current completed month set" if month_span_count > 1 else "Current completed month"
        prior_label = "Prior completed month set" if month_span_count > 1 else "Prior completed month"
        current_short = "Current window"
        prior_short = "Prior window"
        comparison_label = "Completed months vs prior completed months"
        delta_short_label = "MoM" if month_span_count == 1 else "Prior window"
        note = (
            f"Current filtered window spans {_window_label(start, end)}. "
            f"Comparisons use the prior completed window {_window_label(prior_month_start, prior_month_end)}."
        )
        trajectory_note = "Trajectory uses completed periods from the active filtered window."
    else:
        prior_month_end = start - timedelta(days=1)
        prior_month_start = prior_month_end - timedelta(days=current_days - 1)
        method = "selected_window_vs_prior_matched_days"
        current_label = "Current filtered window"
        prior_label = "Prior matched-days window"
        current_short = "Current window"
        prior_short = "Prior comparable"
        comparison_label = "Selected window vs prior matched days"
        delta_short_label = "Prior window"
        note = (
            f"Current filtered window {_window_label(start, end)} is compared with "
            f"{_window_label(prior_month_start, prior_month_end)} using the same number of days."
        )
        trajectory_note = "Trajectory shows only the active filtered window; deltas use the prior matched-days comparison."

    prior_year_start = _shift_years(start, -1)
    prior_year_end = _shift_years(end, -1)
    history_start = min(prior_year_start, prior_month_start, start)
    prior_days = max(1, (prior_month_end - prior_month_start).days + 1)

    return WindowContract(
        current_start=start,
        current_end=end,
        prior_month_start=prior_month_start,
        prior_month_end=prior_month_end,
        prior_year_start=prior_year_start,
        prior_year_end=prior_year_end,
        history_start=history_start,
        defaulted=defaulted,
        current_days=current_days,
        prior_days=prior_days,
        method=method,
        aligned_to_months=completed_month_span,
        terminal_period_incomplete=terminal_period_incomplete,
        is_partial_period=single_month_to_date,
        current_label=current_label,
        prior_label=prior_label,
        current_short_label=current_short,
        prior_short_label=prior_short,
        comparison_label=comparison_label,
        delta_short_label=delta_short_label,
        current_window_label=_window_label(start, end),
        prior_window_label=_window_label(prior_month_start, prior_month_end),
        yoy_label="Same period last year",
        yoy_window_label=_window_label(prior_year_start, prior_year_end),
        note=note,
        trajectory_note=trajectory_note,
    )


def safe_div(numerator: Any, denominator: Any) -> Optional[float]:
    try:
        num = float(numerator)
        den = float(denominator)
    except Exception:
        return None
    if abs(den) < EPSILON:
        return None
    return num / den


def delta_value(current: Any, prior: Any) -> Optional[float]:
    try:
        cur = float(current)
        prv = float(prior)
    except Exception:
        return None
    return cur - prv


def delta_percent(current: Any, prior: Any, *, abs_prior: bool = True) -> Optional[float]:
    dval = delta_value(current, prior)
    if dval is None:
        return None
    try:
        prv = float(prior)
    except Exception:
        return None
    denom = abs(prv) if abs_prior else prv
    if abs(denom) < EPSILON:
        return None
    return (dval / denom) * 100.0


def delta_payload(current: Any, prior: Any) -> dict[str, Any]:
    dval = delta_value(current, prior)
    pct = delta_percent(current, prior, abs_prior=True)
    return {
        "current": None if current is None else float(current),
        "previous": None if prior is None else float(prior),
        "delta": dval,
        "delta_pct": pct,
        "delta_pct_na_reason": "no prior-period value" if pct is None else None,
    }


def decompose_price_volume_mix(
    *,
    current_total: Any,
    prior_total: Any,
    current_qty: Any,
    prior_qty: Any,
) -> dict[str, Optional[float]]:
    try:
        cur_total = float(current_total)
        prev_total = float(prior_total)
        cur_qty = float(current_qty)
        prev_qty = float(prior_qty)
    except Exception:
        return {"price_effect": None, "volume_effect": None, "mix_effect": None, "total": None}

    if abs(cur_qty) < EPSILON or abs(prev_qty) < EPSILON:
        total = cur_total - prev_total
        return {"price_effect": None, "volume_effect": None, "mix_effect": None, "total": total}

    cur_price = cur_total / cur_qty
    prev_price = prev_total / prev_qty
    price_effect = (cur_price - prev_price) * prev_qty
    volume_effect = (cur_qty - prev_qty) * prev_price
    total = cur_total - prev_total
    mix_effect = total - price_effect - volume_effect

    return {
        "price_effect": price_effect,
        "volume_effect": volume_effect,
        "mix_effect": mix_effect,
        "total": total,
    }


def compute_hhi(shares_pct: Iterable[Any]) -> Optional[float]:
    shares: list[float] = []
    for value in shares_pct:
        try:
            s = float(value)
        except Exception:
            continue
        if s < 0:
            continue
        shares.append(s)
    if not shares:
        return None
    return sum((s / 100.0) ** 2 for s in shares) * 10000.0


def hhi_risk_label(hhi: Any) -> str:
    try:
        h = float(hhi)
    except Exception:
        return "n/a"
    if h < 1500:
        return "low"
    if h < 2500:
        return "medium"
    return "high"
