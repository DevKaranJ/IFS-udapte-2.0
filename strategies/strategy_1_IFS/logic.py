import json
import os
import pandas as pd
from datetime import datetime

class Strategy_IFS:
    def __init__(self, exchange_interface, symbol='BTCUSDT'):
        self.exchange = exchange_interface
        self.symbol = symbol

        # Load config
        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.daily_high = None
        self.daily_low = None
        self.fib_0618 = None
        self.fib_0382 = None

        # Calculate initial levels
        self.calculate_levels()

    def calculate_levels(self):
        """
        Filter A requirements:
        - Daily High/Low from last 24h of 1h klines
        - Fib 0.618 from last 7 days of 4h klines
        """
        print("Calculating Daily High/Low and Fib levels...")

        # 1. Daily High/Low (last 24 hours of 1h klines)
        # interval = '1h', limit = 24
        df_1h = self.exchange.get_historical_klines(self.symbol, '1h', limit=24)
        if df_1h is not None and not df_1h.empty:
            self.daily_high = df_1h['high'].max()
            self.daily_low = df_1h['low'].min()
            print(f"Daily High: {self.daily_high}, Daily Low: {self.daily_low}")

        # 2. Fib levels (last 7 days of 4h klines)
        # 7 days * 6 (4h periods per day) = 42 klines
        df_4h = self.exchange.get_historical_klines(self.symbol, '4h', limit=42)
        if df_4h is not None and not df_4h.empty:
            swing_high = df_4h['high'].max()
            swing_low = df_4h['low'].min()

            # Assuming downtrend for retracement: Fib 0.618 is from high to low
            # But we can calculate standard levels from low to high:
            diff = swing_high - swing_low
            self.fib_0618 = swing_high - (diff * 0.618) # 61.8% retracement from high
            self.fib_0382 = swing_high - (diff * 0.382)
            print(f"Fib 0.618: {self.fib_0618} (Swing H: {swing_high}, Swing L: {swing_low})")

    def alert(self, signal, reason):
        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{ts}] SIGNAL: {signal} | REASON: {reason}")

    def update(self, live_data):
        """
        Evaluates the 4 filters.
        Returns 'BUY', 'SELL', or 'HOLD'
        """
        mid_price = live_data.get('mid_price', 0)

        # Wait for sufficient data
        if mid_price == 0 or self.daily_high is None or self.fib_0618 is None:
            return 'HOLD'

        # --- Filter A: Location ---
        # Is mid_price within 0.05% of Daily High, Daily Low, or Fib 0.618?
        threshold = mid_price * 0.0005

        near_high = abs(mid_price - self.daily_high) <= threshold
        near_low = abs(mid_price - self.daily_low) <= threshold
        near_fib = abs(mid_price - self.fib_0618) <= threshold

        if not (near_high or near_low or near_fib):
            return 'HOLD'

        # --- Filter B: 30-minute Trend Confirmation ---
        # We need `mid_price_30m_ago` to determine price trend
        mid_price_30m_ago = live_data.get('mid_price_30m_ago')
        if mid_price_30m_ago is None:
            # Not enough data (needs 30 mins)
            return 'HOLD'

        price_trend_up = mid_price > mid_price_30m_ago
        price_trend_down = mid_price < mid_price_30m_ago

        # We need to know if CVD is making higher highs or lower lows.
        # Simplified: Current CVD > 0 implies net buying over 30 mins, < 0 implies net selling
        # A more strict "higher highs" check would look at the deque in data_streamer,
        # but current_cvd being positive and > previous is the essence of it.
        cvd = live_data.get('cvd', 0)

        # --- Filter C: Stacked Imbalance ---
        stacked_imbalance = live_data.get('stacked_imbalance', False)
        if not stacked_imbalance:
            return 'HOLD'

        # --- Filter D: Block Order Detected ---
        block_detected = live_data.get('block_detected', False)
        if not block_detected:
            return 'HOLD'

        # Final Decision Logic
        # We want to short if near Daily High and trend is down/exhausting
        # Since we are primarily looking to short (per user input: "We need to short and use leverage"),
        # Let's define the SELL condition:

        if near_high or near_fib:
            # If price is near high/fib, and we have imbalance + block
            # If price trend was up but now we want to catch reversal, or if price trend is down and CVD is down (confirming)
            if price_trend_down and cvd < 0:
                self.alert('SELL', f"Near Resistance, Trend Down, CVD < 0, Imbalance: {stacked_imbalance}, Block: {block_detected}")
                return 'SELL'

        if near_low:
            # Reverse logic for BUY if near low
            if price_trend_up and cvd > 0:
                self.alert('BUY', f"Near Support, Trend Up, CVD > 0, Imbalance: {stacked_imbalance}, Block: {block_detected}")
                return 'BUY'

        return 'HOLD'
