from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
import websockets
import json
import hmac
import hashlib
import time
import httpx
from decimal import Decimal
from typing import Dict, Optional, Any, List
from enum import Enum
import logging
import os
from dataclasses import dataclass

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="MEXC Trading Bot", description="Automated trading bot for MEXC Exchange")

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.environ.get('FRONTEND_URL', 'http://localhost:3000')],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Enums and Data Classes
class OrderSide(str, Enum):
    BUY = "BUY"
    SELL = "SELL"

class OrderType(str, Enum):
    LIMIT = "LIMIT"

class OrderStatus(str, Enum):
    NEW = "NEW"
    FILLED = "FILLED" 
    CANCELED = "CANCELED"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"

@dataclass
class OrderBook:
    symbol: str
    best_bid: Optional[Decimal] = None
    best_ask: Optional[Decimal] = None
    best_bid_qty: Optional[Decimal] = None
    best_ask_qty: Optional[Decimal] = None

# Pydantic Models
class TradingConfig(BaseModel):
    api_key: str
    secret_key: str
    symbol: str
    buy_quantity: float
    sell_quantity: float
    max_price_deviation: float = 0.05  # 5% max deviation

class OrderRequest(BaseModel):
    symbol: str
    side: OrderSide
    quantity: float
    price: float

# MEXC API Authentication
class MexcAuthenticator:
    def __init__(self, api_key: str, secret_key: str):
        self.api_key = api_key
        self.secret_key = secret_key.encode('utf-8')
    
    def generate_signature(self, method: str, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, str]:
        timestamp = int(time.time() * 1000)
        
        query_string = ""
        if params:
            filtered_params = {k: str(v) for k, v in params.items() if v is not None}
            query_string = "&".join([f"{k}={v}" for k, v in sorted(filtered_params.items())])
        
        if query_string:
            query_string += f"&timestamp={timestamp}"
        else:
            query_string = f"timestamp={timestamp}"
        
        signature = hmac.new(
            self.secret_key,
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        query_string += f"&signature={signature}"
        
        return {
            'X-MEXC-APIKEY': self.api_key,
            'timestamp': str(timestamp),
            'signature': signature,
            'query_string': query_string
        }

# Order Management
class OrderManager:
    def __init__(self, authenticator: MexcAuthenticator):
        self.authenticator = authenticator
        self.base_url = "https://api.mexc.com"
        self.client = httpx.AsyncClient(timeout=30.0)
        self.active_orders: Dict[str, Dict] = {}
    
    async def place_order(self, symbol: str, side: OrderSide, quantity: float, price: float) -> Dict[str, Any]:
        try:
            params = {
                'symbol': symbol,
                'side': side.value,
                'type': OrderType.LIMIT.value,
                'quantity': str(quantity),
                'price': str(price)
            }
            
            auth_data = self.authenticator.generate_signature('POST', '/api/v3/order', params)
            
            response = await self.client.post(
                f"{self.base_url}/api/v3/order?{auth_data['query_string']}",
                headers={'X-MEXC-APIKEY': auth_data['X-MEXC-APIKEY']}
            )
            
            if response.status_code == 200:
                result = response.json()
                if 'orderId' in result:
                    self.active_orders[result['orderId']] = {
                        'symbol': symbol,
                        'side': side,
                        'quantity': quantity,
                        'price': price,
                        'order_id': result['orderId']
                    }
                logger.info(f"Order placed: {result}")
                return result
            else:
                logger.error(f"Order placement failed: {response.status_code} - {response.text}")
                raise HTTPException(status_code=400, detail=f"Order placement failed: {response.text}")
                
        except Exception as e:
            logger.error(f"Error placing order: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    async def cancel_order(self, symbol: str, order_id: str) -> Dict[str, Any]:
        try:
            params = {
                'symbol': symbol,
                'orderId': order_id
            }
            
            auth_data = self.authenticator.generate_signature('DELETE', '/api/v3/order', params)
            
            response = await self.client.delete(
                f"{self.base_url}/api/v3/order?{auth_data['query_string']}",
                headers={'X-MEXC-APIKEY': auth_data['X-MEXC-APIKEY']}
            )
            
            if response.status_code == 200:
                result = response.json()
                if order_id in self.active_orders:
                    del self.active_orders[order_id]
                logger.info(f"Order canceled: {result}")
                return result
            else:
                logger.error(f"Order cancellation failed: {response.status_code} - {response.text}")
                raise HTTPException(status_code=400, detail=f"Order cancellation failed: {response.text}")
                
        except Exception as e:
            logger.error(f"Error canceling order: {e}")
            raise HTTPException(status_code=500, detail=str(e))

# WebSocket Order Book Monitor  
class OrderBookMonitor:
    def __init__(self):
        self.order_books: Dict[str, OrderBook] = {}
        self.callbacks: List = []
        self.connection = None
        self.running = False
    
    async def connect(self):
        try:
            self.connection = await websockets.connect(
                'wss://wbs.mexc.com/ws',
                ping_interval=20,
                ping_timeout=10
            )
            self.running = True
            logger.info("WebSocket connected to MEXC")
            asyncio.create_task(self._process_messages())
        except Exception as e:
            logger.error(f"WebSocket connection failed: {e}")
            raise
    
    async def subscribe_symbol(self, symbol: str):
        if symbol not in self.order_books:
            self.order_books[symbol] = OrderBook(symbol=symbol)
        
        subscription = {
            "method": "SUBSCRIPTION",
            "params": [f"spot@public.bookTicker.v3.api@{symbol}"]
        }
        
        if self.connection:
            await self.connection.send(json.dumps(subscription))
            logger.info(f"Subscribed to {symbol}")
    
    def add_callback(self, callback):
        self.callbacks.append(callback)
    
    async def _process_messages(self):
        try:
            async for message in self.connection:
                data = json.loads(message)
                await self._handle_message(data)
        except websockets.exceptions.ConnectionClosed:
            logger.warning("WebSocket connection closed")
            self.running = False
        except Exception as e:
            logger.error(f"Error processing WebSocket message: {e}")
            self.running = False
    
    async def _handle_message(self, message: dict):
        if 'c' in message and 'd' in message:
            channel = message['c']
            data = message['d']
            
            if 'bookTicker' in channel:
                parts = channel.split('@')
                if len(parts) >= 3:
                    symbol = parts[2]
                    
                    if symbol in self.order_books:
                        order_book = self.order_books[symbol]
                        
                        if 'b' in data and 'B' in data:
                            order_book.best_bid = Decimal(str(data['b']))
                            order_book.best_bid_qty = Decimal(str(data['B']))
                        
                        if 'a' in data and 'A' in data:
                            order_book.best_ask = Decimal(str(data['a']))
                            order_book.best_ask_qty = Decimal(str(data['A']))
                        
                        # Notify callbacks
                        for callback in self.callbacks:
                            try:
                                await callback(order_book)
                            except Exception as e:
                                logger.error(f"Error in callback: {e}")

# Trading Bot Logic
class TradingBot:
    def __init__(self, config: TradingConfig):
        self.config = config
        self.authenticator = MexcAuthenticator(config.api_key, config.secret_key)
        self.order_manager = OrderManager(self.authenticator)
        self.order_book_monitor = OrderBookMonitor()
        self.current_buy_order = None
        self.current_sell_order = None
        self.running = False
        self.initial_price = None
        
    async def start(self):
        self.running = True
        await self.order_book_monitor.connect()
        await self.order_book_monitor.subscribe_symbol(self.config.symbol)
        self.order_book_monitor.add_callback(self._on_order_book_update)
        logger.info(f"Trading bot started for {self.config.symbol}")
    
    async def stop(self):
        self.running = False
        # Cancel active orders
        if self.current_buy_order:
            try:
                await self.order_manager.cancel_order(self.config.symbol, self.current_buy_order['orderId'])
            except:
                pass
        if self.current_sell_order:
            try:
                await self.order_manager.cancel_order(self.config.symbol, self.current_sell_order['orderId'])
            except:
                pass
        logger.info("Trading bot stopped")
    
    async def _on_order_book_update(self, order_book: OrderBook):
        if not self.running or not order_book.best_bid or not order_book.best_ask:
            return
        
        # Set initial price reference
        if self.initial_price is None:
            mid_price = (order_book.best_bid + order_book.best_ask) / 2
            self.initial_price = mid_price
        
        try:
            # Check if we need to update buy order
            await self._update_buy_order(order_book)
            
            # Check if we need to update sell order  
            await self._update_sell_order(order_book)
            
        except Exception as e:
            logger.error(f"Error updating orders: {e}")
    
    async def _update_buy_order(self, order_book: OrderBook):
        # Calculate optimal buy price (slightly above best bid)
        tick_size = Decimal('0.00001')  # Minimum price increment
        optimal_buy_price = order_book.best_bid + tick_size
        
        # Check price deviation limits
        max_price = self.initial_price * (1 - self.config.max_price_deviation)
        if optimal_buy_price < max_price:
            optimal_buy_price = max_price
        
        # Check if we need to update the order
        should_update = False
        if self.current_buy_order is None:
            should_update = True
        else:
            current_price = Decimal(str(self.current_buy_order.get('price', 0)))
            if abs(optimal_buy_price - current_price) > tick_size:
                should_update = True
        
        if should_update:
            # Cancel existing order
            if self.current_buy_order:
                try:
                    await self.order_manager.cancel_order(self.config.symbol, self.current_buy_order['orderId'])
                    self.current_buy_order = None
                except Exception as e:
                    logger.error(f"Error canceling buy order: {e}")
            
            # Place new order
            try:
                result = await self.order_manager.place_order(
                    self.config.symbol,
                    OrderSide.BUY,
                    self.config.buy_quantity,
                    float(optimal_buy_price)
                )
                self.current_buy_order = result
                logger.info(f"Updated buy order at {optimal_buy_price}")
            except Exception as e:
                logger.error(f"Error placing buy order: {e}")
    
    async def _update_sell_order(self, order_book: OrderBook):
        # Calculate optimal sell price (slightly below best ask)
        tick_size = Decimal('0.00001')
        optimal_sell_price = order_book.best_ask - tick_size
        
        # Check price deviation limits
        min_price = self.initial_price * (1 + self.config.max_price_deviation)
        if optimal_sell_price > min_price:
            optimal_sell_price = min_price
        
        # Check if we need to update the order
        should_update = False
        if self.current_sell_order is None:
            should_update = True
        else:
            current_price = Decimal(str(self.current_sell_order.get('price', 0)))
            if abs(optimal_sell_price - current_price) > tick_size:
                should_update = True
        
        if should_update:
            # Cancel existing order
            if self.current_sell_order:
                try:
                    await self.order_manager.cancel_order(self.config.symbol, self.current_sell_order['orderId'])
                    self.current_sell_order = None
                except Exception as e:
                    logger.error(f"Error canceling sell order: {e}")
            
            # Place new order
            try:
                result = await self.order_manager.place_order(
                    self.config.symbol,
                    OrderSide.SELL,
                    self.config.sell_quantity,
                    float(optimal_sell_price)
                )
                self.current_sell_order = result
                logger.info(f"Updated sell order at {optimal_sell_price}")
            except Exception as e:
                logger.error(f"Error placing sell order: {e}")

# Global bot instance
trading_bot = None

# API Endpoints
@app.post("/api/start-bot")
async def start_bot(config: TradingConfig):
    global trading_bot
    
    try:
        if trading_bot and trading_bot.running:
            await trading_bot.stop()
        
        trading_bot = TradingBot(config)
        await trading_bot.start()
        
        return {"status": "success", "message": f"Trading bot started for {config.symbol}"}
    except Exception as e:
        logger.error(f"Error starting bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/stop-bot")
async def stop_bot():
    global trading_bot
    
    try:
        if trading_bot:
            await trading_bot.stop()
            trading_bot = None
        
        return {"status": "success", "message": "Trading bot stopped"}
    except Exception as e:
        logger.error(f"Error stopping bot: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/bot-status")
async def get_bot_status():
    global trading_bot
    
    if not trading_bot:
        return {"running": False, "message": "Bot not initialized"}
    
    status = {
        "running": trading_bot.running,
        "symbol": trading_bot.config.symbol,
        "current_buy_order": trading_bot.current_buy_order,
        "current_sell_order": trading_bot.current_sell_order,
        "initial_price": str(trading_bot.initial_price) if trading_bot.initial_price else None
    }
    
    if trading_bot.config.symbol in trading_bot.order_book_monitor.order_books:
        order_book = trading_bot.order_book_monitor.order_books[trading_bot.config.symbol]
        status.update({
            "best_bid": str(order_book.best_bid) if order_book.best_bid else None,
            "best_ask": str(order_book.best_ask) if order_book.best_ask else None,
            "spread": str(order_book.best_ask - order_book.best_bid) if order_book.best_ask and order_book.best_bid else None
        })
    
    return status

@app.get("/api/health")
async def health_check():
    return {"status": "healthy", "message": "MEXC Trading Bot API is running"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)