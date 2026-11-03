"""
====================================================================
AVISOS DE ROTINA — processos parados, documentos a expirar, lembrete mensal
====================================================================
Regras do Flavio (Nov 2026, thread «Reduzir notificações a mais»):

1. Processos parados: um RESUMO por pessoa («Tem 5 processos parados.
   URGENTE rever»), nunca um aviso por processo. Cada processo conta para
   um resumo só uma vez quando passa os 7 dias e outra quando passa os 14
   (não todos os dias). Vai a quem está atribuído (consultor e
   intermediário).
2. A gestão (Diretor/CEO) recebe o seu resumo dos processos parados há mais
   de 21 dias — só os da SUA EMPRESA.
3. Só processos activos no motor (as fases finais configuradas não contam)
   e nunca eliminados. Antes havia uma lista de estados finais escrita à mão
   que deixava escapar `perdido`, `arquivo` e as fases finais criadas no
   motor.
4. Documentos a expirar: um aviso aos 60 dias, outro aos 7 e outro no dia,
   e os documentos do mesmo cliente juntam-se num só aviso.
5. Lembrete mensal: ao dia 25 (já se pode pedir o recibo e o extrato do mês
   corrente), um só aviso por pessoa, e só uma vez por mês (o job corre de
   hora a hora: antes repetia-se 24 vezes no dia 1).
6. Nenhum destes vai para o Telegram (`telegram_notifications.TIPOS_SEM_TELEGRAM`).

O que já foi avisado fica em `avisos_de_rotina` (uma marca por processo /
documento / nível), para não repetir.
====================================================================
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

COLECCAO = "avisos_de_rotina"

DIAS_PARADO_URGENTE = 7
DIAS_PARADO_ATRASADO = 14
DIAS_PARADO_GESTAO = 21
PAPEIS_DA_GESTAO = ("diretor", "ceo")

NIVEIS_DE_VALIDADE = (60, 7, 0)
DIA_DO_LEMBRETE_MENSAL = 25

MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril", 5: "Maio", 6: "Junho",
    7: "Julho", 8: "Agosto", 9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def _data(valor: Any) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    texto = _texto(valor)
    if not texto:
        return None
    try:
        data = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        try:
            data = datetime.strptime(texto[:10], "%Y-%m-%d")
        except ValueError:
            return None
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def consultores_e_intermediarios(processo: dict) -> list[str]:
    """Quem está atribuído ao processo, sem o Index (o processo parado é trabalho deles)."""
    from services.alert_audience import ids_atribuidos

    index = _texto(processo.get("assigned_indexacao_id"))
    return [uid for uid in ids_atribuidos(processo) if uid != index]


async def reclamar(bd, chave: str, agora: datetime) -> bool:
    """Marca `chave` como avisada. Devolve True só da primeira vez."""
    resultado = await bd[COLECCAO].update_one(
        {"chave": chave},
        {"$setOnInsert": {"chave": chave, "criado_em": agora.isoformat()}},
        upsert=True,
    )
    return resultado.upserted_id is not None


async def processos_activos(bd, filtro: Optional[dict] = None, limite: int = 5000) -> list[dict]:
    """Processos não eliminados numa fase ACTIVA do workflow da rede dona (o motor decide)."""
    from services.workflow_phases import nomes_activos_de_todas_as_redes, so_processos_com_fase_activa

    activos = await nomes_activos_de_todas_as_redes()
    if not activos:
        return []
    condicoes = [{"status": {"$in": activos}}, {"is_deleted": {"$ne": True}}]
    if filtro:
        condicoes.append(filtro)
    processos = await bd.processes.find({"$and": condicoes}, {"_id": 0}).to_list(limite)
    return await so_processos_com_fase_activa(processos)


# ====================================================================
# 1–3. PROCESSOS PARADOS
# ====================================================================

def _plural(n: int, singular: str, plural: str) -> str:
    return singular if n == 1 else plural


def mensagem_de_parados(atrasados: int, urgentes: int) -> str:
    total = atrasados + urgentes
    partes = []
    if atrasados:
        partes.append(f"{atrasados} há mais de {DIAS_PARADO_ATRASADO} dias")
    if urgentes:
        partes.append(f"{urgentes} há mais de {DIAS_PARADO_URGENTE} dias")
    return (
        f"⚠️ Tem {total} {_plural(total, 'processo parado', 'processos parados')}. URGENTE rever."
        + (f" ({', '.join(partes)})" if partes else "")
    )


def mensagem_de_parados_da_gestao(total: int) -> str:
    return (
        f"⚠️ A sua empresa tem {total} {_plural(total, 'processo parado', 'processos parados')} "
        f"há mais de {DIAS_PARADO_GESTAO} dias. URGENTE rever."
    )


async def avisar_processos_parados(servico, agora: Optional[datetime] = None) -> int:
    """Um resumo por pessoa quando algum dos seus processos passa os 7 ou os 14 dias parado.

    Devolve quantos resumos foram criados.
    """
    from services.alert_audience import gestao_do_processo

    bd = servico.db
    agora = agora or datetime.now(timezone.utc)
    limite = (agora - timedelta(days=DIAS_PARADO_URGENTE)).isoformat()
    processos = await processos_activos(bd, {"$or": [
        {"updated_at": {"$lte": limite}},
        {"updated_at": {"$exists": False}, "created_at": {"$lte": limite}},
        {"updated_at": None, "created_at": {"$lte": limite}},
    ]})

    por_pessoa: dict[str, dict[str, int]] = {}
    com_novidade: set[str] = set()
    gestao: dict[str, int] = {}
    gestao_com_novidade: set[str] = set()

    for processo in processos:
        referencia = processo.get("updated_at") or processo.get("created_at")
        desde = _data(referencia)
        if not desde:
            continue
        dias = (agora - desde).days
        if dias < DIAS_PARADO_URGENTE:
            continue
        nivel = DIAS_PARADO_ATRASADO if dias >= DIAS_PARADO_ATRASADO else DIAS_PARADO_URGENTE
        pid = _texto(processo.get("id"))
        novo = await reclamar(bd, f"parado:{pid}:{_texto(referencia)}:{nivel}", agora)

        for uid in consultores_e_intermediarios(processo):
            contagem = por_pessoa.setdefault(uid, {"atrasados": 0, "urgentes": 0})
            contagem["atrasados" if nivel == DIAS_PARADO_ATRASADO else "urgentes"] += 1
            if novo:
                com_novidade.add(uid)

        if dias > DIAS_PARADO_GESTAO:
            novo_na_gestao = await reclamar(bd, f"parado_gestao:{pid}:{_texto(referencia)}", agora)
            for uid in await gestao_do_processo(processo, PAPEIS_DA_GESTAO):
                gestao[uid] = gestao.get(uid, 0) + 1
                if novo_na_gestao:
                    gestao_com_novidade.add(uid)

    criados = 0
    for uid in sorted(com_novidade):
        contagem = por_pessoa[uid]
        if await servico.create_notification(
            user_id=uid,
            message=mensagem_de_parados(contagem["atrasados"], contagem["urgentes"]),
            notification_type="processos_parados",
            link="/processos",
        ):
            criados += 1
    for uid in sorted(gestao_com_novidade):
        if await servico.create_notification(
            user_id=uid,
            message=mensagem_de_parados_da_gestao(gestao[uid]),
            notification_type="processos_parados_gestao",
            link="/processos",
        ):
            criados += 1
    logger.info(
        "Processos parados: %s processos, %s resumos criados", len(processos), criados,
    )
    return criados


# ====================================================================
# 4. DOCUMENTOS A EXPIRAR
# ====================================================================

def nivel_de_validade(dias: int) -> Optional[int]:
    """O nível (60, 7 ou 0 dias) em que o documento está, ou None fora da janela."""
    if dias == 0:
        return 0
    if 1 <= dias <= 7:
        return 7
    if 8 <= dias <= 60:
        return 60
    return None


def _quando(dias: int, data: datetime) -> str:
    if dias == 0:
        return "expira hoje"
    return f"expira a {data.strftime('%d/%m/%Y')} ({dias} {_plural(dias, 'dia', 'dias')})"


def mensagem_de_validades(cliente: str, documentos: list[tuple[str, int, datetime]]) -> str:
    documentos = sorted(documentos, key=lambda d: d[1])
    if len(documentos) == 1:
        nome, dias, data = documentos[0]
        return f"📄 {nome} de {cliente} {_quando(dias, data)}"
    linhas = "; ".join(f"{nome} {_quando(dias, data)}" for nome, dias, data in documentos)
    return f"📄 {len(documentos)} documentos de {cliente} a expirar: {linhas}"


async def avisar_documentos_a_expirar(servico, agora: Optional[datetime] = None) -> int:
    """Um aviso por (pessoa, cliente) com todos os documentos que entraram num nível novo."""
    bd = servico.db
    agora = agora or datetime.now(timezone.utc)
    hoje = agora.replace(hour=0, minute=0, second=0, microsecond=0)

    processos = {p["id"]: p for p in await processos_activos(bd) if p.get("id")}
    if not processos:
        return 0

    candidatos: list[tuple[dict, str, str, Any]] = []  # (processo, chave do documento, nome, validade)
    metadados = await bd.document_metadata.find(
        {
            "process_id": {"$in": list(processos)},
            "expiry_date": {
                "$ne": None,
                "$gte": hoje.strftime("%Y-%m-%d"),
                "$lte": (hoje + timedelta(days=60)).strftime("%Y-%m-%d"),
            },
            "is_deleted": {"$ne": True},
        },
        {"_id": 0},
    ).to_list(5000)
    for doc in metadados:
        nome = doc.get("ai_category") or doc.get("ai_subcategory") or doc.get("filename") or "Documento"
        candidatos.append((processos[doc["process_id"]], f"meta:{doc.get('id')}", nome, doc.get("expiry_date")))
    for processo in processos.values():
        for i, doc in enumerate(processo.get("documents") or []):
            if isinstance(doc, dict) and doc.get("expiry_date"):
                chave = f"proc:{processo['id']}:{doc.get('id') or i}"
                candidatos.append((processo, chave, doc.get("name") or "Documento", doc.get("expiry_date")))

    grupos: dict[tuple[str, str], dict] = {}
    for processo, chave, nome, validade in candidatos:
        data = _data(validade)
        if not data:
            continue
        data = data.replace(hour=0, minute=0, second=0, microsecond=0)
        dias = (data - hoje).days
        nivel = nivel_de_validade(dias)
        if nivel is None:
            continue
        if not await reclamar(bd, f"validade:{chave}:{_texto(validade)[:10]}:{nivel}", agora):
            continue
        cliente_chave = _texto(processo.get("client_id")) or _texto(processo.get("id"))
        for uid in consultores_e_intermediarios(processo):
            grupo = grupos.setdefault((uid, cliente_chave), {
                "processo": processo, "documentos": [],
            })
            grupo["documentos"].append((nome, dias, data))

    criados = 0
    for (uid, _cliente), grupo in grupos.items():
        processo = grupo["processo"]
        cliente = processo.get("client_name") or "Cliente"
        if await servico.create_notification(
            user_id=uid,
            message=mensagem_de_validades(cliente, grupo["documentos"]),
            notification_type="documentos_a_expirar",
            process_id=processo.get("id"),
            client_name=cliente,
            link=f"/process/{processo.get('id')}",
        ):
            criados += 1
    logger.info("Documentos a expirar: %s avisos criados", criados)
    return criados


# ====================================================================
# 5. LEMBRETE MENSAL
# ====================================================================

def mensagem_do_lembrete_mensal(mes: str, clientes: int) -> str:
    return (
        f"📄 Peça o recibo de vencimento e o extrato bancário de {mes} a "
        f"{clientes} {_plural(clientes, 'cliente', 'clientes')} com processo activo."
    )


async def lembrete_mensal_ja_feito(bd, agora: datetime) -> bool:
    """Reclama o lembrete deste mês. True se já tinha sido feito."""
    return not await reclamar(bd, f"lembrete_mensal:{agora.strftime('%Y-%m')}", agora)
