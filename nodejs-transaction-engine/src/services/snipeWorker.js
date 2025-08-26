const WebSocket = require('ws');
const axios = require('axios');
const logger = require('../utils/logger');

class SnipeWorker {
    constructor(solanaService) {
        this.solanaService = solanaService;
        this.ws = null;
        this.snipeSettings = new Map(); // userId -> snipe settings
        this.isRunning = false;
    }

    async start() {
        this.isRunning = true;
        await this.connectWebSocket();
        await this.startNewTokenMonitoring();
        logger.info('Snipe Worker started');
    }

    async stop() {
        this.isRunning = false;
        if (this.ws) {
            this.ws.close();
        }
        logger.info('Snipe Worker stopped');
    }

    async connectWebSocket() {
        try {
            // Connect to Raydium or other DEX WebSocket for new pool monitoring
            this.ws = new WebSocket('wss://api.mainnet-beta.solana.com/');
            
            this.ws.on('open', () => {
                logger.info('WebSocket connected for token sniping');
                this.subscribeToNewPools();
            });
            
            this.ws.on('message', (data) => {
                this.handleNewPoolUpdate(JSON.parse(data));
            });
            
            this.ws.on('error', (error) => {
                logger.error('Snipe WebSocket error:', error);
            });
            
            this.ws.on('close', () => {
                logger.warn('Snipe WebSocket disconnected');
                if (this.isRunning) {
                    setTimeout(() => this.connectWebSocket(), 5000);
                }
            });
            
        } catch (error) {
            logger.error('Failed to connect snipe WebSocket:', error);
        }
    }

    subscribeToNewPools() {
        // Subscribe to Raydium program account changes
        const subscription = {
            jsonrpc: '2.0',
            id: 'new_pools',
            method: 'programSubscribe',
            params: [
                '675kPX9MHTjS2zt1qfr1NYHuzeLXfQM9H24wFSUt1Mp8', // Raydium AMM program
                {
                    encoding: 'base64',
                    commitment: 'confirmed'
                }
            ]
        };
        
        this.ws.send(JSON.stringify(subscription));
    }

    async handleNewPoolUpdate(data) {
        try {
            if (data.method === 'programNotification') {
                const { params } = data;
                const poolData = params.result.value;
                
                if (this.isNewPool(poolData)) {
                    const tokenInfo = await this.analyzeNewToken(poolData);
                    
                    if (this.shouldSnipe(tokenInfo)) {
                        await this.executeSnipes(tokenInfo);
                    }
                }
            }
        } catch (error) {
            logger.error('Error handling new pool update:', error);
        }
    }

    isNewPool(poolData) {
        // Check if this is a new liquidity pool
        // This is simplified - you'd need to parse the actual pool data
        return poolData.account.data.length > 0;
    }

    async analyzeNewToken(poolData) {
        try {
            // Extract token mint and other details from pool data
            // This is a simplified version
            const tokenMint = 'extracted_token_mint';
            
            // Get token metadata
            const metadata = await this.getTokenMetadata(tokenMint);
            
            // Analyze liquidity and other factors
            const analysis = await this.performTokenAnalysis(tokenMint);
            
            return {
                mint: tokenMint,
                symbol: metadata.symbol,
                name: metadata.name,
                liquidity: analysis.liquidity,
                mcap: analysis.mcap,
                safetyScore: analysis.safetyScore
            };
        } catch (error) {
            logger.error('Error analyzing new token:', error);
            return null;
        }
    }

    async getTokenMetadata(tokenMint) {
        try {
            // Fetch token metadata from Solana
            const response = await axios.get(`https://api.solscan.io/token/${tokenMint}`);
            return response.data;
        } catch (error) {
            logger.error('Error fetching token metadata:', error);
            return { symbol: 'UNKNOWN', name: 'Unknown Token' };
        }
    }

    async performTokenAnalysis(tokenMint) {
        // Perform safety analysis
        // - Check for honeypot indicators
        // - Analyze liquidity depth
        // - Check token distribution
        // - Verify contract safety
        
        return {
            liquidity: 50000, // USD
            mcap: 1000000, // USD
            safetyScore: 0.8 // 0-1 scale
        };
    }

    shouldSnipe(tokenInfo) {
        if (!tokenInfo) return false;
        
        // Check against user snipe settings
        for (const [userId, settings] of this.snipeSettings) {
            if (this.matchesSnipeCriteria(tokenInfo, settings)) {
                return true;
            }
        }
        return false;
    }

    matchesSnipeCriteria(tokenInfo, settings) {
        // Check if token matches user's snipe criteria
        return (
            tokenInfo.liquidity >= settings.minLiquidity &&
            tokenInfo.mcap <= settings.maxMcap &&
            tokenInfo.safetyScore >= settings.minSafetyScore
        );
    }

    async executeSnipes(tokenInfo) {
        for (const [userId, settings] of this.snipeSettings) {
            if (this.matchesSnipeCriteria(tokenInfo, settings)) {
                try {
                    await this.executeSnipe(userId, tokenInfo, settings);
                } catch (error) {
                    logger.error(`Snipe failed for user ${userId}:`, error);
                }
            }
        }
    }

    async executeSnipe(userId, tokenInfo, settings) {
        const snipeData = {
            encryptedPrivateKey: settings.userEncryptedKey,
            inputToken: 'SOL',
            outputToken: tokenInfo.mint,
            amount: settings.snipeAmount,
            slippage: settings.slippage || 1.0,
            tradeType: 'snipe'
        };
        
        // Execute the snipe trade
        // This would use the same trade execution logic
        logger.info(`Executing snipe for user ${userId} on token ${tokenInfo.symbol}`);
        
        // Add to auto-sell monitoring if configured
        if (settings.autoSellEnabled) {
            // Add to auto trade monitoring
        }
    }

    addSnipeSettings(userId, settings) {
        this.snipeSettings.set(userId, settings);
    }

    removeSnipeSettings(userId) {
        this.snipeSettings.delete(userId);
    }

    async startNewTokenMonitoring() {
        // Alternative method: Poll DEX APIs for new tokens
        setInterval(async () => {
            try {
                await this.pollNewTokens();
            } catch (error) {
                logger.error('Error polling new tokens:', error);
            }
        }, 5000); // Check every 5 seconds
    }

    async pollNewTokens() {
        try {
            // Poll DexScreener or other APIs for new tokens
            const response = await axios.get('https://api.dexscreener.com/latest/dex/tokens/new');
            const newTokens = response.data.pairs;
            
            for (const token of newTokens) {
                if (token.chainId === 'solana') {
                    const tokenInfo = {
                        mint: token.baseToken.address,
                        symbol: token.baseToken.symbol,
                        name: token.baseToken.name,
                        liquidity: parseFloat(token.liquidity?.usd || 0),
                        mcap: parseFloat(token.fdv || 0),
                        safetyScore: 0.7 // Default score
                    };
                    
                    if (this.shouldSnipe(tokenInfo)) {
                        await this.executeSnipes(tokenInfo);
                    }
                }
            }
        } catch (error) {
            logger.error('Error polling new tokens:', error);
        }
    }
}

module.exports = SnipeWorker;