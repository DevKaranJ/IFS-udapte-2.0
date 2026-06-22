import time
import json
import csv
import os
from datetime import datetime

from core.exchange_interface import ExchangeInterface
from core.data_streamer import DataStreamer
from core.risk_manager import RiskManager
from strategies.strategy_1_IFS.logic import Strategy_IFS

PAPER_TRADING = True
LOG_FILE = 'trading_log.csv'

def init_log():
    if not os.path.exists(LOG_FILE):
        with open(LOG_FILE, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(['timestamp', 'action', 'symbol', 'price', 'quantity', 'reason'])

def log_action(action, symbol, price, quantity, reason=""):
    with open(LOG_FILE, 'a', newline='') as f:
        writer = csv.writer(f)
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        writer.writerow([ts, action, symbol, price, quantity, reason])

def is_within_trading_window():
    # Trading Window: 18:30 - 22:30 IST
    # UTC equivalent: 13:00 - 17:00 UTC
    now_utc = datetime.utcnow()
    current_hour = now_utc.hour
    current_minute = now_utc.minute

    time_float = current_hour + (current_minute / 60.0)

    # Check if inside 13:00 to 17:00 UTC
    if 13.0 <= time_float < 17.0:
        return True
    return False

def main():
    print(f"Starting Trading Bot... [PAPER TRADING: {PAPER_TRADING}]")
    init_log()

    config_path = 'strategies/strategy_1_IFS/config.json'
    with open(config_path, 'r') as f:
        config = json.load(f)

    symbol = config.get('symbol', 'BTCUSDT')

    exchange = ExchangeInterface(use_testnet=True)

    leverage = config.get('leverage', 3)
    if not PAPER_TRADING:
        exchange.set_leverage(symbol, leverage)

    streamer = DataStreamer(symbol=symbol, use_testnet=True)
    risk_manager = RiskManager(exchange, config)
    strategy = Strategy_IFS(exchange, symbol)

    streamer.start()

    print("Waiting for WebSocket data...")
    time.sleep(5)

    last_level_fetch_date = None

    try:
        while True:
            now_utc = datetime.utcnow()

            # 1. At 12:30 UTC (18:00 IST), fetch daily levels
            if now_utc.hour == 12 and now_utc.minute >= 30:
                today_str = now_utc.strftime("%Y-%m-%d")
                if last_level_fetch_date != today_str:
                    strategy.calculate_levels()
                    last_level_fetch_date = today_str

            live_data = streamer.live_data
            current_price = live_data.get('mid_price', 0)

            if current_price > 0:
                # Update Risk Manager
                risk_manager.update(current_price, paper_trading=PAPER_TRADING)

                # Check Trading Session
                in_session = is_within_trading_window()

                if not in_session and risk_manager.in_position:
                    risk_manager.close_all("Session Closed (NY Drift)", paper_trading=PAPER_TRADING)
                    log_action("CLOSE", symbol, current_price, risk_manager.quantity, "Session Close")

                if in_session and not risk_manager.in_position:
                    signal = strategy.update(live_data)

                    if signal in ['BUY', 'SELL']:
                        balance = 10000.0
                        if not PAPER_TRADING:
                            actual_balance = exchange.get_account_balance('USDT')
                            if actual_balance > 0:
                                balance = actual_balance

                        executed = risk_manager.execute_trade(signal, current_price, balance, paper_trading=PAPER_TRADING)

                        if executed:
                            log_action(signal, symbol, current_price, risk_manager.quantity, "Strategy Entry")

            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopping bot...")
        streamer.stop()

if __name__ == "__main__":
    main()
