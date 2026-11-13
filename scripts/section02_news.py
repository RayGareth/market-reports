"""Select dated official releases and explain their implications with reviewed text."""
import argparse
import html
import json
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time
from email.utils import parsedate_to_datetime
from fractions import Fraction
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree
from zoneinfo import ZoneInfo

KST = ZoneInfo("Asia/Seoul")
ET = ZoneInfo("America/New_York")
LAST_SLOT = time(18, 30)
EVENING_SLOTS = {"0 9 * * 1-5": time(18), "15 9 * * 1-5": time(18, 15), "30 9 * * 1-5": LAST_SLOT}
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


def candidates(topic, after, cutoff, seen, fetch):
    feed_url, publisher, _ = SOURCES[topic]
    raw = fetch(feed_url)
    if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", raw, re.I):
        return []
    feed = ElementTree.fromstring(raw)
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
            if (not url or url in seen or not in_window(published, after, cutoff)
                    or not release_date_matches(topic, url, published)):
                continue
            fact = (policy_rate(fetch(url)) if topic == "policy"
                    else release_fact(topic, entry.findtext("{*}content", "")))
        except (TypeError, ValueError, ZeroDivisionError):
            continue
        if fact:
            term, meaning, connection, interpretation, study = LESSONS[topic]
            title = ("미 연준, FOMC 통화정책 성명 발표" if topic == "policy"
                     else plain(entry.findtext("{*}title", "")))
            if not title:
                continue
            return [{"topic": topic, "title": title, "source": url, "sourceName": publisher,
                     "publishedAt": published.isoformat(), "verified": True, "fact": fact,
                     "interpretation": interpretation, "study": study,
                     "concept": {"term": term, "meaning": meaning, "connection": connection,
                                 "application": f"이번 발표에서 확인한 사실 · {fact} {study}"}}]
    return []


def collect(after, cutoff, seen=(), fetch=download):
    window = {"after": after.isoformat(), "through": cutoff.isoformat()}

    def read(topic):
        try:
            return candidates(topic, after, cutoff, seen, fetch)
        except (OSError, ValueError, ElementTree.ParseError):
            return []

    # Dict order gives priority to a policy decision, then prices and jobs.
    with ThreadPoolExecutor(max_workers=len(SOURCES)) as pool:
        issues = [item for batch in pool.map(read, SOURCES) for item in batch][:2]
    if not issues:
        return {"status": "pending", "issues": [], "window": window}
    concept = issues[0]["concept"]
    for item in issues:
        del item["concept"]
    return {"status": "ready", "issues": issues, "concept": concept, "window": window}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("after", type=datetime.fromisoformat)
    parser.add_argument("through", type=datetime.fromisoformat)
    parser.add_argument("seen", nargs="*", help=argparse.SUPPRESS)
    args = parser.parse_args()
    print(json.dumps(collect(args.after, args.through, args.seen), ensure_ascii=True))
