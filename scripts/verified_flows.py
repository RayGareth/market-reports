#!/usr/bin/env python3
"""Validate licensed, independently reviewed market flow/sector inputs.

This module NEVER scrapes third-party sites. The daily JSON is optional:
missing -> disclose unverified data; malformed -> stop publication.
Amounts are KRW net purchase values (buy minus sell), not share counts.
"""
from __future__ import annotations
import json
import math
import pathlib
from datetime import date, datetime
from urllib.parse import urlsplit

MARKETS = ("KOSPI", "KOSDAQ")
INVESTORS = ("foreign", "institution", "individual")


def _source_url(value):
    if not isinstance(value, str):
        raise ValueError("A documented HTTPS source URL is required")
    parts = urlsplit(value)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("A public HTTPS source URL is required")
    if parts.hostname in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Local source URL is forbidden")
    return value


def _amount(value):
    if isinstance(value, bool) or not isinstance(value, int) or abs(value) > 10**16:
        raise ValueError("Net purchase must be an integer amount in KRW")
    return value


def load_verified_flows(path: pathlib.Path, expected_date: str):
    """Return validated content or None. Never silently accept stale inputs."""
    if not path.is_file():
        return None
    doc = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict) or doc.get("date") != expected_date:
        raise ValueError("Flows input date differs from the report date")
    date.fromisoformat(expected_date)
    verification = doc.get("verification")
    if not isinstance(verification, dict) or verification.get("method") != "manual_review":
        raise ValueError("A recorded manual review is required")
    if verification.get("rights_confirmed") is not True:
        raise ValueError("Source reuse rights must be confirmed before publication")
    if not isinstance(verification.get("reviewed_by"), str) or not verification["reviewed_by"].strip():
        raise ValueError("Reviewer is required")
    _source_url(verification.get("source_url"))
    checked = datetime.fromisoformat(verification.get("checked_at", ""))
    if checked.tzinfo is None or checked.date() < date.fromisoformat(expected_date):
        raise ValueError("Review timestamp must be timezone-aware and current")
    investors = doc.get("investors", {})
    sectors = doc.get("sectors", [])
    if not isinstance(investors, dict) or not isinstance(sectors, list):
        raise ValueError("Investors and sectors must be objects and lists")
    if not investors and not sectors:
        raise ValueError("At least one verified dataset is required")
    for market, values in investors.items():
        if market not in MARKETS or not isinstance(values, dict) or set(values) != set(INVESTORS):
            raise ValueError("Invalid investor market or missing investor category")
        for value in values.values():
            _amount(value)
    if len(sectors) > 50:
        raise ValueError("Too many sectors")
    seen = set()
    for item in sectors:
        if not isinstance(item, dict) or set(item) != {"market", "name", "change_pct"}:
            raise ValueError("Sector rows require market, name and change_pct")
        market, name, pct = item["market"], item["name"], item["change_pct"]
        if market not in MARKETS or not isinstance(name, str) or not name.strip() or len(name) > 50:
            raise ValueError("Invalid sector name or market")
        key = (market, name.strip())
        if key in seen:
            raise ValueError("Duplicate sector")
        seen.add(key)
        if isinstance(pct, bool) or not isinstance(pct, (int, float)) or not math.isfinite(pct) or abs(pct) > 40:
            raise ValueError("Invalid sector percentage")
    return doc


def _krw(value):
    if abs(value) < 100_000_000:
        return f"{value:+,}원"
    return f"{value / 100_000_000:+,.2f}억 원"


def section_for_flows(kospi: dict, kosdaq: dict, doc):
    """Produce transparent Korean analysis; never infer investor flows from prices."""
    a, b = kospi["changePct"], kosdaq["changePct"]
    relative = "코스피가 상대적으로 강했습니다" if a > b else "코스닥이 상대적으로 강했습니다" if a < b else "두 지수의 등락률이 같았습니다"
    paragraphs = [
        f"시장 간 상대 강도: 코스피 {a:+.2f}%, 코스닥 {b:+.2f}%. {relative}. 이는 시장 지수 비교이며 투자자별 순매수나 특정 업종의 움직임을 뜻하지 않습니다."
    ]
    sources = []
    if doc is None:
        paragraphs.append("외국인·기관·개인 순매수액과 업종별 등락률은 출처와 재사용 권한이 확인된 자료가 없어 미검증으로 표시합니다. 지수 하락만으로 외국인 순매도를 추정하지 않습니다.")
        return {"title": "수급과 업종: 상대 강도와 미검증 데이터", "paragraphs": paragraphs}, sources

    investors = doc.get("investors", {})
    if investors:
        labels = {"foreign": "외국인", "institution": "기관", "individual": "개인"}
        for market in MARKETS:
            if market in investors:
                vals = investors[market]
                summary = ", ".join(f"{labels[key]} {_krw(vals[key])}" for key in INVESTORS)
                paragraphs.append(f"{market} 투자자별 순매수(거래대금 기준): {summary}. 순매수는 매수대금에서 매도대금을 뺀 값이며, 다른 투자자 범주가 있어 세 항목의 합이 반드시 0일 필요는 없습니다.")
    else:
        paragraphs.append("외국인·기관·개인 순매수: 미검증(자료 미제공).")
    sectors = doc.get("sectors", [])
    if sectors:
        for market in MARKETS:
            rows = [row for row in sectors if row["market"] == market]
            if not rows:
                continue
            gainers = sorted((row for row in rows if row["change_pct"] > 0), key=lambda r: r["change_pct"], reverse=True)[:3]
            losers = sorted((row for row in rows if row["change_pct"] < 0), key=lambda r: r["change_pct"])[:3]
            def display(items):
                return ", ".join(f"{row['name']} {row['change_pct']:+.2f}%" for row in items) if items else "해당 없음"
            paragraphs.append(f"{market} 확인된 업종 표본의 상승 상위: {display(gainers)}. 하락 하위: {display(losers)}. 전체 업종 순위가 아니라 제공된 표본 범위의 비교입니다.")
    else:
        paragraphs.append("업종별 등락률: 미검증(자료 미제공).")
    verification = doc["verification"]
    paragraphs.append(f"수급·업종 수치 출처: {verification['source_name']} · 수동 검토 {verification['checked_at']} · 검토자 {verification['reviewed_by']}. 자료의 범위와 재사용 권한을 확인한 입력만 반영합니다.")
    sources.append({"label": "수급·업종 수동 검토 출처: " + verification["source_name"], "url": verification["source_url"]})
    return {"title": "수급과 업종: 검토된 수치와 상대 강도", "paragraphs": paragraphs}, sources
