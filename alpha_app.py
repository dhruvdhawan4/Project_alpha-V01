# ==============================================================================
# PROJECT ALPHA: FULL QUANTITATIVE INSTITUTIONAL WORKSPACE
# ==============================================================================

import io, math, sqlite3, datetime, requests, numpy as np, pandas as pd, yfinance as yf, streamlit as st, plotly.graph_objects as go

# ------------------------------------------------------------------------------
# CORE UI CONFIGURATION
# ------------------------------------------------------------------------------
st.set_page_config(page_title="Project Alpha // Pro Workspace", page_icon="🏛️", layout="wide", initial_sidebar_state="expanded")

CONFIG = {"DB_PATH": "alpha_production_workspace.db"}
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30))

# ------------------------------------------------------------------------------
# DATABASE & CLOCK
# ------------------------------------------------------------------------------
def bootstrap_database():
    with sqlite3.connect(CONFIG["DB_PATH"]) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS predictions_ledger (target_date TEXT, ticker TEXT, direction TEXT, current_price REAL, target_entry REAL, target_exit REAL, confidence REAL, expected_return REAL, allocation REAL, PRIMARY KEY(target_date, ticker))")
        conn.execute("CREATE TABLE IF NOT EXISTS intraday_journal (date TEXT, ticker TEXT, direction TEXT, entry_price REAL, exit_price REAL, allocation_amount REAL, predicted_return REAL, actual_return REAL, realized_pnl REAL, confidence REAL, status TEXT)")
        conn.commit()

class ExecutionClock:
    @staticmethod
    def get_state():
        now = datetime.datetime.now(IST)
        is_weekday = now.weekday() <= 4
        market_open, market_close = datetime.time(9, 15), datetime.time(15, 30)
        is_live = is_weekday and (market_open <= now.time() <= market_close)
        next_date = now.date()
        if now.time() >= market_close or not is_weekday: next_date += datetime.timedelta(days=1)
        while next_date.weekday() > 4: next_date += datetime.timedelta(days=1)
        return {"is_live": is_live, "today_iso": now.date().isoformat(), "next_iso": next_date.isoformat(), "next_open": next_date.strftime('%A, %B %d, %Y')}

# ------------------------------------------------------------------------------
# MARKET INTELLIGENCE
# ------------------------------------------------------------------------------
@st.cache_data(ttl=60)
def fetch_indices():
    results = {}
    for name, ticker in {"NIFTY 50": "^NSEI", "NIFTY 100": "^CNX100", "NIFTY 200": "^CNX200"}.items():
        try:
            df = yf.Ticker(ticker).history(period="2d")
            curr, prev = df['Close'].iloc[-1], df['Close'].iloc[-2]
            results[name] = {"current": curr, "change": curr - prev, "pct": ((curr - prev) / prev) * 100}
        except: results[name] = None
    return results

@st.cache_data(ttl=60)
def analyze_market_regime():
    try:
        df = yf.Ticker("^NSEI").history(period="6mo")
        close = df['Close']
        ema20, sma50 = close.ewm(span=20).mean().iloc[-1], close.rolling(50).mean().iloc[-1]
        score = (1 if close.iloc[-1] > ema20 else -1) + (1 if close.iloc[-1] > sma50 else -1)
        return "Bullish 📈" if score > 0 else "Bearish 📉"
    except: return "Neutral"

