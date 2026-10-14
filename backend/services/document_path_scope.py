"""
====================================================================
UM FICHEIRO PEDIDO PELA CHAVE S3 TEM DE SER DE UMA PASTA DA MINHA REDE
====================================================================
(Out 2026, D-31 — fecho)

O QUE ESTAVA ABERTO
  `GET /documents/proxy/{path}` e `GET /documents/download-url/{path}`
  servem qualquer ficheiro de `Documentação Clientes/` a qualquer membro
  da equipa que saiba a chave; o `bulk-download` empacota até 50 chaves
  sem perguntar de quem são. A única parede era «a chave está dentro da
  raiz» (`assert_path_within_document_root`): isso impede o `backups/*.zip`,
  não impede o cliente do vizinho. As chaves não são segredo — aparecem em
  logs, em respostas de listagem e em anexos de email.

A PONTE É A DO EXPLORADOR, COM UMA DIFERENÇA
  A pasta S3 não tem rede; quem a tem é o PROCESSO (`s3_folder`, ou o id no
  caminho — `{cliente}/processos/{processo}`) ou o CLIENTE. Esta guarda
  resolve o dono da mesma maneira que o Explorador (`s3_explorer_scope`) e
  decide como o resto da fronteira de documentos (D-26):

  * a rede CONVIDADA conta — quem vê o processo partilhado vê os ficheiros
    (o Explorador não a conta porque é ferramenta de arrumação da casa);
  * pasta **sem dono** → só o Master (a política da órfã);
  * pasta reclamada por **mais do que uma rede** → ninguém, só o Master
    (a política da ambígua: escolher à sorte qual das redes vê os ficheiros
    da outra é a fuga);
  * **404 e nunca 403**: o nome da pasta É o nome do cliente.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Iterable

from fastapi import HTTPException

from database import db
from services.document_process_resolve import DOCUMENT_S3_ROOT_PREFIX
from services.document_s3_paths import s3_path_variations
from services.role_scope import utilizador_e_global
from services.tenant_network import (
    CAMPO_REDES_PARCEIRAS,
    CAMPO_REDE,
    PROJECCAO_DO_CARIMBO,
    processo_no_ambito,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

ERRO_FICHEIRO_NAO_ENCONTRADO = "Ficheiro não encontrado"

_RAIZ_COM_UNDERSCORE = DOCUMENT_S3_ROOT_PREFIX.replace(" ", "_")

_PROJECCAO_DO_DONO = {
    "_id": 0, "id": 1, "client_id": 1, "s3_folder": 1,
    CAMPO_REDES_PARCEIRAS: 1, **PROJECCAO_DO_CARIMBO,
}

#: Tecto de donos lidos por chave: uma pasta com mais do que isto está
#: errada, e cortar é fechar (vê menos).
_LIMITE_DE_DONOS = 50


def prefixos_e_segmentos(file_path: str) -> tuple[list[str], list[str]]:
    """Pastas ancestrais da chave (sem a raiz) e os segmentos que podem ser ids.

    Para cada variação underscore↔espaço da chave (a mesma tolerância dos
    handlers), todas as pastas entre a raiz e o ficheiro: uma pasta
    consolidada pode estar mapeada a qualquer nível.
    """
    prefixos: list[str] = []
    segmentos: list[str] = []
    for variacao in s3_path_variations((file_path or "").lstrip("/")):
        # A tolerância underscore↔espaço também troca a RAIZ
        # («Documentação_Clientes/»): sem a repor, a variação de uma pasta
        # legada era descartada e a pasta ficava sem dono (órfã).
        if variacao.startswith(_RAIZ_COM_UNDERSCORE):
            variacao = DOCUMENT_S3_ROOT_PREFIX + variacao[len(_RAIZ_COM_UNDERSCORE):]
        if not variacao.startswith(DOCUMENT_S3_ROOT_PREFIX):
            continue
        partes = [p for p in variacao.split("/") if p]
        # partes[0] é a raiz; o último é o ficheiro.
        for fundo in range(2, len(partes)):
            prefixo = "/".join(partes[:fundo])
            prefixos.extend((prefixo, prefixo + "/"))
        segmentos.extend(partes[1:-1])
    return list(dict.fromkeys(prefixos)), list(dict.fromkeys(segmentos))


async def _donos_da_chave(prefixos: Iterable[str], segmentos: Iterable[str]):
    prefixos, segmentos = list(prefixos), list(segmentos)
    condicoes_processo = [{"s3_folder": {"$in": prefixos}}]
    condicoes_cliente = [{"s3_folder": {"$in": prefixos}}]
    if segmentos:
        condicoes_processo += [{"id": {"$in": segmentos}}, {"client_id": {"$in": segmentos}}]
        condicoes_cliente.append({"id": {"$in": segmentos}})
    processos = await db.processes.find(
        {"$or": condicoes_processo}, _PROJECCAO_DO_DONO,
    ).to_list(_LIMITE_DE_DONOS)
    clientes = await db.clients.find(
        {"$or": condicoes_cliente},
        {"_id": 0, "id": 1, "s3_folder": 1, **PROJECCAO_DO_CARIMBO},
    ).to_list(_LIMITE_DE_DONOS)
    return processos, clientes


async def ficheiro_no_ambito(file_path: str, user: dict) -> bool:
    """A chave S3 pertence a uma pasta da rede de quem pede?"""
    if utilizador_e_global(user):
        return True

    prefixos, segmentos = prefixos_e_segmentos(file_path)
    if not prefixos:
        # Fora da raiz: não é desta guarda (a da raiz recusa-o), e não é de
        # ninguém que se prove.
        return False

    try:
        processos, clientes = await _donos_da_chave(prefixos, segmentos)
    except Exception as exc:  # falha fechada: sem saber de quem é, ninguém lê
        logger.warning("[S3-FICHEIRO] Falha a resolver o dono de %s (%s).", file_path, exc)
        return False

    # A chave NOMEIA um processo (`…/processos/{id}/…`)? Então o dono é esse processo e mais nenhum:
    # um cliente com processos em duas empresas (Lote 6: o que transita entre redes é o processo)
    # tem as subpastas de cada um, e a pasta do vizinho não é minha só porque o cliente é o mesmo.
    nomeados = [p for p in processos if str(p.get("id") or "") in set(segmentos)]
    if nomeados:
        processos, clientes = nomeados, []

    donos = [*processos, *clientes]
    if not donos:
        return False  # órfã

    # Ambígua = reclamada por FICHAS DIFERENTES de redes diferentes (os homónimos do D-19). Um cliente
    # e os processos dele são UMA ficha: se os processos estão em duas empresas (a triagem enganou-se
    # e moveu um), o que está na raiz da pasta do cliente é de quem vê qualquer um deles — senão
    # ninguém, nem o dono, leria o BI do próprio cliente.
    fichas = {
        str(i) if i else None for i in (
            *(p.get("client_id") for p in processos),
            *(c.get("id") for c in clientes),
        )
    }
    # Um dono sem ficha identificada conta como outra ficha: não se prova que seja a mesma.
    redes_dos_donos = {
        str(d.get(CAMPO_REDE)).strip() for d in donos if str(d.get(CAMPO_REDE) or "").strip()
    }
    if (len(fichas) != 1 or None in fichas) and len(redes_dos_donos) > 1:
        return False  # ambígua

    scope = await resolve_tenant_scope(user)
    if any(processo_no_ambito(p, scope) for p in processos):
        return True

    # Um cliente sem processo (Pool, onboarding) é aberto pelo predicado de
    # clientes — o mesmo das rotas `/clients/{id}`.
    from services.by_id_scope import cliente_no_ambito

    for cliente in clientes:
        if cliente.get("id") and await cliente_no_ambito(
            str(cliente["id"]), user, com_convidados=True,
        ):
            return True
    return False


async def exigir_ficheiro_no_ambito(file_path: str, user: dict) -> None:
    """404 se a chave não é de uma pasta da rede de quem pede."""
    if not await ficheiro_no_ambito(file_path, user):
        logger.warning(
            "[S3-FICHEIRO] %s pediu uma chave fora da sua rede.", (user or {}).get("id"),
        )
        raise HTTPException(status_code=404, detail=ERRO_FICHEIRO_NAO_ENCONTRADO)


__all__ = [
    "ERRO_FICHEIRO_NAO_ENCONTRADO",
    "exigir_ficheiro_no_ambito",
    "ficheiro_no_ambito",
    "prefixos_e_segmentos",
]
