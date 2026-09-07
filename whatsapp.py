from typing import Optional, Dict
from fastapi import APIRouter, Request, Response, Depends
from twilio.twiml.messaging_response import MessagingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel

from database import get_db
from models import Client 

router = APIRouter()

# essa é a estrutura de dados base do nosso cache
class ClientCache(BaseModel):
    id: Optional[int] = None
    name: str = ""
    num: str
    msg: str = "" # últimas mensagens
    step: str = "start" # momento da conversa

user_cache: Dict[str, ClientCache] = {}

# ==========================================
# FUNÇÃO AUXILIAR DE MENSAGENS
# ==========================================
def send_message(body: str, cache: Optional[ClientCache] = None) -> Response:
    """
    Constrói a resposta XML para o Twilio e salva a fala do bot no histórico de mensagens.
    """
    response = MessagingResponse()
    twiml_msg = response.message()
    twiml_msg.body(body)
    
    # Se o cache existe, registra a resposta do bot para manter o contexto da LLM rico
    if cache is not None:
        if cache.msg:
            cache.msg += f"\nBot: {body}"
        else:
            cache.msg = f"Bot: {body}"
            
    return Response(content=str(response), media_type="application/xml")

@router.post("")
async def whatsapp_bot(request: Request, db: AsyncSession = Depends(get_db)):
    form_data = await request.form()
    
    original_message = form_data.get('Body', '').strip()
    lower_message = original_message.lower()
    sender = form_data.get('From', '')
    
    # ==========================================
    # SPECIAL COMMANDS 
    # ==========================================
    if lower_message == '#reset':
        user_cache.pop(sender, None)
        return send_message("🔄 O seu cache de estado foi resetado.", None)
        
    elif lower_message.startswith('#del '):
        name_to_delete = original_message[5:].strip()
        
        stmt = select(Client).where(Client.user_name.ilike(name_to_delete))
        result = await db.execute(stmt)
        db_client = result.scalars().first()
        
        if db_client:
            if db_client.user_number in user_cache:
                user_cache.pop(db_client.user_number, None)
                
            await db.delete(db_client)
            await db.commit()
            return send_message(f"🗑️ O cliente '{db_client.user_name}' foi apagado do banco de dados.", None)
        else:
            return send_message(f"⚠️ Cliente '{name_to_delete}' não encontrado no banco de dados.", None)

    # ==========================================
    # CHATBOT STATE LOGIC
    # ==========================================
    
    cache = user_cache.get(sender)
    
    if not cache:
        stmt = select(Client).where(Client.user_number == sender)
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
            
            return send_message(
                "Olá! Sou o assistente virtual da distribuidora. Para começarmos, qual é o seu nome?", 
                cache
            )
            
    
    # Atualiza o histórico com o que o usuário acabou de digitar
    if cache.msg:
        cache.msg += f"\nUser: {original_message}"
    else:
        cache.msg = f"User: {original_message}"

    # TODO: preciso validar a mensagem antes de adicionar no db (ex: Meu nome é Gabriel)
    if cache.step == 'awaiting_name':
        client_name = original_message.title()
        
        new_client = Client(
            user_name=client_name,
            user_number=sender
        )
        db.add(new_client)
        await db.commit()
        
        cache.id = new_client.client_id
        cache.name = client_name
        cache.step = 'finished'
        
        reply_text = (
            f"Prazer, {cache.name}! Seu cadastro foi realizado com sucesso. ✅\n\n"
            "Por enquanto, minhas funcionalidades são:\n"
            "📦 Consultar catálogo de produtos\n"
            "🛒 Realizar compras\n\n"
            "(Mais opções serão adicionadas no futuro!)"
        )
        return send_message(reply_text, cache)
        
    elif cache.step == 'finished':
        reply_text = (
            f"Você já está em nossa base, {cache.name}! Aqui estão minhas funcionalidades atuais:\n"
            "📦 Consultar catálogo de produtos\n"
            "🛒 Realizar compras\n\n"
            "Como posso te ajudar agora?"
        )
        return send_message(reply_text, cache)
        
    # Retorno de segurança caso o state não seja mapeado
    return send_message("Desculpe, ocorreu um erro de contexto. Tente novamente.", cache)