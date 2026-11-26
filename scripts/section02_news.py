"""Select dated official releases and explain their implications with reviewed text."""
import argparse
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta
from email.utils import parsedate_to_datetime
from fractions import Fraction
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

if __package__:
    from . import reviewed_news
else:
    import reviewed_news

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")
LAST_SLOT = time(18, 30)
EVENING_SLOTS = {"7 8 * * 1-5": time(17, 7), "0 9 * * 1-5": time(18), "15 9 * * 1-5": time(18, 15), "30 9 * * 1-5": LAST_SLOT}
BOK_FEED = "https://www.bok.or.kr/portal/bbs/B0000552/news.rss?menuNo=200690"
SOURCES = {
    "policy": ("https://www.federalreserve.gov/feeds/press_monetary.xml", "미국 연방준비제도",
               r"/newsevents/pressreleases/monetary\d{8}a\.htm"),
    "prices": ("https://www.bls.gov/feed/cpi.rss", "미국 노동통계국",
               r"/news\.release/archives/cpi_\d{8}\.htm"),
    "jobs": ("https://www.bls.gov/feed/empsit.rss", "미국 노동통계국",
             r"/news\.release/archives/empsit_\d{8}\.htm"),
}
LESSONS = {
    "policy": (
        "정책금리",
        "중앙은행이 단기 자금 시장의 금리를 유도할 때 기준으로 삼는 수준입니다.",
        "성명의 목표 범위와 이전 결정, 시장이 예상한 범위를 비교해 보세요.",
        "금리 경로에 대한 기대가 달라지면 채권 수익률과 달러도 움직일 수 있습니다.",
        "금리 수준과 다음 회의에 대한 성명의 표현을 따로 읽어 보세요.",
    ),
    "prices": (
        "계절조정",
        "해마다 비슷한 시기에 반복되는 변동을 덜어내 서로 다른 달을 비교하기 쉽게 만드는 방법입니다.",
        "이번 발표의 전월 물가와 전년 동월 물가는 비교 기간부터 다릅니다.",
        "물가가 예상보다 오래 높게 유지되면 금리 인하 기대가 약해질 수 있습니다.",
        "전월 수치는 최근 속도, 전년 동월 수치는 지난 1년의 변화를 보여 줍니다.",
    ),
    "jobs": (
        "실업률",
        "일할 의사와 능력이 있어 경제활동에 참여하는 사람 중 일자리를 찾는 실업자의 비율입니다.",
        "이번 실업률과 경제활동참가율을 같이 보면 구직에 참여하는 사람의 변화도 살펴볼 수 있습니다.",
        "고용이 둔화하면 소비와 금리 전망이 달라질 수 있으며 시장은 이전 달과 예상치도 함께 비교합니다.",
        "비농업 고용자 수와 실업률은 조사 대상과 단위가 다릅니다.",
    ),
}
MONTHS = dict(zip("January February March April May June July August September October November December".split(), range(1, 13)))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


def download(url):
    request = Request(url, headers={"User-Agent": "MarketDaily/1.0 (public economic releases)"})
    with build_opener(NoRedirect()).open(request, timeout=6) as response:
        body = response.read(512_001)
    if len(body) > 512_000:
        raise ValueError("Official news response too large")
    return body.decode("utf-8")


def original_url(topic, url):
    item, *_ = SOURCES[topic]
    parts = urlsplit(url)
    if (parts.scheme == "https" and parts.netloc == urlsplit(item).netloc
            and re.fullmatch(SOURCES[topic][2], parts.path)):
        return parts._replace(query="", fragment="").geturl()
    return None


def plain(value):
    return " ".join(html.unescape(re.sub(r"<[^>]*>", " ", value)).split())


