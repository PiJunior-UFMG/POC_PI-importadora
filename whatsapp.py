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
from models import Supplier, Product,Purchase
from agents import get_message_context, extract_product_tags, recommend_products, summary_messages,confirm_purchase,generate_proactive_greeting, resolve_client_problem, extract_feedback_metrics
from schemas import ClientCache, ChatMessage

router = APIRouter()

# configurações do twilio
load_dotenv()
TWILIO_ACCOUNT_SID = os.environ.get("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.environ.get("TWILIO_AUTH_TOKEN")
TWILIO_NUMBER = os.environ.get("TWILIO_NUMBER")

twilio_client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)

# configurações do cache
user_cache: Dict[str, ClientCache] = {}

def add_to_history(cache: ClientCache, sender_type: str, content: str):
    """Adiciona uma mensagem estruturada ao histórico do cache do cliente."""
    cache.messages.append(ChatMessage(
        sender_type=sender_type,
        step=cache.step,
        content=content
    ))

async def update_client_summary(cache: ClientCache, db: Optional[AsyncSession] = None):
    """Gera o resumo geral do histórico de mensagens e atualiza o client_content no banco de dados."""
    if cache.id:
        resumo_geral = await summary_messages(cache.messages)
        
        if db:
            db_client = await db.get(DBClient, cache.id)
            if db_client:
                db_client.client_content = resumo_geral
                await db.commit()
        else:
            async with AsyncSessionLocal() as session:
                db_client = await session.get(DBClient, cache.id)
                if db_client:
                    db_client.client_content = resumo_geral
                    await session.commit()

def answer_message(body: str, cache: Optional[ClientCache] = None) -> Response:
    """
    Gera a resposta passiva (TwiML) para fechar a requisição HTTP atual.
    Uso: Respostas imediatas e confirmações de recebimento.
    """
    response = MessagingResponse()
    twiml_msg = response.message()
    twiml_msg.body(body)
    
    if cache is not None:
        add_to_history(cache, "Bot", body)
            
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
        
        if cache is not None:
            add_to_history(cache, "Bot", body)
                
    except Exception as e:
        print(f"Erro ao enviar mensagem via REST para {to_number}: {e}")

