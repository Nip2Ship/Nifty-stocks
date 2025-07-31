from flask import Flask, jsonify, render_template, make_response
import yfinance as yf
import pandas as pd
import requests
from bs4 import BeautifulSoup
import time

# --- Create the Flask App ---
# Vercel will look for an 'app' variable by default.
app = Flask(__name__)

# --- CONFIGURATION ---
STOCKS = [
    'RELIANCE', 'TCS', 'HDFCBANK', 'ICICIBANK', 'INFY', 'HINDUNILVR', 
    'ADANIENT', 'ZOMATO', 'VEDL', 'ITC', 'BAJFINANCE', 'SBIN'
]

# --- DATA FETCHING LOGIC (modified to be called on-demand) ---

def calculate_rsi(data, window=14):
    if data.empty: return None
    delta = data['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
    if loss.iloc[-1] == 0: return 100 # Avoid division by zero
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1] if not rsi.empty else None

def get_pledge_percentage(symbol):
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
    except Exception as e:
        print(f"Pledge scrape error for {symbol}: {e}")
        return 0.0

def fetch_all_data():
    """This function now contains all the scraping logic."""
    print("--- Starting full data fetch cycle ---")
    all_stocks_data = []
    for symbol in STOCKS:
        stock_data = {}
        try:
            print(f"Fetching data for {symbol}...")
            ticker = yf.Ticker(f"{symbol}.NS")
            info = ticker.info
            hist = ticker.history(period="1mo")
            
            stock_data['name'] = info.get('longName', symbol)
            stock_data['symbol'] = symbol
            stock_data['price'] = info.get('currentPrice', 0)
            prev_close = info.get('previousClose', 0)
            stock_data['change'] = stock_data['price'] - prev_close
            stock_data['pctChange'] = (stock_data['change'] / prev_close) * 100 if prev_close else 0
            stock_data['rsi'] = calculate_rsi(hist)
            stock_data['pledge'] = get_pledge_percentage(symbol)
            stock_data['marketCap'] = info.get('marketCap', 0) / 10**7
            stock_data['high'] = info.get('fiftyTwoWeekHigh', 0)
            stock_data['low'] = info.get('fiftyTwoWeekLow', 0)
            
            all_stocks_data.append(stock_data)
            time.sleep(0.5) # Be polite to servers
        except Exception as e:
            print(f"Error fetching data for {symbol}: {e}")
            continue
    print("--- Data fetch cycle complete ---")
    return {
        "data": all_stocks_data,
        "last_updated": time.strftime('%I:%M:%S %p, %b %d, %Y')
    }

# --- FLASK ROUTES (The Web Server Part) ---

@app.route('/')
def home():
    """Serves the main HTML page."""
    return render_template('index.html')

@app.route('/data')
def get_data():
    """
    This is our API endpoint. It fetches fresh data and tells Vercel to cache it.
    """
    data = fetch_all_data()
    response = make_response(jsonify(data))
    
    # This is the magic header!
    # s-maxage=900 tells Vercel's Edge Cache to cache this for 900 seconds (15 minutes).
    # stale-while-revalidate allows serving a stale (old) response while a new one is being generated.
    response.headers['Cache-Control'] = 's-maxage=900, stale-while-revalidate'
    
    return response

# Note: No 'if __name__ == "__main__"' block is needed for Vercel deployment.
# Vercel uses a WSGI server to run the 'app' variable.