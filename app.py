import streamlit as st
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta

st.set_page_config(page_title="📊 Stock Tracker", page_icon="📊", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');
* { font-family: 'Inter', sans-serif; }
.stApp { background: #0a0e1a; }
.block-container { padding-top: 1rem; max-width: 100% !important; }
h1,h2,h3 { color: #f0f6fc !important; font-weight: 900 !important; letter-spacing: -0.5px; }
.stButton > button { border-radius: 10px !important; font-weight: 700 !important; font-size: 0.85rem !important; }
div[data-testid="stTextInput"] input {
    background: #161b22 !important; border: 1px solid #30363d !important;
    color: #f0f6fc !important; border-radius: 10px !important; font-size: 0.95rem !important; padding: 0.6rem 1rem !important;
}
.stDownloadButton > button { background: #1f6feb !important; color: white !important; border-radius: 10px !important; font-weight: 700 !important; }
.stDivider { border-color: #21262d !important; }

/* ── Metric pills at top ── */
.top-stats { display:flex; gap:1rem; flex-wrap:wrap; margin:0.5rem 0 1.2rem 0; }
.stat-pill {
    background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 0.5rem 1.1rem; display:flex; flex-direction:column; min-width:110px;
}
.stat-pill .label { font-size:0.62rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; color:#7d8590; margin-bottom:2px; }
.stat-pill .val   { font-size:1.1rem; font-weight:800; color:#f0f6fc; }

/* ── Table ── */
.tbl-outer { overflow-x:auto; border-radius:14px; border:1px solid #21262d; margin-top:0.8rem; }
table { width:100%; border-collapse:collapse; background:#0d1117; }
thead tr { background:#161b22; position:sticky; top:0; z-index:10; }
th {
    padding:11px 13px; font-size:0.62rem; font-weight:800; text-transform:uppercase;
    letter-spacing:0.07em; color:#7d8590; text-align:right; white-space:nowrap;
    border-bottom:2px solid #21262d;
}
th:first-child,th:nth-child(2) { text-align:left; }
td {
    padding:10px 13px; font-size:0.82rem; color:#c9d1d9;
    border-bottom:1px solid #161b22; text-align:right; white-space:nowrap;
}
td:first-child { color:#58a6ff; font-weight:800; text-align:left; font-size:0.85rem; }
td:nth-child(2) { color:#e6edf3; text-align:left; font-size:0.75rem; max-width:155px; overflow:hidden; text-overflow:ellipsis; }
tbody tr:hover { background:#161b22 !important; }
tbody tr:last-child td { border-bottom:none; }

/* ── Rating badges ── */
.badge {
    display:inline-block; padding:3px 12px; border-radius:20px;
    font-size:0.72rem; font-weight:800; letter-spacing:0.05em;
}
.buy  { background:#0d2d1a; color:#3fb950; border:1px solid #238636; }
.hold { background:#2d2000; color:#e3b341; border:1px solid #9e6a03; }
.sell { background:#2d1115; color:#f85149; border:1px solid #da3633; }

/* ── Colour classes ── */
.g { color:#3fb950; font-weight:700; }
.r { color:#f85149; font-weight:700; }
.y { color:#e3b341; font-weight:700; }
.m { color:#7d8590; font-size:0.74rem; }
.na{ color:#3d444d; }

/* ── Section header in table ── */
.grp { background:#10161f !important; }
.grp td { color:#58a6ff !important; font-size:0.65rem !important; font-weight:800 !important;
          text-transform:uppercase !important; letter-spacing:0.1em !important; padding:6px 13px !important; }

/* ── Empty state ── */
.empty { text-align:center; padding:5rem 0; color:#484f58; }
</style>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════
# DATA FETCHING
# ═══════════════════════════════════════════════════

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

            # ATH (all time)
            ath_idx = hist["High"].idxmax()
            ath     = float(hist["High"].max())

            # 5-Year Low
            cut      = pd.Timestamp(datetime.now() - timedelta(days=5 * 365))
            h5       = hist[hist.index >= cut] if not hist[hist.index >= cut].empty else hist
            low5_idx = h5["Low"].idxmin()
            low5     = float(h5["Low"].min())

            shares = info.get("sharesOutstanding")
            mktcap = info.get("marketCap")
            eps    = info.get("trailingEps")

            # ── FCF — try 3 methods ───────────────────────
            fcf = info.get("freeCashflow")
            if fcf is None:
                ocf   = info.get("operatingCashflow")
                capex = info.get("capitalExpenditures")
                if ocf is not None and capex is not None:
                    fcf = ocf - abs(capex)
            if fcf is None:
                try:
                    cf   = t.cashflow
                    if cf is not None and not cf.empty:
                        ocf_row   = next((cf.loc[r] for r in cf.index if "operating" in r.lower()), None)
                        capex_row = next((cf.loc[r] for r in cf.index if "capital expenditure" in r.lower() or "capex" in r.lower()), None)
                        if ocf_row is not None and capex_row is not None:
                            fcf = float(ocf_row.iloc[0]) - abs(float(capex_row.iloc[0]))
                        elif ocf_row is not None:
                            fcf = float(ocf_row.iloc[0])
                except Exception:
                    pass

            fcf_yield = (fcf / mktcap * 100) if (fcf and mktcap and mktcap > 0) else None

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
                "fcf":          fcf,
                "fcf_yield":    fcf_yield,
                "margin":       (info.get("profitMargins") or 0) * 100 or None,
                "div_yield":    (info.get("dividendYield") or 0) * 100 or None,
            })
            return d
        except Exception as e:
            d["error"] = str(e)
    d.setdefault("error", "Symbol not found on NSE/BSE. Check spelling.")
    return d


@st.cache_data(ttl=3600, show_spinner=False)
def get_roce(symbol: str):
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0 Safari/537.36"}
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
            if not top:
                continue
            for li in top.find_all("li"):
                n = li.find("span", class_="name")
                v = li.find("span", class_="nowrap") or li.find("span", class_="value")
                if n and v and "roce" in n.get_text(strip=True).lower():
                    txt = re.sub(r"[₹,%\s]", "", v.get_text(strip=True))
                    m   = re.search(r"[\-\d.]+", txt)
                    if m:
                        return float(m.group())
        except Exception:
            pass
    return None


# ═══════════════════════════════════════════════════
# BUFFETT / MUNGER RATING ENGINE
# ═══════════════════════════════════════════════════
def buffett_rating(s: dict):
    """
    Score out of 10 using Buffett + Munger principles:
    1. High ROCE        → durable competitive advantage
    2. Profit growth    → compounding business
    3. FCF yield        → real cash generation
    4. Net margin       → pricing power
    5. Reasonable PE    → don't overpay
    6. Correction       → margin of safety (buy at discount)
    """
    score  = 0
    notes  = []

    roce   = s.get("roce")
    growth = s.get("profit_growth")
    fcfy   = s.get("fcf_yield")
    margin = s.get("margin")
    pe     = s.get("pe")
    corr   = s.get("corr")

    # 1. ROCE (max 2 pts)
    if roce is not None:
        if roce >= 20:
            score += 2; notes.append("Excellent ROCE")
        elif roce >= 15:
            score += 1; notes.append("Good ROCE")
        else:
            notes.append("Weak ROCE")
    
    # 2. Profit growth (max 2 pts)
    if growth is not None:
        if growth >= 15:
            score += 2; notes.append("Strong growth")
        elif growth >= 5:
            score += 1; notes.append("Moderate growth")
        else:
            notes.append("Slow/negative growth")

    # 3. FCF Yield (max 2 pts)
    if fcfy is not None:
        if fcfy >= 5:
            score += 2; notes.append("Rich FCF")
        elif fcfy >= 2:
            score += 1; notes.append("Positive FCF")
        elif fcfy < 0:
            notes.append("Negative FCF")

    # 4. Net Margin (max 2 pts)
    if margin is not None:
        if margin >= 20:
            score += 2; notes.append("Excellent margins")
        elif margin >= 10:
            score += 1; notes.append("Decent margins")
        else:
            notes.append("Thin margins")

    # 5. PE reasonableness (max 1 pt)
    if pe is not None:
        if 0 < pe <= 20:
            score += 1; notes.append("Reasonable PE")
        elif pe > 50:
            notes.append("Expensive PE")

    # 6. Margin of safety — correction from ATH (max 1 pt)
    if corr is not None:
        if corr <= -30:
            score += 1; notes.append(f"{corr:.0f}% from ATH = safety margin")
        elif corr >= -5:
            notes.append("Near ATH — priced to perfection")

    # Convert to rating
    if score >= 7:
        rating, css = "BUY",  "buy"
    elif score >= 4:
        rating, css = "HOLD", "hold"
    else:
        rating, css = "SELL", "sell"

    reason = " · ".join(notes[:3]) if notes else "Insufficient data"
    return rating, css, score, reason


# ═══════════════════════════════════════════════════
# FORMATTERS
# ═══════════════════════════════════════════════════
def _na(v):
    return v is None or (isinstance(v, float) and np.isnan(v))

def fcr(v):                                          # ₹ → Crores
    if _na(v): return '<span class="na">—</span>'
    c = v / 1e7
    if c >= 1_00_000: return f"₹{c/1e5:.2f}L Cr"
    if c >= 1_000:    return f"₹{c/1e3:.1f}K Cr"
    return f"₹{c:,.0f} Cr"

def fpr(v, dec=2):                                   # ₹ price
    if _na(v): return '<span class="na">—</span>'
    return f"₹{v:,.{dec}f}"

def fpct(v, dec=1, rev=False):                       # coloured %
    if _na(v): return '<span class="na">—</span>'
    pos_good = not rev
    css = "g" if (v > 0) == pos_good else "r"
    if abs(v) < 0.1: css = "m"
    sign = "+" if v > 0 else ""
    return f'<span class="{css}">{sign}{v:.{dec}f}%</span>'

def fpe(v):                                          # PE × with est note
    if _na(v): return '<span class="na">—</span>'
    return f"{v:.1f}×"

def fpeest(v):
    if _na(v): return '<span class="na">—</span>'
    return f'<span class="m">{v:.1f}× <span style="font-size:0.6rem">est</span></span>'


# ═══════════════════════════════════════════════════
# SESSION STATE
# ═══════════════════════════════════════════════════
if "watchlist" not in st.session_state:
    st.session_state.watchlist = []


# ═══════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════
st.markdown("## 📊 Indian Stock Table Tracker")

# Top stats bar
total  = len(st.session_state.watchlist)
buys   = sum(1 for s in st.session_state.watchlist if s.get("ok") and buffett_rating(s)[0] == "BUY")
holds  = sum(1 for s in st.session_state.watchlist if s.get("ok") and buffett_rating(s)[0] == "HOLD")
sells  = sum(1 for s in st.session_state.watchlist if s.get("ok") and buffett_rating(s)[0] == "SELL")

st.markdown(f"""
<div class="top-stats">
  <div class="stat-pill"><div class="label">Stocks Tracked</div><div class="val">{total} / 100</div></div>
  <div class="stat-pill"><div class="label">🟢 BUY</div><div class="val" style="color:#3fb950">{buys}</div></div>
  <div class="stat-pill"><div class="label">🟡 HOLD</div><div class="val" style="color:#e3b341">{holds}</div></div>
  <div class="stat-pill"><div class="label">🔴 SELL</div><div class="val" style="color:#f85149">{sells}</div></div>
  <div class="stat-pill"><div class="label">Last Updated</div><div class="val" style="font-size:0.75rem;margin-top:2px">{datetime.now().strftime("%d %b %H:%M")}</div></div>
</div>
""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════
# ADD / CONTROL ROW
# ═══════════════════════════════════════════════════
c1, c2, c3, c4 = st.columns([3.5, 1.2, 1.2, 1.2])
with c1:
    sym_input = st.text_input(
        "sym", label_visibility="collapsed",
        placeholder="Type ANY NSE symbol — RELIANCE / TATAELXSI / any Microcap — then click Add",
    )
with c2:
    add_btn = st.button("➕  Add Stock",  type="primary",   use_container_width=True)
with c3:
    ref_btn = st.button("🔄  Refresh All", use_container_width=True, disabled=total == 0)
with c4:
    clr_btn = st.button("🗑️  Clear All",   use_container_width=True, disabled=total == 0)

# ── Actions ──────────────────────────────────────────────────
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
        if d["ok"]:
            d["roce"] = get_roce(sym)
        st.session_state.watchlist.append(d)
    bar.empty()
    st.rerun()

if add_btn and sym_input.strip():
    sym = sym_input.strip().upper()
    if len(st.session_state.watchlist) >= 100:
        st.warning("You have reached the 100 stock limit. Remove a stock to add more.")
    elif sym in [s["symbol"] for s in st.session_state.watchlist]:
        st.warning(f"**{sym}** is already in the table.")
    else:
        with st.spinner(f"Fetching {sym}…"):
            d = get_stock_data(sym)
            if d["ok"]:
                d["roce"] = get_roce(sym)
                st.session_state.watchlist.append(d)
                st.success(f"✅  {sym} — {d['name']} added!")
            else:
                st.error(f"❌  {sym}: {d.get('error', 'Not found on NSE/BSE')}")
    st.rerun()

st.divider()


# ═══════════════════════════════════════════════════
# TABLE
# ═══════════════════════════════════════════════════
if not st.session_state.watchlist:
    st.markdown("""
    <div class="empty">
        <div style="font-size:4rem">📋</div>
        <div style="font-size:1.2rem;margin-top:1rem;color:#7d8590;font-weight:700">
            Add your first stock above
        </div>
        <div style="font-size:0.9rem;margin-top:0.5rem;color:#3d444d">
            Works for any NSE/BSE listed stock — Largecap · Midcap · Smallcap · Microcap
        </div>
    </div>
    """, unsafe_allow_html=True)

else:
    rows_html = ""
    export_rows = []

    for s in st.session_state.watchlist:
        sym  = s["symbol"]

        if not s.get("ok"):
            rows_html += f'<tr><td>{sym}</td><td colspan="20" style="color:#f85149;text-align:left;">⚠️ {s.get("error","Error")[:60]}</td></tr>'
            continue

        rating, css, score, reason = buffett_rating(s)

        rows_html += f"""
        <tr>
          <td>{sym}</td>
          <td title="{s['name']}">{s['name']}</td>
          <td><span class="badge {css}">{rating}</span></td>
          <td style="font-size:0.72rem;color:#7d8590;" title="{reason}">{score}/10</td>

          <td>{fpr(s.get('price'))}</td>
          <td>{fcr(s.get('mktcap'))}</td>

          <td class="g">{fpr(s.get('ath'))}</td>
          <td>{fcr(s.get('mktcap_ath'))}</td>
          <td class="m">{s.get('ath_date','—')}</td>
          <td>{fpct(s.get('corr'), rev=True)}</td>

          <td class="r">{fpr(s.get('low5'))}</td>
          <td>{fcr(s.get('mktcap_low5'))}</td>
          <td class="m">{s.get('low5_date','—')}</td>

          <td>{fpe(s.get('pe'))}</td>
          <td>{fpeest(s.get('pe_ath'))}</td>
          <td>{fpeest(s.get('pe_low5'))}</td>

          <td>{fpct(s.get('roce'))}</td>
          <td>{fpct(s.get('profit_growth'))}</td>
          <td>{fpct(s.get('fcf_yield'))}</td>
          <td>{fpct(s.get('margin'))}</td>
          <td>{fpct(s.get('div_yield'))}</td>
        </tr>"""

        export_rows.append({
            "Symbol":             sym,
            "Company":            s["name"],
            "Rating":             rating,
            "Score (/10)":        score,
            "Rating Reason":      reason,
            "Current Price (₹)":  s.get("price"),
            "Market Cap (Cr)":    round(s["mktcap"]/1e7, 0) if s.get("mktcap") else None,
            "ATH Price (₹)":      s.get("ath"),
            "MCap @ ATH (Cr)":    round(s["mktcap_ath"]/1e7, 0) if s.get("mktcap_ath") else None,
            "ATH Date":           s.get("ath_date"),
            "Corr from ATH %":    round(s["corr"], 1) if s.get("corr") else None,
            "5Y Low Price (₹)":   s.get("low5"),
            "Min MCap 5Y (Cr)":   round(s["mktcap_low5"]/1e7, 0) if s.get("mktcap_low5") else None,
            "5Y Low Date":        s.get("low5_date"),
            "PE (Current)":       round(s["pe"], 1) if s.get("pe") else None,
            "PE @ ATH (est)":     round(s["pe_ath"], 1) if s.get("pe_ath") else None,
            "PE @ 5Y Low (est)":  round(s["pe_low5"], 1) if s.get("pe_low5") else None,
            "ROCE %":             s.get("roce"),
            "Profit Growth %":    round(s["profit_growth"], 1) if s.get("profit_growth") else None,
            "FCF Yield %":        round(s["fcf_yield"], 2) if s.get("fcf_yield") else None,
            "Net Margin %":       round(s["margin"], 1) if s.get("margin") else None,
            "Dividend Yield %":   round(s["div_yield"], 2) if s.get("div_yield") else None,
        })

    st.markdown(f"""
    <div class="tbl-outer">
      <table>
        <thead><tr>
          <th>Symbol</th>
          <th>Company</th>
          <th>Rating</th>
          <th>Score</th>
          <th>Price</th>
          <th>Mkt Cap</th>
          <th style="color:#3fb950">ATH Price</th>
          <th style="color:#3fb950">MCap@ATH</th>
          <th style="color:#3fb950">ATH Date</th>
          <th style="color:#3fb950">Corr%</th>
          <th style="color:#f85149">5Y Low</th>
          <th style="color:#f85149">MCap@5YLow</th>
          <th style="color:#f85149">5Y Low Date</th>
          <th style="color:#58a6ff">PE Now</th>
          <th style="color:#58a6ff">PE@ATH⚠</th>
          <th style="color:#58a6ff">PE@5YLow⚠</th>
          <th>ROCE</th>
          <th>Profit Growth</th>
          <th>FCF Yield</th>
          <th>Net Margin</th>
          <th>Div Yield</th>
        </tr></thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    <div style="font-size:0.67rem;color:#3d444d;margin-top:0.5rem;padding:0 4px;">
      ⚠️ PE @ ATH &amp; 5Y Low = <b>estimate</b> using current EPS ÷ historical price (true historical PE needs paid data) &nbsp;|&nbsp;
      Rating based on Buffett / Munger principles: ROCE · Growth · FCF · Margins · PE · Margin of Safety &nbsp;|&nbsp;
      ROCE from Screener.in · All other data from Yahoo Finance
    </div>
    """, unsafe_allow_html=True)

    # ── Remove row ────────────────────────────────────────────
    st.markdown("#### ✕ Remove a stock")
    chunk = st.session_state.watchlist[:10]
    rcols = st.columns(len(chunk))
    for i, s in enumerate(chunk):
        with rcols[i]:
            if st.button(f"✕ {s['symbol']}", key=f"rm_{s['symbol']}", use_container_width=True):
                st.session_state.watchlist = [x for x in st.session_state.watchlist if x["symbol"] != s["symbol"]]
                st.rerun()

    # ── Download ──────────────────────────────────────────────
    st.divider()
    if export_rows:
        df  = pd.DataFrame(export_rows)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️  Download Full Table as CSV",
            data=csv,
            file_name=f"stock_tracker_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
            use_container_width=False,
        )

st.markdown(
    "<div style='text-align:center;color:#161b22;font-size:0.7rem;margin-top:2rem'>"
    "Yahoo Finance · Screener.in | Educational only — not financial advice</div>",
    unsafe_allow_html=True,
)
