const express = require('express');
const { Keypair } = require('@solana/web3.js');
const SolanaService = require('../services/solanaService');
const logger = require('../utils/logger');

const router = express.Router();
const solanaService = new SolanaService();

// Create new wallet
router.post('/create', async (req, res) => {
    try {
        const wallet = solanaService.generateKeypair();
        
        logger.info(`New wallet created: ${wallet.publicKey}`);
        
        res.json({
            success: true,
            publicKey: wallet.publicKey,
            encryptedPrivateKey: wallet.encryptedPrivateKey
        });
    } catch (error) {
        logger.error('Wallet creation error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to create wallet'
        });
    }
});

// Import existing wallet
router.post('/import', async (req, res) => {
    try {
        const { private_key } = req.body;
        
        if (!private_key) {
            return res.status(400).json({
                success: false,
                error: 'Private key is required'
            });
        }
        
        // Validate private key format
        let keypair;
        try {
            const secretKey = Buffer.from(private_key, 'base64');
            keypair = Keypair.fromSecretKey(secretKey);
        } catch (e) {
            return res.status(400).json({
                success: false,
                error: 'Invalid private key format'
            });
        }
        
        const encryptedPrivateKey = solanaService.encryptPrivateKey(keypair.secretKey);
        
        logger.info(`Wallet imported: ${keypair.publicKey.toString()}`);
        
        res.json({
            success: true,
            publicKey: keypair.publicKey.toString(),
            encryptedPrivateKey
        });
    } catch (error) {
        logger.error('Wallet import error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to import wallet'
        });
    }
});

// Get wallet balance
router.get('/balance/:address', async (req, res) => {
    try {
        const { address } = req.params;
        
        if (!address) {
            return res.status(400).json({
                success: false,
                error: 'Address is required'
            });
        }
        
        const balance = await solanaService.getBalance(address);
        
        res.json({
            success: true,
            balance
        });
    } catch (error) {
        logger.error('Balance fetch error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to get balance'
        });
    }
});

module.exports = router;

