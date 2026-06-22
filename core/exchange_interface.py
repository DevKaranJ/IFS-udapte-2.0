import os
import pandas as pd
from binance.client import Client
from binance.enums import *
from dotenv import load_dotenv

class ExchangeInterface:
    def __init__(self, use_testnet=True):
        load_dotenv()
        api_key = os.getenv('BINANCE_API_KEY')
        api_secret = os.getenv('BINANCE_API_SECRET')

        self.client = Client(api_key, api_secret, testnet=use_testnet)

        if use_testnet:
            self.client.FUTURES_URL = 'https://testnet.binancefuture.com/fapi'

    def get_account_balance(self, asset='USDT'):
        try:
            account = self.client.futures_account()
            for asset_balance in account['assets']:
                if asset_balance['asset'] == asset:
                    return float(asset_balance['availableBalance'])
            return 0.0
        except Exception as e:
            print(f"Error getting balance: {e}")
            return 0.0

    def set_leverage(self, symbol, leverage):
        try:
            self.client.futures_change_leverage(symbol=symbol, leverage=leverage)
            print(f"Leverage set to {leverage}x for {symbol}")
        except Exception as e:
            print(f"Error setting leverage: {e}")

    def place_market_order(self, symbol, side, quantity, reduce_only=False):
        try:
            params = {
                'symbol': symbol,
                'side': side,
                'type': ORDER_TYPE_MARKET,
                'quantity': quantity
            }
            if reduce_only:
                params['reduceOnly'] = 'true'

            order = self.client.futures_create_order(**params)
            print(f"Market order placed: {side} {quantity} {symbol}")
            return order
        except Exception as e:
            print(f"Error placing market order: {e}")
            return None

    def place_stop_market_order(self, symbol, side, stop_price, quantity=None, close_position=False):
        try:
            params = {
                'symbol': symbol,
                'side': side,
                'type': ORDER_TYPE_STOP_MARKET,
                'stopPrice': stop_price
            }
            if close_position:
                params['closePosition'] = 'true'
            else:
                params['quantity'] = quantity

            order = self.client.futures_create_order(**params)
            print(f"Stop market order placed: {side} {symbol} @ {stop_price}")
            return order
        except Exception as e:
            print(f"Error placing stop order: {e}")
            return None

    def cancel_all_orders(self, symbol):
        try:
            self.client.futures_cancel_all_open_orders(symbol=symbol)
            print(f"Cancelled all open orders for {symbol}")
        except Exception as e:
            print(f"Error cancelling orders: {e}")

    def get_current_price(self, symbol):
        try:
            ticker = self.client.futures_symbol_ticker(symbol=symbol)
            return float(ticker['price'])
        except Exception as e:
            print(f"Error getting price: {e}")
            return None

    def get_historical_klines(self, symbol, interval, limit=24):
        try:
            klines = self.client.futures_klines(symbol=symbol, interval=interval, limit=limit)
            df = pd.DataFrame(klines, columns=[
                'timestamp', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_asset_volume', 'number_of_trades',
                'taker_buy_base_asset_volume', 'taker_buy_quote_asset_volume', 'ignore'
            ])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = df[col].astype(float)
            return df
        except Exception as e:
            print(f"Error fetching klines: {e}")
            return None
