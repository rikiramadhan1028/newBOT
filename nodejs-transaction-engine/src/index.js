const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const compression = require('compression');
const dotenv = require('dotenv');
const logger = require('./utils/logger');
const walletRoutes = require('./controllers/walletController');
const tradeRoutes = require('./controllers/tradeController');
const transactionRoutes = require('./controllers/transactionController');
const SolanaService = require('./services/solanaService');
const CopyTradeWorker = require('./services/copyTradeWorker');
const SnipeWorker = require('./services/snipeWorker');
const AutoTradeWorker = require('./services/autoTradeWorker');

dotenv.config();

class TransactionEngine {
    constructor() {
        this.app = express();
        this.port = process.env.PORT || 3000;
        this.solanaService = new SolanaService();
        this.setupMiddleware();
        this.setupRoutes();
        this.startWorkers();
    }

    setupMiddleware() {
        this.app.use(helmet());
        this.app.use(compression());
        this.app.use(cors({
            origin: process.env.ALLOWED_ORIGINS?.split(',') || ['http://localhost:8000'],
            credentials: true
        }));
        this.app.use(express.json({ limit: '10mb' }));
        this.app.use(express.urlencoded({ extended: true }));

        // Request logging
        this.app.use((req, res, next) => {
            logger.info(`${req.method} ${req.path} - ${req.ip}`);
            next();
        });
    }

    setupRoutes() {
        // Health check
        this.app.get('/health', (req, res) => {
            res.json({ 
                status: 'ok', 
                timestamp: new Date().toISOString(),
                service: 'roku-trade-transaction-engine'
            });
        });

        // API routes
        this.app.use('/wallet', walletRoutes);
        this.app.use('/trade', tradeRoutes);
        this.app.use('/transaction', transactionRoutes);

        // Error handling
        this.app.use((err, req, res, next) => {
            logger.error('Unhandled error:', err);
            res.status(500).json({ 
                error: 'Internal server error',
                message: process.env.NODE_ENV === 'development' ? err.message : undefined
            });
        });

        // 404 handler
        this.app.use('*', (req, res) => {
            res.status(404).json({ error: 'Endpoint not found' });
        });
    }

    async startWorkers() {
        try {
            // Initialize Solana connection
            await this.solanaService.initialize();
            
            // Start background workers
            this.copyTradeWorker = new CopyTradeWorker(this.solanaService);
            this.snipeWorker = new SnipeWorker(this.solanaService);
            this.autoTradeWorker = new AutoTradeWorker(this.solanaService);
            
            await this.copyTradeWorker.start();
            await this.snipeWorker.start();
            await this.autoTradeWorker.start();
            
            logger.info('All background workers started successfully');
        } catch (error) {
            logger.error('Failed to start workers:', error);
        }
    }

    start() {
        this.app.listen(this.port, () => {
            logger.info(`🚀 Transaction Engine running on port ${this.port}`);
            logger.info(`Environment: ${process.env.NODE_ENV || 'development'}`);
        });

        // Graceful shutdown
        process.on('SIGTERM', this.shutdown.bind(this));
        process.on('SIGINT', this.shutdown.bind(this));
    }

    async shutdown() {
        logger.info('Shutting down gracefully...');
        
        if (this.copyTradeWorker) await this.copyTradeWorker.stop();
        if (this.snipeWorker) await this.snipeWorker.stop();
        if (this.autoTradeWorker) await this.autoTradeWorker.stop();
        
        process.exit(0);
    }
}

const engine = new TransactionEngine();
engine.start();