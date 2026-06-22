import json
import time
import threading
import websocket
from collections import deque

class DataStreamer:
    def __init__(self, symbol='btcusdt', use_testnet=True):
        self.symbol = symbol.lower()
        self.use_testnet = use_testnet

        if use_testnet:
            self.ws_url = f"wss://stream.binancefuture.com/ws"
        else:
            self.ws_url = f"wss://fstream.binance.com/ws"

        self.ws = None
        self.ws_thread = None

        # We need recent_trades to hold up to 60 seconds
        self.recent_trades = deque() # tuples of (timestamp_sec, quantity, price)

        # CVD components
        self.current_minute = int(time.time() // 60)
        self.minute_volumes = deque(maxlen=30) # Stores 1-min CVD deltas
        self.current_minute_volume = 0.0

        # To determine 30 min trend, we need price 30 mins ago
        self.mid_price_history = deque(maxlen=30)

        # Shared Dictionary for the strategy logic
        self.live_data = {
            'mid_price': 0.0,
            'bids': [], # list of [price, vol]
            'asks': [], # list of [price, vol]
            'recent_trades': [], # list of dicts for Filter D
            'cvd_buckets': [], # list of 1-minute bucket volumes (up to 30)
            'mid_price_30m_ago': None
        }

    def start(self):
        streams = f"{self.symbol}@depth20@100ms/{self.symbol}@aggTrade"
        url = f"{self.ws_url}/{streams}"

        self.ws = websocket.WebSocketApp(
            url,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            on_open=self.on_open
        )

        self.ws_thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.ws_thread.start()
        print(f"Started DataStreamer for {self.symbol} on {'Testnet' if self.use_testnet else 'Mainnet'}")

    def stop(self):
        if self.ws:
            self.ws.close()
        if self.ws_thread:
            self.ws_thread.join()

    def on_open(self, ws):
        print("WebSocket Connection Opened")

    def on_error(self, ws, error):
        print(f"WebSocket Error: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("WebSocket Connection Closed")

    def on_message(self, ws, message):
        data = json.loads(message)

        if 'e' in data:
            if data['e'] == 'aggTrade':
                self._process_trade(data)
            elif data['e'] == 'depthUpdate':
                self._process_depth(data)

    def _process_trade(self, data):
        price = float(data['p'])
        qty = float(data['q'])
        is_buyer_maker = data['m'] # True if sell order
        trade_time_sec = data['T'] / 1000.0

        # 1. Update CVD buckets
        current_time_min = int(trade_time_sec // 60)

        if current_time_min > self.current_minute:
            self.minute_volumes.append(self.current_minute_volume)
            self.mid_price_history.append(self.live_data['mid_price'])
            self.current_minute = current_time_min
            self.current_minute_volume = 0.0

            self.live_data['cvd_buckets'] = list(self.minute_volumes) + [0.0] # + [current_minute_volume] handled in logic

            if len(self.mid_price_history) == 30:
                self.live_data['mid_price_30m_ago'] = self.mid_price_history[0]

        # Calculate Delta for this trade (Buy Volume - Sell Volume)
        trade_value = price * qty
        if is_buyer_maker:
            self.current_minute_volume -= trade_value # Sell
        else:
            self.current_minute_volume += trade_value # Buy

        # Update live array so strategy gets instantaneous updates for current minute
        current_buckets = list(self.minute_volumes)
        current_buckets.append(self.current_minute_volume)
        self.live_data['cvd_buckets'] = current_buckets

        # 2. Maintain recent trades (60 seconds rolling buffer)
        self.recent_trades.append((trade_time_sec, qty, price))

        # Purge > 60s
        while self.recent_trades and trade_time_sec - self.recent_trades[0][0] > 60:
            self.recent_trades.popleft()

        # Update live_data for Filter D
        self.live_data['recent_trades'] = [
            {'timestamp': t, 'quantity': q, 'price': p} for t, q, p in self.recent_trades
        ]

    def _process_depth(self, data):
        if 'bids' not in data or 'asks' not in data:
            return

        bids = data['bids']
        asks = data['asks']

        if not bids or not asks:
            return

        # Cast to float lists
        self.live_data['bids'] = [[float(p), float(v)] for p, v in bids]
        self.live_data['asks'] = [[float(p), float(v)] for p, v in asks]

        best_bid = self.live_data['bids'][0][0]
        best_ask = self.live_data['asks'][0][0]
        self.live_data['mid_price'] = (best_bid + best_ask) / 2.0
