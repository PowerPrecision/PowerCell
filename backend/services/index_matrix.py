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
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
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
#: O saldo CORRENTE (coluna de saldo após cada movimento) tolera só arredondamentos de cêntimos.
TOLERANCIA_SALDO_CORRENTE = Decimal("0.02")
#: Só se confere linha a linha se a coluna de saldo foi lida em pelo menos esta fracção dos movimentos
#: (e em pelo menos 3): extratos que só imprimem o saldo no fim de cada dia não a têm em todas as linhas.
FRACCAO_MINIMA_COM_SALDO = Decimal("0.8")
MINIMO_DE_MOVIMENTOS_COM_SALDO = 3
#: Um movimento que a IA aponta como «atípico» só conta a partir deste valor. Abaixo disto são os pequenos
#: movimentos do dia-a-dia (50 €, 70 €…) que um analista de crédito não pede para confirmar; o que importa
#: nos pequenos valores é o PADRÃO (recorrência, fragmentação), que o código calcula à parte.
ATIPICO_DA_IA_MINIMO = Decimal("250.00")
#: Fragmentação de numerário: este nº de movimentos em numerário, da mesma natureza, numa janela destes dias,
#: cuja soma atinge `NUMERARIO_ATIPICO` (cada um abaixo dele) — o padrão de quem divide um depósito grande.
FRAGMENTACAO_MINIMA = 3
FRAGMENTACAO_JANELA_DIAS = 7


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


def _achado(code: str, refs: list[dict], periodo: Optional[str] = None, detalhe: Optional[str] = None) -> dict:
    """`detalhe` é a justificação exacta, em texto, calculada aqui a partir dos factos (ver `_eur`)."""
    return {
        "code": code, "refs": [r for r in refs if r.get("document_id")], "periodo": periodo,
        "detalhe": detalhe,
    }


# --------------------------------------------------------------------
# a JUSTIFICAÇÃO de cada achado (Out 2026)
# --------------------------------------------------------------------
# «Há movimentos que merecem confirmação» não diz o que confirmar. Cada achado leva agora o motivo
# exacto — o valor, a data, a diferença — e leva-o do CÓDIGO, que é quem faz as contas: um texto
# escrito pelo modelo podia dizer um valor que não existe. Nada pessoal: nunca o texto da contraparte
# (só se guarda a impressão), nunca nomes nem números de conta.
MAXIMO_DE_ITENS_NA_JUSTIFICACAO = 3


def _eur(valor: Decimal) -> str:
    """`1.234,56 €` (formato português)."""
    texto = f"{valor.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"
    return texto.replace(",", "\0").replace(".", ",").replace("\0", ".") + " €"


def _pct(valor: Decimal, casas: int) -> str:
    return f"{valor.quantize(Decimal(1).scaleb(-casas))}".replace(".", ",") + " %"


def _dia(valor: Any) -> str:
    d = _data(valor)
    return d.strftime("%d/%m/%Y") if d else "data desconhecida"


def _mes(periodo: Optional[str]) -> str:
    return f"{periodo[5:7]}/{periodo[:4]}" if periodo else "?"


def _lista(itens: list[str]) -> str:
    """Os primeiros itens por extenso e «e mais N» para o resto — nunca um parágrafo."""
    visiveis = itens[:MAXIMO_DE_ITENS_NA_JUSTIFICACAO]
    resto = len(itens) - len(visiveis)
    return "; ".join(visiveis) + (f"; e mais {resto}" if resto > 0 else "")


