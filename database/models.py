from sqlalchemy import Column, BigInteger, String, Integer
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)  # Telegram ID
    username = Column(String(32), nullable=True)
    nickname = Column(String(20), unique=True, nullable=False)
    coins = Column(Integer, default=0)
