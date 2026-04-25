"""
📊 Indian Stock Intelligence Dashboard
Sources: Yahoo Finance · Screener.in · NSE India API
"""

import streamlit as st
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import plotly.graph_objects as go
import time
import re
import json

# ══════════════════════════════════════════════════════════════
# PAGE CONFIG
# ══════════════════════════════════════════════════════════════
st.set_page_config(
    page_title="Indian Stock Intelligence",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ══════════════════════════════════════════════════════════════
# CUSTOM CSS — Dark Pro Theme
# ══════════════════════════════════════════════════════════════
st.markdown("""
<style>
    /* ── Global ── */
    .stApp { background-color: #0f172a; }
    .block-container { padding-top: 1.5rem; padding-bottom: 2rem; }
    
    /* ── Header ── */
    .main-title {
        font-size: 2.2rem; font-weight: 900;
        background: linear-gradient(135deg, #f97316 0%, #ef4444 50%, #ec4899 100%);
        -webkit-background-clip: text; -webkit-text-fill-color: transparent;
        letter-spacing: -0.5px;
    }
    .sub-title { color: #64748b; font-size: 0.85rem; margin-top: -0.5rem; margin-bottom: 1.5rem; }
    
    /* ── Metric Cards ── */
    .metric-card {
        background: linear-gradient(145deg, #1e293b, #162032);
        border: 1px solid #2d3f58;
        border-radius: 14px;
        padding: 1.1rem 1.3rem;
        margin-bottom: 0.9rem;
        position: relative;
        overflow: hidden;
        transition: border-color 0.2s;
    }
    .metric-card:hover { border-color: #3b82f6; }
    .metric-card::before {
        content: '';
        position: absolute; top: 0; left: 0;
        width: 3px; height: 100%;
        background: var(--accent, #3b82f6);
        border-radius: 14px 0 0 14px;
    }
    .m-label {
        font-size: 0.7rem; font-weight: 700; letter-spacing: 0.08em;
        text-transform: uppercase; color: #64748b; margin-bottom: 0.35rem;
    }
    .m-value { font-size: 1.45rem; font-weight: 800; color: #f1f5f9; line-height: 1.2; }
    .m-sub   { font-size: 0.78rem; color: #64748b; margin-top: 0.3rem; }
    .m-src   {
        display: inline-block; font-size: 0.6rem; font-weight: 700;
        background: #0f2744; color: #60a5fa; border-radius: 4px;
        padding: 0.05rem 0.35rem; margin-left: 0.4rem; vertical-align: middle;
    }
    
    /* ── Colour Classes ── */
    .c-green { color: #22c55e !important; }
    .c-red   { color: #f87171 !important; }
    .c-amber { color: #fbbf24 !important; }
    .c-blue  { color: #60a5fa !important; }

    /* ── Hero Banner ── */
    .hero-banner {
        background: linear-gradient(135deg, #1e293b 0%, #0f2040 100%);
        border: 1px solid #2d3f58; border-radius: 16px;
        padding: 1.5rem 2rem; margin-bottom: 1.5rem;
        display: flex; align-items: center; flex-wrap: wrap; gap: 2rem;
    }
    .hero-price { font-size: 2.6rem; font-weight: 900; color: #f1f5f9; }
    .hero-label { font-size: 0.7rem; font-weight: 700; text-transform: uppercase;
                  letter-spacing: 0.1em; color: #64748b; margin-bottom: 0.2rem; }
    .hero-sub   { font-size: 1.3rem; font-weight: 700; }
    .hero-cap   { font-size: 1.1rem; font-weight: 700; color: #94a3b8; }

    /* ── Source Legend ── */
    .legend {
        text-align: center; color: #334155; font-size: 0.72rem;
        margin-top: 2rem; padding-top: 1rem; border-top: 1px solid #1e293b;
    }
    
    /* ── Input override ── */
    div[data-testid="stTextInput"] input {
        background: #1e293b !important; border-color: #334155 !important;
        color: #f1f5f9 !important; border-radius: 10px !important;
        font-size: 1rem !important;
    }
    .stButton button { border-radius: 10px !important; }
</style>
""", unsafe_allow_html=True)


# ══════════════════════════════════════════════════════════════
# FORMATTERS
# ══════════════════════════════════════════════════════════════
def fmt_cr(val):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    cr = val / 1e7
    if cr >= 1_00_000:
        return f"₹{cr/1e5:.2f}L Cr"
    if cr >= 1_000:
        return f"₹{cr/1e3:.2f}K Cr"
    return f"₹{cr:,.0f} Cr"

def fmt_pct(val, dec=2):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{val:+.{dec}f}%" if val < 0 else f"{val:.{dec}f}%"

def fmt_num(val, dec=2, pre="", suf=""):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return "N/A"
    return f"{pre}{val:,.{dec}f}{suf}"

def ts_to_date(ts):
    """Convert various timestamp formats to readable date string"""
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            return datetime.fromtimestamp(ts).strftime('%d %b %Y')
        if hasattr(ts, 'strftime'):
            return ts.strftime('%d %b %Y')
        return str(ts)[:10]
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════
# DATA SOURCE 1: YAHOO FINANCE
# ══════════════════════════════════════════════════════════════
@st.cache_data(ttl=900, show_spinner=False)
def fetch_yf(symbol: str) -> dict:
    """Fetch core data from Yahoo Finance (NSE preferred, BSE fallback)"""
    result = {}
    
    for suffix in ['.NS', '.BO']:
        try:
            ticker = yf.Ticker(symbol + suffix)
            info = ticker.info
            
            price = info.get('currentPrice') or info.get('regularMarketPrice')
            if not price:
                continue
            
            # ── Historical for true ATH / ATL ──────────────
            hist = ticker.history(period='max', auto_adjust=True)
            if hist.empty:
                continue
            
            # Remove timezone for clean display
            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)
            
            ath_idx = hist['High'].idxmax()
            atl_idx = hist['Low'].idxmin()
            ath = float(hist['High'].max())
            atl = float(hist['Low'].min())

            # ── Financials ─────────────────────────────────
            mkt_cap = info.get('marketCap')
            fcf     = info.get('freeCashflow')
            fcf_yield = (fcf / mkt_cap * 100) if (fcf and mkt_cap and mkt_cap > 0) else None
            
            pe       = info.get('trailingPE')
            fwd_pe   = info.get('forwardPE')
            div_yld  = (info.get('dividendYield') or 0) * 100 or None
            beta     = info.get('beta')
            
            # ── Earnings date ──────────────────────────────
            result_date = None
            try:
                cal = ticker.calendar
                if cal is not None:
                    # cal can be a dict or DataFrame depending on yfinance version
                    if isinstance(cal, dict):
                        ed = cal.get('Earnings Date', [])
                        if ed:
                            result_date = ts_to_date(ed[0]) if not isinstance(ed[0], str) else str(ed[0])[:10]
                    elif isinstance(cal, pd.DataFrame) and not cal.empty:
                        if 'Earnings Date' in cal.columns:
                            result_date = str(cal['Earnings Date'].iloc[0])[:10]
                        elif 'Earnings Date' in cal.index:
                            val = cal.loc['Earnings Date']
                            result_date = str(val.iloc[0])[:10] if hasattr(val, 'iloc') else str(val)[:10]
            except Exception:
                pass
            
            result.update({
                'ok': True,
                'suffix': suffix,
                'exchange': 'NSE' if suffix == '.NS' else 'BSE',
                'name': info.get('longName') or info.get('shortName') or symbol,
                'sector': info.get('sector', 'N/A'),
                'industry': info.get('industry', 'N/A'),
                'current_price': price,
                'ath': ath,
                'ath_date': ath_idx.strftime('%d %b %Y'),
                'atl': atl,
                'atl_date': atl_idx.strftime('%d %b %Y'),
                'correction_pct': ((price - ath) / ath * 100) if ath else None,
                'mkt_cap': mkt_cap,
                'fcf': fcf,
                'fcf_yield': fcf_yield,
                'pe': pe,
                'fwd_pe': fwd_pe,
                'div_yield': div_yld,
                'ex_div_date': ts_to_date(info.get('exDividendDate')),
                'result_date': result_date,
                'hist': hist,
                'info': info,
                'beta': beta,
                'book_value': info.get('bookValue'),
                'roe': (info.get('returnOnEquity') or 0) * 100 or None,
                'profit_margin': (info.get('profitMargins') or 0) * 100 or None,
                'revenue_growth': (info.get('revenueGrowth') or 0) * 100 or None,
                'earnings_growth': (info.get('earningsGrowth') or 0) * 100 or None,
                'debt_equity': info.get('debtToEquity'),
                'pb': info.get('priceToBook'),
                '52w_high': info.get('fiftyTwoWeekHigh'),
                '52w_low': info.get('fiftyTwoWeekLow'),
            })
            return result
        
        except Exception as e:
            result['error'] = str(e)
    
    result['ok'] = False
    result.setdefault('error', 'Symbol not found on NSE/BSE')
    return result


