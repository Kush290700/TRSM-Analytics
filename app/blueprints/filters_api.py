from __future__ import annotations

import time
from typing import Any, Dict

from flask import Blueprint, jsonify, request, current_app, session
from flask_login import current_user, login_required

from app.services import filters_service
from app.services.filters import bind_filter_cache_key, filters_to_store, resolve_filters

bp = Blueprint("filters_api", __name__, url_prefix="/api/filters")


def _reset_requested() -> bool:
    token = request.args.get("_gf_reset")
    return str(token or "").strip().lower() in {"1", "true", "yes", "on"}


def _merge_filter_meta(*metas: Dict[str, Any]) -> Dict[str, Any]:
    dropped: Dict[str, list[str]] = {}
    notice = None
    sanitized = False
    for meta in metas:
        if not isinstance(meta, dict):
            continue
        sanitized = sanitized or bool(meta.get("sanitized"))
        if not notice:
            notice = meta.get("filters_notice") or meta.get("notice")
        raw_dropped = meta.get("dropped_filters") or meta.get("dropped") or {}
        if not isinstance(raw_dropped, dict):
            continue
        for key, values in raw_dropped.items():
            if not isinstance(values, (list, tuple, set)):
                continue
            bucket = dropped.setdefault(str(key), [])
            for value in values:
                token = str(value).strip()
                if token and token not in bucket:
                    bucket.append(token)
    return {"sanitized": sanitized, "dropped_filters": dropped, "filters_notice": notice}


@bp.get("/schema")
@login_required
def schema() -> Any:
    sticky_enabled = bool(current_app.config.get("STICKY_FILTERS", True))
    v2_mode = bool(current_app.config.get("FILTERS_CANONICAL_V2", False))
    effective, _meta = resolve_filters(
        request,
        current_user,
        session_obj=session,
        source=request.args or {},
        sticky_enabled=sticky_enabled,
        update_session=sticky_enabled and not v2_mode and not _reset_requested(),
    )
    payload = filters_service.schema(filters=effective)
    payload["scope"] = filters_service.scope_from_user(current_user)
    payload["meta"] = {
        "sanitized": bool(_meta.get("sanitized")),
        "dropped_filters": _meta.get("dropped_filters") or {},
        "filters_notice": _meta.get("notice"),
    }
    return jsonify(payload)


@bp.get("/options")
@login_required
def options() -> Any:
    sticky_enabled = bool(current_app.config.get("STICKY_FILTERS", True))
    v2_mode = bool(current_app.config.get("FILTERS_CANONICAL_V2", False))
    requested_dimensions = filters_service.normalize_requested_option_keys(request.args.getlist("dimensions"))
    params, _meta = resolve_filters(
        request,
        current_user,
        session_obj=session,
        source=request.args or {},
        sticky_enabled=sticky_enabled,
        update_session=sticky_enabled and not v2_mode and not _reset_requested(),
    )
    scope = filters_service.scope_from_user(current_user)
    started = time.perf_counter()
    payload_error = None
    try:
        payload = filters_service.get_filter_options(params, scope, requested_keys=requested_dimensions)
        validated_params, payload_meta = filters_service.sanitize_filters_against_options(params, payload)
        if payload_meta.get("sanitized"):
            params = validated_params
            payload = filters_service.get_filter_options(params, scope, requested_keys=requested_dimensions)
        merged_filter_meta = _merge_filter_meta(_meta, payload_meta)
    except Exception as exc:
        payload_error = exc
        current_app.logger.exception(
            "filters.options.failed",
            extra={
                "dimensions": list(requested_dimensions),
                "scope_mode": scope.get("scope_mode"),
                "filter_hash": filters_service.filters_hash(params),
            },
        )
        payload = filters_service.empty_options_payload(params, scope, requested_keys=requested_dimensions, error=exc)
        merged_filter_meta = _merge_filter_meta(_meta)
        payload.setdefault("meta", {})
        payload["meta"]["degraded"] = True
    bind_filter_cache_key(payload.get("meta", {}).get("cache_key") if isinstance(payload.get("meta"), dict) else None)
    duration_ms = payload.get("duration_ms")
    if duration_ms is None:
        duration_ms = int((time.perf_counter() - started) * 1000)
        payload["duration_ms"] = duration_ms
    payload.setdefault("filters", filters_to_store(params))
    payload.setdefault("scope", scope)
    payload.setdefault("meta", {})
    if isinstance(payload.get("meta"), dict):
        payload["meta"]["requested_dimensions"] = list(requested_dimensions)
        payload["meta"]["sanitized"] = bool(merged_filter_meta.get("sanitized"))
        payload["meta"]["dropped_filters"] = merged_filter_meta.get("dropped_filters") or {}
        payload["meta"]["filters_notice"] = merged_filter_meta.get("filters_notice")
    etag = filters_service.options_etag(payload)
    if etag and request.if_none_match and etag in request.if_none_match:
        resp = current_app.response_class(status=304)
        resp.set_etag(etag)
        resp.headers["Cache-Control"] = f"private, max-age={filters_service.OPTIONS_TTL_SECONDS}"
        resp.vary.add("Cookie")
        return resp
    try:
        current_app.logger.info(
            "filters.options",
            extra={
                "duration_ms": payload.get("duration_ms"),
                "cached": payload.get("cached", False),
                "dataset_version": payload.get("dataset_version"),
                "dimensions": list(requested_dimensions),
                "option_counts": payload.get("meta", {}).get("option_counts") if isinstance(payload.get("meta"), dict) else {},
                "degraded": bool(payload.get("meta", {}).get("degraded")) if isinstance(payload.get("meta"), dict) else False,
                "error": str(payload_error) if payload_error else None,
            },
        )
    except Exception:
        pass
    resp = jsonify(payload)
    if etag:
        resp.set_etag(etag)
        resp.headers["Cache-Control"] = f"private, max-age={filters_service.OPTIONS_TTL_SECONDS}"
        resp.vary.add("Cookie")
    return resp