def policy_rate(text):
    pattern = r"decided to (maintain|raise|lower) the target range for the federal funds rate (?:at|to) ([\d/.-]+) to ([\d/.-]+) percent"
    match = re.search(pattern, plain(text), re.I)
    if not match:
        return None

    def rate(value):
        return sum(Fraction(part) for part in value.split("-"))

    direction, low, high = match.groups()
    low, high = rate(low), rate(high)
    if not 0 <= low <= high <= 25:
        return None
    action = {"maintain": "동결했습니다", "raise": "인상했습니다", "lower": "인하했습니다"}[direction.lower()]
    return f"연방공개시장위원회는 연방기금금리 목표 범위를 {float(low):g}~{float(high):g}%로 {action}."


def release_fact(topic, summary):
    text = plain(summary)
    month = re.search(r"\bin (" + "|".join(MONTHS) + r")\b", text, re.I)
    if not month:
        return None
    period = MONTHS[month[1].title()]
    if topic == "prices":
        cpi = re.search(r"Consumer Price Index for All Urban Consumers (rose|increased|fell|decreased|declined) ([0-9.]+) percent, seasonally adjusted", text, re.I)
        if not cpi or not 0 <= float(cpi[2]) <= 25:
            return None
        direction = "상승" if cpi[1].lower() in ("rose", "increased") else "하락"
        return f"{period}월 미국 도시 소비자물가지수는 계절조정 기준 전월보다 {cpi[2]}% {direction}했습니다."
    rate = re.search(r"unemployment rate[^.;]{0,36}?([0-9]+(?:\.[0-9]+)?) percent", text, re.I)
    if rate and 0 <= float(rate[1]) <= 100:
        return f"{period}월 미국 실업률은 {rate[1]}%였습니다."
    return None


def release_date_matches(topic, url, published):
    source_date = published.astimezone(ET).strftime("%Y%m%d" if topic == "policy" else "%m%d%Y")
    return source_date in urlsplit(url).path


def in_window(published, after, cutoff):
    return published.tzinfo is not None and after < published <= cutoff


def parse_feed(raw):
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.I):
        raise ValueError("Invalid feed")
    feed = ElementTree.fromstring(raw)
    if feed.tag.rsplit("}", 1)[-1] not in {"rss", "feed"}:
        raise ValueError("Invalid feed")
    return feed


def domestic_release_candidates(after, cutoff, fetch=download):
    """Return official source metadata for editorial review."""
    feed = parse_feed(fetch(BOK_FEED))
    channel = feed.find("channel")
    if channel is None:
        raise ValueError("Expected the Bank of Korea RSS channel")
    candidates = {}
    for entry in channel.findall("item"):
        source = entry.findtext("link", "").strip()
        parts = urlsplit(source)
        if (parts.scheme != "https" or parts.netloc != "www.bok.or.kr"
                or not re.fullmatch(r"/portal/bbs/[BP]\d{7}/view\.do", parts.path)
                or not re.fullmatch(r"nttId=\d+&menuNo=\d+", parts.query)
                or parts.fragment):
            continue
        try:
            published = parsedate_to_datetime(entry.findtext("pubDate", ""))
        except (TypeError, ValueError):
            continue
        title = plain(entry.findtext("title", ""))
        if title and in_window(published, after, cutoff):
            candidates[source] = {"title": title, "source": source, "sourceName": "한국은행",
                                  "publishedAt": published.astimezone(KST).isoformat()}
    return sorted(candidates.values(), key=lambda row: (row["publishedAt"], row["source"]),
                  reverse=True)[:8]