# ══════════════════════════════════════════════════════════════
# DATA SOURCE 2: SCREENER.IN
# ══════════════════════════════════════════════════════════════
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_screener(symbol: str) -> dict:
    """Fetch ROCE, 5Y avg PE, historical ratios from Screener.in"""
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/122.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate, br',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    result = {'ok': False}
    
    for url in [
        f"https://www.screener.in/company/{symbol.upper()}/consolidated/",
        f"https://www.screener.in/company/{symbol.upper()}/",
    ]:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue
            if 'login' in resp.url:
                result['error'] = 'Screener.in login required'
                continue
            
            soup = BeautifulSoup(resp.text, 'lxml')
            
            # ── Current Ratios from #top-ratios ────────────
            raw = {}
            top = soup.find('ul', id='top-ratios')
            if top:
                for li in top.find_all('li'):
                    n = li.find('span', class_='name')
                    v = li.find('span', class_='nowrap') or li.find('span', class_='value')
                    if n and v:
                        key = n.get_text(strip=True).lower().strip()
                        val_text = v.get_text(separator=' ', strip=True)
                        val_text = re.sub(r'[₹,]', '', val_text).replace('Cr.', '').strip()
                        raw[key] = val_text
            
            # Extract ROCE
            roce = None
            for k, v in raw.items():
                if 'roce' in k:
                    try:
                        roce = float(re.search(r'[\d.]+', v).group())
                    except Exception:
                        pass
            
            # Current PE from screener (for cross-check)
            scr_pe = None
            for k, v in raw.items():
                if 'p/e' in k or ('stock' in k and 'p/e' in k):
                    try:
                        scr_pe = float(re.search(r'[\d.]+', v).group())
                    except Exception:
                        pass
            
            # ── Historical Ratios Table (ROCE + PE over years) ──
            roce_hist = []
            pe_hist   = []
            
            for section in soup.find_all(['section', 'div']):
                h = section.find(['h2', 'h3'])
                if h and 'ratio' in h.get_text().lower():
                    tables = section.find_all('table')
                    for table in tables:
                        rows = table.find_all('tr')
                        for row in rows:
                            cells = row.find_all(['td', 'th'])
                            if not cells:
                                continue
                            label = cells[0].get_text(strip=True).lower()
                            
                            if 'roce' in label:
                                for cell in cells[1:]:
                                    try:
                                        v = float(re.search(r'[\-\d.]+', cell.get_text(strip=True)).group())
                                        if -100 < v < 500:
                                            roce_hist.append(v)
                                    except Exception:
                                        pass
                            
                            if 'price to earning' in label or label in ('p/e', 'pe'):
                                for cell in cells[1:]:
                                    try:
                                        v = float(re.search(r'[\-\d.]+', cell.get_text(strip=True)).group())
                                        if 0 < v < 1000:
                                            pe_hist.append(v)
                                    except Exception:
                                        pass
            
            # Also scan ALL tables for P/E rows (some pages differ)
            if not pe_hist:
                for table in soup.find_all('table'):
                    for row in table.find_all('tr'):
                        cells = row.find_all(['td', 'th'])
                        if not cells:
                            continue
                        label = cells[0].get_text(strip=True).lower()
                        if 'price to earning' in label or label.startswith('p/e'):
                            for cell in cells[1:]:
                                try:
                                    v = float(re.search(r'[\-\d.]+', cell.get_text(strip=True)).group())
                                    if 0 < v < 1000:
                                        pe_hist.append(v)
                                except Exception:
                                    pass
            
            # 5Y averages (last 5 data points)
            pe_5y_avg = float(np.mean(pe_hist[-5:])) if len(pe_hist) >= 2 else None
            
            # ROCE growth = latest - oldest in window
            roce_growth = None
            if len(roce_hist) >= 2:
                window = roce_hist[-5:] if len(roce_hist) >= 5 else roce_hist
                roce_growth = window[-1] - window[0]
            
            # Latest ROCE from history (more reliable than top-ratios scrape)
            if roce_hist:
                roce = roce or roce_hist[-1]
            
            result.update({
                'ok': True,
                'roce': roce,
                'roce_hist': roce_hist,
                'roce_growth': roce_growth,
                'pe_hist': pe_hist,
                'pe_5y_avg': pe_5y_avg,
                'scr_pe': scr_pe,
                'raw': raw,
            })
            return result
        
        except Exception as e:
            result['error'] = str(e)
    
    return result


