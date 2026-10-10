"""A Parede no Gestor de Ficheiros S3 (Épico 10, Passo 3).

O PROBLEMA
==========
O bucket está arrumado por pasta de CLIENTE
(`Documentação Clientes/{Nome_Sanitizado}/…`) e o S3 não sabe o que é uma
rede: não há `network_id` num prefixo. Foi por isso que o Lote 5 trancou a
página a `[ADMIN, CEO]` — era isolamento por ausência de utilizadores.

A PONTE
=======
`processes.s3_folder` guarda o caminho da pasta, e `processes` carrega o
carimbo `network_id` do Lote 4. A correlação existe; faltava consultá-la.

A DECISÃO PERTENCE AO PRIMEIRO SEGMENTO, E SÓ A ELE
====================================================
Tudo abaixo de `Documentação Clientes/Joao_Silva/` é do Joao_Silva. Navegar
cinco níveis custa a mesma decisão que navegar um:

    listar a raiz   → 1 chamada S3 (paginada) + 1 query em LOTE
    listar fundo    → 1 chamada S3 + 1 query de um documento

Nunca N+1. É o que torna isto viável com 12.450 pastas.

SÓ A CAMADA 1 (REDE)
====================
Decisão de produto: o Explorador é uma ferramenta de arrumação documental da
empresa, não uma vista de carteira. Um consultor da Domus vê as pastas de
todos os clientes da Domus, incluindo as dos colegas. O predicado de rede é
o MESMO do tempo real (`realtime_audience.passa_a_rede`) — um dialecto só.

ÓRFÃS E AMBÍGUAS (política confirmada, Set 2026)
================================================
Medição em produção: 12.450 pastas, 9.800 mapeadas, 2.650 órfãs (2.400
resolúveis por backfill), 45 ambíguas, 205 ligações partidas.

* **Órfã** — ninguém a reclama, logo não tem rede. Invisível, excepto
  ADMIN/CEO, que a vêem para reconciliar.
* **Ambígua** — reclamada por processos de redes DIFERENTES. Invisível às
  DUAS: mostrar à "primeira" seria escolher à sorte qual das redes vê os
  documentos da outra.

A excepção é de RECONCILIAÇÃO, não de hierarquia — um director não entra
nela, porque veria pastas cuja rede não se sabe qual é.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable, Optional, Sequence

from fastapi import HTTPException

from database import db
from models.auth import UserRoleEnum as UserRole
from services.realtime_audience import Audiencia, passa_a_rede
from services.s3_document_root import e_id_gerado
from services.s3_explorer_paths import (
    RAIZ_DO_EXPLORADOR,
    normalizar_caminho,
    primeiro_segmento,
)
from services.tenant_network import TenantScope

logger = logging.getLogger(__name__)

# Quem vê o que NÃO tem rede conhecida. Não é hierarquia — é o trabalho de
# reconciliação das 250 órfãs e das 45 ambíguas. Só o MASTER: uma pasta sem
# dono conhecido pode ser de qualquer empresa, e mostrá-la a um Admin ou CEO
# local era mostrar-lhe os clientes das outras.
PAPEIS_DE_RECONCILIACAO = frozenset({UserRole.MASTER})

PROJECCAO = {"_id": 0, "id": 1, "s3_folder": 1, "network_id": 1,
             "company_id": 1, "company_name": 1, "client_id": 1,
             "client_name": 1}

#: Projecção dos CLIENTES. Entram na resolução por duas razões (Lote 6):
#: dão o NOME de uma pasta cujo segmento é um id, e são o único dono de uma
#: pasta de cliente que ainda não tem processo.
PROJECCAO_DO_CLIENTE = {"_id": 0, "id": 1, "nome": 1, "s3_folder": 1,
                        "network_id": 1, "company_id": 1, "company_name": 1}


@dataclass(frozen=True)
class PastaDoExplorador:
    """O que se sabe sobre a pertença de uma pasta de cliente."""

    caminho: str
    network_ids: frozenset[str] = field(default_factory=frozenset)
    company_ids: frozenset[str] = field(default_factory=frozenset)
    company_names: frozenset[str] = field(default_factory=frozenset)
    orfa: bool = False
    #: Os nomes dos clientes que reclamam esta pasta. Mais do que um é a
    #: colisão de identidade do D-19, e é por isso que é um conjunto e não um
    #: campo: escolher um faria a colisão parecer resolvida.
    nomes: frozenset[str] = field(default_factory=frozenset)

    @property
    def ambigua(self) -> bool:
        """Reclamada por mais do que uma REDE.

        Duas EMPRESAS da mesma rede não são ambiguidade: a Power e a
        Precision partilham dados, e um cliente de ambas é o caso normal.
        """
        return len(self.network_ids) > 1


def _texto(valor) -> str:
    return str(valor).strip() if valor is not None else ""


def _normalizar(caminho: str) -> str:
    return (caminho or "").rstrip("/")


def _id_da_pasta(normalizado: str) -> Optional[str]:
    """O id gerado que dá nome a esta pasta, se for esse o caso.

    `e_id_gerado` e não `id_valido`: a segunda pergunta "serve como segmento
    de caminho?", e `Joao_Silva` serve — tratá-lo como id mandaria procurar um
    cliente com esse id, que não existe, e a pasta ficava órfã.
    """
    segmento = primeiro_segmento(normalizado)
    return segmento if e_id_gerado(segmento) else None


async def carregar_pastas(caminhos: Sequence[str]) -> dict[str, PastaDoExplorador]:
    """Pertença de várias pastas, em leituras EM LOTE.

    A chave do resultado é o caminho TAL COMO VEIO, para o chamador não ter
    de reconciliar formas (com e sem barra final).

    TRÊS CAMINHOS DE RESOLUÇÃO (Lote 6), e cada um existe por um motivo:

    1. **`processes.s3_folder`** — o original, e continua a ser a fonte da
       REDE: é o processo que é carimbado na criação (`resolve_tenant_stamp`),
       o cliente não.

    2. **`clients.s3_folder`** — dá o NOME e é o único dono de uma pasta de
       cliente que ainda não tem processo.

    3. **pelo ID, quando o segmento é um uuid gerado.** Sem este, a correcção
       do ponto 1 tornava invisível ao staff normal a pasta de TODOS os
       clientes novos: a pasta do processo passou a viver DENTRO da do cliente
       (`{cid}/processos/{pid}`), logo nenhum processo aponta para `{cid}` e
       ela contava como ÓRFÃ — e uma órfã só é visível a ADMIN/CEO.

    A fronteira de rede **não se alarga**: o passo 3 encontra apenas os
    processos que já existiam, com a rede que já tinham.
    """
    if not caminhos:
        return {}

    por_normalizado: dict[str, list[str]] = {}
    for bruto in caminhos:
        por_normalizado.setdefault(_normalizar(bruto), []).append(bruto)

    # Caminho → id do cliente (só para as pastas nomeadas por um id gerado).
    ids_por_caminho = {
        normalizado: _id_da_pasta(normalizado) for normalizado in por_normalizado
    }
    ids = sorted({i for i in ids_por_caminho.values() if i})

    donos: dict[str, list[dict]] = {}

    def _registar(normalizado: Optional[str], doc: dict) -> None:
        if normalizado and normalizado in por_normalizado:
            donos.setdefault(normalizado, []).append(doc)

    try:
        condicoes: list[dict] = [{"s3_folder": {"$in": list(por_normalizado)}}]
        if ids:
            condicoes.append({"client_id": {"$in": ids}})
        cursor = db.processes.find({"$or": condicoes}, PROJECCAO)
        for doc in await cursor.to_list(50000):
            _registar(_normalizar(doc.get("s3_folder")), doc)
            cliente = _texto(doc.get("client_id"))
            for normalizado, ident in ids_por_caminho.items():
                if ident and ident == cliente:
                    _registar(normalizado, doc)
    except Exception as exc:
        # Falha fechada: sem saber a quem pertence, ninguém vê. Uma leitura
        # falhada não pode abrir o que a leitura bem sucedida fecharia.
        logger.warning("[S3-SCOPE] Falha a ler a pertença das pastas (%s).", exc)
        donos = {}

    try:
        condicoes_cliente: list[dict] = [
            {"s3_folder": {"$in": list(por_normalizado)}}
        ]
        if ids:
            condicoes_cliente.append({"id": {"$in": ids}})
        cursor = db.clients.find({"$or": condicoes_cliente}, PROJECCAO_DO_CLIENTE)
        for doc in await cursor.to_list(50000):
            _registar(_normalizar(doc.get("s3_folder")), doc)
            ident_do_cliente = _texto(doc.get("id"))
            for normalizado, ident in ids_por_caminho.items():
                if ident and ident == ident_do_cliente:
                    _registar(normalizado, doc)
    except Exception as exc:
        logger.warning("[S3-SCOPE] Falha a ler os clientes das pastas (%s).", exc)

    resultado: dict[str, PastaDoExplorador] = {}
    for normalizado, brutos in por_normalizado.items():
        reclamantes = donos.get(normalizado) or []
        # Um mesmo documento pode ter sido registado duas vezes (pelo
        # `s3_folder` e pelo id); os conjuntos tratam disso, e para os nomes
        # é a identidade do documento que conta.
        pasta = PastaDoExplorador(
            caminho=normalizado,
            network_ids=frozenset(
                r for r in (_texto(p.get("network_id")) for p in reclamantes) if r
            ),
            company_ids=frozenset(
                c for c in (_texto(p.get("company_id")) for p in reclamantes) if c
            ),
            company_names=frozenset(
                c for c in (_texto(p.get("company_name")) for p in reclamantes) if c
            ),
            orfa=not reclamantes,
            nomes=frozenset(
                n
                for n in (
                    _texto(p.get("client_name")) or _texto(p.get("nome"))
                    for p in reclamantes
                )
                if n
            ),
        )
        for bruto in brutos:
            resultado[bruto] = pasta
    return resultado


def nome_legivel(pasta: Optional[PastaDoExplorador], nome_cru: str) -> str:
    """O nome a MOSTRAR para uma pasta — nunca o que se usa para operar nela.

    Só substitui quando o nome cru é um id gerado (um nome legível não se
    troca por nada) e quando há **exactamente um** nome: dois nomes na mesma
    pasta é a colisão do D-19, e mostrar um deles faria a colisão parecer
    resolvida. Sem dono, o id fica como está — inventar um nome seria pior do
    que mostrar um uuid, porque a órfã tem de se ver como órfã.

    O caminho continua a ser a autoridade de TODAS as operações (renomear,
    apagar, descarregar). Mostrar uma coisa e operar noutra é a forma discreta
    de uma parede não valer nada.
    """
    if not e_id_gerado(nome_cru):
        return nome_cru
    if pasta is None or len(pasta.nomes) != 1:
        return nome_cru
    return next(iter(pasta.nomes))


def pode_ver(
    pasta: Optional[PastaDoExplorador],
    scope: Optional[TenantScope],
    *,
    role: str,
) -> bool:
    """Este utilizador pode ver esta pasta?

    Sem pasta ou sem âmbito → não. Falha fechada: adivinhar uma fronteira de
    segurança é o mesmo que não a ter.
    """
    if pasta is None:
        return False

    papel = _texto(getattr(role, "value", role)).lower()
    reconcilia = papel in {p.value for p in PAPEIS_DE_RECONCILIACAO}

    if pasta.orfa or pasta.ambigua:
        # Sem rede conhecida (ou com mais do que uma), só a reconciliação.
        return reconcilia

    if reconcilia:
        return True

    if scope is None:
        return False

    # UM dialecto: o mesmo predicado de rede do tempo real.
    return any(
        passa_a_rede(
            Audiencia(
                network_id=rede or None,
                company_id=next(iter(pasta.company_ids), None),
                company_name=next(iter(pasta.company_names), None),
            ),
            scope,
        )
        for rede in (pasta.network_ids or {""})
    )


async def filtrar_subpastas(
    subpastas: Iterable[dict],
    scope: Optional[TenantScope],
    *,
    role: str,
) -> list[dict]:
    """Deixa passar só as subpastas que este utilizador pode ver.

    Uma leitura em lote para a página inteira — é este o ponto em que o
    desenho compra a performance. E é também onde se acrescenta o
    `display_name`, porque o mapa de donos já está aqui: pedi-lo numa segunda
    leitura seria duplicar a consulta que decide a parede.

    `name` e `path` ficam INTACTOS — são o que as operações usam. O
    `display_name` é só para o ecrã.
    """
    entradas = [p for p in subpastas if p and p.get("path")]
    if not entradas:
        return []

    mapa = await carregar_pastas([p["path"] for p in entradas])
    visiveis = []
    for entrada in entradas:
        pasta = mapa.get(entrada["path"])
        if not pode_ver(pasta, scope, role=role):
            continue
        visiveis.append({
            **entrada,
            "display_name": nome_legivel(pasta, entrada.get("name") or ""),
            "nomes_dos_clientes": sorted(pasta.nomes) if pasta else [],
            "orfa": bool(pasta.orfa) if pasta else True,
        })
    return visiveis


async def assert_pasta_no_ambito(
    caminho: str,
    scope: Optional[TenantScope],
    *,
    role: str,
) -> None:
    """Levanta **404** se o caminho não pertencer ao âmbito do utilizador.

    404 e não 403: um 403 confirmaria que a pasta existe, e o nome da pasta
    É o nome do cliente — confirmaria a carteira da concorrência. A mensagem
    também não repete o caminho pedido.

    A raiz é sempre permitida: não é de ninguém, e quem a lista recebe a
    lista já FILTRADA.
    """
    normalizado = normalizar_caminho(caminho)
    if normalizado == RAIZ_DO_EXPLORADOR:
        return

    segmento = primeiro_segmento(normalizado)
    if not segmento:
        raise HTTPException(status_code=404, detail="Pasta não encontrada")

    alvo = f"{RAIZ_DO_EXPLORADOR}/{segmento}"
    mapa = await carregar_pastas([alvo])
    if not pode_ver(mapa.get(alvo), scope, role=role):
        raise HTTPException(status_code=404, detail="Pasta não encontrada")


async def ambito_do_utilizador(request, user: dict) -> tuple[TenantScope, str]:
    """`(TenantScope, papel efectivo)` de quem está a fazer o pedido.

    O papel é o **efectivo**, colapsado por `resolve_concrete_role`: é o
    chapéu que a pessoa tem posto agora. Usar o papel do JWT deixaria um
    admin com o perfil de consultor activo a continuar a ver as pastas
    órfãs — um alargamento silencioso, que é exactamente a brecha que o
    `can_update_status` tinha.
    """
    from services.auth import get_effective_role, resolve_concrete_role
    from services.tenant_network import resolve_tenant_scope

    papel = resolve_concrete_role(get_effective_role(request, user), user)
    return await resolve_tenant_scope(user), papel
