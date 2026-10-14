"""Migração dos `co_buyers` gravados pelo mapeador do CPCV antigo (D-18, Lote 5).

O DEFEITO
  `co_buyers` tinha DOIS significados. O mapeador do CPCV (`ai_document`) gravava TODOS os compradores
  — o elemento 0 era o titular 1, de quem copiava o `personal_data` — e o `build_add_client_update`
  grava só os ADICIONAIS. Contar elementos («há 2 compradores») dava resultados diferentes conforme
  quem escreveu o array, e a regra Sub35 teve de desduplicar por identidade para não se desligar.

A CORRECÇÃO (já em produção no mapeador): o campo passa a ter UM significado — os adicionais. Falta
o que já está gravado: os documentos escritos pelo mapeador antigo têm o titular 1 em `co_buyers[0]`.
Este módulo (PURO) decide, documento a documento e COM PROVA, se esse elemento é o titular 1.

REGRAS
  * só se retira o elemento 0 quando se PROVA que é o titular 1: partilha uma identidade (nome, NIF,
    CC) com o titular 1 do processo e NÃO é um elemento do add-client (esses levam `client_id` e
    `relacao`, e o titular 2 que representam não é duplicado de ninguém);
  * a prova é por IGUALDADE exacta depois de normalizada (`sub35._normalizar_identidade`): um score de
    similaridade entre nomes produziu a colisão de pastas do Lote 6, e aqui abriria a migração no
    sentido errado — apagar um comprador que existe;
  * na dúvida NÃO se toca (`ambiguo`) e o caso vai para o relatório: um comprador a mais lê-se,
    um comprador a menos perde-se;
  * idempotente: depois de migrado, `co_buyers[0]` já não é o titular 1 e o veredicto passa a
    `ja_adicionais`.
"""
from __future__ import annotations

from typing import Any, Optional

from services.sub35 import (
    CHAVES_DE_IDENTIDADE_DO_COMPRADOR,
    SECCOES_DO_CLIENTE,
    SECCOES_DO_PROCESSO,
    _normalizar_identidade,
)

SECCAO = "co_buyers"

#: O elemento 0 é o titular 1 repetido: retira-se.
VEREDICTO_RETIRAR_O_TITULAR_1 = "retirar_o_titular_1"
#: Já só tem adicionais (escritos pelo add-client, ou já migrados): nada a fazer.
VEREDICTO_JA_ADICIONAIS = "ja_adicionais"
#: Não se consegue provar que o elemento 0 é o titular 1: fica como está, para decisão humana.
VEREDICTO_AMBIGUO = "ambiguo"
#: Sem compradores adicionais.
VEREDICTO_SEM_CO_BUYERS = "sem_co_buyers"

#: As chaves que o `build_add_client_update` põe em cada elemento e o mapeador nunca pôs.
MARCAS_DO_ADD_CLIENT = ("client_id", "relacao")

ROTULOS = {
    VEREDICTO_RETIRAR_O_TITULAR_1: "migrável — o elemento 0 é o titular 1",
    VEREDICTO_AMBIGUO: "EXIGE DECISÃO — o elemento 0 não se prova ser o titular 1",
    VEREDICTO_JA_ADICIONAIS: "já só tem adicionais",
    VEREDICTO_SEM_CO_BUYERS: "sem co_buyers",
}


def _identidades_do_titular_1(doc: dict) -> set[str]:
    """Quem é o titular 1 (nunca o 2): o nome do processo/cliente e as secções do titular."""
    identidades: set[str] = set()
    candidatos: list[Any] = [doc.get("client_name"), doc.get("nome")]
    for seccao in (*SECCOES_DO_PROCESSO, *SECCOES_DO_CLIENTE):
        bloco = doc.get(seccao)
        if isinstance(bloco, dict):
            candidatos.extend(bloco.get(chave) for chave in CHAVES_DE_IDENTIDADE_DO_COMPRADOR)
    for valor in candidatos:
        token = _normalizar_identidade(valor)
        if token:
            identidades.add(token)
    return identidades


def _identidades_do_comprador(comprador: dict) -> set[str]:
    return {
        token for token in (
            _normalizar_identidade(comprador.get(chave)) for chave in CHAVES_DE_IDENTIDADE_DO_COMPRADOR
        ) if token
    }


def classificar(doc: Optional[dict]) -> str:
    """O veredicto para UM processo. PURA — o documento tem de vir DESENCRIPTADO
    (o NIF e o CC dos `co_buyers` estão cifrados em repouso)."""
    if not isinstance(doc, dict):
        return VEREDICTO_SEM_CO_BUYERS
    compradores = doc.get(SECCAO)
    if not isinstance(compradores, (list, tuple)) or not compradores:
        return VEREDICTO_SEM_CO_BUYERS

    primeiro = compradores[0]
    if not isinstance(primeiro, dict):
        return VEREDICTO_AMBIGUO
    if any(primeiro.get(marca) for marca in MARCAS_DO_ADD_CLIENT):
        return VEREDICTO_JA_ADICIONAIS

    if _identidades_do_comprador(primeiro) & _identidades_do_titular_1(doc):
        return VEREDICTO_RETIRAR_O_TITULAR_1
    # Sem marcas do add-client e sem identidade do titular 1: pode ser um adicional escrito pelo
    # mapeador novo (legítimo) ou o titular 1 sob outro nome (um CPCV com a grafia do cartão de
    # cidadão). Não se adivinha.
    return VEREDICTO_AMBIGUO


def sem_o_primeiro(compradores_em_bruto: list) -> Optional[list]:
    """A lista a gravar (a forma ENCRIPTADA, tal como está na base): tudo menos o elemento 0.
    ``None`` quando não sobra ninguém — quem aplica faz `$unset` (um campo ausente é «sem adicionais»)."""
    resto = list(compradores_em_bruto[1:])
    return resto or None


def resumir(veredictos: list[str]) -> dict[str, int]:
    resumo = {v: 0 for v in ROTULOS}
    for v in veredictos:
        resumo[v] = resumo.get(v, 0) + 1
    return resumo


__all__ = [
    "MARCAS_DO_ADD_CLIENT",
    "ROTULOS",
    "VEREDICTO_AMBIGUO",
    "VEREDICTO_JA_ADICIONAIS",
    "VEREDICTO_RETIRAR_O_TITULAR_1",
    "VEREDICTO_SEM_CO_BUYERS",
    "classificar",
    "resumir",
    "sem_o_primeiro",
]
