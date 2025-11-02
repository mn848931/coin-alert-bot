import os
import time
import threading
from collections import deque, defaultdict
from datetime import datetime, timedelta, timezone
import requests
from flask import Flask

# ==== 당신의 텔레그램 정보 ====
TELEGRAM_BOT_TOKEN = "8206201047:AAE600FLvi8bnNYZNOlBaXfAgJC-sJCJQy4"
TELEGRAM_CHAT_ID   = "5992540937"

# ==== 기본 설정 ====
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", "5"))   # 10분 내 ±5%
POLL_SECS     = int(os.getenv("POLL_SECS", "60"))        # 1분마다 체크
WINDOW_SECS   = int(os.getenv("WINDOW_SECS", "600"))     # 10분
WATCHLIST_RAW = os.getenv("WATCHLIST", "")               # "BTC,ETH,SOL"
WATCHLIST = [s.strip().upper() for s in WATCHLIST_RAW.split(",") if s.strip()] or None

# ==== CoinGecko API ====
COINGECKO_URL = "https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd&per_page=250&page=1"

# ==== 내부 상태 ====
history = defaultdict(lambda: deque(maxlen=1200))
session = requests.Session()

# ==== Render용 Keepalive Flask 서버 ====
app = Flask(__name__)
@app.route("/")
def home():
    return "🚀 CoinGecko Alert Bot is running!"

def run_server():
    app.run(host="0.0.0.0", port=8080)

def now_utc():
    return datetime.now(timezone.utc)

def send_telegram(text: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        session.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text}, timeout=10)
    except Exception as e:
        print(f"[Telegram Error] {e}")

def fetch_prices():
    """CoinGecko에서 상위 250개 코인 시세 불러오기"""
    r = session.get(COINGECKO_URL, timeout=15)
    r.raise_for_status()
    data = r.json()
    if WATCHLIST:
        return [d for d in data if d["symbol"].upper() in WATCHLIST]
    return data

def check_moves():
    now = now_utc()
    try:
        data = fetch_prices()
    except Exception as e:
        print(f"[Fetch Error] {e}")
        return

    cutoff = now - timedelta(seconds=WINDOW_SECS)

    for coin in data:
        sym = coin["symbol"].upper()
        price = float(coin["current_price"])
        dq = history[sym]
        dq.append((now, price))

        # 오래된 데이터 제거
        while dq and dq[0][0] < cutoff:
            dq.popleft()

        if len(dq) >= 2:
            old_time, old_price = dq[0]
            if old_price > 0:
                pct = (price - old_price) / old_price * 100
                if abs(pct) >= THRESHOLD_PCT:
                    direction = "상승" if pct > 0 else "하락"
                    msg = (
                        f"🚨 급변동 감지: {sym}\n"
                        f"10분 변동: {pct:.2f}% {direction}\n"
                        f"현재가: {price}\n"
                        f"기준가(10분 전): {old_price}\n"
                        f"시각(UTC): {now.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    send_telegram(msg)

def main_loop():
    print("Started: CoinGecko price change alert bot.")
    send_telegram("✅ 코인 급등락 알림 봇이 시작되었습니다. (Render / CoinGecko)")
    while True:
        try:
            check_moves()
        except Exception as e:
            print(f"[Loop Error] {e}")
        time.sleep(POLL_SECS)

if __name__ == "__main__":
    threading.Thread(target=run_server, daemon=True).start()
    main_loop()
