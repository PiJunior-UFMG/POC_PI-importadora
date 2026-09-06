from fastapi import APIRouter, Request, Response
from twilio.twiml.messaging_response import MessagingResponse

# Cria a instância do router ao invés do app
router = APIRouter()

# Memória temporária do bot
estado_usuarios = {}

# Como o prefixo já será "/api" no main.py, deixamos a rota vazia aqui
@router.post("")
async def whatsapp_bot(request: Request):
    form_data = await request.form()
    
    mensagem = form_data.get('Body', '').strip().lower()
    remetente = form_data.get('From', '')
    
    resposta = MessagingResponse()
    msg = resposta.message()    
    
    etapa_atual = estado_usuarios.get(remetente, 'inicio')
    
    if etapa_atual == 'inicio':
        if 'oi' in mensagem or 'olá' in mensagem:
            msg.body("Olá! Para começarmos, qual é o seu nome?")
            estado_usuarios[remetente] = 'aguardando_nome'
        else:
            msg.body("Diga *oi* para iniciar nosso atendimento.")
            
    elif etapa_atual == 'aguardando_nome':
        nome = mensagem.capitalize()
        msg.body(f"Prazer, {nome}! O que você precisa hoje?\n\n*1* - Suporte\n*2* - Vendas")
        estado_usuarios[remetente] = 'aguardando_setor'
        
    elif etapa_atual == 'aguardando_setor':
        if mensagem == '1':
            msg.body("Certo. Um técnico de Suporte vai te chamar em breve.")
            estado_usuarios[remetente] = 'inicio'
        elif mensagem == '2':
            msg.body("Nossos vendedores já foram acionados.")
            estado_usuarios[remetente] = 'inicio'
        else:
            msg.body("Por favor, digite apenas *1* ou *2*.")
            
    return Response(content=str(resposta), media_type="application/xml")