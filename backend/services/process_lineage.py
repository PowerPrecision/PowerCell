"""
====================================================================
LINHAGEM DE UM PROCESSO: Parceiro → Empresa Y → Empresa Z → … (Out 2026)
====================================================================
O Parceiro é um angariador (não executa). A empresa de destino (Y) partilha em
cadeia com a Z — e a Z pode passar à W — sem fricção nem aprovação do parceiro.
Para a cadeia não perder a origem, quem vê o processo tem de conseguir ler DE ONDE
ele veio e ONDE está agora.

DE ONDE DERIVA (nada disto é gravado)
  * a ORIGEM é o parceiro angariador, se houver: `assigned_parceiro_id` /
    `parceiro_name`, escritos pela lead (`partner_attribution`);
  * a CASA DONA é a empresa do carimbo (`network_id`, `company_name`);
  * cada ELO é uma entrada de `partner_companies` (`process_sharing`), com
    `shared_from_network` (quem o abriu) e `depth`. Entradas antigas, sem esses
    campos, foram abertas pela casa dona.

Gravar a linhagem seria uma cópia que divergia no dia em que se revogasse um elo.
A função é PURA: recebe o documento (e, opcionalmente, o nome da casa dona que o
chamador já resolveu) e devolve o que o ecrã desenha.

QUEM VÊ O QUÊ
  * o STAFF de qualquer empresa que veja o processo (a dona e as convidadas) vê a
    linhagem INTEIRA, incluindo o nome do parceiro — é o pedido: a Z vê
    Parceiro → Y → Z;
  * o PARCEIRO vê só onde o processo ESTÁ (`empresas_onde_esta`): o nome da(s)
    empresa(s) que o têm agora, nunca a rede, os ids nem quem passou a quem.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services.process_sharing import (
    elo_e_meu,
    parceiros_do_processo,
    rede_de_origem_da_entrada,
)
from services.tenant_network import CAMPO_REDE

logger = logging.getLogger(__name__)

TIPO_PARCEIRO = "parceiro"
TIPO_EMPRESA = "empresa"
PAPEL_DONA = "dona"
PAPEL_CONVIDADA = "convidada"


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def _nome_da_origem(processo: dict) -> Optional[str]:
    """O parceiro angariador, se o processo veio de um. Sem nome conhecido: «Parceiro»."""
    if not _texto(processo.get("assigned_parceiro_id")):
        return None
    return _texto(processo.get("parceiro_name")) or "Parceiro"


def _filhos_por_rede(registo: list[dict], rede_dona: str) -> dict[str, list[dict]]:
    """`{rede do pai: [elos filhos]}`, com TODO o elo alcançável a partir da casa dona.

    Um elo cujo pai já não está no registo (entrada órfã de dados antigos) ou cujo caminho
    para a casa dona se perde num ciclo (dados corrompidos) pendura-se na casa dona:
    esconder um elo que dá acesso a alguém seria pior do que o mostrar mal.
    """
    pai_de: dict[str, str] = {}
    for entrada in registo:
        rede = _texto(entrada.get(CAMPO_REDE))
        pai_de[rede] = rede_de_origem_da_entrada(entrada, rede_dona)

    def chega_a_dona(rede: str) -> bool:
        vistas: set[str] = set()
        while rede != rede_dona:
            if rede in vistas or rede not in pai_de:
                return False
            vistas.add(rede)
            rede = pai_de[rede]
        return True

    for rede in list(pai_de):
        if not chega_a_dona(rede):
            pai_de[rede] = rede_dona

    filhos: dict[str, list[dict]] = {}
    for entrada in registo:
        filhos.setdefault(pai_de[_texto(entrada.get(CAMPO_REDE))], []).append(entrada)
    for lista in filhos.values():
        lista.sort(key=lambda e: _texto(e.get("added_at")))
    return filhos


def _no_da_empresa(entrada: dict, *, nivel: int, pai_nome: str) -> dict:
    return {
        "tipo": TIPO_EMPRESA,
        "papel": PAPEL_CONVIDADA,
        "nome": _texto(entrada.get("company_name")) or _texto(entrada.get("company_id")) or "?",
        "company_id": _texto(entrada.get("company_id")) or None,
        "network_id": _texto(entrada.get(CAMPO_REDE)) or None,
        "nivel": nivel,
        "partilhado_por": pai_nome or None,
        "em": entrada.get("added_at") if isinstance(entrada.get("added_at"), str) else None,
    }


def construir_linhagem(processo: Optional[dict], *, casa_dona: str = "") -> dict:
    """A linhagem de um processo, como o staff a vê.

    Devolve::

        {
          "origem":         {"tipo": "parceiro", "nome": ...} | None,
          "dona":           {"nome": ..., "network_id": ...},
          "caminhos":       [[nó, nó, …], …],   # um por folha, da origem à folha
          "empresa_actual": ["Z"],              # as folhas (onde está agora)
          "partilhas":      [{company_id, nome, network_id, partilhado_por, nivel, desde}, …],
          "profundidade":   n,                  # nº de empresas no caminho mais longo
          "tem_cadeia":     bool,               # alguma partilha em vigor
        }
    """
    processo = processo or {}
    rede_dona = _texto(processo.get(CAMPO_REDE))
    nome_dona = _texto(casa_dona) or _texto(processo.get("company_name")) or "Empresa dona"
    registo = parceiros_do_processo(processo)

    no_origem = None
    nome_origem = _nome_da_origem(processo)
    if nome_origem:
        no_origem = {"tipo": TIPO_PARCEIRO, "nome": nome_origem, "nivel": 0}

    no_dona = {
        "tipo": TIPO_EMPRESA,
        "papel": PAPEL_DONA,
        "nome": nome_dona,
        "company_id": _texto(processo.get("company_id")) or None,
        "network_id": rede_dona or None,
        "nivel": 1,
        "partilhado_por": None,
        "em": None,
    }

    filhos = _filhos_por_rede(registo, rede_dona)
    caminhos: list[list[dict]] = []
    folhas: list[str] = []
    partilhas: list[dict] = []
    profundidade = 1

    def descer(no_actual: dict, rede_actual: str, trilho: list[dict], vistos: frozenset) -> None:
        nonlocal profundidade
        profundidade = max(profundidade, len(trilho) - (1 if no_origem else 0))
        proximos = [f for f in filhos.get(rede_actual, []) if _texto(f.get(CAMPO_REDE)) not in vistos]
        if not proximos:
            caminhos.append(trilho)
            nome = no_actual["nome"]
            if nome not in folhas:
                folhas.append(nome)
            return
        for entrada in proximos:
            rede = _texto(entrada.get(CAMPO_REDE))
            no = _no_da_empresa(entrada, nivel=no_actual["nivel"] + 1, pai_nome=no_actual["nome"])
            partilhas.append({
                "company_id": no["company_id"],
                "nome": no["nome"],
                "network_id": no["network_id"],
                "partilhado_por": no["partilhado_por"],
                "nivel": no["nivel"],
                "desde": no["em"],
            })
            descer(no, rede, [*trilho, no], vistos | {rede})

    inicio = [no_origem, no_dona] if no_origem else [no_dona]
    descer(no_dona, rede_dona, inicio, frozenset({rede_dona}))

    return {
        "origem": no_origem,
        "dona": {"nome": nome_dona, "network_id": rede_dona or None},
        "caminhos": caminhos,
        "empresa_actual": folhas,
        "partilhas": partilhas,
        "profundidade": profundidade,
        "tem_cadeia": bool(registo),
    }


def empresas_onde_esta(processo: Optional[dict]) -> list[str]:
    """Os nomes das empresas que têm o processo AGORA (as folhas da cadeia).

    O que o PARCEIRO vê: onde está o caso que ele trouxe — nunca quem o passou a quem.
    Sem partilhas é a casa dona. Lista vazia se não se consegue dizer sem adivinhar.
    """
    processo = processo or {}
    if not parceiros_do_processo(processo) and not _texto(processo.get("company_name")):
        return []
    return list(construir_linhagem(processo)["empresa_actual"])


def marcar_o_que_posso_retirar(
    linhagem: dict, processo: dict, *, minhas_redes: set, sou_a_casa_dona: bool,
) -> None:
    """Acrescenta `pode_revogar` a cada partilha, para o ecrã só desenhar o botão certo.

    A casa dona retira qualquer elo; uma convidada só os que abriu ou que dela derivam
    (`process_sharing.elo_e_meu`). É a MESMA regra que o servidor aplica ao revogar — o
    papel (admin/CEO/diretor) continua a ser decidido à parte.
    """
    rede_dona = _texto(processo.get(CAMPO_REDE))
    registo = parceiros_do_processo(processo)
    por_rede = {_texto(e.get(CAMPO_REDE)): e for e in registo}
    for partilha in linhagem.get("partilhas", []):
        entrada = por_rede.get(_texto(partilha.get("network_id")))
        partilha["pode_revogar"] = bool(
            entrada is not None
            and (sou_a_casa_dona or elo_e_meu(registo, entrada, minhas_redes, rede_dona))
        )


async def anexar_linhagem(processo: dict, user: dict, *, casa_dona: str = "") -> None:
    """Põe `linhagem` no documento que vai para o ecrã de detalhe. Nunca levanta.

    Ao staff que vê o processo. Falhar aqui nunca pode estragar o detalhe.
    """
    try:
        from services.tenant_network import documento_no_ambito, resolve_tenant_scope

        scope = await resolve_tenant_scope(user or {})
        linhagem = construir_linhagem(processo, casa_dona=casa_dona)
        marcar_o_que_posso_retirar(
            linhagem, processo,
            minhas_redes={_texto(r) for r in scope.network_ids if _texto(r)},
            sou_a_casa_dona=bool(scope.sem_fronteira or documento_no_ambito(processo, scope)),
        )
        processo["linhagem"] = linhagem
    except Exception as exc:  # noqa: BLE001 - leitura: nunca estragar o detalhe
        logger.warning(
            "[LINHAGEM] Falha a construir a linhagem de %s: %s", (processo or {}).get("id"), exc
        )
        processo["linhagem"] = None


__all__ = [
    "anexar_linhagem",
    "construir_linhagem",
    "empresas_onde_esta",
    "marcar_o_que_posso_retirar",
]
