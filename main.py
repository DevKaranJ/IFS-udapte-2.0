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

def main():
    print(f"Starting Trading Bot... [PAPER TRADING: {PAPER_TRADING}]")
    init_log()

    # 1. Load config
    config_path = 'strategies/strategy_1_IFS/config.json'
    with open(config_path, 'r') as f:
        config = json.load(f)

    symbol = config.get('symbol', 'BTCUSDT')

    # 2. Initialize Core Components
    exchange = ExchangeInterface(use_testnet=True)

    # Set leverage
    leverage = config.get('leverage', 3)
    if not PAPER_TRADING:
        exchange.set_leverage(symbol, leverage)

    streamer = DataStreamer(symbol=symbol, use_testnet=True)
    risk_manager = RiskManager(exchange, config)
    strategy = Strategy_IFS(exchange, symbol)

    # 3. Start Data Streamer
    streamer.start()

    # Give the streamer a moment to connect and populate initial data
    print("Waiting for WebSocket data...")
    time.sleep(5)

    # 4. Main Loop
    try:
        while True:
            live_data = streamer.live_data
            current_price = live_data.get('mid_price', 0)

            if current_price > 0:
                # Update Risk Manager (check SL, Trailing, Invalidation)
                risk_manager.update(current_price, paper_trading=PAPER_TRADING)

                # Check Strategy
                if not risk_manager.in_position:
                    signal = strategy.update(live_data)

                    if signal in ['BUY', 'SELL']:
                        # Get Balance
                        balance = 10000.0 # Default for paper trading if API fails
                        if not PAPER_TRADING:
                            actual_balance = exchange.get_account_balance('USDT')
                            if actual_balance > 0:
                                balance = actual_balance

                        # Execute
                        executed = risk_manager.execute_trade(signal, current_price, balance, paper_trading=PAPER_TRADING)

                        if executed:
                            log_action(signal, symbol, current_price, risk_manager.quantity, "Strategy Entry")

            # Sleep briefly to prevent high CPU usage
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\nStopping bot...")
        streamer.stop()

if __name__ == "__main__":
    main()
