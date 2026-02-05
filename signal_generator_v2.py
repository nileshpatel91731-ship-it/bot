import time
from typing import Optional, Dict
from collections import deque
import logging

import config

logger = logging.getLogger(__name__)


class SignalGenerator:
    """
    UPGRADED Signal Generator with market regime filtering
    
    CRITICAL IMPROVEMENTS:
    - Filters signals in extreme volatility
    - Filters signals in dead markets (calm vol)
    - Considers market regime before generating signals
    - Higher quality signals, fewer false positives
    """
    
    def __init__(self):
        self.last_signal_time = 0
        self.signal_history = deque(maxlen=100)
        
        # Pattern tracking
        self.recent_sweep = None
        self.sweep_time = 0
        self.previous_delta = 0
        self.delta_history = deque(maxlen=20)
        
        # State tracking
        self.current_state = {
            'sweep_detected': False,
            'absorption_detected': False,
            'delta_flip': False,
            'price_reclaim': False
        }
        
        # Regime filtering stats
        self.signals_generated = 0
        self.signals_filtered = 0
        self.filter_reasons = {}
        
        logger.info("Signal Generator initialized (UPGRADED with regime filtering)")
    
    def update_state(self, market_state: Dict):
        """Update internal state based on market data"""
        current_time = time.time()
        
        # Track liquidity sweep
        if market_state['liquidity_sweep']:
            self.recent_sweep = market_state['liquidity_sweep']
            self.sweep_time = current_time
            self.current_state['sweep_detected'] = True
            
            logger.debug(f"🔍 Liquidity sweep detected: {self.recent_sweep['direction']} "
                        f"({self.recent_sweep['levels_removed']} levels)")
        else:
            # Clear sweep if too old (more than 10 seconds)
            if self.recent_sweep and current_time - self.sweep_time > 10:
                self.recent_sweep = None
                self.current_state['sweep_detected'] = False
        
        # Track absorption
        if market_state['absorption']:
            self.current_state['absorption_detected'] = True
            logger.debug(f"💧 Absorption detected: {market_state['absorption']['volume']:.2f} "
                        f"at {market_state['absorption']['price_level']:.2f}")
        else:
            self.current_state['absorption_detected'] = False
        
        # Track delta flip (use normalized delta)
        current_delta = market_state['delta'].get('normalized_delta', market_state['delta']['delta'])
        self.delta_history.append(current_delta)
        
        if len(self.delta_history) >= 2:
            delta_change = current_delta - self.previous_delta
            
            # Adjust threshold based on volatility
            min_flip = config.MIN_DELTA_FLIP
            if market_state.get('atr'):
                vol_factor = market_state['atr'] / 0.0003
                min_flip = config.MIN_DELTA_FLIP * max(0.5, min(vol_factor, 2.0))
            
            # Detect significant delta flip
            if abs(delta_change) > min_flip:
                if self.previous_delta < -min_flip and current_delta > min_flip:
                    self.current_state['delta_flip'] = 'bullish'
                    logger.debug(f"📈 Delta flip: BULLISH (Δ: {delta_change:.2f})")
                elif self.previous_delta > min_flip and current_delta < -min_flip:
                    self.current_state['delta_flip'] = 'bearish'
                    logger.debug(f"📉 Delta flip: BEARISH (Δ: {delta_change:.2f})")
            else:
                if current_time - self.sweep_time > 5:  # Clear flip after 5 seconds
                    self.current_state['delta_flip'] = False
        
        self.previous_delta = current_delta
        
        # Check price reclaim if we have a sweep
        if self.recent_sweep:
            sweep_prices = self.recent_sweep['prices']
            current_price = market_state['price']
            
            if self.recent_sweep['direction'] == 'down':
                # Check if price reclaimed above sweep
                if sweep_prices and current_price > min(sweep_prices):
                    self.current_state['price_reclaim'] = True
            elif self.recent_sweep['direction'] == 'up':
                # Check if price reclaimed below sweep
                if sweep_prices and current_price < max(sweep_prices):
                    self.current_state['price_reclaim'] = True
    
    def check_regime_filter(self, market_state: Dict, signal_direction: str) -> tuple:
        """
        Check if signal should be filtered based on market regime
        
        CRITICAL: Prevents signals in bad conditions
        
        Returns: (should_filter: bool, reason: str)
        """
        volatility = market_state.get('volatility_state', 'unknown')
        
        # FILTER: Extreme volatility (news events, crashes)
        if volatility == 'extreme':
            self._record_filter('extreme_volatility')
            return True, 'extreme_volatility'
        
        # RELAXED: Allow calm markets (was blocking, now allowing)
        # Calm markets can still produce valid signals
        # if volatility == 'calm':
        #     self._record_filter('calm_market')
        #     return True, 'calm_market'
        
        # FILTER: If not synced yet
        if not market_state.get('is_synced', False):
            self._record_filter('book_not_synced')
            return True, 'book_not_synced'
        
        # Signal approved by regime
        return False, 'regime_approved'
    
    def _record_filter(self, reason: str):
        """Record why signal was filtered"""
        self.signals_filtered += 1
        self.filter_reasons[reason] = self.filter_reasons.get(reason, 0) + 1
    
    def check_buy_signal(self, market_state: Dict) -> Optional[Dict]:
        """
        BUY Signal Pattern:
        PRIMARY: Sweep + Delta flip + Absorption
        ALTERNATIVE (calm markets): Delta flip + Absorption + price support
        """
        # Check cooldown
        if time.time() - self.last_signal_time < config.COOLDOWN_SECONDS:
            return None
        
        # Check regime BEFORE generating signal
        should_filter, reason = self.check_regime_filter(market_state, 'up')
        if should_filter:
            logger.debug(f"BUY signal filtered: {reason}")
            return None
        
        # PRIMARY PATH: With sweep
        if self.recent_sweep and self.recent_sweep['direction'] == 'down':
            if self.current_state['delta_flip'] == 'bullish':
                return self._generate_buy_signal_with_sweep(market_state)
        
        # ALTERNATIVE PATH: Without sweep (for calm markets)
        # Requires: Strong delta flip + Absorption
        if self.current_state['delta_flip'] == 'bullish' and self.current_state['absorption_detected']:
            delta = market_state['delta']['delta']
            # Need strong positive delta (buying pressure)
            if delta > config.MIN_DELTA_FLIP * 2:  # 2x threshold for no-sweep signals
                return self._generate_buy_signal_no_sweep(market_state)
        
        return None
    
    def _generate_buy_signal_with_sweep(self, market_state: Dict) -> Optional[Dict]:
        """Generate BUY signal with sweep confirmation"""
        absorption_confirmed = self.current_state['absorption_detected']
        price_reclaim = self.current_state['price_reclaim']
        
        confidence = 0
        reasons = []
        
        if self.recent_sweep:
            confidence += 30
            reasons.append(f"sweep ↓ ({self.recent_sweep['levels_removed']} levels)")
        
        if self.current_state['delta_flip'] == 'bullish':
            confidence += 40
            reasons.append("delta flip ↑")
        
        if absorption_confirmed:
            confidence += 20
            reasons.append("absorption confirmed")
        
        if price_reclaim:
            confidence += 10
            reasons.append("price reclaim")
        
        if confidence >= 70:
            signal = {
                'type': 'BUY',
                'price': market_state['price'],
                'timestamp': time.time(),
                'confidence': confidence,
                'reasons': reasons,
                'delta': market_state['delta']['delta'],
                'sweep_levels': self.recent_sweep['levels_removed'],
                'volatility': market_state.get('volatility_state', 'unknown')
            }
            
            self.last_signal_time = time.time()
            self.signal_history.append(signal)
            self.signals_generated += 1
            self._reset_state()
            
            return signal
        
        return None
    
    def _generate_buy_signal_no_sweep(self, market_state: Dict) -> Optional[Dict]:
        """Generate BUY signal without sweep (alternative for calm markets)"""
        confidence = 0
        reasons = []
        
        # Strong delta flip required (no sweep to confirm)
        if self.current_state['delta_flip'] == 'bullish':
            confidence += 50
            reasons.append("strong delta flip ↑")
        
        # Absorption provides support
        if self.current_state['absorption_detected']:
            confidence += 30
            reasons.append("absorption support")
        
        # Additional delta strength
        delta = market_state['delta']['delta']
        if delta > config.MIN_DELTA_FLIP * 3:
            confidence += 20
            reasons.append("very strong buying")
        
        # Lower threshold for no-sweep signals (60% vs 70%)
        if confidence >= 60:
            signal = {
                'type': 'BUY',
                'price': market_state['price'],
                'timestamp': time.time(),
                'confidence': confidence,
                'reasons': reasons,
                'delta': market_state['delta']['delta'],
                'sweep_levels': 0,  # No sweep
                'volatility': market_state.get('volatility_state', 'unknown'),
                'pattern': 'no_sweep'  # Flag alternative pattern
            }
            
            self.last_signal_time = time.time()
            self.signal_history.append(signal)
            self.signals_generated += 1
            self._reset_state()
            
            return signal
        
        return None
    
    def check_sell_signal(self, market_state: Dict) -> Optional[Dict]:
        """
        SELL Signal Pattern:
        PRIMARY: Sweep + Delta flip + Absorption
        ALTERNATIVE (calm markets): Delta flip + Absorption + price resistance
        """
        # Check cooldown
        if time.time() - self.last_signal_time < config.COOLDOWN_SECONDS:
            return None
        
        # Check regime BEFORE generating signal
        should_filter, reason = self.check_regime_filter(market_state, 'down')
        if should_filter:
            logger.debug(f"SELL signal filtered: {reason}")
            return None
        
        # PRIMARY PATH: With sweep
        if self.recent_sweep and self.recent_sweep['direction'] == 'up':
            if self.current_state['delta_flip'] == 'bearish':
                return self._generate_sell_signal_with_sweep(market_state)
        
        # ALTERNATIVE PATH: Without sweep (for calm markets)
        # Requires: Strong delta flip + Absorption
        if self.current_state['delta_flip'] == 'bearish' and self.current_state['absorption_detected']:
            delta = market_state['delta']['delta']
            # Need strong negative delta (selling pressure)
            if delta < -config.MIN_DELTA_FLIP * 2:  # 2x threshold for no-sweep signals
                return self._generate_sell_signal_no_sweep(market_state)
        
        return None
    
    def _generate_sell_signal_with_sweep(self, market_state: Dict) -> Optional[Dict]:
        """Generate SELL signal with sweep confirmation"""
        absorption_confirmed = self.current_state['absorption_detected']
        price_reclaim = self.current_state['price_reclaim']
        
        confidence = 0
        reasons = []
        
        if self.recent_sweep:
            confidence += 30
            reasons.append(f"sweep ↑ ({self.recent_sweep['levels_removed']} levels)")
        
        if self.current_state['delta_flip'] == 'bearish':
            confidence += 40
            reasons.append("delta flip ↓")
        
        if absorption_confirmed:
            confidence += 20
            reasons.append("absorption confirmed")
        
        if price_reclaim:
            confidence += 10
            reasons.append("price reclaim")
        
        if confidence >= 70:
            signal = {
                'type': 'SELL',
                'price': market_state['price'],
                'timestamp': time.time(),
                'confidence': confidence,
                'reasons': reasons,
                'delta': market_state['delta']['delta'],
                'sweep_levels': self.recent_sweep['levels_removed'],
                'volatility': market_state.get('volatility_state', 'unknown')
            }
            
            self.last_signal_time = time.time()
            self.signal_history.append(signal)
            self.signals_generated += 1
            self._reset_state()
            
            return signal
        
        return None
    
    def _generate_sell_signal_no_sweep(self, market_state: Dict) -> Optional[Dict]:
        """Generate SELL signal without sweep (alternative for calm markets)"""
        confidence = 0
        reasons = []
        
        # Strong delta flip required (no sweep to confirm)
        if self.current_state['delta_flip'] == 'bearish':
            confidence += 50
            reasons.append("strong delta flip ↓")
        
        # Absorption provides resistance
        if self.current_state['absorption_detected']:
            confidence += 30
            reasons.append("absorption resistance")
        
        # Additional delta strength
        delta = market_state['delta']['delta']
        if delta < -config.MIN_DELTA_FLIP * 3:
            confidence += 20
            reasons.append("very strong selling")
        
        # Lower threshold for no-sweep signals (60% vs 70%)
        if confidence >= 60:
            signal = {
                'type': 'SELL',
                'price': market_state['price'],
                'timestamp': time.time(),
                'confidence': confidence,
                'reasons': reasons,
                'delta': market_state['delta']['delta'],
                'sweep_levels': 0,  # No sweep
                'volatility': market_state.get('volatility_state', 'unknown'),
                'pattern': 'no_sweep'  # Flag alternative pattern
            }
            
            self.last_signal_time = time.time()
            self.signal_history.append(signal)
            self.signals_generated += 1
            self._reset_state()
            
            return signal
        
        return None
    
    def generate_signal(self, market_state: Dict) -> Optional[Dict]:
        """Main signal generation logic"""
        # Update state
        self.update_state(market_state)
        
        # Check for BUY signal
        buy_signal = self.check_buy_signal(market_state)
        if buy_signal:
            return buy_signal
        
        # Check for SELL signal
        sell_signal = self.check_sell_signal(market_state)
        if sell_signal:
            return sell_signal
        
        return None
    
    def _reset_state(self):
        """Reset state after signal generation"""
        self.recent_sweep = None
        self.current_state = {
            'sweep_detected': False,
            'absorption_detected': False,
            'delta_flip': False,
            'price_reclaim': False
        }
    
    def get_statistics(self) -> Dict:
        """Get signal statistics including filtering"""
        if not self.signal_history:
            return {
                'total_signals': 0,
                'buy_signals': 0,
                'sell_signals': 0,
                'avg_confidence': 0,
                'signals_filtered': self.signals_filtered,
                'filter_rate': 0,
                'filter_reasons': self.filter_reasons
            }
        
        buy_count = sum(1 for s in self.signal_history if s['type'] == 'BUY')
        sell_count = sum(1 for s in self.signal_history if s['type'] == 'SELL')
        avg_confidence = sum(s['confidence'] for s in self.signal_history) / len(self.signal_history)
        
        total_attempts = self.signals_generated + self.signals_filtered
        filter_rate = (self.signals_filtered / total_attempts * 100) if total_attempts > 0 else 0
        
        return {
            'total_signals': len(self.signal_history),
            'buy_signals': buy_count,
            'sell_signals': sell_count,
            'avg_confidence': avg_confidence,
            'signals_filtered': self.signals_filtered,
            'filter_rate': filter_rate,
            'filter_reasons': self.filter_reasons
        }
