CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    telegram_id BIGINT UNIQUE NOT NULL,
    wallet_address VARCHAR(44) NOT NULL,
    encrypted_private_key JSONB NOT NULL,
    settings JSONB DEFAULT '{}',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE positions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    token_mint VARCHAR(44) NOT NULL,
    token_symbol VARCHAR(20),
    amount DECIMAL(20,8) NOT NULL,
    entry_price DECIMAL(20,8) NOT NULL,
    current_price DECIMAL(20,8),
    pnl_percent DECIMAL(8,4),
    status VARCHAR(20) DEFAULT 'active',
    take_profit_percent DECIMAL(8,4),
    stop_loss_percent DECIMAL(8,4),
    trailing_stop_percent DECIMAL(8,4),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    tx_hash VARCHAR(88) NOT NULL,
    trade_type VARCHAR(20) NOT NULL,
    input_token VARCHAR(44),
    output_token VARCHAR(44),
    input_amount DECIMAL(20,8),
    output_amount DECIMAL(20,8),
    price_impact DECIMAL(8,4),
    status VARCHAR(20) DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE copy_trade_settings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    target_wallet VARCHAR(44) NOT NULL,
    copy_ratio DECIMAL(4,2) DEFAULT 1.0,
    delay_seconds INTEGER DEFAULT 0,
    max_amount DECIMAL(20,8),
    slippage DECIMAL(4,2) DEFAULT 0.5,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE snipe_settings (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id),
    min_liquidity DECIMAL(20,8) DEFAULT 10000,
    max_mcap DECIMAL(20,8) DEFAULT 1000000,
    min_safety_score DECIMAL(3,2) DEFAULT 0.5,
    snipe_amount DECIMAL(20,8) NOT NULL,
    slippage DECIMAL(4,2) DEFAULT 1.0,
    auto_sell_enabled BOOLEAN DEFAULT false,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE captcha_sessions (
    user_id BIGINT PRIMARY KEY,
    answer VARCHAR(10) NOT NULL,
    expires_at BIGINT NOT NULL
);

CREATE INDEX idx_users_telegram_id ON users(telegram_id);
CREATE INDEX idx_positions_user_id ON positions(user_id);
CREATE INDEX idx_transactions_user_id ON transactions(user_id);
CREATE INDEX idx_copy_trade_user_id ON copy_trade_settings(user_id);
CREATE INDEX idx_snipe_settings_user_id ON snipe_settings(user_id);