def candidates(topic, after, cutoff, seen, fetch, outcomes):
    outcomes[topic] = "no_candidate"
    feed_url, publisher, _ = SOURCES[topic]
    feed = parse_feed(fetch(feed_url))
    entries = feed.findall("./channel/item") if topic == "policy" else feed.findall("./{*}entry")
    for entry in entries:
        try:
            if topic == "policy":
                if plain(entry.findtext("title", "")) != "Federal Reserve issues FOMC statement":
                    continue
                url = original_url(topic, entry.findtext("link", ""))
                published = parsedate_to_datetime(entry.findtext("pubDate", ""))
            else:
                link = entry.find("{*}link")
                url = original_url(topic, link.get("href", "") if link is not None else "")
                published = datetime.fromisoformat(entry.findtext("{*}published", ""))
                if published.tzinfo is None:
                    continue
                # Atom can show a pre-release upload. CPI and Employment Situation
                # are scheduled for 08:30 ET. Use the later of the two times.
                earliest = datetime.combine(published.astimezone(ET).date(), time(8, 30), ET)
                published = max(published, earliest)
            if (not url or not in_window(published, after, cutoff)
                    or not release_date_matches(topic, url, published)):
                continue
            if url in seen:
                outcomes[topic] = "duplicate"
                continue
            fact = (policy_rate(fetch(url)) if topic == "policy"
                    else release_fact(topic, entry.findtext("{*}content", "")))
        except (TypeError, ValueError, ZeroDivisionError):
            outcomes[topic] = "error"
            continue
        if fact:
            term, meaning, connection, interpretation, study = LESSONS[topic]
            title = ("미 연준, FOMC 통화정책 성명 발표" if topic == "policy"
                     else plain(entry.findtext("{*}title", "")))
            if not title:
                continue
            outcomes[topic] = "selected"
            return [{"topic": topic, "title": title, "source": url, "sourceName": publisher,
                     "publishedAt": published.isoformat(), "verified": True, "fact": fact,
                     "interpretation": interpretation, "study": study,
                     "concept": {"term": term, "meaning": meaning, "connection": connection,
                                 "application": f"이번 발표에서 확인한 사실 · {fact} {study}"}}]
        outcomes[topic] = "error"
    return []


def collect(after, cutoff, seen=(), fetch=download, reviewed_path=None):
    window = {"after": after.isoformat(), "through": cutoff.isoformat()}

    outcomes = {}

    def read(topic):
        try:
            return candidates(topic, after, cutoff, seen, fetch, outcomes)
        except TimeoutError:
            outcomes[topic] = "timeout"
            return []
        except (OSError, ValueError, ElementTree.ParseError):
            outcomes[topic] = "error"
            return []

    # Dict order gives priority to a policy decision, then prices and jobs.
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        official = [item for batch in pool.map(read, SOURCES) for item in batch]
    articles, result = (reviewed_news.collect_reviewed(after, cutoff, seen, reviewed_path)
                        if reviewed_path else ([], "no_candidate"))
    issues, topics, events, urls = [], set(), set(), set()
    domestic = [item for item in articles if item["region"] == "kr"]
    overseas = [item for item in articles if item["region"] == "overseas"]
    for item in domestic + overseas + official:
        event = item.get("eventId")
        if item["topic"] in topics or event in events or item["source"] in urls:
            continue
        issues.append(item)
        topics.add(item["topic"])
        urls.add(item["source"])
        if event:
            events.add(event)
        if len(issues) == 2:
            break
    if reviewed_path:
        outcomes["reviewed_articles"] = ("selected" if any("eventId" in item for item in issues)
                                         else result)
    if not issues:
        return {"status": "pending", "issues": [], "window": window, "outcomes": outcomes}
    first = issues[0]
    concept = first.get("concept")
    if concept is None:
        term, meaning, connection, _, _ = reviewed_news.LESSONS[first["topic"]]
        concept = {"term": term, "meaning": meaning, "connection": connection,
                   "application": first["fact"]}
    for item in issues:
        item.pop("concept", None)
    return {"status": "ready", "issues": issues, "concept": concept, "window": window, "outcomes": outcomes}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("after", type=datetime.fromisoformat, nargs="?")
    parser.add_argument("through", type=datetime.fromisoformat, nargs="?")
    parser.add_argument("seen", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("--domestic-candidates", action="store_true")
    args = parser.parse_args()
    if args.domestic_candidates:
        cutoff = datetime.now(KST)
        items = domestic_release_candidates(cutoff - timedelta(days=4), cutoff)
        print(json.dumps(items, ensure_ascii=False, indent=2))
    else:
        if args.after is None or args.through is None:
            parser.error("after and through are required for report selection")
        reviewed = Path(__file__).resolve().parents[1] / "config/reviewed-economic-news.json"
        print(json.dumps(collect(args.after, args.through, args.seen, reviewed_path=reviewed),
                         ensure_ascii=True))
