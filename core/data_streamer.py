import json
import time
import threading
import websocket
from collections import deque

class DataStreamer:
    def __init__(self, symbol='btcusdt', use_testnet=True):
        self.symbol = symbol.lower()
        self.use_testnet = use_testnet

        # Testnet Futures Websocket Base URL
        if use_testnet:
            self.ws_url = f"wss://stream.binancefuture.com/ws"
        else:
            self.ws_url = f"wss://fstream.binance.com/ws"

        self.ws = None
        self.ws_thread = None

        # Shared Dictionary for live data
        self.live_data = {
            'mid_price': 0.0,
            'cvd': 0.0,
            'stacked_imbalance': False,
            'block_detected': False,
            'best_bid': 0.0,
            'best_ask': 0.0
        }

        # Internal state for calculations
        self.current_minute = int(time.time() // 60)
        self.minute_volumes = deque(maxlen=30) # Stores (minute_timestamp, volume_delta)
        self.current_minute_volume = 0.0

        self.recent_trades = deque(maxlen=100) # (timestamp, quantity, price)

        # CVD calculation variables
        self.cvd_history = deque(maxlen=30) # Store 1-minute bucketed CVD values for trend check
        self.mid_price_history = deque(maxlen=30) # Store 1-minute mid_prices for trend check

    def start(self):
        # Subscribe to depth20@100ms and aggTrade
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
        # aggTrade format:
        # {
        #   "e": "aggTrade",  // Event type
        #   "E": 123456789,   // Event time
        #   "s": "BTCUSDT",   // Symbol
        #   "a": 5933014,     // Aggregate trade ID
        #   "p": "0.001",     // Price
        #   "q": "100",       // Quantity
        #   "f": 100,         // First trade ID
        #   "l": 105,         // Last trade ID
        #   "T": 123456785,   // Trade time
        #   "m": true,        // Is the buyer the market maker? (True means sell, False means buy)
        # }

        price = float(data['p'])
        qty = float(data['q'])
        is_buyer_maker = data['m'] # True if sell order, False if buy order
        trade_time = data['T']

        # 1. Update CVD (Cumulative Volume Delta) - 30 min rolling window bucketed by minute
        current_time_min = int(trade_time / 1000 // 60)

        if current_time_min > self.current_minute:
            # We entered a new minute
            self.minute_volumes.append((self.current_minute, self.current_minute_volume))
            self.cvd_history.append(self.live_data['cvd'])
            self.mid_price_history.append(self.live_data['mid_price'])
            self.current_minute = current_time_min
            self.current_minute_volume = 0.0

            # Recalculate 30-min CVD by summing up the last 30 minutes
            rolling_cvd = sum([v for t, v in self.minute_volumes]) + self.current_minute_volume
            self.live_data['cvd'] = rolling_cvd

            # We also need to store historical mid_prices exactly 30 mins ago.
            # We have a deque of maxlen 30, so the 0th element is ~30 mins ago.
            if len(self.mid_price_history) == 30:
                self.live_data['mid_price_30m_ago'] = self.mid_price_history[0]
            else:
                self.live_data['mid_price_30m_ago'] = None

        # Calculate Delta for this trade (Buy Volume - Sell Volume)
        # If buyer is maker, it was a market sell hitting limit bids -> Sell Volume (-)
        # If buyer is NOT maker, it was a market buy hitting limit asks -> Buy Volume (+)
        trade_value = price * qty
        if is_buyer_maker:
            self.current_minute_volume -= trade_value
        else:
            self.current_minute_volume += trade_value

        self.live_data['cvd'] += (trade_value if not is_buyer_maker else -trade_value)

        # 2. Check for Block Orders (> 10 BTC in last 5 seconds)
        current_time_sec = trade_time / 1000.0
        self.recent_trades.append((current_time_sec, qty, price))

        # Remove trades older than 5 seconds
        while self.recent_trades and current_time_sec - self.recent_trades[0][0] > 5:
            self.recent_trades.popleft()

        # Check if there's any trade > 10 BTC
        block_detected = any(t_qty > 10.0 for t_time, t_qty, t_price in self.recent_trades)
        self.live_data['block_detected'] = block_detected


    def _process_depth(self, data):
        # Format of depth20 is actually not depthUpdate event, it's just raw order book snap
        # wait, depth20 stream sends full order book every 100ms

        if 'bids' not in data or 'asks' not in data:
            return

        bids = data['bids']
        asks = data['asks']

        if not bids or not asks:
            return

        best_bid = float(bids[0][0])
        best_ask = float(asks[0][0])

        self.live_data['best_bid'] = best_bid
        self.live_data['best_ask'] = best_ask
        self.live_data['mid_price'] = (best_bid + best_ask) / 2.0

        # 3. Stacked Imbalance: top 5 bid/ask levels
        # 3 consecutive levels where Ask/Bid volume ratio > 3 or Bid/Ask volume ratio > 3
        # Ensure we have at least 5 levels
        if len(bids) >= 5 and len(asks) >= 5:
            imbalance_detected = False

            # We look for 3 consecutive levels in the top 5 (indices 0-1-2, 1-2-3, 2-3-4)
            for i in range(3):
                consecutive_ask_heavy = True
                consecutive_bid_heavy = True

                for j in range(3):
                    idx = i + j
                    bid_vol = float(bids[idx][1])
                    ask_vol = float(asks[idx][1])

                    if bid_vol == 0 and ask_vol > 0:
                        ask_ratio = float('inf')
                        bid_ratio = 0
                    elif ask_vol == 0 and bid_vol > 0:
                        bid_ratio = float('inf')
                        ask_ratio = 0
                    elif bid_vol == 0 and ask_vol == 0:
                        ask_ratio = 0
                        bid_ratio = 0
                    else:
                        ask_ratio = ask_vol / bid_vol
                        bid_ratio = bid_vol / ask_vol

                    if ask_ratio <= 3.0:
                        consecutive_ask_heavy = False
                    if bid_ratio <= 3.0:
                        consecutive_bid_heavy = False

                if consecutive_ask_heavy or consecutive_bid_heavy:
                    imbalance_detected = True
                    break

            self.live_data['stacked_imbalance'] = imbalance_detected