# ------------------------------------------------------------------------------
# QUANTITATIVE ENGINE (FIXED: NO FILTERS, ATR TARGETS)
# ------------------------------------------------------------------------------
class QuantEngine:
    @staticmethod
    def analyze_asset(ticker):
        try:
            df = yf.Ticker(ticker).history(period="3mo")
            if len(df) < 50: return None
            
            close = df["Close"]
            curr = float(close.iloc[-1])
            ema20, ema50 = close.ewm(span=20).mean().iloc[-1], close.ewm(span=50).mean().iloc[-1]
            rsi = 100 - (100 / (1 + (close.diff(1).clip(lower=0).rolling(14).mean() / (-close.diff(1).clip(upper=0).rolling(14).mean()))))
            atr = (df['High'] - df['Low']).rolling(14).mean().iloc[-1]
            
            score = (1 if curr > ema20 else -1) + (1 if ema20 > ema50 else -1) + (1 if rsi.iloc[-1] < 70 else -1)
            
            # NO FILTERING: Everything gets a direction
            direction = "LONG" if score >= 0 else "SHORT"
            entry = curr * 1.001 if direction == "LONG" else curr * 0.999
            exit_p = entry + (atr * 1.5) if direction == "LONG" else entry - (atr * 1.5)
            
            return {"ticker": ticker, "direction": direction, "current": round(curr, 2), "entry": round(entry, 2), "exit": round(exit_p, 2), "conf": min(max(abs(score)*20 + 50, 60), 95), "exp": 2.0}
        except: return None

    @staticmethod
    def generate_picks(target_date, universe, total_cap):
        urls = {"NIFTY_50": "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv", "NIFTY_100": "https://niftyindices.com/IndexConstituent/ind_nifty100list.csv", "NIFTY_200": "https://niftyindices.com/IndexConstituent/ind_nifty200list.csv"}
        try:
            res = requests.get(urls[universe], headers={"User-Agent": "Mozilla/5.0"}, timeout=10)
            tickers = [f"{s.strip()}.NS" for s in pd.read_csv(io.StringIO(res.text))["Symbol"].dropna().tolist()]
        except: tickers = ["RELIANCE.NS", "TCS.NS", "HDFCBANK.NS", "TITAN.NS"]
        
        picks = []
        progress = st.progress(0)
        for i, t in enumerate(tickers):
            progress.progress((i + 1) / len(tickers))
            res = QuantEngine.analyze_asset(t)
            if res: picks.append(res)
        progress.empty()
        
        picks = sorted(picks, key=lambda x: x["conf"], reverse=True)[:8]
        alloc = float(math.ceil((total_cap / len(picks)) / 100.0) * 100.0)
        
        with sqlite3.connect(CONFIG["DB_PATH"]) as conn:
            for p in picks:
                conn.execute("INSERT OR REPLACE INTO predictions_ledger VALUES (?,?,?,?,?,?,?,?,?)", 
                             (target_date, p["ticker"], p["direction"], p["current"], p["entry"], p["exit"], p["conf"], p["exp"], alloc))
            conn.commit()

# ------------------------------------------------------------------------------
# UI LAYER
# ------------------------------------------------------------------------------
bootstrap_database()
clock = ExecutionClock.get_state()

with st.sidebar:
    st.title("🏛️ Project Alpha")
    total_cap = st.number_input("Capital (INR)", value=100000)
    univ = st.selectbox("Universe", ["NIFTY_50", "NIFTY_100", "NIFTY_200"])
    if st.button("🏠 Home Dashboard"): st.session_state.page = "home"
    if st.button("🏛️ Historical Ledger"): st.session_state.page = "logs"
    if st.button("🔄 Force Refresh Engine"): 
        QuantEngine.generate_picks(clock["next_iso"], univ, total_cap)
        st.rerun()

if "page" not in st.session_state: st.session_state.page = "home"

if st.session_state.page == "home":
    st.title("📊 Alpha Core Executive Dashboard")
    # Macro Environment
    col1, col2 = st.columns(2)
    with col1: st.metric("Market Regime", analyze_market_regime())
    with col2:
        ind = fetch_indices().get(univ.replace("_", " "))
        if ind: st.metric(univ.replace("_", " "), f"{ind['current']:,.2f}", f"{ind['pct']:.2f}%")
    
    st.markdown("---")
    
    with sqlite3.connect(CONFIG["DB_PATH"]) as conn:
        data = conn.execute("SELECT * FROM predictions_ledger WHERE target_date = ?", (clock["next_iso"],)).fetchall()
    
    if not data:
        st.warning("Analysis engine idle.")
        if st.button("🚀 Run Multi-Factor Strategy"):
            QuantEngine.generate_picks(clock["next_iso"], univ, total_cap)
            st.rerun()
    else:
        df = pd.DataFrame(data, columns=["Date", "Ticker", "Side", "Current", "Entry", "Exit", "Confidence", "Expected", "Allocation"])
        st.dataframe(df, use_container_width=True)
        sel = st.selectbox("Detailed Analysis", df["Ticker"].tolist())
        chart_df = yf.Ticker(sel).history(period="1mo")
        fig = go.Figure(data=[go.Candlestick(x=chart_df.index, open=chart_df['Open'], high=chart_df['High'], low=chart_df['Low'], close=chart_df['Close'])])
        fig.update_layout(template="plotly_dark", height=400)
        st.plotly_chart(fig, use_container_width=True)

elif st.session_state.page == "logs":
    st.title("🏛️ Historical Ledger")
    with sqlite3.connect(CONFIG["DB_PATH"]) as conn:
        st.dataframe(pd.read_sql_query("SELECT * FROM intraday_journal", conn), use_container_width=True)
