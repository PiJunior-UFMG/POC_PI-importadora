import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload

from models import Supplier, Product
from schemas import ProductRecommendation, ProductRecommendationList

load_dotenv()

# Cliente DeepSeek (compartilhado ou instanciado)
client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

prompt_context_path = os.path.join(os.path.dirname(__file__), "prompts", "message_context.txt")
with open(prompt_context_path, "r", encoding="utf-8") as f:
    PROMPT_CONTEXT_TEMPLATE = f.read()

prompt_tags_path = os.path.join(os.path.dirname(__file__), "prompts", "extract_tags.txt")
with open(prompt_tags_path, "r", encoding="utf-8") as f:
    PROMPT_TAGS_TEMPLATE = f.read()

prompt_rec_path = os.path.join(os.path.dirname(__file__), "prompts", "recommend_products.txt")
with open(prompt_rec_path, "r", encoding="utf-8") as f:
    PROMPT_RECOMMEND_TEMPLATE = f.read()

def get_message_context(mensagem: str) -> str:
    """Analisa a intenção geral da mensagem usando o DeepSeek."""
    formatted_prompt = PROMPT_CONTEXT_TEMPLATE.replace("{mensagem}", mensagem)
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Você é um classificador de intenções preciso e conciso."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=0.0,
            max_tokens=10
        )
        intencao = response.choices[0].message.content.strip().lower()
        categorias_validas = ["saudacao", "compra", "problema", "verificacao"]
        return intencao if intencao in categorias_validas else "saudacao"
    except Exception as e:
        print(f"Erro ao consultar o DeepSeek para triagem: {e}")
        return "saudacao"


def extract_product_tags(client_message: str, catalog_data: str) -> list:
    """
    Agente responsável por extrair as tags relevantes com base no pedido do cliente 
    e nos dados atuais do catálogo da distribuidora.
    """
    formatted_prompt = (
        PROMPT_TAGS_TEMPLATE
        .replace("{catalog_data}", catalog_data)
        .replace("{client_message}", client_message)
    )
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Você é um extrator de tags estruturadas em JSON."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=0.0,
            max_tokens=150
        )
        
        content = response.choices[0].message.content.strip()
        
        # Converte a resposta texto em uma lista Python válida
        tags_list = json.loads(content)
        if isinstance(tags_list, list):
            return tags_list
        return []
        
    except Exception as e:
        print(f"Erro ao extrair tags com o DeepSeek: {e}")
        return []

async def recommend_products(client_message: str, tags: list, db_session) -> list:
    """
    1. Faz a query no banco de dados filtrando pelos produtos que contêm as tags.
    2. Envia para o DeepSeek junto com a mensagem do cliente para pontuar a relevância.
    """

    if not tags:
        return []

    # Query no banco buscando produtos cujas tags ou categorias combinem com as extraídas
    # (Buscando em Product.prod_tag ou Supplier.sup_category/sup_tags)
    stmt = (
        select(Product)
        .join(Supplier)
        .options(selectinload(Product.supplier))
        .where(
            or_(*[Product.prod_tag.ilike(f"%{tag}%") for tag in tags] + 
                [Supplier.sup_category.ilike(f"%{tag}%") for tag in tags])
        )
    )
    result = await db_session.execute(stmt)
    products = result.scalars().all()

    if not products:
        # Se a busca exata por tags não retornar nada, pega uma listagem geral ou retorna vazio
        return []

    # Formata os produtos encontrados para o prompt da IA
    products_data = []
    for p in products:
        products_data.append({
            "id": p.prod_id,
            "name": p.prod_name,
            "price": p.prod_price,
            "supplier": p.supplier.sup_name if p.supplier else "Desconhecido",
            "category": p.supplier.sup_category if p.supplier else "",
            "tag": p.prod_tag
        })

    formatted_prompt = (
        PROMPT_RECOMMEND_TEMPLATE
        .replace("{client_message}", client_message)
        .replace("{extracted_tags}", str(tags))
        .replace("{products_from_db}", json.dumps(products_data, ensure_ascii=False))
    )

    try:
        # O DeepSeek / OpenAI API compatível aceita response_format para JSON estruturado
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Você é um recomendador de produtos que responde em JSON estruturado."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=0.0,
            response_format={"type": "json_object"} # Força o modelo a responder estritamente em JSON
        )
        
        content = response.choices[0].message.content
        data = json.loads(content)
        
        # Valida e converte usando o Pydantic do schemas.py
        validated_data = ProductRecommendationList(**data)
        return validated_data.recommendations[:10]
        
    except Exception as e:
        print(f"Erro ao recomendar produtos com IA: {e}")
        return []