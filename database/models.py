from sqlalchemy import Column, BigInteger, String, Integer, ForeignKey, Table
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()

class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, index=True)  # Telegram ID
    username = Column(String(32), nullable=True)
    nickname = Column(String(20), unique=True, nullable=False)
    coins = Column(Integer, default=0)
    pokeballs = Column(Integer, default=0)
    captures = Column(Integer, default=0)
    is_admin = Column(Integer, default=0)  # 0 = Not Admin, 1 = Admin

    # Relationship to inventory
    inventory = relationship("Inventory", back_populates="user")


class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    rarity = Column(String(20), nullable=False)

    # Relationship to inventory
    inventory = relationship("Inventory", back_populates="card")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False)
    quantity = Column(Integer, default=1)

    # Relationships
    user = relationship("User", back_populates="inventory")
    card = relationship("Card", back_populates="inventory")
