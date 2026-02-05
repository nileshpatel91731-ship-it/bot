# Configuration for ETH Order Flow Bot - ULTRA RELAXED
# Use this when market is VERY CALM (like now)

# Exchange Settings
SYMBOL = "ETHUSDT"
EXCHANGE = "Binance"

# WebSocket URLs
BINANCE_ORDERBOOK_WS = "wss://stream.binance.com:9443/ws/ethusdt@depth@100ms"
BINANCE_TRADES_WS = "wss://stream.binance.com:9443/ws/ethusdt@trade"

# Order Flow Parameters - ULTRA RELAXED
DELTA_WINDOW_SECONDS = 5  # Rolling window for buy/sell volume calculation
ABSORPTION_THRESHOLD = 20  # VERY LOW - from 100 (easier to trigger)
PRICE_MOVEMENT_THRESHOLD = 0.0005  # HIGHER - from 0.0001 (allows more movement)
LIQUIDITY_SWEEP_MIN_LEVELS = 1  # MINIMUM - from 3 (any level removal counts)
LIQUIDITY_SWEEP_TIME_MS = 1000  # LONGER - from 200 (more time for sweeps)

# Signal Parameters - ULTRA RELAXED
COOLDOWN_SECONDS = 5  # VERY SHORT - from 30 (more frequent signals)
MIN_DELTA_FLIP = 10  # VERY LOW - from 50 (easier to flip)

# Output Settings
LOG_LEVEL = "INFO"
ENABLE_CONSOLE_OUTPUT = True
SAVE_TO_CSV = False
CSV_FILENAME = "eth_signals.csv"

# Display Mode
QUIET_MODE = False
SILENT_MODE = True

# Data Management
MAX_ORDERBOOK_LEVELS = 50
TRADE_HISTORY_SECONDS = 60

# ULTRA RELAXED THRESHOLDS
MIN_SWEEP_NOTIONAL = 5000  # VERY LOW - $5k instead of $50k
MIN_ABSORPTION_RATIO = 1.0  # MINIMUM - 1:1 instead of 2:1
MIN_TRADE_CONFIRM_NOTIONAL = 1000  # VERY LOW - $1k instead of $25k

# NOTE: These settings will generate MORE signals (including some false ones)
# But at least you'll see the bot working
# Tune UP from here once you see signals
