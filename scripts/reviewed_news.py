"""Select editor-reviewed economic articles without downloading publisher content."""

import json
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

PUBLISHERS = {"050": "한경비즈니스", "079": "노컷뉴스"}
LESSONS = {
    "global_sentiment": (
        "시장 변동성과 투자심리",
        "변동성은 가격이 얼마나 크게 움직이는지를 나타냅니다.",
        "시장 가격의 실제 움직임과 기관의 전망을 구분해 읽어 보세요.",
        "투자심리가 약해지면 위험자산을 줄이려는 움직임이 나타날 수 있습니다.",
        "전망을 비교할 때 전제가 달라지면 결론도 달라질 수 있습니다.",
    ),
    "market_links": (
        "국제 증시의 연결",
        "여러 나라 증시에 상장된 기업도 같은 산업과 투자자의 영향을 받을 수 있습니다.",
        "해외 기술주와 국내 반도체주의 움직임을 같은 기준 시각으로 비교해 보세요.",
        "두 시장이 비슷하게 움직였다면 산업 노출과 투자자 수급도 함께 살펴볼 수 있습니다.",
        "장중 등락률은 장 마감까지 달라질 수 있습니다.",
    ),
    "orders_exports": (
        "수주와 매출 인식",
        "수주는 주문이나 계약을 확보하는 것이고 매출 인식 시점은 계약의 이행에 따라 달라집니다.",
        "계약 규모, 납품 일정, 회사의 매출 인식 기준을 따로 확인해 보세요.",
        "해외 인프라 투자는 국내 공급업체의 수요로 이어질 수 있습니다.",
        "수주 금액과 해당 분기에 인식할 매출을 구별해 보세요.",
    ),
}
QUESTIONS = {
    "global_sentiment": (
        "증시 추가 하락 전망과 이미 관측된 지수 하락 중 어느 쪽이 확인된 시장 사실인가요?",
        "이미 관측된 지수 하락입니다. 추가 하락은 전제가 있는 전망입니다.",
    ),
    "market_links": (
        "오전 등락률을 그날 확정 종가의 등락률로 써도 될까요?",
        "장중 수치는 해당 시각의 관측치입니다. 확정 등락률은 장 마감 후 확인합니다.",
    ),
    "orders_exports": (
        "다른 기업이 3년 납품 계약을 따냈다면 계약 전액이 이번 분기 매출인가요?",
        "계약 금액과 분기 매출은 별개입니다. 실제 이행과 계약에 따른 매출 인식 기준을 확인합니다.",
    ),
}


def editorial_article(item):
    """Validate the fields shared by selection and manuscript validation."""
    try:
        parts = urlsplit(item["source"])
        link = re.fullmatch(r"/article/(\d{3})/\d{10}", parts.path)
        published = datetime.fromisoformat(item["publishedAt"])
        observed = datetime.fromisoformat(item["observedAt"]) if "observedAt" in item else None
        return (
            parts.scheme == "https" and parts.netloc == "n.news.naver.com"
            and not parts.query and not parts.fragment and link is not None
            and PUBLISHERS.get(link[1]) == item["sourceName"]
            and item["topic"] in LESSONS and item["region"] in {"kr", "overseas"}
            and re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", item["eventId"]) is not None
            and item["verified"] is True and published.utcoffset() is not None
            and (observed is None or observed.utcoffset() is not None and observed <= published)
            and (item["topic"] != "market_links" or observed is not None)
            and all(isinstance(item.get(key), str) and item[key].strip()
                    for key in ("title", "fact", "interpretation", "study"))
        )
    except (AttributeError, KeyError, TypeError, ValueError):
        return False


def collect_reviewed(after, cutoff, seen, path):
    try:
        with Path(path).open(encoding="utf-8") as source:
            rows = json.load(source)
        if not isinstance(rows, list):
            return [], "validation_failed"
    except FileNotFoundError:
        return [], "no_candidate"
    except OSError:
        return [], "source_unavailable"
    except (ValueError, UnicodeError):
        return [], "validation_failed"

    issues = []
    outcomes = set()
    for item in rows:
        if not editorial_article(item):
            outcomes.add("validation_failed")
            continue
        published = datetime.fromisoformat(item["publishedAt"])
        if not after < published <= cutoff:
            outcomes.add("outside_window")
            continue
        if item["source"] in seen or f'event:{item["eventId"]}' in seen:
            outcomes.add("duplicate")
            continue
        fields = ("topic", "title", "source", "sourceName", "publishedAt", "verified",
                  "fact", "interpretation", "study", "eventId", "region", "observedAt")
        priority = item.get("priority", 1)
        if type(priority) is not int or priority not in (1, 2, 3):
            outcomes.add("validation_failed")
            continue
        issues.append((priority, {key: item[key] for key in fields if key in item}))
    outcome = next((status for status in ("validation_failed", "duplicate", "outside_window")
                    if status in outcomes), "no_candidate")
    issues.sort(key=lambda entry: (entry[1]["region"] != "kr", -entry[0],
                -datetime.fromisoformat(entry[1]["publishedAt"]).timestamp(), entry[1]["source"]))
    return [item for _, item in issues], outcome
