"""Calendário visual do Dashboard (Bloco 4, pontos 29 e 32).

Mostra, num mês, as MARCAÇÕES, as datas de ESCRITURA e de CPCV e as
AUSÊNCIAS da equipa — numa só chamada pequena, para um componente simples.

DE ONDE VÊM AS DATAS (e porque não bastava o calendário existente)
  * As marcações e as ausências são eventos do calendário (`deadlines`) e
    vêm do MESMO serviço da página do Calendário (`run_get_calendar_deadlines`):
    a visibilidade — a rede, a empresa activa, a agenda pessoal do consultor
    contra a da equipa da gestão — é decidida num sítio só. Ganhou uma
    JANELA de datas para não trazer o calendário inteiro para pintar um mês.
  * As datas de escritura e de CPCV **não são eventos**: vivem no processo
    (`real_estate_data.data_escritura_prevista` / `data_cpcv`). Um calendário
    que só lesse `deadlines` não as mostrava nunca. Lêem-se aqui, com a MESMA
    visibilidade das listagens de processos (`build_process_list_query` com a
    condição de rede de PROCESSOS, que inclui os partilhados).

REGRAS
  * Classificação por categoria num só sítio (`categoria_do_evento`): o
    ecrã não adivinha a partir do título.
  * Um evento «Escritura …» já criado à mão para o mesmo processo e dia NÃO
    se duplica com a data do processo.
  * Datas só em `AAAA-MM-DD`: um texto noutro formato não casa com a janela
    e fica de fora — dito, não escondido (campo `nota`).
  * Tectos: 1000 eventos (o do calendário) e 300 processos por mês.
"""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import HTTPException, Request

from database import db

LIMITE_DE_PROCESSOS = 300

CAT_ESCRITURA = "escritura"
CAT_CPCV = "cpcv"
CAT_MARCACAO = "marcacao"
CAT_AUSENCIA = "ausencia"
CAT_PRAZO = "prazo"
CATEGORIAS = (CAT_ESCRITURA, CAT_CPCV, CAT_MARCACAO, CAT_AUSENCIA, CAT_PRAZO)

NOTA_DE_FORMATO = (
    "Só as datas de escritura e de CPCV gravadas como AAAA-MM-DD aparecem no calendário."
)

_MES = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")


def janela_do_mes(mes: Optional[str], *, hoje: Optional[date] = None) -> tuple[date, date]:
    """`[1.º dia, 1.º dia do mês seguinte[` do mês `AAAA-MM` (omissão: o actual)."""
    hoje = hoje or date.today()
    if mes:
        m = _MES.match(str(mes).strip())
        if not m:
            raise ValueError("month inválido. Use AAAA-MM")
        ano, numero = int(m.group(1)), int(m.group(2))
    else:
        ano, numero = hoje.year, hoje.month
    inicio = date(ano, numero, 1)
    seguinte = date(ano + (numero == 12), 1 if numero == 12 else numero + 1, 1)
    return inicio, seguinte


def categoria_do_evento(evento: dict) -> str:
    """Categoria de um evento do calendário. Pura.

    `type=absence` é ausência; um título/descrição com «escritura» ou «cpcv»
    é dessa categoria; visita/marcação/reunião (ou `type=event`) é marcação;
    o resto é um prazo.
    """
    tipo = str(evento.get("type") or "").lower()
    if tipo == "absence":
        return CAT_AUSENCIA
    texto = f"{evento.get('title') or ''} {evento.get('description') or ''}".lower()
    if "escritura" in texto:
        return CAT_ESCRITURA
    if "cpcv" in texto:
        return CAT_CPCV
    if tipo == "event" or any(p in texto for p in ("visita", "marcação", "marcacao", "reunião", "reuniao")):
        return CAT_MARCACAO
    return CAT_PRAZO


def dias_do_evento(evento: dict, inicio: date, fim_exclusivo: date) -> list[str]:
    """Os dias `AAAA-MM-DD` do evento que caem no mês (multi-dia incluído)."""
    comeco = _como_data(evento.get("due_date"))
    if comeco is None:
        return []
    fim = _como_data(evento.get("end_date")) or comeco
    if fim < comeco:
        fim = comeco
    dias = []
    dia = max(comeco, inicio)
    ultimo = min(fim, fim_exclusivo - timedelta(days=1))
    while dia <= ultimo:
        dias.append(dia.isoformat())
        dia += timedelta(days=1)
    return dias


def _como_data(valor: Any) -> Optional[date]:
    texto = str(valor or "")[:10]
    try:
        return date.fromisoformat(texto)
    except ValueError:
        return None


def _hora(evento: dict) -> Optional[str]:
    texto = str(evento.get("due_date") or "")
    if evento.get("all_day") or len(texto) < 16 or "T" not in texto:
        return None
    return texto[11:16]


