"""
====================================================================
RETRATO DO RELÓGIO DE FASES — o que a base de dados sabe sobre o tempo
====================================================================
Refinamento Analítico e SLAs (Dashboard), Passo Zero.
Análise PURA: não toca na base de dados nem no relógio do sistema.
Quem lê é `scripts/medir_relogio_de_fases.py`.

O PROBLEMA QUE ISTO MEDE
  Nenhum processo sabe quando entrou na fase em que está. Há dois
  instantes gravados — `created_at` e `updated_at` — e o segundo muda
  com QUALQUER escrita: um comentário, uma nota de voz, um documento.

  O `stats_branches` calcula hoje o "tempo médio de fecho" como
  `updated_at - created_at`. Isso não é o tempo de fecho; é o tempo
  entre a criação e o último toque em qualquer campo. Um documento
  carregado hoje num processo escriturado há um ano acrescenta 365 dias
  ao tempo médio desse balcão.

  O carimbo de transição (`fase_desde`) resolve isto para o futuro, mas
  só a partir do dia em que entrar. Para os processos que JÁ existem o
  melhor aproximado é o `updated_at` — e este retrato existe para dizer
  QUÃO MAU é esse aproximado, processo a processo, antes de o semearmos
  como estimativa.

AS CINCO PERGUNTAS
  1. Quantos processos há por macro-fase, resolvidos pelo MOTOR (e não
     pelo valor cru), para o retrato contar os 205 processos de alias e
     as 12 gralhas na coluna certa.
  2. Que cobertura tem o relógio hoje (`fase_desde` presente, ausente,
     estimado) — corre-se outra vez depois do backfill e a resposta muda.
  3. Qual a distribuição de permanência que a estimativa produziria, nas
     MESMAS bandas do `$bucket` que o dashboard vai usar. Se as bandas
     fossem diferentes, o retrato e o gráfico contavam histórias
     distintas sobre os mesmos dados.
  4. Onde é que o `updated_at` MENTE como aproximado, e em que sentido:
     `nunca_tocado` sobrestima a permanência (a estimativa cai na data de
     criação), `tocado_apos_fecho` subestima-a.
  5. Que carimbo de rede existe — porque o isolamento que entra a seguir
     muda o que a Direção vê, e isto diz por quanto.

PORQUE É QUE A RESOLUÇÃO DA MACRO-FASE VEM DO RESOLVEDOR
  Seria mais rápido agrupar por `status` numa agregação e mapear os nomes
  em Python. Mas o `resolver_nome` já sabe tratar `cpcv`, `escriturado` e
  `"Concluidos "`, e reimplementar essa regra aqui dava-nos duas verdades
  sobre os mesmos 217 processos — a do quadro e a do relatório. É o erro
  que o Épico 10 fechou; não volta a entrar por um script de medição.
====================================================================
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from services.workflow_phases import (
    FASE_DESCONHECIDA,
    MACRO_FASES_VALIDAS,
    macro_da_fase,
    resolver_muitos,
)

logger = logging.getLogger(__name__)

# Campo que o carimbo vai escrever. Nomeado aqui porque o retrato precisa
# de saber se já existe, e a medição antecede a implementação.
CAMPO_FASE_DESDE = "fase_desde"
CAMPO_MACRO_DESDE = "macro_fase_desde"
CAMPO_ESTIMADO = "fase_desde_estimado"
CAMPO_TEMPOS = "tempos_macro"

# Bandas de permanência em dias. São as MESMAS que o `$bucket` do
# endpoint de SLAs vai usar — ver o docstring.
LIMITES_DAS_BANDAS: tuple[int, ...] = (8, 16, 31, 61)
ETIQUETAS_DAS_BANDAS: tuple[str, ...] = (
    "0-7", "8-15", "16-30", "31-60", "61+",
)

# Um processo terminal tocado nos últimos `_DIAS_RECENTES` dias, tendo
# sido criado há mais de `_DIAS_MATURO`, é um candidato a "tocado depois
# de fechar": a estimativa dir-lhe-ia que entrou na fase esta semana.
_DIAS_RECENTES = 30
_DIAS_MATUROS = 90

_MACROS_TERMINAIS = ("concluido", "perdido")


def instante(valor: Any) -> Optional[datetime]:
    """Converte para `datetime` com fuso, ou devolve `None`.

    Tolerante de propósito: a colecção tem ISO com `Z`, ISO sem fuso e
    `datetime` nativo do Mongo, tudo no mesmo campo. Um valor que não se
    consegue ler conta como AUSENTE — nunca como agora, que era o erro
    fácil e inflacionava a cobertura do relógio.
    """
    # ATALHO, não guarda de correcção: `fromisoformat("")` levanta de
    # qualquer maneira e o ramo de excepção devolveria `None` igualmente.
    # Está aqui porque antes do backfill a esmagadora maioria das linhas
    # cai neste caso, e levantar uma excepção por cada uma delas custa.
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    try:
        texto = str(valor).strip().replace("Z", "+00:00")
        lido = datetime.fromisoformat(texto)
    except (TypeError, ValueError):
        return None
    return lido if lido.tzinfo else lido.replace(tzinfo=timezone.utc)


def dias_entre(inicio: Optional[datetime], fim: Optional[datetime]) -> Optional[float]:
    """Dias decorridos, ou `None` quando falta um dos instantes."""
    if inicio is None or fim is None:
        return None
    return (fim - inicio).total_seconds() / 86400.0


def banda_de_dias(dias: Optional[float]) -> Optional[str]:
    """Etiqueta da banda de permanência. Dias negativos não têm banda."""
    if dias is None or dias < 0:
        return None
    for indice, limite in enumerate(LIMITES_DAS_BANDAS):
        if dias < limite:
            return ETIQUETAS_DAS_BANDAS[indice]
    return ETIQUETAS_DAS_BANDAS[-1]


def mediana(valores: list[float]) -> Optional[float]:
    """Mediana simples. Devolve `None` para amostra vazia.

    Mediana e não só média porque num gargalo a média mente sempre no
    mesmo sentido: um processo esquecido há 400 dias arrasta-a e esconde
    que a maioria passa em dias.
    """
    if not valores:
        return None
    ordenados = sorted(valores)
    meio = len(ordenados) // 2
    if len(ordenados) % 2:
        return ordenados[meio]
    return (ordenados[meio - 1] + ordenados[meio]) / 2


def _bandas_vazias() -> dict[str, int]:
    return {etiqueta: 0 for etiqueta in ETIQUETAS_DAS_BANDAS}


@dataclass
class Permanencia:
    """Distribuição de permanência estimada de uma macro-fase."""

    processos: int = 0
    amostra: int = 0            # quantos deram um número utilizável
    media_dias: Optional[float] = None
    mediana_dias: Optional[float] = None
    maximo_dias: Optional[float] = None
    bandas: dict[str, int] = field(default_factory=_bandas_vazias)


@dataclass(frozen=True)
class Retrato:
    """O que a base de dados sabe hoje sobre o tempo dos processos."""

    total: int
    sem_status: int
    por_macro: dict[str, int]
    desconhecidos_por_valor: dict[str, int]
    cobertura_do_relogio: dict[str, int]
    permanencia_por_macro: dict[str, Permanencia]
    proxy_suspeito: dict[str, int]
    datas_invalidas: dict[str, int]
    carimbo_de_rede: dict[str, int]
    redes: dict[str, int]


def _macro_por_valor(valores: Iterable[Optional[str]], fases: list[dict]) -> dict[str, Optional[str]]:
    """``valor cru de status -> macro-fase``, pelo motor e pelo resolvedor.

    Duas passagens numa: o `resolver_muitos` diz qual a fase real de cada
    valor gravado (exacto, gralha ou alias) e o `macro_da_fase` diz a que
    grupo essa fase pertence. Um valor que o motor não conhece fica em
    `None` e vai para `desconhecidos_por_valor` — visível, nunca somado a
    um grupo onde não está.
    """
    por_nome = {
        f.get("name"): f for f in fases
        if isinstance(f, dict) and f.get("name")
    }
    resolucoes = resolver_muitos(valores, fases)

    mapa: dict[str, Optional[str]] = {}
    for valor, resolucao in resolucoes.items():
        fase = por_nome.get(resolucao.fase) if resolucao.resolvida else None
        mapa[valor] = macro_da_fase(fase) if fase else None
    return mapa


def analisar(
    linhas: Iterable[dict],
    fases: Iterable[dict],
    *,
    agora: datetime,
) -> Retrato:
    """Constrói o retrato a partir das linhas cruas dos processos.

    `agora` é INJECTADO, não lido do sistema: uma medição que dependa do
    relógio da máquina não se consegue afirmar num teste, e um retrato
    que não se consegue testar é uma opinião.

    Cada linha traz o que a projecção do script leu:
    `status`, `created_at`, `updated_at`, `fase_desde`, `macro_fase_desde`,
    `fase_desde_estimado`, `tempos_macro`, `network_id`, `company_id`.
    """
    fases = [f for f in fases if isinstance(f, dict)]
    linhas = list(linhas)

    valores = [linha.get("status") for linha in linhas]
    macro_por_valor = _macro_por_valor(valores, fases)

    por_macro: dict[str, int] = {m: 0 for m in MACRO_FASES_VALIDAS}
    por_macro[FASE_DESCONHECIDA] = 0
    desconhecidos_por_valor: dict[str, int] = {}
    redes: dict[str, int] = {}

    cobertura = {
        "com_fase_desde": 0,
        "sem_fase_desde": 0,
        "estimados": 0,
        "com_macro_fase_desde": 0,
        "com_tempos_macro": 0,
    }
    suspeito = {
        "nunca_tocado": 0,
        "tocado_apos_fecho": 0,
        "sem_updated_at": 0,
    }
    invalidas = {
        "created_at_ausente": 0,
        "updated_at_antes_de_created_at": 0,
    }
    carimbo = {
        "com_rede": 0,
        "com_empresa_sem_rede": 0,
        "sem_marca_nenhuma": 0,
    }

    # Amostras de permanência estimada, por macro-fase.
    amostras: dict[str, list[float]] = {m: [] for m in por_macro}
    bandas: dict[str, dict[str, int]] = {m: _bandas_vazias() for m in por_macro}

    sem_status = 0

    for linha in linhas:
        bruto = linha.get("status") or ""
        if not bruto:
            sem_status += 1

        macro = macro_por_valor.get(bruto) or FASE_DESCONHECIDA
        por_macro[macro] = por_macro.get(macro, 0) + 1
        if macro == FASE_DESCONHECIDA and bruto:
            desconhecidos_por_valor[bruto] = desconhecidos_por_valor.get(bruto, 0) + 1

        # ── Cobertura do relógio ──
        entrada = instante(linha.get(CAMPO_FASE_DESDE))
        if entrada is not None:
            cobertura["com_fase_desde"] += 1
        else:
            cobertura["sem_fase_desde"] += 1
        if linha.get(CAMPO_ESTIMADO) is True:
            cobertura["estimados"] += 1
        if instante(linha.get(CAMPO_MACRO_DESDE)) is not None:
            cobertura["com_macro_fase_desde"] += 1
        if linha.get(CAMPO_TEMPOS):
            cobertura["com_tempos_macro"] += 1

        criado = instante(linha.get("created_at"))
        tocado = instante(linha.get("updated_at"))

        if criado is None:
            invalidas["created_at_ausente"] += 1
        if tocado is None:
            suspeito["sem_updated_at"] += 1
        elif criado is not None and tocado < criado:
            invalidas["updated_at_antes_de_created_at"] += 1

        # ── Qualidade do aproximado ──
        # `updated_at == created_at` significa que ninguém escreveu no
        # processo depois de o criar: a estimativa cai na data de criação
        # e a permanência aparece como a idade TOTAL do processo.
        # `==` e não `<=`: um `updated_at` ANTERIOR ao `created_at` é dado
        # corrompido, já contado em `datas_invalidas`. Somá-lo aqui
        # também inflacionava o número que decide o backfill.
        if tocado is not None and criado is not None and tocado == criado:
            suspeito["nunca_tocado"] += 1
        if (
            macro in _MACROS_TERMINAIS
            and tocado is not None
            and criado is not None
            and (dias_entre(tocado, agora) or 0) <= _DIAS_RECENTES
            and (dias_entre(criado, agora) or 0) >= _DIAS_MATUROS
        ):
            suspeito["tocado_apos_fecho"] += 1

        # ── Permanência que a estimativa produziria ──
        # Preferimos o carimbo real quando já existe; só na sua ausência
        # é que a medição usa o aproximado. Depois do backfill este ramo
        # passa a ser o minoritário, e é isso que se quer ver.
        referencia = entrada or tocado
        dias = dias_entre(referencia, agora)
        if dias is not None and dias >= 0:
            amostras[macro].append(dias)
            faixa = banda_de_dias(dias)
            if faixa:
                bandas[macro][faixa] += 1

        # ── Carimbo de rede (o isolamento que entra a seguir) ──
        rede = str(linha.get("network_id") or "").strip()
        empresa = any(
            str(linha.get(campo) or "").strip()
            for campo in ("company_id", "company", "company_name")
        )
        if rede:
            carimbo["com_rede"] += 1
            redes[rede] = redes.get(rede, 0) + 1
        elif empresa:
            carimbo["com_empresa_sem_rede"] += 1
        else:
            carimbo["sem_marca_nenhuma"] += 1

    permanencia = {}
    for macro, valores_macro in amostras.items():
        permanencia[macro] = Permanencia(
            processos=por_macro.get(macro, 0),
            amostra=len(valores_macro),
            media_dias=(
                round(sum(valores_macro) / len(valores_macro), 1)
                if valores_macro else None
            ),
            mediana_dias=(
                round(mediana(valores_macro), 1) if valores_macro else None
            ),
            maximo_dias=round(max(valores_macro), 1) if valores_macro else None,
            bandas=bandas[macro],
        )

    return Retrato(
        total=len(linhas),
        sem_status=sem_status,
        por_macro=por_macro,
        desconhecidos_por_valor=dict(
            sorted(desconhecidos_por_valor.items(), key=lambda kv: -kv[1])
        ),
        cobertura_do_relogio=cobertura,
        permanencia_por_macro=permanencia,
        proxy_suspeito=suspeito,
        datas_invalidas=invalidas,
        carimbo_de_rede=carimbo,
        redes=dict(sorted(redes.items(), key=lambda kv: -kv[1])),
    )


# ====================================================================
# APRESENTAÇÃO
# ====================================================================

def _numero(valor: Optional[float]) -> str:
    return "—" if valor is None else f"{valor:.1f}"


def formatar_relatorio(retrato: Retrato) -> str:
    """Relatório legível para o terminal do bastion host."""
    linhas: list[str] = []
    ad = linhas.append

    ad("")
    ad("=" * 68)
    ad("RETRATO DO RELÓGIO DE FASES")
    ad("=" * 68)
    ad(f"Processos analisados: {retrato.total}")
    if retrato.sem_status:
        ad(f"  sem `status` (leads do formulário público): {retrato.sem_status}")

    ad("")
    ad("── COBERTURA DO RELÓGIO " + "─" * 44)
    cob = retrato.cobertura_do_relogio
    ad(f"  com `fase_desde`         : {cob['com_fase_desde']}")
    ad(f"  SEM `fase_desde`         : {cob['sem_fase_desde']}")
    ad(f"  marcados como estimados  : {cob['estimados']}")
    ad(f"  com `macro_fase_desde`   : {cob['com_macro_fase_desde']}")
    ad(f"  com `tempos_macro`       : {cob['com_tempos_macro']}")
    if cob["com_fase_desde"] == 0:
        ad("  → Nenhum processo tem carimbo. É o esperado ANTES do backfill:")
        ad("    tudo o que se segue é ESTIMATIVA sobre `updated_at`.")

    ad("")
    ad("── PERMANÊNCIA POR MACRO-FASE " + "─" * 38)
    ad(f"  {'macro':<18}{'proc':>6}{'amostra':>9}{'média':>8}{'mediana':>9}{'máx':>8}")
    for macro, perm in retrato.permanencia_por_macro.items():
        if not perm.processos:
            continue
        ad(
            f"  {macro:<18}{perm.processos:>6}{perm.amostra:>9}"
            f"{_numero(perm.media_dias):>8}{_numero(perm.mediana_dias):>9}"
            f"{_numero(perm.maximo_dias):>8}"
        )
    ad("  (dias; a média e a mediana longe uma da outra são o gargalo)")

    ad("")
    ad("── DISTRIBUIÇÃO EM BANDAS " + "─" * 42)
    cabecalho = "".join(f"{etq:>9}" for etq in ETIQUETAS_DAS_BANDAS)
    ad(f"  {'macro':<18}{cabecalho}")
    for macro, perm in retrato.permanencia_por_macro.items():
        if not perm.amostra:
            continue
        corpo = "".join(f"{perm.bandas[etq]:>9}" for etq in ETIQUETAS_DAS_BANDAS)
        ad(f"  {macro:<18}{corpo}")

    ad("")
    ad("── QUALIDADE DO APROXIMADO `updated_at` " + "─" * 28)
    sus = retrato.proxy_suspeito
    ad(f"  nunca tocado (estimativa = data de criação): {sus['nunca_tocado']}")
    ad("    → SOBRESTIMA a permanência: conta a idade toda do processo.")
    ad(f"  terminal tocado há <= {_DIAS_RECENTES}d, criado há >= {_DIAS_MATUROS}d: "
       f"{sus['tocado_apos_fecho']}")
    ad("    → SUBESTIMA a permanência: parece ter entrado na fase esta semana.")
    ad(f"  sem `updated_at`: {sus['sem_updated_at']}")

    inv = retrato.datas_invalidas
    if any(inv.values()):
        ad("")
        ad("── DATAS INVÁLIDAS " + "─" * 49)
        ad(f"  `created_at` ausente              : {inv['created_at_ausente']}")
        ad(f"  `updated_at` anterior a `created_at`: "
           f"{inv['updated_at_antes_de_created_at']}")

    ad("")
    ad("── MACRO-FASES " + "─" * 53)
    for macro, quantos in retrato.por_macro.items():
        if quantos:
            ad(f"  {macro:<20} {quantos}")
    if retrato.desconhecidos_por_valor:
        ad("  valores que o motor não conhece:")
        for valor, quantos in retrato.desconhecidos_por_valor.items():
            ad(f"    {valor!r:<28} {quantos}")

    ad("")
    ad("── CARIMBO DE REDE (o isolamento que entra a seguir) " + "─" * 15)
    car = retrato.carimbo_de_rede
    ad(f"  com `network_id`                 : {car['com_rede']}")
    ad(f"  com empresa mas SEM rede         : {car['com_empresa_sem_rede']}")
    ad(f"  sem marca nenhuma (pilha antiga) : {car['sem_marca_nenhuma']}")
    if retrato.redes:
        for rede, quantos in retrato.redes.items():
            ad(f"    {rede:<28} {quantos}")
    if car["sem_marca_nenhuma"]:
        ad("  → A pilha sem marca fica visível a quem estiver na rede de")
        ad("    omissão (`TENANT_DEFAULT_NETWORK_ID`). Este número é quanto")
        ad("    do BI depende dessa variável estar bem definida em produção.")

    ad("")
    ad("=" * 68)
    return "\n".join(linhas)


def para_json(retrato: Retrato) -> dict:
    """Retrato serializável — é este que volta do bastion host."""
    return {
        "total": retrato.total,
        "sem_status": retrato.sem_status,
        "por_macro": retrato.por_macro,
        "desconhecidos_por_valor": retrato.desconhecidos_por_valor,
        "cobertura_do_relogio": retrato.cobertura_do_relogio,
        "permanencia_por_macro": {
            macro: {
                "processos": perm.processos,
                "amostra": perm.amostra,
                "media_dias": perm.media_dias,
                "mediana_dias": perm.mediana_dias,
                "maximo_dias": perm.maximo_dias,
                "bandas": perm.bandas,
            }
            for macro, perm in retrato.permanencia_por_macro.items()
        },
        "proxy_suspeito": retrato.proxy_suspeito,
        "datas_invalidas": retrato.datas_invalidas,
        "carimbo_de_rede": retrato.carimbo_de_rede,
        "redes": retrato.redes,
        "bandas_usadas": list(ETIQUETAS_DAS_BANDAS),
        "macro_fases_validas": list(MACRO_FASES_VALIDAS),
    }
