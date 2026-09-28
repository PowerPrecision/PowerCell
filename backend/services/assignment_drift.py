"""Desfasamento entre a LISTA de atribuídos e os campos singulares.

PORQUE É QUE ISTO EXISTE (Lote 6, ponto 8)
==========================================
Quem grava uma atribuição escreve o conjunto CANÓNICO completo
(`process_staff_assignment.CONSULTOR_ID_FIELDS` / `MEDIADOR_ID_FIELDS`):
uma lista (`assigned_consultor_ids`) mais três campos singulares que
repetem o primeiro id. Até ao Lote 5, `build_clear_consultor_fields`
limpava quatro dos seis campos e deixava `consultor_id` e `consultant_id`
com o valor ANTIGO.

Essa correcção parou de PRODUZIR o problema. **Não limpou o que já
existia.** Um processo desatribuído antes dela continua a carregar o id do
ex-consultor — e há dois leitores que o consultam:

  * `services/alerts.py`, que notifica quem estiver em `consultor_id`;
  * `process_list_filters`, que usa `consultant_id` em "Os Meus Processos".

É a hipótese principal para os alertas que chegam a consultores de
processos que não são deles.

A DISTINÇÃO QUE NÃO SE PODE PERDER
==================================
"Lista vazia + campo singular preenchido" **não é** sinónimo de resíduo. O
`dual_auto_assign_on_pre_registo_transition` gravava SÓ `consultant_id`
(ver AGENTS.md, "Atribuição: campos CANÓNICOS"), pelo que há processos
legitimamente atribuídos cuja lista nunca foi escrita. Limpar esses
DESATRIBUI trabalho real, e um processo sem dono não se nota até alguém
reparar que ninguém lhe pega.

Por isso há três veredictos, e só dois são seguros de corrigir sozinhos:

  ``divergente``  a lista tem gente E o singular aponta para fora dela.
                  Inequívoco: a lista é a verdade, o singular é resíduo.
  ``em_falta``    a lista tem gente E o singular está vazio.
                  Inequívoco: perde notificações; preenche-se com o 1.º id.
  ``ambiguo``     a lista está vazia E o singular tem valor.
                  **Indecidível a partir do documento.** Pode ser resíduo
                  de uma desatribuição antiga ou uma atribuição legada que
                  nunca escreveu a lista. Conta-se, mostra-se, e só se
                  corrige por ordem explícita.

Módulo PURO: não toca na base de dados nem no ambiente, para o script de
diagnóstico e os testes usarem exactamente a mesma lógica.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Optional

from services.process_staff_assignment import (
    CONSULTOR_ID_FIELDS,
    MEDIADOR_ID_FIELDS,
)

#: (papel, campo da lista, campos singulares) — derivado das constantes de
#: produção de propósito: uma lista escrita à mão aqui divergiria do `set`
#: e do `clear` na primeira mudança, que é o defeito original com outro nome.
PAPEIS = (
    ("consultor", "assigned_consultor_ids", CONSULTOR_ID_FIELDS),
    ("mediador", "assigned_mediador_ids", MEDIADOR_ID_FIELDS),
)

VEREDICTO_DIVERGENTE = "divergente"
VEREDICTO_EM_FALTA = "em_falta"
VEREDICTO_AMBIGUO = "ambiguo"


@dataclass(frozen=True)
class Desfasamento:
    """Um campo singular que não concorda com a lista."""

    papel: str
    campo: str
    valor_actual: Optional[str]
    valor_esperado: Optional[str]
    veredicto: str

    @property
    def e_seguro_corrigir(self) -> bool:
        """`ambiguo` fica de fora: corrigi-lo pode desatribuir trabalho real."""
        return self.veredicto in (VEREDICTO_DIVERGENTE, VEREDICTO_EM_FALTA)


def _lista_de_ids(processo: dict, campo: str) -> list[str]:
    valor = (processo or {}).get(campo)
    if not isinstance(valor, list):
        return []
    return [str(v) for v in valor if v]


def _texto(valor: Any) -> Optional[str]:
    if valor is None:
        return None
    texto = str(valor).strip()
    return texto or None


def desfasamentos_do_processo(processo: dict) -> list[Desfasamento]:
    """Todos os campos singulares que não concordam com a sua lista.

    Devolve `[]` para um processo coerente — incluindo o caso comum de
    tudo vazio (um processo por atribuir não está desfasado, está por
    atribuir).
    """
    encontrados: list[Desfasamento] = []

    for papel, campo_da_lista, campos_singulares in PAPEIS:
        ids = _lista_de_ids(processo, campo_da_lista)
        esperado = ids[0] if ids else None

        for campo in campos_singulares:
            actual = _texto((processo or {}).get(campo))

            if actual == esperado:
                continue

            if not ids:
                veredicto = VEREDICTO_AMBIGUO
            elif actual is None:
                veredicto = VEREDICTO_EM_FALTA
            else:
                veredicto = VEREDICTO_DIVERGENTE

            encontrados.append(
                Desfasamento(
                    papel=papel,
                    campo=campo,
                    valor_actual=actual,
                    valor_esperado=esperado,
                    veredicto=veredicto,
                )
            )

    return encontrados


def correccao_do_processo(
    processo: dict,
    *,
    incluir_ambiguos: bool = False,
    historicos_por_papel: Optional[dict[str, Iterable[dict]]] = None,
) -> dict[str, Any]:
    """O `$set` que põe os singulares de acordo com a lista.

    Vazio quando não há nada seguro a corrigir. Os `ambiguo` só entram por
    ordem explícita (`incluir_ambiguos=True`) — ver o cabeçalho do módulo.

    LOTE 6 — `incluir_ambiguos` deixou de significar "limpa TODOS os
    ambíguos". Limpa os que se provam resíduo de uma desatribuição
    (`origem_do_ambiguo`); os de origem `atribuicao_legada` ou
    `indeterminada` continuam intactos **mesmo com a bandeira ligada**,
    porque limpá-los deixa o processo sem dono. A bandeira autoriza a
    escrita; não substitui a prova.
    """
    correccao: dict[str, Any] = {}
    origens: dict[str, str] = {}
    historicos = historicos_por_papel or {}

    for d in desfasamentos_do_processo(processo):
        if d.e_seguro_corrigir:
            correccao[d.campo] = d.valor_esperado
            continue
        if not incluir_ambiguos:
            continue
        if d.papel not in origens:
            origens[d.papel] = origem_do_ambiguo(
                processo, d.papel, historico=historicos.get(d.papel)
            )
        if origens[d.papel] == ORIGEM_DESATRIBUICAO:
            correccao[d.campo] = d.valor_esperado

    return correccao


def resumir(processos: Iterable[dict]) -> dict[str, Any]:
    """Contagens agregadas — é isto que o diagnóstico imprime.

    `por_campo` é o que interessa ao Ponto 8: `consultor_id` e
    `consultant_id` são os dois que o `build_clear_consultor_fields`
    deixava para trás, e são os dois que os alertas e "Os Meus Processos"
    leem.
    """
    total = 0
    afectados = 0
    por_veredicto: dict[str, int] = {}
    por_campo: dict[str, int] = {}
    corrigiveis = 0
    ambiguos_por_decidir = 0

    for processo in processos:
        total += 1
        desfasados = desfasamentos_do_processo(processo)
        if not desfasados:
            continue
        afectados += 1
        seguro = False
        ambiguo = False
        for d in desfasados:
            por_veredicto[d.veredicto] = por_veredicto.get(d.veredicto, 0) + 1
            por_campo[d.campo] = por_campo.get(d.campo, 0) + 1
            if d.e_seguro_corrigir:
                seguro = True
            else:
                ambiguo = True
        if seguro:
            corrigiveis += 1
        if ambiguo:
            ambiguos_por_decidir += 1

    return {
        "total_analisados": total,
        "processos_afectados": afectados,
        "processos_corrigiveis": corrigiveis,
        "processos_ambiguos": ambiguos_por_decidir,
        "por_veredicto": por_veredicto,
        "por_campo": por_campo,
    }


# ────────────────────────────────────────────────────────────────────
# DESAMBIGUAR O `ambiguo` (Lote 6 — a leitura dos números)
#
# O diagnóstico em produção devolveu 213 campos ambíguos. "Lista vazia +
# singular preenchido" continua a ser indecidível **pelo valor do
# campo** — mas não pela ASSINATURA do documento, porque os dois
# escritores antigos deixavam rastos diferentes:
#
#   `build_clear_consultor_fields` (pré-Lote 5)
#       limpava a lista, os nomes e `assigned_consultor_id`, e deixava
#       `consultor_id` + `consultant_id` → assinatura de DOIS campos.
#
#   `dual_auto_assign_on_pre_registo_transition` (pré-`d8a739d1`)
#       escrevia SÓ `consultant_id` → assinatura de UM campo.
#
# Para o consultor isto decide. Para o mediador NÃO decide: ambos os
# escritores antigos deixavam apenas `mediador_id`, e é preciso a
# segunda fonte de prova — o histórico do processo.
#
# A pergunta que o histórico responde é uma só: **o último acontecimento
# de atribuição deste papel foi uma remoção ou uma atribuição?** Se foi
# remoção, o singular é resíduo e limpá-lo é seguro. Se foi atribuição,
# o processo tem dono e limpar desatribui trabalho real.
#
# Porque é que o histórico ganha à assinatura quando existe: a
# assinatura é uma inferência sobre qual escritor passou por ali; o
# histórico é o registo do que aconteceu.
# ────────────────────────────────────────────────────────────────────

ORIGEM_DESATRIBUICAO = "desatribuicao"
ORIGEM_ATRIBUICAO_LEGADA = "atribuicao_legada"
ORIGEM_INDETERMINADA = "indeterminada"

#: Assinaturas que decidem sozinhas, por papel. Conjunto EXACTO dos
#: campos singulares preenchidos com a lista vazia.
_ASSINATURAS: dict[str, tuple[tuple[frozenset[str], str], ...]] = {
    "consultor": (
        (frozenset({"consultor_id", "consultant_id"}), ORIGEM_DESATRIBUICAO),
        (frozenset({"consultant_id"}), ORIGEM_ATRIBUICAO_LEGADA),
    ),
    # O mediador não tem assinatura que decida: `build_clear_mediador_fields`
    # e a dupla auto-atribuição antiga deixavam ambos `{mediador_id}`.
    "mediador": (),
}

#: Campo do histórico que cada papel usa nas remoções manuais, mais o
#: `"assignment"` genérico com que a dupla auto-atribuição regista.
_CAMPOS_DE_HISTORICO = {
    "consultor": ("assigned_consultor_ids", "assignment"),
    "mediador": ("assigned_mediador_ids", "assignment"),
}

#: Palavras com que uma entrada genérica (`field == "assignment"`) se
#: atribui a um papel. Comparadas sem acentos e em minúsculas.
_PALAVRAS_DO_PAPEL = {
    "consultor": ("consultor",),
    "mediador": ("intermediario", "mediador"),
}


def _sem_acentos(texto: str) -> str:
    import unicodedata

    normalizado = unicodedata.normalize("NFD", texto or "")
    return "".join(c for c in normalizado if unicodedata.category(c) != "Mn").lower()


def _campos_ambiguos(processo: dict, papel: str) -> frozenset[str]:
    return frozenset(
        d.campo
        for d in desfasamentos_do_processo(processo)
        if d.papel == papel and d.veredicto == VEREDICTO_AMBIGUO
    )


def _origem_pelo_historico(historico: Iterable[dict], papel: str) -> Optional[str]:
    """O ÚLTIMO acontecimento de atribuição deste papel, se existir.

    Devolve `None` quando o histórico não fala deste papel — que é
    diferente de "não sei decidir": quem chama distingue.
    """
    campos = _CAMPOS_DE_HISTORICO[papel]
    palavras = _PALAVRAS_DO_PAPEL[papel]
    veredicto: Optional[str] = None

    for entrada in historico or []:
        campo = (entrada or {}).get("field") or ""
        if campo not in campos:
            continue

        if campo == "assignment":
            # Entrada genérica (dupla auto-atribuição): só conta se
            # nomear este papel. Um registo que só fala do consultor não
            # diz nada sobre o mediador.
            texto = _sem_acentos(
                f"{entrada.get('action') or ''} {entrada.get('new_value') or ''}"
            )
            if not any(p in texto for p in palavras):
                continue

        novo = entrada.get("new_value")
        veredicto = (
            ORIGEM_DESATRIBUICAO if not novo else ORIGEM_ATRIBUICAO_LEGADA
        )

    return veredicto


def origem_do_ambiguo(
    processo: dict,
    papel: str,
    *,
    historico: Optional[Iterable[dict]] = None,
) -> str:
    """De onde veio o `ambiguo` deste papel — e portanto o que fazer.

    ``desatribuicao``      resíduo de uma remoção: limpar é seguro.
    ``atribuicao_legada``  o processo TEM dono: limpar desatribui
                           trabalho real; o que falta é a lista.
    ``indeterminada``      sem prova suficiente. Fica para decisão
                           humana — nunca para o automatismo.

    O histórico, quando fala deste papel, ganha à assinatura: é registo,
    não inferência. `historico` tem de vir ORDENADO do mais antigo para
    o mais recente.
    """
    campos = _campos_ambiguos(processo, papel)
    if not campos:
        return ORIGEM_INDETERMINADA

    if historico is not None:
        pelo_registo = _origem_pelo_historico(historico, papel)
        if pelo_registo:
            return pelo_registo

    for assinatura, origem in _ASSINATURAS.get(papel, ()):
        if campos == assinatura:
            return origem

    return ORIGEM_INDETERMINADA


def reposicao_de_listas_do_processo(
    processo: dict,
    *,
    historicos_por_papel: Optional[dict[str, Iterable[dict]]] = None,
) -> dict[str, Any]:
    """O `$set` que repõe a LISTA a partir do singular — o caminho oposto.

    Para um `ambiguo` de origem `atribuicao_legada` a correcção certa
    **não é limpar**: o processo tem dono, e limpá-lo deixa-o sem
    ninguém. O que falta é a lista que o escritor antigo nunca escreveu.

    Nota sobre o risco: quem está no singular JÁ recebe os alertas e JÁ
    vê o processo em "Os Meus Processos" (ambos os leitores consultam os
    campos singulares). Repor a lista não alarga acesso nenhum — põe o
    documento de acordo com o comportamento que já está em produção, e
    tira o cartão de Atribuição do estado em branco.

    Não devolve nomes: quem os sabe resolver é o script, contra
    `db.users`.
    """
    correccao: dict[str, Any] = {}
    historicos = historicos_por_papel or {}

    for papel, campo_da_lista, campos_singulares in PAPEIS:
        if _lista_de_ids(processo, campo_da_lista):
            continue
        origem = origem_do_ambiguo(
            processo, papel, historico=historicos.get(papel)
        )
        if origem != ORIGEM_ATRIBUICAO_LEGADA:
            continue
        for campo in campos_singulares:
            valor = _texto((processo or {}).get(campo))
            if valor:
                correccao[campo_da_lista] = [valor]
                break

    return correccao


def resumir_ambiguos(
    processos: Iterable[dict],
    *,
    historicos_por_processo: Optional[dict[str, dict[str, Iterable[dict]]]] = None,
) -> dict[str, Any]:
    """Contagem dos ambíguos POR ORIGEM — é isto que decide o `--corrigir`."""
    historicos = historicos_por_processo or {}
    por_origem: dict[str, int] = {}
    processos_por_origem: dict[str, list[str]] = {}

    for processo in processos:
        pid = str((processo or {}).get("id") or "")
        do_processo = historicos.get(pid) or {}
        for papel, _campo_da_lista, _campos in PAPEIS:
            if not _campos_ambiguos(processo, papel):
                continue
            origem = origem_do_ambiguo(
                processo, papel, historico=do_processo.get(papel)
            )
            chave = f"{papel}:{origem}"
            por_origem[chave] = por_origem.get(chave, 0) + 1
            processos_por_origem.setdefault(origem, []).append(pid)

    return {
        "por_papel_e_origem": por_origem,
        "processos_por_origem": processos_por_origem,
    }
