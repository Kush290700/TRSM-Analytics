from app.services.filters import build_filter_summary, parse_filters, normalize_filters


def test_parse_filters_defaults_to_last_3_months():
    params = parse_filters({})
    assert params.preset == "last_3_months"
    assert params.start is not None
    assert params.end is not None
    assert params.start <= params.end


def test_normalize_filters_keeps_explicit_preset_all():
    params = normalize_filters({"date_preset": "all"})
    assert params.preset == "all"
    assert params.start is None
    assert params.end is None


def test_parse_filters_ignores_drilldown_salesrep_id():
    params = parse_filters({"salesrep_id": "R1"})
    assert params.sales_reps == ()


def test_parse_filters_accepts_plural_sales_rep_keys():
    params = parse_filters({"sales_rep_ids": ["R1", "R2"]})
    assert params.sales_reps == ("R1", "R2")


def test_parse_filters_supports_today_preset():
    params = parse_filters({"date_preset": "today"})
    assert params.preset == "today"
    assert params.start is not None
    assert params.end is not None
    assert params.start == params.end


def test_parse_filters_accepts_schema_alias_names():
    params = parse_filters(
        {
            "date_start": "2025-01-01",
            "date_end": "2025-01-31",
            "region_ids": ["west"],
            "ship_method_ids": ["ground"],
        }
    )
    assert str(params.start.date()) == "2025-01-01"
    assert str(params.end.date()) == "2025-01-31"
    assert params.regions == ("west",)
    assert params.methods == ("ground",)


def test_build_filter_summary_compacts_dimension_labels():
    summary = build_filter_summary(
        {
            "date_preset": "mtd",
            "regions": ["Burnaby", "Delta", "Vancouver W"],
            "suppliers": ["Alberta Bison", "Two Rivers", "Northshore"],
        }
    )
    assert summary["date_label"] == "Month to Date"
    assert summary["active_count"] == 3
    assert summary["dimension_count"] == 2
    chips = {chip["key"]: chip for chip in summary["dimension_chips"]}
    assert chips["regions"]["summary"] == "Burnaby, Delta +1"
    assert chips["suppliers"]["summary"] == "Alberta Bison, Northshore +1"


def test_build_filter_summary_includes_advanced_filter_chips():
    summary = build_filter_summary(
        {
            "start": "2025-01-01",
            "end": "2025-01-31",
            "protein_min": 10,
            "protein_max": 25,
            "protein_name": "beef",
            "complete_months_only": "1",
        }
    )
    chips = {chip["key"]: chip for chip in summary["dimension_chips"]}
    assert chips["protein_range"]["summary"] == ">= 10 <= 25"
    assert chips["protein_name_like"]["summary"] == "beef"
    assert chips["complete_months_only"]["summary"] == "Full months only"
