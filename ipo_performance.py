"""IPOの公開価格と初値を、確認済みCSVから集計する。"""

import csv
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
import re

import streamlit as st


PRICE_CSV = Path(__file__).with_name("ipo_first_prices.csv")
FIELDS = ("code", "company", "listing_date", "offer_price", "first_price", "lot_size", "source_url")
JST = timezone(timedelta(hours=9))


def _number(value):
    return int(str(value).strip().replace(",", ""))


def _optional_number(value):
    text = str(value or "").strip()
    return _number(text) if text else None


def _offer_price(value):
    numbers = re.findall(r"\d[\d,]*", str(value or ""))
    return int(numbers[-1].replace(",", "")) if numbers else None


def load_first_prices():
    """CSVを読み込み、初値未取得の行も保持する。"""
    records, warnings = [], []
    if not PRICE_CSV.exists():
        return records, ["初値データCSVがありません。"]
    try:
        with PRICE_CSV.open(encoding="utf-8-sig", newline="") as file:
            reader = csv.DictReader(file)
            if not set(FIELDS).issubset(reader.fieldnames or []):
                return [], ["CSVの列名が正しくありません。"]
            # 1行ずつ検査し、壊れた行があっても全体を停止させない。
            for line, row in enumerate(reader, start=2):
                if not any(str(value or "").strip() for value in row.values()):
                    continue
                try:
                    code = str(row["code"]).strip()
                    company = str(row["company"]).strip()
                    listed = date.fromisoformat(str(row["listing_date"]).strip())
                    offer = _optional_number(row["offer_price"])
                    first = _optional_number(row["first_price"])
                    lot = _optional_number(row["lot_size"]) or 100
                    source = str(row["source_url"] or "").strip()
                    if not code or not company or lot <= 0:
                        raise ValueError("必須項目が不足しています")
                    if (offer is not None and offer <= 0) or (first is not None and first <= 0):
                        raise ValueError("価格が正しくありません")
                    records.append({"code": code, "company": company, "listing_date": listed,
                                    "offer_price": offer, "first_price": first, "lot_size": lot,
                                    "source_url": source})
                except (ValueError, TypeError, AttributeError) as exc:
                    warnings.append(f"{line}行目は集計対象外です: {exc}")
    except (OSError, UnicodeError) as exc:
        warnings.append(f"CSVを読み込めません: {exc}")
    unique = {(row["code"], row["listing_date"]): row for row in records}
    return list(unique.values()), warnings


def _merged_rows(records, rakuten_items):
    merged = {(row["code"], row["listing_date"]): row for row in records}
    for item in rakuten_items:
        try:
            listed = date.fromisoformat(item.get("listing_date", ""))
        except ValueError:
            continue
        key = (str(item.get("code", "")).strip(), listed)
        if key not in merged:
            merged[key] = {"code": key[0], "company": item.get("company") or key[0],
                           "listing_date": listed, "offer_price": _offer_price(item.get("offer_price")),
                           "first_price": None, "lot_size": 100,
                           "source_url": item.get("source_url", "")}
    return list(merged.values())


