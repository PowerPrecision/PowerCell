"""
Âmbito do Webmail por EMPRESA (Ponto 8, Fase 1 — a Parede de Betão).

O PROBLEMA QUE ISTO FECHA
    `services/email_webmail.py` não tinha uma única ocorrência de
    `network_id` nem de `tenant`: o Webmail ficou inteiramente fora do
    isolamento multi-tenant erguido no Lote 4. Pior — o
    `resolve_ucr_mailbox_filter` devolvia `None` em três caminhos (caixa
    `general`, caixa `shared_indexacao`, e âmbito sem cláusulas) e o
    chamador fazia `if ucr_filter:`. `None` não significava "sem
    empresa": significava **sem filtro nenhum**. Somado ao
    `can_see_all` de admin/ceo/diretor, uma Diretora da Domus a abrir a
    Caixa Geral lia a colecção `emails` inteira, Power/Precision
    incluída.

    É o mesmo `None` = "sem filtro" que o `build_network_scope_condition`
    foi escrito para nunca produzir. **Aqui também não há `None`.**

A REGRA
    A caixa de correio é da EMPRESA. Um separador do Webmail é uma
    empresa, e o âmbito desse separador é, no máximo:

        company_id == <empresa>
        OU  (account ∈ <contas dessa empresa>  E  sem company_id)

    O segundo ramo existe só para a PILHA POR CARIMBAR: o
    `email_service` grava `company_id` condicionalmente
    (`if company_id:`), por isso há emails antigos sem carimbo cuja
    única prova de pertença é o endereço da caixa que os sincronizou.
    Exige `sem company_id` de propósito — sem isso, um email carimbado
    para a Domus apareceria no separador da Power caso o mesmo endereço
    estivesse configurado nas duas empresas. Um carimbo explícito manda
    sempre sobre a dedução pelo endereço.

PORQUE NÃO SE JUNTA AQUI O `build_tenant_condition`
    Seria redundante e, pior, perigoso. Um separador É uma empresa, e
    uma empresa pertence a uma rede: filtrar por empresa é ESTRITAMENTE
    mais apertado do que filtrar por rede. E a empresa pedida é validada
    contra os UCRs do utilizador (`assert_empresa_no_ambito`, 404), logo
    nenhum separador pode sequer nomear uma empresa de outra rede.
    Juntar por cima a condição de rede só acrescentaria um caso: esconder
    a pilha por carimbar a quem não detém a rede de omissão — emails cujo
    endereço da conta JÁ prova a que empresa pertencem. Isolamento de
    rede garantido por construção; nenhum email legítimo desaparece.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from database import db
from services.tenant_network import CONDICAO_IMPOSSIVEL, VALORES_SEM_EMPRESA

logger = logging.getLogger(__name__)

# Cargos com direito à Caixa Geral da empresa. Espelha
# `email_config_resolver.CAIXA_GERAL_ACCESS_ROLES`; importado em uso para
# não duplicar o conjunto.
MAX_EMPRESAS = 50


@dataclass(frozen=True)
class EmpresaDoWebmail:
    """Uma empresa a que o utilizador tem acesso — um separador."""

    company_id: str
    company_name: str
    papeis: frozenset = field(default_factory=frozenset)

    @property
    def tem_caixa_geral(self) -> bool:
        from services.email_config_resolver import CAIXA_GERAL_ACCESS_ROLES

        return bool(self.papeis & set(CAIXA_GERAL_ACCESS_ROLES))


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def _endereco(valor: Any) -> str:
    return _texto(valor).lower()


async def empresas_do_webmail(user: dict) -> list[EmpresaDoWebmail]:
    """
    Empresas onde o utilizador tem um UCR válido — os separadores.

    É esta lista que define o que ele pode sequer PEDIR. Um separador
    nunca nomeia uma empresa que ele não tenha, por isso o isolamento
    entre redes fica garantido antes de a query existir.

    Degradação graciosa: falha de I/O devolve `[]`, e um Webmail sem
    separadores mostra vazio em vez de mostrar tudo — falha fechada.
    """
    user_id = _texto((user or {}).get("id"))
    if not user_id:
        return []

    por_empresa: dict[str, set] = {}
    try:
        ucrs = await db.user_company_roles.find(
            {
                "user_id": user_id,
                "is_deleted": {"$ne": True},
                "is_active": {"$ne": False},
            },
            {"_id": 0, "company_id": 1, "company_name": 1, "role": 1},
        ).to_list(MAX_EMPRESAS)
    except Exception as exc:
        logger.warning("[WebmailScope] Falha a listar UCRs de %s: %s", user_id, exc)
        return []

    nomes: dict[str, str] = {}
    for ucr in ucrs:
        cid = _texto(ucr.get("company_id"))
        if not cid or cid in VALORES_SEM_EMPRESA:
            continue
        por_empresa.setdefault(cid, set())
        papel = _texto(ucr.get("role")).lower()
        if papel:
            por_empresa[cid].add(papel)
        nome = _texto(ucr.get("company_name"))
        if nome and cid not in nomes:
            nomes[cid] = nome

    if not por_empresa:
        return []

    # O nome da empresa vem da colecção `companies` quando existe. Um id
    # cru no separador leria como lixo para o utilizador — foi o defeito
    # que o `resolveActiveCompanyName` corrigiu no menu (ponto 12).
    try:
        docs = await db.companies.find(
            {"id": {"$in": list(por_empresa)}},
            {"_id": 0, "id": 1, "name": 1},
        ).to_list(MAX_EMPRESAS)
        for doc in docs:
            cid = _texto(doc.get("id"))
            nome = _texto(doc.get("name"))
            if cid and nome:
                nomes[cid] = nome
    except Exception as exc:
        logger.warning("[WebmailScope] Falha a ler nomes de empresas: %s", exc)

    return [
        EmpresaDoWebmail(
            company_id=cid,
            company_name=nomes.get(cid) or cid,
            papeis=frozenset(papeis),
        )
        for cid, papeis in sorted(por_empresa.items(), key=lambda p: nomes.get(p[0], p[0]).lower())
    ]


async def assert_empresa_no_ambito(user: dict, company_id: str) -> EmpresaDoWebmail:
    """
    A empresa pedida é uma das do utilizador?

    Raises:
        HTTPException(404): não é. **404 e não 403**, como no CRUD de
            automações e nas notificações: distinguir "não existe" de
            "não é tua" confirmaria que aquele id de empresa existe, e
            os ids das empresas da concorrência são exactamente o que
            não se revela.
    """
    from fastapi import HTTPException

    pedida = _texto(company_id)
    if not pedida:
        raise HTTPException(status_code=404, detail="Empresa não encontrada")

    for empresa in await empresas_do_webmail(user):
        if empresa.company_id == pedida:
            return empresa

    logger.warning(
        "[WebmailScope] Utilizador %s pediu a caixa da empresa %s, fora do seu âmbito.",
        _texto((user or {}).get("id")), pedida,
    )
    raise HTTPException(status_code=404, detail="Empresa não encontrada")


async def contas_pessoais_da_empresa(user_id: str, company_id: str) -> set[str]:
    """Endereços que o utilizador configurou NESTA empresa."""
    uid, cid = _texto(user_id), _texto(company_id)
    if not uid or not cid:
        return set()
    try:
        docs = await db.user_email_configs.find(
            {"user_id": uid, "company_id": cid, "is_configured": True},
            {"_id": 0, "email_address": 1},
        ).to_list(MAX_EMPRESAS)
    except Exception as exc:
        logger.warning("[WebmailScope] Falha a listar contas de %s/%s: %s", uid, cid, exc)
        return set()
    return {e for e in (_endereco(d.get("email_address")) for d in docs) if e}


async def conta_da_caixa_geral(company_id: str) -> set[str]:
    """Endereço da Caixa Geral DESTA empresa — nunca o de outra."""
    cid = _texto(company_id)
    if not cid:
        return set()
    try:
        from services.email_config_resolver import load_caixa_geral_config

        caixa = await load_caixa_geral_config(cid)
    except Exception as exc:
        logger.warning("[WebmailScope] Falha a ler Caixa Geral de %s: %s", cid, exc)
        return set()
    endereco = _endereco((caixa or {}).get("email_address"))
    return {endereco} if endereco else set()


def build_company_mailbox_condition(
    company_id: str,
    contas: Optional[Iterable[str]] = None,
) -> dict:
    """
    Condição Mongo do separador. **Nunca devolve `None`.**

    Um âmbito sem empresa e sem contas devolve `CONDICAO_IMPOSSIVEL`, e
    não uma ausência de filtro: era a ausência que abria a colecção
    inteira.
    """
    ramos: list[dict] = []

    cid = _texto(company_id)
    if cid and cid not in VALORES_SEM_EMPRESA:
        ramos.append({"company_id": cid})

    enderecos = sorted({e for e in (_endereco(c) for c in (contas or [])) if e})
    if enderecos:
        # Só resgata a pilha POR CARIMBAR. Um email com carimbo explícito
        # tem de casar com o carimbo: se o mesmo endereço estiver
        # configurado em duas empresas, é o carimbo que decide.
        ramos.append({
            "$and": [
                {"$or": [
                    {"account": {"$regex": f"^{re.escape(e)}$", "$options": "i"}}
                    for e in enderecos
                ]},
                {"company_id": {"$in": [None, ""]}},
            ]
        })

    if not ramos:
        return dict(CONDICAO_IMPOSSIVEL)
    if len(ramos) == 1:
        return ramos[0]
    return {"$or": ramos}


async def build_webmail_scope(
    user: dict,
    company_id: str,
    *,
    box: Optional[str] = None,
) -> dict:
    """
    Âmbito completo de um separador, já validado.

    `box` escolhe QUE contas resgatam a pilha por carimbar:
      - `general` → só a Caixa Geral desta empresa;
      - tudo o resto → as contas pessoais do utilizador nesta empresa.

    A Caixa Geral de uma empresa nunca entra no âmbito de outra, mesmo
    que o utilizador tenha cargo de gestão nas duas.
    """
    empresa = await assert_empresa_no_ambito(user, company_id)

    if box == "general":
        contas = await conta_da_caixa_geral(empresa.company_id)
    else:
        contas = await contas_pessoais_da_empresa(
            _texto((user or {}).get("id")), empresa.company_id,
        )

    return build_company_mailbox_condition(empresa.company_id, contas)
