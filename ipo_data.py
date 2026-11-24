"""JPXの新規上場会社情報を取得し、24時間キャッシュする。"""

from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from urllib.parse import urljoin
from urllib.request import Request, urlopen


JPX_IPO_URL = "https://www.jpx.co.jp/listing/stocks/new/index.html"
CACHE_PATH = Path(__file__).with_name("ipo_cache.json")
CACHE_TTL = timedelta(hours=24)
JST = timezone(timedelta(hours=9))


class _JPXTableParser(HTMLParser):
    """JPXページ内の新規上場一覧テーブルだけを行単位で読む。"""

    def __init__(self):
        super().__init__()
        self.in_target_table = False
        self.table_depth = 0
        self.in_row = False
        self.in_cell = False
        self.rows = []
        self.current_row = []
        self.current_cell = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == "table":
            classes = attributes.get("class", "").split()
            if not self.in_target_table and "widetable" in classes:
                self.in_target_table = True
                self.table_depth = 1
                return
            if self.in_target_table:
                self.table_depth += 1
        if not self.in_target_table:
            return
        if tag == "tr":
            self.in_row = True
            self.current_row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.current_cell = {"text": [], "links": []}
        elif tag == "a" and self.in_cell:
            href = attributes.get("href")
            if href:
                self.current_cell["links"].append(urljoin(JPX_IPO_URL, href))

    def handle_data(self, data):
        if self.in_cell and self.current_cell is not None:
            self.current_cell["text"].append(data)

    def handle_endtag(self, tag):
        if not self.in_target_table:
            return
        if tag in ("td", "th") and self.in_cell:
            text = " ".join("".join(self.current_cell["text"]).split())
            self.current_cell["text"] = text
            self.current_row.append(self.current_cell)
            self.current_cell = None
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.current_row:
                self.rows.append(self.current_row)
            self.current_row = []
            self.in_row = False
        elif tag == "table":
            self.table_depth -= 1
            if self.table_depth == 0:
                self.in_target_table = False


def _iso_date(value):
    match = re.search(r"(20\d{2})/(\d{2})/(\d{2})", value or "")
    return "-".join(match.groups()) if match else ""


def parse_jpx_ipo_html(html):
    """JPXの表から、上場日・企業名・市場など必要な項目だけを取り出す。"""
    parser = _JPXTableParser()
    parser.feed(html)
    items = []
    rows = parser.rows
    index = 0
    while index < len(rows):
        first = rows[index]
        if len(first) < 8 or not re.search(r"20\d{2}/\d{2}/\d{2}", first[0]["text"]):
            index += 1
            continue
        second = rows[index + 1] if index + 1 < len(rows) else []
        dates = re.findall(r"20\d{2}/\d{2}/\d{2}", first[0]["text"])
        company_links = first[1]["links"]
        outline_links = first[3]["links"]
        items.append({
            "listing_date": _iso_date(dates[0]) if dates else "",
            "approval_date": _iso_date(dates[1]) if len(dates) > 1 else "",
            "company": first[1]["text"],
            "code": first[2]["text"].strip(),
            "market": second[0]["text"] if len(second) >= 1 else "",
            "price_range": first[5]["text"],
            "offer_price": second[3]["text"] if len(second) >= 4 else "",
            "company_url": company_links[0] if company_links else "",
            "outline_url": outline_links[0] if outline_links else "",
        })
        index += 2
    return items


def _read_cache():
    if not CACHE_PATH.exists():
        return None
    try:
        # 保存データが古い場合だけJPXを確認し、正常なら保存し直す。
        return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _cache_is_fresh(cache, now):
    if not cache or not cache.get("checked_at"):
        return False
    try:
        checked_at = datetime.fromisoformat(cache["checked_at"])
    except ValueError:
        return False
    return now - checked_at < CACHE_TTL


def _download():
    request = Request(JPX_IPO_URL, headers={"User-Agent": "Mozilla/5.0 IPO calendar/1.0"})
    with urlopen(request, timeout=30) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def load_ipo_data(force_refresh=False):
    """新鮮なキャッシュを優先し、必要な場合だけJPXを1回確認する。"""
    now = datetime.now(JST)
    cache = _read_cache()
    if not force_refresh and _cache_is_fresh(cache, now):
        return {**cache, "updated": False, "error": ""}

    try:
        items = parse_jpx_ipo_html(_download())
        if not items:
            raise ValueError("新規上場データを読み取れませんでした。")
        payload = {"checked_at": now.isoformat(timespec="seconds"), "source": JPX_IPO_URL, "items": items}
        temporary = CACHE_PATH.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(CACHE_PATH)
        return {**payload, "updated": True, "error": ""}
    except Exception as error:
        # JPXを取得できない場合は、最後に正常取得できた内容を返す。
        if cache:
            return {**cache, "updated": False, "error": str(error)}
        return {"checked_at": "", "source": JPX_IPO_URL, "items": [], "updated": False, "error": str(error)}
