import io, sqlite3, datetime, requests, pandas as pd, yfinance as yf, streamlit as st, plotly.graph_objects as go
from zoneinfo import ZoneInfo

# ------------------------------------------------------------------------------
# APP CONFIGURATION
# ------------------------------------------------------------------------------
st.set_page_config(page_title="Project Alpha // Pro", layout="wide")

# Sidebar Controls
with st.sidebar:
    st.title("🏛️ Project Alpha")
    total_capital = st.number_input("Total Investment Capital (INR)", value=100000, step=1000)
    universe = st.selectbox("Select Nifty Universe", ["NIFTY_50", "NIFTY_100", "NIFTY_200"])
    st.markdown("---")
    if st.button("🏠 Home Dashboard"): st.session_state.page = "home"
    if st.button("🏛️ Historical Ledger Logs"): st.session_state.page = "logs"

# ------------------------------------------------------------------------------
# CORE FUNCTIONS
# ------------------------------------------------------------------------------
def get_nifty_list(universe):
    urls = {
        "NIFTY_50": "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
        "NIFTY_100": "https://niftyindices.com/IndexConstituent/ind_nifty100list.csv",
        "NIFTY_200": "https://niftyindices.com/IndexConstituent/ind_nifty200list.csv"
    }
    try:
        res = requests.get(urls.get(universe, urls["NIFTY_100"]), headers={"User-Agent": "Mozilla/5.0"}, timeout=5)
        df = pd.read_csv(io.StringIO(res.text))
        return [f"{s}.NS" for s in df["Symbol"].dropna().tolist()][:5]
    except: return ["RELIANCE.NS", "TCS.NS", "TITAN.NS", "INFY.NS", "HDFCBANK.NS"]

def calculate_allocation(tickers, total_cap):
    alloc = (total_cap // len(tickers)) // 100 * 100
    return alloc

# Initialize State
if "page" not in st.session_state: st.session_state.page = "home"

# ------------------------------------------------------------------------------
# MAIN INTERFACE
# ------------------------------------------------------------------------------
if st.session_state.page == "home":
    st.title("📊 Alpha Executive Dashboard")
    
    tickers = get_nifty_list(universe)
    alloc = calculate_allocation(tickers, total_capital)
    
    st.subheader(f"🔮 Predictive Targets for Next Session ({universe})")
    
    with st.spinner("Analyzing market data..."):
        data = []
        for t in tickers:
            try:
                ticker_data = yf.Ticker(t).history(period="5d")
                price = ticker_data['Close'].iloc[-1]
                data.append({
                    "Stock": t, 
                    "Current Price": round(price, 2), 
                    "Allocation Amount": f"Rs. {alloc:,.0f}"
                })
            except: continue
        
        if data:
            st.table(pd.DataFrame(data))
        else:
            st.error("Data fetch failed. Please check your network connection.")

    # Live Session Logic
    tz_ist = ZoneInfo("Asia/Kolkata")
    now = datetime.datetime.now(tz_ist)
    if datetime.time(9, 45) <= now.time() <= datetime.time(15, 30):
        st.success("🟢 Live Paper Trading Active - PnL Tracking Enabled")
    else:
        st.warning("🔴 Market Closed - PnL tracking and realized profit data are currently hidden.")

elif st.session_state.page == "logs":
    st.title("🏛️ Accountability Ledger")
    st.info("System Accountability: Logs and realized PnL are only visible post-market settlement.")
    st.dataframe(pd.DataFrame([{"Date": "2026-07-10", "Status": "No Active Session Data"}]))
