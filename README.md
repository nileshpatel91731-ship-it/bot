# ETH Order Flow Bot - Phase 1

A sophisticated order flow analysis bot for ETH/USDT that detects liquidity sweeps, absorption patterns, and generates trading signals based on real-time market microstructure.

## 🎯 What This Bot Does

This bot connects to Binance WebSocket feeds and analyzes:

- **Liquidity Sweeps** - Detects when multiple price levels are rapidly removed (stop hunts)
- **Order Flow Delta** - Tracks aggressive buy vs sell volume in real-time
- **Absorption** - Identifies when large orders are filled without price movement
- **Signal Generation** - Generates BUY/SELL signals based on combined patterns

### Signal Logic

**🟢 BUY Signal Pattern:**
1. Sell-side liquidity sweep below price (stop hunt down)
2. Strong negative delta → flips positive (sellers exhausted, buyers step in)
3. Absorption detected (orders being absorbed)
4. Price reclaims swept level (reversal confirmation)

**🔴 SELL Signal Pattern:**
1. Buy-side liquidity sweep above price (stop hunt up)
2. Strong positive delta → flips negative (buyers exhausted, sellers step in)
3. Absorption at highs
4. Price reclaims swept level

## 📋 Requirements

- Python 3.8+
- Internet connection
- Terminal with color support (for best visualization)

## 🚀 Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

Or install individually:
```bash
pip install websockets sortedcontainers colorama
```

### 2. Run the Bot

```bash
python main.py
```

Or make it executable:
```bash
chmod +x main.py
./main.py
```

### 3. Stop the Bot

Press `Ctrl+C` to gracefully stop the bot and see statistics.

## 📊 Output Examples

### Normal Operation
```
[12:34:56] Price: 2315.45 | Δ: 12.34 ↑ (B: 45.2 / S: 32.9)
```

### Liquidity Sweep Detected
```
[SWEEP ⬇️] 5 levels | 150ms
```

### Absorption Detected
```
[ABSORPTION] Vol: 125.50 | Side: bid
```

### BUY Signal Generated
```
============================================================
🟢 BUY SIGNAL 🟢
[12:35:10] ETH @ 2312.30
Confidence: 90%
Reasons: sweep ↓ (5 levels) | delta flip ↑ | absorption confirmed
Delta: 15.67
============================================================
```

## ⚙️ Configuration

Edit `config.py` to customize parameters:

### Key Parameters

```python
# Delta calculation window
DELTA_WINDOW_SECONDS = 5  # Rolling window for buy/sell volume

# Absorption detection
ABSORPTION_THRESHOLD = 100  # Minimum volume to detect
PRICE_MOVEMENT_THRESHOLD = 0.0001  # Max price movement for absorption

# Liquidity sweep detection
LIQUIDITY_SWEEP_MIN_LEVELS = 3  # Minimum levels removed
LIQUIDITY_SWEEP_TIME_MS = 200  # Max time window for sweep

# Signal generation
COOLDOWN_SECONDS = 30  # Minimum time between signals
MIN_DELTA_FLIP = 50  # Minimum delta change to confirm flip
```

## 📁 Project Structure

```
eth-orderflow-bot/
│
├── main.py                    # Main bot orchestrator
├── config.py                  # Configuration parameters
├── binance_connector.py       # WebSocket connection handler
├── order_flow_analyzer.py     # Core order flow analysis logic
├── signal_generator.py        # Signal generation engine
├── requirements.txt           # Python dependencies
└── README.md                 # This file
```

## 🔍 How It Works

### 1. Data Collection
- Connects to Binance WebSocket feeds for ETH/USDT
- Subscribes to order book updates (depth@100ms)
- Subscribes to real-time trades (trade stream)

### 2. Order Book Tracking
- Maintains a sorted order book with bid/ask levels
- Tracks liquidity changes across price levels
- Detects when levels are added or removed

### 3. Trade Analysis
- Classifies trades as aggressive buy or sell
- Calculates rolling delta (buy volume - sell volume)
- Tracks volume and price movement correlation

### 4. Pattern Detection

