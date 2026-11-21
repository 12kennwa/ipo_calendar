"""楽天証券で取り扱う日本株IPOのカレンダー。"""

import calendar
from datetime import date
from html import escape
import re

import streamlit as st

from calendar_notifications import build_notification_calendar
from ipo_data import load_ipo_data
from ipo_performance import render_ipo_performance
from ipo_reference_prices import REFERENCE_PRICES
from rakuten_ipo import load_rakuten_ipos


def parse_date(value):
    return date.fromisoformat(value) if value else None


def in_month(value, year, month):
    parsed = parse_date(value)
    return bool(parsed and parsed.year == year and parsed.month == month)


def period_overlaps(start_value, end_value, year, month):
    start = parse_date(start_value)
    end = parse_date(end_value)
    if not start or not end:
        return False
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    return start <= month_end and end >= month_start


def current_status(item, today_value):
    bb_start, bb_end = parse_date(item["bookbuilding_start"]), parse_date(item["bookbuilding_end"])
    purchase_start, purchase_end = parse_date(item["purchase_start"]), parse_date(item["purchase_end"])
    if bb_start and bb_start <= today_value <= bb_end:
        return "🟠 ブックビルディング受付中"
    if purchase_start and purchase_start <= today_value <= purchase_end:
        return "🟢 購入申込期間中"
    if bb_start and today_value < bb_start:
        return f"需要申告開始まで {(bb_start - today_value).days}日"
    if purchase_start and today_value < purchase_start:
        return f"購入申込開始まで {(purchase_start - today_value).days}日"
    return "受付期間終了"


def required_funds(item):
    """公開価格、なければ仮条件上限から100株分の必要資金を返す。"""
    offer_values = [int(value.replace(",", "")) for value in re.findall(r"\d[\d,]*", item.get("offer_price", ""))]
    if offer_values:
        return offer_values[-1] * 100, "公開価格"
    range_values = [int(value.replace(",", "")) for value in re.findall(r"\d[\d,]*", item.get("price_range", ""))]
    if range_values:
        return max(range_values) * 100, "仮条件上限"
    reference = item.get("reference_price", {})
    if reference.get("price"):
        return int(reference["price"]) * 100, "想定価格"
    return None, "価格未定"


