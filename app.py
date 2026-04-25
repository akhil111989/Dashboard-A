import streamlit as st
import yfinance as yf
import requests
from bs4 import BeautifulSoup
import pandas as pd
import numpy as np
import re
from datetime import datetime, timedelta

st.set_page_config(page_title="📊 Stock Tracker", page_icon="📊", layout="wide")

# ─────────────────────────────────────────────
# (YOUR CSS — unchanged)
# ─────────────────────────────────────────────
st.markdown("""<style>
/* KEEP YOUR ENTIRE CSS EXACTLY AS IT IS */
</style>""", unsafe_allow_html=True)


# ═══════════════════════════════════════════════════
# DATA FETCHING
# ═══════════════════════════════════════════════════

@st.cache_data(ttl=900, show_spinner=False)
def get_stock_data(symbol: str) -> dict:
    d = {"symbol": symbol, "ok": False}

    for suffix in [".NS", ".BO"]:
        try:
            t = yf.Ticker(symbol + suffix)

            # FIX 1: safer info fetch
            try:
                info = t.get_info()
            except Exception:
                info = {}

            price = info.get("currentPrice") or info.get("regularMarketPrice")
            if not price:
                continue

            hist = t.history(period="max", auto_adjust=True)
            if hist.empty:
                continue

            if hist.index.tz is not None:
                hist.index = hist.index.tz_localize(None)

            ath_idx = hist["High"].idxmax()
            ath = float(hist["High"].max())

            cut = pd.Timestamp(datetime.now() - timedelta(days=5 * 365))
            h5 = hist[hist.index >= cut] if not hist[hist.index >= cut].empty else hist
            low5_idx = h5["Low"].idxmin()
            low5 = float(h5["Low"].min())

            shares = info.get("sharesOutstanding")
            mktcap = info.get("marketCap")
            eps = info.get("trailingEps")

            # ── FIX 2: FCF SAFE LOGIC ──
            fcf = info.get("freeCashflow")

            if fcf is None:
                ocf = info.get("operatingCashflow")
                capex = info.get("capitalExpenditures")
                if ocf is not None and capex is not None:
                    fcf = ocf - abs(capex)

            if fcf is None:
                try:
                    cf = t.cashflow
                    if cf is not None and not cf.empty:
                        ocf_row = next((cf.loc[r] for r in cf.index if "operating" in r.lower()), None)
                        capex_row = next((cf.loc[r] for r in cf.index if "capital" in r.lower()), None)
                        if ocf_row is not None and capex_row is not None:
                            fcf = float(ocf_row.iloc[0]) - abs(float(capex_row.iloc[0]))
                except:
                    pass

            fcf_yield = (fcf / mktcap * 100) if (fcf and mktcap and mktcap > 0) else None

            d.update({
                "ok": True,
                "name": (info.get("longName") or info.get("shortName") or symbol)[:30],
                "price": price,
                "mktcap": mktcap,
                "ath": ath,
                "ath_date": ath_idx.strftime("%d %b %Y"),
                "mktcap_ath": shares * ath if shares else None,
                "corr": ((price - ath) / ath * 100) if ath else None,
                "low5": low5,
                "low5_date": low5_idx.strftime("%d %b %Y"),
                "mktcap_low5": shares * low5 if shares else None,
                "pe": info.get("trailingPE"),
                "pe_ath": (ath / eps) if (eps and eps > 0) else None,
                "pe_low5": (low5 / eps) if (eps and eps > 0) else None,
                "roce": None,
                "profit_growth": (info.get("earningsGrowth") or 0) * 100 or None,
                "fcf": fcf,
                "fcf_yield": fcf_yield,
                "margin": (info.get("profitMargins") or 0) * 100 or None,
                "div_yield": (info.get("dividendYield") or 0) * 100 or None,
            })

            return d

        except Exception as e:
            d["error"] = str(e)

    d.setdefault("error", "Symbol not found")
    return d


@st.cache_data(ttl=3600, show_spinner=False)
def get_roce(symbol: str):
    headers = {"User-Agent": "Mozilla/5.0"}
    for url in [
        f"https://www.screener.in/company/{symbol.upper()}/consolidated/",
        f"https://www.screener.in/company/{symbol.upper()}/",
    ]:
        try:
            r = requests.get(url, headers=headers, timeout=12)
            if r.status_code != 200:
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
        except:
            pass
    return None


# ═══════════════════════════════════════════════════
# BUFFETT RATING (UNCHANGED BUT SAFE USAGE)
# ═══════════════════════════════════════════════════
def buffett_rating(s: dict):
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
            score += 2; notes.append("Excellent ROCE")
        elif roce >= 15:
            score += 1; notes.append("Good ROCE")

    if growth is not None:
        if growth >= 15:
            score += 2; notes.append("Strong growth")
        elif growth >= 5:
            score += 1; notes.append("Moderate growth")

    if fcfy is not None:
        if fcfy >= 5:
            score += 2; notes.append("Rich FCF")
        elif fcfy >= 2:
            score += 1; notes.append("Positive FCF")

    if margin is not None:
        if margin >= 20:
            score += 2; notes.append("Excellent margins")
        elif margin >= 10:
            score += 1; notes.append("Decent margins")

    if pe is not None:
        if 0 < pe <= 20:
            score += 1; notes.append("Reasonable PE")

    if corr is not None:
        if corr <= -30:
            score += 1; notes.append("Margin of safety")

    if score >= 7:
        rating, css = "BUY", "buy"
    elif score >= 4:
        rating, css = "HOLD", "hold"
    else:
        rating, css = "SELL", "sell"

    return rating, css, score, " · ".join(notes[:3])


# ═══════════════════════════════════════════════════
# WATCHLIST LOOP FIX (IMPORTANT FIX HERE)
# ═══════════════════════════════════════════════════

rows_html = ""
export_rows = []

for s in st.session_state.get("watchlist", []):

    if not s.get("ok"):
        continue

    # FIX 3: compute ONCE only
    rating, css, score, reason = buffett_rating(s)

    sym = s["symbol"]

    rows_html += f"""
    <tr>
      <td>{sym}</td>
      <td>{s['name']}</td>
      <td><span class="badge {css}">{rating}</span></td>
      <td>{score}/10</td>
      <td>{s.get('price')}</td>
      <td>{s.get('mktcap')}</td>
    </tr>
    """

    export_rows.append(s)


st.markdown(f"<div class='tbl-outer'><table><tbody>{rows_html}</tbody></table></div>", unsafe_allow_html=True)
