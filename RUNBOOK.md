# Python Trading Bot - Runbook

Follow this step-by-step guide to configure, test, and run your Institutional Footprint Strategy (IFS) trading bot on the Binance Futures Testnet.

## 1. Prerequisites
- **Python Version:** Ensure you have Python 3.9+ installed.
- **Binance Testnet Account:** You need an active Binance Futures Testnet account.
- **.env File Setup:** In the root directory of the project, ensure you have a `.env` file with your exact Testnet API credentials.

  Format for `.env`:
  ```
  BINANCE_API_KEY=your_testnet_api_key_here
  BINANCE_API_SECRET=your_testnet_api_secret_here
  ```

## 2. Installation
Open your terminal in the project's root directory and install the required dependencies:
```bash
pip install -r requirements.txt
```

## 3. Configuration Checks
Before running, verify the following files:

1. **`strategies/strategy_1_IFS/config.json`**
   Ensure your risk parameters are correct:
   ```json
   {
       "leverage": 3,
       "risk_percent": 1.0,
       "trail_activation": 1.5,
       "symbol": "BTCUSDT",
       "sl_pct": 0.5
   }
   ```
2. **`main.py`**
   Verify the `PAPER_TRADING` flag at the top of the file. It must be `True` to prevent the bot from executing real API orders while you test:
   ```python
   PAPER_TRADING = True
   ```

## 4. Running the Backtest
Before going live, validate the logic on historical data.

1. Ensure your historical data CSV is located at `data/btc_orderbook_sample.csv`.
2. Run the backtest engine from the root directory:
   ```bash
   PYTHONPATH=. python3 core/backtest_engine.py
   ```
3. Review the console output to see the simulated trades and final PnL.

## 5. Running the Live Bot (Paper Trading)
Start the bot to connect to the Binance WebSocket and process live data.

1. Run the main orchestrator from the root directory:
   ```bash
   PYTHONPATH=. python3 main.py
   ```
2. **Verification:**
   - The console will output: `Starting Trading Bot... [PAPER TRADING: True]`.
   - Shortly after, you will see `Started DataStreamer for btcusdt on Testnet` and `WebSocket Connection Opened`.
   - The bot fetches daily k-lines, displaying the Daily High/Low and Fib 0.618 levels.
   - It will say `Waiting for WebSocket data...` and then begin evaluating the strategy silently.

## 6. Monitoring
While the bot is running, monitor its actions:

- **Console Output:** The bot will print `SIGNAL: <BUY/SELL> | REASON: <...>` whenever the 4 filters align. It will also print execution details (`--- EXECUTING BUY ---`, Entry, Size, SL) and trailing/closing events.
- **`trading_log.csv`:** Every executed signal is appended to this file. You can open it in Excel/Sheets to review:
  - `timestamp`: When the action occurred.
  - `action`: BUY or SELL.
  - `symbol`: The traded pair.
  - `price`: Entry price.
  - `quantity`: Calculated position size.
  - `reason`: Why the trade was entered or exited.

## 7. Troubleshooting

- **Error: `WebSocket Connection Closed` or Disconnections**
  - *Fix:* Binance WebSockets disconnect every 24 hours. The bot currently attempts to maintain it, but if it drops, you can restart the bot manually or wrap the `main.py` execution in a bash `while` loop to auto-restart.
- **Error: `APIError(code=0): Service unavailable from a restricted location`**
  - *Fix:* Binance restricts access from certain regions (like the US). You must run the bot from an unrestricted IP or use a VPN/VPS located in an allowed region.
- **Error: `KeyError` on Data Stream**
  - *Fix:* Ensure the symbol in `config.json` is correct (e.g., `BTCUSDT`). Binance requires exact string matches.
- **Error: No Trades Firing**
  - *Fix:* The IFS strategy requires strict alignment of Filter A, B, C, and D. It is highly selective. You can temporarily adjust the thresholds in `strategies/strategy_1_IFS/logic.py` (e.g., increase the 0.05% proximity threshold) to force a trade for testing purposes.
