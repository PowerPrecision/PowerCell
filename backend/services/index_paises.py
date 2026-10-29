"""Países dos recibos e extratos do Index: Portugal, Reino Unido, França, Países Baixos e Luxemburgo.

PURO — sem I/O, sem modelo. Há clientes que trabalham (ou trabalharam) fora e trazem recibos e extratos
estrangeiros. Lê-los com as regras portuguesas dava avisos falsos: a Segurança Social «não é 11 %» num
payslip inglês, o SIREN francês (9 dígitos) «é um NIF inválido», o líquido em libras «não aparece» no
extrato em euros, e o modelo lia o «Net à payer avant impôt» francês como o líquido pago.

O que se decide aqui:

* **o país** (`pais_do_documento`): o IBAN da conta manda num extrato (é o país da conta, não se lê mal);
  num recibo, o que o modelo leu (idioma, moeda, designações) e, sem ele, a moeda e o IBAN do ordenado.
  Sem nada, Portugal — o caso de sempre.
* **a moeda** (`moeda_do_documento`): o que o documento diz; sem isso, a do país (libra no Reino Unido).
* **as regras de cada país** (`verificar_descontos`): plausibilidade dos descontos obrigatórios. Só se
  avisa o que é IMPLAUSÍVEL nesse país; as taxas exactas mudam todos os anos (e por escalão, idade,
  regime) e um aviso falso custa mais do que um silêncio.

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **Tolerâncias explícitas**, uma por país e por desconto (constantes abaixo).
2. **As contas do recibo são iguais em todo o lado**: ilíquido − descontos = líquido. O que muda é o que
   conta como «descontos» (em França o imposto sai DEPOIS do «net avant impôt»), por isso a conferência
   aceita as formas em que cada país imprime o recibo — ver `index_matrix.conferencia_do_recibo`.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

PORTUGAL, REINO_UNIDO, FRANCA, PAISES_BAIXOS, LUXEMBURGO = "PT", "GB", "FR", "NL", "LU"
PAISES = (PORTUGAL, REINO_UNIDO, FRANCA, PAISES_BAIXOS, LUXEMBURGO)
NOME_DO_PAIS = {
    PORTUGAL: "Portugal", REINO_UNIDO: "Reino Unido", FRANCA: "França",
    PAISES_BAIXOS: "Países Baixos", LUXEMBURGO: "Luxemburgo",
}
#: «UK»/«EN» (Inglaterra) também chegam do modelo e das pessoas.
_SINONIMOS = {"UK": REINO_UNIDO, "EN": REINO_UNIDO, "ENG": REINO_UNIDO, "NE": PAISES_BAIXOS, "HOL": PAISES_BAIXOS}

EURO, LIBRA = "EUR", "GBP"
MOEDAS = (EURO, LIBRA)
_MOEDA_DO_PAIS = {REINO_UNIDO: LIBRA}
SIMBOLO_DA_MOEDA = {EURO: "€", LIBRA: "£"}

# --------------------------------------------------------------------
# tolerâncias por país (fracção do ilíquido)
# --------------------------------------------------------------------
#: Portugal: 11 % do trabalhador (23,75 % se o recibo mostra a parte da entidade), sobre a BASE de incidência.
TAXAS_SS_PT = (Decimal("0.11"), Decimal("0.2375"))
MARGEM_SS_PT = Decimal("0.0015")
#: Reino Unido: National Insurance do trabalhador (Class 1) nunca passou dos 12 % do pagamento.
NI_MAXIMO_GB = Decimal("0.12")
#: França: cotisations salariales rondam 20–25 % do brut; acima de 30 % é a parte patronal lida como do trabalhador.
COTISATIONS_MAXIMO_FR = Decimal("0.30")
#: Países Baixos: os prémios do trabalhador (pensioenpremie, WW…) raramente passam dos 15 %.
PREMIES_MAXIMO_NL = Decimal("0.15")
#: Luxemburgo: pension 8 % + maladie 3,05 % + dépendance 1,4 % ≈ 12,45 %.
COTISATIONS_MAXIMO_LU = Decimal("0.16")
#: O imposto retido acima disto do ilíquido não é plausível (o escalão máximo de qualquer dos cinco é < 50 %).
IMPOSTO_MAXIMO = {
    PORTUGAL: Decimal("0.50"), REINO_UNIDO: Decimal("0.45"), FRANCA: Decimal("0.43"),
    PAISES_BAIXOS: Decimal("0.52"), LUXEMBURGO: Decimal("0.45"),
}
#: Margem de arredondamento sobre os tectos (pontos percentuais).
MARGEM_DO_TECTO = Decimal("0.005")

#: Categorias das linhas do recibo (o modelo escolhe uma; o texto da linha não se guarda).
CATEGORIAS_DE_ABONO = (
    "vencimento_base", "subsidio_refeicao", "horas_extra", "subsidios", "premios", "ajudas_de_custo", "outro_abono",
)
CATEGORIAS_DE_DESCONTO = (
    "seguranca_social", "imposto", "pensao", "seguro_saude", "emprestimo_estudante", "pago_em_especie",
    "adiantamento", "penhora", "sindicato", "outro_desconto",
)
CATEGORIAS = CATEGORIAS_DE_ABONO + CATEGORIAS_DE_DESCONTO
#: Abonos que em Portugal NÃO entram na base da Segurança Social (até aos limites legais).
_ISENTOS_DE_SS_PT = ("subsidio_refeicao", "ajudas_de_custo")


def normalizar_pais(valor: Any) -> Optional[str]:
    """`PT`/`GB`/`FR`/`NL`/`LU`, ou `None`. Aceita «UK», «Inglaterra», «France»…"""
    if not isinstance(valor, str):
        return None
    t = valor.strip().upper()
    if t in PAISES:
        return t
    if t in _SINONIMOS:
        return _SINONIMOS[t]
    nomes = {
        "PORTUGAL": PORTUGAL, "INGLATERRA": REINO_UNIDO, "ENGLAND": REINO_UNIDO, "REINO UNIDO": REINO_UNIDO,
        "UNITED KINGDOM": REINO_UNIDO, "GREAT BRITAIN": REINO_UNIDO, "FRANCA": FRANCA, "FRANÇA": FRANCA,
        "FRANCE": FRANCA, "HOLANDA": PAISES_BAIXOS, "PAISES BAIXOS": PAISES_BAIXOS, "PAÍSES BAIXOS": PAISES_BAIXOS,
        "NETHERLANDS": PAISES_BAIXOS, "NEDERLAND": PAISES_BAIXOS, "LUXEMBURGO": LUXEMBURGO, "LUXEMBOURG": LUXEMBURGO,
    }
    return nomes.get(t)


def normalizar_moeda(valor: Any) -> Optional[str]:
    if not isinstance(valor, str):
        return None
    t = valor.strip().upper()
    return {"€": EURO, "EURO": EURO, "EUROS": EURO, "£": LIBRA, "GBP": LIBRA, "EUR": EURO}.get(t)


def pais_do_iban(iban: Any) -> Optional[str]:
    return normalizar_pais(iban[:2]) if isinstance(iban, str) and len(iban) >= 2 else None


def pais_do_documento(declarado: Any, *, iban: Any = None, moeda: Any = None, iban_manda: bool = False) -> str:
    """O país do documento. `iban_manda=True` (extrato): o IBAN da conta decide antes do que o modelo leu."""
    do_iban = pais_do_iban(iban)
    if iban_manda and do_iban:
        return do_iban
    lido = normalizar_pais(declarado)
    if lido:
        return lido
    if normalizar_moeda(moeda) == LIBRA:
        return REINO_UNIDO
    return do_iban or PORTUGAL


def moeda_do_documento(declarada: Any, pais: str) -> str:
    return normalizar_moeda(declarada) or _MOEDA_DO_PAIS.get(pais, EURO)


# --------------------------------------------------------------------
# regras por país
# --------------------------------------------------------------------
def _dec(valor: Any) -> Optional[Decimal]:
    if valor is None or isinstance(valor, bool):
        return None
    try:
        v = Decimal(str(valor))
    except Exception:  # noqa: BLE001
        return None
    return v if v.is_finite() else None


def _pct(valor: Decimal, casas: int = 2) -> str:
    return f"{(valor * 100).quantize(Decimal(1).scaleb(-casas))}".replace(".", ",") + " %"


def _soma(rubricas: list[dict], categorias: tuple[str, ...]) -> Optional[Decimal]:
    valores = [_dec(r.get("v")) for r in rubricas if r.get("cat") in categorias]
    valores = [v for v in valores if v is not None]
    return sum(valores, Decimal(0)) if valores else None


def bases_da_seguranca_social_pt(factos: dict) -> list[Decimal]:
    """As bases de incidência possíveis de um recibo português, da mais exacta para a menos.

    A base impressa; a soma dos abonos que o recibo marca como sujeitos; o ilíquido sem o subsídio de
    refeição e as ajudas de custo (isentos até ao limite legal); e o ilíquido. Comparar a SS só com o
    ilíquido dava «contas não batem» em quase todos os recibos com subsídio de refeição.
    """
    bases: list[Decimal] = []
    impressa = _dec(factos.get("ss_base"))
    if impressa and impressa > 0:
        bases.append(impressa)
    rubricas = [r for r in factos.get("rubricas") or [] if isinstance(r, dict)]
    abonos = [r for r in rubricas if r.get("k") == "abono"]
    sujeitos = [_dec(r.get("v")) for r in abonos if r.get("ss") is True]
    if any(v is not None for v in sujeitos):
        bases.append(sum((v for v in sujeitos if v is not None), Decimal(0)))
    bruto = _dec(factos.get("gross"))
    if bruto and bruto > 0:
        isentos = _soma(abonos, _ISENTOS_DE_SS_PT)
        if isentos:
            bases.append(bruto - isentos)
        bases.append(bruto)
    return [b for b in bases if b > 0]


def verificar_descontos(factos: dict, fmt) -> list[str]:
    """Motivos (texto) pelos quais os descontos de um recibo são implausíveis NO SEU PAÍS. `[]` = nada a dizer.

    `fmt(valor)` formata um valor na moeda do recibo. Só corre o que o recibo traz (dados em falta não são erro).
    """
    pais = factos.get("pais") or PORTUGAL
    bruto = _dec(factos.get("gross"))
    if not bruto or bruto <= 0:
        return []
    ss, imposto = _dec(factos.get("ss")), _dec(factos.get("irs"))
    motivos: list[str] = []

    if ss is not None and ss > 0:
        if pais == PORTUGAL:
            bases = bases_da_seguranca_social_pt(factos)
            if bases and not any(abs(ss / b - t) <= MARGEM_SS_PT for b in bases for t in TAXAS_SS_PT):
                motivos.append(
                    f"a Segurança Social ({fmt(ss)}) é {_pct(ss / bases[0])} da base de incidência "
                    f"({fmt(bases[0])}); o esperado em Portugal é 11 % ou 23,75 % (com a parte da entidade)"
                )
        else:
            tecto, nome = {
                REINO_UNIDO: (NI_MAXIMO_GB, "o National Insurance"),
                FRANCA: (COTISATIONS_MAXIMO_FR, "as cotisations salariales"),
                PAISES_BAIXOS: (PREMIES_MAXIMO_NL, "os prémios sociais do trabalhador"),
                LUXEMBURGO: (COTISATIONS_MAXIMO_LU, "as cotisations sociales"),
            }[pais]
            if ss / bruto > tecto + MARGEM_DO_TECTO:
                motivos.append(
                    f"{nome} ({fmt(ss)}) {'é' if pais == REINO_UNIDO else 'são'} {_pct(ss / bruto)} do ilíquido "
                    f"({fmt(bruto)}), acima do máximo plausível em {NOME_DO_PAIS[pais]} ({_pct(tecto)})"
                )
    if imposto is not None and imposto / bruto > IMPOSTO_MAXIMO.get(pais, IMPOSTO_MAXIMO[PORTUGAL]):
        nome = {
            PORTUGAL: "a retenção de IRS", REINO_UNIDO: "o Income Tax (PAYE)",
            FRANCA: "o prélèvement à la source", PAISES_BAIXOS: "a loonheffing", LUXEMBURGO: "o impôt retenu",
        }.get(pais, "o imposto retido")
        motivos.append(f"{nome} ({fmt(imposto)}) é {_pct(imposto / bruto, 1)} do ilíquido ({fmt(bruto)}), acima do plausível")
    return motivos


# --------------------------------------------------------------------
# o que o modelo precisa de saber para ler cada país
# --------------------------------------------------------------------
GUIA_DOS_PAISES = (
    " O documento pode ser de Portugal, do Reino Unido (Inglaterra), de França, dos Países Baixos (Holanda) ou do "
    "Luxemburgo. Identifica o país em 'country' (PT, GB, FR, NL ou LU) pelo idioma, pela moeda, pelo prefixo do "
    "IBAN e pelas designações, e lê o documento com as convenções DESSE país:"
    " PT (EUR): números 1.234,56; datas DD-MM-AAAA; recibo com Total ilíquido, Segurança Social, IRS, Total de "
    "descontos e Líquido a receber; extrato com Débito, Crédito e Saldo."
    " GB (GBP, £): números 1,234.56; datas DD/MM/YYYY; payslip com Gross pay, Income Tax (PAYE), National Insurance "
    "(NI), Pension, Student Loan, Total deductions e Net pay; extrato com Paid out (débito), Paid in (crédito) e "
    "Balance — um saldo com 'D', 'DR' ou 'OD' é NEGATIVO, com 'CR' é positivo."
    " FR (EUR): números 1 234,56; bulletin de paie com Salaire brut, Cotisations salariales (só a coluna da PART "
    "SALARIALE, nunca a part patronale/employeur), Net à payer avant impôt, Impôt sur le revenu prélevé à la "
    "source (PAS) e Net payé — o líquido é o NET PAYÉ, depois do PAS; extrato (relevé) com Débit, Crédit, Ancien "
    "solde e Nouveau solde."
    " NL (EUR): números 1.234,56; loonstrook com Bruto loon, Loonheffing, Pensioenpremie (werknemersdeel), "
    "vakantiegeld e netto vergoedingen/inhoudingen como linhas próprias, e Netto loon / Uit te betalen; extrato "
    "(rekeningafschrift) com Af (débito), Bij (crédito), Beginsaldo e Eindsaldo."
    " LU (EUR): números 1.234,56 ou 1 234,56; fiche de salaire com Salaire brut, cotisations sociales (assurance "
    "maladie, assurance pension, assurance dépendance), Impôt retenu e Net à payer; extrato com Débit, Crédit e Solde."
    " Devolve os valores como números (ponto decimal, sem separador de milhares) na moeda do documento, que indicas "
    "em 'currency' (EUR ou GBP)."
)
