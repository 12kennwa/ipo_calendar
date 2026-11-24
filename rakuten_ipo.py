"""楽天証券公式の取扱IPO一覧を24時間キャッシュする。"""

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
from urllib.request import Request, urlopen


RAKUTEN_IPO_URL = "https://www.rakuten-sec.co.jp/web/domestic/ipo/"
RAKUTEN_IPO_JSON_URL = "https://www.rakuten-sec.co.jp/web/domestic/ipo/json/ipo_lead_json.json"
CACHE_PATH = Path(__file__).with_name("rakuten_ipo_cache.json")
SNAPSHOT_PATH = Path(__file__).with_name("rakuten_ipo_snapshot.json")
CACHE_TTL = timedelta(hours=24)
JST = timezone(timedelta(hours=9))


def _date(value):
    return (value or "").replace("/", "-") if value and value != "-" else ""


def _convert(row):
    """楽天証券独自の項目名を、アプリ内で分かりやすい名前へ変換する。"""
    return {
        "code": str(row.get("code", "")).strip(),
        "company": str(row.get("data1", "")).strip(),
        "price_range": str(row.get("data3", "")).strip(),
        "bookbuilding_start": _date(row.get("data4")),
        "bookbuilding_end": _date(row.get("data6")),
        "offer_price": str(row.get("data10", "")).strip(),
        "purchase_start": _date(row.get("data11")),
        "purchase_end": _date(row.get("data13")),
        "price_decision_date": _date(row.get("data15")),
        "listing_date": _date(row.get("data18")),
        "company_url": str(row.get("com", "")).strip(),
        "market": str(row.get("data19", "")).strip(),
        "business": str(row.get("data22", "")).replace("<br>", " ").strip(),
        "source_url": f"https://www.rakuten-sec.co.jp/web/domestic/ipo/detail.html?code={row.get('code', '')}",
    }


def _read_cache():
    try:
        if CACHE_PATH.exists():
            return json.loads(CACHE_PATH.read_text(encoding="utf-8"))
        if SNAPSHOT_PATH.exists():
            rows = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
            return {"checked_at": "2026-11-17T17:26:00+09:00", "items": [_convert(row) for row in rows]}
        return None
    except (OSError, json.JSONDecodeError):
        return None


def _fresh(cache, now):
    if not cache or not cache.get("checked_at"):
        return False
    try:
        return now - datetime.fromisoformat(cache["checked_at"]) < CACHE_TTL
    except ValueError:
        return False


def load_rakuten_ipos(force_refresh=False):
    """楽天証券のIPO一覧を読み込み、取得結果と更新状態を返す。"""
    now = datetime.now(JST)
    cache = _read_cache()
    # 24時間以内に取得済みなら、外部サイトへ接続せず保存データを使う。
    if not force_refresh and _fresh(cache, now):
        return {**cache, "updated": False, "error": ""}
    try:
        request = Request(RAKUTEN_IPO_JSON_URL, headers={"User-Agent": "Mozilla/5.0 IPO calendar/1.0"})
        with urlopen(request, timeout=30) as response:
            rows = json.load(response)
        # 証券コードと上場日が確認できるデータだけを採用する。
        items = [_convert(row) for row in rows if row.get("code") and row.get("data18")]
        if not items:
            raise ValueError("楽天証券の取扱IPOを読み取れませんでした。")
        payload = {"checked_at": now.isoformat(timespec="seconds"), "items": items}
        temporary = CACHE_PATH.with_suffix(".json.tmp")
        temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(CACHE_PATH)
        return {**payload, "updated": True, "error": ""}
    except Exception as error:
        # 通信に失敗してもアプリを止めず、前回の保存データを表示する。
        if cache:
            return {**cache, "updated": False, "error": str(error)}
        return {"checked_at": "", "items": [], "updated": False, "error": str(error)}