def _pagina(m: dict) -> str:
    return f" (pág. {m['page']})" if m.get("page") else ""


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
        achados.append(_achado(
            "nif_invalido", ref, periodo,
            f"NIF {nif} da entidade patronal falha o dígito de controlo (recibo de {_mes(periodo)}).",
        ))
    nome = _nome_normal(r.get("employer_name"))
    if nif and nome and entidades.get(nome) and entidades[nome] != nif:
        achados.append(_achado(
            "nif_entidade_incoerente", ref, periodo,
            f"O recibo de {_mes(periodo)} indica o NIF {nif}, mas a entidade já conhecida com este nome tem o NIF {entidades[nome]}.",
        ))

    liquido, bruto = _dec(r.get("net")), _dec(r.get("gross"))
    descontos, ss, irs = _dec(r.get("deductions")), _dec(r.get("ss")), _dec(r.get("irs"))

    # contas do recibo (três verificações independentes; o dedup junta as repetidas)
    if None not in (bruto, descontos, liquido) and abs(bruto - descontos - liquido) > TOLERANCIA_CONTAS:
        diferenca = abs(bruto - descontos - liquido)
        achados.append(_achado(
            "contas_nao_batem", ref, periodo,
            f"Recibo de {_mes(periodo)}: ilíquido {_eur(bruto)} − descontos {_eur(descontos)} dá "
            f"{_eur(bruto - descontos)}, mas o líquido indicado é {_eur(liquido)} (diferença de {_eur(diferenca)}).",
        ))
    if bruto and bruto > 0 and ss is not None:
        taxa = ss / bruto
        if not any(abs(taxa - t) <= MARGEM_SS for t in TAXAS_SS):
            achados.append(_achado(
                "contas_nao_batem", ref, periodo,
                f"Recibo de {_mes(periodo)}: a Segurança Social ({_eur(ss)}) é {_pct(taxa * 100, 2)} do ilíquido "
                f"({_eur(bruto)}); o esperado é 11 % ou 23,75 %.",
            ))
    if bruto and bruto > 0 and irs is not None and irs / bruto > IRS_MAXIMO_PLAUSIVEL:
        achados.append(_achado(
            "contas_nao_batem", ref, periodo,
            f"Recibo de {_mes(periodo)}: a retenção de IRS ({_eur(irs)}) é "
            f"{_pct(irs / bruto * 100, 1)} do ilíquido ({_eur(bruto)}), acima do plausível.",
        ))

    # realidade — cada motivo diz-se; vários motivos juntam-se numa só justificação
    motivos: list[str] = []
    if periodo and (int(periodo[:4]), int(periodo[5:7])) > (hoje.year, hoje.month):
        motivos.append(f"o período {_mes(periodo)} ainda não existe")
    if not nif and not r.get("employer_name"):
        motivos.append("não indica entidade patronal")
    if bruto is not None and liquido is not None and liquido > bruto:
        motivos.append(f"o líquido ({_eur(liquido)}) é superior ao ilíquido ({_eur(bruto)})")
    cobrem = _extratos_que_cobrem(periodo, extratos)
    iban = r.get("iban")
    if iban and cobrem and all(e.get("iban") for e in cobrem) and not any(e["iban"] == iban for e in cobrem):
        motivos.append("o IBAN do ordenado não é o de nenhuma das contas dos extratos do período")
    if motivos:
        achados.append(_achado("recibo_irreal", ref, periodo, f"Recibo de {_mes(periodo)}: " + "; ".join(motivos) + "."))

    # o crédito no extrato
    if liquido is not None and periodo:
        if not cobrem:
            achados.append(_achado(
                "extrato_em_falta", ref, periodo,
                f"Não há extrato que cubra {_mes(periodo)} (nem o mês seguinte) para confirmar o líquido de {_eur(liquido)}.",
            ))
        elif not _ha_credito(liquido, periodo, cobrem):
            tolerancia = max(TOLERANCIA_CREDITO_ABSOLUTA, liquido * TOLERANCIA_CREDITO_RELATIVA)
            achados.append(_achado(
                "recibo_sem_credito", ref + [_ref(e.get("document_id")) for e in cobrem], periodo,
                f"Líquido de {_eur(liquido)} do recibo de {_mes(periodo)}: não há crédito de valor semelhante "
                f"(±{_eur(tolerancia)}) nos extratos entre {_dia(_intervalo_do_mes_e_seguinte(periodo)[0])} "
                f"e {_dia(_intervalo_do_mes_e_seguinte(periodo)[1])}.",
            ))
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
def _sinal(m: dict) -> int:
    return 1 if m.get("k") == "c" else -1


