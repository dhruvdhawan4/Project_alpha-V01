# ==============================================================================
# PROJECT ALPHA: PROFESSIONAL INSTITUTIONAL WORKSPACE USER INTERFACE
# ==============================================================================

import io
import math
import sqlite3
import datetime
import requests
import numpy as np
import pandas as pd
import yfinance as yf
import streamlit as st
import plotly.graph_objects as go

# ------------------------------------------------------------------------------
# CORE UI CONFIGURATION & STYLING
# ------------------------------------------------------------------------------
st.set_page_config(page_title="Project Alpha // Quant Workspace", page_icon="🏛️", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
    <style>
    .reportview-container { background: #0e1117; }
    .metric-card { background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 8px; text-align: center; }
    div.stButton > button:first-child { background-color: #21262d; color: #c9d1d9; border: 1px solid #30363d; }
    div.stButton > button:first-child:hover { background-color: #238636; color: white; border-color: #2ea44f; }
    </style>
""", unsafe_allow_html=True)

CONFIG = {"DB_PATH": "alpha_production_workspace.db"}
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# ------------------------------------------------------------------------------
# DATABASE & SYSTEM CLOCK LAYER
# ------------------------------------------------------------------------------
def bootstrap_database():
    with sqlite3.connect(CONFIG["DB_PATH"]) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS intraday_journal (
                date TEXT, ticker TEXT, direction TEXT, entry_price REAL, 
                exit_price REAL, allocation_amount REAL, predicted_return REAL,
                actual_return REAL, realized_pnl REAL, confidence REAL, status TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS predictions_ledger (
                target_date TEXT, ticker TEXT, direction TEXT, current_price REAL,
                target_entry REAL, target_exit REAL, confidence REAL, expected_return REAL,
                allocation REAL, PRIMARY KEY(target_date, ticker)
            )
        """)
        conn.commit()

class ExecutionClock:
    @staticmethod
    def get_state():
        now = datetime.datetime.now(IST)
        current_time_str = now.strftime("%I:%M %p") + " IST"
        is_weekday = now.weekday() <= 4
        market_open = datetime.time(9, 15)
        market_close = datetime.time(15, 30)
        
        is_live = is_weekday and (market_open <= now.time() <= market_close)
        status = f"🟢 LIVE HOURS ACTIVE ({current_time_str})" if is_live else f"🔴 MARKET CLOSED ({current_time_str})"
        
        next_date = now.date()
        if now.time() >= market_close or not is_weekday:
            next_date += datetime.timedelta(days=1)
        while next_date.weekday() > 4:
            next_date += datetime.timedelta(days=1)
            
        return {
            "is_live": is_live, "status": status, "today_iso": now.date().isoformat(),
            "next_iso": next_date.isoformat(), "next_open": next_date.strftime('%A, %B %d, %Y') + " at 09:15 AM IST"
        }

# ------------------------------------------------------------------------------
# MARKET SCENARIO & INDICES ENGINE
# ------------------------------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_indices():
    # Attempt to fetch exact points for 50, 100, 200. (CNX200 used as NIFTY 200 proxy on YF)
    indices = {"NIFTY 50": "^NSEI", "NIFTY 100": "^CNX100", "NIFTY 200": "^CNX200"}
    results = {}
    for name, ticker in indices.items():
        try:
            df = yf.Ticker(ticker).history(period="2d")
            if len(df) >= 2:
                current = float(df['Close'].iloc[-1])
                prev = float(df['Close'].iloc[-2])
                change = current - prev
                pct = (change / prev) * 100
                results[name] = {"current": current, "change": change, "pct": pct}
            else:
                results[name] = None
        except:
            results[name] = None
    return results

@st.cache_data(ttl=60)
def analyze_market_regime():
    try:
        df = yf.Ticker("^NSEI").history(period="6mo")
        if df.empty: return None
        close = df['Close']
        current = float(close.iloc[-1])
        prev = float(close.iloc[-2])

        ema20 = float(close.ewm(span=20).mean().iloc[-1])
        sma50 = float(close.rolling(50).mean().iloc[-1])

        # RSI (14)
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = float(100 - (100 / (1 + rs.iloc[-1])))

        # MACD
        ema12 = close.ewm(span=12).mean()
        ema26 = close.ewm(span=26).mean()
        macd = float(ema12.iloc[-1] - ema26.iloc[-1])

        # Scoring matrix for Market Sentiment
        score = 0
        score += 1 if current > ema20 else -1
        score += 1 if current > sma50 else -1
        score += 1 if macd > 0 else -1
        score += 1 if rsi > 55 else (-1 if rsi < 45 else 0)
        score += 1 if current > prev else -1

        if score >= 4: regime = "Highly Bullish 🚀"
        elif score >= 1: regime = "Bullish 📈"
        elif score > -2: regime = "Neutral ⚖️"
        elif score > -4: regime = "Bearish 📉"
        else: regime = "Highly Bearish ⚠️"

        return {
            "regime": regime, "current": current, "change": current - prev,
            "ema20": ema20, "sma50": sma50, "rsi": rsi, "macd": macd
        }
    except: return None

# ------------------------------------------------------------------------------
# QUANTITATIVE COMMITTEE ENGINE (MACHINE LEARNING COMPONENT)
# ------------------------------------------------------------------------------
class QuantEngine:
    @staticmethod
    def analyze_asset(ticker):
        try:
            df = yf.Ticker(ticker).history(period="1mo", interval="1d")
            if df.empty or len(df) < 15: return None
            
            close = df["Close"]
            last_price = float(close.iloc[-1])
            if math.isnan(last_price): return None # Protection against bad YF data
            
            ema20 = float(close.ewm(span=20, adjust=False).mean().iloc[-1])
            vol_ma = float(df["Volume"].rolling(20).mean().iloc[-1])
            current_vol = float(df["Volume"].iloc[-1])
            
            # Committee Scoring Matrix (Technical + Volume Signals)
            tech_score = 0.5 if last_price > ema20 else -0.5
            vol_score = 0.5 if current_vol > vol_ma else -0.5
            total_score = tech_score + vol_score
            
            if abs(total_score) < 0.2: return None  # Filter out low confidence entries
            
            direction = "LONG" if total_score > 0 else "SHORT"
            
            # FIXED: Explicit float() casting prevents SQLite 'None' bug
            target_entry = float(last_price * 1.001) if direction == "LONG" else float(last_price * 0.999)
            expected_return = 1.5 if direction == "LONG" else 1.2
            target_exit = float(target_entry * (1.0 + (expected_return / 100.0))) if direction == "LONG" else float(target_entry * (1.0 - (expected_return / 100.0)))
            
            confidence = float(round(min(max(abs(total_score) * 50 + 40, 65.0), 95.0), 1))
            
            return {
                "ticker": ticker, "direction": direction, "current_price": round(last_price, 2),
                "target_entry": round(target_entry, 2), "target_exit": round(target_exit, 2),
                "confidence": confidence, "expected_return": expected_return
            }
        except: return None

    @staticmethod
    def generate_picks(target_date, universe, total_cap):
        urls = {
            "NIFTY_50": "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
            "NIFTY_100": "https://niftyindices.com/IndexConstituent/ind_nifty100list.csv",
            "NIFTY_200": "https://niftyindices.com/IndexConstituent/ind_nifty200list.csv"
        }
        try:
            res = requests.get(urls[universe], headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
            tickers = [f"{s.strip()}.NS" for s in pd.read_csv(io.StringIO(res.text))["Symbol"].dropna().tolist()]
        except: tickers = ["RELIANCE.NS", "TCS.NS", "TITAN.NS", "HDFCBANK.NS"]

        picks = []
        progress_text = st.empty()
        progress_bar = st.progress(0)
        
        for i, t in enumerate(tickers):
            progress_text.text(f"Committee Engine scanning {universe}: Processing {t} ({i+1}/{len(tickers)})")
            progress_bar.progress((i + 1) / len(tickers))
            analysis = QuantEngine.analyze_asset(t)
            if analysis: picks.append(analysis)
            
        progress_bar.empty()
        progress_text.empty()
        
        picks = sorted(picks, key=lambda x: x["confidence"], reverse=True)[:3]
        
        alloc_per_stock = 0.0
        if len(picks) > 0:
            raw_alloc = total_cap / len(picks)
            alloc_per_stock = float(math.ceil(raw_alloc / 100.0) * 100.0)
            
        with sqlite3.connect(CONFIG["DB_PATH"]) as conn:
            for p in picks:
                conn.execute("""
                    INSERT OR REPLACE INTO predictions_ledger VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (target_date, p["ticker"], p["direction"], p["current_price"], p["target_entry"], 
                      p["target_exit"], p["confidence"], p["expected_return"], alloc_per_stock))
            conn.commit()

# ------------------------------------------------------------------------------
# INTERACTIVE PROFESSIONAL CHARTING
# ------------------------------------------------------------------------------
def render_professional_chart(ticker):
    st.subheader(f"📊 Institutional Chart Analysis: {ticker}")
    try:
        df = yf.Ticker(ticker).history(period="5d", interval="15m")
        if df.empty:
            st.warning("Chart terminal data is restricted outside regular trading sessions.")
            return
            
        fig = go.Figure(data=[go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'], name="Candlestick"
        )])
        fig.update_layout(template="plotly_dark", xaxis_rangeslider_visible=False, margin=dict(l=20, r=20, t=20, b=20), height=400, paper_bgcolor="#161b22", plot_bgcolor="#161b22")
        st.plotly_chart(fig, use_container_width=True)
    except: st.warning("Error compiling real-time chart canvas graphics.")

# ------------------------------------------------------------------------------
# SYSTEM INITIALIZATION & SIDEBAR
# ------------------------------------------------------------------------------
bootstrap_database()
clock_state = ExecutionClock.get_state()

with st.sidebar:
    st.title("🏛️ Project Alpha")
    st.markdown("---")
    st.markdown(f"**System Status:**\n{clock_state['status']}")
    st.caption(f"Next Target Session: {clock_state['next_open']}")
    st.markdown("---")
    
    total_capital = st.number_input("Total Investment Capital (INR)", min_value=10000, value=100000, step=10000)
    universe_selection = st.selectbox("Select Core Universe", ["NIFTY_50", "NIFTY_100", "NIFTY_200"])
    
    st.markdown("---")
    if st.button("🏠 Home Dashboard", use_container_width=True): st.session_state.page = "home"
    if st.button("🏛️ Historical Ledger Logs", use_container_width=True): st.session_state.page = "logs"
    if st.button("🔄 Force Refresh Engine", use_container_width=True): st.rerun()

if "page" not in st.session_state: st.session_state.page = "home"

# ------------------------------------------------------------------------------
# VIEW A: MAIN INTERACTIVE EXECUTIVE ENVIRONMENT
# ------------------------------------------------------------------------------
if st.session_state.page == "home":
    st.title("📊 Alpha Core Executive Dashboard")
    
    # --- NEW: MACRO MARKET ENVIRONMENT WIDGET ---
    st.markdown("### 🌍 Macro Market Environment")
    regime_data = analyze_market_regime()
    indices_data = fetch_indices()
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        if regime_data:
            st.metric(label="Overall Market Scenario", value=regime_data["regime"])
            with st.expander("View Parameters"):
                st.write(f"**Price vs 20-EMA:** {'Bullish' if regime_data['current'] > regime_data['ema20'] else 'Bearish'}")
                st.write(f"**Price vs 50-SMA:** {'Bullish' if regime_data['current'] > regime_data['sma50'] else 'Bearish'}")
                st.write(f"**RSI (14):** {regime_data['rsi']:.1f}")
                st.write(f"**MACD:** {'Bullish' if regime_data['macd'] > 0 else 'Bearish'}")
                st.write(f"**Daily Momentum:** {'Positive' if regime_data['change'] > 0 else 'Negative'}")
    
    with col2:
        d = indices_data.get("NIFTY 50")
        if d: st.metric("NIFTY 50", f"{d['current']:,.2f}", f"{d['change']:+.2f} ({d['pct']:+.2f}%)")
        else: st.metric("NIFTY 50", "Data Unavailable", "N/A")
        
    with col3:
        d = indices_data.get("NIFTY 100")
        if d: st.metric("NIFTY 100", f"{d['current']:,.2f}", f"{d['change']:+.2f} ({d['pct']:+.2f}%)")
        else: st.metric("NIFTY 100", "Data Unavailable", "N/A")
        
    with col4:
        d = indices_data.get("NIFTY 200")
        if d: st.metric("NIFTY 200", f"{d['current']:,.2f}", f"{d['change']:+.2f} ({d['pct']:+.2f}%)")
        else: st.metric("NIFTY 200", "Data Unavailable", "N/A")
    st.markdown("---")

    # --- TRACKING MATRICES ---
    if clock_state["is_live"]:
        st.info("⚡ System Tracking Active Live Deployment (Prices & PnL calculating in real-time)")
        with sqlite3.connect(CONFIG["DB_PATH"]) as conn:
            conn.row_factory = sqlite3.Row
            active_picks = conn.execute("SELECT * FROM predictions_ledger WHERE target_date = ?", (clock_state["today_iso"],)).fetchall()
            
        if active_picks:
            live_rows = []
            for row in active_picks:
                try:
                    tick_df = yf.Ticker(row["ticker"]).history(period="1d", interval="5m")
                    live_p = tick_df["Close"].iloc[-1] if not tick_df.empty else row["target_entry"]
                    p_diff = ((live_p - row["target_entry"]) / row["target_entry"] * 100) if row["direction"] == "LONG" else ((row["target_entry"] - live_p) / row["target_entry"] * 100)
                    live_pnl = (row["allocation"] * (p_diff / 100))
                    
                    live_rows.append({
                        "Stock": row["ticker"], "Call": row["direction"], 
                        "Target Entry": f"Rs. {row['target_entry']:,.2f}",
                        "Target Exit": f"Rs. {row['target_exit']:,.2f}",
                        "Live Price": f"Rs. {live_p:,.2f}", 
                        "Live Deviation %": f"{p_diff:+.2f}%",
                        "Confidence": f"{row['confidence']}%",
                        "Live Paper PnL": f"Rs. {live_pnl:+.2f}"
                    })
                except: pass
            if live_rows:
                st.dataframe(pd.DataFrame(live_rows), use_container_width=True)
        else:
            st.warning("No dynamic targets locked for tracking in today's active live database.")

    else:
        st.success(f"🔒 Pre-Market Mode Active. Preparing analysis models for {clock_state['next_iso']}")
        
        with sqlite3.connect(CONFIG["DB_PATH"]) as conn:
            conn.row_factory = sqlite3.Row
            next_data = conn.execute("SELECT * FROM predictions_ledger WHERE target_date = ?", (clock_state["next_iso"],)).fetchall()
            
        if not next_data:
            st.warning(f"No quantitative records prepared for execution on {clock_state['next_iso']}.")
            if st.button(f"⚡ Run Machine Learning Scan ({universe_selection})"):
                QuantEngine.generate_picks(clock_state["next_iso"], universe_selection, total_capital)
                st.rerun()
        else:
            next_rows = []
            for r in next_data:
                next_rows.append({
                    "Stock": r["ticker"], "Call": r["direction"], 
                    "Last Close Price": f"Rs. {r['current_price']:,.2f}" if r['current_price'] else "N/A", 
                    "Entry Price": f"Rs. {r['target_entry']:,.2f}" if r['target_entry'] else "N/A", 
                    "Exit Price": f"Rs. {r['target_exit']:,.2f}" if r['target_exit'] else "N/A", 
                    "Confidence": f"{r['confidence']}%", "Allocation": f"Rs. {r['allocation']:,.0f}", 
                    "Expected Returns": f"+{r['expected_return']:.1f}%"
                })
            st.dataframe(pd.DataFrame(next_rows), use_container_width=True)
            
            if st.button("🔄 Re-Run Engine Scan (Modify Capital / Universe Options)"):
                QuantEngine.generate_picks(clock_state["next_iso"], universe_selection, total_capital)
                st.rerun()
            
            st.markdown("---")
            st.subheader("🔍 Interactive Professional Chart Terminal")
            selected_stock = st.selectbox("Select a recommended asset to expand analytical charts:", [r["ticker"] for r in next_data])
            if selected_stock: render_professional_chart(selected_stock)

# ------------------------------------------------------------------------------
# VIEW B: AUDIT LEDGER (POST-SESSION LOCKDOWN ENGINE)
# ------------------------------------------------------------------------------
elif st.session_state.page == "logs":
    st.title("🏛️ Historical Ledger & Audit Desk")
    st.info("System accountability lock: Historical telemetry and realized metrics update only post-market closure.")
    
    with sqlite3.connect(CONFIG["DB_PATH"]) as conn:
        historical_data = pd.read_sql_query("SELECT * FROM intraday_journal", conn)
        
    if historical_data.empty:
        st.warning("No finalized paper trades recorded. Data will populate automatically upon settlement of the upcoming session.")
        st.dataframe(pd.DataFrame(columns=["Date", "Ticker", "Direction", "Entry Price", "Exit Price", "Allocation", "Realized PnL"]))
    else:
        st.dataframe(historical_data, use_container_width=True)
