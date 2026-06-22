import json
import os
import pandas as pd
from datetime import datetime

class Strategy_IFS:
    def __init__(self, exchange_interface, symbol='BTCUSDT'):
        self.exchange = exchange_interface
        self.symbol = symbol

        config_path = os.path.join(os.path.dirname(__file__), 'config.json')
        with open(config_path, 'r') as f:
            self.config = json.load(f)

        self.proximity_threshold = self.config.get('proximity_threshold', 0.05)
        self.imbalance_ratio = self.config.get('imbalance_ratio', 3.0)
        self.imbalance_levels = self.config.get('imbalance_levels', 3)
        self.block_order_threshold = self.config.get('block_order_threshold', 10.0)
        self.fib_lookback_days = self.config.get('fib_lookback_days', 7)
        self.fib_timeframe = self.config.get('fib_timeframe', '4h')

        self.daily_high = None
        self.daily_low = None
        self.weekly_pivots = []
        self.fib_levels = []
        self.fvg_zones = [] # list of dicts: {'top': x, 'bottom': y, 'type': 'bullish'/'bearish'}

        self.calculate_levels()

    def calculate_levels(self):
        print(f"[{datetime.now().strftime('%H:%M:%S')}] Fetching Daily, Weekly, and Fib Levels...")

        # 1. Daily High/Low (last 24 hours of 1h klines)
        df_1h = self.exchange.get_historical_klines(self.symbol, '1h', limit=24)
        if df_1h is not None and not df_1h.empty:
            self.daily_high = df_1h['high'].max()
            self.daily_low = df_1h['low'].min()

        # 2. Weekly Pivots (Need previous week's High, Low, Close)
        # Using 1w interval, limit 2 to get last closed week
        df_1w = self.exchange.get_historical_klines(self.symbol, '1w', limit=2)
        if df_1w is not None and len(df_1w) >= 2:
            prev_week = df_1w.iloc[-2]
            self._calculate_weekly_pivots(prev_week['high'], prev_week['low'], prev_week['close'])

        # 3. Fib Levels & FVG (last 7 days of 4h klines)
        limit_4h = self.fib_lookback_days * 6 # 6 4H periods per day
        df_4h = self.exchange.get_historical_klines(self.symbol, self.fib_timeframe, limit=limit_4h)
        if df_4h is not None and not df_4h.empty:
            swing_high = df_4h['high'].max()
            swing_low = df_4h['low'].min()
            self._calculate_fib_levels(swing_high, swing_low)
            self._calculate_fvg(df_4h)

        print(f"Levels Updated. Daily High: {self.daily_high}, Low: {self.daily_low}")

    def _calculate_weekly_pivots(self, high, low, close):
        p = (high + low + close) / 3
        r1 = (2 * p) - low
        r2 = p + (high - low)
        s1 = (2 * p) - high
        s2 = p - (high - low)
        self.weekly_pivots = [p, r1, r2, s1, s2]

    def _calculate_fib_levels(self, swing_high, swing_low):
        diff = swing_high - swing_low
        # Assuming standard retracements from Low to High
        self.fib_levels = [
            swing_high - (diff * 0.382),
            swing_high - (diff * 0.500),
            swing_high - (diff * 0.618),
            swing_high - (diff * 0.786),
            swing_high + (diff * 0.272), # 1.272 ext
            swing_high + (diff * 0.618)  # 1.618 ext
        ]

    def _calculate_fvg(self, df):
        self.fvg_zones = []
        for i in range(2, len(df)):
            c1 = df.iloc[i-2]
            # c2 = df.iloc[i-1]
            c3 = df.iloc[i]

            # Bullish FVG: Low of candle 3 is higher than High of candle 1
            if c3['low'] > c1['high']:
                self.fvg_zones.append({'bottom': c1['high'], 'top': c3['low'], 'type': 'bullish'})

            # Bearish FVG: High of candle 3 is lower than Low of candle 1
            if c3['high'] < c1['low']:
                self.fvg_zones.append({'bottom': c3['high'], 'top': c1['low'], 'type': 'bearish'})

    def _is_near_daily_high(self, mid_price):
        if not self.daily_high: return False
        return abs(mid_price - self.daily_high) / mid_price * 100 <= self.proximity_threshold

    def _is_near_daily_low(self, mid_price):
        if not self.daily_low: return False
        return abs(mid_price - self.daily_low) / mid_price * 100 <= self.proximity_threshold

    def _is_in_fvg(self, mid_price):
        for fvg in self.fvg_zones:
            if fvg['bottom'] <= mid_price <= fvg['top']:
                return True
        return False

    def _at_key_level(self, mid_price):
        if self._is_near_daily_high(mid_price) or self._is_near_daily_low(mid_price):
            return True

        for pivot in self.weekly_pivots:
            if abs(mid_price - pivot) / mid_price * 100 <= self.proximity_threshold:
                return True

        for fib in self.fib_levels:
            if abs(mid_price - fib) / mid_price * 100 <= self.proximity_threshold:
                return True

        if self._is_in_fvg(mid_price):
            return True

        return False

    def _get_price_direction(self, mid_price, mid_price_30m_ago):
        if mid_price_30m_ago is None: return None
        return 'UP' if mid_price > mid_price_30m_ago else 'DOWN'

    def _get_cvd_direction(self, cvd_buckets):
        if len(cvd_buckets) < 30: return None

        # 30 min rolling sum
        cvd_30min = sum(cvd_buckets[-30:])

        # 5 min rolling sum (short term slope)
        cvd_5min = sum(cvd_buckets[-5:])

        # simplified check: if short term momentum aligns with long term sum
        # higher highs over 30 mins means overall cvd is positive and growing
        return 'UP' if cvd_5min > 0 and cvd_30min > 0 else 'DOWN'

    def _cvd_confirms_trend(self, cvd_buckets, mid_price, mid_price_30m_ago):
        price_direction = self._get_price_direction(mid_price, mid_price_30m_ago)
        cvd_direction = self._get_cvd_direction(cvd_buckets)

        if not price_direction or not cvd_direction:
            return False

        if price_direction == 'UP' and cvd_direction == 'UP':
            return True
        elif price_direction == 'DOWN' and cvd_direction == 'DOWN':
            return True

        return False # Divergence

    def _stacked_imbalance(self, bids, asks):
        # We need at least top 5
        if len(bids) < 5 or len(asks) < 5: return None

        buy_imbalance_count = 0
        sell_imbalance_count = 0

        for i in range(5):
            bid_vol = bids[i][1]
            ask_vol = asks[i][1]

            # Avoid divide by zero
            if bid_vol == 0: bid_vol = 0.0001
            if ask_vol == 0: ask_vol = 0.0001

            if ask_vol > self.imbalance_ratio * bid_vol:
                buy_imbalance_count += 1
                sell_imbalance_count = 0
            elif bid_vol > self.imbalance_ratio * ask_vol:
                sell_imbalance_count += 1
                buy_imbalance_count = 0
            else:
                buy_imbalance_count = 0
                sell_imbalance_count = 0

            if buy_imbalance_count >= self.imbalance_levels:
                return 'BUY'
            elif sell_imbalance_count >= self.imbalance_levels:
                return 'SELL'

        return None

    def _block_detected(self, recent_trades):
        for trade in recent_trades:
            if trade['quantity'] >= self.block_order_threshold:
                return True

            # Cluster check
            cluster = [t for t in recent_trades
                       if abs(t['timestamp'] - trade['timestamp']) <= 1.0
                       and t['quantity'] >= self.block_order_threshold * 0.5]

            if len(cluster) >= 3:
                return True
        return False

    def update(self, live_data):
        mid_price = live_data.get('mid_price', 0)
        cvd_buckets = live_data.get('cvd_buckets', [])
        bids = live_data.get('bids', [])
        asks = live_data.get('asks', [])
        recent_trades = live_data.get('recent_trades', [])
        mid_price_30m_ago = live_data.get('mid_price_30m_ago')

        if mid_price == 0 or not bids or not asks:
            return 'HOLD'

        # Check Filters
        filter_A = self._at_key_level(mid_price)
        filter_B = self._cvd_confirms_trend(cvd_buckets, mid_price, mid_price_30m_ago)
        filter_C = self._stacked_imbalance(bids, asks)
        filter_D = self._block_detected(recent_trades)

        if filter_A and filter_B and filter_D:
            if filter_C == 'BUY':
                # Further check: are we absorbing?
                # "bid_vol_1 + bid_vol_2 > ask_vol_1 + ask_vol_2 by large margin"
                top2_bid_vol = bids[0][1] + bids[1][1]
                top2_ask_vol = asks[0][1] + asks[1][1]
                if top2_bid_vol > (top2_ask_vol * 1.5): # Absorption
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] LONG ABSORPTION TRIGGERED.")
                    return 'BUY'

            elif filter_C == 'SELL':
                top2_bid_vol = bids[0][1] + bids[1][1]
                top2_ask_vol = asks[0][1] + asks[1][1]
                if top2_ask_vol > (top2_bid_vol * 1.5): # Absorption
                    print(f"[{datetime.now().strftime('%H:%M:%S')}] SHORT ABSORPTION TRIGGERED.")
                    return 'SELL'

        return 'HOLD'