def render_calendar(items, year, month, today_value, enabled_event_kinds, selected_code=""):
    """期間を週ごとの横棒でつないだ月間カレンダーを描画する。"""
    month_start = date(year, month, 1)
    month_end = date(year, month, calendar.monthrange(year, month)[1])
    events = []
    colors = {
        "需要申告": ("#f59e0b", "#fff7e6"),
        "購入申込": ("#16a34a", "#ecfdf3"),
        "抽選・価格決定": ("#7c3aed", "#f3e8ff"),
        "上場": ("#2563eb", "#eaf2ff"),
    }

    def add_event(item, kind, start_value, end_value=None):
        if kind not in enabled_event_kinds:
            return
        start = parse_date(start_value)
        end = parse_date(end_value or start_value)
        if not start or not end or end < month_start or start > month_end:
            return
        events.append({
            "start": max(start, month_start),
            "end": min(end, month_end),
            "kind": kind,
            "code": item["code"],
            "company": item["company"].replace("株式会社", ""),
            "color": colors[kind][0],
            "background": colors[kind][1],
        })

    for item in items:
        add_event(item, "需要申告", item["bookbuilding_start"], item["bookbuilding_end"])
        add_event(item, "購入申込", item["purchase_start"], item["purchase_end"])
        add_event(item, "抽選・価格決定", item["price_decision_date"])
        add_event(item, "上場", item["listing_date"])

    weeks = calendar.Calendar(firstweekday=0).monthdatescalendar(year, month)
    parts = ["""
    <style>
      html {scroll-behavior:smooth;}
      .ipo-calendar {font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;}
      .ipo-weekdays,.ipo-week {display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:2px;}
      .ipo-weekdays div {font-weight:700;text-align:center;padding:7px 2px;color:#475569;}
      .ipo-week {position:relative;border-top:1px solid #dbe2ea;margin-bottom:5px;}
      .ipo-day {grid-row:1;min-height:31px;padding:5px 7px;background:#f8fafc;border-radius:5px 5px 0 0;font-weight:650;color:#334155;}
      .ipo-day.outside {color:#b8c1cc;background:#fbfcfd;}
      .ipo-day.today {background:#dbeafe;color:#1d4ed8;}
      .ipo-bar {position:relative;z-index:2;margin:1px 2px;padding:4px 17px 4px 7px;border-left:4px solid;border-radius:5px;font-size:12px;font-weight:650;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;min-height:20px;text-decoration:none;cursor:pointer;}
      .ipo-bar:hover {filter:brightness(.96);box-shadow:0 1px 4px rgba(15,23,42,.22);}
      .ipo-bar.selected {outline:2px solid #0f172a;outline-offset:1px;}
      .ipo-bar.range::after {content:"➜";position:absolute;right:4px;top:3px;font-weight:900;}
      @media (max-width:700px){.ipo-bar{font-size:10px;padding-left:4px}.ipo-day{font-size:12px;padding:4px}.ipo-weekdays div{font-size:12px}}
    </style>
    <div class="ipo-calendar">
      <div class="ipo-weekdays"><div>月</div><div>火</div><div>水</div><div>木</div><div>金</div><div>土</div><div>日</div></div>
    """]

    for week in weeks:
        week_start, week_end = week[0], week[-1]
        segments = []
        for event in events:
            start = max(event["start"], week_start)
            end = min(event["end"], week_end)
            if start <= end:
                segments.append({**event, "column_start": (start - week_start).days + 1,
                                 "column_end": (end - week_start).days + 1})
        segments.sort(key=lambda event: (event["column_start"], event["column_end"], event["kind"]))

        lane_ends = []
        for segment in segments:
            lane = next((index for index, last_column in enumerate(lane_ends)
                         if segment["column_start"] > last_column), len(lane_ends))
            if lane == len(lane_ends):
                lane_ends.append(segment["column_end"])
            else:
                lane_ends[lane] = segment["column_end"]
            segment["lane"] = lane

        row_count = max(1, len(lane_ends))
        parts.append(f'<div class="ipo-week" style="grid-template-rows:31px repeat({row_count},29px);">')
        for column, current in enumerate(week, start=1):
            classes = ["ipo-day"]
            if current.month != month:
                classes.append("outside")
            if current == today_value:
                classes.append("today")
            parts.append(f'<div class="{" ".join(classes)}" style="grid-column:{column};">{current.day}</div>')
        for segment in segments:
            is_range = segment["start"] != segment["end"]
            label = f'{segment["kind"]}｜{segment["company"]}'
            selected_class = "selected" if segment["code"] == selected_code else ""
            parts.append(
                f'<a class="ipo-bar {"range" if is_range else ""} {selected_class}" '
                f'href="#ipo-detail-{escape(segment["code"])}" '
                f'style="grid-column:{segment["column_start"]}/{segment["column_end"] + 1};'
                f'grid-row:{segment["lane"] + 2};border-color:{segment["color"]};'
                f'background:{segment["background"]};color:#1f2937;" title="{escape(label)}">'
                f'{escape(label)}</a>'
            )
        parts.append("</div>")
    parts.append("</div>")
    st.markdown("".join(parts), unsafe_allow_html=True)


