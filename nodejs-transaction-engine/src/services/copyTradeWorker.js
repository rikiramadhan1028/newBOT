const WebSocket = require('ws');
const logger = require('../utils/logger');

class CopyTradeWorker {
    constructor(solanaService) {
        this.solanaService = solanaService;
        this.ws = null;
        this.watchedWallets = new Map(); // wallet -> user settings
        this.isRunning = false;
    }

    async start() {
        this.isRunning = true;
        await this.connectWebSocket();
        logger.info('Copy Trade Worker started');
    }

    async stop() {
        this.isRunning = false;
        if (this.ws) {
            this.ws.close();
        }
        logger.info('Copy Trade Worker stopped');
    }

    async connectWebSocket() {
        try {
            // Connect to Solana WebSocket for real-time transaction monitoring
            this.ws = new WebSocket('wss://api.mainnet-beta.solana.com/');
            
            this.ws.on('open', () => {
                logger.info('WebSocket connected for copy trading');
                this.subscribeToWallets();
            });
            
            this.ws.on('message', (data) => {
                this.handleTransactionUpdate(JSON.parse(data));
            });
            
            this.ws.on('error', (error) => {
                logger.error('Copy trade WebSocket error:', error);
            });
            
            this.ws.on('close', () => {
                logger.warn('Copy trade WebSocket disconnected');
                if (this.isRunning) {
                    setTimeout(() => this.connectWebSocket(), 5000);
                }
            });
            
        } catch (error) {
            logger.error('Failed to connect copy trade WebSocket:', error);
        }
    }

    subscribeToWallets() {
        // Subscribe to account changes for watched wallets
        this.watchedWallets.forEach((settings, walletAddress) => {
            const subscription = {
                jsonrpc: '2.0',
                id: `copy_${walletAddress}`,
                method: 'accountSubscribe',
                params: [
                    walletAddress,
                    {
                        encoding: 'base64',
                        commitment: 'confirmed'
                    }
                ]
            };
            
            this.ws.send(JSON.stringify(subscription));
        });
    }

    async handleTransactionUpdate(data) {
        try {
            if (data.method === 'accountNotification') {
                const { params } = data;
                const walletAddress = params.subscription;
                
                // Get transaction details
                const signature = params.result.value.data;
                const txDetails = await this.solanaService.connection.getParsedTransaction(signature);
                
                if (this.isSwapTransaction(txDetails)) {
                    await this.copyTrade(walletAddress, txDetails);
                }
            }
        } catch (error) {
            logger.error('Error handling copy trade update:', error);
        }
    }

    isSwapTransaction(txDetails) {
        // Check if transaction is a token swap
        return txDetails.meta.innerInstructions.some(instruction => 
            instruction.instructions.some(inst => 
                inst.programId.toString() === 'JUP6LkbZbjS1jKKwapdHNy74zcZ3tLUZoi5QNyVTaV4'
            )
        );
    }

    async copyTrade(originalWallet, txDetails) {
        try {
            const copySettings = this.watchedWallets.get(originalWallet);
            if (!copySettings) return;
            
            // Extract trade information
            const tradeInfo = this.extractTradeInfo(txDetails);
            
            // Calculate copy amount based on user settings
            const copyAmount = tradeInfo.amount * copySettings.copyRatio;
            
            // Add delay if configured
            if (copySettings.delay > 0) {
                await new Promise(resolve => setTimeout(resolve, copySettings.delay * 1000));
            }
            
            // Execute copy trade
            const copyTradeData = {
                encryptedPrivateKey: copySettings.userEncryptedKey,
                inputToken: tradeInfo.inputToken,
                outputToken: tradeInfo.outputToken,
                amount: copyAmount,
                slippage: copySettings.slippage || 0.5,
                tradeType: 'copy'
            };
            
            // This would call the trade execution endpoint internally
            await this.executeCopyTrade(copyTradeData, copySettings.userId);
            
        } catch (error) {
            logger.error('Error executing copy trade:', error);
        }
    }

    extractTradeInfo(txDetails) {
        // Extract input/output tokens and amounts from transaction
        const instructions = txDetails.meta.innerInstructions.flatMap(i => i.instructions);
        
        // This is simplified - in reality you'd need more complex parsing
        return {
            inputToken: 'SOL',
            outputToken: 'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v', // USDC
            amount: 1.0
        };
    }

    async executeCopyTrade(tradeData, userId) {
        try {
            // Execute the trade using the same logic as manual trades
            const result = await this.solanaService.executeJupiterSwap(/* trade params */);
            logger.info(`Copy trade executed for user ${userId}: ${result.txid}`);
        } catch (error) {
            logger.error(`Copy trade failed for user ${userId}:`, error);
        }
    }

    addWatchedWallet(walletAddress, settings) {
        this.watchedWallets.set(walletAddress, settings);
        if (this.ws && this.ws.readyState === WebSocket.OPEN) {
            this.subscribeToWallets();
        }
    }

    removeWatchedWallet(walletAddress) {
        this.watchedWallets.delete(walletAddress);
    }
}

module.exports = CopyTradeWorker;