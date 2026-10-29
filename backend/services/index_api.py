"""Handlers da API do módulo Index (Lote 12, Fase 3) — `/api/index/*`.

A rota (`routes/index_module.py`) é um stub fino: autoriza o VERBO (`require_roles`),
a fronteira de rede é do router (`exigir_processo_no_ambito`, 404 igual ao de «não existe»)
e o estado fechado do processo também (`exigir_processo_editavel`, nas escritas).

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **Nada aqui bloqueia a indexação.** Analisar devolve já (`task_id`); IA em baixo, campos em
   dúvida ou alertas abertos nunca são erro para quem clica.
2. **Listas POSITIVAS** (DTO): a fila e a bancada mostram o que o ecrã precisa, nunca o
   documento do processo (`extra="allow"`, já vazou dados por aí). A fila NÃO leva os
   metadados profissionais; a bancada leva-os, porque é quem os revê.
3. **A fila só lista processos ACTIVOS** (Out 2026): fase não terminal NO WORKFLOW DA REDE
   DONA (`condicao_de_processo_activo`) — um processo concluído ou desistido não é trabalho
   de indexação. A fila mostra a empresa de origem (`company`), calculada ao servir.
   **A fila segue o âmbito de PROCESSOS** (dono + convidadas, `build_tenant_process_condition`):
   um Index da rede A nunca lista nem abre um processo da rede B, e o directório de entidades
   patronais é global PORQUE não leva dados de clientes (só NIF e nome da empresa).
4. **O estado lê-se do documento** (`index_status.derivar_estado`), nunca de um diff.
5. **Um erro de edição é 422 com motivo**, nunca um 500; um alerta que não é DESTE processo
   é 404 (o id de um alerta alheio não se confirma).
"""
from __future__ import annotations

import logging
from types import SimpleNamespace
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from models.task_log import TaskType
from services import index_jobs
from services import index_queue_query as consulta_da_fila
from services import index_status as estado_do_index
from services import index_store as store
from services.index_ai import TIPOS_ANALISADOS, tipo_do_documento
from services.index_ficheiros_do_s3 import registos_da_pasta_do_processo
from services.index_conversa import CAMPOS_DE_QUEM_CARREGOU, nomes_de_quem_carregou
from services.index_substituicao import ids_substituidos, titulares_e_substituidos
from services.partner_titulares import titulares_do_caso
from services.process_owner import calcular_empresa_dona
from services import tenant_network
from services.tenant_network import CAMPO_REDE, build_process_scope_condition, com_isolamento, rede_de_omissao
from services.workflow_phases import carregar_fases, nomes_terminais, redes_com_workflow

logger = logging.getLogger(__name__)

ABAS = ("pending", "reviews")

PROJECCAO_DA_FILA = {
    "_id": 0, "id": 1, "process_number": 1, "client_name": 1, "status": 1, "created_at": 1,
    "updated_at": 1, "index_status": 1, "index_skipped": 1, "is_indexed": 1, "skip_index": 1,
    "assigned_indexacao_id": 1, "has_pending_review": 1, "index_alerts_open": 1,
    "indexed_at": 1, "indexed_by_name": 1, "index_stagnation_alerted_at": 1,
    "company_id": 1, "company_name": 1, CAMPO_REDE: 1,
    # quem carregou o processo (coluna «Carregado por»)
    **{campo: 1 for campo in CAMPOS_DE_QUEM_CARREGOU},
}
PROJECCAO_DOS_FICHEIROS = {
    "_id": 0, "id": 1, "process_id": 1, "filename": 1, "s3_path": 1, "ai_category": 1,
    "ai_subcategory": 1, "ai_subtype": 1, "analysis_fingerprint": 1, "file_state": 1,
    "in_index_queue": 1, "created_at": 1, "clean_pdf_path": 1, "purge_after": 1, "is_clean_pdf": 1,
    "uploaded_by_index": 1, "index_type_override": 1, "index_classified_type": 1,
}


