from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from database import get_db
from models import Supplier, Product, Client

router = APIRouter()
templates = Jinja2Templates(directory="templates")

@router.get("/", response_class=HTMLResponse)
async def view_dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    # Busca Suppliers carregando seus Produtos junto (Eager Loading)
    stmt_suppliers = select(Supplier).options(selectinload(Supplier.products))
    result_sup = await db.execute(stmt_suppliers)
    suppliers = result_sup.scalars().all()
    
    # Busca Clientes
    stmt_clients = select(Client)
    result_cli = await db.execute(stmt_clients)
    clients = result_cli.scalars().all()

    return templates.TemplateResponse(
        request=request,
        name="dashboard.html", 
        context={"request": request, "suppliers": suppliers, "clients": clients}
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
        # Necessário recriar a lista para o SQLAlchemy entender a mutação no JSON
        updated_tags = list(supplier.sup_tags)
        updated_tags.append(new_tag.strip())
        supplier.sup_tags = updated_tags
        await db.commit()
        
    return RedirectResponse(url="/dashboard", status_code=303)