def item_de_evento(evento: dict, dia: str) -> dict:
    categoria = categoria_do_evento(evento)
    return {
        "id": f"{evento.get('id')}:{dia}",
        "dia": dia,
        "categoria": categoria,
        "titulo": evento.get("title") or "",
        "hora": _hora(evento),
        "todo_o_dia": bool(evento.get("all_day")),
        "origem": "evento",
        "process_id": evento.get("process_id") or None,
        "client_id": evento.get("client_id") or None,
        "client_name": (evento.get("client_name") if categoria != CAT_AUSENCIA else "") or "",
        "responsavel": evento.get("responsible_name") or None,
    }


def itens_do_processo(processo: dict, inicio: date, fim_exclusivo: date) -> list[dict]:
    """A escritura e o CPCV de um processo que caem no mês."""
    dados = processo.get("real_estate_data") or {}
    itens = []
    for campo, categoria, rotulo in (
        ("data_escritura_prevista", CAT_ESCRITURA, "Escritura"),
        ("data_cpcv", CAT_CPCV, "CPCV"),
    ):
        dia = _como_data(dados.get(campo))
        if dia is None or not (inicio <= dia < fim_exclusivo):
            continue
        numero = processo.get("process_number")
        itens.append({
            "id": f"{processo.get('id')}:{campo}",
            "dia": dia.isoformat(),
            "categoria": categoria,
            "titulo": f"{rotulo}" + (f" · processo #{numero}" if numero is not None else ""),
            "hora": None,
            "todo_o_dia": True,
            "origem": "processo",
            "process_id": processo.get("id"),
            "client_id": processo.get("client_id") or None,
            "client_name": processo.get("client_name") or "",
            "responsavel": None,
        })
    return itens


def sem_duplicados(eventos: list[dict], do_processo: list[dict]) -> list[dict]:
    """Tira o que o processo diz e um evento criado à mão já diz."""
    ja_ha = {(i["categoria"], i["process_id"], i["dia"]) for i in eventos if i["process_id"]}
    return [i for i in do_processo if (i["categoria"], i["process_id"], i["dia"]) not in ja_ha]


def contagens(itens: list[dict]) -> dict[str, int]:
    return {c: sum(1 for i in itens if i["categoria"] == c) for c in CATEGORIAS}


async def _processos_do_mes(user: dict, request: Optional[Request], inicio: date, fim_exclusivo: date) -> list[dict]:
    from services.auth import get_all_user_roles, get_effective_role
    from services.process_list_filters import build_process_list_query
    from services.tenant_network import build_tenant_process_condition
    from services.workflow_phases import carregar_fases, nomes_terminais

    papel = get_effective_role(request, user) if request is not None else (user.get("role") or "")
    consulta = build_process_list_query(
        user, papel,
        tenant_condition=await build_tenant_process_condition(user),
        view_mode="active_only",
        show_all=False,
        all_roles=get_all_user_roles(user),
        terminais=nomes_terminais(await carregar_fases()),
    )
    desde, ate = inicio.isoformat(), fim_exclusivo.isoformat()
    janela = {"$or": [
        {"real_estate_data.data_escritura_prevista": {"$gte": desde, "$lt": ate}},
        {"real_estate_data.data_cpcv": {"$gte": desde, "$lt": ate}},
    ]}
    return await db.processes.find(
        {"$and": [consulta, janela]},
        {"_id": 0, "id": 1, "process_number": 1, "client_id": 1, "client_name": 1,
         "real_estate_data.data_escritura_prevista": 1, "real_estate_data.data_cpcv": 1},
    ).to_list(LIMITE_DE_PROCESSOS)


async def run_dashboard_calendar(user: dict, request: Optional[Request] = None, month: Optional[str] = None) -> dict:
    """Os itens do mês, por dia, e as contagens por categoria."""
    from services.deadlines_api_calendar import run_get_calendar_deadlines

    try:
        inicio, fim_exclusivo = janela_do_mes(month)
    except ValueError as erro:
        raise HTTPException(status_code=422, detail=str(erro))

    eventos = await run_get_calendar_deadlines(
        None, None, user, request, desde=inicio.isoformat(), ate=fim_exclusivo.isoformat(),
    )
    itens_de_eventos = [
        item_de_evento(e, dia)
        for e in eventos
        for dia in dias_do_evento(e, inicio, fim_exclusivo)
    ]
    processos = await _processos_do_mes(user, request, inicio, fim_exclusivo)
    do_processo = sem_duplicados(
        itens_de_eventos,
        [i for p in processos for i in itens_do_processo(p, inicio, fim_exclusivo)],
    )
    itens = sorted(itens_de_eventos + do_processo, key=lambda i: (i["dia"], i["hora"] or "", i["categoria"]))
    return {
        "month": f"{inicio.year:04d}-{inicio.month:02d}",
        "dias_no_mes": calendar.monthrange(inicio.year, inicio.month)[1],
        "itens": itens,
        "contagens": contagens(itens),
        "truncado": len(processos) >= LIMITE_DE_PROCESSOS,
        "nota": NOTA_DE_FORMATO,
    }
