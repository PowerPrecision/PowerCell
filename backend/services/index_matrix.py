"""Matriz de verificação do Index (Lote 12, Fase 2): cruza recibos, extratos e identificação.

PURA — sem I/O, sem modelo. Recebe os FACTOS que `index_ai` extraiu e devolve
achados (`code` + referências). As mensagens e as severidades vêm da tabela
`models.index_module.ALERTAS`; aqui só se decide SE há achado.

NADA AQUI BLOQUEIA a indexação. O resultado é uma lista de avisos para a pessoa
confirmar; um código a mais ou a menos nunca muda o que o utilizador pode fazer.

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **O código calcula; a IA só aponta.** O saldo, a recorrência e o crédito do
   ordenado são aritmética sobre os movimentos. Um achado da IA
   (`numerario_atipico`) só vale se o valor (e a data, quando a IA a dá) existir
   MESMO num movimento do extrato — um modelo não é uma parede.
2. **Dúvida a favor do cliente, e dita.** Data de um movimento desconhecida conta
   como «dentro do período»; sem extrato que cubra o mês, o aviso é `extrato_em_falta`
   (informativo), NUNCA `recibo_sem_credito`: falta de prova não é prova de falta.
3. **Dados em falta não são erro.** Uma verificação que precisa de um campo que o
   documento não tem NÃO corre (e não diz «tudo bem» nem «mal»).
4. **Tolerâncias explícitas** (constantes), não números soltos no meio da lógica.
"""
from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from models.index_module import nif_e_valido, normalizar_nif

#: Diferença aceite entre o líquido do recibo e o crédito no extrato: o maior de 1 € e 1 %.
TOLERANCIA_CREDITO_ABSOLUTA = Decimal("1.00")
TOLERANCIA_CREDITO_RELATIVA = Decimal("0.01")
#: Arredondamentos de cêntimos nas contas do recibo.
TOLERANCIA_CONTAS = Decimal("0.05")
#: Diferença aceite entre o saldo final e o que os movimentos dão.
TOLERANCIA_SALDO = Decimal("1.00")
#: Taxas da Segurança Social: 11 % (trabalhador) e 23,75 % (entidade). Margem de ±0,15 pontos.
TAXAS_SS = (Decimal("0.11"), Decimal("0.2375"))
MARGEM_SS = Decimal("0.0015")
#: Retenção de IRS acima disto do ilíquido não é plausível.
IRS_MAXIMO_PLAUSIVEL = Decimal("0.50")
#: Numerário num único movimento a partir deste valor é atípico.
NUMERARIO_ATIPICO = Decimal("1000.00")
#: Mesma contraparte, este nº de vezes ou mais, cada uma acima do mínimo → recorrente.
RECORRENCIA_MINIMA = 3
RECORRENCIA_VALOR_MINIMO = Decimal("100.00")
#: Se o extrato chegou ao tecto de movimentos pode estar truncado: não se confere o saldo.
TECTO_DE_MOVIMENTOS = 150


def _dec(valor: Any) -> Optional[Decimal]:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        v = Decimal(str(valor))
    except (InvalidOperation, ValueError):
        return None
    return v if v.is_finite() else None


def _data(valor: Any) -> Optional[date]:
    try:
        return date.fromisoformat(str(valor)[:10]) if valor else None
    except ValueError:
        return None


def _ref(documento: Optional[str], pagina: Optional[int] = None) -> dict:
    return {"document_id": documento, "page": pagina}


def _achado(code: str, refs: list[dict], periodo: Optional[str] = None) -> dict:
    return {"code": code, "refs": [r for r in refs if r.get("document_id")], "periodo": periodo}


