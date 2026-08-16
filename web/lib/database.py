import os
from sqlalchemy import create_engine, Column, String, Date, BigInteger, Integer, Float
from sqlalchemy.orm import sessionmaker, declarative_base
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")
if DATABASE_URL and DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

if DATABASE_URL:
    engine = create_engine(
        DATABASE_URL, 
        pool_pre_ping=True,  # Memeriksa koneksi sebelum digunakan
        pool_recycle=300     # Merecycle koneksi setiap 5 menit agar tidak stale di serverless
    )
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
else:
    engine = None
    SessionLocal = None

Base = declarative_base()

class Saham(Base):
    __tablename__ = 'daftar_saham'
    no = Column(Integer, nullable=True)
    kode = Column(String(10), primary_key=True, index=True)
    nama_perusahaan = Column(String(255), nullable=False)
    tanggal_pencatatan = Column(Date, nullable=True)
    saham = Column(BigInteger, nullable=True)
    papan_pencatatan = Column(String(50), nullable=True)
    tanggal_update = Column(Date, nullable=True)

class OpenPosition(Base):
    __tablename__ = 'open_positions'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    entry_date = Column(Date, nullable=False)
    entry_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    current_trailing_stop = Column(Float, nullable=False)
    last_updated = Column(Date, nullable=False)

class HargaSaham(Base):
    __tablename__ = 'harga_saham'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    tanggal = Column(Date, nullable=False, index=True)
    open = Column(Float, nullable=True)
    high = Column(Float, nullable=True)
    low = Column(Float, nullable=True)
    close = Column(Float, nullable=True)
    volume = Column(BigInteger, nullable=True)

class TradeHistory(Base):
    __tablename__ = 'trade_history'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    entry_date = Column(Date, nullable=False)
    entry_price = Column(Float, nullable=False)
    exit_date = Column(Date, nullable=False)
    exit_price = Column(Float, nullable=False)
    quantity = Column(Integer, nullable=False)
    profit_loss_percent = Column(Float, nullable=False)

class BrokerSummary(Base):
    __tablename__ = 'broker_summary'
    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String(10), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)
    broker_code = Column(String(5), nullable=False)
    buy_vol = Column(BigInteger, default=0)
    buy_val = Column(Float, default=0.0)
    buy_avg = Column(Float, default=0.0)
    sell_vol = Column(BigInteger, default=0)
    sell_val = Column(Float, default=0.0)
    sell_avg = Column(Float, default=0.0)
    net_vol = Column(BigInteger, default=0)
    net_val = Column(Float, default=0.0)

# Base.metadata.create_all(bind=engine) # Disabled on Serverless, worker handles creation

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
