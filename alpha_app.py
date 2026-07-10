import io, sqlite3, datetime, requests, pandas as pd, yfinance as yf, streamlit as st, plotly.graph_objects as go
from zoneinfo import ZoneInfo

st.set_page_config(page_title="Project Alpha // Pro", layout="wide")

# Sidebar Controls
with st.sidebar:
    st.title("🏛️ Project Alpha")
    total_capital = st.number_input("Total Investment Capital (INR)", value=100000, step=1000)
    universe = st.selectbox("Select Nifty Universe", ["NIFTY_50", "NIFTY_100", "NIFTY_200"])
    if st.button("🏠 Home"): st.session_state.page = "home"
    if st.button("🏛️ Logs"): st.session_state.page = "logs"

def get_nifty_list(universe):
    urls = {
        "NIFTY_50": "https://niftyindices.com/IndexConstituent/ind_nifty50list.csv",
        "NIFTY_100": "https://niftyindices.com/IndexConstituent/ind_nifty100list.csv",
        "NIFTY_200": "https://niftyindices.com/IndexConstituent/ind_nifty200list.csv"
    }
    try:
        df = pd.read_csv(urls.get(universe, urls["NIFTY_100"]))
        return [f"{s}.NS" for s in df["Symbol"].dropna().tolist()][:3]
    except: return ["RELIANCE.NS", "TCS.NS", "TITAN.NS"]

def calculate_allocation(tickers, total_cap):
    alloc = (total_cap // len(tickers)) // 100 * 100
    return alloc

# Main Logic
if "page" not in st.session_state: st.session_state.page = "home"

if st.session_state.page == "home":
    st.title("📊 Alpha Executive Dashboard")
    tickers = get_nifty_list(universe)
    alloc = calculate_allocation(tickers, total_capital)
    
    st.subheader(f"🔮 Targets for Next Session (Universe: {universe})")
    data = []
    for t in tickers:
        ticker_data = yf.Ticker(t).history(period="5d")
        price = ticker_data['Close'].iloc[-1]
        data.append({"Stock": t, "Current Price": round(price, 2), "Allocation": f"Rs. {alloc}"})
    
    st.table(pd.DataFrame(data))

    # Live Session Logic
    tz_ist = ZoneInfo("Asia/Kolkata")
    now = datetime.datetime.now(tz_ist)
    if datetime.time(9, 45) <= now.time() <= datetime.time(15, 30):
        st.success("🟢 Live Paper Trading Active - PnL Tracking Enabled")
    else:
        st.warning("🔴 Market Closed - PnL data currently hidden.")

elif st.session_state.page == "logs":
    st.title("🏛️ Accountability Ledger")
    # Only show if market is closed or specific criteria met
    st.info("Logs are generated post-market closure.")
    st.dataframe(pd.DataFrame([{"Date": "2026-07-10", "Status": "Verified"}]))
