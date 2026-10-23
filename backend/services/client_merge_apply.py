"""
====================================================================
FUSÃO DE CLIENTES DUPLICADOS (D-42/D-40) — EXECUTAR O PLANO
====================================================================
`client_merge_plan` decide; este módulo escreve. O `db` entra por argumento
(como no `campos_limpaveis`): o mesmo código corre contra o Mongo de produção
no script e contra um `mongod` avulso nos testes de integração.

ORDEM DAS ESCRITAS (e porque é esta)
  1. reapontar os PROCESSOS (`client_id`, `second_client_id`, `client_ids`);
  2. reapontar o resto das colecções que referem o cliente;
  3. acrescentar ao SOBREVIVENTE (preencher o que falta, redes associadas,
     processos, rasto da fusão);
  4. só no fim, eliminar o ABSORVIDO.
  Se o processo morrer a meio, o absorvido continua activo, o grupo continua a
  existir e uma segunda passagem retoma — nada fica reapontado para um
  cliente que não existe. Cada passo é idempotente.

O INVENTÁRIO DAS COLECÇÕES NÃO ESTÁ PROVADO
  Os processos têm o inventário conhecido. Para as outras colecções não há
  tabela fiável (a lição do `assignment_drift`: uma dedução vale o inventário
  que a suporta), por isso a descoberta é POR LEITURA: percorre-se
  `list_collection_names()` e conta-se, em cada uma, quem aponta para um
  absorvido nos campos habituais. O que se encontra reaponta-se; **o que sobra
  depois da fusão reporta-se** (`orfaos`) — nunca é um silêncio.

O QUE NUNCA SE TOCA
  O S3 (nada se move), o documento do absorvido (fica eliminado, não apagado:
  é o rasto e a reversão) e o telemóvel (já não é identidade).
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Iterable

from services.client_merge_plan import FUNDIR, PlanoDeFusao

logger = logging.getLogger(__name__)

#: Campos escalares de outras colecções que guardam o id de um cliente.
CAMPOS_ESCALARES_DE_CLIENTE = ("client_id", "second_client_id", "matched_client_id")
#: Campos que guardam uma LISTA de ids de clientes.
CAMPOS_DE_LISTA_DE_CLIENTES = ("client_ids",)

#: Colecções que não se percorrem (o sobrevivente e o absorvido vivem em `clients`;
#: os processos têm tratamento próprio; as de sistema do MongoDB não são nossas).
COLECCOES_FORA_DA_DESCOBERTA = frozenset({"clients", "processes"})

MAX_TIME_MS = 120_000

#: Ordem de uma lista que mantém a primeira ocorrência de cada elemento (o primeiro titular
#: continua primeiro depois de dois ids passarem a ser o mesmo).
PIPELINE_SEM_REPETIDOS_EM_CLIENT_IDS = [
    {"$set": {"client_ids": {"$reduce": {
        "input": "$client_ids",
        "initialValue": [],
        "in": {"$cond": [
            {"$in": ["$$this", "$$value"]},
            "$$value",
            {"$concatArrays": ["$$value", ["$$this"]]},
        ]},
    }}}},
]


def _agora_iso(agora: Any) -> str:
    return agora.isoformat() if hasattr(agora, "isoformat") else str(agora)


async def colecoes_a_percorrer(db) -> list[str]:
    nomes = await db.list_collection_names()
    return sorted(
        n for n in nomes
        if n not in COLECCOES_FORA_DA_DESCOBERTA and not n.startswith("system.")
    )


async def referencias_fora_dos_processos(db, absorvidos: Iterable[str]) -> dict[str, dict[str, int]]:
    """``colecção → campo → quantos documentos`` que ainda apontam para um absorvido.

    É a descoberta e é também a prova no fim: depois da fusão tem de estar vazia.
    """
    ids = [a for a in absorvidos if a]
    achado: dict[str, dict[str, int]] = {}
    if not ids:
        return achado
    for colecao in await colecoes_a_percorrer(db):
        for campo in (*CAMPOS_ESCALARES_DE_CLIENTE, *CAMPOS_DE_LISTA_DE_CLIENTES):
            try:
                n = await db[colecao].count_documents({campo: {"$in": ids}}, maxTimeMS=MAX_TIME_MS)
            except Exception as exc:  # noqa: BLE001 — uma colecção ilegível não pára as outras, mas diz-se
                logger.warning("[FUSAO] Não foi possível ler %s.%s (%s).", colecao, campo, exc)
                continue
            if n:
                achado.setdefault(colecao, {})[campo] = n
    return achado


async def reapontar_processos(db, absorvido: str, sobrevivente: str) -> dict[str, int]:
    """Os processos que tinham o absorvido como titular passam a ter o sobrevivente."""
    contagem: dict[str, int] = {}
    for campo in ("client_id", "second_client_id"):
        r = await db.processes.update_many({campo: absorvido}, {"$set": {campo: sobrevivente}})
        contagem[campo] = getattr(r, "modified_count", 0)
    r = await db.processes.update_many(
        {"client_ids": absorvido},
        {"$set": {"client_ids.$[el]": sobrevivente}},
        array_filters=[{"el": absorvido}],
    )
    contagem["client_ids"] = getattr(r, "modified_count", 0)
    if contagem["client_ids"]:
        await db.processes.update_many(
            {"client_ids": sobrevivente}, PIPELINE_SEM_REPETIDOS_EM_CLIENT_IDS,
        )
    return contagem


async def reapontar_outras_colecoes(
    db, absorvido: str, sobrevivente: str, onde: dict[str, dict[str, int]],
) -> dict[str, dict[str, int]]:
    """Reaponta, só nas colecções/campos onde a descoberta encontrou referências."""
    feito: dict[str, dict[str, int]] = {}
    for colecao, campos in onde.items():
        for campo in campos:
            if campo in CAMPOS_DE_LISTA_DE_CLIENTES:
                r = await db[colecao].update_many(
                    {campo: absorvido},
                    {"$set": {f"{campo}.$[el]": sobrevivente}},
                    array_filters=[{"el": absorvido}],
                )
            else:
                r = await db[colecao].update_many({campo: absorvido}, {"$set": {campo: sobrevivente}})
            n = getattr(r, "modified_count", 0)
            if n:
                feito.setdefault(colecao, {})[campo] = n
    return feito


async def _acrescentar_ao_sobrevivente(
    db, plano: PlanoDeFusao, absorvido_doc: dict, agora: str,
) -> None:
    absorvido = absorvido_doc["id"]
    sets = {"updated_at": agora, **plano.preenchimentos.get(absorvido, {})}
    adicionar: dict[str, Any] = {}
    if plano.redes_a_associar:
        adicionar["redes_associadas"] = {"$each": list(plano.redes_a_associar)}
    processos = [p for p in (absorvido_doc.get("process_ids") or []) if p]
    if processos:
        adicionar["process_ids"] = {"$each": processos}
    atualizacao: dict[str, Any] = {"$set": sets}
    if adicionar:
        atualizacao["$addToSet"] = adicionar
    if absorvido_doc.get("partner_leads"):
        atualizacao["$push"] = {"partner_leads": {"$each": list(absorvido_doc["partner_leads"])}}

    # Uma segunda passagem não repete o rasto nem as leads: o filtro diz «ainda não fundi este».
    filtro = {"id": plano.sobrevivente, "fundido_de.id": {"$ne": absorvido}}
    rasto = {"id": absorvido, "em": agora, "s3_folder": absorvido_doc.get("s3_folder")}
    atualizacao.setdefault("$push", {})["fundido_de"] = rasto
    r = await db.clients.update_one(filtro, atualizacao)
    if not getattr(r, "matched_count", 0):
        # Já fundido numa passagem anterior: só garante o que é idempotente.
        extra: dict[str, Any] = {"$set": {"updated_at": agora}}
        if adicionar:
            extra["$addToSet"] = adicionar
        await db.clients.update_one({"id": plano.sobrevivente}, extra)


async def _eliminar_absorvido(db, absorvido_doc: dict, sobrevivente: str, agora: str) -> None:
    dados = absorvido_doc.get("dados_pessoais") or {}
    contacto = absorvido_doc.get("contacto") or {}
    identidade = {
        k: v for k, v in (("nif_hash", dados.get("nif_hash")), ("email_hash", contacto.get("email_hash"))) if v
    }
    await db.clients.update_one(
        {"id": absorvido_doc["id"]},
        {
            "$set": {
                "deleted": True,
                "is_deleted": True,
                "is_active": False,
                "status": "eliminado",
                "deleted_at": agora,
                "deleted_by": "scripts/resolve_client_duplicates.py",
                "merged_into": sobrevivente,
                "merged_at": agora,
                "merged_identity": identidade,
                "updated_at": agora,
            },
            # Os índices cegos saem do documento: as procuras por hash (que não distinguem eliminados)
            # já não o encontram, e o índice único parcial nunca o vê.
            "$unset": {"dados_pessoais.nif_hash": "", "contacto.email_hash": ""},
        },
    )


async def aplicar_plano(db, plano: PlanoDeFusao, *, agora: Any) -> dict[str, Any]:
    """Executa UM plano `fundir`. Devolve o que fez (contagens, sem dados pessoais)."""
    if plano.veredicto != FUNDIR:
        raise ValueError("Só se executa um plano `fundir`; os ambíguos decidem-se à mão.")
    quando = _agora_iso(agora)
    relatorio: dict[str, Any] = {"sobrevivente": plano.sobrevivente, "absorvidos": []}

    ainda_activos = await db.clients.find(
        {"id": {"$in": list(plano.absorvidos)}}, {"_id": 0},
    ).to_list(len(plano.absorvidos))
    docs = {d["id"]: d for d in ainda_activos}
    onde = await referencias_fora_dos_processos(db, plano.absorvidos)

    for absorvido in plano.absorvidos:
        doc = docs.get(absorvido)
        if not doc:
            continue
        linha: dict[str, Any] = {"id": absorvido}
        linha["processos"] = await reapontar_processos(db, absorvido, plano.sobrevivente)
        linha["outras_colecoes"] = await reapontar_outras_colecoes(db, absorvido, plano.sobrevivente, onde)
        await _acrescentar_ao_sobrevivente(db, plano, doc, quando)
        await _eliminar_absorvido(db, doc, plano.sobrevivente, quando)
        relatorio["absorvidos"].append(linha)
    return relatorio


__all__ = [
    "CAMPOS_DE_LISTA_DE_CLIENTES",
    "CAMPOS_ESCALARES_DE_CLIENTE",
    "aplicar_plano",
    "colecoes_a_percorrer",
    "referencias_fora_dos_processos",
    "reapontar_outras_colecoes",
    "reapontar_processos",
]