def _quebras_do_saldo(ordem: list[dict], abertura: Optional[Decimal]) -> tuple[list[dict], Optional[Decimal]]:
    """Percorre os movimentos NESTA ordem e devolve onde o saldo impresso não bate com a conta.

    `esperado = saldo anterior ± movimento`; um movimento sem saldo impresso mantém a expectativa (não se
    inventa um saldo). Devolve `(quebras, saldo_do_último_movimento)`.
    """
    quebras: list[dict] = []
    anterior = abertura
    for i, m in enumerate(ordem):
        v = _dec(m.get("v"))
        if v is None:
            continue
        impresso = _dec(m.get("s"))
        esperado = None if anterior is None else anterior + _sinal(m) * v
        if impresso is None:
            anterior = esperado
            continue
        if esperado is not None and abs(esperado - impresso) > TOLERANCIA_SALDO_CORRENTE:
            quebras.append({"i": i, "m": m, "anterior": anterior, "impresso": impresso, "esperado": esperado})
        anterior = impresso
    return quebras, anterior


def _conferir_saldo_corrente(movimentos: list[dict], abertura: Optional[Decimal], fecho: Optional[Decimal]) -> Optional[str]:
    """A conta LINHA A LINHA, como a faria um analista com o extrato à frente. `None` = não se aplica.

    Só corre se a coluna de saldo foi lida (≥ 80 % dos movimentos). Experimenta a ordem do documento e a
    inversa (há bancos que listam do mais recente para o mais antigo) e fica com a que menos quebras tem.
    Devolve o texto da justificação se algo não bate, `""` se tudo bate, `None` se não é aplicável.
    """
    com_saldo = [m for m in movimentos if _dec(m.get("s")) is not None]
    if len(com_saldo) < MINIMO_DE_MOVIMENTOS_COM_SALDO or Decimal(len(com_saldo)) < FRACCAO_MINIMA_COM_SALDO * len(movimentos):
        return None
    directa = _quebras_do_saldo(movimentos, abertura)
    inversa = _quebras_do_saldo(movimentos[::-1], abertura)
    ordem, (quebras, ultimo) = (movimentos, directa) if len(directa[0]) <= len(inversa[0]) else (movimentos[::-1], inversa)

    frases: list[str] = []
    for q in quebras:
        m = q["m"]
        natureza = "crédito" if m.get("k") == "c" else "débito"
        origem = (
            "o primeiro movimento não parte do saldo inicial"
            if q["i"] == 0 and abertura is not None and q["anterior"] == abertura else "o saldo anterior era "
            + _eur(q["anterior"])
        )
        frases.append(
            f"no {natureza} de {_eur(_dec(m['v']))} a {_dia(m.get('d'))}{_pagina(m)}, {origem}; o saldo devia ficar em "
            f"{_eur(q['esperado'])} mas o extrato indica {_eur(q['impresso'])} (diferença de "
            f"{_eur(abs(q['esperado'] - q['impresso']))})"
        )
    fim = ""
    if fecho is not None and ultimo is not None and len(movimentos) < TECTO_DE_MOVIMENTOS and abs(ultimo - fecho) > TOLERANCIA_SALDO:
        fim = (
            f" O saldo depois do último movimento ({_eur(ultimo)}) não coincide com o saldo final indicado "
            f"({_eur(fecho)})."
        )
    if not frases and not fim:
        return ""
    texto = ""
    if frases:
        texto = (
            f"Conferindo o saldo linha a linha, falha em {len(frases)} ponto(s): {_lista(frases)}. "
            "Pode faltar um movimento ou ter sido lido um valor errado."
        )
    return (texto + fim).strip()


