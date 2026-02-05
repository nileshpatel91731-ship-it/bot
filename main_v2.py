#!/usr/bin/env python3
"""
ETH Order Flow Bot - Phase 1 UPGRADED
Binance Only | Professional Detection | Regime Filtering

CRITICAL IMPROVEMENTS:
✓ Proper order book synchronization with REST snapshot
✓ Trade-confirmed liquidity sweeps
✓ Volume/depth ratio absorption
✓ Adaptive delta calculation
✓ Market regime filtering
"""

import asyncio
import logging
import signal
import sys
from datetime import datetime
from colorama import init, Fore, Style

import config
from binance_connector_v2 import BinanceConnector
from order_flow_analyzer_v2 import OrderFlowAnalyzer
from signal_generator_v2 import SignalGenerator

# Initialize colorama for colored console output
init()

# Setup logging
logging.basicConfig(
    level=getattr(logging, config.LOG_LEVEL),
    format='%(asctime)s | %(levelname)s | %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)


class ETHOrderFlowBot:
    """Main bot orchestrating order flow analysis - UPGRADED VERSION"""
    
    def __init__(self):
        self.analyzer = OrderFlowAnalyzer()
        self.signal_generator = SignalGenerator()
        self.connector = None
        self.running = False
        
        # Stats
        self.orderbook_updates = 0
        self.trade_count = 0
        self.start_time = None
        
        logger.info("=" * 70)
        logger.info("ETH Order Flow Bot - Phase 1 UPGRADED")
        logger.info("=" * 70)
        logger.info(f"Symbol: {config.SYMBOL}")
        logger.info(f"Exchange: {config.EXCHANGE}")
        logger.info(f"Delta Window: {config.DELTA_WINDOW_SECONDS}s (adaptive)")
        logger.info(f"Signal Cooldown: {config.COOLDOWN_SECONDS}s")
        
        # Display mode info
        if hasattr(config, 'SILENT_MODE') and config.SILENT_MODE:
            logger.info(f"Display Mode: SILENT (signals and status only)")
        elif hasattr(config, 'QUIET_MODE') and config.QUIET_MODE:
            logger.info(f"Display Mode: QUIET (signals, sweeps, absorption)")
        else:
            logger.info(f"Display Mode: NORMAL (all updates)")
        
        logger.info("")
        logger.info("🔥 IMPROVEMENTS ACTIVE:")
        logger.info("  ✓ Proper order book synchronization")
        logger.info("  ✓ Trade-confirmed sweep detection")
        logger.info("  ✓ Volume/depth ratio absorption")
        logger.info("  ✓ Adaptive delta calculation")
        logger.info("  ✓ Market regime filtering")
        logger.info("=" * 70)
    
    async def on_orderbook_update(self, data):
        """Callback for order book updates"""
        self.orderbook_updates += 1
        self.analyzer.update_orderbook(data)
        
        # Periodic status update every 100 updates
        if self.orderbook_updates % 100 == 0:
            self._print_status()
    
    async def on_trade(self, trade):
        """Callback for trade updates"""
        self.trade_count += 1
        self.analyzer.add_trade(trade)
        
        # Check for signals every trade
        market_state = self.analyzer.get_market_state()
        signal = self.signal_generator.generate_signal(market_state)
        
        if signal:
            # Add visual break before signal
            print("\n" * 3)  # Clear space
            self._print_signal(signal)
            print("\n")  # Space after signal
        
        # Determine display mode
        silent_mode = hasattr(config, 'SILENT_MODE') and config.SILENT_MODE
        quiet_mode = hasattr(config, 'QUIET_MODE') and config.QUIET_MODE
        
        if silent_mode:
            # Silent mode: only signals (printed above) and periodic status
            pass  # Status is handled in on_orderbook_update
        elif quiet_mode:
            # Quiet mode: only show sweeps and absorption
            if market_state['liquidity_sweep'] or market_state['absorption']:
                self._print_market_state(market_state)
        else:
            # Normal mode: print every 50 trades
            if self.trade_count % 50 == 0:
                self._print_market_state(market_state)
    
    def _print_status(self):
        """Print status update with sync info"""
        uptime = (datetime.now() - self.start_time).total_seconds()
        delta_info = self.analyzer.calculate_delta()
        
        # Get sync status
        sync_stats = self.connector.get_sync_stats() if self.connector else {}
        sync_status = "✓" if sync_stats.get('synced', False) else "✗"
        
        # Get regime info
        market_state = self.analyzer.get_market_state()
        volatility = market_state.get('volatility_state', 'unknown')
        
        print(f"\n{Fore.CYAN}[STATUS] "
              f"Sync: {sync_status} | "
              f"Uptime: {uptime:.0f}s | "
              f"OB Updates: {self.orderbook_updates} | "
              f"Trades: {self.trade_count} | "
              f"Delta: {delta_info['delta']:.2f} | "
              f"Vol: {volatility}"
              f"{Style.RESET_ALL}")
    
    def _print_market_state(self, market_state):
        """Print current market state"""
        delta = market_state['delta']
        price = market_state['price']
        volatility = market_state.get('volatility_state', 'unknown')
        
        # Check if quiet mode is enabled
        quiet_mode = hasattr(config, 'QUIET_MODE') and config.QUIET_MODE
        
        # In quiet mode, ONLY print sweeps and absorption, NOT price updates
        if quiet_mode:
            # Only print sweep/absorption notifications
            if market_state['liquidity_sweep']:
                sweep = market_state['liquidity_sweep']
                direction = "⬇️" if sweep['direction'] == 'down' else "⬆️"
                sweep_color = Fore.YELLOW if sweep['levels_removed'] >= 5 else Fore.WHITE
                
                # Show if trade confirmed
                confirmed = "✓ CONFIRMED" if sweep.get('trade_confirmed') else "⚠ unconfirmed"
                
                print(f"{sweep_color}{Style.BRIGHT}[{datetime.now().strftime('%H:%M:%S')}] "
                      f"SWEEP {direction} {sweep['levels_removed']} levels | "
                      f"{sweep['time_ms']:.0f}ms | "
                      f"${sweep.get('notional', 0)/1000:.1f}k | "
                      f"{confirmed} | "
                      f"Price: {price:.2f}{Style.RESET_ALL}")
            
            if market_state['absorption']:
                absorption = market_state['absorption']
                ratio = absorption.get('volume_to_depth_ratio', 0)
                print(f"{Fore.MAGENTA}{Style.BRIGHT}[{datetime.now().strftime('%H:%M:%S')}] "
                      f"ABSORPTION | Vol: {absorption['volume']:.2f} | "
                      f"Ratio: {ratio:.1f}:1 | "
                      f"Side: {absorption['absorbing_side']} | "
                      f"Price: {price:.2f}{Style.RESET_ALL}")
        else:
            # Normal mode: print price updates
            # Delta color
            if delta['delta'] > 0:
                delta_color = Fore.GREEN
                delta_arrow = "↑"
            else:
                delta_color = Fore.RED
                delta_arrow = "↓"
            
            # Add line break every 10 updates to keep console readable
            end_char = '\n' if self.trade_count % 500 == 0 else '\r'
            
            # Print compact market info
            print(f"{Fore.WHITE}[{datetime.now().strftime('%H:%M:%S')}] "
                  f"Price: {price:.2f} | "
                  f"{delta_color}Δ: {delta['delta']:.2f} {delta_arrow} "
                  f"{Fore.WHITE}(B: {delta['buy_volume']:.1f} / S: {delta['sell_volume']:.1f}) | "
                  f"Vol: {volatility[:3]}"
                  f"{Style.RESET_ALL}", end=end_char)
            
            # Print sweep/absorption if detected (always on new line)
            if market_state['liquidity_sweep']:
                sweep = market_state['liquidity_sweep']
                direction = "⬇️" if sweep['direction'] == 'down' else "⬆️"
                sweep_color = Fore.YELLOW if sweep['levels_removed'] >= 5 else Fore.WHITE
                confirmed = "✓" if sweep.get('trade_confirmed') else "⚠"
                print(f"\n{sweep_color}{Style.BRIGHT}[SWEEP {direction}] "
                      f"{sweep['levels_removed']} levels | "
                      f"{sweep['time_ms']:.0f}ms | "
                      f"${sweep.get('notional', 0)/1000:.1f}k {confirmed}"
                      f"{Style.RESET_ALL}")
            
            if market_state['absorption']:
                absorption = market_state['absorption']
                ratio = absorption.get('volume_to_depth_ratio', 0)
                print(f"\n{Fore.MAGENTA}{Style.BRIGHT}[ABSORPTION] "
                      f"Vol: {absorption['volume']:.2f} | "
                      f"Ratio: {ratio:.1f}:1 | "
                      f"Side: {absorption['absorbing_side']}"
                      f"{Style.RESET_ALL}")
    
    def _print_signal(self, signal):
        """Print trading signal"""
        timestamp = datetime.fromtimestamp(signal['timestamp']).strftime('%H:%M:%S')
        
        if signal['type'] == 'BUY':
            color = Fore.GREEN
            emoji = "🟢"
        else:
            color = Fore.RED
            emoji = "🔴"
        
        # Multiple beeps to get attention
        for _ in range(3):
            print('\a', end='', flush=True)
        
        print(f"\n\n{'=' * 70}")
        print(f"{color}{Style.BRIGHT}{'*' * 70}{Style.RESET_ALL}")
        print(f"{color}{Style.BRIGHT}{emoji * 5} {signal['type']} SIGNAL {emoji * 5}{Style.RESET_ALL}")
        print(f"{color}{Style.BRIGHT}{'*' * 70}{Style.RESET_ALL}")
        print(f"{color}{Style.BRIGHT}[{timestamp}] ETH @ {signal['price']:.2f}{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}Confidence: {signal['confidence']}%{Style.RESET_ALL}")
        print(f"{Style.BRIGHT}Reasons: {' | '.join(signal['reasons'])}{Style.RESET_ALL}")
        print(f"Delta: {signal['delta']:.2f}")
        print(f"Volatility: {signal.get('volatility', 'unknown')}")
        print(f"{color}{Style.BRIGHT}{'*' * 70}{Style.RESET_ALL}")
        print(f"{'=' * 70}\n")
    
    async def start(self):
        """Start the bot"""
        self.running = True
        self.start_time = datetime.now()
        
        logger.info("Starting bot...")
        logger.info("Press Ctrl+C to stop\n")
        
        # Initialize connector (will fetch REST snapshot)
        self.connector = BinanceConnector(
            orderbook_callback=self.on_orderbook_update,
            trade_callback=self.on_trade
        )
        
        try:
            await self.connector.start(
                config.BINANCE_ORDERBOOK_WS,
                config.BINANCE_TRADES_WS
            )
        except KeyboardInterrupt:
            await self.stop()
    
    async def stop(self):
        """Stop the bot"""
        logger.info("\n\nStopping bot...")
        self.running = False
        
        if self.connector:
            await self.connector.stop()
        
        # Print final statistics
        stats = self.signal_generator.get_statistics()
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        print(f"\n{Fore.CYAN}{'=' * 70}")
        print("FINAL STATISTICS")
        print(f"{'=' * 70}")
        print(f"Runtime: {uptime:.0f}s")
        print(f"Order Book Updates: {self.orderbook_updates}")
        print(f"Trades Processed: {self.trade_count}")
        print(f"")
        print(f"SIGNALS:")
        print(f"  • Total Generated: {stats['total_signals']}")
        print(f"  • BUY Signals: {stats['buy_signals']}")
        print(f"  • SELL Signals: {stats['sell_signals']}")
        print(f"  • Avg Confidence: {stats['avg_confidence']:.1f}%")
        print(f"")
        print(f"REGIME FILTERING:")
        print(f"  • Signals Filtered: {stats['signals_filtered']}")
        print(f"  • Filter Rate: {stats['filter_rate']:.1f}%")
        if stats.get('filter_reasons'):
            print(f"  • Filter Reasons:")
            for reason, count in stats['filter_reasons'].items():
                print(f"      - {reason}: {count}")
        print(f"{'=' * 70}{Style.RESET_ALL}\n")
        
        logger.info("Bot stopped successfully")


def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    print("\n\nReceived interrupt signal...")
    sys.exit(0)


async def main():
    """Main entry point"""
    signal.signal(signal.SIGINT, signal_handler)
    
    bot = ETHOrderFlowBot()
    await bot.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Shutting down...")
