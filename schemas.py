from pydantic import BaseModel, Field
from typing import Optional, List

class ChatMessage(BaseModel):
    sender_type: str  # "User" ou "Bot"
    step: str         # "start", "awaiting_name", "finished", "awaiting_purchase", etc.
    content: str      # O texto da mensagem

class ClientCache(BaseModel):
    id: Optional[int] = None
    name: str = ""
    num: str
    msg: List[ChatMessage] = []
    step: str = "start"

class ProductRecommendation(BaseModel):
    product_name: str = Field(description="Nome do produto correspondente no catálogo")
    supplier_name: str = Field(description="Nome da distribuidora ou fornecedor do produto")
    price: float = Field(description="Preço unitário do produto")
    match_percentage: int = Field(description="Porcentagem de relação/relevância com o pedido do cliente (0 a 100)")

class ProductRecommendationList(BaseModel):
    # Aceita tanto 'recommendations' quanto 'recommended_products' vindo da IA
    recommendations: List[ProductRecommendation] = Field(alias="recommended_products")

    class Config:
        populate_by_name = True