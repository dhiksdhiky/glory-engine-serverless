"""
models.py — SQLAlchemy ORM Models
==================================
Definisi tabel untuk broker_summary dan bot_error_logs.
Tabel harga_saham & daftar_saham dibuat via raw SQL di db_config.py
karena pipeline menggunakan raw SQL untuk bulk operations.
"""

from sqlalchemy import Column, String, Date, BigInteger, Float, Integer, DateTime, Text
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


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


class BotErrorLog(Base):
    __tablename__ = 'bot_error_logs'

    id = Column(Integer, primary_key=True, autoincrement=True)
    bot_name = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    error_level = Column(String(20), nullable=False)
    ticker = Column(String(10), nullable=True)
    error_message = Column(String(255), nullable=False)
    traceback = Column(Text, nullable=True)
