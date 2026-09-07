import os
import json
from openai import OpenAI
from dotenv import load_dotenv

load_dotenv()

# Cliente DeepSeek (compartilhado ou instanciado)
client = OpenAI(
    api_key=os.environ.get("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com"
)

# 1. Carregamento do Prompt de Intenção (já existente)
prompt_context_path = os.path.join(os.path.dirname(__file__), "prompts", "message_context.txt")
with open(prompt_context_path, "r", encoding="utf-8") as f:
    PROMPT_CONTEXT_TEMPLATE = f.read()

# 2. Carregamento do Novo Prompt de Extração de Tags
prompt_tags_path = os.path.join(os.path.dirname(__file__), "prompts", "extract_tags.txt")
with open(prompt_tags_path, "r", encoding="utf-8") as f:
    PROMPT_TAGS_TEMPLATE = f.read()


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