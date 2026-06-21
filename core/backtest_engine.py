import pandas as pd
import json
import math
from strategies.strategy_1_IFS.logic import Strategy_IFS

class MockExchange:
    """Mocks the exchange interface for the Strategy to fetch static daily/fib levels"""
    def __init__(self):
        pass
    def get_historical_klines(self, symbol, interval, limit=24):
        # Return empty dataframe to prevent API calls, we'll manually inject levels for backtesting
        return pd.DataFrame()

class BacktestEngine:
    def __init__(self, data_file, config_file):
        self.data_file = data_file
        with open(config_file, 'r') as f:
            self.config = json.load(f)

        self.initial_balance = 10000.0
        self.balance = self.initial_balance
        self.position = None # 'BUY', 'SELL' or None
        self.entry_price = 0.0
        self.quantity = 0.0
        self.sl_price = 0.0

        self.trades = []

        # Risk params
        self.risk_percent = self.config.get('risk_percent', 1.0) / 100.0
        self.sl_pct = self.config.get('sl_pct', 0.5) / 100.0

    def calculate_position_size(self, entry_price):
        risk_amount = self.balance * self.risk_percent
        sl_distance = entry_price * self.sl_pct
        if sl_distance == 0: return 0
        qty = risk_amount / sl_distance
        return math.floor(qty * 1000) / 1000.0

    def run(self):
        print(f"Loading data from {self.data_file}...")
        try:
            df = pd.read_csv(self.data_file)
        except Exception as e:
            print(f"Error loading CSV: {e}")
            return

        # Initialize strategy with mock exchange
        mock_exchange = MockExchange()
        strategy = Strategy_IFS(mock_exchange, symbol='BTCUSDT')

        # Manually set Strategy levels for backtesting (In a real scenario, you'd calculate these from historical klines)
        strategy.daily_high = df['price'].max() if 'price' in df else 65000.0
        strategy.daily_low = df['price'].min() if 'price' in df else 60000.0
        strategy.fib_0618 = strategy.daily_high - ((strategy.daily_high - strategy.daily_low) * 0.618)

        print(f"Starting Backtest. Initial Balance: {self.balance}")

        # Simulate live_data dictionary building row by row
        live_data = {
            'mid_price': 0.0,
            'cvd': 0.0,
            'stacked_imbalance': False,
            'block_detected': False,
            'mid_price_30m_ago': 0.0 # simplified
        }

        for index, row in df.iterrows():
            # Update live_data from row
            # Expected CSV columns: timestamp, price, bid_vol, ask_vol, trade_size, cvd_calc
            current_price = float(row.get('price', 0))
            if current_price == 0: continue

            live_data['mid_price'] = current_price
            live_data['cvd'] = float(row.get('cvd', 0))
            live_data['stacked_imbalance'] = bool(row.get('stacked_imbalance', False))
            live_data['block_detected'] = bool(row.get('block_detected', False))
            live_data['mid_price_30m_ago'] = float(row.get('mid_price_30m_ago', current_price))

            timestamp = row.get('timestamp', index)

            # Check existing position for Stop Loss or Take Profit (Simplified)
            if self.position:
                if self.position == 'BUY' and current_price <= self.sl_price:
                    self._close_position(timestamp, current_price, "SL Hit")
                elif self.position == 'SELL' and current_price >= self.sl_price:
                    self._close_position(timestamp, current_price, "SL Hit")
                # Add Trailing Stop / Invalidation logic here as needed for comprehensive backtesting
                continue # Skip new entries while in position

            # Query Strategy
            signal = strategy.update(live_data)

            if signal in ['BUY', 'SELL']:
                self.position = signal
                self.entry_price = current_price
                self.quantity = self.calculate_position_size(current_price)

                if signal == 'BUY':
                    self.sl_price = self.entry_price * (1 - self.sl_pct)
                else:
                    self.sl_price = self.entry_price * (1 + self.sl_pct)

                print(f"[{timestamp}] Opened {signal} @ {current_price}, Qty: {self.quantity}, SL: {self.sl_price}")

        # Close open position at end
        if self.position:
            last_price = df.iloc[-1]['price']
            self._close_position("END", last_price, "End of Data")

        print("\n--- Backtest Results ---")
        print(f"Final Balance: {self.balance:.2f}")
        print(f"Total Trades: {len(self.trades)}")

    def _close_position(self, timestamp, current_price, reason):
        pnl = 0
        if self.position == 'BUY':
            pnl = (current_price - self.entry_price) * self.quantity
        elif self.position == 'SELL':
            pnl = (self.entry_price - current_price) * self.quantity

        self.balance += pnl
        print(f"[{timestamp}] Closed {self.position} @ {current_price} | PnL: {pnl:.2f} | Reason: {reason}")
        self.trades.append({'side': self.position, 'pnl': pnl})
        self.position = None

if __name__ == "__main__":
    # Create dummy data for demonstration
    import os
    if not os.path.exists('data/btc_orderbook_sample.csv'):
        dummy_data = """timestamp,price,cvd,stacked_imbalance,block_detected,mid_price_30m_ago
1,60000,-500,False,False,60100
2,60050,-1000,True,True,60150
3,60100,-1500,True,True,60200
"""
        with open('data/btc_orderbook_sample.csv', 'w') as f:
            f.write(dummy_data)

    engine = BacktestEngine('data/btc_orderbook_sample.csv', 'strategies/strategy_1_IFS/config.json')
    engine.run()