def _ficheiro_dto(doc: dict, substituidos: frozenset = frozenset(), titulares: Optional[dict] = None) -> dict[str, Any]:
    # o PDF limpo não se analisa: os factos vivem nos originais (senão contavam-se duas vezes)
    tipo = None if doc.get("is_clean_pdf") else tipo_do_documento(doc)
    return {
        "id": doc.get("id"),
        "filename": doc.get("filename"),
        "path": doc.get("s3_path"),
        "category": doc.get("ai_category"),
        "subcategory": doc.get("ai_subcategory"),
        "subtype": doc.get("ai_subtype"),
        "analysis_type": tipo if tipo in TIPOS_ANALISADOS else None,
        "analysed": bool(doc.get("analysis_fingerprint")),
        "file_state": doc.get("file_state") or "original",
        "in_index_queue": bool(doc.get("in_index_queue")),
        "has_clean_pdf": bool(doc.get("clean_pdf_path")),
        "is_clean_pdf": bool(doc.get("is_clean_pdf")),
        "uploaded_by_index": bool(doc.get("uploaded_by_index")),
        # comprovativo do cliente que o Index já voltou a carregar: não conta e só se vê a pedido
        "superseded": doc.get("id") in substituidos,
        "titular": (titulares or {}).get(doc.get("id")),
        "purge_after": doc.get("purge_after"),
        "created_at": doc.get("created_at"),
    }


def _processo_dto(proc: dict, ficheiros: Optional[list[dict]] = None) -> dict[str, Any]:
    estado = estado_do_index.derivar_estado(proc)
    saida = {
        "id": proc.get("id"),
        "process_number": proc.get("process_number"),
        "client_name": proc.get("client_name"),
        "status": proc.get("status"),
        "created_at": proc.get("created_at"),
        "updated_at": proc.get("updated_at"),
        "index_status": estado["index_status"],
        "index_skipped": estado["index_skipped"],
        "has_pending_review": bool(proc.get("has_pending_review")),
        "index_alerts_open": int(proc.get("index_alerts_open") or 0),
        "indexed_at": proc.get("indexed_at"),
        "indexed_by_name": proc.get("indexed_by_name"),
        # o SLA do Index avisou que este processo estagnou (sem actividade); limpa-se quando o indexador volta a mexer
        "stagnant": bool(proc.get("index_stagnation_alerted_at")) and estado["index_status"] == estado_do_index.IN_REVIEW,
    }
    if ficheiros is not None:
        saida["documents_total"] = len(ficheiros)
        saida["documents_to_analyse"] = sum(
            1 for f in ficheiros
            if f["analysis_type"] and not f["analysed"] and f["file_state"] != "purgado" and not f.get("superseded")
        )
    return saida


async def _carregar_processo(process_id: str, user: dict) -> dict:
    """O processo, já dentro do âmbito (o router o garantiu); 404 se não existe."""
    proc = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}}, {"_id": 0, **{k: 1 for k in (
            "id", "process_number", "client_name", "status", "created_at", "updated_at", "index_status",
            "index_skipped", "is_indexed", "skip_index", "assigned_indexacao_id", "indexacao_name", "has_pending_review",
            "index_alerts_open", "indexed_at", "indexed_by_name", "network_id", "index_stagnation_alerted_at",
            "second_client_id", "second_client_name", "titular2_data.name", "titular2_data.nome", "s3_folder")}},
    )
    if not proc:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    return proc