def render_detail_cards(items, today_value):
    """カレンダーから同じ画面内で開くIPO詳細カードを描画する。"""
    parts = ["""
    <style>
      .ipo-detail-guide {padding:14px 16px;border:1px dashed #94a3b8;border-radius:10px;background:#f8fafc;color:#475569;}
      .ipo-detail-target {display:block;position:relative;top:-12px;height:1px;scroll-margin-top:18px;}
      .ipo-detail-card {display:none;margin-top:12px;padding:18px;border:1px solid #dbe2ea;border-radius:12px;background:white;box-shadow:0 2px 8px rgba(15,23,42,.08);}
      .ipo-detail-target:target + .ipo-detail-card {display:block;}
      .ipo-detail-target:target ~ .ipo-detail-guide {display:none;}
      .ipo-detail-card h3 {margin:0 0 8px;color:#0f172a;}
      .ipo-detail-grid {display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px 22px;margin:12px 0;}
      .ipo-detail-grid div {padding:7px 0;border-bottom:1px solid #eef2f7;}
      .ipo-detail-links a {display:inline-block;margin:8px 10px 0 0;padding:8px 12px;border-radius:8px;background:#eef2ff;color:#3730a3;text-decoration:none;font-weight:650;}
      @media (max-width:700px){.ipo-detail-grid{grid-template-columns:1fr}.ipo-detail-card{padding:14px}}
    </style>
    """]
    for item in items:
        funds, funds_basis = required_funds(item)
        funds_text = f"{funds:,}円（{funds_basis} × 100株）" if funds is not None else "価格未定のため計算できません"
        links = []
        if item.get("company_url"):
            links.append(f'<a href="{escape(item["company_url"])}" target="_blank" rel="noopener">企業公式サイト</a>')
        elif item.get("source_url"):
            links.append(f'<a href="{escape(item["source_url"])}" target="_blank" rel="noopener">楽天証券の銘柄詳細</a>')
        if item.get("outline_url"):
            links.append(f'<a href="{escape(item["outline_url"])}" target="_blank" rel="noopener">JPX会社概要</a>')
        parts.append(
            f'<span id="ipo-detail-{escape(item["code"])}" class="ipo-detail-target"></span>'
            f'<section class="ipo-detail-card">'
            f'<h3>{escape(item["company"])}</h3>'
            f'<div><strong>{escape(current_status(item, today_value))}</strong></div>'
            f'<div class="ipo-detail-grid">'
            f'<div><strong>市場：</strong>{escape(item.get("market") or "未確認")}</div>'
            f'<div><strong>上場承認日：</strong>{escape(item.get("approval_date") or "未確認")}</div>'
            f'<div><strong>ブックビルディング：</strong>{escape(item["bookbuilding_start"] or "未定")} ～ {escape(item["bookbuilding_end"] or "未定")}</div>'
            f'<div><strong>抽選・価格決定：</strong>{escape(item["price_decision_date"] or "未定")}</div>'
            f'<div><strong>購入申込：</strong>{escape(item["purchase_start"] or "未定")} ～ {escape(item["purchase_end"] or "未定")}</div>'
            f'<div><strong>上場日：</strong>{escape(item["listing_date"] or "未定")}</div>'
            f'<div><strong>仮条件：</strong>{escape(item["price_range"] or "未定")}</div>'
            f'<div><strong>公開価格：</strong>{escape(item["offer_price"] or "未定")}</div>'
            f'<div><strong>100株の必要資金：</strong>{escape(funds_text)}</div>'
            f'</div>'
            f'<p><strong>事業内容：</strong>{escape(item.get("business") or "未確認")}</p>'
            f'<div class="ipo-detail-links">{"".join(links)}</div>'
            f'</section>'
        )
    parts.append('<div class="ipo-detail-guide">カレンダー内の会社名が入った色付きバーを押すと、ここに詳細が表示されます。</div>')
    st.markdown("".join(parts), unsafe_allow_html=True)


