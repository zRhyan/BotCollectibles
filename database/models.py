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
    is_admin = Column(Integer, default=0)  # 0 = Not Admin, 1 = Admin

    # Relationship to inventory
    inventory = relationship("Inventory", back_populates="user")
    marketplace_listings = relationship("Marketplace", back_populates="seller")

    @property
    def captures(self):
        """
        Dynamically calculate the total captures for the user.
        This is the sum of all card quantities in the user's inventory.
        """
        return sum(item.quantity for item in self.inventory)

class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)

    # Relationship to groups
    groups = relationship("Group", back_populates="category")


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)

    # Relationships
    category = relationship("Category", back_populates="groups")
    cards = relationship("Card", back_populates="group")


class Tag(Base):
    __tablename__ = "tags"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False, unique=True)

    # Relationship to cards
    cards = relationship("Card", secondary="card_tags", back_populates="tags")


# Association table for many-to-many relationship between Card and Tag
card_tags = Table(
    "card_tags",
    Base.metadata,
    Column("card_id", Integer, ForeignKey("cards.id"), primary_key=True),
    Column("tag_id", Integer, ForeignKey("tags.id"), primary_key=True),
)

class Card(Base):
    __tablename__ = "cards"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(50), nullable=False)
    rarity = Column(String(10), nullable=False)  # Adjusted length for emojis
    image_file_id = Column(String(255), nullable=False)
    group_id = Column(Integer, ForeignKey("groups.id"), nullable=False)

    # Relationships
    inventory = relationship("Inventory", back_populates="card")
    group = relationship("Group", back_populates="cards")
    tags = relationship("Tag", secondary="card_tags", back_populates="cards")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False)
    quantity = Column(Integer, default=1)

    # Relationships
    user = relationship("User", back_populates="inventory")
    card = relationship("Card", back_populates="inventory")

class Marketplace(Base):
    __tablename__ = "marketplace"

    id = Column(Integer, primary_key=True, autoincrement=True)
    seller_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    card_id = Column(Integer, ForeignKey("cards.id"), nullable=False)
    price = Column(Integer, nullable=False)

    # Relationships
    seller = relationship("User", back_populates="marketplace_listings")
    card = relationship("Card")