# ====================================================================
# A FILA
# ====================================================================
async def condicao_de_processo_activo() -> dict:
    """Só processos activos: fase NÃO terminal no workflow da rede DONA.

    O workflow é por rede e um mesmo nome pode fechar numa e não noutra, pelo que a condição
    é um `$or` por rede dona (e não um `$nin` com a união). Os processos por carimbar são da
    rede de omissão (`rede_do_processo`); sem ela, do modelo. `is_active: False` também
    exclui (campo legado, tolerante a ausente: a autoridade é a fase).
    """
    redes = [r for r in await redes_com_workflow() if r]
    omissao = rede_de_omissao()
    ramos: list[dict] = []
    for rede in redes:
        terminais = nomes_terminais(await carregar_fases(rede=rede))
        dona = {CAMPO_REDE: rede}
        if omissao == rede:
            dona = {"$or": [{CAMPO_REDE: rede}, {CAMPO_REDE: {"$in": [None, ""]}}]}
        ramos.append({"$and": [dona, {"status": {"$nin": terminais}}]})
    # as redes sem workflow próprio usam o MODELO (`rede=None`, dito de propósito: o inventário exige a rede)
    resto_terminais = nomes_terminais(await carregar_fases(rede=None))
    resto = {CAMPO_REDE: {"$nin": redes}}
    if omissao in redes:
        resto = {CAMPO_REDE: {"$nin": [*redes, None, ""]}}
    ramos.append({"$and": [resto, {"status": {"$nin": resto_terminais}}]})
    return {"$and": [{"is_active": {"$ne": False}}, {"$or": ramos}]}


async def _empresas_da_fila(processos: list[dict], scope) -> dict[str, Optional[dict]]:
    """`empresa` (nome + «é de outra rede») por processo, sem ids nem redes no DTO."""
    saida: dict[str, Optional[dict]] = {}
    for p in processos:
        try:
            dona = await calcular_empresa_dona(p, scope)
        except Exception as exc:  # noqa: BLE001 - enfeite de leitura: nunca derruba a fila
            logger.warning("[INDEX] empresa dona de %s: %s", p.get("id"), exc)
            dona = None
        saida[p["id"]] = (
            {"name": dona["company_name"], "other_network": bool(dona["e_de_outra_rede"])} if dona else None
        )
    return saida


async def _empresas_para_filtrar(base: dict) -> list[dict]:
    """As empresas que a fila TEM (id + nome + quantos), para o filtro do ecrã. Da fila inteira, sem filtros:
    as opções não encolhem à medida que se escolhe uma. Nunca levanta (é um enfeite de leitura)."""
    try:
        linhas = await db.processes.aggregate(
            [
                {"$match": {**base, "company_id": {"$nin": [None, ""]}}},
                {"$group": {"_id": "$company_id", "name": {"$first": "$company_name"}, "n": {"$sum": 1}}},
                {"$sort": {"name": 1, "_id": 1}},
                {"$limit": 100},
            ],
            maxTimeMS=5000,
        ).to_list(100)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Empresas da fila não listadas: %s", type(exc).__name__)
        return []
    return [{"id": str(l["_id"]), "name": l.get("name") or str(l["_id"]), "count": int(l.get("n") or 0)} for l in linhas]


