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
div[data-testid="stTextInput"] input {
    background: #161b22 !important; border: 1px solid #30363d !important;
    color: #f0f6fc !important; border-radius: 10px !important; padding: 0.6rem 1rem !important;
}
.stat-row { display: flex; gap: 1rem; flex-wrap: wrap; margin: 0.5rem 0 1.2rem 0; }
.stat-box {
    background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 0.5rem 1.2rem; min-width: 120px;
}
.stat-box .lbl { font-size: 0.62rem; font-weight: 700; text-transform: uppercase;
                 letter-spacing: 0.08em; color: #7d8590; margin-bottom: 2px; }
.stat-box .val { font-size: 1.1rem; font-weight: 800; color: #f0f6fc; }
</style>
""", unsafe_allow_html=True)


# ── FETCH YAHOO FINANCE ──────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_stock_data(symbol: str) -> dict:
    d = {"symbol": symbol, "ok": False}
    for suffix in [".NS", ".BO"]:
        try:
            t    = yf.Ticker(symbol + suffix)
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

            cut      = pd.Timestamp(datetime.now() - timedelta(days=5 * 365))
            h5       = hist[hist.index >= cut]
            if h5.empty: h5 = hist
            low5_idx = h5["Low"].idxmin()
            low5     = float(h5["Low"].min())

            shares = info.get("sharesOutstanding")
            mktcap = info.get("marketCap")
            eps    = info.get("trailingEps")

            # FCF — 3 fallback methods
            fcf = info.get("freeCashflow")
            if fcf is None:
                ocf   = info.get("operatingCashflow")
                capex = info.get("capitalExpenditures")
                if ocf is not None and capex is not None:
                    fcf = ocf - abs(capex)
            if fcf is None:
                try:
                    cf = t.cashflow
                    if cf is not None and not cf.empty:
                        for row in cf.index:
                            if "free cash" in row.lower():
                                fcf = float(cf.loc[row].iloc[0])
                                break
                except Exception:
                    pass

            fcf_yield = (fcf / mktcap * 100) if (fcf and mktcap and mktcap > 0) else None

            d.update({
                "ok":            True,
                "name":          (info.get("longName") or info.get("shortName") or symbol)[:30],
                "price":         price,
                "mktcap":        mktcap,
                "ath":           ath,
                "ath_date":      ath_idx.strftime("%d %b %Y"),
                "mktcap_ath":    shares * ath  if shares else None,
                "corr":          ((price - ath) / ath * 100) if ath else None,
                "low5":          low5,
                "low5_date":     low5_idx.strftime("%d %b %Y"),
                "mktcap_low5":   shares * low5 if shares else None,
                "pe":            info.get("trailingPE"),
                "pe_ath":        (ath  / eps) if (eps and eps > 0) else None,
                "pe_low5":       (low5 / eps) if (eps and eps > 0) else None,
                "roce":          None,
                "profit_growth": (info.get("earningsGrowth") or 0) * 100 or None,
                "fcf":           fcf,
                "fcf_yield":     fcf_yield,
                "margin":        (info.get("profitMargins") or 0) * 100 or None,
                "div_yield":     (info.get("dividendYield") or 0) * 100 or None,
            })
            return d
        except Exception as e:
            d["error"] = str(e)
    d.setdefault("error", "Symbol not found on NSE/BSE. Check spelling.")
    return d


# ── FETCH SCREENER.IN (ROCE) ────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def get_roce(symbol: str):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
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


# ── BUFFETT / MUNGER RATING ─────────────────────────────────────
def buffett_rating(s: dict):
    score = 0
    notes = []

    roce   = s.get("roce")
    growth = s.get("profit_growth")
    fcfy   = s.get("fcf_yield")
    margin = s.get("margin")
    pe     = s.get("pe")
    corr   = s.get("corr")

    if roce is not None:
        if roce >= 20:   score += 2; notes.append("Excellent ROCE ✓")
        elif roce >= 15: score += 1; notes.append("Good ROCE")
        else:            notes.append("Weak ROCE ✗")

    if growth is not None:
        if growth >= 15:   score += 2; notes.append("Strong profit growth ✓")
        elif growth >= 5:  score += 1; notes.append("Moderate growth")
        else:              notes.append("Weak growth ✗")

    if fcfy is not None:
        if fcfy >= 5:    score += 2; notes.append("Strong FCF yield ✓")
        elif fcfy >= 2:  score += 1; notes.append("Positive FCF")
        elif fcfy < 0:   notes.append("Negative FCF ✗")

    if margin is not None:
        if margin >= 20:   score += 2; notes.append("Excellent margins ✓")
        elif margin >= 10: score += 1; notes.append("Decent margins")
        else:              notes.append("Thin margins ✗")

    if pe is not None:
        if 0 < pe <= 20:  score += 1; notes.append("Reasonable PE ✓")
        elif pe > 50:     notes.append("Very expensive PE ✗")

    if corr is not None:
        if corr <= -30:   score += 1; notes.append(f"Safety margin {corr:.0f}% from ATH ✓")
        elif corr >= -5:  notes.append("Near ATH — priced to perfection ✗")

    if score >= 7:   rating = "🟢 BUY"
    elif score >= 4: rating = "🟡 HOLD"
    else:            rating = "🔴 SELL"

    reason = " · ".join(notes[:3]) if notes else "Insufficient data"
    return rating, score, reason


# ── HELPERS ─────────────────────────────────────────────────────
def _na(v): return v is None or (isinstance(v, float) and np.isnan(v))

def cr(v):
    if _na(v): return "—"
    c = v / 1e7
    if c >= 1_00_000: return f"₹{c/1e5:.2f}L Cr"
    if c >= 1_000:    return f"₹{c/1e3:.1f}K Cr"
    return f"₹{c:,.0f} Cr"

def pr(v, dec=2):
    if _na(v): return "—"
    return f"₹{v:,.{dec}f}"

def pct(v, dec=1):
    if _na(v): return "—"
    return f"{'+'if v>0 else ''}{v:.{dec}f}%"

def pe_fmt(v):
    if _na(v): return "—"
    return f"{v:.1f}x"


# ── SESSION STATE ───────────────────────────────────────────────
if "watchlist" not in st.session_state:
    st.session_state.watchlist = []


# ── HEADER ──────────────────────────────────────────────────────
st.markdown("## 📊 Indian Stock Table Tracker")

total = len(st.session_state.watchlist)
ok    = [s for s in st.session_state.watchlist if s.get("ok")]
buys  = sum(1 for s in ok if buffett_rating(s)[0].startswith("🟢"))
holds = sum(1 for s in ok if buffett_rating(s)[0].startswith("🟡"))
sells = sum(1 for s in ok if buffett_rating(s)[0].startswith("🔴"))

st.markdown(f"""
<div class="stat-row">
  <div class="stat-box"><div class="lbl">Tracked</div><div class="val">{total} / 100</div></div>
  <div class="stat-box"><div class="lbl">🟢 BUY</div><div class="val" style="color:#3fb950">{buys}</div></div>
  <div class="stat-box"><div class="lbl">🟡 HOLD</div><div class="val" style="color:#e3b341">{holds}</div></div>
  <div class="stat-box"><div class="lbl">🔴 SELL</div><div class="val" style="color:#f85149">{sells}</div></div>
  <div class="stat-box"><div class="lbl">Updated</div><div class="val" style="font-size:0.8rem">{datetime.now().strftime("%d %b %H:%M")}</div></div>
</div>
""", unsafe_allow_html=True)


# ── CONTROLS ────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns([3.5, 1.2, 1.2, 1.2])
with c1:
    sym_input = st.text_input(
        "sym", label_visibility="collapsed",
        placeholder="Type ANY NSE symbol (Largecap / Microcap / anything listed) → e.g. RELIANCE, TATAELXSI, WAAREEENER",
    )
with c2:
    add_btn = st.button("➕  Add Stock",   type="primary", use_container_width=True)
with c3:
    ref_btn = st.button("🔄  Refresh All", use_container_width=True, disabled=total == 0)
with c4:
    clr_btn = st.button("🗑️  Clear All",   use_container_width=True, disabled=total == 0)

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
        bar.progress((i + 1) / len(syms), text=f"Refreshing {sym} ({i+1}/{len(syms)})…")
        d = get_stock_data(sym)
        if d["ok"]: d["roce"] = get_roce(sym)
        st.session_state.watchlist.append(d)
    bar.empty()
    st.rerun()

if add_btn and sym_input.strip():
    sym = sym_input.strip().upper()
    if len(st.session_state.watchlist) >= 100:
        st.warning("100 stock limit reached. Remove one to
