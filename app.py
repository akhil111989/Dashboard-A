import streamlit as st
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta

st.set_page_config(page_title="Stock Tracker", page_icon="📊", layout="wide")

st.markdown("""
<style>
.stApp { background: #0a0e1a; }
.block-container { padding-top: 1rem; max-width: 100% !important; }
h2, h3 { color: #f0f6fc !important; font-weight: 900 !important; }
.stButton > button { border-radius: 10px !important; font-weight: 700 !important; }
.stDownloadButton > button { background: #1f6feb !important; color: white !important; border-radius: 10px !important; font-weight: 700 !important; }
.top-stats { display: flex; gap: 1rem; flex-wrap: wrap; margin: 0.5rem 0 1.2rem 0; }
.stat-pill { background: #161b22; border: 1px solid #30363d; border-radius: 10px; padding: 0.5rem 1.1rem; display: flex; flex-direction: column; min-width: 110px; }
.stat-label { font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.08em; color: #7d8590; margin-bottom: 2px; }
.stat-val { font-size: 1.1rem; font-weight: 800; color: #f0f6fc; }
.tbl-outer { overflow-x: auto; border-radius: 14px; border: 1px solid #21262d; margin-top: 0.8rem; }
table { width: 100%; border-collapse: collapse; background: #0d1117; }
thead tr { background: #161b22; }
th { padding: 11px 13px; font-size: 0.62rem; font-weight: 800; text-transform: uppercase; letter-spacing: 0.07em; color: #7d8590; text-align: right; white-space: nowrap; border-bottom: 2px solid #21262d; }
th:first-child, th:nth-child(2) { text-align: left; }
td { padding: 10px 13px; font-size: 0.82rem; color: #c9d1d9; border-bottom: 1px solid #161b22; text-align: right; white-space: nowrap; }
td:first-child { color: #58a6ff; font-weight: 800; text-align: left; }
td:nth-child(2) { color: #e6edf3; text-align: left; font-size: 0.75rem; max-width: 155px; overflow: hidden; text-overflow: ellipsis; }
tbody tr:hover { background: #161b22 !important; }
tbody tr:last-child td { border-bottom: none; }
.badge { display: inline-block; padding: 3px 12px; border-radius: 20px; font-size: 0.72rem; font-weight: 800; }
.buy  { background: #0d2d1a; color: #3fb950; border: 1px solid #238636; }
.hold { background: #2d2000; color: #e3b341; border: 1px solid #9e6a03; }
.sell { background: #2d1115; color: #f85149; border: 1px solid #da3633; }
.cg { color: #3fb950; font-weight: 700; }
.cr { color: #f85149; font-weight: 700; }
.cm { color: #7d8590; font-size: 0.74rem; }
.cn { color: #3d444d; }
</style>
""", unsafe_allow_html=True)