async def run_get_index_queue(
    user: dict, *, tab: str, page: int = 1, size: int = 25, q: Optional[str] = None,
    sort_by: Optional[str] = None, index_status: Optional[str] = None,
    company_id: Optional[str] = None, origin: Optional[str] = None, mine: bool = False,
) -> dict[str, Any]:
    if tab not in ABAS:
        raise HTTPException(status_code=400, detail="Separador inválido")
    # tudo o que vem do pedido valida-se ANTES de tocar na base de dados (422, nunca «lista vazia»)
    campo, sentido, e_texto, ordem_normalizada = consulta_da_fila.validar_ordenacao(tab, sort_by)
    filtros = consulta_da_fila.validar_filtros(tab, index_status=index_status, company_id=company_id, origin=origin)
    # o âmbito resolve-se UMA vez: serve a condição da fila e o «é de outra rede» de cada linha
    scope = await tenant_network.resolve_vista_scope(user)
    rede = build_process_scope_condition(scope)
    base = com_isolamento(rede, {
        "$and": [
            {"is_deleted": {"$ne": True}},
            estado_do_index.condicao_da_fila(tab),
            await condicao_de_processo_activo(),
        ],
    })
    if mine:
        # «Os Meus Processos»: só o que está atribuído a quem pergunta. Sem id de utilizador a condição NUNCA
        # casa (`assigned_indexacao_id: None` casaria com todos os processos por atribuir — a lista de outra pessoa).
        meu = (user or {}).get("id")
        base = {"$and": [base, {"assigned_indexacao_id": meu} if meu else {"id": {"$in": []}}]}
    consulta = base
    dos_filtros = consulta_da_fila.condicao_dos_filtros(tab, filtros, scope)
    if dos_filtros:
        consulta = {"$and": [consulta, dos_filtros]}
    texto = (q or "").strip()
    if texto:
        import re

        consulta = {"$and": [consulta, {"$or": [
            {"client_name": {"$regex": re.escape(texto), "$options": "i"}},
            {"process_number": {"$regex": re.escape(texto), "$options": "i"}},
        ]}]}
    total = await db.processes.count_documents(consulta)
    pagina = max(1, page)
    tamanho = max(1, min(size, 100))
    cursor = db.processes.find(consulta, PROJECCAO_DA_FILA).sort(consulta_da_fila.ordem_mongo(campo, sentido))
    if e_texto:
        cursor = cursor.collation(consulta_da_fila.COLACAO)
    processos = await cursor.skip((pagina - 1) * tamanho).limit(tamanho).to_list(tamanho)

    ids = [p["id"] for p in processos]
    por_processo: dict[str, list[dict]] = {i: [] for i in ids}
    if ids:
        docs = await db.document_metadata.find(
            {"process_id": {"$in": ids}, "file_state": {"$ne": "purgado"}}, PROJECCAO_DOS_FICHEIROS
        ).to_list(5000)
        # só um processo onde o Index já carregou alguma coisa pode ter comprovativos do cliente substituídos
        com_uploads_do_index = {d.get("process_id") for d in docs if d.get("uploaded_by_index")}
        substituidos: set[str] = set()
        for pid in com_uploads_do_index:
            substituidos |= await ids_substituidos(pid)
        for d in docs:
            por_processo.setdefault(d.get("process_id"), []).append(_ficheiro_dto(d, frozenset(substituidos)))
    empresas = await _empresas_da_fila(processos, scope)
    carregadores = await nomes_de_quem_carregou(processos)
    return {
        "items": [
            {
                **_processo_dto(p, por_processo.get(p["id"], [])),
                "company": empresas.get(p["id"]),
                "loaded_by": carregadores.get(p["id"]),
            }
            for p in processos
        ],
        "total": total,
        "page": pagina,
        "size": tamanho,
        "tab": tab,
        "sort_by": ordem_normalizada,
        "filters": {k: v for k, v in filtros.items() if v},
        "facets": {
            "companies": await _empresas_para_filtrar(base),
            "statuses": list(consulta_da_fila.ESTADOS_POR_ABA[tab]),
        },
    }


