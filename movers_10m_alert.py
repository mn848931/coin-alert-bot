import os
import time
import requests
from collections import deque, defaultdict
from datetime import datetime, timedelta, timezone

# ====== 환경변수 (Render 대시보드에서 설정) ======
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8206201047:AAE600FLvi8bnNYZNOlBaXfAgJC-sJCJQy4")
TELEGRAM_CHAT_ID   = os.getenv("TELEGRAM_CHAT_ID",   "5992540937")

# 파라미터(원하면 Render에서 환경변수로 수정 가능)
THRESHOLD_PCT = float(os.getenv("THRESHOLD_PCT", "5"))   # 10분 내 ±5%
POLL_SECS     = int(os.getenv("POLL_SECS", "60"))        # 1분마다 체크
WINDOW_SECS   = int(os.getenv("WINDOW_SECS", "600"))     # 10분
WATCHLIST_RAW = os.getenv("WATCHLIST", "")               # "BTCUSDT,ETHUSDT" 형태면 해당 심볼만 감시
WATCHLIST = [s.strip().upper() for s in WATCHLIST_RAW.split(",") if s.strip()] or None

# Binance USDT-M Futures 공개 티커 (API키 불필요)
BINANCE_FUTURES_TICKER = "https://fapi.binance.com/fapi/v1/ticker/price"

# 내부 상태
history = defaultdict(lambda: deque(maxlen=1200))
session = requests.Session()


def now_utc():
    return datetime.now(timezone.utc)


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": text, "disable_web_page_preview": True}
    try:
        session.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"[TG] send error: {e}")


def fetch_all_tickers():
    """Binance 선물 USDT 페어 현재가 전량"""
    r = session.get(BINANCE_FUTURES_TICKER, timeout=10)
    r.raise_for_status()
    data = r.json()  # [{'symbol':'BTCUSDT','price':'67890.12'}, ...]
    if WATCHLIST:
        return [d for d in data if d.get("symbol") in WATCHLIST]
    return [d for d in data if (sym := d.get("symbol","")).endswith("USDT")]


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
            price = float(item.get("price"))
        except Exception:
            continue

        dq = history[sym]
        dq.append((t_now, price))

        # 10분 창 밖 데이터 제거
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
                        f"🚨 선물 급변동 감지: {sym}\n"
                        f"10분 변동: {pct:.2f}% {direction}\n"
                        f"현재가: {price:g}\n"
                        f"기준가(10분 전): {oldest_price:g}\n"
                        f"시각(UTC): {t_now.strftime('%Y-%m-%d %H:%M:%S')}"
                    )
                    send_telegram(msg)


if __name__ == "__main__":
    print("Started: 10m ±5% futures mover watcher (Binance USDT-M, no API key).")
    # 시작 알림(옵션)
    try:
        send_telegram("✅ 코인 급등락 알림 봇이 시작되었습니다. (Render)")
    except:
        pass

    while True:
        try:
            check_moves()
        except Exception as e:
            print(f"[LOOP] error: {e}")
        time.sleep(POLL_SECS)
