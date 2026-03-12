"""
Rotas para gestão de Imóveis Angariados
CRUD completo para imóveis listados pela agência
"""
import uuid
import logging
import asyncio
from typing import List, Optional
from datetime import datetime, timezone
from fastapi import APIRouter, HTTPException, Depends, Query, BackgroundTasks, UploadFile, File

from database import db
from models.property import (
    Property, PropertyCreate, PropertyUpdate, PropertyListItem,
    PropertyStatus, PropertyType, PropertyHistory
)
from services.auth import get_current_user, require_roles
from services.alerts import check_and_notify_matches_for_new_property
from services.background_jobs import background_jobs, JobType, JobStatus
from models.auth import UserRole

router = APIRouter(prefix="/properties", tags=["Properties"])
logger = logging.getLogger(__name__)


async def get_next_reference() -> str:
    """Gera próxima referência interna (IMO-001, IMO-002...)"""
    last = await db.properties.find_one(
        {"internal_reference": {"$regex": "^IMO-"}},
        sort=[("internal_reference", -1)]
    )
    if last and last.get("internal_reference"):
        try:
            num = int(last["internal_reference"].split("-")[1])
            return f"IMO-{num + 1:03d}"
        except (ValueError, IndexError):
            pass
    return "IMO-001"


@router.get("", response_model=List[PropertyListItem])
async def list_properties(
    status: Optional[PropertyStatus] = None,
    property_type: Optional[PropertyType] = None,
    district: Optional[str] = None,
    municipality: Optional[str] = None,
    min_price: Optional[float] = None,
    max_price: Optional[float] = None,
    min_bedrooms: Optional[int] = None,
    agent_id: Optional[str] = None,
    search: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Listar imóveis com filtros."""
    query = {}
    
    if status:
        query["status"] = status
    if property_type:
        query["property_type"] = property_type
    if district:
        query["address.district"] = {"$regex": district, "$options": "i"}
    if municipality:
        query["address.municipality"] = {"$regex": municipality, "$options": "i"}
    if min_price:
        query["financials.asking_price"] = {"$gte": min_price}
    if max_price:
        query.setdefault("financials.asking_price", {})["$lte"] = max_price
    if min_bedrooms:
        query["features.bedrooms"] = {"$gte": min_bedrooms}
    if agent_id:
        query["assigned_agent_id"] = agent_id
    if search:
        query["$or"] = [
            {"title": {"$regex": search, "$options": "i"}},
            {"internal_reference": {"$regex": search, "$options": "i"}},
            {"address.locality": {"$regex": search, "$options": "i"}},
        ]
    
    properties = await db.properties.find(query, {"_id": 0}).sort("created_at", -1).to_list(500)
    
    # Converter para formato de listagem
    result = []
    for p in properties:
        result.append(PropertyListItem(
            id=p["id"],
            internal_reference=p.get("internal_reference"),
            title=p["title"],
            property_type=p["property_type"],
            status=p["status"],
            asking_price=p["financials"]["asking_price"],
            municipality=p["address"]["municipality"],
            district=p["address"]["district"],
            bedrooms=p.get("features", {}).get("bedrooms") if p.get("features") else None,
            useful_area=p.get("features", {}).get("useful_area") if p.get("features") else None,
            photo_url=p["photos"][0] if p.get("photos") else None,
            assigned_agent_name=p.get("assigned_agent_name"),
            created_at=p["created_at"]
        ))
    
    return result


@router.get("/stats")
async def get_property_stats(user: dict = Depends(get_current_user)):
    """Obter estatísticas dos imóveis."""
    pipeline = [
        {
            "$group": {
                "_id": "$status",
                "count": {"$sum": 1},
                "total_value": {"$sum": "$financials.asking_price"}
            }
        }
    ]
    
    stats_cursor = db.properties.aggregate(pipeline)
    status_stats = {s["_id"]: {"count": s["count"], "total_value": s["total_value"]} 
                    async for s in stats_cursor}
    
    total = await db.properties.count_documents({})
    
    return {
        "total": total,
        "by_status": status_stats,
        "disponivel": status_stats.get("disponivel", {"count": 0, "total_value": 0}),
        "reservado": status_stats.get("reservado", {"count": 0, "total_value": 0}),
        "vendido": status_stats.get("vendido", {"count": 0, "total_value": 0}),
    }


@router.post("", response_model=Property)
async def create_property(
    data: PropertyCreate,
    user: dict = Depends(get_current_user)
):
    """Criar novo imóvel angariado."""
    now = datetime.now(timezone.utc).isoformat()
    
    # Gerar referência se não fornecida
    internal_ref = data.internal_reference or await get_next_reference()
    
    # Obter nome do agente se atribuído
    agent_name = None
    if data.assigned_agent_id:
        agent = await db.users.find_one({"id": data.assigned_agent_id}, {"name": 1})
        if agent:
            agent_name = agent["name"]
    
    property_doc = Property(
        id=str(uuid.uuid4()),
        internal_reference=internal_ref,
        property_type=data.property_type,
        title=data.title,
        description=data.description,
        address=data.address,
        features=data.features,
        condition=data.condition,
        financials=data.financials,
        owner=data.owner,
        photos=data.photos,
        video_url=data.video_url,
        virtual_tour_url=data.virtual_tour_url,
        documents=data.documents,
        status=data.status,
        assigned_agent_id=data.assigned_agent_id,
        assigned_agent_name=agent_name,
        notes=data.notes,
        private_notes=data.private_notes,
        history=[
            PropertyHistory(
                timestamp=now,
                event="Imóvel criado",
                user=user.get("email")
            )
        ],
        created_at=now,
        updated_at=now,
        created_by=user.get("email")
    )
    
    await db.properties.insert_one(property_doc.model_dump())
    
    logger.info(f"Imóvel criado: {property_doc.id} ({internal_ref}) por {user.get('email')}")
    
    # Verificar matches em background (não bloqueia resposta)
    asyncio.create_task(check_and_notify_matches_for_new_property(property_doc.id))
    
    return property_doc


@router.get("/{property_id}", response_model=Property)
async def get_property(
    property_id: str,
    user: dict = Depends(get_current_user)
):
    """Obter detalhes de um imóvel."""
    prop = await db.properties.find_one({"id": property_id}, {"_id": 0})
    
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    # Incrementar contador de visualizações
    await db.properties.update_one(
        {"id": property_id},
        {"$inc": {"view_count": 1}}
    )
    
    return Property(**prop)


@router.patch("/{property_id}", response_model=Property)
async def update_property(
    property_id: str,
    data: PropertyUpdate,
    user: dict = Depends(get_current_user)
):
    """Actualizar um imóvel."""
    prop = await db.properties.find_one({"id": property_id})
    
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Preparar actualização
    update_dict = data.model_dump(exclude_none=True)
    update_dict["updated_at"] = now
    
    # Actualizar nome do agente se mudou
    if "assigned_agent_id" in update_dict:
        agent = await db.users.find_one({"id": update_dict["assigned_agent_id"]}, {"name": 1})
        update_dict["assigned_agent_name"] = agent["name"] if agent else None
    
    # Registar mudança de status no histórico
    if "status" in update_dict and update_dict["status"] != prop.get("status"):
        history_entry = PropertyHistory(
            timestamp=now,
            event=f"Status alterado para {update_dict['status']}",
            user=user.get("email")
        )
        await db.properties.update_one(
            {"id": property_id},
            {"$push": {"history": history_entry.model_dump()}}
        )
    
    await db.properties.update_one(
        {"id": property_id},
        {"$set": update_dict}
    )
    
    updated = await db.properties.find_one({"id": property_id}, {"_id": 0})
    
    return Property(**updated)


@router.patch("/{property_id}/status")
async def update_property_status(
    property_id: str,
    status: PropertyStatus,
    user: dict = Depends(get_current_user)
):
    """Actualizar apenas o status de um imóvel."""
    prop = await db.properties.find_one({"id": property_id})
    
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    history_entry = PropertyHistory(
        timestamp=now,
        event=f"Status alterado para {status.value}",
        user=user.get("email")
    )
    
    await db.properties.update_one(
        {"id": property_id},
        {
            "$set": {"status": status.value, "updated_at": now},
            "$push": {"history": history_entry.model_dump()}
        }
    )
    
    return {"success": True, "status": status.value}


@router.delete("/{property_id}")
async def delete_property(
    property_id: str,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """Eliminar um imóvel (apenas admin/CEO/diretor)."""
    result = await db.properties.delete_one({"id": property_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    logger.info(f"Imóvel {property_id} eliminado por {user.get('email')}")
    
    return {"success": True, "message": "Imóvel eliminado"}


@router.post("/{property_id}/interested-client")
async def add_interested_client(
    property_id: str,
    client_id: str,
    user: dict = Depends(get_current_user)
):
    """Adicionar cliente interessado a um imóvel."""
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    # Verificar se cliente existe
    process = await db.processes.find_one({"id": client_id})
    if not process:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    
    # Adicionar se não existe
    if client_id not in prop.get("interested_clients", []):
        now = datetime.now(timezone.utc).isoformat()
        await db.properties.update_one(
            {"id": property_id},
            {
                "$addToSet": {"interested_clients": client_id},
                "$inc": {"inquiry_count": 1},
                "$push": {
                    "history": PropertyHistory(
                        timestamp=now,
                        event=f"Cliente interessado: {process.get('client_name')}",
                        user=user.get("email")
                    ).model_dump()
                }
            }
        )
    
    return {"success": True, "message": f"Cliente {process.get('client_name')} adicionado"}


@router.get("/{property_id}/interested-clients")
async def get_interested_clients(
    property_id: str,
    user: dict = Depends(get_current_user)
):
    """Obter lista de clientes interessados num imóvel."""
    prop = await db.properties.find_one({"id": property_id}, {"interested_clients": 1})
    
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    client_ids = prop.get("interested_clients", [])
    
    if not client_ids:
        return []
    
    clients = await db.processes.find(
        {"id": {"$in": client_ids}},
        {"_id": 0, "id": 1, "client_name": 1, "client_email": 1, "client_phone": 1, "status": 1}
    ).to_list(100)
    
    return clients


@router.post("/{property_id}/register-visit")
async def register_visit(
    property_id: str,
    client_id: Optional[str] = None,
    notes: Optional[str] = None,
    user: dict = Depends(get_current_user)
):
    """Registar uma visita ao imóvel."""
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    event_text = "Visita registada"
    if client_id:
        process = await db.processes.find_one({"id": client_id}, {"client_name": 1})
        if process:
            event_text = f"Visita com {process.get('client_name')}"
    
    if notes:
        event_text += f" - {notes}"
    
    await db.properties.update_one(
        {"id": property_id},
        {
            "$inc": {"visit_count": 1},
            "$push": {
                "history": PropertyHistory(
                    timestamp=now,
                    event=event_text,
                    user=user.get("email")
                ).model_dump()
            }
        }
    )
    
    return {"success": True, "message": "Visita registada"}



@router.post("/{property_id}/upload-photo")
async def upload_property_photo(
    property_id: str,
    photo_url: str,
    user: dict = Depends(get_current_user)
):
    """
    Adicionar foto a um imóvel.
    Aceita URL de foto (pode ser do OneDrive, Dropbox, etc.)
    """
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.properties.update_one(
        {"id": property_id},
        {
            "$addToSet": {"photos": photo_url},
            "$set": {"updated_at": now},
            "$push": {
                "history": PropertyHistory(
                    timestamp=now,
                    event="Foto adicionada",
                    user=user.get("email")
                ).model_dump()
            }
        }
    )
    
    return {"success": True, "message": "Foto adicionada", "photo_url": photo_url}


@router.delete("/{property_id}/photo")
async def remove_property_photo(
    property_id: str,
    photo_url: str,
    user: dict = Depends(get_current_user)
):
    """Remover foto de um imóvel."""
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    now = datetime.now(timezone.utc).isoformat()
    
    await db.properties.update_one(
        {"id": property_id},
        {
            "$pull": {"photos": photo_url},
            "$set": {"updated_at": now}
        }
    )
    
    return {"success": True, "message": "Foto removida"}


@router.post("/bulk/import-excel")
async def import_properties_from_excel(
    file: UploadFile,
    user: dict = Depends(require_roles([UserRole.ADMIN, UserRole.CEO, UserRole.DIRETOR]))
):
    """
    Importar imóveis a partir de ficheiro Excel (processamento em background).
    
    Retorna imediatamente com um job_id para acompanhar o progresso.
    
    Colunas esperadas (case-insensitive):
    - titulo (obrigatório): Título do imóvel
    - tipo: apartamento, moradia, terreno, loja, escritorio, armazem, garagem, outro
    - preco (obrigatório): Preço pedido
    - distrito (obrigatório): Ex: Lisboa, Porto
    - concelho (obrigatório): Ex: Lisboa, Cascais
    - localidade: Ex: Cascais, Oeiras
    - morada: Endereço completo
    - codigo_postal: Ex: 2750-123
    - quartos: Número de quartos (T0=0, T1=1, etc.)
    - casas_banho: Número de casas de banho
    - area_util: Área útil em m²
    - area_bruta: Área bruta em m²
    - ano_construcao: Ano de construção
    - certificado_energetico: A, B, C, D, E, F, G
    - estado: novo, como_novo, bom, para_recuperar, em_construcao
    - proprietario_nome (obrigatório): Nome do proprietário
    - proprietario_telefone: Telefone do proprietário
    - proprietario_email: Email do proprietário
    - descricao: Descrição do imóvel
    - notas: Notas internas
    """
    import pandas as pd
    from io import BytesIO
    
    # Validar tipo de ficheiro
    if not file.filename.endswith(('.xlsx', '.xls')):
        raise HTTPException(status_code=400, detail="Ficheiro deve ser Excel (.xlsx ou .xls)")
    
    # Ler ficheiro
    try:
        contents = await file.read()
        df = pd.read_excel(BytesIO(contents))
    except Exception as e:
        logger.error(f"Erro ao ler ficheiro Excel: {e}")
        raise HTTPException(status_code=400, detail=f"Erro ao ler ficheiro: {str(e)}")
    
    # Criar job de background
    job_id = await background_jobs.create_job(
        job_type=JobType.EXCEL_IMPORT,
        user_id=user.get("id"),
        user_email=user.get("email"),
        metadata={
            "filename": file.filename,
            "total_rows": len(df)
        }
    )
    
    # Iniciar processamento em background
    background_jobs.run_in_background(
        job_id,
        _process_excel_import(job_id, df, file.filename, user)
    )
    
    return {
        "job_id": job_id,
        "message": "Importação iniciada em background",
        "total_rows": len(df)
    }


async def _process_excel_import(job_id: str, df, filename: str, user: dict):
    """
    Processa a importação Excel em background.
    """
    import pandas as pd
    
    await background_jobs.set_status(job_id, JobStatus.PROCESSING)
    
    try:
        # Normalizar nomes das colunas (lowercase, sem espaços)
        df.columns = df.columns.str.lower().str.strip().str.replace(' ', '_')
        
        # Mapear colunas alternativas (para formatos HCPro, CRM externo, etc.)
        column_aliases = {
            # Título
            'título': 'titulo',
            # Preço
            'preço': 'preco',
            # Localização
            'freguesia': 'localidade',
            'rua': 'morada',
            'código_postal': 'codigo_postal',
            # Áreas
            'área_útil': 'area_util',
            'área_terreno': 'area_terreno',
            'área_bruta': 'area_bruta',
            # Características
            'tipologia': 'quartos_raw',  # T1, T2, T3...
            'ano_de_construção': 'ano_construcao',
            'certificado_energético': 'certificado_energetico',
            # Proprietário (formato HCPro)
            'proprietário': 'proprietario_nome',
            'proprietário,_email': 'proprietario_email',
            'proprietário,_telemóvel': 'proprietario_telefone',
            'proprietário,_telefone': 'proprietario_telefone2',
            # Descrição
            'descrição_pt': 'descricao',
            'descrição': 'descricao',
            # Referência
            'referência': 'referencia_externa',
            # Agência
            'agência': 'agencia',
            'agencia_responsável': 'agencia',
            # Outros
            'observações': 'notas',
            'responsável': 'responsavel',
        }
        
        # Aplicar aliases
        df = df.rename(columns=column_aliases)
        
        # Mapear tipos de imóvel
        tipo_map = {
            'apartamento': 'apartamento',
            'moradia': 'moradia',
            'moradia_isolada': 'moradia',
            'moradia_geminada': 'moradia',
            'moradia_em_banda': 'moradia',
            'terreno': 'terreno',
            'loja': 'loja',
            'escritorio': 'escritorio',
            'escritório': 'escritorio',
            'armazem': 'armazem',
            'armazém': 'armazem',
            'garagem': 'garagem',
            'outro': 'outro',
            't0': 'apartamento',
            't1': 'apartamento',
            't2': 'apartamento',
            't3': 'apartamento',
            't4': 'apartamento',
            't5': 'apartamento',
        }
        
        # Mapear estados
        estado_map = {
            'novo': 'novo',
            'como_novo': 'como_novo',
            'como novo': 'como_novo',
            'bom': 'bom',
            'para_recuperar': 'para_recuperar',
            'para recuperar': 'para_recuperar',
            'em_construcao': 'em_construcao',
            'em construção': 'em_construcao',
            'em construcao': 'em_construcao'
        }
        
        results = {
            "total": len(df),
            "importados": 0,
            "erros": [],
            "ids_criados": []
        }
        
        now = datetime.now(timezone.utc).isoformat()
        total_rows = len(df)
        
        for idx, row in df.iterrows():
            linha = idx + 2  # +2 porque idx começa em 0 e Excel tem cabeçalho
            
            # Atualizar progresso a cada 5 linhas para não sobrecarregar
            if idx % 5 == 0:
                await background_jobs.update_progress(
                    job_id,
                    current=idx,
                    total=total_rows,
                    message=f"A processar linha {linha} de {total_rows + 1}..."
                )
            
            try:
                # Helper function para obter valor da linha de forma segura
                def get_value(keys, default=''):
                    if isinstance(keys, str):
                        keys = [keys]
                    for key in keys:
                        if key not in row.index:
                            continue
                        val = row[key]
                        # Se é uma Series (colunas duplicadas), pegar o primeiro valor
                        if hasattr(val, 'iloc'):
                            val = val.iloc[0] if len(val) > 0 else None
                        if val is not None and not pd.isna(val) and str(val).strip() not in ('nan', '', 'NaN'):
                            return str(val).strip()
                    return default
                
                # Helper para converter preço (remove € e espaços, trata formato europeu)
                def parse_price(price_str):
                    if price_str is None:
                        return None
                    # Se é uma Series, pegar o primeiro valor
                    if hasattr(price_str, 'iloc'):
                        price_str = price_str.iloc[0] if len(price_str) > 0 else None
                    if price_str is None or pd.isna(price_str):
                        return None
                    price_str = str(price_str).replace('€', '').strip()
                    # Se tem "/" provavelmente é venda/arrendamento, pegar o primeiro
                    if '/' in price_str:
                        price_str = price_str.split('/')[0].strip()
                    # Formato europeu: 700.000 = 700000, 700,00 = 700.00
                    # Se tem ponto e vírgula, é formato europeu
                    if '.' in price_str and ',' in price_str:
                        # 700.000,00 -> 700000.00
                        price_str = price_str.replace('.', '').replace(',', '.')
                    elif '.' in price_str:
                        # Pode ser 700.000 (europeu) ou 700.00 (americano)
                        # Se tem mais de 2 dígitos após o ponto, é europeu (separador de milhares)
                        parts = price_str.split('.')
                        if len(parts[-1]) == 3 and len(parts) > 1:
                            # 700.000 -> 700000
                            price_str = price_str.replace('.', '')
                    elif ',' in price_str:
                        # 700,00 -> 700.00
                        price_str = price_str.replace(',', '.')
                    try:
                        return float(price_str)
                    except ValueError:
                        return None
                
                # Helper para extrair quartos de tipologia (T0, T1, T2, etc.)
                def parse_tipologia(tipologia):
                    if pd.isna(tipologia):
                        return None
                    tip = str(tipologia).upper().strip()
                    if tip.startswith('T') and len(tip) >= 2:
                        try:
                            return int(tip[1])
                        except ValueError:
                            pass
                    return None
                
                # Campos obrigatórios - com múltiplas fontes
                titulo = get_value(['titulo', 'título'])
                if not titulo:
                    results["erros"].append({"linha": linha, "erro": "Título em falta"})
                    continue
                
                preco = parse_price(row.get('preco', row.get('preço')))
                if preco is None:
                    results["erros"].append({"linha": linha, "erro": "Preço em falta ou inválido"})
                    continue
                
                distrito = get_value(['distrito'])
                if not distrito:
                    results["erros"].append({"linha": linha, "erro": "Distrito em falta"})
                    continue
                
                concelho = get_value(['concelho'])
                if not concelho:
                    results["erros"].append({"linha": linha, "erro": "Concelho em falta"})
                    continue
                
                # Proprietário - pode estar em várias colunas
                proprietario_nome = get_value(['proprietario_nome', 'proprietário', 'proprietário_nome'])
                if not proprietario_nome:
                    # Tentar usar agência como fallback
                    proprietario_nome = get_value(['agencia', 'agencia_responsável'], 'Não informado')
                
                # Campos opcionais
                tipo_raw = get_value(['tipo'], 'apartamento').lower()
                tipologia = get_value(['quartos_raw', 'tipologia'])
                
                # Extrair quartos da tipologia se disponível
                quartos = parse_tipologia(tipologia)
                
                # Mapear tipo de imóvel
                if tipologia:
                    # Se tem tipologia, usar título para determinar tipo
                    if 'moradia' in titulo.lower() or 'moradia' in tipo_raw:
                        tipo = 'moradia'
                    elif 'armazém' in titulo.lower() or 'armazem' in tipo_raw:
                        tipo = 'armazem'
                    elif 'loja' in titulo.lower():
                        tipo = 'loja'
                    else:
                        tipo = 'apartamento'
                else:
                    tipo = tipo_map.get(tipo_raw, 'apartamento')
                
                estado_raw = get_value(['estado'], 'bom').lower()
                estado = estado_map.get(estado_raw, 'bom')
                # Mapear estados adicionais
                if 'em construção' in estado_raw or 'em construcao' in estado_raw:
                    estado = 'em_construcao'
                elif 'recupera' in estado_raw:
                    estado = 'para_recuperar'
                elif 'execução' in estado_raw:
                    estado = 'em_construcao'
                
                # Criar documento
                internal_ref = await get_next_reference()
                
                # Extrair áreas com helper
                def parse_float(val):
                    if pd.isna(val):
                        return None
                    try:
                        return float(str(val).replace(',', '.').strip())
                    except (ValueError, TypeError):
                        return None
                
                def parse_int(val):
                    if pd.isna(val):
                        return None
                    try:
                        return int(float(str(val).replace(',', '.').strip()))
                    except (ValueError, TypeError):
                        return None
                
                property_doc = {
                    "id": str(uuid.uuid4()),
                    "internal_reference": internal_ref,
                    "external_reference": get_value(['referencia_externa']) or None,
                    "property_type": tipo,
                    "title": titulo,
                    "description": get_value(['descricao']) or None,
                    "address": {
                        "street": get_value(['morada', 'rua']) or None,
                        "postal_code": get_value(['codigo_postal']) or None,
                        "locality": get_value(['localidade', 'freguesia']) or None,
                        "municipality": concelho,
                        "district": distrito
                    },
                    "features": {
                        "bedrooms": quartos or parse_int(row.get('quartos')),
                        "bathrooms": parse_int(row.get('casas_banho')),
                        "useful_area": parse_float(row.get('area_util')),
                        "gross_area": parse_float(row.get('area_bruta')),
                        "land_area": parse_float(row.get('area_terreno')),
                        "construction_year": parse_int(row.get('ano_construcao')),
                        "energy_certificate": get_value(['certificado_energetico']).upper() if get_value(['certificado_energetico']) else None,
                        "extra_features": []
                    },
                    "condition": estado,
                    "financials": {
                        "asking_price": preco
                    },
                    "owner": {
                        "name": proprietario_nome,
                        "phone": get_value(['proprietario_telefone']) or None,
                        "email": get_value(['proprietario_email']) or None
                    },
                    "agency": get_value(['agencia']) or None,
                    "photos": [],
                    "documents": [],
                    "status": "em_analise",
                    "notes": get_value(['notas', 'observações']) or None,
                    "history": [{
                        "timestamp": now,
                        "event": "Importado via Excel",
                        "user": user.get("email")
                    }],
                    "created_at": now,
                    "updated_at": now,
                    "created_by": user.get("email"),
                    "view_count": 0,
                    "inquiry_count": 0,
                    "visit_count": 0,
                    "interested_clients": []
                }
                
                await db.properties.insert_one(property_doc)
                results["importados"] += 1
                results["ids_criados"].append(property_doc["id"])
                
                logger.info(f"Imóvel importado: {internal_ref} - {titulo}")
                
            except Exception as e:
                logger.error(f"Erro na linha {linha}: {e}")
                results["erros"].append({"linha": linha, "erro": str(e)})
        
        # Log de erros para análise usando o logger centralizado
        if results["erros"]:
            from services.system_error_logger import system_error_logger
            for err in results["erros"]:
                await system_error_logger.log_error(
                    error_type="excel_import_error",
                    message=f"Erro ao importar linha {err['linha']}: {err['erro']}",
                    component="properties",
                    details={
                        "linha": err["linha"],
                        "erro": err["erro"],
                        "ficheiro": filename
                    },
                    severity="warning",
                    user_id=user.get("id")
                )
        
        # Log de sucesso
        if results["importados"] > 0:
            from services.system_error_logger import system_error_logger
            await system_error_logger.log_error(
                error_type="excel_import_success",
                message=f"Importação Excel concluída: {results['importados']}/{results['total']} imóveis",
                component="properties",
                details={
                    "total": results["total"],
                    "importados": results["importados"],
                    "erros": len(results["erros"]),
                    "ficheiro": filename,
                    "ids": results["ids_criados"]
                },
                severity="info",
                user_id=user.get("id")
            )
        
        # Finalizar job com resultado
        await background_jobs.set_result(job_id, results)
        logger.info(f"Job {job_id} concluído: {results['importados']}/{results['total']} importados")
    
    except Exception as e:
        logger.error(f"Job {job_id} falhou: {e}")
        await background_jobs.set_error(job_id, str(e))


@router.get("/bulk/job/{job_id}")
async def get_import_job_status(
    job_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Consultar o status de um job de importação.
    """
    job = await background_jobs.get_job(job_id)
    
    if not job:
        raise HTTPException(status_code=404, detail="Job não encontrado")
    
    # Verificar se o utilizador tem acesso ao job
    if job.get("user_id") != user.get("id") and user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Sem permissão para ver este job")
    
    return job


@router.get("/bulk/jobs")
async def get_user_import_jobs(
    limit: int = Query(default=20, le=100),
    user: dict = Depends(get_current_user)
):
    """
    Listar jobs de importação do utilizador actual.
    """
    jobs = await background_jobs.get_user_jobs(
        user_id=user.get("id"),
        job_type=JobType.EXCEL_IMPORT,
        limit=limit
    )
    
    return {"jobs": jobs}


@router.get("/bulk/import-template")
async def get_import_template(user: dict = Depends(get_current_user)):
    """
    Retorna instruções para o template de importação Excel.
    """
    return {
        "instrucoes": "Crie um ficheiro Excel (.xlsx) com as seguintes colunas:",
        "colunas_obrigatorias": [
            {"nome": "titulo", "descricao": "Título do imóvel", "exemplo": "T2 em Cascais"},
            {"nome": "preco", "descricao": "Preço pedido", "exemplo": "250000"},
            {"nome": "distrito", "descricao": "Distrito", "exemplo": "Lisboa"},
            {"nome": "concelho", "descricao": "Concelho", "exemplo": "Cascais"},
            {"nome": "proprietario_nome", "descricao": "Nome do proprietário", "exemplo": "João Silva"}
        ],
        "colunas_opcionais": [
            {"nome": "tipo", "valores": "apartamento, moradia, terreno, loja, escritorio, armazem, garagem, outro"},
            {"nome": "localidade", "exemplo": "Cascais"},
            {"nome": "morada", "exemplo": "Rua das Flores, 123"},
            {"nome": "codigo_postal", "exemplo": "2750-123"},
            {"nome": "quartos", "exemplo": "2"},
            {"nome": "casas_banho", "exemplo": "1"},
            {"nome": "area_util", "exemplo": "85"},
            {"nome": "area_bruta", "exemplo": "100"},
            {"nome": "ano_construcao", "exemplo": "2010"},
            {"nome": "certificado_energetico", "valores": "A, B, C, D, E, F, G"},
            {"nome": "estado", "valores": "novo, como_novo, bom, para_recuperar, em_construcao"},
            {"nome": "proprietario_telefone", "exemplo": "+351 912345678"},
            {"nome": "proprietario_email", "exemplo": "email@exemplo.com"},
            {"nome": "descricao", "exemplo": "Apartamento renovado com vista mar"},
            {"nome": "notas", "exemplo": "Notas internas"}
        ]
    }


# ============== DOCUMENTOS DE IMÓVEIS (Item 1 - Outros erros/melhorias) ==============

@router.post("/{property_id}/documents")
async def upload_property_document(
    property_id: str,
    file: UploadFile = File(...),
    document_type: str = "outro",
    description: str = None,
    user: dict = Depends(get_current_user)
):
    """
    Upload de documento para um imóvel da empresa.
    
    Tipos de documento:
    - caderneta_predial
    - certidao_registo
    - licenca_utilizacao
    - planta
    - cpcv
    - contrato
    - outro
    """
    from services.s3_service import upload_file_to_s3
    
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    # Validar tipo de documento
    valid_types = [
        "caderneta_predial", "certidao_registo", "licenca_utilizacao",
        "planta", "cpcv", "contrato", "foto", "outro"
    ]
    if document_type not in valid_types:
        raise HTTPException(status_code=400, detail=f"Tipo inválido. Use: {valid_types}")
    
    # Validar ficheiro
    allowed_extensions = ['pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'xls', 'xlsx']
    file_ext = file.filename.split('.')[-1].lower() if '.' in file.filename else ''
    if file_ext not in allowed_extensions:
        raise HTTPException(status_code=400, detail=f"Tipo de ficheiro não permitido. Use: {allowed_extensions}")
    
    # Ler conteúdo
    content = await file.read()
    if len(content) > 20 * 1024 * 1024:  # 20MB max
        raise HTTPException(status_code=400, detail="Ficheiro muito grande (máx 20MB)")
    
    try:
        # Upload para S3
        s3_path = f"properties/{property_id}/documents/{document_type}_{file.filename}"
        result = await upload_file_to_s3(content, s3_path, file.content_type)
        
        if not result.get("success"):
            raise HTTPException(status_code=500, detail=f"Erro no upload: {result.get('error')}")
        
        # Criar registo do documento
        doc_record = {
            "id": str(uuid.uuid4()),
            "filename": file.filename,
            "document_type": document_type,
            "description": description,
            "s3_key": result.get("key"),
            "url": result.get("url"),
            "size": len(content),
            "mime_type": file.content_type,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "uploaded_by": user.get("email")
        }
        
        # Adicionar ao array de documentos do imóvel
        await db.properties.update_one(
            {"id": property_id},
            {
                "$push": {"documents": doc_record},
                "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
            }
        )
        
        # Registar no histórico
        await db.properties.update_one(
            {"id": property_id},
            {
                "$push": {
                    "history": PropertyHistory(
                        timestamp=datetime.now(timezone.utc).isoformat(),
                        event=f"Documento adicionado: {file.filename} ({document_type})",
                        user=user.get("email")
                    ).model_dump()
                }
            }
        )
        
        return {
            "success": True,
            "document": doc_record,
            "message": f"Documento {file.filename} carregado com sucesso"
        }
    
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Erro ao carregar documento para imóvel {property_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Erro ao carregar documento: {str(e)}")


@router.get("/{property_id}/documents")
async def get_property_documents(
    property_id: str,
    document_type: str = None,
    user: dict = Depends(get_current_user)
):
    """
    Listar documentos de um imóvel.
    """
    prop = await db.properties.find_one(
        {"id": property_id},
        {"_id": 0, "documents": 1}
    )
    
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    documents = prop.get("documents", [])
    
    # Filtrar por tipo se especificado
    if document_type:
        documents = [d for d in documents if d.get("document_type") == document_type]
    
    return {
        "property_id": property_id,
        "total": len(documents),
        "documents": documents
    }


@router.delete("/{property_id}/documents/{document_id}")
async def delete_property_document(
    property_id: str,
    document_id: str,
    user: dict = Depends(get_current_user)
):
    """
    Remover documento de um imóvel.
    """
    from services.s3_service import delete_file_from_s3
    
    prop = await db.properties.find_one({"id": property_id})
    if not prop:
        raise HTTPException(status_code=404, detail="Imóvel não encontrado")
    
    # Encontrar documento
    document = None
    for doc in prop.get("documents", []):
        if doc.get("id") == document_id:
            document = doc
            break
    
    if not document:
        raise HTTPException(status_code=404, detail="Documento não encontrado")
    
    # Remover do S3
    if document.get("s3_key"):
        try:
            await delete_file_from_s3(document["s3_key"])
        except Exception as e:
            logger.warning(f"Erro ao remover do S3: {e}")
    
    # Remover do array
    await db.properties.update_one(
        {"id": property_id},
        {
            "$pull": {"documents": {"id": document_id}},
            "$set": {"updated_at": datetime.now(timezone.utc).isoformat()}
        }
    )
    
    # Registar no histórico
    await db.properties.update_one(
        {"id": property_id},
        {
            "$push": {
                "history": PropertyHistory(
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    event=f"Documento removido: {document.get('filename')}",
                    user=user.get("email")
                ).model_dump()
            }
        }
    )
    
    return {"success": True, "message": "Documento removido"}