# ── Yahoo Finance ──────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_stock_data(symbol):
    result = {}
    result["symbol"] = symbol
    result["ok"] = False

    for suffix in [".NS", ".BO"]:
        try:
            ticker = yf.Ticker(symbol + suffix)
            info = ticker.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if not price:
                continue

            hist = ticker.history(period="max", auto_adjust=True)
            if hist.empty:
                continue
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)

            ath_idx = hist["High"].idxmax()
            ath = float(hist["High"].max())

            cutoff = pd.Timestamp(datetime.now() - timedelta(days=5 * 365))
            hist5 = hist[hist.index >= cutoff]
            if hist5.empty:
                hist5 = hist
            low5_idx = hist5["Low"].idxmin()
            low5 = float(hist5["Low"].min())

            shares = info.get("sharesOutstanding")
            mktcap = info.get("marketCap")
            eps = info.get("trailingEps")

            fcf = info.get("freeCashflow")
            if fcf is None:
                ocf = info.get("operatingCashflow")
                capex = info.get("capitalExpenditures")
                if ocf is not None and capex is not None:
                    fcf = ocf - abs(capex)
            if fcf is None:
                try:
                    cf = ticker.cashflow
                    if cf is not None and not cf.empty:
                        for row_name in cf.index:
                            if "free cash" in str(row_name).lower():
                                fcf = float(cf.loc[row_name].iloc[0])
                                break
                except Exception:
                    pass

            if fcf is not None and mktcap is not None and mktcap > 0:
                fcf_yield = fcf / mktcap * 100
            else:
                fcf_yield = None

            if ath and ath > 0:
                corr = (price - ath) / ath * 100
            else:
                corr = None

            name = info.get("longName") or info.get("shortName") or symbol
            name = str(name)[:30]

            result["ok"] = True
            result["name"] = name
            result["price"] = price
            result["mktcap"] = mktcap
            result["ath"] = ath
            result["ath_date"] = ath_idx.strftime("%d %b %Y")
            result["mktcap_ath"] = shares * ath if shares else None
            result["corr"] = corr
            result["low5"] = low5
            result["low5_date"] = low5_idx.strftime("%d %b %Y")
            result["mktcap_low5"] = shares * low5 if shares else None
            result["pe"] = info.get("trailingPE")
            result["pe_ath"] = ath / eps if (eps and eps > 0) else None
            result["pe_low5"] = low5 / eps if (eps and eps > 0) else None
            result["roce"] = None
            result["profit_growth"] = (info.get("earningsGrowth") or 0) * 100 or None
            result["fcf"] = fcf
            result["fcf_yield"] = fcf_yield
            result["margin"] = (info.get("profitMargins") or 0) * 100 or None
            result["div_yield"] = (info.get("dividendYield") or 0) * 100 or None
            return result

        except Exception as e:
            result["error"] = str(e)

    if "error" not in result:
        result["error"] = "Symbol not found on NSE/BSE. Check spelling."
    return result


# ── Screener ROCE ──────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_roce(symbol):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36"}
    urls = [
        "https://www.screener.in/company/" + symbol.upper() + "/consolidated/",
        "https://www.screener.in/company/" + symbol.upper() + "/",
    ]
    for url in urls:
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200 or "login" in r.url:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            top = soup.find("ul", id="top-ratios")
            if not top:
                continue
            for li in top.find_all("li"):
                n = li.find("span", class_="name")
                v = li.find("span", class_="nowrap") or li.find("span", class_="value")
                if n and v and "roce" in n.get_text(strip=True).lower():
                    txt = re.sub(r"[₹,%\s]", "", v.get_text(strip=True))
                    m = re.search(r"[\-\d.]+", txt)
                    if m:
                        return float(m.group())
        except Exception:
            pass
    return None


# ── Buffett Rating ─────────────────────────────────────────────
def get_rating(s):
    score = 0
    notes = []

    roce = s.get("roce")
    growth = s.get("profit_growth")
    fcfy = s.get("fcf_yield")
    margin = s.get("margin")
    pe = s.get("pe")
    corr = s.get("corr")

    if roce is not None:
        if roce >= 20:
            score += 2
            notes.append("Excellent ROCE")
        elif roce >= 15:
            score += 1
            notes.append("Good ROCE")
        else:
            notes.append("Weak ROCE")

    if growth is not None:
        if growth >= 15:
            score += 2
            notes.append("Strong growth")
        elif growth >= 5:
            score += 1
            notes.append("Moderate growth")
        else:
            notes.append("Slow growth")

    if fcfy is not None:
        if fcfy >= 5:
            score += 2
            notes.append("Rich FCF yield")
        elif fcfy >= 2:
            score += 1
            notes.append("Positive FCF")
        elif fcfy < 0:
            notes.append("Negative FCF")

    if margin is not None:
        if margin >= 20:
            score += 2
            notes.append("Excellent margins")
        elif margin >= 10:
            score += 1
            notes.append("Decent margins")
        else:
            notes.append("Thin margins")

    if pe is not None:
        if 0 < pe <= 20:
            score += 1
            notes.append("Reasonable PE")
        elif pe > 50:
            notes.append("Expensive PE")

    if corr is not None:
        if corr <= -30:
            score += 1
            notes.append(str(int(round(corr, 0))) + "% from ATH")
        elif corr >= -5:
            notes.append("Near ATH")

    if score >= 7:
        rating = "BUY"
        css = "buy"
    elif score >= 4:
        rating = "HOLD"
        css = "hold"
    else:
        rating = "SELL"
        css = "sell"

    if notes:
        reason = " · ".join(notes[:3])
    else:
        reason = "Insufficient data"

    return rating, css, score, reason


