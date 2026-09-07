import os
import asyncio
from typing import Optional, Dict
from fastapi import APIRouter, Request, Response, Depends, BackgroundTasks
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from dotenv import load_dotenv
from sqlalchemy.orm import selectinload

# Imports do projeto
from database import get_db, AsyncSessionLocal
from models import Client as DBClient
from models import Supplier, Product
from agents import get_message_context, extract_product_tags, recommend_products
from schemas import ClientCache

router = APIRouter()

# configurações do twilio
load_dotenv()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.environ.get("TWILIO_NUMBER")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# configurações do cache
user_cache: Dict[str, ClientCache] = {}

def answer_message(body: str, cache: Optional[ClientCache] = None) -> Response:
    """
    Gera a resposta passiva (TwiML) para fechar a requisição HTTP atual.
    Uso: Respostas imediatas e confirmações de recebimento.
    """
    response = MessagingResponse()
    twiml_msg = response.message()
    twiml_msg.body(body)
    
    if cache is not None:
        if cache.msg:
            cache.msg += f"\nBot: {body}"
        else:
            cache.msg = f"Bot: {body}"
            
    return Response(content=str(response), media_type="application/xml")


def send_message(to_number: str, body: str, cache: Optional[ClientCache] = None):
    """
    Envia uma mensagem ativamente via API REST do Twilio.
    Uso: Background tasks, alertas, ou respostas processadas por IA após o TwiML.
    """
    try:
        twilio_client.messages.create(
            from_=TWILIO_NUMBER,
            body=body,
            to=to_number
        )
        
        # Atualiza o histórico no cache, se fornecido
        if cache is not None:
            if cache.msg:
                cache.msg += f"\nBot: {body}"
            else:
                cache.msg = f"Bot: {body}"
                
    except Exception as e:
        print(f"Erro ao enviar mensagem via REST para {to_number}: {e}")

async def manage_agent(sender_num: str, original_message: str, intention: str):
    """
    Gerencia o agente responsável com base na intenção já triada.
    """
    cache = user_cache.get(sender_num)
    
    if intention == "saudacao":
        if cache:
            cache.step = "finished"
        reply = "Olá! Como posso ajudar você hoje?" 
        
    elif intention == "compra":
        if cache:
            cache.step = "awaiting_purchase"
            
        # 1. Busca todo o catálogo bruto (ou resumo) para a primeira etapa de extração de tags
        catalog_info_str = ""
        async with AsyncSessionLocal() as db:
            from models import Supplier, Product
            from sqlalchemy.orm import selectinload
            
            stmt = select(Supplier).options(selectinload(Supplier.products))
            result = await db.execute(stmt)
            suppliers = result.scalars().all()
            
            catalog_lines = [
                f"Produto: {prod.prod_name} | Categoria: {sup.sup_category} | Tag: {prod.prod_tag or 'nenhuma'}"
                for sup in suppliers for prod in sup.products
            ]
            catalog_info_str = "\n".join(catalog_lines)

            # 2. Extrai as tags usando o agente de tags
            tags_encontradas = extract_product_tags(original_message, catalog_info_str)
            
            # 3. Roda o novo agente de recomendação passando a sessão do banco
            recomendacoes = await recommend_products(original_message, tags_encontradas, db)

        # 4. Formata a resposta para o WhatsApp com base nos produtos encontrados
        if recomendacoes:
            reply = "🛒 Encontrei estes produtos para o seu pedido:\n"
            for rec in recomendacoes:
                reply += f"\n• *{rec.product_name}* ({rec.supplier_name})\n  Preço: R$ {rec.price:.2f} — Relevância: {rec.match_percentage}%\n"
        else:
            reply = f"🛒 Analisei seu pedido, mas não encontrei produtos compatíveis com as tags: {tags_encontradas}"
        
    elif intention == "problema":
        if cache:
            cache.step = "finished"
        reply = "Certo, entendi seu problema! vou avisar a chefia"
        
    elif intention == "verificacao":
        if cache:
            cache.step = "finished"
        reply = "verifiquei e não encontrei nada!"
        
    else:
        reply = "Desculpe, não compreendi muito bem. Pode reformular?"

    # Envia a resposta ativamente pelo Twilio REST
    send_message(to_number=sender_num, body=reply, cache=cache)