# ══════════════════════════════════════════════════════════════
# DATA SOURCE 3: NSE INDIA API
# ══════════════════════════════════════════════════════════════
@st.cache_data(ttl=1800, show_spinner=False)
def fetch_nse(symbol: str) -> dict:
    """Fetch corporate actions & result dates from NSE India"""
    result = {'ok': False, 'div_date': None, 'result_date': None, 'actions': []}
    
    session = requests.Session()
    headers = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/122.0.0.0 Safari/537.36'
        ),
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'en-US,en;q=0.9',
        'Referer': 'https://www.nseindia.com/',
        'X-Requested-With': 'XMLHttpRequest',
    }
    
    try:
        # Warm-up: get cookies from the main page
        session.get('https://www.nseindia.com', headers=headers, timeout=12)
        time.sleep(0.8)
        
        today = datetime.now()
        sym = symbol.upper()
        
        # ── Corporate Actions ───────────────────────────────
        url = (
            f"https://www.nseindia.com/api/corporates-corporateActions"
            f"?index=equities&symbol={sym}"
        )
        resp = session.get(url, headers=headers, timeout=12)
        if resp.status_code == 200:
            try:
                actions = resp.json()
                result['actions'] = actions if isinstance(actions, list) else []
                
                future_divs    = []
                future_results = []
                
                for a in result['actions']:
                    if not isinstance(a, dict):
                        continue
                    purpose = (
                        a.get('subject', '') + ' ' +
                        a.get('purpose', '') + ' ' +
                        a.get('remarks', '')
                    ).lower()
                    date_str = a.get('exDate') or a.get('ex_date') or ''
                    
                    parsed = None
                    for fmt in ['%d-%b-%Y', '%Y-%m-%d', '%d/%m/%Y', '%b %d, %Y']:
                        try:
                            parsed = datetime.strptime(date_str.strip(), fmt)
                            break
                        except Exception:
                            pass
                    
                    if parsed and parsed >= today:
                        if 'dividend' in purpose:
                            future_divs.append((parsed, a.get('remarks', '') or purpose))
                        if any(k in purpose for k in ['result', 'quarterly', 'financial results', 'board meeting']):
                            future_results.append((parsed, purpose))
                
                if future_divs:
                    future_divs.sort(key=lambda x: x[0])
                    result['div_date']     = future_divs[0][0].strftime('%d %b %Y')
                    result['div_remarks']  = future_divs[0][1]
                
                if future_results:
                    future_results.sort(key=lambda x: x[0])
                    result['result_date']  = future_results[0][0].strftime('%d %b %Y')
                
                result['ok'] = True
            except Exception:
                pass
        
        # ── Event Calendar (Result Dates) ───────────────────
        url2 = "https://www.nseindia.com/api/event-calendar?index=equities"
        resp2 = session.get(url2, headers=headers, timeout=12)
        if resp2.status_code == 200:
            try:
                events = resp2.json()
                if isinstance(events, list):
                    for ev in events:
                        if not isinstance(ev, dict):
                            continue
                        if ev.get('symbol', '').upper() != sym:
                            continue
                        purpose  = ev.get('purpose', '').lower()
                        date_str = ev.get('date', '') or ev.get('bDDate', '')
                        
                        if any(k in purpose for k in ['result', 'quarterly', 'financial', 'board meeting']):
                            for fmt in ['%d-%b-%Y', '%Y-%m-%d', '%d/%m/%Y']:
                                try:
                                    ev_date = datetime.strptime(date_str.strip(), fmt)
                                    if ev_date >= today:
                                        result['result_date'] = ev_date.strftime('%d %b %Y')
                                        result['ok'] = True
                                        break
                                except Exception:
                                    pass
            except Exception:
                pass
    
    except Exception as e:
        result['error'] = str(e)
    
    return result


