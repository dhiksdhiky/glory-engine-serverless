CREATE TABLE IF NOT EXISTS stocks_daily (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    open NUMERIC,
    high NUMERIC,
    low NUMERIC,
    close NUMERIC,
    volume BIGINT,
    UNIQUE(ticker, date)
);

CREATE TABLE IF NOT EXISTS broker_summary (
    id SERIAL PRIMARY KEY,
    ticker VARCHAR(10) NOT NULL,
    date DATE NOT NULL,
    broker VARCHAR(5),
    buy_vol BIGINT,
    buy_val NUMERIC,
    sell_vol BIGINT,
    sell_val NUMERIC,
    UNIQUE(ticker, date, broker)
);

-- Indexing untuk mempercepat query PWA
CREATE INDEX IF NOT EXISTS idx_stocks_date ON stocks_daily(date);
CREATE INDEX IF NOT EXISTS idx_broker_date ON broker_summary(date);
