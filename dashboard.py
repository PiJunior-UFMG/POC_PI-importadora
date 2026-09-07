from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload
import os

from database import get_db
# Importe o model Purchase aqui
from models import Supplier, Product, Client, Purchase

router = APIRouter()
templates = Jinja2Templates(directory="templates")

def parse_agent_metrics():
    """Função auxiliar para ler o arquivo de log e consolidar as métricas de IA."""
    agent_metrics_dict = {}
    total_calls = 0
    total_tokens_in = 0
    total_tokens_out = 0

    log_path = "agent_metrics.log"
    
    if os.path.exists(log_path):
        with open(log_path, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("AGENT:"):
                    try:
                        # Exemplo da linha: AGENT: get_message_context    | In:  343 | Out:    2 | Total:   345
                        parts = line.split("|")
                        
                        agent_name = parts[0].replace("AGENT:", "").strip()
                        in_tokens = int(parts[1].split("In:")[1].strip())
                        out_tokens = int(parts[2].split("Out:")[1].strip())

                        total_calls += 1
                        total_tokens_in += in_tokens
                        total_tokens_out += out_tokens

                        if agent_name not in agent_metrics_dict:
                            agent_metrics_dict[agent_name] = {
                                "name": agent_name, 
                                "calls": 0, 
                                "total_in": 0, 
                                "total_out": 0
                            }

                        agent_metrics_dict[agent_name]["calls"] += 1
                        agent_metrics_dict[agent_name]["total_in"] += in_tokens
                        agent_metrics_dict[agent_name]["total_out"] += out_tokens
                    except Exception as e:
                        print(f"Erro ao parsear linha do log: {line} -> {e}")
                        continue

    # Calcula as médias e converte o dicionário para lista
    agent_metrics = []
    for agent, data in agent_metrics_dict.items():
        calls = data["calls"]
        data["avg_in"] = data["total_in"] // calls if calls > 0 else 0
        data["avg_out"] = data["total_out"] // calls if calls > 0 else 0
        agent_metrics.append(data)
        
    return agent_metrics, total_calls, total_tokens_in, total_tokens_out


@router.get("/", response_class=HTMLResponse)
async def view_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    # 1. Busca Suppliers (com produtos)
    stmt_suppliers = select(Supplier).options(selectinload(Supplier.products))
    result_sup = await db.execute(stmt_suppliers)
    suppliers = result_sup.scalars().all()
    
    # 2. Busca Clientes
    stmt_clients = select(Client)
    result_cli = await db.execute(stmt_clients)
    clients = result_cli.scalars().all()

    # 3. Busca Compras (carregando o relacionamento em cascata: Purchase -> Product -> Supplier & Purchase -> Client)
    stmt_purchases = (
        select(Purchase)
        .options(
            selectinload(Purchase.client),
            selectinload(Purchase.product).selectinload(Product.supplier)
        )
        .order_by(Purchase.occurred_datetime.desc()) # Ordena das mais recentes para as mais antigas
    )
    result_pur = await db.execute(stmt_purchases)
    purchases = result_pur.scalars().all()

    # 4. Extrai as métricas consolidadas do arquivo de log
    agent_metrics, total_calls, total_tokens_in, total_tokens_out = parse_agent_metrics()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html", 
        context={
            "request": request, 
            "suppliers": suppliers, 
            "clients": clients,
            "purchases": purchases,
            "agent_metrics": agent_metrics,
            "total_calls": total_calls,
            "total_tokens_in": total_tokens_in,
            "total_tokens_out": total_tokens_out
        }
    )

@router.post("/supplier/add")
async def add_supplier(
    name: str = Form(...), category: str = Form(...), 
    db: AsyncSession = Depends(get_db)
):
    new_sup = Supplier(sup_name=name, sup_category=category, sup_tags=[])
    db.add(new_sup)
    await db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)

@router.post("/supplier/{sup_id}/tag")
async def add_tag_to_supplier(
    sup_id: int, new_tag: str = Form(...), db: AsyncSession = Depends(get_db)
):
    stmt = select(Supplier).where(Supplier.sup_id == sup_id)
    result = await db.execute(stmt)
    supplier = result.scalars().first()
    
    if supplier and new_tag not in supplier.sup_tags:
        updated_tags = list(supplier.sup_tags)
        updated_tags.append(new_tag.strip())
        supplier.sup_tags = updated_tags
        await db.commit()
        
    return RedirectResponse(url="/dashboard", status_code=303)

@router.post("/supplier/{sup_id}/product/add")
async def add_product(
    sup_id: int, 
    prod_name: str = Form(...), 
    prod_price: float = Form(...), 
    prod_tag: str = Form(""), # Opcional
    db: AsyncSession = Depends(get_db)
):
    """Cria um novo produto vinculado a um fornecedor específico."""
    novo_produto = Product(
        prod_name=prod_name,
        prod_price=prod_price,
        prod_tag=prod_tag.strip() if prod_tag else None,
        supplier_id=sup_id # Ajuste este campo para o nome exato da ForeignKey no seu model Product
    )
    db.add(novo_produto)
    await db.commit()
    return RedirectResponse(url="/dashboard", status_code=303)


@router.post("/product/{prod_id}/edit")
async def edit_product(
    prod_id: int, 
    prod_name: str = Form(...), 
    prod_price: float = Form(...), 
    prod_tag: str = Form(""), 
    db: AsyncSession = Depends(get_db)
):
    """Edita os detalhes de um produto existente."""
    stmt = select(Product).where(Product.prod_id == prod_id)
    result = await db.execute(stmt)
    produto = result.scalars().first()
    
    if produto:
        produto.prod_name = prod_name
        produto.prod_price = prod_price
        produto.prod_tag = prod_tag.strip() if prod_tag else None
        await db.commit()
        
    return RedirectResponse(url="/dashboard", status_code=303)