**Liquidity Sweep:**
- Monitors for rapid removal of multiple price levels
- Confirms with time threshold (must happen quickly)
- Tracks direction (up or down)

**Absorption:**
- Large volume traded with minimal price movement
- Indicates strong support/resistance
- Often precedes reversals

**Delta Flip:**
- Sudden change in order flow direction
- From negative (selling) to positive (buying) or vice versa
- Indicates momentum shift

### 5. Signal Generation
- Combines multiple confirmations
- Calculates confidence score (70%+ required)
- Enforces cooldown period between signals
- Prints detailed signal information

## 📈 Understanding the Output

### Real-time Price Display
```
[12:34:56] Price: 2315.45 | Δ: 12.34 ↑ (B: 45.2 / S: 32.9)
```
- **Price**: Current trade price
- **Δ**: Delta (positive = more buying, negative = more selling)
- **↑/↓**: Delta direction
- **B**: Buy volume (last 5 seconds)
- **S**: Sell volume (last 5 seconds)

### Status Updates
```
[STATUS] Uptime: 120s | OB Updates: 500 | Trades: 450 | Delta: 12.34
```
- Shows bot health and activity
- Updates every 100 order book updates

### Final Statistics
When you stop the bot:
```
============================================================
FINAL STATISTICS
============================================================
Runtime: 300s
Order Book Updates: 1500
Trades Processed: 1200
Total Signals: 3
  • BUY Signals: 2
  • SELL Signals: 1
  • Avg Confidence: 85.0%
============================================================
```

## ⚠️ Important Notes

### This is Phase 1
- **Binance only** (not multi-exchange yet)
- **Console output** (no CSV or webhooks yet)
- **Real-time only** (no backtesting yet)
- **No execution** (signals only)

### Limitations
- Public WebSocket feeds have latency (~50-200ms)
- Not suitable for high-frequency trading
- Works best for scalping and intraday timeframes
- May have false signals in choppy markets

### Risk Warnings
- **This is NOT financial advice**
- Signals are for informational purposes only
- Always do your own research
- Never trade with money you can't afford to lose
- Past performance does not guarantee future results

## 🔧 Troubleshooting

### Connection Issues
If the bot can't connect:
```bash
# Check your internet connection
ping binance.com

# Try running with debug logging
# In config.py, change:
LOG_LEVEL = "DEBUG"
```

### No Signals Generated
This is normal! Signals require specific conditions:
- Liquidity sweep must occur
- Delta must flip
- Absorption often needed
- All within a short time window

The bot is designed to be conservative and only signal high-probability setups.

### Performance Issues
If the bot is slow:
- Reduce `MAX_ORDERBOOK_LEVELS` in config.py
- Increase `DELTA_WINDOW_SECONDS` for less frequent updates
- Close other resource-intensive applications

## 🚀 Next Phases (Roadmap)

### Phase 2
- [ ] Add Bybit and OKX exchanges
- [ ] Implement global aggregated order book
- [ ] Enhanced multi-exchange liquidity detection

### Phase 3
- [ ] CSV logging for backtesting
- [ ] Performance metrics and statistics
- [ ] Configurable alert system

### Phase 4
- [ ] Strategy backtesting framework
- [ ] Optional execution integration
- [ ] Web dashboard for monitoring

## 📚 Learn More

### Order Flow Trading
- Order flow reveals the "why" behind price movement
- Liquidity sweeps = stop hunts = potential reversals
- Absorption = smart money positioning
- Delta = real-time sentiment indicator

### Resources
- [Binance WebSocket API](https://binance-docs.github.io/apidocs/spot/en/#websocket-market-streams)
- [OrderFlow Fundamentals](https://www.investopedia.com/terms/o/order-flow.asp)

## 🤝 Contributing

This is Phase 1 - the foundation. Contributions welcome:
- Bug fixes
- Performance improvements
- Documentation enhancements

## 📝 License

Use at your own risk. Educational purposes only.

## 💬 Feedback

Found a bug? Have suggestions? Open an issue!

---

**Happy Trading! 🚀**

*Remember: The best signal is the one you understand.*
