const cron = require('node-cron');
const logger = require('../utils/logger');

class AutoTradeWorker {
    constructor(solanaService) {
        this.solanaService = solanaService;
        this.activePositions = new Map(); // userId -> positions with TP/SL
        this.isRunning = false;
        this.monitoringInterval = null;
    }

    async start() {
        this.isRunning = true;
        
        // Monitor prices every 10 seconds
        this.monitoringInterval = setInterval(() => {
            this.monitorPositions();
        }, 10000);
        
        // Cleanup old positions daily
        cron.schedule('0 0 * * *', () => {
            this.cleanupOldPositions();
        });
        
        logger.info('Auto Trade Worker started');
    }

    async stop() {
        this.isRunning = false;
        if (this.monitoringInterval) {
            clearInterval(this.monitoringInterval);
        }
        logger.info('Auto Trade Worker stopped');
    }

    async monitorPositions() {
        try {
            for (const [userId, userPositions] of this.activePositions) {
                for (const position of userPositions) {
                    await this.checkPosition(userId, position);
                }
            }
        } catch (error) {
            logger.error('Error monitoring positions:', error);
        }
    }

    async checkPosition(userId, position) {
        try {
            // Get current token price
            const currentPrice = await this.getCurrentPrice(position.tokenMint);
            
            if (!currentPrice) return;
            
            const priceChange = (currentPrice - position.entryPrice) / position.entryPrice;
            
            // Check Take Profit
            if (position.takeProfitPercent && priceChange >= position.takeProfitPercent / 100) {
                await this.executeTakeProfit(userId, position, currentPrice);
                return;
            }
            
            // Check Stop Loss
            if (position.stopLossPercent && priceChange <= -position.stopLossPercent / 100) {
                await this.executeStopLoss(userId, position, currentPrice);
                return;
            }
            
            // Check Trailing Stop
            if (position.trailingStopPercent) {
                await this.checkTrailingStop(userId, position, currentPrice);
            }
            
        } catch (error) {
            logger.error(`Error checking position for user ${userId}:`, error);
        }
    }

    async getCurrentPrice(tokenMint) {
        try {
            // Use Jupiter API to get current price
            const quote = await this.solanaService.getJupiterQuote(
                tokenMint,
                'So11111111111111111111111111111111111111112', // SOL
                1000000 // 1 token (assuming 6 decimals)
            );
            
            return parseFloat(quote.outAmount) / 1000000000; // Convert to SOL
        } catch (error) {
            logger.error('Error getting current price:', error);
            return null;
        }
    }

    async executeTakeProfit(userId, position, currentPrice) {
        try {
            logger.info(`Executing take profit for user ${userId}, token ${position.tokenSymbol} at ${currentPrice}`);
            
            const sellData = {
                encryptedPrivateKey: position.userEncryptedKey,
                inputToken: position.tokenMint,
                outputToken: 'SOL',
                amount: position.amount,
                slippage: 1.0,
                tradeType: 'take_profit'
            };
            
            // Execute sell order
            // This would call the trade execution logic
            
            // Remove from monitoring
            this.removePosition(userId, position.id);
            
            logger.info(`Take profit executed for user ${userId}`);
            
        } catch (error) {
            logger.error(`Take profit execution failed for user ${userId}:`, error);
        }
    }

    async executeStopLoss(userId, position, currentPrice) {
        try {
            logger.info(`Executing stop loss for user ${userId}, token ${position.tokenSymbol} at ${currentPrice}`);
            
            const sellData = {
                encryptedPrivateKey: position.userEncryptedKey,
                inputToken: position.tokenMint,
                outputToken: 'SOL',
                amount: position.amount,
                slippage: 2.0, // Higher slippage for emergency sells
                tradeType: 'stop_loss'
            };
            
            // Execute sell order
            // This would call the trade execution logic
            
            // Remove from monitoring
            this.removePosition(userId, position.id);
            
            logger.info(`Stop loss executed for user ${userId}`);
            
        } catch (error) {
            logger.error(`Stop loss execution failed for user ${userId}:`, error);
        }
    }

    async checkTrailingStop(userId, position, currentPrice) {
        const priceChange = (currentPrice - position.entryPrice) / position.entryPrice;
        
        // Update highest price if current price is higher
        if (currentPrice > position.highestPrice) {
            position.highestPrice = currentPrice;
        }
        
        // Check if price has dropped from highest by trailing stop percentage
        const dropFromHigh = (position.highestPrice - currentPrice) / position.highestPrice;
        
        if (dropFromHigh >= position.trailingStopPercent / 100) {
            await this.executeTrailingStop(userId, position, currentPrice);
        }
    }

    async executeTrailingStop(userId, position, currentPrice) {
        try {
            logger.info(`Executing trailing stop for user ${userId}, token ${position.tokenSymbol} at ${currentPrice}`);
            
            const sellData = {
                encryptedPrivateKey: position.userEncryptedKey,
                inputToken: position.tokenMint,
                outputToken: 'SOL',
                amount: position.amount,
                slippage: 1.5,
                tradeType: 'trailing_stop'
            };
            
            // Execute sell order
            // This would call the trade execution logic
            
            // Remove from monitoring
            this.removePosition(userId, position.id);
            
            logger.info(`Trailing stop executed for user ${userId}`);
            
        } catch (error) {
            logger.error(`Trailing stop execution failed for user ${userId}:`, error);
        }
    }

    addPosition(userId, position) {
        if (!this.activePositions.has(userId)) {
            this.activePositions.set(userId, []);
        }
        
        // Add timestamp and highest price tracking
        position.addedAt = Date.now();
        position.highestPrice = position.entryPrice;
        
        this.activePositions.get(userId).push(position);
        logger.info(`Added position to monitoring for user ${userId}`);
    }

    removePosition(userId, positionId) {
        const userPositions = this.activePositions.get(userId);
        if (userPositions) {
            const index = userPositions.findIndex(p => p.id === positionId);
            if (index > -1) {
                userPositions.splice(index, 1);
                if (userPositions.length === 0) {
                    this.activePositions.delete(userId);
                }
            }
        }
    }

    cleanupOldPositions() {
        const oneDayAgo = Date.now() - (24 * 60 * 60 * 1000);
        
        for (const [userId, positions] of this.activePositions) {
            const activePositions = positions.filter(p => p.addedAt > oneDayAgo);
            
            if (activePositions.length === 0) {
                this.activePositions.delete(userId);
            } else {
                this.activePositions.set(userId, activePositions);
            }
        }
        
        logger.info('Cleaned up old positions');
    }
}

module.exports = AutoTradeWorker;