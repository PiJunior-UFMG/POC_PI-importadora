import logging
import sys

logger = logging.getLogger("agent_metrics")
logger.setLevel(logging.INFO)

logger.propagate = False 

if not logger.handlers:
    handler = logging.StreamHandler(sys.stdout)
    
    formatter = logging.Formatter("\033[32mAGENT:\033[0m    %(message)s")
    handler.setFormatter(formatter)
    
    logger.addHandler(handler)

def log_agent_usage(agent_name: str, prompt_tokens: int, completion_tokens: int):
    """
    Registra no terminal o uso do agente substituindo 'INFO:' por 'AGENT:' 
    e mantendo o visual idêntico ao do FastAPI.
    """
    total_tokens = prompt_tokens + completion_tokens
    
    # Formatação alinhada para os dados de entrada e saída
    log_message = (
        f"{agent_name.ljust(22)} | "
        f"In: {str(prompt_tokens).rjust(4)} | "
        f"Out: {str(completion_tokens).rjust(4)} | "
        f"Total: {str(total_tokens).rjust(5)}"
    )
    
    logger.info(log_message)