# ══════════════════════════════════════════════════════════════
# PRICE CHART
# ══════════════════════════════════════════════════════════════
def make_chart(hist: pd.DataFrame, symbol: str, ath: float, ath_date: str):
    if hist is None or hist.empty:
        return None
    
    # 5-year window
    cutoff  = pd.Timestamp(datetime.now() - timedelta(days=5 * 365))
    h       = hist[hist.index >= cutoff].copy()
    if h.empty:
        h = hist.copy()
    
    # Low of 5Y window
    low_5y      = float(h['Low'].min())
    low_5y_date = h['Low'].idxmin().strftime('%d %b %Y')
    
    fig = go.Figure()
    
    # Price area
    fig.add_trace(go.Scatter(
        x=h.index, y=h['Close'],
        mode='lines', name='Close Price',
        line=dict(color='#3b82f6', width=1.8),
        fill='tozeroy',
        fillcolor='rgba(59,130,246,0.06)',
        hovertemplate='<b>%{x|%d %b %Y}</b><br>₹%{y:,.2f}<extra></extra>',
    ))
    
    # ATH reference
    fig.add_hline(
        y=ath, line_dash='dot', line_color='#22c55e', line_width=1.2,
        annotation_text=f"  ATH ₹{ath:,.0f}  ({ath_date})",
        annotation_position='top left',
        annotation_font=dict(color='#22c55e', size=11),
    )
    
    # 5Y low reference
    fig.add_hline(
        y=low_5y, line_dash='dot', line_color='#f87171', line_width=1.2,
        annotation_text=f"  5Y Low ₹{low_5y:,.0f}  ({low_5y_date})",
        annotation_position='bottom left',
        annotation_font=dict(color='#f87171', size=11),
    )
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        font=dict(color='#64748b', family='Inter, sans-serif', size=11),
        margin=dict(l=0, r=20, t=40, b=0),
        height=360,
        showlegend=False,
        title=dict(
            text=f"<b style='color:#f1f5f9'>{symbol}</b>  —  5-Year Price History",
            font=dict(size=14, color='#94a3b8'),
            x=0.01,
        ),
        xaxis=dict(
            showgrid=False, showline=True, linecolor='#1e293b',
            tickformat='%b %Y', tickfont=dict(size=10),
            rangeslider=dict(visible=False),
        ),
        yaxis=dict(
            showgrid=True, gridcolor='rgba(30,41,59,0.8)',
            tickformat=',.0f', tickprefix='₹',
            tickfont=dict(size=10),
            side='right',
        ),
        hovermode='x unified',
    )
    return fig


