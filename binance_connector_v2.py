import asyncio
import websockets
import json
import aiohttp
from datetime import datetime
from typing import Callable, Dict, Any
import logging

logger = logging.getLogger(__name__)


class BinanceConnector:
    """
    Handles WebSocket connections to Binance with PROPER order book synchronization
    
    CRITICAL FIX:
    - Fetches REST snapshot before WS updates
    - Validates U/u sequence IDs
    - Auto-detects and recovers from desyncs
    """
    
    def __init__(self, orderbook_callback: Callable, trade_callback: Callable):
        self.orderbook_callback = orderbook_callback
        self.trade_callback = trade_callback
        self.orderbook_ws = None
        self.trades_ws = None
        self.running = False
        
        # Order book synchronization (CRITICAL)
        self.last_update_id = 0
        self.synced = False
        self.desync_count = 0
        self.rest_url = "https://api.binance.com/api/v3/depth"
        self.snapshot_pending = []  # Buffer updates until synced
        
    async def fetch_orderbook_snapshot(self, symbol: str = "ETHUSDT"):
        """
        Fetch initial order book snapshot via REST API
        REQUIRED by Binance for proper sync
        """
        logger.info(f"Fetching order book snapshot for {symbol}...")
        
        async with aiohttp.ClientSession() as session:
            params = {'symbol': symbol, 'limit': 1000}
            
            try:
                async with session.get(self.rest_url, params=params) as response:
                    if response.status != 200:
                        raise Exception(f"REST API error: {response.status}")
                    
                    data = await response.json()
                    
                    # Store the lastUpdateId (CRITICAL)
                    self.last_update_id = data['lastUpdateId']
                    
                    # Convert to our format
                    bids = [[float(price), float(qty)] for price, qty in data['bids']]
                    asks = [[float(price), float(qty)] for price, qty in data['asks']]
                    
                    snapshot = {
                        'timestamp': datetime.now().timestamp() * 1000,
                        'bids': bids,
                        'asks': asks,
                        'exchange': 'Binance',
                        'lastUpdateId': self.last_update_id,
                        'is_snapshot': True
                    }
                    
                    # Send snapshot to callback
                    await self.orderbook_callback(snapshot)
                    
                    logger.info(f"✓ Snapshot loaded: {len(bids)} bids, {len(asks)} asks")
                    logger.info(f"  Last update ID: {self.last_update_id}")
                    
                    # Now process buffered updates
                    await self._process_buffered_updates()
                    
            except Exception as e:
                logger.error(f"Failed to fetch snapshot: {e}")
                raise
        
    async def _process_buffered_updates(self):
        """Process updates that arrived while waiting for snapshot"""
        logger.info(f"Processing {len(self.snapshot_pending)} buffered updates...")
        
        for data in self.snapshot_pending:
            await self._process_orderbook_update(data)
        
        self.snapshot_pending.clear()
        
    async def connect_orderbook(self, url: str):
        """Connect to Binance order book WebSocket"""
        logger.info(f"Connecting to order book feed: {url}")
        
        # Fetch snapshot FIRST
        await self.fetch_orderbook_snapshot()
        
        while self.running:
            try:
                async with websockets.connect(url) as websocket:
                    self.orderbook_ws = websocket
                    logger.info("✓ Order book WebSocket connected")
                    
                    async for message in websocket:
                        if not self.running:
                            break
                        
                        data = json.loads(message)
                        await self.process_orderbook(data)
                        
            except Exception as e:
                logger.error(f"Order book connection error: {e}")
                if self.running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)
                    # Re-snapshot on reconnect
                    await self.fetch_orderbook_snapshot()
                    
    async def connect_trades(self, url: str):
        """Connect to Binance trades WebSocket"""
        logger.info(f"Connecting to trades feed: {url}")
        
        while self.running:
            try:
                async with websockets.connect(url) as websocket:
                    self.trades_ws = websocket
                    logger.info("✓ Trades connected")
                    
                    async for message in websocket:
                        if not self.running:
                            break
                        
                        data = json.loads(message)
                        await self.process_trade(data)
                        
            except Exception as e:
                logger.error(f"Trades connection error: {e}")
                if self.running:
                    logger.info("Reconnecting in 5 seconds...")
                    await asyncio.sleep(5)
                    
    async def process_orderbook(self, data: Dict[Any, Any]):
        """Process incoming order book data with sequence validation"""
        try:
            # Binance depth stream format includes U and u fields
            if 'b' in data and 'a' in data:
                # Buffer updates until we're synced
                if not self.synced:
                    self.snapshot_pending.append(data)
                    return
                
                await self._process_orderbook_update(data)
                
        except Exception as e:
            logger.error(f"Error processing order book: {e}")
    
    async def _process_orderbook_update(self, data: Dict[Any, Any]):
        """
        Process update with sequence validation
        
        Binance spec:
        - U = first update ID in event
        - u = final update ID in event
        - First update: U <= lastUpdateId+1 AND u >= lastUpdateId+1
        - Subsequent: U = previous_u + 1
        """
        first_update_id = data.get('U')
        final_update_id = data.get('u')
        
        if not self.synced:
            # Check if this is the first valid update after snapshot
            if first_update_id <= self.last_update_id + 1 <= final_update_id:
                logger.info(f"✓ Order book sync established (U={first_update_id}, u={final_update_id})")
                self.synced = True
            else:
                # Not the right update yet, skip
                return
        
        # Validate sequence continuity
        if self.synced and first_update_id != self.last_update_id + 1:
            logger.warning(f"⚠️  Sequence gap! Expected {self.last_update_id + 1}, got {first_update_id}")
            self.desync_count += 1
            
            # If multiple desyncs, need to re-snapshot
            if self.desync_count >= 3:
                logger.error("Multiple desyncs detected - re-snapshotting...")
                self.synced = False
                self.desync_count = 0
                await self.fetch_orderbook_snapshot()
                return
        else:
            self.desync_count = 0  # Reset on good sequence
        
        # Update is valid - process it
        bids = [[float(price), float(qty)] for price, qty in data['b']]
        asks = [[float(price), float(qty)] for price, qty in data['a']]
        
        normalized_data = {
            'timestamp': datetime.now().timestamp() * 1000,
            'bids': bids,
            'asks': asks,
            'exchange': 'Binance',
            'U': first_update_id,
            'u': final_update_id,
            'is_snapshot': False
        }
        
        # Update our sequence tracker
        self.last_update_id = final_update_id
        
        await self.orderbook_callback(normalized_data)
            
    async def process_trade(self, data: Dict[Any, Any]):
        """Process incoming trade data"""
        try:
            # Binance trade stream format
            if 'p' in data and 'q' in data:
                trade = {
                    'price': float(data['p']),
                    'size': float(data['q']),
                    'side': 'sell' if data['m'] else 'buy',  # m = buyer is maker
                    'timestamp': int(data['T']),
                    'exchange': 'Binance'
                }
                
                await self.trade_callback(trade)
        except Exception as e:
            logger.error(f"Error processing trade: {e}")
            
    async def start(self, orderbook_url: str, trades_url: str):
        """Start both WebSocket connections"""
        self.running = True
        
        await asyncio.gather(
            self.connect_orderbook(orderbook_url),
            self.connect_trades(trades_url)
        )
        
    async def stop(self):
        """Stop all connections"""
        logger.info("Stopping connections...")
        self.running = False
        
        if self.orderbook_ws:
            await self.orderbook_ws.close()
        if self.trades_ws:
            await self.trades_ws.close()
    
    def get_sync_stats(self) -> Dict:
        """Get synchronization statistics"""
        return {
            'synced': self.synced,
            'last_update_id': self.last_update_id,
            'desync_count': self.desync_count
        }
