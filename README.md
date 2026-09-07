# 🤖 Assistente WhatsApp da P.I. Importadora

![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![FastAPI](https://img.shields.io/badge/FastAPI-0.100+-green)
![Twilio](https://img.shields.io/badge/Twilio-API-red)
![DeepSeek](https://img.shields.io/badge/DeepSeek-LLM-purple)
![Status](https://img.shields.io/badge/status-MVP%20%2F%20PoC-yellow)

## Descrição

Sistema de atendimento automatizado para WhatsApp utilizando IA (DeepSeek) para classificar intenções, extrair tags, recomendar produtos, resolver problemas, gerar saudações proativas e extrair métricas de feedback da distribuidora "P.I. Importadora". A aplicação integra-se com a API do Twilio para envio e recebimento de mensagens, utiliza o FastAPI para expor o webhook de forma assíncrona e oferece um painel administrativo (dashboard) para gestão de fornecedores, produtos, clientes e compras, além de métricas de consumo da IA.

Este projeto é um **MVP (Prova de Conceito)** desenvolvido com o objetivo de demonstrar a viabilidade técnica e comercial de um assistente virtual para vendas B2B. O código foi estruturado para priorizar a agilidade no desenvolvimento e a funcionalidade de ponta a ponta (end-to-end) do fluxo de compra. Como tal, ele apresenta limitações arquiteturais conhecidas inerentes a esta fase, como cache em memória não persistente, carregamento ineficiente do catálogo e fluxos de "problema/verificação" ainda em evolução, servindo como base sólida para iterações futuras.

## Funcionalidades

| Item | Descrição |
| :--- | :--- |
| **Classificação de Intenção** | Identifica se o cliente deseja comprar, verificar status de pedido, relatar um problema ou apenas cumprimentar. |
| **Extração de Tags** | Analisa a mensagem do cliente e o histórico de compras para extrair as tags mais relevantes do catálogo. |
| **Recomendação Inteligente** | Utiliza o DeepSeek para ranquear os produtos do banco de dados com base no pedido atual e no perfil do cliente. |
| **Confirmação e Finalização** | Extrai os IDs dos produtos mencionados na mensagem de confirmação e registra a compra no banco. |
| **Resumo de Conversa** | Sintetiza todo o histórico de interações do cliente para alimentar decisões futuras da IA. |
| **Gerenciamento de Sessão** | Mantém o estado do cliente (etapa do fluxo, produtos sugeridos) em cache durante a conversa. |
| **Comandos Administrativos** | Comandos como `#reset`, `#del` e `#ch` para depuração e manutenção durante os testes. |
| **Dashboard de Gestão** | Interface web para visualizar fornecedores, produtos, clientes, histórico de compras e métricas de uso da IA (tokens). |
| **CRUD de Fornecedores e Produtos** | Permite adicionar/editar fornecedores, produtos e suas tags diretamente pelo dashboard. |
| **Saudação Proativa** | Gera uma saudação personalizada com recomendação de produtos baseada no histórico do cliente. |
| **Resolução de Problemas** | Oferece respostas empáticas, identifica o produto com defeito e sugere contato do fornecedor ou produtos de reposição. |
| **Extração de Feedback** | Extrai métricas NPS e CSAT de mensagens de avaliação em linguagem natural. |

## Diagrama Entidade-Relacionamento (ER)

```mermaid
erDiagram
    User {
        int user_id PK
        string user_name
        string user_number
        string user_type "discriminador (client/seller)"
    }

    Client {
        int client_id PK, FK "herda de User.user_id"
        datetime client_last_op
        text client_content
    }

    Seller {
        int seller_id PK, FK "herda de User.user_id"
        string token_id "único"
        int sup_id FK
    }

    Supplier {
        int sup_id PK
        string sup_name
        string sup_category
        string sup_number
        string sup_email
        json sup_tags "lista de tags"
    }

    Product {
        int prod_id PK
        string prod_name
        float prod_price
        int sup_id FK
        string prod_tag "tag específica do produto"
    }

    Purchase {
        int pur_id PK
        int client_id FK
        int prod_id FK
        datetime occurred_datetime
    }

    Client ||--o{ Purchase : "realiza"
    Product ||--o{ Purchase : "incluído em"
    Supplier ||--o{ Product : "fornece"
    Supplier ||--o{ Seller : "possui"
    User ||--|| Client : "herda"
    User ||--|| Seller : "herda"
```

## Como Executar

### Pré-requisitos

- Python 3.10 ou superior
- PostgreSQL (ou SQLite para testes locais)
- Conta no Twilio com um número ativo para WhatsApp Sandbox ou Produção
- Chave de API do DeepSeek (acessível via console da plataforma)

### Passos gerais

Clone o repositório, configure o ambiente virtual, instale as dependências e defina as variáveis de ambiente.

```bash
# 1. Clonar o repositório
git clone https://github.com/seu-usuario/pi-importadora-whatsapp.git
cd pi-importadora-whatsapp

# 2. Criar e ativar o ambiente virtual
python -m venv venv
source venv/bin/activate  # Linux/Mac
# ou .\venv\Scripts\activate  # Windows

# 3. Instalar as dependências
pip install -r requirements.txt

# 4. Configurar as variáveis de ambiente
# Crie um arquivo .env na raiz do projeto com o seguinte conteúdo:
cat > .env << EOF
DEEPSEEK_API_KEY="sk-xxxxxxxxxxxxxxxxxxxxxxxx"
TWILIO_ACCOUNT_SID="ACxxxxxxxxxxxxxxxxxxxxxxxx"
TWILIO_AUTH_TOKEN="xxxxxxxxxxxxxxxxxxxxxxxx"
TWILIO_NUMBER="whatsapp:+5511999999999"
DATABASE_URL="postgresql+asyncpg://user:password@localhost/pi_importadora"
EOF

# 5. Executar as migrações do banco de dados (se aplicável)
# (Caso não haja migrações configuradas, verifique se as tabelas são criadas automaticamente ou via script manual)

# 6. Iniciar o servidor FastAPI
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

> **Nota importante sobre o Webhook do Twilio**: Para testar localmente, utilize o **ngrok** para expor a porta `8000` e configure a URL do webhook no console do Twilio como `https://seu-subdominio.ngrok.io/webhook/whatsapp` (ajuste a rota conforme definida no `APIRouter`). Para produção, utilize um domínio público com HTTPS.

## Estrutura de Diretórios

```
├── agents.py                # Lógica de interação com a API DeepSeek (prompts, extração, recomendação, feedback, etc.)
├── whatsapp.py              # Handlers do Twilio, gerenciamento de estados e cache do cliente
├── dashboard.py             # Endpoints e lógica do painel administrativo (FastAPI + Jinja2)
├── schemas.py               # Modelos Pydantic para validação (Cache, Mensagens, Recomendações, Feedback)
├── models.py                # Definições SQLAlchemy das tabelas (herança User->Client/Seller, Supplier, Product, Purchase)
├── database.py              # Configuração da engine e sessão assíncrona
├── logger.py                # Utilitário para registro de uso de tokens da IA (console + arquivo)
├── prompts/                 # Diretório com os templates de prompt para cada agente
│   ├── message_context.txt
│   ├── message_context_purchase.txt
│   ├── extract_tags.txt
│   ├── recommend_products.txt
│   ├── confirm_purchase.txt
│   ├── summary_messages.txt
│   ├── proactive_greeting.txt
│   ├── problem_resolver.txt
│   └── extract_feedback.txt
├── templates/               # Templates HTML para o dashboard (Jinja2)
│   └── dashboard.html
├── agent_metrics.log        # Arquivo de log gerado automaticamente com métricas de tokens
└── requirements.txt         # Dependências do projeto (FastAPI, SQLAlchemy, Twilio, OpenAI, etc.)
```

## Limitações Conhecidas (MVP)

- **Cache volátil**: O estado da conversa (`user_cache`) é armazenado em um dicionário em memória. Isso significa que, em caso de reinicialização do servidor ou uso de múltiplos processos (Gunicorn/Uvicorn workers), o histórico da sessão será perdido.
- **Carregamento do catálogo**: Na etapa de recomendação, a aplicação carrega **todos** os fornecedores e produtos do banco para montar o contexto do prompt. Esta abordagem não escala para catálogos extensos e gera alto custo com tokens.
- **Falta de fallback**: Depende estritamente da resposta da API DeepSeek. Se a IA falhar ou retornar um formato inesperado, o sistema retorna listas vazias ou mensagens genéricas sem regras de contingência.
- **Dashboard com funcionalidades limitadas**: Embora permita visualização e edição de fornecedores/produtos, não há autenticação ou controle de acesso, e a gestão de clientes é apenas consultiva.

## 📋 Backlog / Próximos Passos (Baseado na Análise Técnica)

Lista de tarefas priorizadas para evolução do protótipo para um ambiente de produção:

### Alta Prioridade (Essencial para Demo e Estabilidade)
- [ ] **Otimizar a consulta ao catálogo**: Aplicar filtros diretamente no banco de dados (usando `ilike` nas tags/categorias) e limitar o número de produtos retornados, evitando sobrecarregar o prompt da IA.
- [ ] **Implementar fallback para falhas da IA**: Criar uma camada de regras manuais (ex.: busca por palavras-chave) para quando a API DeepSeek estiver indisponível ou retornar erro.
- [ ] **Finalizar fluxo de "Problema"**: Adicionar um sub-estado para coletar a descrição detalhada do problema e notificar a equipe (via e-mail ou mensagem interna).
- [ ] **Finalizar fluxo de "Verificação"**: Consultar a tabela `Purchase` para retornar o status real dos pedidos do cliente.

### Média Prioridade (Melhorias Arquiteturais)
- [ ] **Substituir cache em memória por Redis**: Garantir persistência e compartilhamento de estado entre diferentes workers/instâncias.
- [ ] **Adicionar logging estruturado**: Implementar logs com níveis (INFO, WARN, ERROR) e correlação de requisições (request_id) para facilitar monitoramento.
- [ ] **Extrair camada de serviço**: Criar classes como `RecommendationService` e `PurchaseService` para separar a lógica de negócio dos handlers HTTP.
- [ ] **Configurar testes automatizados**: Escrever testes unitários para os agentes (com mocks) e testes de integração para o webhook.
- [ ] **Implementar autenticação no dashboard**: Adicionar login básico para proteger o painel administrativo.

### Futuro (Escalabilidade e Novas Features)
- [ ] **Busca semântica com embeddings**: Substituir a busca por `ilike` por similaridade de vetores para recomendações mais precisas.
- [ ] **Sistema de filas (Celery/RQ)**: Mover tarefas pesadas (como `manage_agent`) para workers assíncronos dedicados.
- [ ] **Dashboard avançado**: Incluir gráficos de uso da IA, análise de sentimentos das conversas e relatórios de vendas.