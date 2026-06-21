# Python Trading Bot (Institutional Footprint Strategy)

A standalone, modular Python trading bot connecting to Binance Futures Testnet. It implements an orderbook and trade streamer to calculate real-time cumulative volume delta (CVD), detect block orders, and find stacked imbalances to execute trades.

## Structure
- `core/`: Core infrastructure (exchange interface, websocket streamer, risk manager, backtester).
- `strategies/strategy_1_IFS/`: The Institutional Footprint Strategy logic and configuration.
- `data/`: Sample CSV data for backtesting.
- `main.py`: The live bot orchestrator.

## Installation
```bash
pip install -r requirements.txt
```

## Configuration
1. Edit `.env` and add your Binance Testnet API Keys:
   ```
   BINANCE_API_KEY=your_testnet_api_key_here
   BINANCE_API_SECRET=your_testnet_api_secret_here
   ```
2. Edit `strategies/strategy_1_IFS/config.json` to adjust leverage, risk percentage, and symbols.

## Running the Live Bot
```bash
PYTHONPATH=. python3 main.py
```
*(Note: `main.py` is configured with `PAPER_TRADING = True` by default to prevent real orders from being sent. Change it to `False` when ready).*

## Running the Backtest Engine
To run the strategy logic against historical data without connecting to the exchange:
```bash
PYTHONPATH=. python3 core/backtest_engine.py
```
