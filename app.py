"""
📊 Indian Stock Portfolio Table Tracker
Add multiple stocks → see all key metrics in one clean table
Sources: Yahoo Finance · Screener.in
"""

import streamlit as st
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta

# ────────────────────────────────────────────────────────────────
# PAGE CONFIG
# ────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Stock Table Tracker",
    page_icon="📊",
    layout="wide",
)

# ────────────────────────────────────────────────────────────────
# CSS — dark GitHub-style theme
# ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
  .stApp { background: #0d1117; }
  .block-container { padding-top: 1.5rem; padding-bottom: 2rem; max-width: 100% !important; }
  h1, h2, h3, h4 { color: #f0f6fc !important; font-weight: 900 !important; }
  .stButton button { border-radius: 8px !important; font-weight: 600 !important; }

  /* ── Table ── */
  .tbl-wrap {
    overflow-x: auto;
    border-radius: 12px;
    border: 1px solid #21262d;
    margin-top: 1rem;
  }
  table { width: 100%; border-collapse: collapse; background: #161b22; }
  thead tr { background: #1c2128; }
  th {
    padding: 10px 14px;
    font-size: 0.67rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: #7d8590;
    text-align: right;
    white-space: nowrap;
    border-bottom: 2px solid #30363d;
  }
  th:first-child, th:nth-child(2) { text-align: left; }
  td {
    padding: 9px 14px;
    font-size: 0.83rem;
    color: #c9d1d9;
    border-bottom: 1px solid #21262d;
    text-align: right;
    white-space: nowrap;
  }
  td:first-child { color: #58a6ff; font-weight: 700; text-align: left; }
  td:nth-child(2) {
    color: #e6edf3; text-align: left;
    font-size: 0.74rem; max-width: 160px;
    overflow: hidden; text-overflow: ellipsis;
  }
  tbody tr:hover { background: #1c2128; }
  tbody tr:last-child td { border-bottom: none; }

  /* ── Colour helpers ── */
  .up   { color: #3fb950 !important; font-weight: 700; }
  .down { color: #f85149 !important; font-weight: 700; }
  .amb  { color: #d29922 !important; font-weight: 700; }
  .muted { color: #7d8590; font-size: 0.75rem; }
  .na   { color: #3d444d; }

  /* ── Section headers inside table ── */
  .grp-ath  { background: #0d2015 !important; color: #3fb950 !important; }
  .grp-5yl  { background: #2d1520 !important; color: #f85149 !important; }
  .grp-val  { background: #0d1e2d !important; color: #58a6ff !important; }

  /* ── Pills ── */
  .pill-row { display: flex; gap: 0.5rem; flex-wrap: wrap; margin: 0.4rem 0 1rem 0; }
  .pill {
    background: #161b22; border: 1px solid #30363d;
    border-radius: 6px; padding: 3px 10px;
    font-size: 0.72rem; color: #7d8590;
  }
  .pill b { color: #c9d1d9; }

  /* ── Empty state ── */
  .empty-state {
    text-align: center; padding: 4rem 2rem; color: #484f58;
  }
</style>
""", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────
# FORMAT HELPERS
# ────────────────────────────────────────────────────────────────
def _none(val):
    return val is None or (isinstance(val, float) and np.isnan(val))

def fmt_cr(val):
    """Absolute ₹ value → ₹ Crores display string (HTML)"""
    if _none(val):
        return '<span class="na">—</span>'
    c = val / 1e7
    if c >= 1_00_000:
        return f"₹{c/1e5:.2f}L Cr"
    if c >= 1_000:
        return f"₹{c/1e3:.1f}K Cr"
    return f"₹{c:,.0f} Cr"

def fmt_pr(val, dec=2):
    """Price in ₹"""
    if _none(val):
        return '<span class="na">—</span>'
    return f"₹{val:,.{dec}f}"

def fmt_pct(val, dec=1, good_positive=True):
    """Coloured percentage"""
    if _none(val):
        return '<span class="na">—</span>'
    css = "up" if (val > 0) == good_positive else "down"
    sign = "+" if val > 0 else ""
    return f'<span class="{css}">{sign}{val:.{dec}f}%</span>'

def fmt_pe(val, dec=1, note=""):
    """PE ratio with optional note"""
    if _none(val):
        return '<span class="na">—</span>'
    note_html = f' <span class="na" style="font-size:0.6rem;">{note}</span>' if note else ""
    return f"{val:.{dec}f}×{note_html}"

def fmt_date(val):
    if not val:
        return '<span class="na">—</span>'
    return f'<span class="muted">{val}</span>'


# ────────────────────────────────────────────────────────────────
# DATA — YAHOO FINANCE
# ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def fetch_stock(symbol: str) -> dict:
    d = {"symbol": symbol, "ok": False}

    for suffix in [".NS", ".BO"]:
        try:
            ticker = yf.Ticker(symbol + suffix)
            info   = ticker.info
            price  = info.get("currentPrice") or info.get("regularMarketPrice")
            if not price:
                continue

            # ── Full history → true ATH ──────────────────
            hist_all = ticker.history(period="max", auto_adjust=True)
            if hist_all.empty:
                continue
            if hist_all.index.tz is not None:
                hist_all.index = hist_all.index.tz_localize(None)

            ath_idx  = hist_all["High"].idxmax()
            ath      = float(hist_all["High"].max())

            # ── 5-Year window → 5Y Low ───────────────────
            cutoff_5y = pd.Timestamp(datetime.now() - timedelta(days=5 * 365))
            hist_5y   = hist_all[hist_all.index >= cutoff_5y]
            if hist_5y.empty:
                hist_5y = hist_all   # fallback if stock < 5 years old

            low5y_idx = hist_5y["Low"].idxmin()
            low5y     = float(hist_5y["Low"].min())

            # ── Shares outstanding ───────────────────────
            shares   = info.get("sharesOutstanding")
            mkt_cap  = info.get("marketCap")                 # current
            mcap_ath = (shares * ath)   if shares else None  # approx MCap at ATH
            mcap_5yl = (shares * low5y) if shares else None  # approx MCap at 5Y low

            # ── PE at ATH / 5Y Low (estimated via current EPS) ──
            eps     = info.get("trailingEps")
            pe_ath  = (ath   / eps) if (eps and eps > 0) else None
            pe_5yl  = (low5y / eps) if (eps and eps > 0) else None

            # ── Free cash flow yield ─────────────────────
            fcf     = info.get("freeCashflow")
            fcf_yld = (fcf / mkt_cap * 100) if (fcf and mkt_cap and mkt_cap > 0) else None

            # ── Correction from ATH ──────────────────────
            corr = ((price - ath) / ath * 100) if ath else None

            d.update({
                "ok"           : True,
                "suffix"       : suffix,
                "name"         : (info.get("longName") or info.get("shortName") or symbol)[:32],
                # ── Current ──
                "price"        : price,
                "mkt_cap"      : mkt_cap,
                # ── ATH ──
                "ath"          : ath,
                "mcap_ath"     : mcap_ath,
                "ath_date"     : ath_idx.strftime("%d %b %Y"),
                "corr_pct"     : corr,
                # ── 5Y Low ──
                "low5y"        : low5y,
                "mcap_5yl"     : mcap_5yl,
                "low5y_date"   : low5y_idx.strftime("%d %b %Y"),
                # ── Valuation ──
                "pe"           : info.get("trailingPE"),
                "pe_ath"       : pe_ath,
                "pe_5yl"       : pe_5yl,
                "roce"         : None,          # filled later by Screener
                "profit_growth": (info.get("earningsGrowth") or 0) * 100 or None,
                "fcf_yield"    : fcf_yld,
                "margin"       : (info.get("profitMargins") or 0) * 100 or None,
                "div_yield"    : (info.get("dividendYield") or 0) * 100 or None,
            })
            return d

        except Exception as e:
            d["error"] = str(e)

    d.setdefault("error", "Symbol not found on NSE / BSE. Check spelling.")
    return d


# ────────────────────────────────────────────────────────────────
# DATA — SCREENER.IN  (ROCE only)
# ────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_roce(symbol: str):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/122.0.0.0 Safari/537.36"
        )
    }
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
                v = (li.find("span", class_="nowrap") or
                     li.find("span", class_="value"))
                if n and v and "roce" in n.get_text(strip=True).lower():
                    txt = re.sub(r"[₹,%\s]", "", v.get_text(strip=True))
                    m   = re.search(r"[\-\d.]+", txt)
                    if m:
                        return float(m.group())
        except Exception:
            pass
    return None


# ────────────────────────────────────────────────────────────────
# SESSION STATE
# ────────────────────────────────────────────────────────────────
if "stocks" not in st.session_state:
    st.session_state.stocks = []


# ────────────────────────────────────────────────────────────────
# HEADER
# ────────────────────────────────────────────────────────────────
st.markdown("## 📊 Indian Stock Table Tracker")
st.markdown("""
<div class="pill-row">
  <div class="pill">Price &amp; ATH/5Y Low → <b>Yahoo Finance</b></div>
  <div class="pill">ROCE → <b>Screener.in</b></div>
  <div class="pill">Cache: <b>YF 15 min</b> · <b>Screener 1 hr</b></div>
  <div class="pill">⚠️ PE @ ATH / 5Y Low = <b>estimate</b> (current EPS used)</div>
</div>
""", unsafe_allow_html=True)


# ────────────────────────────────────────────────────────────────
# CONTROLS ROW
# ────────────────────────────────────────────────────────────────
c1, c2, c3, c4 = st.columns([3, 1.2, 1.2, 1.2])

with c1:
    new_sym = st.text_input(
        "sym",
        placeholder="Type NSE symbol and press Enter  e.g.  RELIANCE   TCS   HDFCBANK",
        label_visibility="collapsed",
    )
with c2:
    add_btn = st.button("➕  Add Stock", type="primary", use_container_width=True)
with c3:
    refresh_btn = st.button(
        "🔄  Refresh All",
        use_container_width=True,
        disabled=(len(st.session_state.stocks) == 0),
    )
with c4:
    clear_btn = st.button(
        "🗑️  Clear All",
        use_container_width=True,
        disabled=(len(st.session_state.stocks) == 0),
    )

# ── Clear ──────────────────────────────────────────────────────
if clear_btn:
    st.session_state.stocks = []
    st.rerun()

# ── Refresh ────────────────────────────────────────────────────
if refresh_btn:
    syms = [s["symbol"] for s in st.session_state.stocks]
    st.session_state.stocks = []
    fetch_stock.clear()
    fetch_roce.clear()
    prog = st.progress(0, text="Refreshing…")
    for i, sym in enumerate(syms):
        prog.progress((i + 1) / len(syms), text=f"Refreshing {sym}…")
        data = fetch_stock(sym)
        if data["ok"]:
            data["roce"] = fetch_roce(sym)
        st.session_state.stocks.append(data)
    prog.empty()
    st.rerun()

# ── Add single stock ───────────────────────────────────────────
if add_btn and new_sym.strip():
    sym = new_sym.strip().upper()
    if sym in [s["symbol"] for s in st.session_state.stocks]:
        st.warning(f"**{sym}** is already in the table.")
    else:
        with st.spinner(f"Fetching {sym} from Yahoo Finance + Screener.in…"):
            data = fetch_stock(sym)
            if data["ok"]:
                data["roce"] = fetch_roce(sym)
                st.session_state.stocks.append(data)
                st.success(f"✅  **{sym}** — {data['name']} added!")
            else:
                st.error(f"❌  **{sym}** → {data.get('error', 'Not found')}")
    st.rerun()


# ────────────────────────────────────────────────────────────────
# QUICK-ADD BUTTONS
# ────────────────────────────────────────────────────────────────
POPULAR = [
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK",
    "WIPRO",    "ITC", "MARUTI",   "BHARTIARTL", "SUNPHARMA",
    "BAJFINANCE", "LT", "AXISBANK", "ASIANPAINT", "NESTLEIND",
]

st.markdown("**Quick add:**")
q_cols = st.columns(len(POPULAR))
for i, sym in enumerate(POPULAR):
    with q_cols[i]:
        already = sym in [s["symbol"] for s in st.session_state.stocks]
        if st.button(
            sym,
            key=f"q_{sym}",
            use_container_width=True,
            disabled=already,
            type="secondary",
        ):
            with st.spinner(f"Fetching {sym}…"):
                data = fetch_stock(sym)
                if data["ok"]:
                    data["roce"] = fetch_roce(sym)
                    st.session_state.stocks.append(data)
            st.rerun()

st.markdown("---")


# ────────────────────────────────────────────────────────────────
# MAIN TABLE
# ────────────────────────────────────────────────────────────────
if not st.session_state.stocks:
    st.markdown("""
    <div class="empty-state">
      <div style="font-size:3.5rem;margin-bottom:1rem;">📋</div>
      <div style="font-size:1.15rem;color:#7d8590;">Add stocks above to start tracking</div>
      <div style="font-size:0.85rem;margin-top:0.5rem;color:#3d444d;">
        Type any NSE symbol or click a Quick Add button
      </div>
    </div>
    """, unsafe_allow_html=True)

else:
    # ── Build table rows ────────────────────────────────────
    rows_html = ""
    for s in st.session_state.stocks:

        if not s.get("ok"):
            rows_html += (
                f'<tr>'
                f'<td>{s["symbol"]}</td>'
                f'<td colspan="18" style="color:#f85149;text-align:left;">'
                f'⚠️ {s.get("error","Unknown error")[:70]}'
                f'</td></tr>'
            )
            continue

        rows_html += f"""
        <tr>
          <td>{s['symbol']}</td>
          <td title="{s['name']}">{s['name']}</td>

          <td>{fmt_pr(s.get('price'))}</td>
          <td>{fmt_cr(s.get('mkt_cap'))}</td>

          <td class="up">{fmt_pr(s.get('ath'))}</td>
          <td>{fmt_cr(s.get('mcap_ath'))}</td>
          <td>{fmt_date(s.get('ath_date'))}</td>
          <td>{fmt_pct(s.get('corr_pct'), good_positive=False)}</td>

          <td class="down">{fmt_pr(s.get('low5y'))}</td>
          <td>{fmt_cr(s.get('mcap_5yl'))}</td>
          <td>{fmt_date(s.get('low5y_date'))}</td>

          <td>{fmt_pe(s.get('pe'))}</td>
          <td>{fmt_pe(s.get('pe_ath'), note='est')}</td>
          <td>{fmt_pe(s.get('pe_5yl'), note='est')}</td>

          <td>{fmt_pct(s.get('roce'))}</td>
          <td>{fmt_pct(s.get('profit_growth'))}</td>
          <td>{fmt_pct(s.get('fcf_yield'))}</td>
          <td>{fmt_pct(s.get('margin'))}</td>
          <td>{fmt_pct(s.get('div_yield'))}</td>
        </tr>
        """

    # ── Column group colours in header ──────────────────────
    st.markdown(f"""
    <div class="tbl-wrap">
      <table>
        <thead>
          <tr>
            <th>Symbol</th>
            <th>Company</th>

            <th>Current Price</th>
            <th>Market Cap</th>

            <th class="grp-ath">ATH Price</th>
            <th class="grp-ath">MCap @ ATH</th>
            <th class="grp-ath">ATH Date</th>
            <th class="grp-ath">Corr % from ATH</th>

            <th class="grp-5yl">5Y Low Price</th>
            <th class="grp-5yl">Min MCap (5Y)</th>
            <th class="grp-5yl">5Y Low Date</th>

            <th class="grp-val">PE (Now)</th>
            <th class="grp-val">PE @ ATH ⚠️</th>
            <th class="grp-val">PE @ 5Y Low ⚠️</th>

            <th>ROCE</th>
            <th>Profit Growth</th>
            <th>FCF Yield</th>
            <th>Net Margin</th>
            <th>Div Yield</th>
          </tr>
        </thead>
        <tbody>
          {rows_html}
        </tbody>
      </table>
    </div>
    <div style="font-size:0.68rem;color:#3d444d;margin-top:0.5rem;padding-left:2px;">
      ⚠️ <b>PE @ ATH</b> and <b>PE @ 5Y Low</b> are <b>estimates</b> —
      calculated as historical price ÷ <i>current</i> trailing EPS.
      True historical PE requires paid data sources (Bloomberg / Refinitiv).
      &nbsp;|&nbsp; ROCE from Screener.in &nbsp;|&nbsp; All other data from Yahoo Finance
    </div>
    """, unsafe_allow_html=True)

    # ── Remove individual stock ──────────────────────────────
    st.markdown("#### Remove a stock from table")
    max_show = min(len(st.session_state.stocks), 10)
    r_cols   = st.columns(max_show)
    for i, s in enumerate(st.session_state.stocks[:max_show]):
        with r_cols[i]:
            if st.button(
                f"✕ {s['symbol']}",
                key=f"del_{s['symbol']}",
                use_container_width=True,
            ):
                st.session_state.stocks = [
                    x for x in st.session_state.stocks
                    if x["symbol"] != s["symbol"]
                ]
                st.rerun()

    # ── Export as CSV ────────────────────────────────────────
    st.markdown("#### Download")
    export_rows = []
    for s in st.session_state.stocks:
        if not s.get("ok"):
            continue
        export_rows.append({
            "Symbol"             : s["symbol"],
            "Company"            : s["name"],
            "Current Price (₹)"  : s.get("price"),
            "Market Cap (Cr)"    : round(s["mkt_cap"] / 1e7, 0) if s.get("mkt_cap") else None,
            "ATH Price (₹)"      : s.get("ath"),
            "MCap at ATH (Cr)"   : round(s["mcap_ath"] / 1e7, 0) if s.get("mcap_ath") else None,
            "ATH Date"           : s.get("ath_date"),
            "Correction from ATH": round(s["corr_pct"], 2) if s.get("corr_pct") else None,
            "5Y Low Price (₹)"   : s.get("low5y"),
            "Min MCap 5Y (Cr)"   : round(s["mcap_5yl"] / 1e7, 0) if s.get("mcap_5yl") else None,
            "5Y Low Date"        : s.get("low5y_date"),
            "PE Current"         : round(s["pe"], 1) if s.get("pe") else None,
            "PE at ATH (est)"    : round(s["pe_ath"], 1) if s.get("pe_ath") else None,
            "PE at 5Y Low (est)" : round(s["pe_5yl"], 1) if s.get("pe_5yl") else None,
            "ROCE %"             : s.get("roce"),
            "Profit Growth %"    : round(s["profit_growth"], 1) if s.get("profit_growth") else None,
            "FCF Yield %"        : round(s["fcf_yield"], 2) if s.get("fcf_yield") else None,
            "Net Margin %"       : round(s["margin"], 1) if s.get("margin") else None,
            "Dividend Yield %"   : round(s["div_yield"], 2) if s.get("div_yield") else None,
        })

    if export_rows:
        df  = pd.DataFrame(export_rows)
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="⬇️  Download table as CSV",
            data=csv,
            file_name=f"stocks_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
            mime="text/csv",
        )


# ────────────────────────────────────────────────────────────────
# FOOTER
# ────────────────────────────────────────────────────────────────
st.markdown(
    "<div style='margin-top:2rem;color:#21262d;font-size:0.7rem;text-align:center;'>"
    "📡 Yahoo Finance · Screener.in &nbsp;|&nbsp; "
    "For educational purposes only — not financial advice"
    "</div>",
    unsafe_allow_html=True,
)