async def manage_agent(sender_num: str, original_message: str, intention: str):
    """
    Papel exclusivo: Despachar a execução para o agente de IA/DB responsável.
    """
    cache = user_cache.get(sender_num)
    
    if intention == "compra":
        async with AsyncSessionLocal() as db:
            from models import Supplier, Product, Client as DBClient
            from sqlalchemy.orm import selectinload
            from sqlalchemy import select
            
            # 1. Resgata o resumo histórico do cliente logo de cara
            client_summary = ""
            if cache and cache.id:
                db_client = await db.get(DBClient, cache.id)
                if db_client and db_client.client_content:
                    client_summary = db_client.client_content

            # 2. Busca catálogo geral
            stmt = select(Supplier).options(selectinload(Supplier.products))
            result = await db.execute(stmt)
            suppliers = result.scalars().all()
            
            catalog_lines = [
                f"Produto: {prod.prod_name} | Categoria: {sup.sup_category} | Tag: {prod.prod_tag or 'nenhuma'}"
                for sup in suppliers for prod in sup.products
            ]
            catalog_info_str = "\n".join(catalog_lines)

            # 3. Extrai tags COM O CONTEXTO DO HISTÓRICO
            tags_encontradas = extract_product_tags(original_message, catalog_info_str, client_summary)
            
            previously_suggested = cache.suggested_products if cache else []
            
            # 4. Chama a recomendação
            recomendacoes = await recommend_products(
                client_message=original_message, 
                tags=tags_encontradas, 
                db_session=db,
                previously_suggested=previously_suggested,
                client_summary=client_summary
            )

        if recomendacoes:
            if cache:
                cache.suggested_products.extend([rec.model_dump() for rec in recomendacoes])

            reply = "🛒 Encontrei estas novas opções para o seu pedido:\n"
            for rec in recomendacoes:
                reply += f"\n• *{rec.product_name}* ({rec.supplier_name})\n  Preço: R$ {rec.price:.2f} — Relevância: {rec.match_percentage}%\n"
            reply += "\n_Deseja confirmar algum item, ver outras opções ou cancelar?_"
        else:
            texto_tags = ", ".join(tags_encontradas) if tags_encontradas else "sugestões gerais"
            reply = f"🛒 Analisei seu pedido, mas não encontrei novos produtos compatíveis com: {texto_tags}"
            if cache:
                cache.step = "finished"

        await update_client_summary(cache, db)

    elif intention == "saudacao":
        async with AsyncSessionLocal() as db:
            from models import Supplier, Product, Client as DBClient
            from sqlalchemy.orm import selectinload
            from sqlalchemy import select
            
            # 1. Resgata informações básicas e histórico do cliente
            db_client = await db.get(DBClient, cache.id) if cache and cache.id else None
            client_summary = db_client.client_content if db_client and db_client.client_content else ""
            client_name = db_client.user_name if db_client else "Cliente"

            # 2. Gera um cardápio rápido para a IA usar nas sugestões
            stmt = select(Supplier).options(selectinload(Supplier.products))
            result = await db.execute(stmt)
            suppliers = result.scalars().all()
            
            catalog_lines = [
                f"Produto: {prod.prod_name} | Preço: R${prod.prod_price:.2f} | Tag: {prod.prod_tag or ''}"
                for sup in suppliers for prod in sup.products
            ]
            catalog_info_str = "\n".join(catalog_lines)

            # 3. Executa o Agente
            reply = await generate_proactive_greeting(
                client_message=original_message, 
                client_name=client_name, 
                client_summary=client_summary, 
                catalog_data=catalog_info_str
            )

        if cache:
            cache.step = "finished"
            await update_client_summary(cache, db)

    elif intention == "problema":
        async with AsyncSessionLocal() as db:
            
            # 1. Resgata informações básicas e histórico (para a IA saber o que ele comprou antes)
            db_client = await db.get(DBClient, cache.id) if cache and cache.id else None
            client_summary = db_client.client_content if db_client and db_client.client_content else ""
            client_name = db_client.user_name if db_client else "Cliente"

            # 2. Gera um mapa completo de Produtos E Contatos dos fornecedores
            stmt = select(Supplier).options(selectinload(Supplier.products))
            result = await db.execute(stmt)
            suppliers = result.scalars().all()
            
            catalog_lines = []
            for sup in suppliers:
                # Usa os campos de contato da sua model (ajuste se os nomes das colunas forem diferentes)
                contato = getattr(sup, 'sup_number', 'Contato indisponível') 
                email = getattr(sup, 'sup_email', 'Email indisponível')
                
                catalog_lines.append(f"Distribuidora: {sup.sup_name} | Tel: {contato} | Email: {email}")
                for prod in sup.products:
                    catalog_lines.append(f"  - Produto: {prod.prod_name} | Preço: R${prod.prod_price:.2f} | Tag: {prod.prod_tag or ''}")

            catalog_info_str = "\n".join(catalog_lines)

            # 3. Executa o Agente de Resolução
            reply = await resolve_client_problem(
                client_message=original_message, 
                client_name=client_name, 
                client_summary=client_summary, 
                catalog_data=catalog_info_str
            )

    elif intention == "feedback":
        async with AsyncSessionLocal() as db:
            from models import Client as DBClient
            
            # 1. Aciona o agente para traduzir a mensagem em notas
            feedback_data = await extract_feedback_metrics(original_message)
            
            # 2. Salva as notas no banco de dados do cliente
            if cache and cache.id:
                db_client = await db.get(DBClient, cache.id)
                if db_client:
                    db_client.nps_score = feedback_data["nps_score"]
                    db_client.csat_score = feedback_data["csat_score"]
                    db_client.last_feedback = feedback_data["summary"]
                    await db.commit()
            
            # 3. Prepara a mensagem de agradecimento
            if feedback_data["nps_score"] >= 9:
                reply = "Que notícia maravilhosa! 😍 Muito obrigado pela confiança de sempre. Até a próxima compra!"
            elif feedback_data["nps_score"] >= 7:
                reply = "Muito obrigado pelo seu retorno! Vamos continuar trabalhando para entregar uma experiência nota 10 na próxima vez. 🚀"
            else:
                reply = "Agradeço a sinceridade. Peço desculpas se a experiência não foi ideal, registrei seu comentário para melhorarmos! 🤝"
            
            # 4. Finaliza a sessão e consolida o resumo geral
            if cache:
                cache.step = "finished"
                # Aqui aproveitamos para atualizar o client_content (histórico) incluindo a compra + o feedback
                await update_client_summary(cache, db)

        if cache:
            # Mantém em estado finalizado, permitindo que a próxima mensagem inicie um fluxo normal
            cache.step = "finished"
    else:
        reply = "Processamento concluído."

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

    cache = user_cache.get(sender)
    
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

    elif lower_message.startswith("#ch "):
        if not cache:
            return answer_message("⚠️ Nenhum cache ativo encontrado para alterar o step.")
        new_step = original_message[4:].strip()
        old_step = cache.step
        cache.step = new_step
        return answer_message(f"🔄 old_step: {old_step}, new_step: {new_step}", cache)
    
    # --- LÓGICA DE ESTADOS / AUTENTICAÇÃO ---
    
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
            add_to_history(cache, "User", original_message)
            return answer_message("Olá! Sou o assistente virtual da distribuidora. Para começarmos, qual é o seu nome?", cache)
            
    add_to_history(cache, "User", original_message)
    
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
        
    # --- ESTADO DE COMPRA EM ANDAMENTO ---
    elif cache.step == 'awaiting_purchase':
        msg_lower = original_message.lower()
        
        # 1. FORÇAR CONFIRMAÇÃO: Se o usuário expressar claramente que quer fechar/levar itens
        palavras_confirmacao = ["confirmar", "confirmo", "vou levar", "quero a", "quero o", "fechar", "pode fechar", "comprar"]
        
        if any(term in msg_lower for term in palavras_confirmacao):
            sub_intention = "confirmar"
        # 2. FORÇAR BUSCA/SUGESTÃO: Se ele estiver pedindo mais opções ou preço
        elif any(term in msg_lower for term in ["barata", "barato", "outro", "outra", "mais", "sugest", "procur", "ver", "opções"]):
            sub_intention = "sugestoes"
        else:
            # Caso seja ambíguo, recorre ao classificador de IA
            sub_intention = get_message_context(
                original_message, 
                "message_context_purchase.txt", 
                ["confirmar", "cancelar", "sugestoes", "continuار_busca"]
            )
        
        if sub_intention == "confirmar":
            selected_ids = confirm_purchase(original_message, cache.suggested_products)
            
            if not selected_ids:
                return answer_message("Não consegui identificar qual produto você escolheu. Pode me confirmar o nome exato?", cache)
            
            stmt = select(Product).options(selectinload(Product.supplier)).where(Product.prod_id.in_(selected_ids))
            result = await db.execute(stmt)
            purchased_prods = result.scalars().all()
            
            if not purchased_prods:
                return answer_message("Houve um problema ao localizar os produtos no banco. Vamos tentar de novo?", cache)

            reply_lines = ["✅ *Compra confirmada com sucesso!* Seus pedidos:\n"]
            
            for p in purchased_prods:
                nova_compra = Purchase(client_id=cache.id, prod_id=p.prod_id)
                db.add(nova_compra)
                
                numero = p.supplier.sup_number 
                email = p.supplier.sup_email
                reply_lines.append(f"📦 *{p.prod_name}*\n🏢 Distribuidora: {p.supplier.sup_name} (Contato: {numero}, Email: {email})\n")

            await db.commit()
            
            cache.suggested_products = []
            cache.step = "awaiting_feedback"
            recibo_texto = "\n".join(reply_lines)
            recibo_texto += "\n\n_Para me ajudar a melhorar, como você avalia sua experiência hoje de 0 a 10? Pode deixar um comentário rápido se quiser!_ ⭐"
            
            return answer_message(recibo_texto, cache)

        elif sub_intention == "cancelar":
            cache.suggested_products = []
            cache.step = "finished"
            await update_client_summary(cache, db)
            return answer_message("🔄 Pesquisa de compra cancelada. Como posso ajudar agora?", cache)
        
        elif sub_intention == "sugestoes":
            reply = "💡 Entendido! Estou buscando opções alternativas e mais baratas para você..."
            background_tasks.add_task(manage_agent, sender, original_message, "compra")
            return answer_message(reply, cache)
            
        elif sub_intention == "continuar_busca":
            reply = "🔍 Entendido! Vou refinar a busca considerando seu pedido e histórico. Só um instante..."
            background_tasks.add_task(manage_agent, sender, original_message, "compra")
            return answer_message(reply, cache)
            
        else:
            reply = "🛒 Processando sua solicitação sobre os produtos..."
            background_tasks.add_task(manage_agent, sender, original_message, "compra")
            return answer_message(reply, cache)

    elif cache.step == 'awaiting_feedback':
        # Avisa ao usuário que estamos processando, pois a IA será chamada ativamente
        holding_msg = "🙏 Processando sua avaliação..."
        background_tasks.add_task(manage_agent, sender, original_message, "feedback")
        return answer_message(holding_msg, cache)
    
    # --- ESTADO NORMAL / FINALIZADO ---
    elif cache.step == 'finished':
        # Identifica a intenção global usando o prompt padrão
        intention = get_message_context(
            original_message, 
            "message_context.txt", 
            ["saudacao", "compra", "problema", "verificacao"]
        )
        
        heavy_intentions = ["compra", "problema", "saudacao"]
        
        if intention in heavy_intentions:
            if intention == "compra":
                holding_msg = "⏳ Entendi que deseja fazer um pedido. Vou buscar os produtos disponíveis no banco de dados, só um instante..."
                cache.step = "awaiting_purchase"
            elif intention == "problema":
                holding_msg = "⏳ Compreendi que há um problema. Vou registrar os detalhes e notificar a equipe, um momento..."
                cache.step = "finished"
                await update_client_summary(cache, db)
            elif intention == "saudacao":
                # Mensagem de espera suave enquanto a IA lê o histórico
                holding_msg = "👋 Olá!"
                cache.step = "finished"
            
            background_tasks.add_task(manage_agent, sender, original_message, intention)
            return answer_message(holding_msg, cache)

        else:           
            if intention == "saudacao":
                reply = "Olá! Como posso ajudar você hoje?"
            elif intention == "verificacao":
                reply = "Verifiquei e não encontrei registros recentes por aqui."
            else:
                reply = "Desculpe, não compreendi muito bem. Poderia reformular?"

            await update_client_summary(cache, db)
            return answer_message(reply, cache)   
    
    return answer_message("Desculpe, ocorreu um erro de contexto.", cache)