def _fragmentacao_de_numerario(movimentos: list[dict]) -> list[tuple[str, list[dict]]]:
    """Janelas em que o numerário foi FRACCIONADO: vários movimentos pequenos que juntos passam o limiar."""
    achados: list[tuple[str, list[dict]]] = []
    for natureza, rotulo in (("c", "depósitos"), ("d", "levantamentos")):
        pequenos = sorted(
            (
                (d, _dec(m.get("v")), m) for m in movimentos
                if m.get("canal") == "numerario" and m.get("k") == natureza
                and (d := _data(m.get("d"))) is not None and (v := _dec(m.get("v"))) is not None and v < NUMERARIO_ATIPICO
            ),
            key=lambda t: t[0],
        )
        i = 0
        while i < len(pequenos):
            janela = [t for t in pequenos[i:] if (t[0] - pequenos[i][0]).days < FRAGMENTACAO_JANELA_DIAS]
            total = sum((t[1] for t in janela), Decimal(0))
            if len(janela) >= FRAGMENTACAO_MINIMA and total >= NUMERARIO_ATIPICO:
                achados.append((
                    f"{len(janela)} {rotulo} em numerário entre {_dia(janela[0][0].isoformat())} e "
                    f"{_dia(janela[-1][0].isoformat())}, no total de {_eur(total)} (cada um abaixo de "
                    f"{_eur(NUMERARIO_ATIPICO)})",
                    [t[2] for t in janela],
                ))
                i += len(janela)       # a janela seguinte começa depois desta: não se conta duas vezes
            else:
                i += 1
    return achados


def _verificar_extrato(e: dict) -> list[dict]:
    achados: list[dict] = []
    doc = e.get("document_id")
    ref = [_ref(doc)]
    movimentos = e.get("movimentos") or []

    abertura, fecho = _dec(e.get("opening")), _dec(e.get("closing"))
    corrente = _conferir_saldo_corrente(movimentos, abertura, fecho) if movimentos else None
    if corrente is not None:
        # a conta linha a linha é mais exacta do que a dos totais: diz ONDE falha. Se ela bate, os totais
        # (que são só o encadeamento das mesmas linhas) não precisam de segunda opinião.
        if corrente:
            achados.append(_achado("saldo_nao_bate", ref, None, corrente))
    elif None not in (abertura, fecho) and movimentos and len(movimentos) < TECTO_DE_MOVIMENTOS:
        creditos = sum((_dec(m["v"]) or Decimal(0) for m in movimentos if m.get("k") == "c"), Decimal(0))
        debitos = sum((_dec(m["v"]) or Decimal(0) for m in movimentos if m.get("k") == "d"), Decimal(0))
        esperado = abertura + creditos - debitos
        if abs(esperado - fecho) > TOLERANCIA_SALDO:
            pista = ""
            if abertura == fecho:
                # dois valores iguais ao cêntimo num extrato com movimentos quase nunca são verdade: o mais
                # provável é o mesmo número lido duas vezes. Diz-se como pista, não como facto.
                pista = (
                    " O saldo final indicado é igual ao saldo inicial, o que costuma indicar o mesmo valor lido "
                    "duas vezes — confirmar o saldo final no extrato."
                )
            achados.append(_achado(
                "saldo_nao_bate", ref, None,
                f"Saldo inicial {_eur(abertura)} + créditos {_eur(creditos)} − débitos {_eur(debitos)} dá "
                f"{_eur(esperado)}, mas o saldo final indicado é {_eur(fecho)} (diferença de {_eur(abs(esperado - fecho))})."
                f"{pista} Este extrato não traz o saldo linha a linha, pelo que não se localiza onde falha "
                "(analisar de novo para o conferir movimento a movimento).",
            ))

    estranho: list[dict] = []
    razoes: list[str] = []
    por_movimento: dict[tuple, int] = {}  # (valor, data) → posição em `razoes`: o mesmo movimento diz-se UMA vez
    # numerário alto (código)
    for m in movimentos:
        v = _dec(m.get("v"))
        if m.get("canal") == "numerario" and v is not None and v >= NUMERARIO_ATIPICO:
            estranho.append(_ref(doc, m.get("page")))
            sentido = "Depósito" if m.get("k") == "c" else "Levantamento"
            por_movimento[(v, m.get("d"))] = len(razoes)
            razoes.append(f"{sentido} em numerário de {_eur(v)} a {_dia(m.get('d'))}{_pagina(m)}")
    # a IA aponta numerário atípico: só vale se existe mesmo um movimento assim
    for a in e.get("achados") or []:
        if a.get("tipo") != "numerario_atipico":
            continue  # recorrência e saldo recalculam-se aqui; não se confia no que o modelo diz
        v = _dec(a.get("v"))
        if v is None:
            continue
        for m in movimentos:
            mv = _dec(m.get("v"))
            if mv is not None and mv < ATIPICO_DA_IA_MINIMO:
                continue    # um movimento pequeno não é «atípico» por a IA o dizer; o padrão calcula-se à parte
            if mv is not None and abs(mv - v) <= Decimal("0.01") and (not a.get("d") or a["d"] == m.get("d")):
                estranho.append(_ref(doc, m.get("page") or a.get("page")))
                # o valor, a data e a página saem do MOVIMENTO (verificado); a nota é só a leitura do modelo
                nota = f" — nota da IA: {a['nota']}" if a.get("nota") else ""
                existente = por_movimento.get((mv, m.get("d")))
                if existente is not None:
                    razoes[existente] += nota  # o código já o apontou: só se junta a nota
                else:
                    por_movimento[(mv, m.get("d"))] = len(razoes)
                    razoes.append(f"Movimento atípico de {_eur(mv)} a {_dia(m.get('d'))}{_pagina(m)}{nota}")
                break
    # mesma contraparte várias vezes (código, pela impressão — o texto não existe aqui)
    por_contraparte: dict[str, list[Decimal]] = defaultdict(list)
    for m in movimentos:
        v = _dec(m.get("v"))
        if m.get("cp") and v is not None and v >= RECORRENCIA_VALOR_MINIMO and m.get("canal") != "debito_direto":
            por_contraparte[m["cp"]].append(v)
    recorrentes = [vs for vs in por_contraparte.values() if len(vs) >= RECORRENCIA_MINIMA]
    if recorrentes:
        estranho.append(_ref(doc))
        for vs in recorrentes:
            razoes.append(
                f"{len(vs)} movimentos de {_eur(RECORRENCIA_VALOR_MINIMO)} ou mais para a mesma contraparte, "
                f"no total de {_eur(sum(vs, Decimal(0)))}"
            )
    for frase, grupo in _fragmentacao_de_numerario(movimentos):
        estranho.extend(_ref(doc, m.get("page")) for m in grupo)
        razoes.append(frase)
    if estranho:
        achados.append(_achado("movimento_estranho", estranho, None, _lista(razoes) + "." if razoes else None))
    return achados


