import aiohttp
import json
import logging
from typing import Dict, Optional, Any

logger = logging.getLogger(__name__)

class TransactionService:
    def __init__(self, engine_url: str):
        self.engine_url = engine_url
        self.session = None

    async def get_session(self):
        if not self.session:
            self.session = aiohttp.ClientSession()
        return self.session

    async def create_wallet(self) -> Dict[str, Any]:
        """Create new Solana wallet"""
        try:
            session = await self.get_session()
            async with session.post(f"{self.engine_url}/wallet/create") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    logger.error(f"Wallet creation failed: {error}")
                    return {"error": error}
        except Exception as e:
            logger.error(f"Wallet creation error: {str(e)}")
            return {"error": str(e)}

    async def import_wallet(self, private_key: str) -> Dict[str, Any]:
        """Import existing wallet"""
        try:
            session = await self.get_session()
            payload = {"private_key": private_key}
            async with session.post(f"{self.engine_url}/wallet/import", json=payload) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    return {"error": error}
        except Exception as e:
            logger.error(f"Wallet import error: {str(e)}")
            return {"error": str(e)}

    async def get_balance(self, address: str) -> Dict[str, Any]:
        """Get wallet balance"""
        try:
            session = await self.get_session()
            async with session.get(f"{self.engine_url}/wallet/balance/{address}") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    return {"error": error}
        except Exception as e:
            logger.error(f"Balance fetch error: {str(e)}")
            return {"error": str(e)}

    async def execute_trade(self, trade_data: Dict[str, Any]) -> Dict[str, Any]:
        """Execute buy/sell trade"""
        try:
            session = await self.get_session()
            async with session.post(f"{self.engine_url}/trade/execute", json=trade_data) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    return {"error": error}
        except Exception as e:
            logger.error(f"Trade execution error: {str(e)}")
            return {"error": str(e)}

    async def get_transaction_status(self, tx_hash: str) -> Dict[str, Any]:
        """Check transaction status"""
        try:
            session = await self.get_session()
            async with session.get(f"{self.engine_url}/transaction/status/{tx_hash}") as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error = await response.text()
                    return {"error": error}
        except Exception as e:
            logger.error(f"Transaction status error: {str(e)}")
            return {"error": str(e)}

    async def close(self):
        if self.session:
            await self.session.close()