# ── Formatters ─────────────────────────────────────────────────
def isna(v):
    if v is None:
        return True
    if isinstance(v, float) and np.isnan(v):
        return True
    return False

def fmt_cr(v):
    if isna(v):
        return '<span class="cn">—</span>'
    c = v / 1e7
    if c >= 100000:
        return "Rs." + str(round(c / 1e5, 2)) + "L Cr"
    if c >= 1000:
        return "Rs." + str(round(c / 1e3, 1)) + "K Cr"
    return "Rs." + "{:,.0f}".format(c) + " Cr"

def fmt_price(v):
    if isna(v):
        return '<span class="cn">—</span>'
    return "Rs." + "{:,.2f}".format(v)

def fmt_pct(v, rev=False):
    if isna(v):
        return '<span class="cn">—</span>'
    if abs(v) < 0.1:
        cls = "cm"
    elif (v > 0 and not rev) or (v < 0 and rev):
        cls = "cg"
    else:
        cls = "cr"
    sign = "+" if v > 0 else ""
    return '<span class="' + cls + '">' + sign + "{:.1f}".format(v) + "%</span>"

def fmt_pe(v):
    if isna(v):
        return '<span class="cn">—</span>'
    return "{:.1f}x".format(v)

def fmt_pe_est(v):
    if isna(v):
        return '<span class="cn">—</span>'
    return '<span class="cm">' + "{:.1f}".format(v) + "x est</span>"


# ── Session state ──────────────────────────────────────────────
if "watchlist" not in st.session_state:
    st.session_state.watchlist = []


# ── Header ─────────────────────────────────────────────────────
st.markdown("## 📊 Indian Stock Table Tracker")

total = len(st.session_state.watchlist)
buys = 0
holds = 0
sells = 0
for s in st.session_state.watchlist:
    if s.get("ok"):
        r, _, _, _ = get_rating(s)
        if r == "BUY":
            buys += 1
        elif r == "HOLD":
            holds += 1
        else:
            sells += 1

st.markdown(
    '<div class="top-stats">'
    '<div class="stat-pill"><div class="stat-label">Stocks Tracked</div><div class="stat-val">' + str(total) + " / 100</div></div>"
    '<div class="stat-pill"><div class="stat-label">BUY</div><div class="stat-val" style="color:#3fb950">' + str(buys) + "</div></div>"
    '<div class="stat-pill"><div class="stat-label">HOLD</div><div class="stat-val" style="color:#e3b341">' + str(holds) + "</div></div>"
    '<div class="stat-pill"><div class="stat-label">SELL</div><div class="stat-val" style="color:#f85149">' + str(sells) + "</div></div>"
    '<div class="stat-pill"><div class="stat-label">Updated</div><div class="stat-val" style="font-size:0.75rem">' + datetime.now().strftime("%d %b %H:%M") + "</div></div>"
    "</div>",
    unsafe_allow_html=True,
)


# ── Controls ───────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns([3.5, 1.2, 1.2, 1.2])
with c1:
    sym_input = st.text_input(
        "sym",
        label_visibility="collapsed",
        placeholder="Type any NSE symbol — RELIANCE / TATAELXSI / any Microcap — then click Add",
    )
with c2:
    add_btn = st.button("Add Stock", type="primary", use_container_width=True)
with c3:
    ref_btn = st.button("Refresh All", use_container_width=True, disabled=(total == 0))
with c4:
    clr_btn = st.button("Clear All", use_container_width=True, disabled=(total == 0))

if clr_btn:
    st.session_state.watchlist = []
    st.rerun()

if ref_btn:
    syms = [s["symbol"] for s in st.session_state.watchlist]
    st.session_state.watchlist = []
    get_stock_data.clear()
    get_roce.clear()
    bar = st.progress(0)
    for i, sym in enumerate(syms):
        pct_done = (i + 1) / len(syms)
        bar.progress(pct_done, text="Refreshing " + sym + " (" + str(i + 1) + "/" + str(len(syms)) + ")")
        d = get_stock_data(sym)
        if d["ok"]:
            d["roce"] = get_roce(sym)
        st.session_state.watchlist.append(d)
    bar.empty()
    st.rerun()