# ══════════════════════════════════════════════════════════════
# METRIC CARD HTML BUILDER
# ══════════════════════════════════════════════════════════════
def card(title, value, sub="", color_class="", source="", accent="#3b82f6", icon=""):
    cc = f"class='m-value {color_class}'" if color_class else "class='m-value'"
    src_html = f"<span class='m-src'>{source}</span>" if source else ""
    sub_html = f"<div class='m-sub'>{sub}</div>" if sub else ""
    return f"""
    <div class='metric-card' style='--accent:{accent};'>
        <div class='m-label'>{icon} {title}{src_html}</div>
        <div {cc}>{value}</div>
        {sub_html}
    </div>
    """


# ══════════════════════════════════════════════════════════════
# SIDEBAR — Quick Reference
# ══════════════════════════════════════════════════════════════
with st.sidebar:
    st.markdown("### 📖 Quick Symbols")
    popular = {
        "🛢️ Reliance": "RELIANCE",
        "💻 TCS": "TCS",
        "🏦 HDFC Bank": "HDFCBANK",
        "📱 Infosys": "INFY",
        "🏦 ICICI Bank": "ICICIBANK",
        "🚗 Maruti": "MARUTI",
        "🏭 L&T": "LT",
        "🛍️ ITC": "ITC",
        "💊 Sun Pharma": "SUNPHARMA",
        "⚡ Adani Green": "ADANIGREEN",
        "🏗️ Adani Ports": "ADANIPORTS",
        "📡 Airtel": "BHARTIARTL",
        "🏠 Bajaj Finance": "BAJFINANCE",
        "🔑 Asian Paints": "ASIANPAINT",
        "🥤 Nestle": "NESTLEIND",
    }
    for label, sym in popular.items():
        if st.button(label, key=f"btn_{sym}", use_container_width=True):
            st.session_state['queued_symbol'] = sym
    
    st.markdown("---")
    st.markdown("**Data Sources**")
    st.markdown("""
    - 🟢 **Yahoo Finance** — Price, ATH, FCF, PE, Div  
    - 🔵 **Screener.in** — ROCE, 5Y Avg PE  
    - 🟣 **NSE India API** — Result & Dividend dates  
    """)
    st.markdown("---")
    st.caption("Cache: YF 15min · SCR 1hr · NSE 30min")
    st.caption("⚠️ Educational only. Not financial advice.")


# ══════════════════════════════════════════════════════════════
# MAIN UI
# ══════════════════════════════════════════════════════════════
st.markdown("<div class='main-title'>📊 Indian Stock Intelligence</div>", unsafe_allow_html=True)
st.markdown(
    "<div class='sub-title'>Real-time data · Yahoo Finance &nbsp;·&nbsp; Screener.in &nbsp;·&nbsp; NSE India API</div>",
    unsafe_allow_html=True,
)

# ── Session State ───────────────────────────────────────────
if 'fetched_symbol' not in st.session_state:
    st.session_state['fetched_symbol'] = None

