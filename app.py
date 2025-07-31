from flask import Flask, jsonify, render_template, make_response
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time

# --- Create the Flask App ---
app = Flask(__name__)

# --- NEW: Function to get Nifty 100 symbols dynamically ---
def get_nifty100_symbols():
    """
    Scrapes the list of Nifty 100 symbols from a reliable source.
    Using a well-maintained GitHub repo is often more stable than scraping NSE directly.
    """
    try:
        # This URL points to a CSV file with the Nifty 100 constituents
        url = "https://raw.githubusercontent.com/piyush-eon/trading-scripts/master/data/ind_nifty100list.csv"
        df = pd.read_csv(url)
        # The 'Symbol' column contains the stock tickers we need
        symbols = df['Symbol'].tolist()
        print(f"Successfully fetched {len(symbols)} Nifty 100 symbols.")
        return symbols
    except Exception as e:
        print(f"CRITICAL: Failed to fetch Nifty 100 stock list: {e}")
        print("Falling back to a hardcoded list.")
        # --- Fallback list in case the scrape fails ---
        return [
            'ADANIENT', 'ADANIGREEN', 'ADANIPORTS', 'ADANIPOWER', 'AMBUJACEM', 
            'APOLLOHOSP', 'ASIANPAINT', 'AXISBANK', 'BAJAJ-AUTO', 'BAJFINANCE', 
            'BAJAJFINSV', 'BPCL', 'BHARTIARTL', 'BRITANNIA', 'CIPLA', 'COALINDIA', 
            'DIVISLAB', 'DRREDDY', 'EICHERMOT', 'GRASIM', 'HCLTECH', 'HDFCBANK', 
            'HDFCLIFE', 'HEROMOTOCO', 'HINDALCO', 'HINDUNILVR', 'ICICIBANK', 
            'ITC', 'INDUSINDBK', 'INFY', 'JSWSTEEL', 'KOTAKBANK', 'LTIM', 'LT', 
            'M&M', 'MARUTI', 'NTPC', 'NESTLEIND', 'ONGC', 'POWERGRID', 'RELIANCE', 
            'SBILIFE', 'SBIN', 'SUNPHARMA', 'TCS', 'TATACONSUM', 'TATAMOTORS', 
            'TATASTEEL', 'TECHM', 'TITAN', 'ULTRACEMCO', 'WIPRO', 'ZOMATO',
            'DMART', 'BAJAJHLDNG', 'ICICIGI', 'TRENT'
        ]


# --- DATA LOGIC (largely unchanged) ---

def calculate_rsi(data, window=14):
    if data.empty or len(data) < window: return None
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    if loss.iloc[-1] == 0: return 100.0
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]

def get_pledge_percentage(symbol):
    # This function remains the same
    try:
        url = f"https://www.screener.in/company/{symbol}/consolidated/"
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')
        pledge_li = soup.find('li', class_='flex-space-between', string=lambda t: t and 'Pledge' in t)
        if pledge_li:
            pledge_span = pledge_li.find('span', class_='number')
            return float(pledge_span.text.strip()) if pledge_span else 0.0
        return 0.0
    except Exception:
        return 0.0

def get_recommendation(rsi, pe, pledge):
    # This function remains the same
    score = 0
    reason = []
    if rsi is not None:
        if rsi < 30:
            score += 3
            reason.append("Oversold (RSI < 30)")
        elif rsi < 40:
            score += 1
            reason.append("Approaching Oversold")
    if pe is not None:
        if pe > 0 and pe < 20:
            score += 2
            reason.append("Low P/E (< 20)")
        elif pe < 0:
            score -= 1
            reason.append("Negative P/E")
    if pledge is not None:
        if pledge > 25:
            score -= 2
            reason.append("High Pledge (> 25%)")
        elif pledge > 50:
            score -= 4
            reason.append("Very High Pledge (> 50%)")
    if score >= 3:
        return {"signal": "Yes", "reason": ", ".join(reason)}
    else:
        return {"signal": "No", "reason": "Neutral or Unfavorable"}


# --- MODIFIED: Main data fetch function ---
def fetch_all_data():
    """
    This function now dynamically gets the stock list first.
    """
    # 1. Get the latest list of Nifty 100 stocks
    stock_symbols = get_nifty100_symbols()
    
    print(f"--- Starting data fetch for {len(stock_symbols)} stocks ---")
    all_stocks_data = []

    # 2. Loop through the dynamically fetched list
    for symbol in stock_symbols:
        stock_data = {}
        try:
            print(f"Fetching data for {symbol}...")
            ticker = yf.Ticker(f"{symbol}.NS")
            info = ticker.info
            
            if not info or 'currentPrice' not in info or info.get('currentPrice') is None:
                print(f"  - Skipping {symbol} due to missing or invalid data from yfinance.")
                continue

            hist = ticker.history(period="1mo")
            
            # Core Data
            stock_data['name'] = info.get('longName', symbol)
            stock_data['symbol'] = symbol
            stock_data['price'] = info.get('currentPrice', 0)
            prev_close = info.get('previousClose', 0)
            stock_data['change'] = stock_data['price'] - prev_close
            stock_data['pctChange'] = (stock_data['change'] / prev_close) * 100 if prev_close else 0
            
            # Analytics Data
            rsi = calculate_rsi(hist)
            pe = info.get('trailingPE', None)
            pledge = get_pledge_percentage(symbol)
            
            stock_data['rsi'] = rsi
            stock_data['pe'] = pe
            stock_data['pledge'] = pledge
            
            # Recommendation
            recommendation = get_recommendation(rsi, pe, pledge)
            stock_data['recommendation'] = recommendation['signal']
            stock_data['reason'] = recommendation['reason']
            
            all_stocks_data.append(stock_data)
            time.sleep(0.3) # Be polite
        except Exception as e:
            print(f"  - Error fetching data for {symbol}: {e}")
            continue
            
    print("--- Data fetch cycle complete ---")
    return {
        "data": all_stocks_data,
        "last_updated": time.strftime('%I:%M:%S %p, %b %d, %Y')
    }

# --- FLASK ROUTES (Unchanged) ---

@app.route('/')
def home():
    return render_template('index.html')

@app.route('/data')
def get_data():
    data = fetch_all_data()
    response = make_response(jsonify(data))
    response.headers['Cache-Control'] = 's-maxage=900, stale-while-revalidate'
    return response