if add_btn and sym_input.strip():
    sym = sym_input.strip().upper()
    if total >= 100:
        st.warning("100 stock limit reached. Remove a stock first.")
    elif sym in [s["symbol"] for s in st.session_state.watchlist]:
        st.warning(sym + " is already in the table.")
    else:
        with st.spinner("Fetching " + sym + "..."):
            d = get_stock_data(sym)
            if d["ok"]:
                d["roce"] = get_roce(sym)
                st.session_state.watchlist.append(d)
                st.success("Added: " + sym + " — " + d["name"])
            else:
                st.error(sym + ": " + d.get("error", "Not found on NSE/BSE"))
    st.rerun()

st.divider()


# ── Table ──────────────────────────────────────────────────────
if not st.session_state.watchlist:
    st.markdown(
        "<div style='text-align:center;padding:5rem 0;'>"
        "<div style='font-size:4rem'>📋</div>"
        "<div style='font-size:1.2rem;margin-top:1rem;color:#7d8590;font-weight:700'>Add your first stock above</div>"
        "<div style='font-size:0.9rem;margin-top:0.5rem;color:#3d444d'>Works for any NSE/BSE listed stock — Largecap · Midcap · Smallcap · Microcap</div>"
        "</div>",
        unsafe_allow_html=True,
    )
