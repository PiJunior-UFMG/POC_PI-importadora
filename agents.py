import os
import json
from openai import OpenAI
from dotenv import load_dotenv
from sqlalchemy import select, or_
from sqlalchemy.orm import selectinload
from typing import Optional

from models import Supplier, Product
from schemas import ProductRecommendation, ProductRecommendationList, FeedbackResult
from logger import log_agent_usage

load_dotenv()

# Cliente DeepSeek (compartilhado ou instanciado)
client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

def get_message_context(mensagem: str, prompt_filename: str, valid_categories: list) -> str:
    """
    Analisa a intenção da mensagem usando um prompt específico passado por parâmetro 
    e valida o resultado contra as categorias permitidas.
    """
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", prompt_filename)
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()
        
    formatted_prompt = template.replace("{mensagem}", mensagem)
    
    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Você é um classificador de intenções preciso e conciso."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=0.0,
            max_tokens=30
        )
        intencao = response.choices[0].message.content.strip().lower()

        if response.usage:
            log_agent_usage(
                agent_name="get_message_context", 
                prompt_tokens=response.usage.prompt_tokens, 
                completion_tokens=response.usage.completion_tokens
            )
        # Retorna a intenção se for válida para este contexto, senão pega a primeira da lista como fallback
        return intencao if intencao in valid_categories else valid_categories[0]
        
    except Exception as e:
        print(f"Erro ao consultar o DeepSeek para triagem contextual ({prompt_filename}): {e}")
        return valid_categories[0]

def extract_product_tags(client_message: str, catalog_data: str, client_summary: str = "") -> list:
    """
    Agente responsável por extrair as tags relevantes com base no pedido do cliente 
    e nos dados atuais do catálogo da distribuidora.
    """
    # Se o resumo for vazio, garante que a IA não se confunda
    summary_text = client_summary if client_summary else "Sem histórico recente."

    prompt_tags_path = os.path.join(os.path.dirname(__file__), "prompts", "extract_tags.txt")
    with open(prompt_tags_path, "r", encoding="utf-8") as f:
        PROMPT_TAGS_TEMPLATE = f.read()

    formatted_prompt = (
        PROMPT_TAGS_TEMPLATE
        .replace("{catalog_data}", catalog_data)
        .replace("{client_message}", client_message)
        .replace("{client_summary}", summary_text)
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

        if response.usage:
            log_agent_usage(
                agent_name="extract_product_tags", 
                prompt_tokens=response.usage.prompt_tokens, 
                completion_tokens=response.usage.completion_tokens
            )
        # Converte a resposta texto em uma lista Python válida
        tags_list = json.loads(content)
        if isinstance(tags_list, list):
            return tags_list
        return []
        
    except Exception as e:
        print(f"Erro ao extrair tags com o DeepSeek: {e}")
        return []

async def recommend_products(
    client_message: str, 
    tags: list, 
    db_session, 
    previously_suggested: list = None,
    client_summary: str = ""
) -> list:
    """
    Faz a busca no banco usando as tags e aciona a IA para ranquear os produtos,
    levando em consideração o histórico do cliente e o que já foi oferecido na sessão.
    """

    if tags:
        stmt = (
            select(Product)
            .join(Supplier)
            .options(selectinload(Product.supplier))
            .where(
                or_(*[Product.prod_tag.ilike(f"%{tag}%") for tag in tags] + 
                    [Supplier.sup_category.ilike(f"%{tag}%") for tag in tags])
            )
        )
    else:
        # Se a mensagem foi ampla (ex: "me recomende algo"), trazemos um lote geral
        # e deixamos a IA escolher as melhores opções baseada no client_summary!
        stmt = (
            select(Product)
            .join(Supplier)
            .options(selectinload(Product.supplier))
            .limit(40) # Ajuste o limite conforme o tamanho real do seu catálogo
        )

    result = await db_session.execute(stmt)
    products = result.scalars().all()

    if not products:
        return []

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

    # Tratamento dos contextos opcionais para evitar variáveis nulas no prompt
    prev_sug_str = json.dumps(previously_suggested, ensure_ascii=False) if previously_suggested else "[]"
    summary_str = client_summary if client_summary else "Cliente sem histórico registrado."

    prompt_tags_path = os.path.join(os.path.dirname(__file__), "prompts", "recommend_products.txt")
    with open(prompt_tags_path, "r", encoding="utf-8") as f:
        PROMPT_RECOMMEND_TEMPLATE = f.read()

    formatted_prompt = (
        PROMPT_RECOMMEND_TEMPLATE
        .replace("{client_message}", client_message)
        .replace("{extracted_tags}", str(tags))
        .replace("{client_summary}", summary_str)
        .replace("{previously_suggested}", prev_sug_str)
        .replace("{products_from_db}", json.dumps(products_data, ensure_ascii=False))
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Você é um recomendador de produtos inteligente que responde em JSON estruturado."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=0.2, # Ligeiramente maior que 0 para permitir certa criatividade nas alternativas
            response_format={"type": "json_object"} 
        )

        if response.usage:
            log_agent_usage(
                agent_name="recommend_products", 
                prompt_tokens=response.usage.prompt_tokens, 
                completion_tokens=response.usage.completion_tokens
            )

        content = response.choices[0].message.content
        data = json.loads(content)
        validated_data = ProductRecommendationList(**data)
        
        return validated_data.recommendations[:10]
        
    except Exception as e:
        print(f"Erro ao recomendar produtos com IA: {e}")
        return []
    
async def summary_messages(client_messages: list, target_step: Optional[str] = None) -> str:
    """
    Resgata o histórico de mensagens e faz um resumo objetivo.
    Se target_step for informado, restringe o resumo apenas àquele passo específico.
    """
    # Filtra as mensagens se um step específico foi solicitado
    if target_step:
        filtered_msgs = [m for m in client_messages if m.step == target_step]
        filter_instruction = f"Restrinja o resumo estritamente aos acontecimentos e diálogos do step: '{target_step}'."
    else:
        filtered_msgs = client_messages
        filter_instruction = "Faça um resumo geral de toda a conversa."

    if not filtered_msgs:
        return "Não há histórico de mensagens registrado para este critério."

    # Formata o histórico para o prompt
    formatted_history = "\n".join(
        f"[{m.sender_type}][Step: {m.step}]: {m.content}" for m in filtered_msgs
    )

    # Carrega o prompt do arquivo externo
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "summary_messages.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    formatted_prompt = (
        template
        .replace("{chat_history}", formatted_history)
        .replace("{filter_instruction}", filter_instruction)
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Você é um assistente analítico especializado em resumos de atendimento."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=0.2,
            max_tokens=300
        )
        if response.usage:
            log_agent_usage(
                agent_name="summary_messages", 
                prompt_tokens=response.usage.prompt_tokens, 
                completion_tokens=response.usage.completion_tokens
            )
        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"Erro ao gerar resumo de mensagens: {e}")
        return "Desculpe, ocorreu um erro ao gerar o resumo das mensagens."

