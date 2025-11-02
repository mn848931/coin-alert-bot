import os
import time
import threading
from collections import deque, defaultdict
from datetime import datetime, timedelta, timezone

import requests
from flask import Flask

# ====== 환경변수 (Replit Secrets에 넣는 것을 권장) ======
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8206201047:AAE600FLvi8bnNYZNOlBaXfAgJC-sJCJQy4")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "5992540937")

THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", "5"))   # 10분 내 ±5%
POLL_SECS     = int(os.getenv("POLL_SECS", "60"))        # 1분마다 체크
WINDOW_SECS   = int(os.getenv("WINDOW_SECS", "600"))     # 10분
WATCHLIST_RAW = os.getenv("WATCHLIST", "")               # "BTCUSDT,ETHUSDT"
WATCHLIST = [s.strip().upper() for s in WATCHLIST_RAW.split(",") if s.strip()] or None

# Bybit 선물(USDT-M, linear) 공개 티커 (API 키 불필요)
BYBIT_TICKER = "https://api.bybit.com/v5/market/tickers?category=linear"

# 내부 상태
history = defaultdict(lambda: deque(maxlen=1200))
session = requests.Session()

# ----- Replit Keepalive용 초간단 웹서버 -----
app = Flask(__name__)
@app.route("/")
def home():
    return "Coin alert bot is running."

def run_keepalive():
    app.run(host="0.0.0.0", port=8080)

def now_utc():
    return datetime.now(timezone.utc)

def send_telegram(text: str):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        session.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True}, timeout=10)
    except Exception as e:
        print(f"[TG] send error: {e}")

def fetch_all_tickers():
    """Bybit 선물 USDT 페어 현재가 목록 반환"""
    r = session.get(BYBIT_TICKER, timeout=15)
    r.raise_for_status()
    data = r.json()
    items = data.get("result", {}).get("list", []) or []
    if WATCHLIST:
        return [d for d in items if d.get("symbol") in WATCHLIST]
    return [d for d in items if (d.get("symbol","")).endswith("USDT")]

def check_moves():
    t_now = now_utc()
    try:
        tickers = fetch_all_tickers()
    except Exception as e:
        print(f"[FETCH] error: {e}")
        return

    cutoff = t_now - timedelta(seconds=WINDOW_SECS)

    for item in tickers:
        sym = item.get("symbol")
        try:
            price = float(item.get("lastPrice"))
        except Exception:
            continue

        dq = history[sym]
        dq.append((t_now, price))

        # 윈도우 밖 제거
        while dq and dq[0][0] < cutoff:
            dq.popleft()

        # 비교 가능하면 10분 전 대비 변화율 계산
        if len(dq) >= 2:
            oldest_time, oldest_price = dq[0]
            if oldest_price > 0:
                pct = (price - oldest_price) / oldest_price * 100.0
                if abs(pct) >= THRESHOLD_PCT:
                    direction = "상승" if pct > 0 else "하락"
                    msg = (
                        f"🚨 급변동 감지: {sym}\n"
                        f"10분 변동: {pct:.2f}% {direction}\n"
                        f"현재가: {price:g}\n"
                        f"기준가(10분 전): {oldest_price:g}\n"
                        f"시각(UTC): {t_now.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    send_telegram(msg)

def main_loop():
    print("Started: 10m ±5% futures mover watcher (Bybit linear, no API key).")
    try:
        send_telegram("✅ 코인 급등락 알림 봇이 시작되었습니다. (Replit / Bybit)")
    except:
        pass

    while True:
        try:
            check_moves()
        except Exception as e:
            print(f"[LOOP] error: {e}")
        time.sleep(POLL_SECS)

if __name__ == "__main__":
    # 웹서버(keepalive) 스레드 시작
    threading.Thread(target=run_keepalive, daemon=True).start()
    # 메인 감시 루프
    main_loop()