st.set_page_config(page_title="IPOスケジュールナビ", page_icon="🗓️", layout="wide")
st.markdown(
    """
    <style>
      .stApp {background:linear-gradient(180deg,#f4fbfc 0,#ffffff 360px);}
      h1 {color:#083344 !important;letter-spacing:.02em;}
      h2, h3 {color:#164e63 !important;}
      h2 {border-left:6px solid #0f766e;padding-left:10px;}
      div[data-testid="stSidebar"] {background:linear-gradient(180deg,#e6f7f6,#f8fafc);border-right:1px solid #b9dfdc;}
      div[data-testid="stSidebar"] h1, div[data-testid="stSidebar"] h2,
      div[data-testid="stSidebar"] h3 {border-left:0;color:#0f4c5c !important;}
      div[data-testid="stMetric"] {background:#ffffff;border:1px solid #c9e5e3;border-top:4px solid #0f766e;border-radius:12px;padding:.75rem 1rem;box-shadow:0 3px 10px rgba(15,118,110,.08);}
      div[data-testid="stExpander"] {background:#ffffff;border:1px solid #c9e5e3;border-radius:12px;box-shadow:0 2px 8px rgba(15,23,42,.05);}
      .stButton > button {border-radius:10px;border:1px solid #0f766e;color:#0f5f59;font-weight:700;}
      .stButton > button:hover {border-color:#ea580c;color:#c2410c;background:#fff7ed;}
      .stDownloadButton > button {border:0;border-radius:10px;background:linear-gradient(135deg,#0f766e,#0891b2);color:white;font-weight:800;box-shadow:0 4px 10px rgba(15,118,110,.22);}
      .stDownloadButton > button:hover {background:linear-gradient(135deg,#115e59,#0e7490);color:white;}
      div[data-testid="stDataFrame"] {border:1px solid #d7e7e5;border-radius:10px;overflow:hidden;}
      hr {border-color:#cfe5e3 !important;}
      @media (max-width: 700px) {
        .stMainBlockContainer {padding:1rem .65rem 3rem;}
        h1 {font-size:1.55rem !important;line-height:1.25 !important;}
        h2, h3 {line-height:1.3 !important;}
        div[data-testid="stHorizontalBlock"] {gap:.45rem;}
        .stButton > button, .stLinkButton > a {min-height:44px;width:100%;}
        div[data-testid="stMetric"] {padding:.5rem;}
        div[data-testid="stMetricValue"] {font-size:1.35rem;}
        div[data-testid="stDataFrame"] {overflow-x:auto;}
      }
    </style>
    """,
    unsafe_allow_html=True,
)
st.title("🗓️ IPOスケジュールナビ")
st.caption("楽天証券で取り扱う日本株IPOだけを表示します。公式データを1日1回確認します。")

rakuten = load_rakuten_ipos(force_refresh=False)
with st.expander("🔔 iPhoneへIPO通知を追加"):
    st.write("ブックビルディング、価格決定、購入申込、上場日の各日程を登録し、前日と当日の朝9時に通知します。")
    st.download_button(
        "通知カレンダーをダウンロード",
        data=build_notification_calendar(rakuten["items"]),
        file_name="rakuten_ipo_notifications.ics",
        mime="text/calendar",
        width="stretch",
    )
    st.caption("iPhoneでダウンロードしたファイルを開き、『すべて追加』を押してください。新しいIPOが増えたら、もう一度追加してください。")
jpx = load_ipo_data(force_refresh=False)
jpx_by_code = {item["code"]: item for item in jpx["items"]}
items = []
for row in rakuten["items"]:
    jpx_item = jpx_by_code.get(row["code"], {})
    items.append({
        **row,
        "market": jpx_item.get("market", "楽天証券公式で確認"),
        "approval_date": jpx_item.get("approval_date", ""),
        "outline_url": jpx_item.get("outline_url", ""),
        "reference_price": REFERENCE_PRICES.get(row["code"], {}),
    })

if rakuten["error"]:
    st.warning(f"楽天証券の確認に失敗したため、保存済みデータを表示しています。\n\n{rakuten['error']}")
elif rakuten["updated"]:
    st.success("楽天証券の最新IPO一覧を取得しました。")