def _nome_normal(nome: Any) -> str:
    import re
    import unicodedata

    t = unicodedata.normalize("NFD", str(nome or "").lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    t = re.sub(r"\b(lda|limitada|sa|s\.a|unipessoal|sociedade|ltd)\b\.?", " ", t)
    return " ".join(re.sub(r"[^a-z0-9 ]", " ", t).split())


def nome_normalizado_da_entidade(nome: Any) -> str:
    """Chave de comparação de nomes de entidades (sem acentos, pontuação nem «Lda»/«SA»)."""
    return _nome_normal(nome)


def _periodo(valor: Any) -> Optional[str]:
    """`YYYY-MM` real, ou `None`: os factos vêm da base de dados e a matriz não confia no que lê."""
    import re

    return valor if isinstance(valor, str) and re.fullmatch(r"\d{4}-(0[1-9]|1[0-2])", valor) else None


def _intervalo_do_mes_e_seguinte(periodo: str) -> tuple[date, date]:
    ano, mes = int(periodo[:4]), int(periodo[5:7])
    inicio = date(ano, mes, 1)
    ano2, mes2 = (ano + 1, 1) if mes == 12 else (ano, mes + 1)
    fim = date(ano2, mes2, calendar.monthrange(ano2, mes2)[1])
    return inicio, fim


# --------------------------------------------------------------------
# recibos
# --------------------------------------------------------------------
def _verificar_recibo(r: dict, extratos: list[dict], entidades: dict[str, str], hoje: date) -> list[dict]:
    achados: list[dict] = []
    doc = r.get("document_id")
    ref = [_ref(doc)]
    periodo = _periodo(r.get("period"))

    nif = normalizar_nif(r.get("employer_nif"))
    if nif and not nif_e_valido(nif):
        achados.append(_achado("nif_invalido", ref, periodo))
    nome = _nome_normal(r.get("employer_name"))
    if nif and nome and entidades.get(nome) and entidades[nome] != nif:
        achados.append(_achado("nif_entidade_incoerente", ref, periodo))

    liquido, bruto = _dec(r.get("net")), _dec(r.get("gross"))
    descontos, ss, irs = _dec(r.get("deductions")), _dec(r.get("ss")), _dec(r.get("irs"))

    # contas do recibo (três verificações independentes; o dedup junta as repetidas)
    if None not in (bruto, descontos, liquido) and abs(bruto - descontos - liquido) > TOLERANCIA_CONTAS:
        achados.append(_achado("contas_nao_batem", ref, periodo))
    if bruto and bruto > 0 and ss is not None:
        taxa = ss / bruto
        if not any(abs(taxa - t) <= MARGEM_SS for t in TAXAS_SS):
            achados.append(_achado("contas_nao_batem", ref, periodo))
    if bruto and bruto > 0 and irs is not None and irs / bruto > IRS_MAXIMO_PLAUSIVEL:
        achados.append(_achado("contas_nao_batem", ref, periodo))

    # realidade
    irreal = False
    if periodo and (int(periodo[:4]), int(periodo[5:7])) > (hoje.year, hoje.month):
        irreal = True  # recibo de um mês que ainda não existe
    if not nif and not r.get("employer_name"):
        irreal = True  # sem entidade nenhuma
    if bruto is not None and liquido is not None and liquido > bruto:
        irreal = True  # líquido acima do ilíquido
    cobrem = _extratos_que_cobrem(periodo, extratos)
    iban = r.get("iban")
    if iban and cobrem and all(e.get("iban") for e in cobrem) and not any(e["iban"] == iban for e in cobrem):
        irreal = True  # o ordenado iria para um IBAN que não é o das contas apresentadas
    if irreal:
        achados.append(_achado("recibo_irreal", ref, periodo))

    # o crédito no extrato
    if liquido is not None and periodo:
        if not cobrem:
            achados.append(_achado("extrato_em_falta", ref, periodo))
        elif not _ha_credito(liquido, periodo, cobrem):
            achados.append(_achado("recibo_sem_credito", ref + [_ref(e.get("document_id")) for e in cobrem], periodo))
    return achados


def _extratos_que_cobrem(periodo: Optional[str], extratos: list[dict]) -> list[dict]:
    """Extratos cujo intervalo toca o mês do recibo e o seguinte (o ordenado pode entrar no mês a seguir)."""
    if not periodo:
        return []
    inicio, fim = _intervalo_do_mes_e_seguinte(periodo)
    cobrem = []
    for e in extratos:
        a, b = _data(e.get("period_start")), _data(e.get("period_end"))
        # intervalo desconhecido: tenta pelas datas dos movimentos
        if a is None or b is None:
            datas = [d for d in (_data(m.get("d")) for m in e.get("movimentos") or []) if d]
            if datas:
                a, b = min(datas), max(datas)
        if a is None or b is None:
            continue
        if a <= fim and b >= inicio:
            cobrem.append(e)
    return cobrem


def _ha_credito(liquido: Decimal, periodo: str, extratos: list[dict]) -> bool:
    inicio, fim = _intervalo_do_mes_e_seguinte(periodo)
    tolerancia = max(TOLERANCIA_CREDITO_ABSOLUTA, liquido * TOLERANCIA_CREDITO_RELATIVA)
    for e in extratos:
        for m in e.get("movimentos") or []:
            if m.get("k") != "c":
                continue
            v = _dec(m.get("v"))
            if v is None or abs(v - liquido) > tolerancia:
                continue
            d = _data(m.get("d"))
            if d is None or inicio <= d <= fim:  # data desconhecida: dúvida a favor do cliente
                return True
    return False


# --------------------------------------------------------------------
# extratos
# --------------------------------------------------------------------
def _verificar_extrato(e: dict) -> list[dict]:
    achados: list[dict] = []
    doc = e.get("document_id")
    ref = [_ref(doc)]
    movimentos = e.get("movimentos") or []

    abertura, fecho = _dec(e.get("opening")), _dec(e.get("closing"))
    if None not in (abertura, fecho) and movimentos and len(movimentos) < TECTO_DE_MOVIMENTOS:
        creditos = sum((_dec(m["v"]) or Decimal(0) for m in movimentos if m.get("k") == "c"), Decimal(0))
        debitos = sum((_dec(m["v"]) or Decimal(0) for m in movimentos if m.get("k") == "d"), Decimal(0))
        if abs((abertura + creditos - debitos) - fecho) > TOLERANCIA_SALDO:
            achados.append(_achado("saldo_nao_bate", ref))

    estranho: list[dict] = []
    # numerário alto (código)
    for m in movimentos:
        v = _dec(m.get("v"))
        if m.get("canal") == "numerario" and v is not None and v >= NUMERARIO_ATIPICO:
            estranho.append(_ref(doc, m.get("page")))
    # a IA aponta numerário atípico: só vale se existe mesmo um movimento assim
    for a in e.get("achados") or []:
        if a.get("tipo") != "numerario_atipico":
            continue  # recorrência e saldo recalculam-se aqui; não se confia no que o modelo diz
        v = _dec(a.get("v"))
        if v is None:
            continue
        for m in movimentos:
            mv = _dec(m.get("v"))
            if mv is not None and abs(mv - v) <= Decimal("0.01") and (not a.get("d") or a["d"] == m.get("d")):
                estranho.append(_ref(doc, m.get("page") or a.get("page")))
                break
    # mesma contraparte várias vezes (código, pela impressão — o texto não existe aqui)
    por_contraparte: dict[str, int] = defaultdict(int)
    for m in movimentos:
        v = _dec(m.get("v"))
        if m.get("cp") and v is not None and v >= RECORRENCIA_VALOR_MINIMO and m.get("canal") != "debito_direto":
            por_contraparte[m["cp"]] += 1
    if any(n >= RECORRENCIA_MINIMA for n in por_contraparte.values()):
        estranho.append(_ref(doc))
    if estranho:
        achados.append(_achado("movimento_estranho", estranho))
    return achados


# --------------------------------------------------------------------
# identificação
# --------------------------------------------------------------------
def _verificar_identificacao(i: dict) -> list[dict]:
    ref = [_ref(i.get("document_id"))]
    if i.get("legivel") is False:
        return [_achado("identificacao_ilegivel", ref)]
    if i.get("expirada") is True:
        return [_achado("identificacao_expirada", ref)]
    return []


# --------------------------------------------------------------------
# entrada
# --------------------------------------------------------------------
def avaliar(
    factos: list[dict],
    *,
    entidades: Optional[dict[str, str]] = None,
    hoje: Optional[date] = None,
) -> list[dict]:
    """Todos os achados da matriz. `entidades`: `{nome_normalizado: nif}` já conhecidas.

    Devolve `[{"code", "refs", "periodo"}]`, sem repetições, na ordem em que surgem.
    """
    hoje = hoje or datetime.now(timezone.utc).date()
    entidades = entidades or {}
    recibos = [f for f in factos if f.get("tipo") == "recibo_vencimento"]
    extratos = [f for f in factos if f.get("tipo") == "extrato_bancario"]
    identificacoes = [f for f in factos if f.get("tipo") == "identificacao"]

    achados: list[dict] = []
    for r in recibos:
        achados.extend(_verificar_recibo(r, extratos, entidades, hoje))
    for e in extratos:
        achados.extend(_verificar_extrato(e))
    for i in identificacoes:
        achados.extend(_verificar_identificacao(i))

    vistos: set = set()
    unicos: list[dict] = []
    for a in achados:
        chave = (a["code"], tuple(r["document_id"] for r in a["refs"]), a.get("periodo"))
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(a)
    return unicos
