"""
====================================================================
DIAGNÓSTICO DE DUPLICADOS DE CLIENTES POR REDE (D-38) — PURO
====================================================================
A regra «NIF, Email e Telemóvel não se repetem dentro da rede»
(`client_uniqueness`) é NOVA e a base de dados é ANTIGA. Este módulo
responde, sem escrever nada, a uma pergunta de operações: **quantos
clientes violam a regra hoje, em que rede, e por que campo?** É esse
número que decide se um índice único por rede é viável ou se há uma
limpeza manual antes dele (a corrida entre dois pedidos simultâneos é a
parte da D-38 que só um índice fecha).

A IDENTIDADE É A DA GUARDA, NÃO UMA SEGUNDA REGRA
  Duas cópias da mesma regra divergem sem dar erro. O valor-chave de cada
  campo sai das mesmas peças que o `client_uniqueness` usa:
    * NIF       — 9 dígitos (o `generate_nif_hash` ignora o resto);
    * Email     — aparado e em minúsculas;
    * Telemóvel — `telefones_candidatos(...)[0]`: `912 345 678`,
                  `+351 912 345 678` e `00351912345678` são o mesmo.
  Um valor que a guarda não consegue indexar (NIF com 8 dígitos, telefone
  com 5) não identifica ninguém e aqui também não conta.

COMO SE ATRIBUI UMA REDE A UM CLIENTE
  `network_id` do carimbo; senão a rede da EMPRESA (a ilha implícita
  `rede:<id>` quando a empresa não tem grupo); senão a pilha por carimbar,
  que pertence à rede de omissão (`TENANT_DEFAULT_NETWORK_ID`). Sem essa
  variável a pilha fica num grupo à parte (`SEM_REDE`) e isso é DITO —
  nunca se funde com uma rede concreta por adivinhação.

O QUE NÃO É VIOLAÇÃO
  O mesmo NIF em DUAS redes são dois clientes (D-32: «a mesma pessoa em
  duas redes são dois clientes»). Conta-se à parte, como informação, e não
  entra nos grupos. Eliminados (`is_deleted`/`status="eliminado"`) não
  bloqueiam a guarda, logo também não entram aqui.

PRIVACIDADE
  O relatório diz QUAIS valores se repetem, mas por omissão mascarados
  (`*****9461`, `a***@dominio.pt`): o operador abre o cliente pelo `id`.
  Os valores completos exigem pedido explícito no script.
====================================================================
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from services.client_uniqueness import (
    CAMPO_EMAIL,
    CAMPO_NIF,
    CAMPO_TELEFONE,
    CAMPOS_UNICOS,
    telefones_candidatos,
)
from services.tenant_network import CAMPOS_EMPRESA, CAMPO_REDE, rede_de_omissao, resolve_network_id

#: Grupo da pilha por carimbar quando `TENANT_DEFAULT_NETWORK_ID` não existe.
SEM_REDE = "(por carimbar)"

PREFIXO_CIFRADO = "ENC:"

CONDICAO_ELIMINADO_STATUS = "eliminado"


# --------------------------------------------------------------------
# Identidade de cada campo
# --------------------------------------------------------------------
def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def chave_nif(valor: Any) -> Optional[str]:
    digitos = re.sub(r"\D", "", _texto(valor))
    return digitos if len(digitos) == 9 else None


def chave_email(valor: Any) -> Optional[str]:
    texto = _texto(valor).lower()
    return texto or None


def chave_telefone(valor: Any) -> Optional[str]:
    candidatos = telefones_candidatos(_texto(valor))
    return candidatos[0] if candidatos else None


_CHAVES = {CAMPO_NIF: chave_nif, CAMPO_EMAIL: chave_email, CAMPO_TELEFONE: chave_telefone}


def esta_eliminado(doc: dict) -> bool:
    return bool(doc.get("is_deleted")) or doc.get("status") == CONDICAO_ELIMINADO_STATUS


# --------------------------------------------------------------------
# O registo auditado
# --------------------------------------------------------------------
@dataclass(frozen=True)
class Registo:
    """Um cliente reduzido ao que a auditoria precisa (já com a rede)."""

    id: str
    rede: str
    nif: Optional[str] = None
    email: Optional[str] = None
    telefone: Optional[str] = None
    nome: str = ""
    #: Campos cuja chave veio do índice cego por o valor não se ter podido
    #: decifrar. Contam-se e dizem-se: um relatório que não os visse seria
    #: um limite inferior apresentado como total.
    sem_decifrar: tuple[str, ...] = ()

    def chave(self, campo: str) -> Optional[str]:
        return getattr(self, campo)


def _valor_ou_indice(valor: Any, indice: Any, prefixo: str, normaliza) -> tuple[Optional[str], bool]:
    """(chave, veio_do_indice). O índice cego só entra quando o valor está cifrado."""
    texto = _texto(valor)
    if texto.startswith(PREFIXO_CIFRADO):
        indice_texto = _texto(indice)
        return (f"{prefixo}:{indice_texto}" if indice_texto else None), True
    return normaliza(texto), False


def registo_de(
    doc: dict, *, rede: str, decifrar=None,
) -> Registo:
    """Reduz um documento de cliente (tal como está na base) a um `Registo`.

    `decifrar` é a função do cifrador de produção (`decrypt_client_data`);
    sem ela, os valores cifrados caem para o índice cego.
    """
    if decifrar is not None:
        try:
            doc = decifrar(doc)
        except Exception:
            pass
    dados = doc.get("dados_pessoais") or {}
    contacto = doc.get("contacto") or {}

    nif, nif_cego = _valor_ou_indice(dados.get("nif"), dados.get("nif_hash"), "nif-hash", chave_nif)
    email, email_cego = _valor_ou_indice(contacto.get("email"), contacto.get("email_hash"), "email-hash", chave_email)
    telefone, tel_cego = _valor_ou_indice(
        contacto.get("telefone"), contacto.get("telefone_hash"), "telefone-hash", chave_telefone,
    )
    cegos = tuple(
        c for c, cego in ((CAMPO_NIF, nif_cego), (CAMPO_EMAIL, email_cego), (CAMPO_TELEFONE, tel_cego))
        if cego
    )
    return Registo(
        id=_texto(doc.get("id")),
        rede=rede,
        nif=nif,
        email=email,
        telefone=telefone,
        nome=_texto(doc.get("nome") or doc.get("name") or doc.get("client_name")),
        sem_decifrar=cegos,
    )


def rede_do_documento(doc: dict, redes_das_empresas: dict[str, Optional[str]]) -> str:
    """A rede a que o cliente pertence, pela ordem: carimbo → empresa → omissão."""
    carimbo = _texto(doc.get(CAMPO_REDE))
    if carimbo:
        return carimbo
    for campo in CAMPOS_EMPRESA:
        empresa = _texto(doc.get(campo))
        if empresa:
            return redes_das_empresas.get(empresa) or resolve_network_id(None, company_id=empresa) or SEM_REDE
    return rede_de_omissao() or SEM_REDE


# --------------------------------------------------------------------
# A auditoria
# --------------------------------------------------------------------
@dataclass(frozen=True)
class Grupo:
    rede: str
    campo: str
    chave: str
    membros: tuple[str, ...]  # ids dos clientes, por ordem estável


@dataclass
class Relatorio:
    total_clientes: int = 0
    grupos: list[Grupo] = field(default_factory=list)
    #: rede → nº de clientes activos auditados nela
    clientes_por_rede: dict[str, int] = field(default_factory=dict)
    #: Conjuntos de clientes ligados por qualquer campo (uma «pessoa duplicada»
    #: são N linhas): o nº de decisões humanas é este, não o de grupos.
    casos: list[tuple[str, ...]] = field(default_factory=list)
    #: Valores partilhados entre redes DIFERENTES — informação, não violação.
    partilhados_entre_redes: dict[str, int] = field(default_factory=dict)
    sem_decifrar: dict[str, int] = field(default_factory=dict)
    sem_rede_de_omissao: bool = False

    @property
    def clientes_afectados(self) -> int:
        return sum(len(c) for c in self.casos)


def auditar(registos: Iterable[Registo]) -> Relatorio:
    """Agrupa por (rede, campo, chave) e devolve só os grupos com 2+ clientes."""
    relatorio = Relatorio()
    por_grupo: dict[tuple[str, str, str], list[str]] = {}
    por_valor: dict[tuple[str, str], set[str]] = {}
    rede_de: dict[str, str] = {}

    for r in registos:
        if not r.id:
            continue
        relatorio.total_clientes += 1
        relatorio.clientes_por_rede[r.rede] = relatorio.clientes_por_rede.get(r.rede, 0) + 1
        rede_de[r.id] = r.rede
        for campo in r.sem_decifrar:
            relatorio.sem_decifrar[campo] = relatorio.sem_decifrar.get(campo, 0) + 1
        for campo in CAMPOS_UNICOS:
            chave = r.chave(campo)
            if not chave:
                continue
            por_grupo.setdefault((r.rede, campo, chave), []).append(r.id)
            por_valor.setdefault((campo, chave), set()).add(r.rede)

    relatorio.sem_rede_de_omissao = rede_de_omissao() is None
    for (rede, campo, chave), ids in por_grupo.items():
        if len(set(ids)) >= 2:
            relatorio.grupos.append(Grupo(rede, campo, chave, tuple(sorted(set(ids)))))
    relatorio.grupos.sort(key=lambda g: (-len(g.membros), g.rede, g.campo, g.chave))

    for (campo, _chave), redes in por_valor.items():
        if len(redes) >= 2:
            relatorio.partilhados_entre_redes[campo] = relatorio.partilhados_entre_redes.get(campo, 0) + 1

    relatorio.casos = _casos(relatorio.grupos)
    return relatorio


def _casos(grupos: list[Grupo]) -> list[tuple[str, ...]]:
    """Componentes ligados: dois grupos que partilham um cliente são UM caso."""
    pai: dict[str, str] = {}

    def raiz(x: str) -> str:
        pai.setdefault(x, x)
        while pai[x] != x:
            pai[x] = pai[pai[x]]
            x = pai[x]
        return x

    for g in grupos:
        primeiro = raiz(g.membros[0])
        for outro in g.membros[1:]:
            pai[raiz(outro)] = primeiro
    componentes: dict[str, set[str]] = {}
    for x in list(pai):
        componentes.setdefault(raiz(x), set()).add(x)
    return sorted((tuple(sorted(c)) for c in componentes.values()), key=lambda c: (-len(c), c))


def resumir(relatorio: Relatorio) -> dict:
    """Os números do relatório, por rede e por campo (sem valores pessoais)."""
    por_rede: dict[str, dict[str, Any]] = {}
    for g in relatorio.grupos:
        linha = por_rede.setdefault(
            g.rede, {"grupos": {c: 0 for c in CAMPOS_UNICOS}, "clientes": set()},
        )
        linha["grupos"][g.campo] += 1
        linha["clientes"].update(g.membros)
    return {
        "total_clientes": relatorio.total_clientes,
        "clientes_por_rede": dict(relatorio.clientes_por_rede),
        "grupos": len(relatorio.grupos),
        "casos": len(relatorio.casos),
        "clientes_afectados": relatorio.clientes_afectados,
        "por_rede": {
            rede: {"grupos": v["grupos"], "clientes": len(v["clientes"])}
            for rede, v in sorted(por_rede.items())
        },
        "por_campo": {c: sum(1 for g in relatorio.grupos if g.campo == c) for c in CAMPOS_UNICOS},
        "partilhados_entre_redes": dict(relatorio.partilhados_entre_redes),
        "sem_decifrar": dict(relatorio.sem_decifrar),
        "sem_rede_de_omissao": relatorio.sem_rede_de_omissao,
        # Zero clientes lidos não é «sem duplicados»: é, quase de certeza, a base errada.
        "indice_unico_viavel": relatorio.total_clientes > 0 and not relatorio.grupos,
    }


# --------------------------------------------------------------------
# Máscara
# --------------------------------------------------------------------
def mascarar(campo: str, chave: str) -> str:
    """O valor de um grupo sem o expor: o suficiente para o reconhecer, não para o usar."""
    if ":" in chave and chave.split(":", 1)[0].endswith("-hash"):
        return f"(índice cego …{chave[-6:]})"
    if campo == CAMPO_EMAIL:
        local, _, dominio = chave.partition("@")
        return f"{local[:1]}***@{dominio}" if dominio else "***"
    return "*" * max(len(chave) - 4, 0) + chave[-4:]


def mostrar(campo: str, chave: str, *, valores_completos: bool) -> str:
    return chave if valores_completos else mascarar(campo, chave)


__all__ = [
    "Grupo",
    "Registo",
    "Relatorio",
    "SEM_REDE",
    "auditar",
    "chave_email",
    "chave_nif",
    "chave_telefone",
    "esta_eliminado",
    "mascarar",
    "mostrar",
    "rede_do_documento",
    "registo_de",
    "resumir",
]