def render_ipo_performance(rakuten_items, year, month):
    """期間と予算で実績を絞り、上昇割合と銘柄別損益を画面表示する。"""
    st.subheader("📊 IPO過去実績分析")
    st.caption("公開価格で100株購入し、最初に売買が成立した価格で売却できたと仮定した集計です。税金・手数料は含みません。")
    records, warnings = load_first_prices()
    for warning in warnings[:5]:
        st.warning(warning)

    st.caption("確認できない価格は推測せず『未取得』と表示します。")

    rows = _merged_rows(records, rakuten_items)
    if not rows:
        st.info("表示できるIPOデータがありません。")
        return
    with st.sidebar:
        st.divider()
        st.subheader("実績分析")
        period_mode = st.segmented_control(
            "集計期間",
            ["月間", "半年", "年間"],
            default="月間",
            key="ipo_perf_period",
        ) or "月間"
        limits = {"5万円以下": 50_000, "10万円以下": 100_000, "20万円以下": 200_000,
                  "30万円以下": 300_000, "50万円以下": 500_000, "制限なし": None}
        selected_limit = limits[st.selectbox("100株の購入資金", list(limits), index=5,
                                             key="ipo_perf_budget")]
    if period_mode == "年間":
        period_start, period_end = date(year, 1, 1), date(year, 12, 31)
        period_label = f"{year}年"
    elif period_mode == "半年":
        start_month = 1 if month <= 6 else 7
        end_month = start_month + 5
        period_start = date(year, start_month, 1)
        period_end = date(year, end_month, 30 if end_month in (6, 9) else 31)
        period_label = f"{year}年{'上半期（1～6月）' if start_month == 1 else '下半期（7～12月）'}"
    else:
        period_start = date(year, month, 1)
        next_month = date(year + (month == 12), 1 if month == 12 else month + 1, 1)
        period_end = next_month - timedelta(days=1)
        period_label = f"{year}年{month}月"
    st.markdown(f"**集計対象：{period_label}に上場した銘柄**")
    today = datetime.now(JST).date()
    candidates = [row for row in rows if period_start <= row["listing_date"] <= period_end
                  and row["listing_date"] <= today
                  and row["lot_size"] == 100
                  and (selected_limit is None or
                       row["offer_price"] is not None and row["offer_price"] * 100 <= selected_limit)]
    # 公開価格と初値の両方を確認できた銘柄だけを割合計算に使う。
    confirmed = [row for row in candidates if row["offer_price"] is not None and row["first_price"] is not None]
    rising = sum(row["first_price"] > row["offer_price"] for row in confirmed)
    falling = sum(row["first_price"] < row["offer_price"] for row in confirmed)
    unchanged = len(confirmed) - rising - falling
    compared = rising + falling
    st.markdown("**公開価格に対する初値の上昇・下落割合**")
    if compared:
        rising_percent = rising / compared * 100
        falling_percent = falling / compared * 100
        st.markdown(
            f"""
            <div style="display:flex;flex-direction:column;align-items:center;margin:10px 0 16px;">
              <div role="img" aria-label="上昇 {rising_percent:.1f}パーセント、下落 {falling_percent:.1f}パーセント"
                   style="width:min(250px,68vw);aspect-ratio:1;border-radius:50%;
                          background:conic-gradient(#16a34a 0 {rising_percent:.4f}%,#dc2626 {rising_percent:.4f}% 100%);
                          position:relative;box-shadow:0 3px 12px rgba(15,23,42,.16);">
                <div style="position:absolute;inset:27%;border-radius:50%;background:white;
                            display:flex;align-items:center;justify-content:center;text-align:center;
                            font-size:clamp(18px,4vw,27px);font-weight:800;color:#16a34a;">
                  上昇<br>{rising_percent:.1f}%
                </div>
              </div>
              <div style="display:flex;gap:22px;flex-wrap:wrap;justify-content:center;margin-top:14px;font-weight:700;">
                <span><span style="color:#16a34a;font-size:22px;">●</span> 上昇 {rising}社（{rising_percent:.1f}%）</span>
                <span><span style="color:#dc2626;font-size:22px;">●</span> 下落 {falling}社（{falling_percent:.1f}%）</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.caption(f"価格確認済み{len(confirmed)}銘柄のうち、上昇・下落を確認できた{compared}銘柄で計算しています。")
        if unchanged:
            st.caption(f"公開価格と初値が同値の{unchanged}銘柄は円グラフから除外しています。")
    else:
        st.markdown('<div style="text-align:center;font-size:clamp(36px,8vw,68px);font-weight:800;color:#64748b">未取得</div>', unsafe_allow_html=True)
        st.caption("上昇・下落を確認できた銘柄がないため、割合は計算していません。")
    if not candidates:
        st.info("この条件に該当するIPOはありません。")
        return
    table = []
    for row in sorted(candidates, key=lambda item: item["listing_date"]):
        offer, first = row["offer_price"], row["first_price"]
        # 1株の値幅を求め、表示時に100倍して100株分の損益にする。
        diff = first - offer if offer is not None and first is not None else None
        table.append({"銘柄名": row["company"], "上場日": row["listing_date"].isoformat(),
                      "公開価格": f"{offer:,}円" if offer is not None else "未取得",
                      "初値": f"{first:,}円" if first is not None else "未取得",
                      "上昇率": f"{diff / offer * 100:+.2f}%" if diff is not None else "未取得",
                      "100株当たりの損益": f"{diff * 100:+,}円" if diff is not None else "未取得"})
    st.markdown("#### 銘柄別の初値実績")
    st.dataframe(table, hide_index=True, width="stretch")
    missing = len(candidates) - len(confirmed)
    st.caption(f"確認済みデータだけで割合を計算しています。未取得は{missing}銘柄です。")
