const express = require('express');
const SolanaService = require('../services/solanaService');
const logger = require('../utils/logger');

const router = express.Router();
const solanaService = new SolanaService();

// Get transaction status
router.get('/status/:txHash', async (req, res) => {
    try {
        const { txHash } = req.params;
        
        if (!txHash) {
            return res.status(400).json({
                success: false,
                error: 'Transaction hash is required'
            });
        }
        
        const status = await solanaService.getTransactionStatus(txHash);
        
        res.json({
            success: true,
            txHash,
            ...status
        });
        
    } catch (error) {
        logger.error('Transaction status error:', error);
        res.status(500).json({
            success: false,
            error: 'Failed to get transaction status'
        });
    }
});

module.exports = router;