"""
====================================================================
O RELÓGIO DE FASES — quando o processo entrou onde está
====================================================================
Refinamento Analítico e SLAs (Dashboard), Camada 1.

PORQUE É QUE O RELÓGIO NÃO TEM ATOR
  A pergunta "quanto tempo fica um processo preso em Análise" não tem
  resposta na base de dados: só existem `created_at` e `updated_at`, e o
  segundo muda com qualquer escrita. A medição de produção confirmou o
  tamanho do problema — em 12.450 processos, **3.105 nunca foram tocados**
  depois de criados (a estimativa cairia na data de criação e
  sobrestimava) e **1.840 foram tocados depois de fechar** (subestimava).
  Quase 5.000 aproximações falsas.

  A fonte óbvia seria a colecção `history`, que grava `field="status"` com
  o antes e o depois. Não serve, e não é um defeito a corrigir: dos seis
  caminhos que escrevem `status`, dois são filtrados pelo stealth do
  perfil `indexacao`, o `process_indexing` silencia-se quando é a
  Indexação a avançar, o `portal_onboarding_advance` grava com
  `track_history: False` e o `workflow_engine.change_status` não grava
  nada. Metade das transições é invisível PORQUE A REGRA DE OURO ASSIM
  MANDA.

  Daí este desenho: o relógio é **estado do processo**, não rasto de um
  utilizador. Não recebe `user`, não sabe quem move, não escreve em
  `history` nem em `activities`. Funciona exactamente onde o rasto não
  pode existir — e o cronómetro fica correcto mesmo quando o autor tem de
  ser invisível. Há uma guarda sobre o código-fonte deste ficheiro em
  `test_process_phase_clock.py` a afirmar que nenhuma noção de utilizador
  entra aqui.

OS CAMPOS
  `fase_desde`                   instante de entrada na FASE actual
  `fase_desde_estimado`          o carimbo acima veio do backfill?
  `macro_fase_desde`             instante de entrada na MACRO-FASE actual
  `macro_fase_desde_estimado`    idem, para o carimbo da macro
  `tempos_macro`                 {macro: segundos} acumulado À SAÍDA

  Duas bandeiras e não uma: cada uma diz respeito ao seu carimbo. Um
  movimento DENTRO da mesma macro-fase torna o `fase_desde` medido mas
  deixa o `macro_fase_desde` como estava, e uma bandeira só não conseguia
  dizer isso sem mentir sobre metade.

PORQUE `macro_fase_desde` SÓ REINICIA QUANDO A MACRO MUDA
  Mover de `fase_documental` para `fase_escritura` não sai da Análise. Se
  reiniciasse, medir o gargalo passava a contar só a última sub-fase e o
  número ficava bonito à custa de ser falso.

PORQUE UM ACUMULADOR E NÃO UMA COLECÇÃO DE TRANSIÇÕES
  Um processo que volta de `aprovado` para `renegociacao` passa por
  Análise DUAS vezes, e o que interessa é a soma. Com o acumulador no
  documento, a média por macro-fase é um `$avg` sobre um campo que já
  existe: sem colecção nova, sem `$lookup`, sem pipeline sobre strings.

  As chaves de `tempos_macro` são **factos históricos** — o tempo foi
  passado enquanto aquela fase pertencia àquela macro. Não são uma cópia
  da verdade do motor, e é essa a diferença entre memória e dívida. Por
  isso a `macro_fase` NÃO é desnormalizada no processo: seria uma cópia em
  12.450 documentos, desactualizada no dia em que o administrador
  reclassificasse uma fase no `<Select>` da Parte 2.

O QUE NÃO É UMA TRANSIÇÃO
  - **Reestruturação do funil.** O `admin_workflow` move em massa os
    processos de uma fase eliminada. Decisão do dono: não reiniciar. O
    processo não avançou, o mapa mudou debaixo dele, e reiniciar apagava
    a evidência de que estava parado.
  - **Ciclo de vida.** Soft-delete e restauro escrevem `status`
    (`eliminado` e de volta) e não são fases de negócio. Apagar e
    restaurar um processo não pode limpar a prova de que esteve 90 dias
    em Análise.
  - **Guardar sem mudar de fase.** Um `PUT` com o mesmo `status`
    devolve uma transição VAZIA. Sem esta guarda, cada gravação reiniciava
    o cronómetro e nenhum processo aparecia preso.

O TEMPO ACUMULADO É SÓ O MEDIDO
  Um carimbo marcado como estimado nunca entra no `tempos_macro`: misturar
  medido com estimado é o erro que este lote inteiro existe para não
  cometer. A transição que sai de um carimbo estimado limpa a bandeira, e
  a partir daí acumula.
====================================================================
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

logger = logging.getLogger(__name__)

CAMPO_FASE_DESDE = "fase_desde"
CAMPO_FASE_ESTIMADO = "fase_desde_estimado"
CAMPO_MACRO_DESDE = "macro_fase_desde"
CAMPO_MACRO_ESTIMADO = "macro_fase_desde_estimado"
CAMPO_TEMPOS = "tempos_macro"

#: Macro-fases onde a permanência não é uma medida de eficiência: um
#: processo concluído não "demora" em concluído, fica lá. A medição de
#: produção mostra-o em bruto — 3.200 processos na banda `61+` de
#: `concluido` e 820 na de `perdido`. Quem lê o relógio para encontrar
#: gargalos tem de excluir estas, senão o painel grita sobre processos
#: que estão exactamente onde devem estar.
MACROS_SEM_PERMANENCIA: tuple[str, ...] = ("concluido", "perdido")

#: O que o relógio precisa de ler do processo ANTES da escrita.
#:
#: Declarado aqui e não em cada caminho porque a alternativa não é
#: testável: a base de dados falsa dos testes unitários IGNORA projecções
#: (contrato documentado no `conftest`), pelo que uma projecção que
#: deixasse cair o `status` passava em todos os testes e, em produção,
#: fazia o cronómetro carimbar sem nunca acumular — sub-medição
#: silenciosa, que é o pior resultado possível.
#:
#: Como constante, o facto fica afirmável: há um teste sobre o CONTEÚDO
#: desta projecção e uma guarda a exigir que os caminhos que leem o
#: processo de propósito para o relógio a usem.
PROJECCAO_DO_RELOGIO: dict = {
    "_id": 0,
    "status": 1,
    "created_at": 1,
    "fase_desde": 1,
    "fase_desde_estimado": 1,
    "macro_fase_desde": 1,
    "macro_fase_desde_estimado": 1,
}


def agora_utc() -> datetime:
    """O instante, em UTC. Isolado para os testes o poderem injectar."""
    return datetime.now(timezone.utc)


def _instante(valor: Any) -> Optional[datetime]:
    """Lê um instante do documento, ou `None`.

    Tolerante porque a colecção tem ISO com `Z`, ISO sem fuso e `datetime`
    nativo no mesmo campo. O que não se consegue ler conta como AUSENTE —
    nunca como agora, que daria uma permanência de zero segundos a um
    processo parado há meses.
    """
    if valor is None or valor == "":
        return None
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    try:
        lido = datetime.fromisoformat(str(valor).strip().replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return lido if lido.tzinfo else lido.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class Transicao:
    """Os campos a gravar numa transição de fase. Nunca contém o ator."""

    set: dict = field(default_factory=dict)
    inc: dict = field(default_factory=dict)

    @property
    def vazia(self) -> bool:
        return not self.set and not self.inc


TRANSICAO_VAZIA = Transicao()


def campos_de_transicao(
    *,
    fase_anterior: Optional[str],
    fase_nova: Optional[str],
    macro_anterior: Optional[str],
    macro_nova: Optional[str],
    documento: Optional[dict] = None,
    agora: Optional[datetime] = None,
) -> Transicao:
    """Os campos `$set`/`$inc` de uma transição. PURA e sem ator.

    `documento` é o processo ANTES da escrita — de onde saem os carimbos
    actuais e o `created_at`. Só se lê; nunca se muta.
    """
    if not fase_nova or fase_nova == fase_anterior:
        # Guardar sem mudar de fase não é uma transição. Sem isto, cada
        # `PUT` reiniciava o cronómetro e nada aparecia preso.
        return TRANSICAO_VAZIA

    agora = agora or agora_utc()
    instante_iso = agora.isoformat()
    doc = documento or {}

    conjunto: dict[str, Any] = {
        CAMPO_FASE_DESDE: instante_iso,
        CAMPO_FASE_ESTIMADO: False,
    }
    incrementos: dict[str, Any] = {}

    if macro_nova == macro_anterior:
        # Movimento DENTRO da mesma macro-fase: o relógio da macro não
        # reinicia e nada se acumula. É o caso de `fase_documental` →
        # `fase_escritura` dentro de `analise`.
        return Transicao(set=conjunto, inc=incrementos)

    conjunto[CAMPO_MACRO_DESDE] = instante_iso
    conjunto[CAMPO_MACRO_ESTIMADO] = False

    segundos = _segundos_na_macro(doc, agora)
    if macro_anterior and segundos is not None:
        incrementos[f"{CAMPO_TEMPOS}.{macro_anterior}"] = segundos

    return Transicao(set=conjunto, inc=incrementos)


def _segundos_na_macro(doc: dict, agora: datetime) -> Optional[int]:
    """Segundos MEDIDOS na macro-fase que se está a deixar, ou `None`.

    `None` significa "não se sabe", e não se acumula: um número inventado
    contaminava o acumulador que é a base de todas as médias.

    Três casos:
      1. Carimbo marcado como ESTIMADO → `None`. O acumulador só leva
         tempo medido; a bandeira limpa-se nesta transição e a seguinte
         já acumula.
      2. Carimbo presente e legível → a diferença.
      3. Sem carimbo nenhum → recurso ao `created_at`. Para um processo
         nascido depois deste código, a entrada na primeira fase É a
         criação, e isso é exacto, não uma estimativa. Para um processo
         legado que o backfill ainda não tocou é uma sobre-estimativa —
         daí a ordem de operações em produção: o backfill corre na mesma
         janela do deploy, e o que ele carimba fica marcado como estimado
         e cai no caso 1.
    """
    if doc.get(CAMPO_MACRO_ESTIMADO) is True:
        return None

    entrada = _instante(doc.get(CAMPO_MACRO_DESDE))
    if entrada is None:
        if doc.get(CAMPO_MACRO_DESDE) or doc.get(CAMPO_FASE_DESDE):
            # Há carimbo mas não se consegue ler: dado corrompido. Não se
            # troca por um recurso que daria um número plausível e errado.
            return None
        entrada = _instante(doc.get("created_at"))

    if entrada is None:
        return None

    segundos = int((agora - entrada).total_seconds())
    if segundos < 0:
        # Carimbo no futuro (relógios dessincronizados, dado corrompido).
        # Um negativo no `$inc` SUBTRAI tempo já medido de outras
        # passagens pela mesma macro-fase.
        logger.warning(
            "[PHASE-CLOCK] Carimbo no futuro (%s); nada acumulado.",
            doc.get(CAMPO_MACRO_DESDE) or doc.get("created_at"),
        )
        return None
    return segundos


def montar_update(conjunto: dict, transicao: Transicao) -> dict:
    """Documento de actualização do Mongo com o `$set` e o `$inc`.

    Os seis caminhos de escrita montam todos um dicionário de `$set` e
    chamam `update_one({"$set": ...})`. Esta função é a forma de lá meter
    o `$inc` sem cada um deles ter de saber que ele existe.

    O `$inc` vazio é OMITIDO: o Mongo recusa um operador de actualização
    sem campos, e a transição dentro da mesma macro-fase produz
    exactamente isso.
    """
    fundido = {**conjunto, **transicao.set}
    update: dict[str, Any] = {"$set": fundido}
    if transicao.inc:
        update["$inc"] = dict(transicao.inc)
    return update


# ====================================================================
# RESOLUÇÃO PELO MOTOR
# ====================================================================

async def _macro_de(nome: Optional[str], fases: list[dict]) -> Optional[str]:
    """Macro-fase de um valor de `status` tal como está GRAVADO.

    Passa pelo resolvedor: um processo gravado como `cpcv` ou
    `"Concluidos "` tem de contar na macro da fase a que corresponde, a
    mesma que o quadro lhe desenha. Sem isto, os 217 processos de alias e
    gralha do retrato de produção mudavam de macro-fase a cada movimento e
    o acumulador enchia-se de intervalos atribuídos ao grupo errado.
    """
    if not nome:
        return None

    from services.workflow_phases import macro_da_fase, resolver_nome

    resolucao = resolver_nome(nome, fases)
    if not resolucao.resolvida:
        return None
    for fase in fases:
        if isinstance(fase, dict) and fase.get("name") == resolucao.fase:
            return macro_da_fase(fase)
    return None


async def transicao_de_fase(
    processo: Optional[dict],
    nova_fase: Optional[str],
    *,
    agora: Optional[datetime] = None,
) -> Transicao:
    """A transição de um processo para `nova_fase`, resolvida pelo motor.

    É este o ponto que os caminhos de escrita chamam. NUNCA levanta: uma
    falha a ler as fases degrada para o carimbo da fase (que não precisa do
    motor) e deixa o relógio da macro como estava. Escrever um intervalo
    atribuído à macro errada é pior do que não escrever nenhum — e parar
    uma transição de negócio por causa de uma métrica seria pior do que as
    duas coisas.
    """
    doc = processo or {}
    fase_anterior = doc.get("status")

    macro_anterior = macro_nova = None
    try:
        from services.workflow_phases import carregar_fases

        fases = await carregar_fases()
        macro_anterior = await _macro_de(fase_anterior, fases)
        macro_nova = await _macro_de(nova_fase, fases)
    except Exception as exc:  # degradação graciosa
        logger.warning(
            "[PHASE-CLOCK] Falha a resolver as macro-fases (%s); só o "
            "carimbo da fase é gravado.", exc,
        )

    return campos_de_transicao(
        fase_anterior=fase_anterior,
        fase_nova=nova_fase,
        macro_anterior=macro_anterior,
        macro_nova=macro_nova,
        documento=doc,
        agora=agora,
    )