@router.post("")
async def whatsapp_bot(
    request: Request, 
    background_tasks: BackgroundTasks, 
    db: AsyncSession = Depends(get_db)
):
    form_data = await request.form()
    original_message = form_data.get('Body', '').strip()
    lower_message = original_message.lower()
    sender = form_data.get('From', '')
    
    # --- COMANDOS ESPECIAIS ---
    if lower_message == '#reset':
        user_cache.pop(sender, None)
        return answer_message("🔄 O seu cache de estado foi resetado.", None)
        
    elif lower_message.startswith('#del '):
        name_to_delete = original_message[5:].strip()
        stmt = select(DBClient).where(DBClient.user_name.ilike(name_to_delete))
        result = await db.execute(stmt)
        db_client = result.scalars().first()
        
        if db_client:
            if db_client.user_number in user_cache:
                user_cache.pop(db_client.user_number, None)
            await db.delete(db_client)
            await db.commit()
            return answer_message(f"🗑️ O cliente '{db_client.user_name}' foi apagado.", None)
        return answer_message(f"⚠️ Cliente não encontrado.", None)

    # --- LÓGICA DE ESTADOS / AUTENTICAÇÃO ---
    cache = user_cache.get(sender)
    
    if not cache:
        stmt = select(DBClient).where(DBClient.user_number == sender)
        result = await db.execute(stmt)
        existing_client = result.scalars().first()
        
        if existing_client:
            cache = ClientCache(
                id=existing_client.client_id, 
                name=existing_client.user_name,
                num=existing_client.user_number,
                step="finished"
            )
            user_cache[sender] = cache
        else:
            cache = ClientCache(num=sender, step="awaiting_name")
            user_cache[sender] = cache
            return answer_message("Olá! Sou o assistente virtual da distribuidora. Para começarmos, qual é o seu nome?", cache)
            
    # Salva a mensagem do usuário no histórico
    if cache.msg:
        cache.msg += f"\nUser: {original_message}"
    else:
        cache.msg = f"User: {original_message}"
    
    # --- ROTEAMENTO DO FLUXO ---
    if cache.step == 'awaiting_name':
        client_name = original_message.title()
        
        new_client = DBClient(user_name=client_name, user_number=sender)
        db.add(new_client)
        await db.commit()
        
        cache.id = new_client.client_id
        cache.name = client_name
        cache.step = 'finished'
        
        return answer_message(f"Prazer, {cache.name}! Seu cadastro foi feito. ✅\nComo posso ajudar?", cache)
        
    elif cache.step == 'finished' or cache.step == 'awaiting_purchase':
        # 1. Identifica a intenção de forma instantânea via Regex (agents.py)
        intention = get_message_context(original_message)
        
        # 2. Lista de intenções que exigem processamento pesado (DB / IA)
        heavy_intentions = ["compra", "problema"]
        
        if intention in heavy_intentions:
            if intention == "compra":
                holding_msg = "⏳ Entendi que deseja fazer um pedido. Vou buscar os produtos disponíveis no banco de dados, só um instante..."
            elif intention == "problema":
                holding_msg = "⏳ Compreendi que há um problema. Vou registrar os detalhes e notificar a equipe, um momento..."
            else:
                holding_msg = "⏳ Processando sua solicitação no sistema..."
            
            # Aciona o gerenciador de agentes em segundo plano
            background_tasks.add_task(manage_agent, sender, original_message, intention)
            
            # Responde rápido ao webhook com o aviso contextual
            return answer_message(holding_msg, cache)

        # mensagens que são mais leves de processar (envio rápido)
        else:           
            if intention == "saudacao":
                reply = "Olá! Como posso ajudar você hoje?"
            elif intention == "verificacao":
                reply = "Verifiquei e não encontrei registros recentes por aqui."
            else:
                reply = "Desculpe, não compreendi muito bem. Poderia reformular?"
                
            # Retorna a resposta direta imediatamente
            return answer_message(reply, cache)   
    
    return answer_message("Desculpe, ocorreu um erro de contexto.", cache)