# Handle sidebar quick-pick
if 'queued_symbol' in st.session_state:
    st.session_state['fetched_symbol'] = st.session_state.pop('queued_symbol')

# ── Search Bar ──────────────────────────────────────────────
c1, c2 = st.columns([5, 1])
with c1:
    raw_input = st.text_input(
        "NSE Symbol",
        value=st.session_state.get('fetched_symbol', ''),
        placeholder="Enter NSE symbol e.g. RELIANCE, TCS, HDFCBANK, INFY …",
        label_visibility="collapsed",
    )
with c2:
    go_btn = st.button("🔍 Analyse", type="primary", use_container_width=True)

if go_btn and raw_input.strip():
    st.session_state['fetched_symbol'] = raw_input.strip().upper()

symbol = st.session_state.get('fetched_symbol')

# ════════════════════════════════════════════════════════════
# RESULTS
# ════════════════════════════════════════════════════════════
if symbol:
    # ── Fetch All Sources ────────────────────────────────
    col_s1, col_s2, col_s3 = st.columns(3)
    
    with col_s1:
        with st.spinner("⚡ Yahoo Finance …"):
            yf_d = fetch_yf(symbol)
    
    if not yf_d.get('ok'):
        st.error(f"❌ **{symbol}** not found on NSE/BSE. Check the symbol and try again.")
        st.info("💡 Examples: RELIANCE, TCS, INFY, HDFCBANK, ITC, WIPRO, BHARTIARTL, MARUTI")
        st.stop()
    
    with col_s2:
        with st.spinner("📊 Screener.in …"):
            sc_d = fetch_screener(symbol)
    
    with col_s3:
        with st.spinner("🏛️ NSE India …"):
            nse_d = fetch_nse(symbol)
    
    # ── Company Header ───────────────────────────────────
    name    = yf_d.get('name', symbol)
    suffix  = yf_d.get('suffix', '.NS')
    sector  = yf_d.get('sector', '')
    price   = yf_d.get('current_price', 0)
    mkt_cap = yf_d.get('mkt_cap')
    corr    = yf_d.get('correction_pct', 0) or 0
    ath     = yf_d.get('ath', 0)
    atl     = yf_d.get('atl', 0)
    ath_d   = yf_d.get('ath_date', 'N/A')
    atl_d   = yf_d.get('atl_date', 'N/A')
    
    corr_color = "#22c55e" if corr > -15 else "#fbbf24" if corr > -40 else "#f87171"
    
    st.markdown(f"""
    <div style='margin: 1.2rem 0 0.5rem 0;'>
        <span style='font-size:1.7rem;font-weight:900;color:#f1f5f9;'>{name}</span>
        <span style='font-size:0.9rem;color:#475569;margin-left:0.6rem;'>{symbol}{suffix}</span>
        <span style='font-size:0.85rem;color:#64748b;margin-left:1rem;'>{sector}</span>
    </div>
    """, unsafe_allow_html=True)
    
    # ── Hero Banner ─────────────────────────────────────
    st.markdown(f"""
    <div class='hero-banner'>
        <div>
            <div class='hero-label'>Current Price</div>
            <div class='hero-price'>₹{price:,.2f}</div>
        </div>
        <div>
            <div class='hero-label'>Correction from ATH</div>
            <div class='hero-sub' style='color:{corr_color};'>{corr:.1f}%</div>
            <div style='font-size:0.75rem;color:#475569;'>from ₹{ath:,.2f}</div>
        </div>
        <div>
            <div class='hero-label'>Market Cap</div>
            <div class='hero-sub c-blue'>{fmt_cr(mkt_cap)}</div>
        </div>
        <div>
            <div class='hero-label'>Exchange</div>
            <div class='hero-sub' style='color:#94a3b8;'>{yf_d.get('exchange','')}</div>
            <div style='font-size:0.75rem;color:#475569;'>{yf_d.get('industry','')}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # ── 3-Column Metrics Grid ────────────────────────────
    col1, col2, col3 = st.columns(3, gap="medium")
    
    with col1:
        # ATH
        st.markdown(card(
            "ALL TIME HIGH", f"₹{ath:,.2f}",
            sub=f"📅 {ath_d}",
            color_class="c-green", source="YF", accent="#22c55e", icon="🏆"
        ), unsafe_allow_html=True)
        
        # PE + 5Y Avg PE
        pe = yf_d.get('pe')
        pe_5y = sc_d.get('pe_5y_avg')
        pe_str  = f"{pe:.1f}×" if pe else "N/A"
        pe5_str = f"5Y Avg: {pe_5y:.1f}×" if pe_5y else "5Y Avg: N/A  (Screener.in)"
        
        if pe and pe_5y:
            if pe > pe_5y * 1.25:
                pe_c, pe_acc = "c-red", "#ef4444"
            elif pe < pe_5y * 0.80:
                pe_c, pe_acc = "c-green", "#22c55e"
            else:
                pe_c, pe_acc = "c-amber", "#fbbf24"
        else:
            pe_c, pe_acc = "", "#6366f1"
        
        st.markdown(card(
            "P / E RATIO", pe_str, sub=pe5_str,
            color_class=pe_c, source="YF+SCR", accent=pe_acc, icon="📐"
        ), unsafe_allow_html=True)
        
        # Result Date
        rdate = nse_d.get('result_date') or yf_d.get('result_date') or "Check NSE"
        st.markdown(card(
            "NEXT RESULT DATE", rdate,
            sub="Board meeting / Quarterly results",
            source="NSE+YF", accent="#8b5cf6", icon="📋"
        ), unsafe_allow_html=True)
    
    with col2:
        # ATL
        st.markdown(card(
            "ALL TIME LOW", f"₹{atl:,.2f}",
            sub=f"📅 {atl_d}",
            color_class="c-red", source="YF", accent="#ef4444", icon="📉"
        ), unsafe_allow_html=True)
        
        # ROCE + Growth
        roce = sc_d.get('roce')
        roce_growth = sc_d.get('roce_growth')
        roce_str  = f"{roce:.1f}%" if roce is not None else "N/A"
        
        if roce_growth is not None:
            g_sign = "+" if roce_growth >= 0 else ""
            roce_sub = f"5Y Δ: {g_sign}{roce_growth:.1f}pp"
        else:
            roce_sub = "Screener.in data"
        
        if roce is not None:
            if roce >= 20:
                rc, ra = "c-green", "#22c55e"
            elif roce >= 12:
                rc, ra = "c-amber", "#fbbf24"
            else:
                rc, ra = "c-red", "#ef4444"
        else:
            rc, ra = "", "#0ea5e9"
        
        st.markdown(card(
            "ROCE", roce_str, sub=roce_sub,
            color_class=rc, source="SCR", accent=ra, icon="⚙️"
        ), unsafe_allow_html=True)
        
        # Dividend Yield
        div_yld = yf_d.get('div_yield')
        div_str = f"{div_yld:.2f}%" if div_yld else "N/A"
        div_dt  = nse_d.get('div_date') or yf_d.get('ex_div_date') or "N/A"
        
        st.markdown(card(
            "DIVIDEND YIELD", div_str,
            sub=f"Ex-Date: {div_dt}",
            color_class="c-green" if div_yld and div_yld > 1 else "",
            source="YF+NSE", accent="#10b981", icon="💰"
        ), unsafe_allow_html=True)
    
    with col3:
        # Free Cash Flow + Yield
        fcf = yf_d.get('fcf')
        fcy = yf_d.get('fcf_yield')
        fcf_str = fmt_cr(fcf) if fcf else "N/A"
        fcy_str = f"FCF Yield: {fcy:.2f}%" if fcy else "FCF Yield: N/A"
        
        if fcf is not None:
            fc_c = "c-green" if fcf > 0 else "c-red"
            fc_a = "#22c55e" if fcf > 0 else "#ef4444"
        else:
            fc_c, fc_a = "", "#f97316"
        
        st.markdown(card(
            "FREE CASH FLOW", fcf_str, sub=fcy_str,
            color_class=fc_c, source="YF", accent=fc_a, icon="💵"
        ), unsafe_allow_html=True)
        
        # Market Cap breakdown
        st.markdown(card(
            "MARKET CAP", fmt_cr(mkt_cap),
            sub=f"52W: ₹{yf_d.get('52w_low',0) or 0:,.0f} – ₹{yf_d.get('52w_high',0) or 0:,.0f}",
            source="YF", accent="#0ea5e9", icon="🏛️"
        ), unsafe_allow_html=True)
        
        # Dividend Date
        div_remarks = nse_d.get('div_remarks', '')
        div_date_display = nse_d.get('div_date') or yf_d.get('ex_div_date') or "N/A"
        
        st.markdown(card(
            "DIVIDEND EX-DATE", div_date_display,
            sub=div_remarks[:55] + "…" if div_remarks and len(div_remarks) > 55 else div_remarks,
            source="NSE+YF", accent="#a855f7", icon="📅"
        ), unsafe_allow_html=True)
    
    # ── Additional Ratios Row ────────────────────────────
    st.markdown("---")
    st.markdown("#### 📊 Additional Metrics")
    c4, c5, c6, c7 = st.columns(4, gap="medium")
    
    with c4:
        roe = yf_d.get('roe')
        st.markdown(card(
            "ROE", f"{roe:.1f}%" if roe else "N/A",
            color_class="c-green" if roe and roe > 15 else "c-amber" if roe else "",
            source="YF", icon="📈"
        ), unsafe_allow_html=True)
    
    with c5:
        pb = yf_d.get('pb')
        st.markdown(card(
            "PRICE / BOOK", f"{pb:.2f}×" if pb else "N/A",
            source="YF", icon="📚"
        ), unsafe_allow_html=True)
    
    with c6:
        eg = yf_d.get('earnings_growth')
        st.markdown(card(
            "EARNINGS GROWTH (YoY)", fmt_pct(eg),
            color_class="c-green" if eg and eg > 0 else "c-red" if eg else "",
            source="YF", accent="#f97316", icon="📈"
        ), unsafe_allow_html=True)
    
    with c7:
        beta = yf_d.get('beta')
        b_color = "c-red" if beta and beta > 1.5 else "c-green" if beta and beta < 0.8 else "c-amber"
        st.markdown(card(
            "BETA", f"{beta:.2f}" if beta else "N/A",
            sub="vs Nifty 50",
            color_class=b_color, source="YF", icon="⚡"
        ), unsafe_allow_html=True)
    
    # ── Price Chart ─────────────────────────────────────
    st.markdown("---")
    fig = make_chart(yf_d.get('hist'), symbol, ath, ath_d)
    if fig:
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    
    # ── Data Quality Indicators ──────────────────────────
    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        st.success("✅ Yahoo Finance — Connected")
    with col_s2:
        if sc_d.get('ok'):
            st.success("✅ Screener.in — Connected")
        else:
            msg = sc_d.get('error', 'Could not connect')
            st.warning(f"⚠️ Screener.in — {msg[:40]}")
    with col_s3:
        if nse_d.get('ok'):
            st.success("✅ NSE India API — Connected")
        else:
            st.warning("⚠️ NSE India API — Limited data")
    
    # ── Footer ──────────────────────────────────────────
    st.markdown("""
    <div class='legend'>
        📡 <b>Sources:</b> Yahoo Finance (yfinance) &nbsp;·&nbsp; Screener.in &nbsp;·&nbsp; NSE India API &nbsp;&nbsp;|&nbsp;&nbsp;
        ⏱️ <b>Cache TTL:</b> YF 15 min · Screener 1 hr · NSE 30 min &nbsp;&nbsp;|&nbsp;&nbsp;
        ⚠️ For educational use only — not financial advice
    </div>
    """, unsafe_allow_html=True)

else:
    # ── Landing Page ─────────────────────────────────────
    st.markdown("""
    <div style='text-align:center;padding:5rem 2rem 3rem;'>
        <div style='font-size:5rem;margin-bottom:1.5rem;'>📊</div>
        <div style='font-size:1.4rem;font-weight:600;color:#94a3b8;margin-bottom:0.5rem;'>
            Enter an NSE symbol above to begin
        </div>
        <div style='color:#475569;font-size:0.95rem;'>
            or pick a stock from the left sidebar
        </div>
        <div style='margin-top:2rem;color:#334155;font-size:0.85rem;'>
            RELIANCE &nbsp;·&nbsp; TCS &nbsp;·&nbsp; INFY &nbsp;·&nbsp; HDFCBANK &nbsp;·&nbsp;
            ICICIBANK &nbsp;·&nbsp; ITC &nbsp;·&nbsp; MARUTI &nbsp;·&nbsp; BHARTIARTL
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Feature cards
    f1, f2, f3 = st.columns(3, gap="large")
    for col, icon, title, desc in [
        (f1, "🏆", "ATH / ATL + Dates", "True all-time high & low with exact dates from full historical data"),
        (f2, "⚙️", "ROCE + 5Y Growth", "Return on Capital Employed with 5-year trend from Screener.in"),
        (f3, "📅", "Live Corporate Actions", "Next result date & dividend ex-date from NSE India API"),
    ]:
        with col:
            st.markdown(f"""
            <div class='metric-card' style='text-align:center;padding:1.5rem;'>
                <div style='font-size:2rem;margin-bottom:0.5rem;'>{icon}</div>
                <div style='font-weight:700;color:#f1f5f9;margin-bottom:0.4rem;'>{title}</div>
                <div style='color:#64748b;font-size:0.85rem;'>{desc}</div>
            </div>
            """, unsafe_allow_html=True)
