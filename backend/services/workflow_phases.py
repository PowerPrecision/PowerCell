"""O motor de workflow como ponto ÚNICO de consulta de fases.

ÉPICO 10, PARTE 3 — O RESOLVEDOR

O PROBLEMA QUE ISTO FECHA
  O raio-x encontrou cinco vocabulários de fases no código e dois deles
  não existiam no motor. O `workflow_lookup` já era o ponto único das
  FLAGS de propósito; faltava o ponto único dos NOMES.

  Sem ele, cada sítio que precisa de saber "que fases são terminais" ou
  "que fase é esta que está gravada" escreve a sua própria lista — e as
  listas envelhecem enquanto o motor muda.

A REGRA DO ALIAS
  Um alias só vence quando o motor NÃO conhece o nome gravado E conhece o
  destino. E com mais do que um destino possível não se escolhe. Basta o
  admin criar uma fase com um nome antigo para a tradução passar a
  reescrever processos correctos — foi por isso que a timeline do CRM
  mentia (Lote 5, P0).

A ORDEM DA RESOLUÇÃO, E PORQUÊ
  1. `exacto`       — o nome gravado É uma fase. Nada a fazer.
  2. `gralha`       — normaliza (maiúsculas, espaços, hífen) para UMA
                      fase. `"Concluidos "` não é uma fase de outra
                      época: é a mesma fase mal gravada, e um espaço à
                      direita é invisível no ecrã (Lote 5, ponto 2).
  3. `alias`        — nome legítimo de uma versão anterior do produto.
  4. `desconhecido` — não se adivinha. Vai para a coluna de órfãos, que é
                      visível a quem reconcilia.

  A gralha vem ANTES do alias de propósito: é o caso mais determinístico
  dos dois (a mesma string, mal escrita) e não deve ficar refém de uma
  tabela de nomes antigos.

O QUE ESTE MÓDULO NÃO FAZ
  Não escreve. A resolução é de LEITURA: o cartão aparece na coluna certa
  e o `status` gravado fica como está. Reescrever 205 processos em massa
  dispararia automações sobre processos que ninguém tocou — exactamente
  o defeito do `run_delete_workflow_status`. Quem muda a fase de um
  processo é o `run_move_process_kanban`, um de cada vez, com o motor a
  reagir.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Iterable, Optional

from database import db
from models.workflow import MacroFase
from services.process_status import INACTIVE_STATUSES, STATUS_VALUE_ALIASES

logger = logging.getLogger(__name__)

# Chave da coluna que recolhe o que não tem fase. Não é uma fase do
# motor — é o sítio onde o que sobra fica VISÍVEL em vez de desaparecer.
FASE_DESCONHECIDA = "__desconhecidas__"
ETIQUETA_DESCONHECIDA = "Fases desconhecidas"

# Nomes antigos de fases, de versões anteriores do produto. Porte de
# `frontend/src/utils/processTimeline.js::ALIASES_LEGADOS`, com guarda de
# paridade em `tests/unit/test_workflow_status_coverage.py`.
#
# NÃO é a lista de fases — essa vem do motor. É um RECURSO de leitura, e
# perde sempre para o motor.
ALIASES_LEGADOS_DO_PRODUTO: dict[str, str] = {
    "clientes_em_espera": "clientes_espera",
    "enviado_ao_bruno": "enviado_bruno",
    "enviado_ao_luis": "enviado_luis",
    "banco_em_analise": "fase_bancaria",
    "aprovado_pelo_banco": "ch_aprovado",
    "cpcv": "fase_escritura",
    "a_escriturar": "escritura_agendada",
    "escriturado": "concluidos",
    "recusado": "desistencias",
    "desistiu": "desistencias",
}


# ====================================================================
# TABELA DE ALIASES
# ====================================================================

def _fundir_grupos(grupos: list[set[str]]) -> list[set[str]]:
    """Funde grupos que partilhem pelo menos um nome.

    `escriturado -> concluidos` (frontend) e `{concluido, concluidos}`
    (backend) são o mesmo assunto visto de dois sítios; sem a fusão,
    procurar por `escriturado` não encontrava `concluido`.
    """
    fundidos: list[set[str]] = []
    for grupo in grupos:
        actual = set(grupo)
        restantes: list[set[str]] = []
        for existente in fundidos:
            if existente & actual:
                actual |= existente
            else:
                restantes.append(existente)
        restantes.append(actual)
        fundidos = restantes
    return fundidos


def construir_tabela_de_aliases() -> dict[str, set[str]]:
    """``nome -> outros nomes que significam o mesmo`` (sem o próprio)."""
    grupos = [set(v) for v in STATUS_VALUE_ALIASES.values()]
    grupos += [
        {antigo, actual}
        for antigo, actual in ALIASES_LEGADOS_DO_PRODUTO.items()
    ]
    tabela: dict[str, set[str]] = {}
    for grupo in _fundir_grupos(grupos):
        for nome in grupo:
            tabela[nome] = grupo - {nome}
    return tabela


def normalizar_para_gralha(nome: Optional[str]) -> str:
    """Forma canónica para detectar gralhas invisíveis.

    Um espaço à direita é outra chave no Mongo e a diferença não se vê no
    ecrã — a mesma armadilha do Campo de Rede (Lote 5, ponto 2).
    """
    return (nome or "").strip().lower().replace("-", "_")


# ====================================================================
# RESOLUÇÃO
# ====================================================================

@dataclass(frozen=True)
class Resolucao:
    """O que um `status` gravado significa para o motor de hoje."""

    original: str
    fase: Optional[str]
    motivo: str  # exacto | gralha | alias | desconhecido

    @property
    def resolvida(self) -> bool:
        return self.fase is not None

    @property
    def traduzida(self) -> bool:
        """Verdadeiro quando o nome gravado não é o nome da fase."""
        return self.resolvida and self.fase != self.original


def nomes_das_fases(fases: Iterable[dict]) -> list[str]:
    """Nomes, pela ordem em que vêm (o motor já ordena por `order`)."""
    return [
        f["name"] for f in fases
        if isinstance(f, dict) and f.get("name")
    ]


def resolver_nome(status: Optional[str], fases: Iterable[dict]) -> Resolucao:
    """A que fase do motor corresponde um `status` gravado.

    Nunca levanta e nunca adivinha: com zero ou mais do que um candidato,
    devolve `desconhecido`.
    """
    original = status or ""
    conhecidas = nomes_das_fases(fases)
    conjunto = set(conhecidas)

    if original in conjunto:
        return Resolucao(original, original, "exacto")

    if not original:
        return Resolucao(original, None, "desconhecido")

    # Gralha: várias fases não podem normalizar para a mesma chave, mas
    # se acontecer (o admin criou `Escritura` e `escritura`) é
    # ambiguidade e não se escolhe.
    alvo = normalizar_para_gralha(original)
    por_normalizacao = [n for n in conhecidas if normalizar_para_gralha(n) == alvo]
    if len(por_normalizacao) == 1:
        return Resolucao(original, por_normalizacao[0], "gralha")

    candidatos = sorted(construir_tabela_de_aliases().get(original, set()) & conjunto)
    if len(candidatos) == 1:
        return Resolucao(original, candidatos[0], "alias")

    return Resolucao(original, None, "desconhecido")


def resolver_muitos(
    valores: Iterable[Optional[str]],
    fases: Iterable[dict],
) -> dict[str, Resolucao]:
    """Resolve um conjunto de valores distintos de uma vez.

    A tabela de aliases é reconstruída a cada `resolver_nome`; num quadro
    com 1000 cartões isso seria 1000 reconstruções. Aqui resolve-se o
    conjunto DISTINTO, que num quadro real são dezenas.
    """
    fases = list(fases)
    return {
        valor: resolver_nome(valor, fases)
        for valor in {v or "" for v in valores}
    }


# ====================================================================
# CONJUNTOS DE FASES — o que substitui as listas cravadas
# ====================================================================

def nomes_terminais(fases: Iterable[dict]) -> list[str]:
    """Fases em que o processo está terminado.

    A verdade é a flag `is_active: False` do motor. Duas ressalvas, ambas
    a preservar comportamento existente:

    - Fase configurada SEM a flag definida cai na lista legada — a mesma
      regra de fallback do `resolve_workflow_purpose_flags`, para não
      mudar o significado de uma instalação que ainda não correu o
      backfill das flags.
    - Nomes da lista legada que NÃO são fases (`perdido`, `cancelado`,
      `arquivo`) continuam a contar como terminais. Existem em dados
      reais e deixá-los de fora fá-los-ia aparecer como activos, que é
      pior do que aparecerem como órfãos.
    """
    fases = list(fases)
    conhecidas = set(nomes_das_fases(fases))
    legado = set(INACTIVE_STATUSES)

    por_flag = {
        f["name"] for f in fases
        if isinstance(f, dict) and f.get("name") and f.get("is_active") is False
    }
    sem_flag = {
        f["name"] for f in fases
        if isinstance(f, dict) and f.get("name")
        and f.get("is_active") is None and f["name"] in legado
    }
    residuo_legado = legado - conhecidas
    return sorted(por_flag | sem_flag | residuo_legado)


def nomes_activos(fases: Iterable[dict]) -> list[str]:
    """Fases de trabalho: as que o motor conhece e não são terminais."""
    terminais = set(nomes_terminais(fases))
    return [n for n in nomes_das_fases(fases) if n not in terminais]


# ====================================================================
# CACHE DAS FASES
# ====================================================================
# As fases passaram a ser lidas em CADA pedido de listagem — é o preço
# de o motor mandar. São 14 documentos com índice, mas numa listagem de
# alta frequência é uma ida ao Mongo a mais por pedido.
#
# TTL curto, LOCAL AO PROCESSO. Com `UVICORN_WORKERS=2` cada worker tem a
# sua: uma edição de fase invalida a do worker que a gravou e o outro
# fica até 30s desactualizado. Para "que fases são terminais" isso é
# inofensivo e cura-se sozinho — e é por isso que o TTL é curto e não
# longo. Um cache mais esperto (invalidação por Pub/Sub) só se paga se o
# desfasamento passar a custar alguma coisa.
_TTL_DA_CACHE_SEGUNDOS = 30.0
#: rede (ou ``""`` para o MODELO) → (expira_em, fases)
_cache_de_fases: dict[str, tuple[float, list[dict]]] = {}

#: Valores que o Mongo trata como «sem rede» no campo `network_id` das fases.
_SEM_REDE = [None, ""]


def invalidar_cache_de_fases() -> None:
    """Esquece as fases em cache (de TODAS as redes). Chamada por quem ESCREVE uma fase.

    Também é o gancho dos testes: sem ela, uma bateria que patcha o `db`
    herdava as fases de um teste anterior e o resultado dependia da
    ORDEM de recolha do pytest — a mesma armadilha do
    `from database import db` ao nível do módulo.
    """
    _cache_de_fases.clear()


# ====================================================================
# WORKFLOW POR REDE (multi-tenant, Out 2026)
# ====================================================================
# Cada rede tem o SEU workflow: as fases, as flags de propósito, as macro-
# fases, os modelos de tarefas. Os documentos de `workflow_statuses` levam
# `network_id`; os que NÃO o levam são o MODELO — a semente de que uma rede
# nova nasce, e o recurso de uma rede que ainda não tem as suas.
#
# DUAS PERGUNTAS, DUAS RESPOSTAS (e misturá-las é o erro a evitar):
#
# 1. «O que é este PROCESSO?» (está fechado? o portal fecha? que automação
#    corre? que flags tem a fase?) — responde o workflow da rede DONA do
#    processo (`fases_do_processo`). Um processo partilhado com outra rede
#    continua a significar o que significa em casa: a fase gravada é um nome
#    do workflow do dono.
# 2. «O que VEJO?» (colunas do quadro, filtros, funil, ordenação) — responde
#    o workflow da rede de quem olha (`fases_do_ambito`).
def rede_do_processo(processo: Optional[dict]) -> Optional[str]:
    """A rede cujo workflow governa este processo: a do dono.

    Um processo por carimbar pertence à rede de omissão (a pilha antiga
    do grupo incumbente), se configurada; senão ao MODELO (``None``).
    """
    from services.tenant_network import CAMPO_REDE, rede_de_omissao

    rede = str((processo or {}).get(CAMPO_REDE) or "").strip()
    return rede or rede_de_omissao()


def _chave_da_rede(rede: Optional[str]) -> str:
    return str(rede or "").strip()


#: Para quem indexa o dicionário de `fases_por_rede` (chave = rede, ``""`` = modelo).
chave_da_rede = _chave_da_rede


async def ler_fases_da_rede(base, rede: Optional[str]) -> list[dict]:
    """A REGRA de leitura, sem cache: as da rede; se não tem, as do modelo.

    Recebe a base de dados como argumento para ter UM sítio onde a regra
    vive e vários módulos (que patcham o seu próprio `db` nos testes) a
    usá-la. Levanta se a leitura falhar — quem chama decide o degradado.
    """
    chave = _chave_da_rede(rede)
    fases: list[dict] = []
    if chave:
        fases = await base.workflow_statuses.find(
            {"network_id": chave}, {"_id": 0},
        ).sort("order", 1).to_list(500)
    if not fases:
        fases = await base.workflow_statuses.find(
            {"network_id": {"$in": _SEM_REDE}}, {"_id": 0},
        ).sort("order", 1).to_list(500)
    return fases


async def carregar_fases(*, rede: Optional[str] = None, usar_cache: bool = True) -> list[dict]:
    """As fases do workflow de UMA rede, por `order`. Degrada para `[]`, nunca levanta.

    `rede=None` é o MODELO (as fases sem `network_id`): serve os scripts, a
    migração e os testes — **um chamador de produção que tenha um processo
    ou um utilizador passa a rede** (há um inventário por AST que falha se
    um chamador novo a esquecer).

    Uma rede sem fases próprias recebe as do modelo: nada muda para quem
    ainda não migrou, e uma rede nova funciona antes de ser personalizada.
    (A escrita é que NUNCA toca no modelo por engano — `admin_workflow`
    materializa a cópia da rede antes de editar.)

    Uma leitura falhada não pode abrir o que a leitura bem sucedida
    fecharia (Gestor S3, Passo 3): sem fases, `nomes_activos` devolve
    vazio e `nomes_terminais` devolve só o resíduo legado — os filtros
    ficam restritivos, não permissivos.

    Uma leitura falhada TAMBÉM não fica em cache: guardar `[]` por 30s
    transformava um soluço do Mongo em meio minuto de listagens vazias.
    """
    chave = _chave_da_rede(rede)
    agora = time.monotonic()
    if usar_cache:
        em_cache = _cache_de_fases.get(chave)
        if em_cache is not None and agora < em_cache[0]:
            return em_cache[1]

    try:
        fases = await ler_fases_da_rede(db, chave)
    except Exception as e:  # pragma: no cover — degradação graciosa
        logger.warning(f"[WORKFLOW-PHASES] Falha ao ler as fases: {e}")
        return []

    if usar_cache:
        _cache_de_fases[chave] = (agora + _TTL_DA_CACHE_SEGUNDOS, fases)
    return fases


async def fases_do_processo(processo: Optional[dict]) -> list[dict]:
    """As fases que governam ESTE processo (o workflow da rede dona)."""
    return await carregar_fases(rede=rede_do_processo(processo))


async def fases_por_rede(redes: Iterable[Optional[str]]) -> dict[str, list[dict]]:
    """Fases de várias redes de uma vez (chave = rede, ``""`` = modelo).

    Para quem trabalha sobre uma LISTA de processos de redes diferentes (as
    próprias e as partilhadas): lê cada workflow uma vez, em vez de um por
    processo.
    """
    resultado: dict[str, list[dict]] = {}
    for rede in dict.fromkeys(_chave_da_rede(r) for r in redes):
        resultado[rede] = await carregar_fases(rede=rede or None)
    return resultado


async def fases_dos_processos(processos: Iterable[dict]) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """``(fases por rede, rede por id de processo)`` para uma lista de processos."""
    lista = [p for p in processos if isinstance(p, dict)]
    rede_de = {str(p.get("id")): _chave_da_rede(rede_do_processo(p)) for p in lista if p.get("id")}
    return await fases_por_rede(rede_de.values()), rede_de


def juntar_fases(listas: Iterable[list[dict]]) -> list[dict]:
    """Junta workflows de várias redes numa lista, por NOME.

    Para quem vê mais do que uma rede (utilizador com acesso a duas, ou o
    Master): a primeira rede ganha a definição de cada nome e a ordem é a
    menor `order` encontrada. Um nome é uma fase uma vez só.
    """
    por_nome: dict[str, dict] = {}
    for fases in listas:
        for fase in fases or []:
            nome = fase.get("name") if isinstance(fase, dict) else None
            if not nome:
                continue
            existente = por_nome.get(nome)
            if existente is None:
                por_nome[nome] = dict(fase)
            elif (fase.get("order") or 0) < (existente.get("order") or 0):
                existente["order"] = fase.get("order")
    return sorted(por_nome.values(), key=lambda f: (f.get("order") is None, f.get("order") or 0))


async def redes_com_workflow() -> list[str]:
    """As redes que têm fases próprias (sem o modelo)."""
    try:
        todas = await db.workflow_statuses.distinct("network_id")
    except Exception as e:  # pragma: no cover — degradação graciosa
        logger.warning(f"[WORKFLOW-PHASES] Falha a listar as redes com workflow: {e}")
        return []
    return sorted({_chave_da_rede(r) for r in todas if _chave_da_rede(r)})


async def nomes_terminais_de_todas_as_redes() -> list[str]:
    """Os nomes que QUALQUER workflow fecha (a união), mais os do modelo.

    Só para quem conta CARGA de trabalho de uma pessoa (indexador,
    consultor), que não pertence a um processo nem a uma rede: um processo
    fechado no workflow do dono não pesa. É uma aproximação, dita — se duas
    redes usarem o mesmo nome com sentidos opostos, a carga subestima; o que
    se perde é um desempate, não um acesso.
    """
    nomes = set(nomes_terminais(await carregar_fases()))
    for rede in await redes_com_workflow():
        nomes |= set(nomes_terminais(await carregar_fases(rede=rede)))
    return sorted(nomes)


async def nomes_activos_de_todas_as_redes() -> list[str]:
    """Os nomes que ALGUM workflow mantém activos (a união) — um SUPERCONJUNTO.

    Serve para pré-filtrar numa consulta; quem precisa da resposta exacta
    por processo filtra depois com `so_processos_com_fase_activa`.
    """
    nomes = set(nomes_activos(await carregar_fases()))
    for rede in await redes_com_workflow():
        nomes |= set(nomes_activos(await carregar_fases(rede=rede)))
    return sorted(nomes)


async def so_processos_com_fase_activa(processos: Iterable[dict]) -> list[dict]:
    """Os processos cuja fase está activa NO WORKFLOW DA REDE DONA (resposta exacta)."""
    lista = [p for p in processos if isinstance(p, dict)]
    por_rede, rede_de = await fases_dos_processos(lista)
    activas = {rede: set(nomes_activos(fases)) for rede, fases in por_rede.items()}
    return [
        p for p in lista
        if p.get("status") in activas.get(rede_de.get(str(p.get("id")), ""), set())
    ]


async def fases_do_ambito(scope) -> list[dict]:
    """As fases que quem OLHA vê: o workflow da(s) sua(s) rede(s).

    O Master (sem fronteira) e o consolidado (`scope=None`) vêem a junção de
    todas; um âmbito sem redes cai na rede de omissão e, sem ela, no modelo.
    """
    from services.tenant_network import rede_de_omissao

    if scope is None or getattr(scope, "sem_fronteira", False):
        redes = await redes_com_workflow()
        return juntar_fases([await carregar_fases(rede=r) for r in redes] or [await carregar_fases()])

    redes = [r for r in getattr(scope, "network_ids", ()) or () if _chave_da_rede(r)]
    if not redes:
        omissao = rede_de_omissao()
        redes = [omissao] if omissao else []
    if not redes:
        return await carregar_fases()
    return juntar_fases([await carregar_fases(rede=r) for r in redes])


async def fases_do_utilizador(user: dict) -> list[dict]:
    """O workflow de quem olha: `fases_do_ambito(âmbito do utilizador)`."""
    from services.tenant_network import resolve_tenant_scope

    return await fases_do_ambito(await resolve_tenant_scope(user))


# ====================================================================
# QUEM RECONCILIA
# ====================================================================
# Espelha deliberadamente `s3_explorer_scope.PAPEIS_DE_RECONCILIACAO`: é
# a mesma política de produto — o que não tem dono conhecido fica
# visível a quem o pode arrumar, e a mais ninguém. Duas constantes e não
# uma porque são dois domínios: juntá-las faria uma decisão sobre pastas
# mudar quem vê cartões.
def papeis_de_reconciliacao() -> frozenset:
    from services.role_scope import PAPEIS_GLOBAIS

    return frozenset(PAPEIS_GLOBAIS)


def pode_ver_desconhecidas(papel) -> bool:
    """O papel EFECTIVO decide (Lote 4): quem entra como Indexação não é admin.

    Desembrulha o Enum à mão de propósito: em Python 3.11
    `str(UserRole.ADMIN)` devolve `'UserRole.ADMIN'`, não `'admin'` — foi
    o que partiu 105 casos do alinhamento dos dois dialectos no Épico 10,
    Fase 2.
    """
    if papel is None:
        return False
    texto = getattr(papel, "value", papel)
    texto = str(texto).split(".")[-1].strip().lower()
    return texto in {
        str(getattr(p, "value", p)).split(".")[-1].strip().lower()
        for p in papeis_de_reconciliacao()
    }


# ====================================================================
# MACRO-FASES — o agrupamento do funil de negócio
# ====================================================================
# Enum FECHADO, derivado do modelo — não copiado. Duas cópias divergiriam,
# e a divergência aqui seria o Pydantic a recusar um valor que este módulo
# aceita (ou pior, ao contrário).
#
# São os VALORES em `str`, não os membros do Enum. Com o mixin `str` é o
# `str.__hash__` que ganha, portanto `MacroFase.NOVO in {"novo"}` até é
# verdadeiro — mas essa igualdade depende INTEIRAMENTE do mixin: num
# `Enum` puro, `__hash__` é o do NOME e a pertença passa a False em
# silêncio (a igualdade `==` também). Tirar `str` da declaração do Enum é
# uma linha inocente que partiria o agrupamento inteiro sem um erro.
#
# Daqui para dentro circula `str` simples: é o que vai para o Mongo, para
# o JSON e para as comparações, venha o documento do Pydantic ou da BD.
MACRO_FASES_VALIDAS: tuple[str, ...] = tuple(m.value for m in MacroFase)

# A SEMENTE, não a verdade. A partir da Parte 2 quem manda é o campo
# `macro_fase` no documento da fase, editável no WorkflowEditor; este
# mapa é o que o backfill semeia e o recurso para uma instalação que
# ainda não o correu.
MACRO_FASE_POR_OMISSAO: dict[str, str] = {
    # novo
    "clientes_espera": "novo",
    "fase_documental": "novo",
    "fase_documental_ii": "novo",
    "documentacao": "novo",
    # analise
    "enviado_bruno": "analise",
    "enviado_luis": "analise",
    "enviado_bcp_rui": "analise",
    "entradas_precision": "analise",
    "fase_bancaria": "analise",
    "fase_visitas": "analise",
    "analise": "analise",
    "pre_aprovacao": "analise",
    # Fases criadas pelo admin, vistas no retrato de produção. Decisão
    # de produto: ficam em "Em Análise" até serem editáveis na UI.
    "renegociacao": "analise",
    "pausa_cliente": "analise",
    # aprovado
    "ch_aprovado": "aprovado",
    "fase_escritura": "aprovado",
    "escritura_agendada": "aprovado",
    "credito_aprovado": "aprovado",
    "pedido_avaliacao": "aprovado",
    "avaliacao": "aprovado",
    "cpcv": "aprovado",
    "minuta": "aprovado",
    "aprovado": "aprovado",
    # concluido
    "concluidos": "concluido",
    "concluido": "concluido",
    "escritura": "concluido",
    # perdido
    "desistencias": "perdido",
    "desistencia": "perdido",
    "desistido": "perdido",
    "cancelado": "perdido",
    "perdido": "perdido",
    "arquivo": "perdido",
}


def macro_da_fase(fase: dict) -> Optional[str]:
    """A macro-fase de uma fase do motor.

    O campo `macro_fase` do documento ganha SEMPRE ao mapa de omissão —
    é a decisão do administrador, e é ela que a Parte 2 torna editável.
    Um valor fora do enum é ignorado (e registado): um grupo inventado
    parte o funil em silêncio, que é o que o enum fechado evita.
    """
    if not isinstance(fase, dict):
        return None
    declarada = fase.get("macro_fase")
    if declarada:
        # `.value` porque o documento pode vir do Pydantic (membro do
        # Enum) ou da base de dados (string). Daqui sai SEMPRE `str`.
        texto = str(getattr(declarada, "value", declarada))
        if texto in MACRO_FASES_VALIDAS:
            return texto
        logger.warning(
            f"[WORKFLOW-PHASES] Fase {fase.get('name')!r} declara a macro-fase "
            f"{declarada!r}, que não pertence ao enum — ignorada."
        )
    return MACRO_FASE_POR_OMISSAO.get(fase.get("name") or "")


def nomes_por_macro(fases: Iterable[dict], *macros: str) -> list[str]:
    """Nomes das fases do motor que pertencem a estas macro-fases.

    É isto que substitui as listas cravadas do BI. Devolve SÓ nomes que
    o motor conhece: uma estatística não pode continuar a medir fases
    que não existem.
    """
    pedidas = set(macros)
    return [
        f["name"] for f in fases
        if isinstance(f, dict) and f.get("name") and macro_da_fase(f) in pedidas
    ]


# ====================================================================
# BACKFILL IDEMPOTENTE DA MACRO-FASE
# ====================================================================

async def ensure_macro_fase_backfill() -> dict:
    """Semeia `macro_fase` nas fases que ainda não a têm (arranque).

    Mesmo padrão do `ensure_workflow_purpose_flags_backfill`: a semântica
    fica NA BASE DE DADOS e o runtime só lê a partir daí.

    IDEMPOTENTE, e a idempotência aqui é a parte que interessa:

    - Só escreve onde `macro_fase` está AUSENTE ou a `None`. Uma fase que
      o administrador já classificou nunca é tocada — correr isto outra
      vez não desfaz uma decisão humana, e é isso que torna seguro
      chamá-lo em todos os arranques.
    - A condição de ausência está na QUERY, não num `if` em Python: entre
      ler e escrever há uma janela em que o admin pode gravar, e o Mongo
      resolve-a por nós.
    - O que o mapa de omissão não cobre fica por classificar, de
      propósito. `None` é uma resposta: a fase aparece em "Outras fases",
      com o nome à vista, até alguém decidir. Inventar um grupo seria
      pior do que não ter nenhum.

    Nunca levanta — um arranque não pode falhar por causa disto.
    """
    escritas = 0
    ja_classificadas = 0
    sem_proposta: list[str] = []
    try:
        fases = await db.workflow_statuses.find({}, {"_id": 0}).to_list(500)
        for fase in fases:
            nome = fase.get("name")
            if not nome:
                continue
            if fase.get("macro_fase"):
                ja_classificadas += 1
                continue
            proposta = MACRO_FASE_POR_OMISSAO.get(nome)
            if not proposta:
                sem_proposta.append(nome)
                continue
            resultado = await db.workflow_statuses.update_one(
                {
                    "id": fase.get("id", nome),
                    "$or": [
                        {"macro_fase": {"$exists": False}},
                        {"macro_fase": None},
                    ],
                },
                {"$set": {"macro_fase": proposta}},
            )
            escritas += resultado.modified_count
        if escritas or sem_proposta:
            logger.info(
                f"[WORKFLOW-PHASES] Backfill de macro-fases: {escritas} "
                f"semeada(s), {ja_classificadas} já classificada(s), "
                f"{len(sem_proposta)} sem proposta ({sem_proposta})."
            )
    except Exception as e:  # pragma: no cover — arranque nunca falha
        logger.warning(
            f"[WORKFLOW-PHASES] Backfill de macro-fases falhou (não fatal): {e}"
        )
    return {
        "escritas": escritas,
        "ja_classificadas": ja_classificadas,
        "sem_proposta": sem_proposta,
    }
