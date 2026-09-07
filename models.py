import enum
from datetime import datetime
from typing import List, Optional

from sqlalchemy import String, Integer, Float, DateTime, Text, ForeignKey,JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.ext.asyncio import AsyncAttrs

# 1. Base declarativa moderna (SQLAlchemy 2.0)
class Base(AsyncAttrs, DeclarativeBase):
    pass

# 2. Enum para as categorias dos fornecedores
class SupplierCategory(enum.Enum):
    ELETRONICOS = "Eletrônicos"
    BIJUTERIAS = "Bijuterias"
    LIVROS = "Livros"
    OUTROS = "Outros"

# 3. Modelos Independentes (Supplier e Product)
class Supplier(Base):
    __tablename__ = "supplier"

    sup_id: Mapped[int] = mapped_column(primary_key=True)
    sup_name: Mapped[str] = mapped_column(String(150))
    sup_category: Mapped[str] = mapped_column(String(50))
    sup_number: Mapped[str] = mapped_column(String(20))
    sup_email: Mapped[str] = mapped_column(String(150))
    
    # Nova coluna para armazenar a lista de tags (Ex: ["gamer", "escritório", "hardware"])
    sup_tags: Mapped[list[str]] = mapped_column(JSON, default=list)

    products: Mapped[List["Product"]] = relationship(back_populates="supplier", cascade="all, delete-orphan")
    sellers: Mapped[List["Seller"]] = relationship(back_populates="supplier")

class Product(Base):
    __tablename__ = "product"

    prod_id: Mapped[int] = mapped_column(primary_key=True)
    prod_name: Mapped[str] = mapped_column(String(150))
    prod_price: Mapped[float] = mapped_column()
    sup_id: Mapped[int] = mapped_column(ForeignKey("supplier.sup_id"))
    
    # Nova coluna: A tag específica do produto
    prod_tag: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)

    supplier: Mapped["Supplier"] = relationship(back_populates="products")
    purchases: Mapped[List["Purchase"]] = relationship(back_populates="product")

# 4. Estrutura de Herança (User -> Client, Seller)
class User(Base):
    __tablename__ = "user"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    user_name: Mapped[str] = mapped_column(String(150))
    user_number: Mapped[str] = mapped_column(String(20))
    
    # Coluna discriminadora para o SQLAlchemy saber qual é a subclasse correta
    user_type: Mapped[str] = mapped_column(String(30)) 

    __mapper_args__ = {
        "polymorphic_identity": "user",
        "polymorphic_on": "user_type",
    }


class Client(User):
    __tablename__ = "client"

    # Chave primária que também é FK para a tabela pai (User)
    client_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"), primary_key=True)
    client_last_op: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    client_content: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relacionamentos
    purchases: Mapped[List["Purchase"]] = relationship(back_populates="client")

    __mapper_args__ = {
        "polymorphic_identity": "client", # Valor que será salvo na coluna 'user_type'
    }


class Seller(User):
    __tablename__ = "seller"

    # Chave primária que também é FK para a tabela pai (User)
    seller_id: Mapped[int] = mapped_column(ForeignKey("user.user_id"), primary_key=True)
    token_id: Mapped[str] = mapped_column(String(255), unique=True)
    sup_id: Mapped[int] = mapped_column(ForeignKey("supplier.sup_id"))

    # Relacionamentos
    supplier: Mapped["Supplier"] = relationship(back_populates="sellers")

    __mapper_args__ = {
        "polymorphic_identity": "seller", # Valor que será salvo na coluna 'user_type'
    }


# 5. Tabela de Relacionamento/Transação (Purchase)
class Purchase(Base):
    __tablename__ = "purchase"

    pur_id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[int] = mapped_column(ForeignKey("client.client_id"))
    prod_id: Mapped[int] = mapped_column(ForeignKey("product.prod_id"))
    occurred_datetime: Mapped[datetime] = mapped_column(DateTime, default=datetime.now)

    # Relacionamentos
    client: Mapped["Client"] = relationship(back_populates="purchases")
    product: Mapped["Product"] = relationship(back_populates="purchases")