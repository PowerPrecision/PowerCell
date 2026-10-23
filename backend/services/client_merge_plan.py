"""
====================================================================
FUSÃO DE CLIENTES DUPLICADOS (D-42/D-40) — O PLANO, PURO
====================================================================
A direcção decidiu que **NIF e Email definem um cliente único em toda a base
de dados** (o telemóvel não conta). A base é antiga e tem duplicados — o mesmo
NIF em duas redes eram "dois clientes" até ao D-38. Este módulo decide, sem
escrever nada, **quais clientes se fundem em qual**; quem escreve é
`scripts/resolve_client_duplicates.py`, que executa o plano.

DOIS VEREDICTOS, E O QUE NÃO SE ADIVINHA
  `fundir`   — um grupo ligado por NIF e/ou Email onde NÃO há dois NIFs
               diferentes: é a mesma pessoa. Escolhe-se um sobrevivente e os
               outros são absorvidos.
  `ambiguo`  — o grupo junta dois NIFs DIFERENTES por um email partilhado (um
               casal que usa o mesmo email; um mediador que preenche os dois):
               são duas pessoas. **Nunca se funde sozinho**: decide-se à mão
               (corrigir o email de um deles) e o índice único do email só
               se constrói depois. Fundir aqui juntava dados de duas pessoas.
  Dois emails diferentes com o mesmo NIF são a mesma pessoa (o NIF é a
  identidade fiscal) e fundem-se; o email do absorvido fica no registo dele.

O SOBREVIVENTE
  O que tem mais processos (é o que menos obriga a reapontar), depois o que
  completou o registo, depois o mais antigo, depois o id — uma ordem total,
  para correr duas vezes dar o mesmo resultado.

O QUE A FUSÃO NÃO FAZ
  * Não mexe no S3: nada se move (mover objectos produziu as 205 ligações
    partidas do Épico 10). A pasta do absorvido fica registada em `fundido_de`.
  * Não reescreve o que o sobrevivente já tem: só PREENCHE o que lhe falta
    (secções de dados pessoais, contacto e financeiros).
  * Não perde a segregação: as redes dos processos do absorvido ficam em
    `redes_associadas` do sobrevivente, que passa a ser um *visitante* delas
    (a janela de `client_window`) — cada equipa continua a ver só o seu processo.
====================================================================
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable

from services.client_duplicates_audit import Registo
from services.client_uniqueness import CAMPO_EMAIL, CAMPO_NIF

FUNDIR = "fundir"
AMBIGUO = "ambiguo"

MOTIVO_NIFS_DIFERENTES = "nifs_diferentes_ligados_por_email"

#: As secções do cliente de que se preenche o que falta (nunca se sobrepõe o que existe).
SECCOES_A_PREENCHER = ("contacto", "dados_pessoais", "dados_financeiros", "dados_imobiliarios")

#: Identidade: estes campos NÃO se preenchem a partir do absorvido (o sobrevivente mantém a SUA;
#: copiar o NIF/email de outra pessoa-registo para o sobrevivente é trocar a identidade).
CAMPOS_DE_IDENTIDADE = {
    "contacto": ("email", "email_hash"),
    "dados_pessoais": ("nif", "nif_hash"),
}


@dataclass(frozen=True)
class Candidato:
    """Um cliente activo reduzido ao que o plano precisa."""

    registo: Registo
    #: O documento tal como está na base (cifrado) — dele saem os campos a preencher.
    doc: dict
    n_processos: int = 0


@dataclass(frozen=True)
class PlanoDeFusao:
    veredicto: str
    membros: tuple[str, ...]
    sobrevivente: str
    absorvidos: tuple[str, ...]
    #: Só para `ambiguo`: porque é que não se funde sozinho.
    motivo: str = ""
    #: Redes dos absorvidos que o sobrevivente passa a ter como associadas (sem a dele).
    redes_a_associar: tuple[str, ...] = ()
    #: ``absorvido → {"secção.campo": valor}`` — o que o sobrevivente PREENCHE.
    preenchimentos: dict[str, dict[str, Any]] = field(default_factory=dict)


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def _vazio(valor: Any) -> bool:
    return valor is None or valor == "" or valor == [] or valor == {}


# --------------------------------------------------------------------
# Agrupar: componentes ligados por NIF ou Email
# --------------------------------------------------------------------
def componentes(candidatos: Iterable[Candidato]) -> list[list[Candidato]]:
    """Os conjuntos de clientes ligados (directa ou indirectamente) por NIF ou Email."""
    por_id = {c.registo.id: c for c in candidatos if c.registo.id}
    pai: dict[str, str] = {i: i for i in por_id}

    def raiz(x: str) -> str:
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    vistos: dict[tuple[str, str], str] = {}
    for cid, c in por_id.items():
        for campo in (CAMPO_NIF, CAMPO_EMAIL):
            chave = c.registo.chave(campo)
            if not chave:
                continue
            anterior = vistos.setdefault((campo, chave), cid)
            if anterior != cid:
                pai[raiz(cid)] = raiz(anterior)

    grupos: dict[str, list[Candidato]] = {}
    for cid, c in por_id.items():
        grupos.setdefault(raiz(cid), []).append(c)
    return [sorted(g, key=lambda c: c.registo.id) for g in grupos.values() if len(g) >= 2]


# --------------------------------------------------------------------
# Escolher o sobrevivente
# --------------------------------------------------------------------
def _chave_de_sobrevivencia(c: Candidato) -> tuple:
    registo_completo = bool(c.doc.get("registration_completed"))
    return (
        -c.n_processos,
        0 if registo_completo else 1,
        _texto(c.doc.get("created_at")) or "9999",
        c.registo.id,
    )


def escolher_sobrevivente(grupo: list[Candidato]) -> Candidato:
    return min(grupo, key=_chave_de_sobrevivencia)


# --------------------------------------------------------------------
# O que o sobrevivente preenche
# --------------------------------------------------------------------
def preencher_o_que_falta(sobrevivente: dict, absorvido: dict) -> dict[str, Any]:
    """``{"secção.campo": valor}`` do absorvido onde o sobrevivente NÃO tem nada.

    Valores copiados TAL COMO ESTÃO (cifrados, quando o são): a cifra é a mesma em todo o
    cliente, e decifrar para voltar a cifrar abria uma janela para o texto simples sem razão.
    Os campos de identidade ficam de fora (ver `CAMPOS_DE_IDENTIDADE`).
    """
    saida: dict[str, Any] = {}
    for seccao in SECCOES_A_PREENCHER:
        origem = absorvido.get(seccao)
        if not isinstance(origem, dict):
            continue
        destino = sobrevivente.get(seccao)
        destino = destino if isinstance(destino, dict) else {}
        proibidos = CAMPOS_DE_IDENTIDADE.get(seccao, ())
        for campo, valor in origem.items():
            if campo in proibidos or _vazio(valor):
                continue
            if _vazio(destino.get(campo)):
                saida[f"{seccao}.{campo}"] = valor
    return saida


# --------------------------------------------------------------------
# O plano
# --------------------------------------------------------------------
def _nifs_distintos(grupo: list[Candidato]) -> set[str]:
    return {c.registo.nif for c in grupo if c.registo.nif}


def planear(candidatos: Iterable[Candidato]) -> list[PlanoDeFusao]:
    """Um plano por grupo de duplicados, dos maiores para os mais pequenos."""
    planos: list[PlanoDeFusao] = []
    for grupo in componentes(candidatos):
        membros = tuple(c.registo.id for c in grupo)
        sobrevivente = escolher_sobrevivente(grupo)

        if len(_nifs_distintos(grupo)) >= 2:
            planos.append(PlanoDeFusao(
                veredicto=AMBIGUO,
                membros=membros,
                sobrevivente=sobrevivente.registo.id,
                absorvidos=(),
                motivo=MOTIVO_NIFS_DIFERENTES,
            ))
            continue

        absorvidos = [c for c in grupo if c.registo.id != sobrevivente.registo.id]
        redes = sorted({
            c.registo.rede for c in absorvidos
            if c.registo.rede and c.registo.rede != sobrevivente.registo.rede
        })
        planos.append(PlanoDeFusao(
            veredicto=FUNDIR,
            membros=membros,
            sobrevivente=sobrevivente.registo.id,
            absorvidos=tuple(c.registo.id for c in absorvidos),
            redes_a_associar=tuple(redes),
            preenchimentos={
                c.registo.id: preencher_o_que_falta(sobrevivente.doc, c.doc) for c in absorvidos
            },
        ))
    planos.sort(key=lambda p: (p.veredicto != FUNDIR, -len(p.membros), p.membros))
    return planos


def resumir(planos: Iterable[PlanoDeFusao]) -> dict:
    planos = list(planos)
    fundir = [p for p in planos if p.veredicto == FUNDIR]
    return {
        "grupos": len(planos),
        "a_fundir": len(fundir),
        "ambiguos": sum(1 for p in planos if p.veredicto == AMBIGUO),
        "clientes_absorvidos": sum(len(p.absorvidos) for p in fundir),
        "atravessam_redes": sum(1 for p in fundir if p.redes_a_associar),
        # Os índices únicos só se constroem sem NENHUM grupo por resolver, ambíguos incluídos.
        "indice_unico_viavel": not planos,
    }


__all__ = [
    "AMBIGUO",
    "Candidato",
    "FUNDIR",
    "MOTIVO_NIFS_DIFERENTES",
    "PlanoDeFusao",
    "componentes",
    "escolher_sobrevivente",
    "planear",
    "preencher_o_que_falta",
    "resumir",
]
