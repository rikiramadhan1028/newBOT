const { Connection, PublicKey, Keypair, Transaction, SystemProgram, LAMPORTS_PER_SOL } = require('@solana/web3.js');
const { getAssociatedTokenAddress, createAssociatedTokenAccountInstruction, TOKEN_PROGRAM_ID } = require('@solana/spl-token');
const crypto = require('crypto');
const axios = require('axios');
const logger = require('../utils/logger');

class SolanaService {
    constructor() {
        this.connection = null;
        this.rpcUrl = process.env.SOLANA_RPC_URL || 'https://api.mainnet-beta.solana.com';
        this.jupiterUrl = 'https://quote-api.jup.ag/v6';
    }

    async initialize() {
        try {
            this.connection = new Connection(this.rpcUrl, 'confirmed');
            
            // Test connection
            const version = await this.connection.getVersion();
            logger.info(`Connected to Solana cluster: ${JSON.stringify(version)}`);
            
            return true;
        } catch (error) {
            logger.error('Failed to initialize Solana connection:', error);
            throw error;
        }
    }

    generateKeypair() {
        const keypair = Keypair.generate();
        const privateKeyBytes = keypair.secretKey;
        const publicKey = keypair.publicKey.toString();
        
        // Encrypt private key
        const encryptedPrivateKey = this.encryptPrivateKey(privateKeyBytes);
        
        return {
            publicKey,
            encryptedPrivateKey
        };
    }

    encryptPrivateKey(privateKeyBytes) {
        const algorithm = 'aes-256-gcm';
        const key = crypto.scryptSync(process.env.ENCRYPTION_KEY, 'salt', 32);
        const iv = crypto.randomBytes(16);
        const cipher = crypto.createCipher(algorithm, key);
        
        cipher.setAAD(Buffer.from('roku-trade-wallet'));
        
        let encrypted = cipher.update(Buffer.from(privateKeyBytes), 'binary', 'hex');
        encrypted += cipher.final('hex');
        
        const authTag = cipher.getAuthTag();
        
        return {
            encrypted,
            iv: iv.toString('hex'),
            authTag: authTag.toString('hex')
        };
    }

    decryptPrivateKey(encryptedData) {
        const algorithm = 'aes-256-gcm';
        const key = crypto.scryptSync(process.env.ENCRYPTION_KEY, 'salt', 32);
        
        const decipher = crypto.createDecipher(algorithm, key);
        decipher.setAAD(Buffer.from('roku-trade-wallet'));
        decipher.setAuthTag(Buffer.from(encryptedData.authTag, 'hex'));
        
        let decrypted = decipher.update(encryptedData.encrypted, 'hex', 'binary');
        decrypted += decipher.final('binary');
        
        return new Uint8Array(Buffer.from(decrypted, 'binary'));
    }

    async getBalance(address) {
        try {
            const publicKey = new PublicKey(address);
            
            // Get SOL balance
            const solBalance = await this.connection.getBalance(publicKey);
            
            // Get token accounts
            const tokenAccounts = await this.connection.getParsedTokenAccountsByOwner(
                publicKey,
                { programId: TOKEN_PROGRAM_ID }
            );
            
            const tokens = tokenAccounts.value.map(account => {
                const { mint, tokenAmount } = account.account.data.parsed.info;
                return {
                    mint,
                    amount: tokenAmount.uiAmount,
                    decimals: tokenAmount.decimals
                };
            }).filter(token => token.amount > 0);
            
            return {
                sol: solBalance / LAMPORTS_PER_SOL,
                tokens
            };
        } catch (error) {
            logger.error('Error getting balance:', error);
            throw error;
        }
    }

    async getJupiterQuote(inputMint, outputMint, amount, slippageBps = 50) {
        try {
            const params = new URLSearchParams({
                inputMint,
                outputMint,
                amount: amount.toString(),
                slippageBps: slippageBps.toString()
            });
            
            const response = await axios.get(`${this.jupiterUrl}/quote?${params}`);
            return response.data;
        } catch (error) {
            logger.error('Error getting Jupiter quote:', error);
            throw error;
        }
    }

    async executeJupiterSwap(quoteResponse, userKeypair) {
        try {
            const swapResponse = await axios.post(`${this.jupiterUrl}/swap`, {
                quoteResponse,
                userPublicKey: userKeypair.publicKey.toString(),
                wrapAndUnwrapSol: true
            });
            
            const { swapTransaction } = swapResponse.data;
            
            // Deserialize and sign transaction
            const transaction = Transaction.from(Buffer.from(swapTransaction, 'base64'));
            transaction.sign(userKeypair);
            
            // Send transaction
            const txid = await this.connection.sendRawTransaction(transaction.serialize());
            
            logger.info(`Transaction sent: ${txid}`);
            return { txid, success: true };
            
        } catch (error) {
            logger.error('Error executing Jupiter swap:', error);
            throw error;
        }
    }

    async getTransactionStatus(txHash) {
        try {
            const status = await this.connection.getSignatureStatus(txHash);
            
            if (status.value?.confirmationStatus) {
                return {
                    confirmed: status.value.confirmationStatus !== null,
                    status: status.value.confirmationStatus,
                    error: status.value.err
                };
            }
            
            return {
                confirmed: false,
                status: 'pending',
                error: null
            };
        } catch (error) {
            logger.error('Error getting transaction status:', error);
            throw error;
        }
    }
}

module.exports = SolanaService;