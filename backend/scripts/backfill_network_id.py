"""
====================================================================
MIGRAÇÃO: carimbar `network_id` (Rede / Grupo Empresarial)
====================================================================
Lote 4, ponto 10 — isolamento multi-tenant. Ver `services/tenant_network.py`.

O PROBLEMA QUE ISTO RESOLVE
  Até esta mudança nenhum documento de negócio levava carimbo de
  empresa: `build_staff_process_doc` não escrevia sequer `company_id`.
  A pilha existente não tem dono legível, e o filtro de isolamento não
  tem por onde lhe pegar. A variável `TENANT_DEFAULT_NETWORK_ID` diz a
  que rede essa pilha pertence enquanto não estiver carimbada; este
  script carimba-a, e a partir daí a pertença é explícita.

DUAS FASES, COM PESOS MUITO DIFERENTES
  --empresas    OBRIGATÓRIA e barata (dezenas de linhas). Põe as
                empresas já existentes na rede de omissão. Sem ela, cada
                empresa antiga fica a valer como ilha própria e a Power
                deixa de ver a Precision — a regressão que a Política C
                existe para evitar.
  --documentos  OPCIONAL e pesada (processos, clientes, tarefas). Deduz
                o dono de cada documento. É uma optimização: enquanto
                não correr, a rede de omissão já cobre o que falta.

  Sem bandeiras, corre as duas.

COMO DEDUZ O DONO DE UM DOCUMENTO
  1. empresa já escrita no documento (`company_id` / `company` / `company_name`)
  2. as empresas dos utilizadores atribuídos — SÓ se concordarem todas
     na mesma rede (um processo partilhado entre redes não se adivinha)
  3. a empresa de quem o criou (`created_by`)
  4. nada: fica por carimbar, e continua coberto pela rede de omissão

  Nunca escreve uma rede "provável". Um carimbo errado é pior do que
  nenhum: torna o documento visível à rede errada PARA SEMPRE, e o
  passo 1 da próxima execução aceitá-lo-ia como verdade.

EXECUÇÃO
  cd backend && python -m scripts.backfill_network_id --dry-run
  cd backend && python -m scripts.backfill_network_id --empresas
  cd backend && python -m scripts.backfill_network_id --documentos

  Flags:
    --dry-run    Mostra o que faria, sem escrever nada
    --rede REDE  Rede a usar (por omissão: TENANT_DEFAULT_NETWORK_ID)
    --verbose    Detalhe por documento
====================================================================
"""
import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from typing import Any, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("backfill_network_id")

# Colecções carimbadas e os campos por onde se descobre quem lá trabalha.
COLECCOES = {
    "processes": (
        "assigned_consultor_ids", "assigned_consultor_id", "consultor_id",
        "assigned_mediador_ids", "assigned_mediador_id", "mediador_id",
        "assigned_indexacao_id", "assigned_to", "consultant_id", "manager_id",
    ),
    "clients": ("assigned_to", "assigned_consultor_id", "consultor_id"),
    "tasks": ("assigned_to", "assigned_user_id", "user_id"),
}


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def ids_atribuidos(doc: dict, campos: tuple) -> list[str]:
    """IDs de utilizadores ligados a um documento, de todos os campos."""
    encontrados: list[str] = []
    for campo in campos:
        valor = doc.get(campo)
        if isinstance(valor, (list, tuple, set)):
            encontrados.extend(_texto(v) for v in valor)
        elif valor is not None:
            encontrados.append(_texto(valor))
    return [v for v in dict.fromkeys(encontrados) if v]