# --------------------------------------------------------------------
# identificação
# --------------------------------------------------------------------
def _verificar_identificacao(i: dict) -> list[dict]:
    ref = [_ref(i.get("document_id"))]
    if i.get("legivel") is False:
        return [_achado(
            "identificacao_ilegivel", ref, None,
            "Não se reconheceu o tipo do documento (cartão, bilhete, passaporte ou título) ou a imagem está ilegível.",
        )]
    if i.get("expirada") is True:
        return [_achado(
            "identificacao_expirada", ref, None,
            "A data de validade lida no documento é anterior à data de hoje.",
        )]
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

    # Sem repetições. Quando o mesmo achado nasce de duas verificações (as três contas de um recibo dão
    # todas `contas_nao_batem`), as justificações JUNTAM-SE: descartar a segunda escondia o motivo.
    por_chave: dict[tuple, dict] = {}
    for a in achados:
        chave = (a["code"], tuple(r["document_id"] for r in a["refs"]), a.get("periodo"))
        existente = por_chave.get(chave)
        if existente is None:
            por_chave[chave] = a
        elif a.get("detalhe") and a["detalhe"] not in (existente.get("detalhe") or ""):
            existente["detalhe"] = " ".join(filter(None, [existente.get("detalhe"), a["detalhe"]]))
    return list(por_chave.values())
