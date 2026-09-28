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
    PAPEIS_COMO_CONSULTOR,
    PAPEIS_COMO_MEDIADOR,
    PAPEL_DA_INDEXACAO,
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
    incluir_orfaos: bool = False,
    incluir_indexacao: bool = False,
    historicos_por_papel: Optional[dict[str, Iterable[dict]]] = None,
    utilizadores: Optional[dict[str, Optional[dict]]] = None,
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

    `incluir_orfaos` é uma ordem SEPARADA, para uma prova separada: o
    utilizador nomeado não existe. Bandeiras distintas para provas
    distintas — quem autoriza limpar resíduo provado por registo não
    autorizou, com isso, limpar por ausência de utilizador.

    `incluir_indexacao` é a terceira ordem, pela mesma razão: o utilizador
    existe e está activo, mas tem o perfil `indexacao`, que nunca é um
    atribuído. Limpar não lhe tira acesso nenhum — o Índice vê os
    processos pelo carimbo próprio — mas continua a ser uma prova
    diferente das outras duas, logo uma bandeira diferente.
    """
    correccao: dict[str, Any] = {}
    origens: dict[str, str] = {}
    historicos = historicos_por_papel or {}

    autorizadas = set()
    if incluir_ambiguos:
        autorizadas.add(ORIGEM_DESATRIBUICAO)
    if incluir_orfaos:
        autorizadas.add(ORIGEM_ORFAO)
    if incluir_indexacao:
        autorizadas.add(ORIGEM_INDEXACAO_NAS_LISTAS)

    for d in desfasamentos_do_processo(processo):
        if d.e_seguro_corrigir:
            correccao[d.campo] = d.valor_esperado
            continue
        if not autorizadas:
            continue
        if d.papel not in origens:
            origens[d.papel] = origem_do_ambiguo(
                processo,
                d.papel,
                historico=historicos.get(d.papel),
                utilizadores=utilizadores,
            )
        if origens[d.papel] in autorizadas:
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

# ── A TERCEIRA FONTE DE PROVA: QUEM LÁ ESTÁ (Set 2026) ──────────────
#
# Os 199 indeterminados de produção não eram um bloco. Resolvidos os ids
# contra `db.users`, partiram-se em três grupos com respostas OPOSTAS:
#
#   153 papéis   o utilizador **não existe**
#    34 papéis   utilizador activo com o papel CERTO para o campo
#    12 papéis   utilizador activo com papel `indexacao`
#
# Nem a assinatura nem o histórico os distinguem — só saber quem lá
# está. E a consequência é o fecho de todo este módulo:
#
#   **Limpar um órfão não desatribui ninguém.** O risco contra o qual
#   tudo isto foi construído — "limpar deixa o processo sem dono" — não
#   se materializa quando o dono não existe: o processo JÁ está sem dono
#   e o campo está a mentir. Alguém a quem o processo não aparece em
#   lado nenhum não perde nada quando o campo desaparece.
#
# Por isso o utilizador ganha ao registo: um processo atribuído a alguém
# que já não existe não tem dono, diga o histórico o que disser.

#: O utilizador nomeado pelo campo não existe. Limpar é seguro.
ORIGEM_ORFAO = "orfao"

#: O utilizador existe mas não pode ocupar aquele campo — papel
#: incompatível ou conta inactiva. Nenhum automatismo lhe toca: repor a
#: lista cimentaria um estado que as regras do produto não admitem, e
#: limpar pode ser cedo demais se a conta for reactivada.
ORIGEM_ATRIBUIDO_INVALIDO = "atribuido_invalido"

# ── O ÚLTIMO RESÍDUO: A INDEXAÇÃO NAS LISTAS (Set 2026) ─────────────
#
# Os 12 que sobreviveram à limpeza de produção eram todos a MESMA conta
# (`2285198b`, "654", perfil `indexacao`) em `assigned_consultor_id`.
# Estavam em `atribuido_invalido`, que é intocável — e bem, enquanto essa
# origem juntar DUAS provas diferentes debaixo do mesmo nome:
#
#   conta inactiva      um consultor a sério que saiu. O campo regista uma
#                       atribuição REAL; limpá-la apaga-a, e a conta pode
#                       ser reactivada amanhã.
#   papel `indexacao`   nunca foi uma atribuição. O Índice tem carimbo
#                       próprio e as regras do produto não admitem que
#                       ocupe um campo de consultor ou de mediador.
#
# São respostas opostas, logo não podem partilhar bandeira — é a regra
# que o `--limpar-orfaos` já tinha estabelecido: bandeiras distintas para
# provas distintas.
#
# E limpar este caso é seguro pela MESMA razão que o órfão: não desatribui
# ninguém. Não porque a pessoa não exista — existe e está activa — mas
# porque não é por este campo que ela vê o processo. `process_list_filters`
# dá ao perfil `indexacao` `assigned_indexacao_id` / `created_by` /
# `status: fila_espera`, e **nunca** `assigned_consultor_id`. O campo não
# lhe dá acesso nenhum: só mente ao cartão de Atribuição e aos alertas.
#
# O que fica depois de limpar é o processo a aparecer "Por Atribuir", que
# é o estado verdadeiro e o que aciona a triagem na UI. Não se escreve
# `assigned_indexacao_id` em troca: quem indexou o processo é um facto que
# este campo não prova, e inventá-lo — ou pior, escrever por cima de um
# carimbo legítimo — seria trocar uma mentira por outra.
ORIGEM_INDEXACAO_NAS_LISTAS = "indexacao_nas_listas"

#: Que papéis podem ocupar o campo de cada função. Deriva das constantes
#: de produção — uma lista à mão aqui divergiria dos escritores.
_PAPEIS_ACEITES = {
    "consultor": frozenset(PAPEIS_COMO_CONSULTOR),
    "mediador": frozenset(PAPEIS_COMO_MEDIADOR),
}

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


def _id_no_singular(processo: dict, papel: str, campos: frozenset[str]) -> Optional[str]:
    """O id que o campo ambíguo nomeia. Um papel tem UM dono."""
    for _p, _lista, campos_singulares in PAPEIS:
        if _p != papel:
            continue
        for campo in campos_singulares:
            if campo not in campos:
                continue
            valor = _texto((processo or {}).get(campo))
            if valor:
                return valor
    return None


def _origem_pelo_utilizador(
    processo: dict,
    papel: str,
    campos: frozenset[str],
    utilizadores: dict[str, Optional[dict]],
) -> Optional[str]:
    """Quem está no campo — a prova mais forte que existe.

    Devolve `None` quando NÃO se perguntou por este id. "Não perguntei"
    é diferente de "perguntei e não existe": sem essa distinção, um mapa
    incompleto (uma consulta que falhou, um lote por resolver) apagaria
    atribuições boas em silêncio.
    """
    uid = _id_no_singular(processo, papel, campos)
    if not uid or uid not in utilizadores:
        return None

    doc = utilizadores[uid]
    if doc is None:
        return ORIGEM_ORFAO

    papel_do_utilizador = str(doc.get("role") or "")

    # A INDEXAÇÃO antes do estado da conta, de propósito: "este perfil não
    # ocupa este campo" é uma regra de produto e vale com a conta activa ou
    # inactiva. Pela ordem inversa, um indexador desactivado caía em
    # `conta inactiva` e ficava à espera de uma reactivação que não muda
    # nada — continuaria a não poder ser consultor.
    if papel_do_utilizador == PAPEL_DA_INDEXACAO:
        return ORIGEM_INDEXACAO_NAS_LISTAS

    if not doc.get("is_active", True):
        return ORIGEM_ATRIBUIDO_INVALIDO

    if papel_do_utilizador not in _PAPEIS_ACEITES.get(papel, frozenset()):
        return ORIGEM_ATRIBUIDO_INVALIDO

    return ORIGEM_ATRIBUICAO_LEGADA


def origem_do_ambiguo(
    processo: dict,
    papel: str,
    *,
    historico: Optional[Iterable[dict]] = None,
    utilizadores: Optional[dict[str, Optional[dict]]] = None,
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

    # O UTILIZADOR primeiro: ganha ao registo porque um processo
    # atribuído a alguém que já não existe não tem dono, diga o
    # histórico o que disser.
    if utilizadores is not None:
        pelo_utilizador = _origem_pelo_utilizador(
            processo, papel, campos, utilizadores
        )
        if pelo_utilizador:
            return pelo_utilizador

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
    utilizadores: Optional[dict[str, Optional[dict]]] = None,
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
            processo,
            papel,
            historico=historicos.get(papel),
            utilizadores=utilizadores,
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
    utilizadores: Optional[dict[str, Optional[dict]]] = None,
) -> dict[str, Any]:
    """Contagem dos ambíguos POR ORIGEM — é isto que decide o `--corrigir`.

    Três leituras, e não se confundem:

    ``por_papel_e_origem``   quantos PAPÉIS (processo × consultor/mediador).
                             É por papel que se decide o que fazer, logo é
                             este o número que conta para o trabalho.
    ``processos_por_origem`` que PROCESSOS, sem repetições. Um processo com
                             os dois papéis ambíguos aparecia aqui duas
                             vezes e o relatório anunciava "N casos" sobre
                             uma lista que não era nem de processos nem de
                             papéis.
    ``responsaveis_por_origem``
                             QUEM aparece nos singulares, e quantas vezes.
                             É a pergunta que transforma "199 processos
                             indecidíveis" em "duas pessoas a confirmar":
                             os mesmos dois ou três ids repetidos não são
                             actividade orgânica, são uma escrita em massa.
    """
    historicos = historicos_por_processo or {}
    por_origem: dict[str, int] = {}
    processos_por_origem: dict[str, list[str]] = {}
    vistos: dict[str, set[str]] = {}
    responsaveis: dict[str, dict[str, int]] = {}

    for processo in processos:
        pid = str((processo or {}).get("id") or "")
        do_processo = historicos.get(pid) or {}
        for papel, _campo_da_lista, campos_singulares in PAPEIS:
            ambiguos = _campos_ambiguos(processo, papel)
            if not ambiguos:
                continue
            origem = origem_do_ambiguo(
                processo,
                papel,
                historico=do_processo.get(papel),
                utilizadores=utilizadores,
            )
            chave = f"{papel}:{origem}"
            por_origem[chave] = por_origem.get(chave, 0) + 1

            # A lista é de PROCESSOS: sem repetir quem tem os dois papéis.
            ja = vistos.setdefault(origem, set())
            if pid not in ja:
                ja.add(pid)
                processos_por_origem.setdefault(origem, []).append(pid)

            # Quem está nos singulares. Um papel contribui com UM id — o
            # mesmo valor repetido em dois campos do mesmo papel é a mesma
            # pessoa, não duas.
            for campo in campos_singulares:
                if campo not in ambiguos:
                    continue
                valor = _texto((processo or {}).get(campo))
                if not valor:
                    continue
                contagem = responsaveis.setdefault(origem, {})
                contagem[valor] = contagem.get(valor, 0) + 1
                break

    return {
        "por_papel_e_origem": por_origem,
        "processos_por_origem": {
            origem: sorted(ids) for origem, ids in processos_por_origem.items()
        },
        "responsaveis_por_origem": responsaveis,
    }
