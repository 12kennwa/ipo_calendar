"""IPO日程をiPhone/Googleカレンダーへ追加できるICSに変換する。"""

from datetime import date, datetime, timezone
import hashlib


def _escape(value):
    return str(value or "").replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _event(item, kind, date_value):
    try:
        event_date = date.fromisoformat(date_value)
    except (TypeError, ValueError):
        return []
    company = item.get("company") or "IPO"
    code = item.get("code") or "unknown"
    uid_seed = f"{code}-{kind}-{date_value}".encode("utf-8")
    uid = f"{hashlib.sha256(uid_seed).hexdigest()[:20]}@ipo-calendar"
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    start = event_date.strftime("%Y%m%d") + "T090000"
    end = event_date.strftime("%Y%m%d") + "T093000"
    return [
        "BEGIN:VEVENT",
        f"UID:{uid}",
        f"DTSTAMP:{stamp}",
        f"DTSTART;TZID=Asia/Tokyo:{start}",
        f"DTEND;TZID=Asia/Tokyo:{end}",
        f"SUMMARY:{_escape(kind)}｜{_escape(company)}",
        f"DESCRIPTION:{_escape(company)}の{_escape(kind)}です。楽天証券で最新日程と締切時刻を確認してください。",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:前日のお知らせ｜{_escape(kind)}｜{_escape(company)}",
        "TRIGGER:-P1D",
        "END:VALARM",
        "BEGIN:VALARM",
        "ACTION:DISPLAY",
        f"DESCRIPTION:本日のお知らせ｜{_escape(kind)}｜{_escape(company)}",
        "TRIGGER:-PT1M",
        "END:VALARM",
        "END:VEVENT",
    ]


def build_notification_calendar(items):
    """主要なIPO日程すべてを前日・当日通知付きICSにする。"""
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//IPO Calendar//Rakuten IPO Alerts//JA",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        "X-WR-CALNAME:楽天証券 IPO通知",
        "X-WR-TIMEZONE:Asia/Tokyo",
    ]
    for item in items:
        lines.extend(_event(item, "ブックビルディング開始", item.get("bookbuilding_start")))
        lines.extend(_event(item, "ブックビルディング終了", item.get("bookbuilding_end")))
        lines.extend(_event(item, "抽選・価格決定", item.get("price_decision_date")))
        lines.extend(_event(item, "購入申込開始", item.get("purchase_start")))
        lines.extend(_event(item, "購入申込終了", item.get("purchase_end")))
        lines.extend(_event(item, "上場日", item.get("listing_date")))
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
