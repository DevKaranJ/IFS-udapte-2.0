import time
import math

class RiskManager:
    def __init__(self, exchange_interface, config):
        self.exchange = exchange_interface
        self.config = config

        self.risk_percent = self.config.get('risk_percent', 1.0) / 100.0
        self.sl_pct = self.config.get('sl_pct', 0.5) / 100.0
        self.trail_activation_pct = self.config.get('trail_activation', 1.5) / 100.0
        self.symbol = self.config.get('symbol', 'BTCUSDT')

        self.in_position = False
        self.position_side = None # 'BUY' or 'SELL'
        self.entry_price = 0.0
        self.entry_time = 0.0
        self.quantity = 0.0

        self.sl_price = 0.0
        self.breakeven_activated = False

    def calculate_position_size(self, account_balance, entry_price):
        """
        Calculates position size based on risk amount and stop loss distance.
        Formula: (Balance * risk) / (entry - stop_loss)
        Since SL is a fixed percentage, SL distance = entry_price * sl_pct
        """
        risk_amount = account_balance * self.risk_percent
        sl_distance = entry_price * self.sl_pct

        if sl_distance == 0:
            return 0.0

        qty = risk_amount / sl_distance

        # Round to 3 decimal places for BTC
        return math.floor(qty * 1000) / 1000.0

    def execute_trade(self, signal, current_price, account_balance, paper_trading=True):
        if self.in_position:
            print("Already in position, ignoring signal.")
            return False

        self.entry_price = current_price
        self.position_side = signal
        self.quantity = self.calculate_position_size(account_balance, self.entry_price)

        if self.quantity <= 0:
            print("Calculated quantity is 0, aborting trade.")
            return False

        # Calculate SL Price
        if signal == 'BUY':
            self.sl_price = self.entry_price * (1 - self.sl_pct)
        else:
            self.sl_price = self.entry_price * (1 + self.sl_pct)

        self.entry_time = time.time()
        self.breakeven_activated = False
        self.in_position = True

        print(f"--- EXECUTING {signal} ---")
        print(f"Entry: {self.entry_price}")
        print(f"Size: {self.quantity}")
        print(f"Initial SL: {self.sl_price}")

        if not paper_trading:
            # Place Market Order
            order_side = 'BUY' if signal == 'BUY' else 'SELL'
            self.exchange.place_market_order(self.symbol, order_side, self.quantity)

            # Place Stop Market Order
            sl_side = 'SELL' if signal == 'BUY' else 'BUY'
            self.exchange.place_stop_market_order(self.symbol, sl_side, self.sl_price, close_position=True)

        return True

    def update(self, current_price, paper_trading=True):
        """
        Monitors open position for trailing stop and 60-second invalidation rule.
        """
        if not self.in_position:
            return

        time_in_trade = time.time() - self.entry_time

        # 1. 60-second invalidation (reversal)
        # "If price is reversed within 60 seconds, trigger a manual market close."
        # Meaning if it crosses back through entry price.
        if time_in_trade <= 60:
            if self.position_side == 'BUY' and current_price < self.entry_price:
                self._close_position("60-second Invalidation: Price reversed below entry.", paper_trading)
                return
            elif self.position_side == 'SELL' and current_price > self.entry_price:
                self._close_position("60-second Invalidation: Price reversed above entry.", paper_trading)
                return

        # 2. Hard Stop Loss hit (mainly for paper trading simulation or backup)
        if self.position_side == 'BUY' and current_price <= self.sl_price:
            self._close_position("Stop Loss Hit.", paper_trading)
            return
        elif self.position_side == 'SELL' and current_price >= self.sl_price:
            self._close_position("Stop Loss Hit.", paper_trading)
            return

        # 3. Trailing Stop to Breakeven
        # "If price moves 1.5% in our favor, move the stop-loss to the entry price"
        if not self.breakeven_activated:
            profit_pct = 0.0
            if self.position_side == 'BUY':
                profit_pct = (current_price - self.entry_price) / self.entry_price
            else:
                profit_pct = (self.entry_price - current_price) / self.entry_price

            if profit_pct >= self.trail_activation_pct:
                print(f"Price moved {profit_pct*100:.2f}% in favor. Moving SL to Breakeven ({self.entry_price}).")
                self.sl_price = self.entry_price
                self.breakeven_activated = True

                if not paper_trading:
                    # Cancel existing SL and place new one at entry
                    self.exchange.cancel_all_orders(self.symbol)
                    sl_side = 'SELL' if self.position_side == 'BUY' else 'BUY'
                    self.exchange.place_stop_market_order(self.symbol, sl_side, self.sl_price, close_position=True)

    def _close_position(self, reason, paper_trading=True):
        print(f"--- CLOSING POSITION: {reason} ---")
        if not paper_trading:
            close_side = 'SELL' if self.position_side == 'BUY' else 'BUY'
            self.exchange.place_market_order(self.symbol, close_side, self.quantity)
            self.exchange.cancel_all_orders(self.symbol)

        self.in_position = False
        self.position_side = None
