import motor.motor_asyncio
import json
import os
from typing import Optional, Dict, List, Any
from datetime import datetime
from bson import ObjectId
import logging

logger = logging.getLogger(__name__)

class Database:
    def __init__(self):
        self.connection_string = os.getenv('MONGODB_URL', 'mongodb://localhost:27017')
        self.database_name = os.getenv('MONGODB_DATABASE', 'roku_trade')
        self.client = None
        self.db = None

    async def init_connection(self):
        if not self.client:
            try:
                self.client = motor.motor_asyncio.AsyncIOMotorClient(self.connection_string)
                self.db = self.client[self.database_name]
                # Test connection
                await self.client.admin.command('ping')
                logger.info(f"Connected to MongoDB: {self.database_name}")
                
                # Create indexes
                await self._create_indexes()
            except Exception as e:
                logger.error(f"Failed to connect to MongoDB: {e}")
                raise

    async def get_user(self, user_id: int) -> Optional[Dict]:
        await self.init_connection()
        try:
            user = await self.db.users.find_one({"telegram_id": user_id})
            if user:
                user['_id'] = str(user['_id'])  # Convert ObjectId to string
            return user
        except Exception as e:
            logger.error(f"Error getting user {user_id}: {e}")
            return None

    async def create_user(self, user_id: int, wallet_address: str, encrypted_key: Dict):
        await self.init_connection()
        try:
            user_doc = {
                "telegram_id": user_id,
                "wallet_address": wallet_address,
                "encrypted_private_key": encrypted_key,
                "settings": {},
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            result = await self.db.users.insert_one(user_doc)
            logger.info(f"Created user {user_id} with ID: {result.inserted_id}")
            return result.inserted_id
        except Exception as e:
            logger.error(f"Error creating user {user_id}: {e}")
            raise

    async def update_user_settings(self, user_id: int, settings: Dict):
        await self.init_connection()
        try:
            result = await self.db.users.update_one(
                {"telegram_id": user_id},
                {
                    "$set": {
                        "settings": settings,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating settings for user {user_id}: {e}")
            return False

    async def get_user_positions(self, user_id: int) -> List[Dict]:
        await self.init_connection()
        try:
            cursor = self.db.positions.find({
                "user_id": user_id,
                "status": "active"
            })
            positions = await cursor.to_list(length=None)
            
            # Convert ObjectId to string
            for position in positions:
                position['_id'] = str(position['_id'])
                
            return positions
        except Exception as e:
            logger.error(f"Error getting positions for user {user_id}: {e}")
            return []

    async def store_captcha(self, user_id: int, answer: str):
        await self.init_connection()
        try:
            captcha_doc = {
                "user_id": user_id,
                "answer": answer,
                "expires_at": datetime.utcnow().timestamp() + 300,  # 5 minutes
                "created_at": datetime.utcnow()
            }
            
            # Upsert (update if exists, insert if not)
            await self.db.captcha_sessions.replace_one(
                {"user_id": user_id},
                captcha_doc,
                upsert=True
            )
        except Exception as e:
            logger.error(f"Error storing captcha for user {user_id}: {e}")
            raise

    async def verify_captcha(self, user_id: int, user_answer: str) -> bool:
        await self.init_connection()
        try:
            captcha = await self.db.captcha_sessions.find_one({
                "user_id": user_id,
                "expires_at": {"$gt": datetime.utcnow().timestamp()}
            })
            
            if captcha and captcha['answer'] == user_answer:
                # Delete captcha after successful verification
                await self.db.captcha_sessions.delete_one({"user_id": user_id})
                return True
            return False
        except Exception as e:
            logger.error(f"Error verifying captcha for user {user_id}: {e}")
            return False

    async def close(self):
        if self.client:
            self.client.close()
            logger.info("MongoDB connection closed")

    async def _create_indexes(self):
        """Create database indexes for optimal performance"""
        try:
            # Users collection indexes
            await self.db.users.create_index("telegram_id", unique=True)
            await self.db.users.create_index("wallet_address")
            await self.db.users.create_index("created_at")
            
            # Positions collection indexes
            await self.db.positions.create_index([("user_id", 1), ("status", 1)])
            await self.db.positions.create_index("token_mint")
            await self.db.positions.create_index("created_at")
            
            # Transactions collection indexes
            await self.db.transactions.create_index("user_id")
            await self.db.transactions.create_index("tx_hash", unique=True)
            await self.db.transactions.create_index("created_at")
            
            # Copy trade settings indexes
            await self.db.copy_trade_settings.create_index("user_id")
            await self.db.copy_trade_settings.create_index("target_wallet")
            
            # Snipe settings indexes
            await self.db.snipe_settings.create_index("user_id")
            
            # Captcha sessions indexes
            await self.db.captcha_sessions.create_index("user_id", unique=True)
            await self.db.captcha_sessions.create_index("expires_at", expireAfterSeconds=0)
            
            logger.info("Database indexes created successfully")
        except Exception as e:
            logger.warning(f"Some indexes may already exist: {e}")

    # Additional MongoDB-specific methods
    async def save_position(self, user_id: int, token_mint: str, amount: float, entry_price: float, tx_hash: str, token_symbol: str = None):
        """Save trading position"""
        await self.init_connection()
        try:
            position_doc = {
                "user_id": user_id,
                "token_mint": token_mint,
                "token_symbol": token_symbol,
                "amount": amount,
                "entry_price": entry_price,
                "current_price": entry_price,
                "pnl_percent": 0.0,
                "status": "active",
                "tx_hash": tx_hash,
                "take_profit_percent": None,
                "stop_loss_percent": None,
                "trailing_stop_percent": None,
                "created_at": datetime.utcnow(),
                "updated_at": datetime.utcnow()
            }
            
            result = await self.db.positions.insert_one(position_doc)
            return result.inserted_id
        except Exception as e:
            logger.error(f"Error saving position: {e}")
            return None

    async def update_user_wallet(self, user_id: int, wallet_address: str, encrypted_key: Dict):
        """Update user wallet information"""
        await self.init_connection()
        try:
            result = await self.db.users.update_one(
                {"telegram_id": user_id},
                {
                    "$set": {
                        "wallet_address": wallet_address,
                        "encrypted_private_key": encrypted_key,
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error updating wallet for user {user_id}: {e}")
            return False

    async def get_position(self, position_id: str) -> Optional[Dict]:
        """Get specific position by ID"""
        await self.init_connection()
        try:
            position = await self.db.positions.find_one({"_id": ObjectId(position_id)})
            if position:
                position['_id'] = str(position['_id'])
            return position
        except Exception as e:
            logger.error(f"Error getting position {position_id}: {e}")
            return None

    async def close_position(self, position_id: str, tx_hash: str, sol_received: float):
        """Close a trading position"""
        await self.init_connection()
        try:
            result = await self.db.positions.update_one(
                {"_id": ObjectId(position_id)},
                {
                    "$set": {
                        "status": "closed",
                        "close_tx_hash": tx_hash,
                        "sol_received": sol_received,
                        "closed_at": datetime.utcnow(),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            return result.modified_count > 0
        except Exception as e:
            logger.error(f"Error closing position {position_id}: {e}")
            return False

    async def add_copy_wallet(self, user_id: int, target_wallet: str, ratio: float = 1.0, max_amount: float = 1.0):
        """Add wallet to copy trading list"""
        await self.init_connection()
        try:
            # Check if wallet already exists
            existing = await self.db.copy_trade_settings.find_one({
                "user_id": user_id,
                "target_wallet": target_wallet
            })
            
            if existing:
                return False
            
            copy_doc = {
                "user_id": user_id,
                "target_wallet": target_wallet,
                "copy_ratio": ratio,
                "delay_seconds": 0,
                "max_amount": max_amount,
                "slippage": 0.5,
                "enabled": True,
                "created_at": datetime.utcnow()
            }
            
            await self.db.copy_trade_settings.insert_one(copy_doc)
            return True
        except Exception as e:
            logger.error(f"Error adding copy wallet: {e}")
            return False

    async def get_copy_wallets(self, user_id: int) -> List[Dict]:
        """Get user's copy trading wallets"""
        await self.init_connection()
        try:
            cursor = self.db.copy_trade_settings.find({"user_id": user_id})
            wallets = await cursor.to_list(length=None)
            
            for wallet in wallets:
                wallet['_id'] = str(wallet['_id'])
                wallet['active'] = wallet.get('enabled', True)
                wallet['address'] = wallet['target_wallet']
                wallet['ratio'] = wallet['copy_ratio']
                
            return wallets
        except Exception as e:
            logger.error(f"Error getting copy wallets: {e}")
            return []

    async def get_snipe_settings(self, user_id: int) -> Dict:
        """Get user's snipe settings"""
        await self.init_connection()
        try:
            settings = await self.db.snipe_settings.find_one({"user_id": user_id})
            if not settings:
                # Return default settings
                return {
                    "min_liquidity": 1000,
                    "max_mcap": 100000,
                    "min_safety": 7,
                    "buy_amount": 0.1,
                    "profit_target": 200,
                    "stop_loss": 50
                }
            
            settings['_id'] = str(settings['_id'])
            return settings
        except Exception as e:
            logger.error(f"Error getting snipe settings: {e}")
            return {}

    async def update_snipe_status(self, user_id: int, enabled: bool) -> bool:
        """Update snipe status"""
        await self.init_connection()
        try:
            result = await self.db.snipe_settings.update_one(
                {"user_id": user_id},
                {
                    "$set": {
                        "enabled": enabled,
                        "updated_at": datetime.utcnow()
                    }
                },
                upsert=True
            )
            return result.modified_count > 0 or result.upserted_id is not None
        except Exception as e:
            logger.error(f"Error updating snipe status: {e}")
            return False

    async def get_auto_orders(self, user_id: int) -> List[Dict]:
        """Get user's auto orders (TP/SL)"""
        await self.init_connection()
        try:
            cursor = self.db.auto_orders.find({"user_id": user_id, "active": True})
            orders = await cursor.to_list(length=None)
            
            for order in orders:
                order['_id'] = str(order['_id'])
                
            return orders
        except Exception as e:
            logger.error(f"Error getting auto orders: {e}")
            return []

    async def save_transaction(self, user_id: int, tx_hash: str, trade_type: str, input_token: str, output_token: str, input_amount: float, output_amount: float):
        """Save transaction record"""
        await self.init_connection()
        try:
            tx_doc = {
                "user_id": user_id,
                "tx_hash": tx_hash,
                "trade_type": trade_type,
                "input_token": input_token,
                "output_token": output_token,
                "input_amount": input_amount,
                "output_amount": output_amount,
                "price_impact": 0.0,
                "status": "pending",
                "created_at": datetime.utcnow()
            }
            
            await self.db.transactions.insert_one(tx_doc)
            return True
        except Exception as e:
            logger.error(f"Error saving transaction: {e}")
            return False