"""
====================================================================
ÂMBITO DAS ESTATÍSTICAS — o isolamento de rede no BI
====================================================================
Refinamento Analítico e SLAs (Dashboard), ponto 1.

O DIAGNÓSTICO QUE ISTO FECHA
  `grep -n "tenant\|network_id"` nos seis módulos de estatísticas e no
  `analytics_service`: ZERO ocorrências. O Lote 4 fechou as listagens e
  as pesquisas, o Lote 5 acrescentou o quadro Kanban e o explorador de
  ficheiros — e o Dashboard nunca entrou nesse inventário.

  O que isso significava em concreto:
    • `stats_overview`: `process_query = {}` mais um filtro por PAPEL.
      Admin, CEO, Administrativo e Diretor não levavam filtro nenhum.
    • `stats_branches`: volume financiado, taxa de aprovação e tempo de
      fecho de TODOS os bancos de TODAS as redes, numa só agregação.
    • `stats_communications`: para esses mesmos papéis, os primeiros 150
      caracteres do que os clientes escreveram no Portal e os assuntos
      dos emails não lidos. Não é uma contagem — é conteúdo.
    • `analytics_service`: o relatório de produtividade que vai por email
      ao CEO todas as Segundas, com as pessoas das duas redes na mesma
      tabela.

A CACHE ERA METADE DO PROBLEMA
  `stats:branches:v2` e `stats:global:conversion` são chaves GLOBAIS.
  Mesmo com o filtro posto, o PRIMEIRO pedido a chegar semeava a cache
  para todos: quem pedisse a seguir recebia os números da outra rede
  vindos do Redis, com o filtro a funcionar perfeitamente. Um filtro
  sobre uma cache partilhada é teatro.

  As chaves por utilizador (`stats:user:{id}:kpis`) já eram seguras por
  construção — o âmbito é função do utilizador. Só as globais precisavam
  do sufixo.

PORQUE UM HASH E NÃO OS NOMES DAS REDES NA CHAVE
  Os nomes de empresa têm espaços e acentos e o âmbito pode ter várias
  redes; uma chave construída por concatenação ficava longa, frágil e
  dependente da ORDEM com que as associações vêm da base de dados. O
  sufixo é o resumo canónico do âmbito COMPLETO — redes, empresas e a
  bandeira da rede de omissão — porque duas pessoas na mesma rede mas em
  empresas diferentes têm condições de filtro DIFERENTES e não podem
  partilhar a entrada da cache.

NUNCA reconstruir a condição em linha num módulo de estatísticas. Há uma
guarda sobre o código-fonte em `test_isolamento_estatisticas.py`.
====================================================================
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from typing import Optional

from database import db
from services.tenant_network import (
    TenantScope,
    build_network_scope_condition,
    resolve_tenant_scope,
)

logger = logging.getLogger(__name__)

#: Versão do esquema do sufixo. Muda quando o SIGNIFICADO do âmbito muda,
#: para as entradas antigas do Redis não serem servidas com semântica nova.
VERSAO_DO_AMBITO = "a1"

#: 64 bits de resumo. Um prefixo curto era económico e um choque de hash
#: entre dois âmbitos serviria os números de uma rede a outra — é o único
#: sítio deste módulo onde poupar bytes custava isolamento.
_DIGITOS_DO_RESUMO = 16


def _canonico(scope: TenantScope) -> str:
    """Texto estável e ordenado do âmbito.

    Ordenado de propósito: as associações chegam da base de dados na
    ordem que o Mongo quiser, e sem ordenar a mesma pessoa teria duas
    chaves de cache em pedidos consecutivos.
    """
    partes = [
        VERSAO_DO_AMBITO,
        "r=" + ",".join(sorted(scope.network_ids)),
        "e=" + ",".join(sorted(scope.company_ids)),
        "n=" + ",".join(sorted(scope.company_names)),
        "o=" + ("1" if scope.inclui_rede_de_omissao else "0"),
    ]
    return "|".join(partes)


def sufixo_de_cache(scope: TenantScope) -> str:
    """Resumo do âmbito para pôr numa chave de cache. Puro."""
    resumo = hashlib.sha256(_canonico(scope).encode("utf-8")).hexdigest()
    return f"{VERSAO_DO_AMBITO}{resumo[:_DIGITOS_DO_RESUMO]}"


@dataclass(frozen=True)
class AmbitoEstatistico:
    """O âmbito de um pedido de estatísticas, resolvido uma vez."""

    scope: TenantScope
    #: Condição Mongo sobre `processes` (e sobre qualquer colecção
    #: carimbada com `network_id`/`company_id`).
    condicao: dict
    #: Sufixo para as chaves de cache GLOBAIS.
    sufixo: str

    def chave(self, base: str) -> str:
        """Chave de cache global já com o âmbito lá dentro."""
        return f"{base}:{self.sufixo}"


async def resolver_ambito(user: Optional[dict]) -> AmbitoEstatistico:
    """Âmbito de quem pede, pelo ponto único do `tenant_network`."""
    scope = await resolve_tenant_scope(user or {})
    return AmbitoEstatistico(
        scope=scope,
        condicao=build_network_scope_condition(scope),
        sufixo=sufixo_de_cache(scope),
    )


def com_ambito(query: dict, ambito: AmbitoEstatistico) -> dict:
    """Junta a condição de rede a uma query já construída. Pura.

    `$and` e não uma actualização de chaves: a query de negócio pode já
    trazer um `$or` (é o caso das visibilidades por papel) e fundir os
    dois dicionários apagaria um deles em silêncio — o pior resultado
    possível, porque a query continuava válida e devolvia mais.
    """
    if not query:
        return dict(ambito.condicao)
    return {"$and": [ambito.condicao, query]}


async def processos_no_ambito(
    process_ids,
    ambito: AmbitoEstatistico,
) -> set[str]:
    """Dos ids dados, quais pertencem ao âmbito. UMA consulta.

    PORQUE ESTE SENTIDO E NÃO O CONTRÁRIO
      A pergunta natural seria "dá-me os processos da minha rede" e
      filtrar `prazos`/`mensagens` por esse conjunto. Mas os processos
      são a colecção GRANDE (12.450 e a crescer) e as outras são
      pequenas: um `$in` com doze mil identificadores por pedido de
      dashboard funciona hoje e morre à primeira multiplicação de
      volume.

      Aqui o conjunto de partida vem da colecção pequena (os prazos
      abertos, as mensagens não lidas) e a verificação é um `$in`
      limitado por ESSE número. O custo passa a acompanhar o que se está
      mesmo a mostrar.

    Fail-closed: sem ids, conjunto vazio. Um `None` ou um "sem filtro"
    aqui devolveria tudo, que é exactamente o contrário do pedido.
    """
    ids = {str(i) for i in (process_ids or []) if i}
    if not ids:
        return set()

    permitidos = await db.processes.find(
        {"$and": [ambito.condicao, {"id": {"$in": sorted(ids)}}]},
        {"_id": 0, "id": 1},
    ).to_list(len(ids))
    return {str(p["id"]) for p in permitidos if p.get("id")}