# ====================================================================
# A BANCADA (workstation)
# ====================================================================
async def run_get_index_workstation(user: dict, process_id: str) -> dict[str, Any]:
    proc = await _carregar_processo(process_id, user)
    docs = await db.document_metadata.find(
        {"process_id": process_id, "file_state": {"$ne": "purgado"}}, PROJECCAO_DOS_FICHEIROS
    ).to_list(500)
    # a lista é a MESMA da aba Documentos (a pasta S3); os registos do processo fora dela não se perdem
    da_pasta = await registos_da_pasta_do_processo(proc, PROJECCAO_DOS_FICHEIROS)
    if da_pasta is not None:
        ja = {d.get("id") for d in da_pasta}
        docs = da_pasta + [d for d in docs if d.get("id") not in ja]
    titulares, substituidos = await titulares_e_substituidos(process_id, proc)
    ficheiros = [_ficheiro_dto(d, frozenset(substituidos), titulares) for d in docs]
    metadados = await store.carregar_metadados(process_id)
    alertas = await store.alertas_do_processo(process_id)
    # a última análise deste ficheiro falhou (alerta aberto): o ecrã di-lo na linha, ao lado de «Analisar»
    falhados = {
        r.get("document_id") for a in alertas
        if a.get("code") == "analise_falhou" and not a.get("dismissed_by_human") for r in (a.get("refs") or [])
    }
    for f in ficheiros:
        f["analysis_failed"] = not f["analysed"] and f["id"] in falhados
    jobs = {}
    for nome, tipo in (("analysis", TaskType.INDEX_ANALYSIS), ("finalize", TaskType.INDEX_FINALIZE),
                       ("sanitize", TaskType.INDEX_SANITIZE)):
        activo = await index_jobs.job_activo(process_id, tipo)
        jobs[nome] = (activo or {}).get("task_id")
    processo_dto = _processo_dto(proc, ficheiros)
    # o ecrã só arranca o tratamento se o processo é DELE (o servidor volta a decidir ao receber o pedido)
    dono = proc.get("assigned_indexacao_id") or None
    processo_dto["assigned_to_me"] = bool(dono) and dono == (user or {}).get("id")
    # sem acções cruzadas: num processo de outro indexador o ecrã do Index só consulta (o servidor recusa na mesma)
    processo_dto["assigned_to_other"] = bool(dono) and dono != (user or {}).get("id")
    processo_dto["assigned_indexacao_name"] = proc.get("indexacao_name") if dono else None
    # com 2.º titular o Index diz de quem é o que carrega (a substituição é por titular)
    processo_dto["titulares"] = titulares_do_caso(SimpleNamespace(e_processo=True, process=proc, client=None))
    return {
        "process": processo_dto,
        "files": ficheiros,
        "professional_metadata": {
            "jobs": (metadados or {}).get("jobs") or [],
            "has_pending_review": bool((metadados or {}).get("has_pending_review")),
            "updated_at": (metadados or {}).get("updated_at"),
        },
        "alerts": [
            {"id": a.get("id"), "code": a.get("code"), "severity": a.get("severity"), "message": a.get("message"),
             "detail": a.get("detail"), "refs": a.get("refs") or [], "dismissed": bool(a.get("dismissed_by_human")), "period": a.get("periodo")}
            for a in alertas
        ],
        "active_jobs": jobs,
    }


# ====================================================================
# ACÇÕES
# ====================================================================
async def run_start_work(user: dict, process_id: str) -> dict[str, Any]:
    """O indexador abriu a bancada: arranca o tratamento (`pending → in_review`) se o processo é DELE.

    Substitui o «Reivindicar» manual: a atribuição é automática e o estado «em tratamento» nasce de
    o indexador atribuído começar mesmo a trabalhar. Quem não é o atribuído (um diretor a espreitar)
    recebe `iniciado=False` e nada muda — ver `index_status.registar_trabalho`.
    """
    await _carregar_processo(process_id, user)
    resultado = await estado_do_index.registar_trabalho(process_id, user.get("id"))
    return {"success": True, **resultado}