today = date.today()
months = set()
for item in items:
    for key in ("bookbuilding_start", "bookbuilding_end", "price_decision_date", "purchase_start", "purchase_end", "listing_date"):
        if item.get(key):
            months.add(item[key][:7])
months = sorted(months) or [today.strftime("%Y-%m")]
default_month = today.strftime("%Y-%m")
if default_month not in months:
    default_month = next((value for value in months if value > default_month), months[-1])

st.markdown("### 表示設定")
if st.session_state.get("calendar_month") not in months:
    st.session_state.calendar_month = default_month

current_month_index = months.index(st.session_state.calendar_month)
previous_column, month_column, next_column = st.columns([1, 3, 1])
if previous_column.button("← 前月", disabled=current_month_index == 0, use_container_width=True):
    st.session_state.calendar_month = months[current_month_index - 1]
    st.rerun()
if next_column.button("翌月 →", disabled=current_month_index == len(months) - 1, use_container_width=True):
    st.session_state.calendar_month = months[current_month_index + 1]
    st.rerun()

with month_column:
    selected_month = st.selectbox(
        "表示する月", months,
        format_func=lambda value: f"{value[:4]}年{int(value[5:7])}月",
        key="calendar_month",
        label_visibility="collapsed",
    )
year, month = map(int, selected_month.split("-"))

fund_limits = {
    "制限なし": None,
    "10万円以下": 100_000,
    "20万円以下": 200_000,
    "30万円以下": 300_000,
    "50万円以下": 500_000,
    "100万円以下": 1_000_000,
}
with st.sidebar:
    st.header("絞り込み")
    selected_fund_label = st.selectbox("カレンダー：100株の必要資金", list(fund_limits))
    selected_fund_limit = fund_limits[selected_fund_label]
    if selected_fund_limit is not None:
        st.caption("価格が未定の銘柄は除外します。")
    st.markdown("**カレンダーに表示する予定**")
    show_bookbuilding = st.checkbox("ブックビルディング", value=True)
    show_purchase = st.checkbox("購入申込", value=True)
    show_price_decision = st.checkbox("抽選・価格決定", value=True)
    show_listing = st.checkbox("上場日", value=True)
enabled_event_kinds = set()
if show_bookbuilding:
    enabled_event_kinds.add("需要申告")
if show_purchase:
    enabled_event_kinds.add("購入申込")
if show_price_decision:
    enabled_event_kinds.add("抽選・価格決定")
if show_listing:
    enabled_event_kinds.add("上場")

visible = [
    item for item in items
    if (
        in_month(item["listing_date"], year, month)
        or in_month(item["price_decision_date"], year, month)
        or period_overlaps(item["bookbuilding_start"], item["bookbuilding_end"], year, month)
        or period_overlaps(item["purchase_start"], item["purchase_end"], year, month)
    )
    and (
        selected_fund_limit is None
        or (required_funds(item)[0] is not None and required_funds(item)[0] <= selected_fund_limit)
    )
]

metric1, metric2, metric3 = st.columns(3)
metric1.metric("この月の取扱IPO", f"{len(visible)}社")
metric2.metric("楽天証券の保存銘柄", f"{len(items)}社")
metric3.metric("最終確認", rakuten["checked_at"][:16].replace("T", " ") if rakuten["checked_at"] else "未取得")

st.markdown("🟠 ブックビルディング　🟢 購入申込　🟣 抽選・価格決定　🔵 上場")
st.subheader(f"{year}年{month}月")
render_calendar(visible, year, month, today, enabled_event_kinds)

st.divider()
st.markdown('<div id="ipo-details"></div>', unsafe_allow_html=True)
st.subheader("選択したIPOの詳細")
if not visible:
    st.info("この月に該当する取扱IPOはありません。")
if visible:
    render_detail_cards(visible, today)

st.divider()
render_ipo_performance(rakuten["items"], year, month)

st.divider()
st.caption("情報源: 楽天証券公式IPO一覧。日程・取扱いは変更される場合があります。投資判断を示すものではありません。")
