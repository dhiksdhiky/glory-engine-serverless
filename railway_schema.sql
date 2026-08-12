-- 1. Tabel Daftar Saham
CREATE TABLE IF NOT EXISTS daftar_saham (
    kode VARCHAR(10) PRIMARY KEY,
    no INTEGER,
    nama_perusahaan VARCHAR(255) NOT NULL,
    tanggal_pencatatan DATE,
    saham BIGINT,
    papan_pencatatan VARCHAR(50),
    tanggal_update DATE
);

-- 2. Tabel Open Positions (Untuk Portofolio Aktif)
CREATE TABLE IF NOT EXISTS open_positions (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    entry_date DATE NOT NULL,
    entry_price FLOAT NOT NULL,
    quantity INTEGER NOT NULL,
    current_trailing_stop FLOAT NOT NULL,
    last_updated DATE NOT NULL
);

-- 3. Tabel Trade History (Untuk Histori Trade Tertutup)
CREATE TABLE IF NOT EXISTS trade_history (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    entry_date DATE NOT NULL,
    entry_price FLOAT NOT NULL,
    exit_date DATE NOT NULL,
    exit_price FLOAT NOT NULL,
    quantity INTEGER NOT NULL,
    profit_loss_percent FLOAT NOT NULL
);

-- 4. Tabel Harga Saham (OHLCV)
CREATE TABLE IF NOT EXISTS harga_saham (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    tanggal DATE NOT NULL,
    open NUMERIC(20,4), 
    high NUMERIC(20,4),
    low NUMERIC(20,4), 
    close NUMERIC(20,4),
    volume BIGINT,
    UNIQUE (ticker, tanggal)
);

-- 5. Tabel Broker Summary
CREATE TABLE IF NOT EXISTS broker_summary (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    broker_code VARCHAR(5) NOT NULL,
    buy_vol BIGINT DEFAULT 0,
    buy_val FLOAT DEFAULT 0,
    buy_avg FLOAT DEFAULT 0,
    sell_vol BIGINT DEFAULT 0,
    sell_val FLOAT DEFAULT 0,
    sell_avg FLOAT DEFAULT 0,
    net_vol BIGINT DEFAULT 0,
    net_val FLOAT DEFAULT 0,
    UNIQUE (ticker, date, broker_code)
);

-- 6. Tabel Error Logs
CREATE TABLE IF NOT EXISTS bot_error_logs (
    id SERIAL PRIMARY KEY,
    bot_name VARCHAR(50) NOT NULL,
    timestamp TIMESTAMPTZ DEFAULT NOW(),
    error_level VARCHAR(20) NOT NULL,
    ticker VARCHAR(10),
    error_message VARCHAR(255) NOT NULL,
    traceback TEXT
);

-- INDEX untuk mempercepat query PWA/Bot
CREATE INDEX IF NOT EXISTS idx_harga_saham_tanggal ON harga_saham(tanggal);
CREATE INDEX IF NOT EXISTS idx_harga_saham_ticker ON harga_saham(ticker);
CREATE INDEX IF NOT EXISTS idx_broker_summary_date ON broker_summary(date);
CREATE INDEX IF NOT EXISTS idx_broker_summary_ticker ON broker_summary(ticker);
