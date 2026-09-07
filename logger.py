import logging
import sys
import os

logger = logging.getLogger("agent_metrics")
logger.setLevel(logging.INFO)
logger.propagate = False 

if not logger.handlers:
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter("\033[32mAGENT:\033[0m    %(message)s")
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    file_handler = logging.FileHandler("agent_metrics.log", encoding="utf-8")
    file_formatter = logging.Formatter("AGENT: %(message)s")
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

def log_agent_usage(agent_name: str, prompt_tokens: int, completion_tokens: int):
    total_tokens = prompt_tokens + completion_tokens
    log_message = (
        f"{agent_name.ljust(22)} | "
        f"In: {str(prompt_tokens).rjust(4)} | "
        f"Out: {str(completion_tokens).rjust(4)} | "
        f"Total: {str(total_tokens).rjust(5)}"
    )
    logger.info(log_message)