else:
    rows_html = ""
    export_rows = []

    for s in st.session_state.watchlist:
        sym = s["symbol"]

        if not s.get("ok"):
            err = s.get("error", "Unknown error")[:60]
            rows_html += "<tr><td>" + sym + "</td><td colspan='20' style='color:#f85149;text-align:left;'>Error: " + err + "</td></tr>"
            continue

        rating, css, score, reason = get_rating(s)
        score_str = str(score) + "/10"
        ath_date = s.get("ath_date") or "—"
        low5_date = s.get("low5_date") or "—"

        rows_html += "<tr>"
        rows_html += "<td>" + sym + "</td>"
        rows_html += "<td>" + s["name"] + "</td>"
        rows_html += "<td><span class='badge " + css + "'>" + rating + "</span></td>"
        rows_html += "<td class='cm'>" + score_str + "</td>"
        rows_html += "<td>" + fmt_price(s.get("price")) + "</td>"
        rows_html += "<td>" + fmt_cr(s.get("mktcap")) + "</td>"
        rows_html += "<td class='cg'>" + fmt_price(s.get("ath")) + "</td>"
        rows_html += "<td>" + fmt_cr(s.get("mktcap_ath")) + "</td>"
        rows_html += "<td class='cm'>" + ath_date + "</td>"
        rows_html += "<td>" + fmt_pct(s.get("corr"), rev=True) + "</td>"
        rows_html += "<td class='cr'>" + fmt_price(s.get("low5")) + "</td>"
        rows_html += "<td>" + fmt_cr(s.get("mktcap_low5")) + "</td>"
        rows_html += "<td class='cm'>" + low5_date + "</td>"
        rows_html += "<td>" + fmt_pe(s.get("pe")) + "</td>"
        rows_html += "<td>" + fmt_pe_est(s.get("pe_ath")) + "</td>"
        rows_html += "<td>" + fmt_pe_est(s.get("pe_low5")) + "</td>"
        rows_html += "<td>" + fmt_pct(s.get("roce")) + "</td>"
        rows_html += "<td>" + fmt_pct(s.get("profit_growth")) + "</td>"
        rows_html += "<td>" + fmt_pct(s.get("fcf_yield")) + "</td>"
        rows_html += "<td>" + fmt_pct(s.get("margin")) + "</td>"
        rows_html += "<td>" + fmt_pct(s.get("div_yield")) + "</td>"
        rows_html += "</tr>"

        mktcap_cr = round(s["mktcap"] / 1e7, 0) if s.get("mktcap") else None
        mktcap_ath_cr = round(s["mktcap_ath"] / 1e7, 0) if s.get("mktcap_ath") else None
        mktcap_low5_cr = round(s["mktcap_low5"] / 1e7, 0) if s.get("mktcap_low5") else None
        corr_r = round(s["corr"], 1) if s.get("corr") else None
        pe_r = round(s["pe"], 1) if s.get("pe") else None
        pe_ath_r = round(s["pe_ath"], 1) if s.get("pe_ath") else None
        pe_low5_r = round(s["pe_low5"], 1) if s.get("pe_low5") else None
        pg_r = round(s["profit_growth"], 1) if s.get("profit_growth") else None
        fcfy_r = round(s["fcf_yield"], 2) if s.get("fcf_yield") else None
        mg_r = round(s["margin"], 1) if s.get("margin") else None
        dy_r = round(s["div_yield"], 2) if s.get("div_yield") else None

        export_rows.append({
            "Symbol": sym,
            "Company": s["name"],
            "Rating": rating,
            "Score": score,
            "Reason": reason,
            "Current Price": s.get("price"),
            "Market Cap Cr": mktcap_cr,
            "ATH Price": s.get("ath"),
            "MCap at ATH Cr": mktcap_ath_cr,
            "ATH Date": s.get("ath_date"),
            "Corr from ATH pct": corr_r,
            "5Y Low Price": s.get("low5"),
            "MCap at 5YLow Cr": mktcap_low5_cr,
            "5Y Low Date": s.get("low5_date"),
            "PE Current": pe_r,
            "PE at ATH est": pe_ath_r,
            "PE at 5YLow est": pe_low5_r,
            "ROCE pct": s.get("roce"),
            "Profit Growth pct": pg_r,
            "FCF Yield pct": fcfy_r,
            "Net Margin pct": mg_r,
            "Dividend Yield pct": dy_r,
        })

    thead = (
        "<thead><tr>"
        "<th>Symbol</th>"
        "<th>Company</th>"
        "<th>Rating</th>"
        "<th>Score</th>"
        "<th>Price</th>"
        "<th>Mkt Cap</th>"
        "<th style='color:#3fb950'>ATH Price</th>"
        "<th style='color:#3fb950'>MCap@ATH</th>"
        "<th style='color:#3fb950'>ATH Date</th>"
        "<th style='color:#3fb950'>Corr%</th>"
        "<th style='color:#f85149'>5Y Low</th>"
        "<th style='color:#f85149'>MCap@5YLow</th>"
        "<th style='color:#f85149'>5Y Low Date</th>"
        "<th style='color:#58a6ff'>PE Now</th>"
        "<th style='color:#58a6ff'>PE@ATH</th>"
        "<th style='color:#58a6ff'>PE@5YLow</th>"
        "<th>ROCE</th>"
        "<th>Profit Growth</th>"
        "<th>FCF Yield</th>"
        "<th>Net Margin</th>"
        "<th>Div Yield</th>"
        "</tr></thead>"
    )

    full_table = (
        '<div class="tbl-outer">'
        "<table>"
        + thead
        + "<tbody>"
        + rows_html
        + "</tbody></table></div>"
        "<div style='font-size:0.67rem;color:#3d444d;margin-top:0.6rem;'>"
        "PE@ATH and PE@5YLow are estimates using current EPS divided by historical price. "
        "Rating uses Buffett and Munger principles: ROCE, Growth, FCF Yield, Net Margin, PE, Margin of Safety from ATH."
        "</div>"
    )

    st.markdown(full_table, unsafe_allow_html=True)

    st.markdown("#### Remove a stock")
    to_show = st.session_state.watchlist[:10]
    if to_show:
        rcols = st.columns(len(to_show))
        for i, s in enumerate(to_show):
            with rcols[i]:
                btn_label = "X " + s["symbol"]
                btn_key = "rm_" + s["symbol"]
                if st.button(btn_label, key=btn_key, use_container_width=True):
                    st.session_state.watchlist = [x for x in st.session_state.watchlist if x["symbol"] != s["symbol"]]
                    st.rerun()

    st.divider()

    if export_rows:
        df = pd.DataFrame(export_rows)
        csv = df.to_csv(index=False).encode("utf-8")
        fname = "stocks_" + datetime.now().strftime("%Y%m%d_%H%M") + ".csv"
        st.download_button(
            label="Download Full Table as CSV",
            data=csv,
            file_name=fname,
            mime="text/csv",
        )

st.markdown(
    "<div style='text-align:center;color:#21262d;font-size:0.7rem;margin-top:2rem'>"
    "Yahoo Finance and Screener.in. Educational only. Not financial advice."
    "</div>",
    unsafe_allow_html=True,
)
