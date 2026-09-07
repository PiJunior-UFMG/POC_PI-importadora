import os
import asyncio
from typing import Optional, Dict
from fastapi import APIRouter, Request, Response, Depends, BackgroundTasks
from twilio.twiml.messaging_response import MessagingResponse
from twilio.rest import Client
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from dotenv import load_dotenv

# Imports do seu projeto
from database import get_db, AsyncSessionLocal
from models import Client as DBClient 

router = APIRouter()

# configurações do twilio
load_dotenv()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.environ.get("TWILIO_NUMBER")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# configurações do cache
class ClientCache(BaseModel):
    id: Optional[int] = None
    name: str = ""
    num: str
    msg: str = ""
    step: str = "start"

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

async def get_message_context(sender_num: str, original_message: str):
    """
    Função abstraída que será expandida com IA e NLP futuramente.
    """
    # 1. Simula o tempo de chamada para a LLM
    await asyncio.sleep(4) 
    
    # 2. Busca de dados no banco (se necessário)
    async with AsyncSessionLocal() as db:
        # stmt = select(Product)...
        pass
    
    resposta_da_ia = f"✅ Análise concluída! Processei a sua mensagem: '{original_message}' e consultei o estoque."
    
    # 3. Usa a função abstraída send_message
    cache = user_cache.get(sender_num)
    send_message(to_number=sender_num, body=resposta_da_ia, cache=cache)

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
        
    elif cache.step == 'finished':
        # Delega o processamento pesado e envia resposta rápida
        background_tasks.add_task(get_message_context, sender, original_message)
        return answer_message("⏳ Entendi! Vou processar o seu pedido, só um instante...", cache)
        
    return answer_message("Desculpe, ocorreu um erro de contexto.", cache)