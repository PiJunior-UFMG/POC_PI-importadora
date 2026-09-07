import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI
from sqlalchemy import select

from database import AsyncSessionLocal 
from models import Client
from whatsapp import user_cache 

async def sync_all_caches_to_db():
    """Percorre o cache e salva as mensagens de todos os usuários no banco."""
    # Se o cache estiver vazio, não faz nada
    if not user_cache:
        return

    # Abre a sessão do banco de dados manualmente
    async with AsyncSessionLocal() as db:
        try:
            for sender_num, cache_data in user_cache.items():
                if cache_data.msg: # Só atualiza se houver histórico
                    stmt = select(Client).where(Client.user_number == sender_num)
                    result = await db.execute(stmt)
                    client = result.scalars().first()
                    
                    if client:
                        client.client_content = cache_data.msg
            
            # Faz o commit de todas as alterações de uma vez
            await db.commit()
        except Exception as e:
            await db.rollback()
            print(f"Erro ao sincronizar cache: {e}")

async def periodic_sync_task():
    """Loop infinito que roda a cada 5 segundos."""
    while True:
        await sync_all_caches_to_db()
        await asyncio.sleep(5)

@asynccontextmanager
async def lifespan(app: FastAPI):

    task = asyncio.create_task(periodic_sync_task())
    print("Rotina de sincronização de cache iniciada (5s).")
    
    yield # O servidor fica rodando aqui...
    
    # --- EVENTO DE SHUTDOWN ---
    # Quando você apertar Ctrl+C para parar o servidor, ele cancela a tarefa
    task.cancel()
    print("Rotina de sincronização encerrada.")