async def run_assumir_processo(user: dict, process_id: str) -> dict[str, Any]:
    """«Atribuir a mim»: o indexador assume um processo POR INDEXAR que ninguém começou (Out 2026).

    O Index vê a rede inteira em «Todos os Processos» para trabalhar de forma proactiva. Regra da direcção:
    só se assume o que está «Por indexar» (de um colega que ainda não o abriu, ou sem ninguém); o que já está
    «Em tratamento» fica com quem o começou. A escrita é CONDICIONAL ao dono e ao estado lidos: se o colega
    abrir a bancada entre a leitura e a escrita, ganha quem trabalha (409) — como no SLA das 48 h.
    Stealth: sem histórico do processo, só auditoria. Assumir não é começar: o relógio das 48 h recomeça e
    o estado passa a «Em tratamento» quando o novo dono abrir a bancada.
    """
    proc = await _carregar_processo(process_id, user)
    meu_id = (user or {}).get("id")
    anterior = proc.get("assigned_indexacao_id") or None
    if anterior and anterior == meu_id:
        raise HTTPException(status_code=400, detail="Este processo já está atribuído a si.")
    if estado_do_index.derivar_estado(proc)["index_status"] != estado_do_index.PENDING:
        raise HTTPException(
            status_code=409,
            detail="Só pode assumir processos «Por indexar» que ainda ninguém começou.",
        )
    assumido = await estado_do_index.assumir(process_id, anterior, user)
    if not assumido:
        raise HTTPException(
            status_code=409,
            detail="O processo mudou entretanto (outro indexador começou a trabalhar nele). Actualize a página.",
        )
    await _auditar(user, process_id, "Processo assumido pelo Index", ["assigned_indexacao_id"])
    if anterior:
        try:
            from services.realtime_notifications import send_realtime_notification

            numero = proc.get("process_number") or str(process_id)[:8]
            await send_realtime_notification(
                anterior, "Processo assumido por um colega",
                f"O processo {numero} foi assumido por {user.get('name') or 'outro indexador'}.",
                "process_unassigned", process_id=process_id,
            )
        except Exception as exc:  # noqa: BLE001 — o aviso nunca desfaz a atribuição
            logger.warning("[INDEX] Aviso ao indexador anterior não enviado: %s", type(exc).__name__)
    return {"success": True, "assigned_indexacao_id": meu_id}


async def run_exigir_titularidade(user: dict, process_id: str, papel: str) -> None:
    """Guarda das escritas da bancada: o Index só age no que é seu (ver `index_status.exigir_titularidade`)."""
    estado_do_index.exigir_titularidade(await _carregar_processo(process_id, user), user, papel)


async def _trabalhou(user: dict, process_id: str) -> None:
    """Uma acção de escrita do Index: carimba a actividade (relógio da estagnação). Nunca levanta."""
    await estado_do_index.registar_trabalho(process_id, (user or {}).get("id"))


async def run_analyze_process(user: dict, process_id: str, *, force: bool = False) -> dict[str, Any]:
    """«Analisar» (`force=False`: só o que é novo ou mudou) e «Extrair dados» (`force=True`: tudo)."""
    await _carregar_processo(process_id, user)
    resultado = await index_jobs.iniciar_analise(process_id, user, force=force, gatilho="manual")
    await _trabalhou(user, process_id)
    return {
        "success": True,
        "task_id": resultado["task_id"],
        "started": resultado["iniciado"],
        "message": (
            "A análise está a correr em segundo plano; recebe uma notificação no fim."
            if resultado["iniciado"] else "Já há uma análise a correr neste processo."
        ),
    }


async def run_analyze_document(
    user: dict, process_id: str, document_id: str, *, tipo: Optional[str] = None
) -> dict[str, Any]:
    """«Analisar» na linha de UM ficheiro: lê-o de novo (ignora a impressão digital), mesmo que o tipo não se
    perceba pelo nome. `tipo` («Analisar como…») é a pessoa a dizer o que o ficheiro é: fica gravado e manda
    nas análises seguintes."""
    await _carregar_processo(process_id, user)
    doc = await db.document_metadata.find_one(
        {"id": document_id, "process_id": process_id},
        {"_id": 0, "id": 1, "file_state": 1, "is_clean_pdf": 1, "s3_path": 1},
    )
    if not doc:
        raise HTTPException(status_code=404, detail="Documento não encontrado neste processo.")
    if doc.get("file_state") == "purgado" or not doc.get("s3_path"):
        raise HTTPException(status_code=422, detail="O original deste documento já foi eliminado: não há o que ler.")
    if doc.get("is_clean_pdf"):
        raise HTTPException(status_code=422, detail="O PDF limpo não se analisa: analise o documento original.")
    if tipo is not None:
        await db.document_metadata.update_one({"id": document_id}, {"$set": {"index_type_override": tipo}})
    resultado = await index_jobs.iniciar_analise(
        process_id, user, force=True, gatilho="manual", documento_id=document_id
    )
    await _trabalhou(user, process_id)
    return {
        "success": True,
        "task_id": resultado["task_id"],
        "started": resultado["iniciado"],
        "message": (
            "O documento está a ser analisado em segundo plano; recebe uma notificação no fim."
            if resultado["iniciado"] else "Já há uma análise a correr neste processo. Tente quando terminar."
        ),
    }


