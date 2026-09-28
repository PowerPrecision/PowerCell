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
) -> dict[str, Any]:
    """O `$set` que põe os singulares de acordo com a lista.

    Vazio quando não há nada seguro a corrigir. Os `ambiguo` só entram por
    ordem explícita (`incluir_ambiguos=True`) — ver o cabeçalho do módulo.
    """
    correccao: dict[str, Any] = {}
    for d in desfasamentos_do_processo(processo):
        if d.e_seguro_corrigir or incluir_ambiguos:
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
