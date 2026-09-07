import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Inicializa o cliente apontando para a API do DeepSeek (compatível com OpenAI)
# O DeepSeek usa a baseUrl oficial: https://api.deepseek.com
client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# Carrega o prompt externo da pasta prompts/
prompt_path = os.path.join(os.path.dirname(__file__), "prompts", "message_context.txt")
with open(prompt_path, "r", encoding="utf-8") as f:
    PROMPT_TEMPLATE = f.read()

def get_message_context(mensagem: str) -> str:
    """
    Analisa a mensagem do usuário utilizando o DeepSeek LLM 
    com base no prompt estruturado em arquivo externo.
    """
    # Injeta a mensagem do usuário dentro do template do prompt
    formatted_prompt = PROMPT_TEMPLATE.replace("{mensagem}", mensagem)
    
    try:
        # Chamada ao modelo leve e rápido do DeepSeek (deepseek-chat / V3)
        response = client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "Você é um classificador de intenções preciso e conciso."},
                {"role": "user", "content": formatted_prompt}
            ],
            temperature=0.0,  # Zero criatividade para garantir respostas determinísticas
            max_tokens=10     # Precisamos apenas de uma palavra como resposta
        )
        
        # Limpa o texto retornado pela LLM
        intencao = response.choices[0].message.content.strip().lower()
        
        # Valida se a resposta está dentro das permitidas, caso contrário aplica fallback
        categorias_validas = ["saudacao", "compra", "problema", "verificacao"]
        if intencao not in categorias_validas:
            return "saudacao"
            
        return intencao
        
    except Exception as e:
        print(f"Erro ao consultar o DeepSeek para triagem: {e}")
        return "saudacao"  # Fallback de segurança caso a API falhe