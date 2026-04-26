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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;900&display=swap');
* { font-family: 'Inter', sans-serif; }
.stApp { background: #0a0e1a; }
.block-container { padding-top: 1rem; max-width: 100% !important; }
h1,h2,h3 { color: #f0f6fc !important; font-weight: 900 !important; }
.stButton > button { border-radius: 10px !important; font-weight: 700 !important; }
div[data-testid="stTextInput"] input {
    background: #161b22 !important; border: 1px solid #30363d !important;
    color: #f0f6fc !important; border-radius: 10px !important;
    font-size: 0.95rem !important; padding: 0.6rem 1rem !important;
}
.stDownloadButton > button {
    background: #1f6feb !important; color: white !important;
    border-radius: 10px !important; font-weight: 700 !important;
}
.top-stats { display:flex; gap:1rem; flex-wrap:wrap; margin:0.5rem 0 1.2rem 0; }
.stat-pill {
    background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 0.5rem 1.1rem; display:flex; flex-direction:column; min-width:110px;
}
.stat-pill .label { font-size:0.62rem; font-weight:700; text-transform:uppercase; letter-spacing:0.08em; color:#7d8590; margin-bottom:2px; }
.stat-pill .val   { font-size:1.1rem; font-weight:800; color:#f0f6fc; }
.tbl-outer { overflow-x:auto; border-radius:14px; border:1px solid #21262d; margin-top:0.8rem; }
table { width:100%; border-collapse:collapse; background:#0d1117; }
thead tr { background:#161b22; }
th {
    padding:11px 13px; font-size:0.62rem; font-weight:800; text-transform:uppercase;
    letter-spacing:0.07em; color:#7d8590; text-align:right; white-space:nowrap;
    border-bottom:2px solid #21262d;
}
th:first-child, th:nth-child(2) { text-align:left; }
td {
    padding:10px 13px; font-size:0.82rem; color:#c9d1d9;
    border-bottom:1px solid #161b22; text-align:right; white-space:nowrap;
}
td:first-child { color:#58a6ff; font-weight:800; text-align:left; }
td:nth-child(2) { color:#e6edf3; text-align:left; font-size:0.75rem; max-width:155px; overflow:hidden; text-overflow:ellipsis; }
tbody tr:hover { background:#161b22 !important; }
tbody tr:last-child td { border-bottom:none; }
.badge { display:inline-block; padding:3px 12px; border-radius:20px; font-size:0.72rem; font-weight:800; letter-spacing:0.05em; }
.buy  { background:#0d2d1a; color:#3fb950; border:1px solid #238636; }
.hold { background:#2d2000; color:#e3b341; border:1px solid #9e6a03; }
.sell { background:#2d1115; color:#f85149; border:1px solid #da3633; }
.g  { color:#3fb950; font-weight:700; }
.r  { color:#f85149; font-weight:700; }
.m  { color:#7d8590; font-size:0.74rem; }
.na { color:#3d444d; }
.empty { text-align:center; padding:5rem 0; color:#484f58; }
</style>
""", unsafe_allow_html=True)


# ── Fetch Yahoo Finance ────────────────────────────────────────
@st.cache_data(ttl=900, show_spinner=False)
def get_stock_data(symbol: str) -> dict:
    d = {"symbol": symbol, "ok": False}
    for suffix in [".NS", ".BO"]:
        try:
            t     = yf.Ticker(symbol + suffix)
            info  = t.info
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
            if h5.empty:
                h5 = hist
            low5_idx = h5["Low"].idxmin()
            low5     = float(h5["Low"].min())

            shares = info.get("sharesOutstanding")
            mktcap = info.get("marketCap")
            eps    = info.get("trailingEps")

            # FCF — try multiple methods
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
                "mktcap_ath":    shares * ath  i
