import time
from collections import deque
from typing import Dict, Optional
import logging
from sortedcontainers import SortedDict

import config

logger = logging.getLogger(__name__)


class OrderFlowAnalyzer:
    """
    UPGRADED Order Flow Analyzer with professional-grade detection
    
    IMPROVEMENTS:
    - Proper order book management with snapshot support
    - Trade-confirmed sweep detection
    - Volume/depth ratio absorption
    - Adaptive delta calculation
    - Market regime awareness
    """
    
    def __init__(self):
        # Order book tracking (properly synced)
        self.order_book = SortedDict()
        self.previous_book = SortedDict()
        self.book_snapshot_time = 0
        self.is_snapshot_loaded = False
        
        # Trade tracking
        self.trades = deque(maxlen=10000)
        self.buy_volume = deque()
        self.sell_volume = deque()
        
        # Metrics
        self.current_price = 0
        self.previous_price = 0
        self.last_update = time.time()
        
        # Improved detection components
        self.recent_trades_for_sweep = deque(maxlen=100)
        
        # Price history for volatility
        self.price_history = deque(maxlen=100)
        self.price_changes = deque(maxlen=100)
        self.atr = None
        
        # Adaptive delta parameters
        self.base_delta_window = config.DELTA_WINDOW_SECONDS
        self.current_delta_window = config.DELTA_WINDOW_SECONDS
        
        # Market regime tracking
        self.volatility_state = 'unknown'
        self.trend_state = 'unknown'
        
        logger.info("Order Flow Analyzer initialized (UPGRADED)")
        
    def update_orderbook(self, data: Dict):
        """
        Update order book with proper snapshot/update handling
        
        CRITICAL: Handles both snapshots and incremental updates
        """
        is_snapshot = data.get('is_snapshot', False)
        
        if is_snapshot:
            # This is a REST snapshot - rebuild book
            self.order_book.clear()
            self.is_snapshot_loaded = True
            logger.info("Order book snapshot loaded")
        
        self.previous_book = self.order_book.copy()
        self.book_snapshot_time = time.time()
        
        # Update bids
        for price, size in data['bids']:
            if size == 0:
                self.order_book.pop(price, None)
            else:
                if price not in self.order_book:
                    self.order_book[price] = {'bid': size, 'ask': 0}
                else:
                    self.order_book[price]['bid'] = size
        
        # Update asks
        for price, size in data['asks']:
            if size == 0:
                self.order_book.pop(price, None)
            else:
                if price not in self.order_book:
                    self.order_book[price] = {'bid': 0, 'ask': size}
                else:
                    self.order_book[price]['ask'] = size
        
        # Keep only reasonable number of levels
        if len(self.order_book) > config.MAX_ORDERBOOK_LEVELS * 2:
            mid_price = self.get_mid_price()
            if mid_price:
                keys_to_remove = [k for k in self.order_book.keys() 
                                if abs(k - mid_price) > mid_price * 0.01]
                for k in keys_to_remove:
                    self.order_book.pop(k)
    
    def add_trade(self, trade: Dict):
        """Add trade and update all metrics"""
        self.trades.append(trade)
        self.recent_trades_for_sweep.append(trade)
        
        self.previous_price = self.current_price
        self.current_price = trade['price']
        
        # Track price changes for volatility
        if self.price_history:
            prev_price = self.price_history[-1]
            price_change_pct = abs(self.current_price - prev_price) / prev_price
            self.price_changes.append(price_change_pct)
        
        self.price_history.append(self.current_price)
        
        # Update ATR
        if len(self.price_changes) >= 20:
            import statistics
            self.atr = statistics.mean(self.price_changes)
            
            # Adjust delta window based on volatility
            if self.atr:
                vol_factor = 0.0001 / max(self.atr, 0.00001)
                self.current_delta_window = self.base_delta_window * max(0.6, min(vol_factor, 2.0))
        
        # Add to volume tracking with timestamp
        timestamp = time.time()
        if trade['side'] == 'buy':
            self.buy_volume.append((timestamp, trade['size']))
        else:
            self.sell_volume.append((timestamp, trade['size']))
        
        # Clean old trades
        self._clean_old_data()
        
        # Update market regime
        self._update_regime()
    
    def _clean_old_data(self):
        """Remove data older than configured window"""
        current_time = time.time()
        cutoff_time = current_time - config.TRADE_HISTORY_SECONDS
        
        # Clean trades
        while self.trades and self.trades[0]['timestamp'] / 1000 < cutoff_time:
            self.trades.popleft()
        
        # Clean volume data (use adaptive window)
        delta_cutoff = current_time - self.current_delta_window
        while self.buy_volume and self.buy_volume[0][0] < delta_cutoff:
            self.buy_volume.popleft()
        while self.sell_volume and self.sell_volume[0][0] < delta_cutoff:
            self.sell_volume.popleft()
    
    def _update_regime(self):
        """Update market regime classification"""
        if self.atr:
            # Classify volatility
            if self.atr < 0.0001:
                self.volatility_state = 'calm'
            elif self.atr < 0.0003:
                self.volatility_state = 'normal'
            elif self.atr < 0.0007:
                self.volatility_state = 'volatile'
            else:
                self.volatility_state = 'extreme'
    
    def get_mid_price(self) -> Optional[float]:
        """Get current mid price from order book"""
        if not self.order_book:
            return self.current_price
        
        best_bid = max((p for p, v in self.order_book.items() if v['bid'] > 0), default=0)
        best_ask = min((p for p, v in self.order_book.items() if v['ask'] > 0), default=float('inf'))
        
        if best_bid > 0 and best_ask < float('inf'):
            return (best_bid + best_ask) / 2
        return self.current_price
    
    def calculate_delta(self) -> Dict:
        """
        Calculate delta with adaptive window and normalization
        
        IMPROVEMENT: Window adapts to volatility
        """
        buy_vol = sum(size for _, size in self.buy_volume)
        sell_vol = sum(size for _, size in self.sell_volume)
        raw_delta = buy_vol - sell_vol
        
        # Normalize by volatility if available
        normalized_delta = raw_delta
        if self.atr and self.atr > 0:
            expected_movement = abs(raw_delta) * self.atr
            normalized_delta = raw_delta / (1 + expected_movement)
        
        return {
            'buy_volume': buy_vol,
            'sell_volume': sell_vol,
            'delta': raw_delta,
            'normalized_delta': normalized_delta,
            'delta_ratio': buy_vol / sell_vol if sell_vol > 0 else 0,
            'window_seconds': self.current_delta_window
        }
    
    def detect_liquidity_sweep(self) -> Optional[Dict]:
        """
        IMPROVED liquidity sweep detection with trade confirmation
        
        CRITICAL IMPROVEMENTS:
        - Groups price-adjacent levels
        - Requires minimum notional ($50k default)
        - Confirms with actual trades in zone
        """
        if not self.previous_book or not self.order_book or not self.is_snapshot_loaded:
            return None
        
        current_time = time.time()
        time_diff_ms = (current_time - self.book_snapshot_time) * 1000
        
        if time_diff_ms > config.LIQUIDITY_SWEEP_TIME_MS:
            return None
        
        # Check for removed bid levels (sweep down)
        removed_bids = []
        for price, data in self.previous_book.items():
            if price not in self.order_book or self.order_book[price]['bid'] == 0:
                if data['bid'] > 0:
                    removed_bids.append((price, data['bid']))
        
        # Check for removed ask levels (sweep up)
        removed_asks = []
        for price, data in self.previous_book.items():
            if price not in self.order_book or self.order_book[price]['ask'] == 0:
                if data['ask'] > 0:
                    removed_asks.append((price, data['ask']))
        
        # Process bid sweeps
        if len(removed_bids) >= config.LIQUIDITY_SWEEP_MIN_LEVELS:
            sweep = self._process_sweep(removed_bids, 'down', time_diff_ms)
            if sweep:
                return sweep
        
        # Process ask sweeps
        if len(removed_asks) >= config.LIQUIDITY_SWEEP_MIN_LEVELS:
            sweep = self._process_sweep(removed_asks, 'up', time_diff_ms)
            if sweep:
                return sweep
        
        return None
    
    def _process_sweep(self, removed_levels: list, direction: str, time_ms: float) -> Optional[Dict]:
        """
        Process potential sweep with trade confirmation
        
        CRITICAL: Confirms sweep with actual market trades
        """
        if not removed_levels:
            return None
        
        # Sort by price
        removed_levels.sort(key=lambda x: x[0])
        
        # Check for price adjacency
        adjacent_group = self._find_largest_adjacent_group(removed_levels)
        
        if len(adjacent_group) < config.LIQUIDITY_SWEEP_MIN_LEVELS:
            return None  # Scattered removals, not a sweep
        
        # Calculate notional
        notional = sum(price * qty for price, qty in adjacent_group)
        
        # Use config value if available, otherwise default
        min_notional = getattr(config, 'MIN_SWEEP_NOTIONAL', 50000)
        
        if notional < min_notional:
            return None  # Too small
        
        # Get sweep zone
        sweep_prices = [price for price, _ in adjacent_group]
        zone_min = min(sweep_prices)
        zone_max = max(sweep_prices)
        
        # Confirm with trades (CRITICAL)
        trade_confirmed = self._confirm_sweep_with_trades(zone_min, zone_max, direction)
        
        if not trade_confirmed:
            return None  # No trades in zone = false positive
        
        return {
            'direction': direction,
            'levels_removed': len(adjacent_group),
            'notional': notional,
            'prices': sweep_prices,
            'time_ms': time_ms,
            'trade_confirmed': True
        }
    
    def _find_largest_adjacent_group(self, levels: list) -> list:
        """Find largest group of price-adjacent levels"""
        if not levels:
            return []
        
        sorted_levels = sorted(levels, key=lambda x: x[0])
        
        if len(sorted_levels) < 2:
            return sorted_levels
        
        # Calculate typical tick
        distances = [abs(sorted_levels[i+1][0] - sorted_levels[i][0]) 
                    for i in range(len(sorted_levels) - 1)]
        
        if not distances:
            return sorted_levels
        
        median_dist = sorted(distances)[len(distances) // 2]
        adjacency_threshold = median_dist * 2
        
        # Group adjacent levels
        groups = []
        current_group = [sorted_levels[0]]
        
        for i in range(1, len(sorted_levels)):
            dist = abs(sorted_levels[i][0] - sorted_levels[i-1][0])
            
            if dist <= adjacency_threshold:
                current_group.append(sorted_levels[i])
            else:
                if len(current_group) >= config.LIQUIDITY_SWEEP_MIN_LEVELS:
                    groups.append(current_group)
                current_group = [sorted_levels[i]]
        
        if len(current_group) >= config.LIQUIDITY_SWEEP_MIN_LEVELS:
            groups.append(current_group)
        
        # Return largest group
        return max(groups, key=len) if groups else []
    
    def _confirm_sweep_with_trades(self, price_min: float, price_max: float, direction: str) -> bool:
        """
        Confirm sweep with actual market trades
        
        CRITICAL: Real sweep = aggressive trades in that zone
        """
        current_time = time.time()
        lookback = current_time - 2  # 2 second window
        
        # Filter trades in sweep zone
        relevant_trades = [
            t for t in self.recent_trades_for_sweep
            if lookback <= t['timestamp'] / 1000 <= current_time
            and price_min <= t['price'] <= price_max
        ]
        
        if not relevant_trades:
            return False  # No trades = not a real sweep
        
        # Check if trades match expected side
        expected_side = 'sell' if direction == 'down' else 'buy'
        matching_trades = [t for t in relevant_trades if t['side'] == expected_side]
        
        # Need significant volume
        if not matching_trades:
            return False
        
        trade_notional = sum(t['price'] * t['size'] for t in matching_trades)
        
        # Use config value if available, otherwise default
        min_confirm = getattr(config, 'MIN_TRADE_CONFIRM_NOTIONAL', 25000)
        
        return trade_notional >= min_confirm
    
    def detect_absorption(self) -> Optional[Dict]:
        """
        IMPROVED absorption detection with volume/depth ratio
        
        CRITICAL IMPROVEMENT:
        - Compares trade volume to available depth
        - Requires 2:1 ratio minimum
        - Volatility-adjusted thresholds
        """
        if len(self.trades) < 10:
            return None
        
        current_time = time.time()
        window = 10  # 10 second window
        recent_trades = [t for t in self.trades 
                        if t['timestamp'] / 1000 > current_time - window]
        
        if not recent_trades:
            return None
        
        # Calculate volume and price movement
        total_volume = sum(t['size'] for t in recent_trades)
        prices = [t['price'] for t in recent_trades]
        price_range_pct = (max(prices) - min(prices)) / min(prices)
        
        # Adjust threshold by volatility
        max_movement = config.PRICE_MOVEMENT_THRESHOLD
        if self.atr:
            vol_multiplier = min(self.atr / 0.0001, 3.0)
            max_movement = config.PRICE_MOVEMENT_THRESHOLD * vol_multiplier
        
        if price_range_pct > max_movement:
            return None  # Too much movement
        
        # Check volume vs depth ratio
        buy_vol = sum(t['size'] for t in recent_trades if t['side'] == 'buy')
        sell_vol = sum(t['size'] for t in recent_trades if t['side'] == 'sell')
        
        absorbing_side = 'ask' if buy_vol > sell_vol else 'bid'
        aggressive_vol = max(buy_vol, sell_vol)
        
        # Get available depth
        available_depth = self._get_depth_at_side(absorbing_side, 10)
        
        if available_depth == 0:
            return None
        
        volume_to_depth_ratio = aggressive_vol / available_depth
        
        # Use config value if available, otherwise default
        min_ratio = getattr(config, 'MIN_ABSORPTION_RATIO', 2.0)
        
        if volume_to_depth_ratio < min_ratio:
            return None  # Volume not large enough relative to depth
        
        # Valid absorption
        return {
            'volume': total_volume,
            'price_change_pct': price_range_pct,
            'absorbing_side': absorbing_side,
            'price_level': sum(prices) / len(prices),
            'volume_to_depth_ratio': volume_to_depth_ratio
        }
    
    def _get_depth_at_side(self, side: str, num_levels: int) -> float:
        """Get total depth on one side"""
        if side == 'bid':
            if not self.order_book:
                return 0.0
            levels = [(p, v['bid']) for p, v in self.order_book.items() if v['bid'] > 0]
            top_levels = sorted(levels, key=lambda x: x[0])[-num_levels:]
            return sum(qty for _, qty in top_levels)
        else:
            if not self.order_book:
                return 0.0
            levels = [(p, v['ask']) for p, v in self.order_book.items() if v['ask'] > 0]
            top_levels = sorted(levels, key=lambda x: x[0])[:num_levels]
            return sum(qty for _, qty in top_levels)
    
    def get_market_state(self) -> Dict:
        """Get comprehensive market state with regime info"""
        delta_info = self.calculate_delta()
        liquidity_sweep = self.detect_liquidity_sweep()
        absorption = self.detect_absorption()
        mid_price = self.get_mid_price()
        
        return {
            'timestamp': time.time(),
            'price': self.current_price,
            'mid_price': mid_price,
            'delta': delta_info,
            'liquidity_sweep': liquidity_sweep,
            'absorption': absorption,
            'total_trades': len(self.trades),
            'volatility_state': self.volatility_state,
            'atr': self.atr,
            'is_synced': self.is_snapshot_loaded
        }
