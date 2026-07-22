"""Excel bulk import, jobs, and template.

Extraído de `routes/properties.py`.
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime, timezone

from fastapi import HTTPException, UploadFile

from database import db
from services.background_jobs import background_jobs, JobType, JobStatus
from utils.input_sanitization import (
    sanitize_string, sanitize_name, sanitize_email, sanitize_phone, sanitize_html,
)
from services.property_helpers import get_next_reference

logger = logging.getLogger(__name__)


async def run_import_properties_from_excel(
    file: UploadFile,
    user: dict
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


async def _process_excel_import(
    job_id: str,
    df,
    filename: str,
    user: dict
):
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
            
            # Actualizar progresso a cada 5 linhas para não sobrecarregar
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
                    """Obtém o valor de uma coluna do Excel, tentando múltiplas chaves.

                    Útil quando o Excel pode ter variações no nome das colunas
                    (ex: "titulo" ou "título"). Aceita string única ou lista.

                    Args:
                        keys: Nome da coluna (str) ou lista de nomes a tentar.
                        default: Valor a retornar se nenhum for encontrado.

                    Returns:
                        str: Primeiro valor não-vazio encontrado, ou default.
                    """
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
                    """Converte uma string de preço para float.

                    Suporta formatos europeus (700.000,00€, 700 000€) e americanos
                    (700000.00). Remove o símbolo €, trata separadores de milhares
                    e decimais automaticamente.

                    Args:
                        price_str: String de preço ou valor pandas.

                    Returns:
                        float: Valor numérico do preço, ou None se inválido.
                    """
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
                    """Extrai o número de quartos de uma tipologia T{N}.

                    Exemplos: "T2" → 2, "t3" → 3, "Studio" → None.

                    Args:
                        tipologia: String de tipologia (ex: "T2", "T0+1").

                    Returns:
                        int: Número de quartos, ou None se não for parseável.
                    """
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
                    """Converte um valor para float, tratando formato europeu.

                    Substitui vírgula decimal por ponto antes de converter.

                    Args:
                        val: Valor numérico, string ou valor pandas.

                    Returns:
                        float: Valor convertido, ou None se inválido.
                    """
                    if pd.isna(val):
                        return None
                    try:
                        return float(str(val).replace(',', '.').strip())
                    except (ValueError, TypeError):
                        return None
                
                def parse_int(val):
                    """Converte um valor para int, tratando formato europeu.

                    Primeiro converte para float (para handle decimais residuais),
                    depois para int.

                    Args:
                        val: Valor numérico, string ou valor pandas.

                    Returns:
                        int: Valor convertido, ou None se inválido.
                    """
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
                    "title": sanitize_string(titulo, max_length=300),
                    "description": sanitize_html(get_value(['descricao'])) if get_value(['descricao']) else None,
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
                        "name": sanitize_name(proprietario_nome),
                        "phone": sanitize_phone(get_value(['proprietario_telefone'])) or None,
                        "email": sanitize_email(get_value(['proprietario_email'])) or None
                    },
                    "agency": get_value(['agencia']) or None,
                    "photos": [],
                    "documents": [],
                    "status": "em_analise",
                    "notes": sanitize_string(get_value(['notas', 'observações']), max_length=1000) if get_value(['notas', 'observações']) else None,
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


async def run_get_import_job_status(
    job_id: str,
    user: dict
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


async def run_get_user_import_jobs(
    user: dict,
    limit: int = 20
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


async def run_get_import_template(user: dict):
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