def rede_consensual(redes: list[Optional[str]]) -> Optional[str]:
    """Rede única entre as candidatas, ou ``None`` se não houver consenso.

    Um processo trabalhado por pessoas de redes diferentes não tem dono
    óbvio — e adivinhar aqui é escolher a quem vazar.
    """
    distintas = {r for r in redes if r}
    return distintas.pop() if len(distintas) == 1 else None


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Carimbar network_id")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--empresas", action="store_true")
    parser.add_argument("--documentos", action="store_true")
    parser.add_argument("--rede", default=None)
    parser.add_argument("--verbose", action="store_true")
    args = parser.parse_args()

    from database import db
    from services.tenant_network import (
        CAMPO_REDE, CAMPOS_EMPRESA, VALORES_SEM_EMPRESA,
        rede_de_omissao, resolve_network_id,
    )

    rede = _texto(args.rede) or rede_de_omissao()
    if not rede:
        logger.error(
            "Nenhuma rede indicada. Defina TENANT_DEFAULT_NETWORK_ID ou "
            "passe --rede <nome-da-rede>."
        )
        return 1

    fazer_empresas = args.empresas or not (args.empresas or args.documentos)
    fazer_documentos = args.documentos or not (args.empresas or args.documentos)
    agora = datetime.now(timezone.utc).isoformat()
    prefixo = "[SIMULAÇÃO] " if args.dry_run else ""

    logger.info("%sRede de destino: %s", prefixo, rede)

    # ── Fase 1: empresas ────────────────────────────────────────────
    if fazer_empresas:
        sem_rede = await db.companies.find(
            {CAMPO_REDE: {"$in": [None, ""]}}, {"_id": 0, "id": 1, "name": 1},
        ).to_list(1000)
        logger.info("%sEmpresas sem rede: %d", prefixo, len(sem_rede))
        for empresa in sem_rede:
            logger.info("%s  → %s (%s)", prefixo, empresa.get("name"), empresa.get("id"))
        if sem_rede and not args.dry_run:
            resultado = await db.companies.update_many(
                {CAMPO_REDE: {"$in": [None, ""]}},
                {"$set": {CAMPO_REDE: rede, "updated_at": agora}},
            )
            logger.info("  %d empresas carimbadas.", resultado.modified_count)

    if not fazer_documentos:
        return 0

    # ── Fase 2: documentos ──────────────────────────────────────────
    empresas = await db.companies.find(
        {}, {"_id": 0, "id": 1, "name": 1, CAMPO_REDE: 1},
    ).to_list(1000)
    rede_por_empresa: dict[str, Optional[str]] = {}
    for empresa in empresas:
        alvo = resolve_network_id(empresa)
        for chave in (_texto(empresa.get("id")), _texto(empresa.get("name"))):
            if chave:
                rede_por_empresa[chave] = alvo

    # Rede de cada utilizador, pelas suas associações (UCR).
    rede_por_utilizador: dict[str, Optional[str]] = {}
    ucrs = await db.user_company_roles.find(
        {"is_deleted": {"$ne": True}, "is_active": {"$ne": False}},
        {"_id": 0, "user_id": 1, "company_id": 1, "company_name": 1},
    ).to_list(50000)
    por_utilizador: dict[str, list] = {}
    for ucr in ucrs:
        por_utilizador.setdefault(_texto(ucr.get("user_id")), []).append(ucr)
    for user_id, associacoes in por_utilizador.items():
        candidatas = [
            rede_por_empresa.get(_texto(a.get("company_id")))
            or rede_por_empresa.get(_texto(a.get("company_name")))
            for a in associacoes
        ]
        rede_por_utilizador[user_id] = rede_consensual(candidatas)

    # Email → id, para o passo 3 (`created_by` guarda ora um, ora outro).
    utilizadores = await db.users.find({}, {"_id": 0, "id": 1, "email": 1}).to_list(50000)
    id_por_email = {
        _texto(u.get("email")).lower(): _texto(u.get("id"))
        for u in utilizadores if u.get("email")
    }

    def rede_de(user_ref: str) -> Optional[str]:
        chave = _texto(user_ref)
        if not chave:
            return None
        return rede_por_utilizador.get(
            chave, rede_por_utilizador.get(id_por_email.get(chave.lower(), ""))
        )

    total_geral = {"carimbados": 0, "por_resolver": 0}
    for coleccao, campos in COLECCOES.items():
        por_carimbar = await db[coleccao].find(
            {CAMPO_REDE: {"$in": [None, ""]}}, {"_id": 0},
        ).to_list(100000)

        carimbados = 0
        por_resolver = 0
        for doc in por_carimbar:
            # 1 — empresa já escrita no documento
            alvo = None
            for campo in CAMPOS_EMPRESA:
                valor = _texto(doc.get(campo))
                if valor and valor not in VALORES_SEM_EMPRESA:
                    alvo = rede_por_empresa.get(valor)
                    if alvo:
                        break

            # 2 — consenso entre quem lá trabalha
            if not alvo:
                alvo = rede_consensual(
                    [rede_de(ref) for ref in ids_atribuidos(doc, campos)]
                )

            # 3 — quem criou
            if not alvo:
                alvo = rede_de(doc.get("created_by") or doc.get("created_by_id") or "")

            if not alvo:
                por_resolver += 1
                if args.verbose:
                    logger.info(
                        "    ? %s/%s sem dono dedutível (fica na rede de omissão)",
                        coleccao, doc.get("id"),
                    )
                continue

            carimbados += 1
            if args.verbose:
                logger.info("    → %s/%s = %s", coleccao, doc.get("id"), alvo)
            if not args.dry_run:
                await db[coleccao].update_one(
                    {"id": doc.get("id")},
                    {"$set": {CAMPO_REDE: alvo, "updated_at": agora}},
                )

        logger.info(
            "%s%s: %d por carimbar → %d carimbados, %d por resolver",
            prefixo, coleccao, len(por_carimbar), carimbados, por_resolver,
        )
        total_geral["carimbados"] += carimbados
        total_geral["por_resolver"] += por_resolver

    logger.info(
        "%sTotal: %d carimbados, %d por resolver (cobertos pela rede de omissão).",
        prefixo, total_geral["carimbados"], total_geral["por_resolver"],
    )
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(_main()))
