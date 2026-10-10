"""
====================================================================
O CARIMBO DE REDE DOS EMAILS (D-8, Out 2026)
====================================================================

O QUE FALTAVA
  Os processos, clientes, tarefas, leads, visitas e imóveis têm
  `network_id`; os emails não. A LEITURA (`email_access`) passou a ter
  fronteira no Bloco 2 deduzindo a rede pela EMPRESA do email — o que falha
  para um email sem `company_id` (as caixas partilhadas por cargo e tudo o
  que a sincronização antiga gravou) e obriga a uma ida à base de dados em
  cada decisão. Fechar a escrita é o que torna o carimbo uma propriedade do
  documento, como nas outras colecções.

UM PONTO ÚNICO DE ESCRITA
  Havia OITO `db.emails.insert_one` (envio, sincronização pessoal,
  sincronização das caixas partilhadas ×3, Gmail API, registo manual e
  rascunhos automáticos). Carimbar cada um à mão era garantir que o nono
  se esquece — é a lição dos cinco escritores de atribuição. Todos passam
  hoje por `inserir_email`, e um inventário por AST falha se aparecer um
  `db.emails.insert_one` fora deste módulo.

DE ONDE VEM A REDE  (a mesma regra do `rede_consensual` do backfill)
  * do PROCESSO a que o email pertence (o processo já leva o carimbo certo
    desde o Lote 4) — ou, se o processo só tiver empresa, da rede dela;
  * da EMPRESA gravada no email (`company_id`, por id ou por nome).
  Uma candidata é uma resposta. **Duas candidatas diferentes não se
  resolvem por maioria nem por prioridade: não se carimba.** Um carimbo
  errado é permanente e prende o email à rede errada; um email por
  carimbar continua a cair na dedução que a leitura já tem.

  Sem processo e sem empresa (caixa partilhada por cargo, ainda não
  associada) NÃO se carimba — meio carimbo é pior do que nenhum, e as
  caixas partilhadas por cargo continuam a não distinguir redes (D-8, o
  que fica em aberto).

QUEM RECEBE O `db`
  O carimbo usa o handle que o ESCRITOR já tem, e não um `from database
  import db` próprio: um serviço que importa `db` no topo fica com a sua
  referência ao proxy, e os testes que patcham o módulo do escritor não
  apanhariam esta (a armadilha da ordem de importação do AGENTS.md).

NUNCA FAZ FALHAR A ESCRITA
  Falhar a resolver a rede degrada para «email por carimbar» com `warning`
  — não se perde um email por causa de um carimbo. Mas nunca em silêncio.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services.tenant_network import (
    CAMPO_REDE,
    CAMPOS_EMPRESA,
    PROJECCAO_DO_CARIMBO,
    VALORES_SEM_EMPRESA,
    resolve_network_id,
)

logger = logging.getLogger(__name__)


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def rede_consensual_do_email(*candidatas: Optional[str]) -> Optional[str]:
    """Uma candidata é uma resposta; duas diferentes não se resolvem."""
    distintas = {_texto(c) for c in candidatas if _texto(c)}
    if len(distintas) == 1:
        return next(iter(distintas))
    return None


async def _rede_da_empresa(db_handle, referencia: Any, memo: Optional[dict] = None) -> Optional[str]:
    ref = _texto(referencia)
    if not ref or ref in {_texto(v) for v in VALORES_SEM_EMPRESA}:
        return None
    chave = ("empresa", ref)
    if memo is not None and chave in memo:
        return memo[chave]
    empresa = await db_handle.companies.find_one(
        {"$or": [{"id": ref}, {"name": ref}]},
        {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1},
    )
    rede = resolve_network_id(empresa, company_id=ref)
    if memo is not None:
        memo[chave] = rede
    return rede


async def _rede_do_processo(db_handle, process_id: Any, memo: Optional[dict] = None) -> Optional[str]:
    pid = _texto(process_id)
    if not pid:
        return None
    chave = ("processo", pid)
    if memo is not None and chave in memo:
        return memo[chave]
    processo = await db_handle.processes.find_one({"id": pid}, {"_id": 0, **PROJECCAO_DO_CARIMBO})
    rede: Optional[str] = None
    if isinstance(processo, dict):
        rede = _texto(processo.get(CAMPO_REDE)) or None
        if not rede:
            # Processo com empresa mas ainda sem rede (entre o carimbo na
            # escrita e a migração).
            for campo in CAMPOS_EMPRESA:
                rede = await _rede_da_empresa(db_handle, processo.get(campo), memo)
                if rede:
                    break
    if memo is not None:
        memo[chave] = rede
    return rede


async def resolver_rede_do_email(db_handle, doc: dict, *, memo: Optional[dict] = None) -> Optional[str]:
    """A rede de um email a gravar, ou ``None`` se não for dedutível sem adivinhar.

    `memo` (opcional) evita repetir as mesmas consultas numa passagem em
    massa (o backfill); nunca é usado na escrita normal, onde os dados
    podem mudar entre dois emails.
    """
    rede_processo = await _rede_do_processo(db_handle, doc.get("process_id"), memo)
    rede_empresa = await _rede_da_empresa(db_handle, doc.get("company_id"), memo)
    if rede_processo and rede_empresa and rede_processo != rede_empresa:
        logger.warning(
            "[EMAIL-CARIMBO] Email %s: o processo %s é da rede %s mas a empresa %s é da %s — "
            "não se carimba (fica por carimbar).",
            doc.get("id"), doc.get("process_id"), rede_processo, doc.get("company_id"), rede_empresa,
        )
        return None
    return rede_consensual_do_email(rede_processo, rede_empresa)


async def inserir_email(db_handle, doc: dict) -> None:
    """O ÚNICO sítio onde um email novo entra em `db.emails`.

    Carimba `network_id` quando é dedutível, sem nunca sobrepor um carimbo
    que o escritor já tenha posto, e sem nunca falhar a escrita por causa do
    carimbo.
    """
    if not _texto(doc.get(CAMPO_REDE)):
        try:
            rede = await resolver_rede_do_email(db_handle, doc)
        except Exception as exc:  # noqa: BLE001 — o carimbo nunca derruba a escrita
            rede = None
            logger.warning(
                "[EMAIL-CARIMBO] Falha a resolver a rede do email %s (%s): fica por carimbar.",
                doc.get("id"), exc,
            )
        if rede:
            doc[CAMPO_REDE] = rede
    await db_handle.emails.insert_one(doc)