async def run_sanitize_process(user: dict, process_id: str) -> dict[str, Any]:
    """«Apagar metadados do PDF»: PDF limpo dos ficheiros que o Index carregou. Corre em segundo plano."""
    from services import index_sanitize

    await _carregar_processo(process_id, user)
    resultado = await index_sanitize.iniciar_sanitizacao(process_id, user)
    await _trabalhou(user, process_id)
    return {
        "success": True,
        "task_id": resultado["task_id"],
        "started": resultado["iniciado"],
        "message": (
            "Os PDFs limpos estão a ser gerados em segundo plano; recebe uma notificação no fim. "
            "Os originais só são eliminados passada a margem de segurança."
            if resultado["iniciado"] else "Já há uma limpeza de PDFs a correr neste processo."
        ),
    }


async def run_edit_professional_job(
    user: dict, process_id: str, job_id: str, alteracoes: dict[str, Any]
) -> dict[str, Any]:
    proc = await _carregar_processo(process_id, user)
    try:
        modelo = await store.editar_trabalho(process_id, proc.get("network_id"), job_id, alteracoes)
    except store.EdicaoInvalida as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    await estado_do_index.gravar_contadores(process_id, has_pending_review=modelo.has_pending_review)
    await _auditar(user, process_id, "Metadados profissionais editados", sorted(alteracoes))
    await _trabalhou(user, process_id)
    alvo = next((j for j in modelo.jobs if j.job_id == job_id), None)
    return {
        "success": True,
        "job": alvo.model_dump(mode="json") if alvo else None,
        "has_pending_review": modelo.has_pending_review,
    }


async def run_set_file_titular(user: dict, process_id: str, document_id: str, titular: str) -> dict[str, Any]:
    """Corrige de quem é um ficheiro. Só com 2.º titular; vale para qualquer ficheiro do processo (também os do
    cliente: um recibo do 2.º enviado pela conta do 1.º). A próxima análise refaz os empregos por titular."""
    proc = await _carregar_processo(process_id, user)
    if not titulares_do_caso(SimpleNamespace(e_processo=True, process=proc, client=None)):
        raise HTTPException(status_code=422, detail="Este processo só tem um titular.")
    feito = await db.document_metadata.update_one(
        {"id": document_id, "process_id": process_id}, {"$set": {"titular": titular}}
    )
    if not feito.matched_count:
        raise HTTPException(status_code=404, detail="Documento não encontrado neste processo.")
    await _auditar(user, process_id, "Titular do documento corrigido", ["titular"])
    await _trabalhou(user, process_id)
    return {"success": True, "id": document_id, "titular": titular}


async def run_dismiss_alert(user: dict, process_id: str, alert_id: str) -> dict[str, Any]:
    await _carregar_processo(process_id, user)
    alerta = await store.dispensar_alerta(process_id, alert_id, user.get("id"))
    if alerta is None:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    abertos = await store.contar_alertas_abertos(process_id)
    await estado_do_index.gravar_contadores(process_id, index_alerts_open=abertos)
    await _auditar(user, process_id, "Alerta do Index dispensado", [alerta.get("code") or ""])
    await _trabalhou(user, process_id)
    return {"success": True, "alerts_open": abertos}


async def run_search_employers(user: dict, q: str) -> dict[str, Any]:
    return {"items": await store.procurar_entidades(q)}


async def _auditar(user: dict, process_id: str, accao: str, campos: list[str]) -> None:
    """Rasto de auditoria SÓ com nomes de campos/códigos, nunca valores. Nunca levanta."""
    try:
        from services.audit_trail_service import log_audit_event

        await log_audit_event(
            process_id=process_id, user=user, action=accao, field=", ".join(campos) or None,
            metadata={"origem": "index"},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Auditoria não gravada: %s", type(exc).__name__)
