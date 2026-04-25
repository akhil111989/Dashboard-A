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
.stApp{background:#0d1117}
.block-container{padding-top:1.2rem;max-width:100%!important}
h2,h3{color:#f0f6fc!important}
.stButton>button{border-radius:8px!important;font-weight:700!important}
</style>
""", unsafe_allow_html=True)

# ── Fetch from Yahoo Finance ───────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_stock_data(symbol: str) -> dict:
    d = {"symbol": symbol, "ok": False}
    for suffix in [".NS", ".BO"]:
        try:
            t = yf.Ticker(symbol + suffix)
            info = t.info
            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if not price:
                continue
            hist = t.history(period="max", auto_adjust=True)
            if hist.empty:
                continue
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)

            ath_idx = hist["High"].idxmax()
            ath     = float(hist["High"].max())

            cut  = pd.Timestamp(datetime.now() - timedelta(days=5*365))
            h5   = hist[hist.index >= cut]
            if h5.empty: h5 = hist
            low5_idx = h5["Low"].idxmin()
            low5     = float(h5["Low"].min())

            shares = info.get("sharesOutstanding")
            mktcap = info.get("marketCap")
            eps    = info.get("trailingEps")
            fcf    = info.get("freeCashflow")

            d.update({
                "ok":           True,
                "name":         (info.get("longName") or info.get("shortName") or symbol)[:30],
                "price":        price,
                "mktcap":       mktcap,
                "ath":          ath,
                "ath_date":     ath_idx.strftime("%d %b %Y"),
                "mktcap_ath":   shares * ath  if shares else None,
                "corr":         ((price - ath) / ath * 100) if ath else None,
                "low5":         low5,
                "low5_date":    low5_idx.strftime("%d %b %Y"),
                "mktcap_low5":  shares * low5 if shares else None,
                "pe":           info.get("trailingPE"),
                "pe_ath":       (ath  / eps) if (eps and eps > 0) else None,
                "pe_low5":      (low5 / eps) if (eps and eps > 0) else None,
                "roce":         None,
                "profit_growth":(info.get("earningsGrowth") or 0) * 100 or None,
                "fcf_yield":    (fcf / mktcap * 100) if (fcf and mktcap and mktcap > 0) else None,
                "margin":       (info.get("profitMargins") or 0) * 100 or None,
                "div_yield":    (info.get("dividendYield") or 0) * 100 or None,
            })
            return d
        except Exception as e:
            d["error"] = str(e)
    d.setdefault("error", "Not found. Check NSE symbol spelling.")
    return d

# ── Fetch ROCE from Screener.in ───────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_roce(symbol: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in [
        f"https://www.screener.in/company/{symbol.upper()}/consolidated/",
        f"https://www.screener.in/company/{symbol.upper()}/",
    ]:
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200 or "login" in r.url:
                continue
            soup = BeautifulSoup(r.text, "lxml")
            top  = soup.find("ul", id="top-ratios")
            if not top: continue
            for li in top.find_all("li"):
                n = li.find("span", class_="name")
                v = li.find("span", class_="nowrap") or li.find("span", class_="value")
                if n and v and "roce" in n.get_text(strip=True).lower():
                    txt = re.sub(r"[₹,%\s]", "", v.get_text(strip=True))
                    m   = re.search(r"[\-\d.]+", txt)
                    if m: return float(m.group())
        except Exception:
            pass
    return None

# ── Format helpers ────────────────────────────────────────────
def fmtcr(v):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "—"
    c = v / 1e7
    if c >= 1_00_000: return f"₹{c/1e5:.2f}L Cr"
    if c >= 1_000:    return f"₹{c/1e3:.1f}K Cr"
    return f"₹{c:,.0f} Cr"

def fmtp(v, dec=2):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "—"
    return f"₹{v:,.{dec}f}"

def fmtpct(v, dec=1):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "—"
    return f"{'+'if v>0 else ''}{v:.{dec}f}%"

def fmtpe(v):
    if v is None or (isinstance(v, float) and np.isnan(v)): return "—"
    return f"{v:.1f}×"

# ── Session state ─────────────────────────────────────────────
if "watchlist" not in st.session_state:
    st.session_state.watchlist = []

# ── UI ────────────────────────────────────────────────────────
st.markdown("## 📊 Indian Stock Table Tracker")
st.caption("Type **any** NSE symbol — Largecap, Midcap, Smallcap, Microcap — all work")

c1, c2, c3, c4 = st.columns([3, 1.2, 1.2, 1.2])
with c1:
    sym_input = st.text_input(
        "symbol",
        placeholder="Type any NSE symbol  →  RELIANCE  /  TATAELXSI  /  ANY MICROCAP",
        label_visibility="collapsed",
    )
with c2:
    add_btn = st.button("➕  Add Stock", type="primary", use_container_width=True)
with c3:
    ref_btn = st.button("🔄  Refresh All", use_container_width=True,
                         disabled=len(st.session_state.watchlist) == 0)
with c4:
    clr_btn = st.button("🗑️  Clear All", use_container_width=True,
                         disabled=len(st.session_state.watchlist) == 0)

# ── Button logic ──────────────────────────────────────────────
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
        bar.progress((i+1)/len(syms), text=f"Refreshing {sym}…")
        d = get_stock_data(sym)
        if d["ok"]: d["roce"] = get_roce(sym)
        st.session_state.watchlist.append(d)
    bar.empty()
    st.rerun()

if add_btn and sym_input.strip():
    sym = sym_input.strip().upper()
    if sym in [s["symbol"] for s in st.session_state.watchlist]:
        st.warning(f"**{sym}** is already in the table.")
    else:
        with st.spinner(f"Fetching {sym} from Yahoo Finance + Screener.in…"):
            d = get_stock_data(sym)
            if d["ok"]:
                d["roce"] = get_roce(sym)
                st.session_state.watchlist.append(d)
                st.success(f"✅  Added: {sym} — {d['name']}")
            else:
                st.error(f"❌  {sym}: {d.get('error','Symbol not found on NSE/BSE')}")
    st.rerun()

st.divider()

# ── Table ─────────────────────────────────────────────────────
if not st.session_state.watchlist:
    st.markdown("""
    <div style='text-align:center;padding:5rem 0;'>
        <div style='font-size:3rem'>📋</div>
        <div style='font-size:1.1rem;margin-top:1rem;color:#7d8590'>
            Type any NSE symbol above and click Add Stock
        </div>
        <div style='font-size:0.85rem;margin-top:0.5rem;color:#484f58'>
            Works for any listed stock — large, mid, small or microcap
        </div>
    </div>
    """, unsafe_allow_html=True)
else:
    rows = []
    for s in st.session_state.watchlist:
        if not s.get("ok"):
            rows.append({
                "Symbol": s["symbol"], "Company": f"⚠️ {s.get('error','Error')[:50]}",
                "Current Price":"—","Market Cap":"—","ATH Price":"—",
                "MCap @ ATH":"—","ATH Date":"—","Corr from ATH":"—",
                "5Y Low Price":"—","Min MCap (5Y)":"—","5Y Low Date":"—",
                "PE (Now)":"—","PE @ ATH":"—","PE @ 5Y Low":"—",
                "ROCE":"—","Profit Growth":"—","FCF Yield":"—",
                "Net Margin":"—","Div Yield":"—",
            })
            continue
        rows.append({
            "Symbol":        s["symbol"],
            "Company":       s["name"],
            "Current Price": fmtp(s.get("price")),
            "Market Cap":    fmtcr(s.get("mktcap")),
            "ATH Price":     fmtp(s.get("ath")),
            "MCap @ ATH":    fmtcr(s.get("mktcap_ath")),
            "ATH Date":      s.get("ath_date","—"),
            "Corr from ATH": fmtpct(s.get("corr")),
            "5Y Low Price":  fmtp(s.get("low5")),
            "Min MCap (5Y)": fmtcr(s.get("mktcap_low5")),
            "5Y Low Date":   s.get("low5_date","—"),
            "PE (Now)":      fmtpe(s.get("pe")),
            "PE @ ATH":      fmtpe(s.get("pe_ath")) + " est" if s.get("pe_ath") else "—",
            "PE @ 5Y Low":   fmtpe(s.get("pe_low5")) + " est" if s.get("pe_low5") else "—",
            "ROCE":          fmtpct(s.get("roce")),
            "Profit Growth": fmtpct(s.get("profit_growth")),
            "FCF Yield":     fmtpct(s.get("fcf_yield")),
            "Net Margin":    fmtpct(s.get("margin")),
            "Div Yield":     fmtpct(s.get("div_yield")),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True,
                 height=min(60 + len(rows)*38, 650))

    # Remove individual stocks
    st.markdown("**Remove from table:**")
    rcols = st.columns(min(len(st.session_state.watchlist), 10))
    for i, s in enumerate(st.session_state.watchlist[:10]):
        with rcols[i]:
            if st.button(f"✕ {s['symbol']}", key=f"rm_{s['symbol']}", use_container_width=True):
                st.session_state.watchlist = [
                    x for x in st.session_state.watchlist if x["symbol"] != s["symbol"]
                ]
                st.rerun()

    st.divider()

    # CSV export
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "⬇️  Download as CSV",
        data=csv,
        file_name=f"stocks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
        mime="text/csv",
    )

st.markdown(
    "<div style='text-align:center;color:#21262d;font-size:0.7rem;margin-top:2rem'>"
    "Yahoo Finance · Screener.in | Educational only — not financial advice"
    "</div>",
    unsafe_allow_html=True,
)
