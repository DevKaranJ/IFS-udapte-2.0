import time
import math

class RiskManager:
    def __init__(self, exchange_interface, config):
        self.exchange = exchange_interface
        self.config = config

        self.symbol = self.config.get('symbol', 'BTCUSDT')
        self.risk_percent = self.config.get('risk_percent', 1.0) / 100.0

        # Determine if altcoin
        is_altcoin = self.symbol not in ['BTCUSDT', 'ETHUSDT']

        if is_altcoin:
            self.sl_pct = self.config.get('altcoin_stop_loss_percent', 1.0) / 100.0
            # "Reduce position size by 50% (risk 0.5% instead of 1%)"
            self.risk_percent = self.risk_percent * 0.5
        else:
            self.sl_pct = self.config.get('stop_loss_percent', 0.5) / 100.0

        self.trail_activation_pct = self.config.get('trail_activation', 1.5) / 100.0
        self.invalidation_seconds = self.config.get('invalidation_seconds', 60)

        self.in_position = False
        self.position_side = None
        self.entry_price = 0.0
        self.entry_time = 0.0
        self.quantity = 0.0

        self.sl_price = 0.0
        self.tp1_hit = False
        self.breakeven_activated = False

    def calculate_position_size(self, account_balance, entry_price):
        risk_amount = account_balance * self.risk_percent
        risk_per_unit = entry_price * self.sl_pct

        if risk_per_unit == 0:
            return 0.0

        qty = risk_amount / risk_per_unit

        # Format based on symbol. BTC needs 3 decimals usually
        if 'BTC' in self.symbol:
            return math.floor(qty * 1000) / 1000.0
        elif 'ETH' in self.symbol:
            return math.floor(qty * 100) / 100.0
        else:
            return math.floor(qty)

    def execute_trade(self, signal, current_price, account_balance, paper_trading=True):
        if self.in_position:
            return False

        self.entry_price = current_price
        self.position_side = signal
        self.quantity = self.calculate_position_size(account_balance, self.entry_price)

        if self.quantity <= 0:
            return False

        if signal == 'BUY':
            self.sl_price = self.entry_price * (1 - self.sl_pct)
        else:
            self.sl_price = self.entry_price * (1 + self.sl_pct)

        self.entry_time = time.time()
        self.breakeven_activated = False
        self.tp1_hit = False
        self.in_position = True

        print(f"--- EXECUTING {signal} ---")
        print(f"Entry: {self.entry_price}")
        print(f"Size: {self.quantity}")
        print(f"Initial SL: {self.sl_price}")

        if not paper_trading:
            order_side = 'BUY' if signal == 'BUY' else 'SELL'
            self.exchange.place_market_order(self.symbol, order_side, self.quantity)

            sl_side = 'SELL' if signal == 'BUY' else 'BUY'
            self.exchange.place_stop_market_order(self.symbol, sl_side, self.sl_price, close_position=True)

        return True

    def update(self, current_price, paper_trading=True):
        if not self.in_position:
            return

        time_in_trade = time.time() - self.entry_time

        # 1. 60-second invalidation
        if time_in_trade <= self.invalidation_seconds:
            if self.position_side == 'BUY' and current_price < self.entry_price:
                self._close_position("60-second Invalidation (Price reversed)", paper_trading)
                return
            elif self.position_side == 'SELL' and current_price > self.entry_price:
                self._close_position("60-second Invalidation (Price reversed)", paper_trading)
                return

        # 2. Hard Stop Loss
        if self.position_side == 'BUY' and current_price <= self.sl_price:
            self._close_position("Stop Loss Hit.", paper_trading)
            return
        elif self.position_side == 'SELL' and current_price >= self.sl_price:
            self._close_position("Stop Loss Hit.", paper_trading)
            return

        # Profit Calculation
        profit_pct = 0.0
        if self.position_side == 'BUY':
            profit_pct = (current_price - self.entry_price) / self.entry_price
        else:
            profit_pct = (self.entry_price - current_price) / self.entry_price

        # 3. Take Profit 1 (1.5x risk)
        # Risk is self.sl_pct. 1.5x risk is self.sl_pct * 1.5
        tp1_pct = self.sl_pct * 1.5
        if not self.tp1_hit and profit_pct >= tp1_pct:
            print(f"TP1 Hit ({tp1_pct*100:.2f}%). Closing 50% of position.")
            self.tp1_hit = True

            half_qty = self.quantity / 2.0
            if 'BTC' in self.symbol: half_qty = math.floor(half_qty * 1000) / 1000.0
            elif 'ETH' in self.symbol: half_qty = math.floor(half_qty * 100) / 100.0
            else: half_qty = math.floor(half_qty)

            self.quantity -= half_qty

            if not paper_trading and half_qty > 0:
                close_side = 'SELL' if self.position_side == 'BUY' else 'BUY'
                self.exchange.place_market_order(self.symbol, close_side, half_qty, reduce_only=True)

        # 4. Trailing Stop to Breakeven
        if not self.breakeven_activated and profit_pct >= self.trail_activation_pct:
            print(f"Price moved {profit_pct*100:.2f}% in favor. Moving SL to Breakeven ({self.entry_price}).")
            self.sl_price = self.entry_price
            self.breakeven_activated = True

            if not paper_trading:
                self.exchange.cancel_all_orders(self.symbol)
                sl_side = 'SELL' if self.position_side == 'BUY' else 'BUY'
                self.exchange.place_stop_market_order(self.symbol, sl_side, self.sl_price, close_position=True)

    def close_all(self, reason, paper_trading=True):
        if self.in_position:
            self._close_position(reason, paper_trading)

    def _close_position(self, reason, paper_trading=True):
        print(f"--- CLOSING POSITION: {reason} ---")
        if not paper_trading and self.quantity > 0:
            close_side = 'SELL' if self.position_side == 'BUY' else 'BUY'
            self.exchange.place_market_order(self.symbol, close_side, self.quantity, reduce_only=True)
            self.exchange.cancel_all_orders(self.symbol)

        self.in_position = False
        self.position_side = None
        self.quantity = 0.0
