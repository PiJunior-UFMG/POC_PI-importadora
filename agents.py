import os
import re
import json 

caminho_intencoes = os.path.join(os.path.dirname(__file__), "intencoes.json")

with open(caminho_intencoes, "r", encoding="utf-8") as f:
    dicionario_intencoes = json.load(f)

REGEX_INTENCOES = {}
for intencao, palavras in dicionario_intencoes.items():
    # Monta o padrão: \b(palavra1|palavra2|palavra3)\b
    padrao = r'\b(' + '|'.join(palavras) + r')\b'
    # re.IGNORECASE faz com que ignore maiúsculas e minúsculas automaticamente
    REGEX_INTENCOES[intencao] = re.compile(padrao, re.IGNORECASE)

def get_message_context(mensagem: str) -> str:
    """
    Avalia a mensagem do usuário comparando com as regex pré-compiladas.
    """
    # Não precisamos usar .lower() aqui pois o re.IGNORECASE já faz esse trabalho
    
    # Testa cada padrão compilado contra a mensagem
    for intencao, regex_compilada in REGEX_INTENCOES.items():
        if regex_compilada.search(mensagem):
            return intencao
            
    # Retorno padrão caso não identifique nenhuma palavra-chave
    return "saudacao"