def confirm_purchase(client_message: str, suggested_products: list) -> list:
    """Extrai os IDs dos produtos selecionados pelo cliente na confirmação."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "confirm_purchase.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    formatted_prompt = template.replace(
        "{suggested_products}", json.dumps(suggested_products, ensure_ascii=False)
    ).replace(
        "{client_message}", client_message
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Você é um extrator JSON de IDs de produtos."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=0.0,
            max_tokens=50
        )
        
        if response.usage:
            log_agent_usage(
                agent_name="confirm_purchase", 
                prompt_tokens=response.usage.prompt_tokens, 
                completion_tokens=response.usage.completion_tokens
            )
        
        content = response.choices[0].message.content.strip()
        ids = json.loads(content)
        return ids if isinstance(ids, list) else []
    except Exception as e:
        print(f"Erro ao confirmar compra com IA: {e}")
        return []

async def generate_proactive_greeting(client_message: str, client_name: str, client_summary: str, catalog_data: str) -> str:
    """Gera uma saudação inteligente cruzando o catálogo com o histórico do cliente."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "proactive_greeting.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    summary_str = client_summary if client_summary else "Cliente novo, sem histórico recente."

    formatted_prompt = (
        template
        .replace("{client_message}", client_message)
        .replace("{client_name}", client_name)
        .replace("{client_summary}", summary_str)
        .replace("{catalog_data}", catalog_data)
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Você é um vendedor proativo e amigável especializado em WhatsApp."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=0.4, # Um pouco mais alto para permitir criatividade nas sugestões
            max_tokens=250
        )
        
        # --- REGISTRO DE LOG ---
        if response.usage:
            from logger import log_agent_usage
            log_agent_usage(
                agent_name="proactive_greeting", 
                prompt_tokens=response.usage.prompt_tokens, 
                completion_tokens=response.usage.completion_tokens
            )

        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"Erro ao gerar saudação proativa com IA: {e}")
        return f"Olá, {client_name}! Como posso ajudar você hoje?"

async def resolve_client_problem(client_message: str, client_name: str, client_summary: str, catalog_data: str) -> str:
    """Gera uma resposta empática sugerindo soluções ou contatos para problemas."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "problem_resolver.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    summary_str = client_summary if client_summary else "Sem histórico de compras recente."

    formatted_prompt = (
        template
        .replace("{client_message}", client_message)
        .replace("{client_name}", client_name)
        .replace("{client_summary}", summary_str)
        .replace("{catalog_data}", catalog_data)
    )

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Você é um especialista em suporte técnico e atendimento humanizado via WhatsApp."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=0.3, # Baixa temperatura para não inventar telefones ou dados que não existem
            max_tokens=300
        )
        
        # --- REGISTRO DE LOG ---
        if response.usage:
            from logger import log_agent_usage
            log_agent_usage(
                agent_name="resolve_problem", 
                prompt_tokens=response.usage.prompt_tokens, 
                completion_tokens=response.usage.completion_tokens
            )

        return response.choices[0].message.content.strip()
        
    except Exception as e:
        print(f"Erro ao gerar resolução de problema com IA: {e}")
        return "Sinto muito pelo transtorno. Houve um erro no meu sistema, mas nossa equipe humana entrará em contato em breve para ajudar você."

async def extract_feedback_metrics(client_message: str) -> dict:
    """Extrai CSAT e NPS de uma mensagem de feedback em linguagem natural."""
    prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "extract_feedback.txt")
    with open(prompt_path, "r", encoding="utf-8") as f:
        template = f.read()

    formatted_prompt = template.replace("{client_message}", client_message)

    try:
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Você é um classificador JSON especializado em métricas de satisfação (NPS/CSAT)."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=0.1,
            response_format={"type": "json_object"}
        )
        
        # --- REGISTRO DE LOG ---
        if response.usage:
            from logger import log_agent_usage
            log_agent_usage(
                agent_name="extract_feedback", 
                prompt_tokens=response.usage.prompt_tokens, 
                completion_tokens=response.usage.completion_tokens
            )

        content = response.choices[0].message.content
        data = json.loads(content)
        validated_data = FeedbackResult(**data)
        
        return validated_data.model_dump()
        
    except Exception as e:
        print(f"Erro ao extrair feedback com IA: {e}")
        return {"nps_score": 0, "csat_score": 0, "summary": "Erro ao processar feedback."}