const express = require('express');
const { Keypair, PublicKey } = require('@solana/web3.js');
const SolanaService = require('../services/solanaService');
const logger = require('../utils/logger');

const router = express.Router();
const solanaService = new SolanaService();

// Execute trade
router.post('/execute', async (req, res) => {
    try {
        const { 
            encryptedPrivateKey, 
            inputToken, 
            outputToken, 
            amount, 
            slippage = 0.5,
            tradeType 
        } = req.body;
        
        // Validate required fields
        if (!encryptedPrivateKey || !inputToken || !outputToken || !amount) {
            return res.status(400).json({
                success: false,
                error: 'Missing required fields'
            });
        }
        
        // Decrypt private key and create keypair
        const privateKeyBytes = solanaService.decryptPrivateKey(encryptedPrivateKey);
        const userKeypair = Keypair.fromSecretKey(privateKeyBytes);
        
        // Convert amount to smallest unit if needed
        const tradeAmount = Math.floor(amount * (10 ** (inputToken === 'SOL' ? 9 : 6)));
        
        // Get Jupiter quote
        const inputMint = inputToken === 'SOL' ? 'So11111111111111111111111111111111111111112' : inputToken;
        const outputMint = outputToken === 'SOL' ? 'So11111111111111111111111111111111111111112' : outputToken;
        
        const quote = await solanaService.getJupiterQuote(
            inputMint,
            outputMint,
            tradeAmount,
            Math.floor(slippage * 100) // Convert to basis points
        );
        
        // Execute swap
        const result = await solanaService.executeJupiterSwap(quote, userKeypair);
        
        logger.info(`Trade executed: ${result.txid} for user ${userKeypair.publicKey.toString()}`);
        
        res.json({
            success: true,
            txid: result.txid,
            inputAmount: amount,
            outputAmount: quote.outAmount / (10 ** (outputToken === 'SOL' ? 9 : 6)),
            priceImpact: quote.priceImpactPct
        });
        
    } catch (error) {
        logger.error('Trade execution error:', error);
        res.status(500).json({
            success: false,
            error: error.message || 'Failed to execute trade'
        });
    }
});

// Get current price
router.get('/price/:inputToken/:outputToken/:amount', async (req, res) => {
    try {
        const { inputToken, outputToken, amount } = req.params;
        
        const inputMint = inputToken === 'SOL' ? 'So11111111111111111111111111111111111111112' : inputToken;
        const outputMint = outputToken === 'SOL' ? 'So11111111111111111111111111111111111111112' : outputToken;
        
        const tradeAmount = Math.floor(parseFloat(amount) * (10 ** (inputToken === 'SOL' ? 9 : 6)));
        
        const quote = await solanaService.getJupiterQuote(inputMint, outputMint, tradeAmount);
        
        res.json({
            success: true,
            inputAmount: amount,
            outputAmount: quote.outAmount / (10 ** (outputToken === 'SOL' ? 9 : 6)),
            priceImpact: quote.priceImpactPct,
            route: quote.routePlan
        });
        
    } catch (error) {
        logger.error('Price fetch error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to get price'
        });
    }
});

module.exports = router;
