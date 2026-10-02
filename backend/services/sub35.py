"""Sub35 — a etiqueta e o filtro de elegibilidade jovem (Lote 4, ponto 1).

PORQUE É QUE ISTO É UM PONTO ÚNICO E NÃO UM `if` EM CADA SÍTIO
==============================================================
A mesma pergunta — "este cliente tem menos de 36 anos?" — estava escrita
de QUATRO maneiras no sistema, e nenhuma delas funcionava de ponta a
ponta:

1. ``alerts.check_age_alert`` calcula a idade e compara com ``< 35``.
   Note-se: 35, não 36. Um cliente de 35 anos — que É elegível, porque os
   programas de apoio jovem vão "até aos 35 anos", inclusive — não
   recebia o alerta. Um ano inteiro de clientes de fora.

2. ``idade_menos_35`` é um booleano PERSISTIDO. O registo público
   escreve-o ``False`` à letra (``public_registration``), o
   ``client_assign`` copia-o do cliente e o ``client_registered``
   devolve-o ao frontend. Ninguém o CALCULA em sítio nenhum: é um campo
   que está sempre falso.

3. ``under_35`` está na projecção do Kanban
   (``PROCESS_KANBAN_PROJECTION``) e é lido por TRÊS componentes do
   frontend — ``KanbanCard``, ``SearchResultsList`` e
   ``FilteredProcessList``, cada um com a sua etiqueta "<35 anos"
   desenhada à mão. **Nenhum ficheiro do backend escreve este campo.**
   A etiqueta foi construída e nunca apareceu uma única vez.

   É a mesma forma do ``doc_id`` do Lote 3 e da fila Mongo do Lote 2:
   a UI lê um campo que o servidor nunca enviou. Terceiro lote seguido.

4. A data de nascimento vive em DOIS nomes — ``birth_date`` e
   ``data_nascimento`` — e o ``client_crud`` sincroniza as duas entradas
   do formulário para ``personal_data.data_nascimento``, que é
   precisamente o nome que o ``check_age_alert`` **não** lê.

Daí este módulo: uma regra, um limite, uma lista de campos. O cálculo é
dinâmico (a idade muda sozinha todos os dias — um booleano gravado fica
errado no dia do aniversário) e a condição Mongo do filtro deriva do
MESMO limite que o predicado em Python, para a listagem filtrada e a
etiqueta nunca discordarem.

A REGRA DE NEGÓCIO
==================
Sub35 = **menos de 36 anos** = até aos 35, inclusive. É o critério dos
apoios à habitação jovem (isenção de IMT/IS e garantia pública), e foi o
que o dono do produto confirmou. ``check_age_alert`` passa a derivar
daqui, o que corrige o tal ano de clientes que ficava de fora.

A data de nascimento NÃO é encriptada em repouso (não está nas
``SENSITIVE_FIELDS``), ao contrário do NIF. É o que permite comparar no
Mongo — e é dívida técnica registada (D-15), não um desenho.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

logger = logging.getLogger(__name__)

# ────────────────────────────────────────────────────────────────────
# A REGRA
# ────────────────────────────────────────────────────────────────────

#: Idade máxima elegível, INCLUSIVE (até aos 35).
IDADE_MAXIMA_INCLUSIVE = 35

#: O limite exclusivo que se usa nas comparações: idade < 36.
IDADE_EXCLUSIVA = IDADE_MAXIMA_INCLUSIVE + 1

#: Os dois nomes do mesmo campo. Ler só um é como o defeito nasceu.
CAMPOS_DE_NASCIMENTO = ("birth_date", "data_nascimento")

#: Onde a data vive num PROCESSO (por ordem de confiança).
SECCOES_DO_PROCESSO = ("personal_data",)

#: Onde vive num CLIENTE da Pool.
SECCOES_DO_CLIENTE = ("dados_pessoais",)

#: A secção do 2.º TITULAR — a mesma no processo e no cliente. O
#: `titular2_data` fica no cliente até o processo nascer e é copiado na
#: criação (ver `process_create`).
SECCAO_DO_TITULAR2 = "titular2_data"

#: O que prova que um 2.º titular EXISTE.
#:
#: Nunca `if doc.get("titular2_data")`: o formulário público grava as
#: chaves PRESENTES E VAZIAS (`{"nif": "", "name": ""}`), logo o
#: dicionário é verdadeiro e não há titular nenhum. É a lição do RGPD do
#: 2.º titular — «presente mas vazio» não é «presente» — e aqui o custo
#: de a esquecer era retirar a etiqueta a TODOS os processos do portal.
CHAVES_DE_IDENTIDADE = ("name", "nome", "nif", "documento_id")

#: Booleanos legados que, quando explicitamente verdadeiros, VENCEM o
#: cálculo. São uma marca manual: alguém afirmou a elegibilidade sem a
#: data de nascimento estar na ficha. `check_age_alert` já os honrava e
#: retirar-lhes o efeito apagaria informação introduzida à mão.
MARCAS_MANUAIS = ("is_sub35", "under_35", "idade_menos_35")

#: O campo que a UI lê. Um nome só, escolhido de propósito para deixar
#: de haver dois (`under_35` fica como marca manual de leitura).
CAMPO_DA_FLAG = "is_sub35"

#: Os campos que uma projecção de listagem tem de trazer para a etiqueta
#: poder ser calculada. Vive AQUI e espalha-se com `**` nas projecções
#: (`process_service`), em vez de ser escrita à mão em cada uma: foi uma
#: lista de campos repetida em três sítios que produziu o desfasamento de
#: atribuição do Lote 5, e uma projecção a que falte um destes campos dá
#: uma etiqueta ausente — silenciosamente, porque um campo que não vem
#: lê-se como "não é Sub35".
PROJECCAO = {
    "personal_data.birth_date": 1,
    "personal_data.data_nascimento": 1,
    "birth_date": 1,
    "data_nascimento": 1,
    # As marcas manuais: nenhuma é escrita pelo backend, mas uma delas
    # posta à mão é informação e tem de chegar aos DOIS ecrãs — se o
    # Kanban a projectar e a listagem não, a mesma linha tem etiqueta num
    # ecrã e não tem no outro.
    "under_35": 1,
    "idade_menos_35": 1,
}

#: `YYYY-MM-DD` — o formato canónico. Tudo o que escreve esta data
#: (formulário `type=date`, prompts da IA, `strptime` do `alerts`) usa
#: ISO; é também o que torna a comparação lexicográfica no Mongo fiel.
_FORMATO_ISO = "%Y-%m-%d"


def _hoje(hoje: Optional[date] = None) -> date:
    if isinstance(hoje, datetime):
        return hoje.date()
    if isinstance(hoje, date):
        return hoje
    return datetime.now().date()


def data_iso(valor: Any) -> Optional[str]:
    """`YYYY-MM-DD` a partir do que estiver gravado, ou `None`.

    Aceita `datetime`/`date` (há escritores que gravam objectos) e uma
    string ISO com ou sem hora. **Recusa** tudo o resto, incluindo
    `15/03/1988`: uma data noutro formato não se compara com o limite, e
    adivinhar a ordem dia/mês de um registo ambíguo
    (`03/04/1990`) poria um cliente na lista errada sem ninguém notar.
    """
    if valor is None:
        return None
    if isinstance(valor, datetime):
        return valor.date().isoformat()
    if isinstance(valor, date):
        return valor.isoformat()
    if not isinstance(valor, str):
        return None

    texto = valor.strip()
    if not texto:
        return None
    # "1990-03-15T00:00:00Z" → "1990-03-15"
    texto = texto.split("T")[0].split(" ")[0]
    try:
        return datetime.strptime(texto, _FORMATO_ISO).date().isoformat()
    except ValueError:
        return None


def idade(valor: Any, hoje: Optional[date] = None) -> Optional[int]:
    """Idade em anos completos, ou `None` se a data não for interpretável."""
    iso = data_iso(valor)
    if not iso:
        return None
    nascimento = datetime.strptime(iso, _FORMATO_ISO).date()
    referencia = _hoje(hoje)
    anos = referencia.year - nascimento.year
    if (referencia.month, referencia.day) < (nascimento.month, nascimento.day):
        anos -= 1
    return anos


def data_limite_de_nascimento(hoje: Optional[date] = None) -> str:
    """A data de nascimento de quem faz 36 anos HOJE.

    Quem nasceu DEPOIS dela tem menos de 36; quem nasceu nela faz 36 hoje
    e já não é elegível. Daí o filtro usar `$gt` e não `$gte`.
    """
    referencia = _hoje(hoje)
    try:
        limite = referencia.replace(year=referencia.year - IDADE_EXCLUSIVA)
    except ValueError:
        # 29 de Fevereiro cujo ano-36 não é bissexto (2136 → 2100).
        # 1 de Março é o dia em que essa pessoa faz anos nesse ano.
        limite = date(referencia.year - IDADE_EXCLUSIVA, 3, 1)
    return limite.isoformat()


def e_sub35(valor: Any, hoje: Optional[date] = None) -> bool:
    """A data de nascimento é de alguém com menos de 36 anos?"""
    anos = idade(valor, hoje)
    if anos is None:
        return False
    # Uma data no FUTURO é um erro de introdução, não um bebé: idade
    # negativa não é elegibilidade.
    if anos < 0:
        return False
    return anos < IDADE_EXCLUSIVA


def _primeira_data(doc: dict, seccoes: Iterable[str]) -> Any:
    """A data de nascimento do documento: secções primeiro, raiz depois."""
    if not isinstance(doc, dict):
        return None
    for seccao in seccoes:
        bloco = doc.get(seccao)
        if isinstance(bloco, dict):
            for campo in CAMPOS_DE_NASCIMENTO:
                if data_iso(bloco.get(campo)):
                    return bloco.get(campo)
    # Alguns processos antigos têm a data na raiz.
    for campo in CAMPOS_DE_NASCIMENTO:
        if data_iso(doc.get(campo)):
            return doc.get(campo)
    return None


def tem_marca_manual(doc: dict) -> bool:
    """Alguém afirmou a elegibilidade à mão (e não a negou)."""
    if not isinstance(doc, dict):
        return False
    return any(doc.get(campo) is True for campo in MARCAS_MANUAIS)


def _e_sub35_do_documento(doc: dict, seccoes, hoje=None) -> bool:
    if not isinstance(doc, dict):
        return False
    if tem_marca_manual(doc):
        return True
    return e_sub35(_primeira_data(doc, seccoes), hoje)


def titular2_presente(doc: dict) -> bool:
    """Existe um 2.º titular com identidade preenchida?

    `titular2_data` existe quase sempre — o registo público grava-o com
    as chaves vazias. O que conta é haver VALOR em alguma das chaves de
    identidade.
    """
    if not isinstance(doc, dict):
        return False
    bloco = doc.get(SECCAO_DO_TITULAR2)
    if not isinstance(bloco, dict):
        return False
    return any(
        bloco.get(chave) is not None and str(bloco.get(chave)) != ""
        for chave in CHAVES_DE_IDENTIDADE
    )


def titular2_bloqueia(doc: dict, hoje: Optional[date] = None) -> bool:
    """O 2.º titular impede a etiqueta Sub35?

    REGRA (Lote 5, confirmada pelo dono do produto): o benefício do
    Estado exige que **todos** os compradores cumpram o requisito de
    idade. Logo um 2.º titular com mais de 35 anos retira a etiqueta ao
    processo inteiro.

    **E a data desconhecida também bloqueia.** "Todos têm 35 ou menos"
    não se pode afirmar de quem não tem data na ficha, e o custo dos dois
    erros não é simétrico: uma etiqueta a mais faz o consultor prometer a
    um cliente uma isenção de IMT que a Autoridade Tributária vai
    recusar; uma etiqueta a menos é uma oportunidade que alguém confirma
    à mão. Falha fechada, como a audiência dos alertas.
    """
    if not titular2_presente(doc):
        return False
    bloco = doc.get(SECCAO_DO_TITULAR2) or {}
    for campo in CAMPOS_DE_NASCIMENTO:
        if data_iso(bloco.get(campo)):
            return not e_sub35(bloco.get(campo), hoje)
    # Titular real, sem data interpretável.
    return True


def processo_e_sub35(processo: dict, hoje: Optional[date] = None) -> bool:
    """O processo é Sub35? TODOS os titulares com 35 anos ou menos.

    Os `co_buyers` ficam de fora e não é esquecimento: a estrutura que o
    `ai_document` grava (nome, nif, cc, estado civil, morada, contactos)
    **não tem data de nascimento nenhuma**. Bloquear por eles seria
    bloquear por dados que não existem — retirava a etiqueta a todos os
    processos com mais de um comprador sem nunca poder confirmar porquê.
    Fica dito em `TECHNICAL_DEBT.md` (D-17).
    """
    if tem_marca_manual(processo):
        # Afirmação humana sobre o processo INTEIRO: quem a escreveu sabe
        # quantos compradores há. Não se descarta informação introduzida
        # à mão — é a mesma razão por que `check_age_alert` já a honrava.
        return True
    if not _e_sub35_do_documento(processo, SECCOES_DO_PROCESSO, hoje):
        return False
    return not titular2_bloqueia(processo, hoje)


def cliente_e_sub35(cliente: dict, hoje: Optional[date] = None) -> bool:
    """O cliente da Pool é Sub35? (mesma regra, outra secção).

    O `titular2_data` do cliente é o MESMO bloco que será copiado para o
    processo, logo a regra estrita vale aqui desde a triagem.
    """
    if tem_marca_manual(cliente):
        return True
    if not _e_sub35_do_documento(cliente, SECCOES_DO_CLIENTE, hoje):
        return False
    return not titular2_bloqueia(cliente, hoje)


def aplicar_flag_a_processos(
    processos: Optional[list], hoje: Optional[date] = None
) -> None:
    """Escreve `is_sub35` em cada processo da lista, no sítio.

    Ponto único de serialização: as listagens e o Kanban chamam isto em
    vez de cada uma calcular a sua. `under_35` continua a ser escrito
    porque é o nome que três componentes do frontend já leem — e durante
    a transição é mais seguro enviar os dois do que esperar que todos os
    ecrãs mudem no mesmo commit.
    """
    for processo in processos or []:
        if not isinstance(processo, dict):
            continue
        valor = processo_e_sub35(processo, hoje)
        processo[CAMPO_DA_FLAG] = valor
        processo["under_35"] = valor


def aplicar_flag_a_clientes(
    clientes: Optional[list], hoje: Optional[date] = None
) -> None:
    """O mesmo para os registos da Pool."""
    for cliente in clientes or []:
        if not isinstance(cliente, dict):
            continue
        cliente[CAMPO_DA_FLAG] = cliente_e_sub35(cliente, hoje)


# ────────────────────────────────────────────────────────────────────
# O FILTRO (Mongo)
# ────────────────────────────────────────────────────────────────────

#: Só uma data ISO bem formada participa na comparação. Sem esta âncora,
#: `"25/03/1988" > "1990-10-02"` é VERDADEIRO (compara `"2"` com `"1"`) e
#: um registo com a data em formato português entrava na lista como se
#: fosse de um jovem. Com ela, uma data mal formatada fica de fora — que
#: é o mesmo que o predicado em Python faz.
REGEX_ISO = "^[0-9]{4}-[0-9]{2}-[0-9]{2}"


def intervalo_de_nascimento(hoje: Optional[date] = None) -> tuple[str, str]:
    """O intervalo meio-aberto `[inicio, fim)` das datas de nascimento Sub35.

    - `inicio` = o dia SEGUINTE ao de quem faz 36 hoje (inclusive);
    - `fim` = amanhã (exclusivo), para excluir datas no FUTURO.

    Porque é meio-aberto e por dias INTEIROS: uma data pode estar gravada
    como `1990-10-03T00:00:00Z`, e a âncora do regex casa só o prefixo.
    Com `$gt "1990-10-02"`, essa string com hora entrava — e o predicado
    em Python, que corta a hora, dizia que não. Foi o teste de
    concordância a apanhar exactamente isso na primeira execução, com a
    data no futuro: o filtro incluía um `2206-01-01` (gralha de
    introdução) que a etiqueta recusava.
    """
    referencia = _hoje(hoje)
    limite = datetime.strptime(data_limite_de_nascimento(referencia), _FORMATO_ISO).date()
    inicio = limite + timedelta(days=1)
    fim = referencia + timedelta(days=1)
    return inicio.isoformat(), fim.isoformat()


def _ramos_do_campo(caminho: str, inicio: str, fim: str) -> list[dict]:
    inicio_dt = datetime.strptime(inicio, _FORMATO_ISO)
    fim_dt = datetime.strptime(fim, _FORMATO_ISO)
    return [
        # Gravado como TEXTO ISO (o caso normal).
        {caminho: {"$gte": inicio, "$lt": fim, "$regex": REGEX_ISO}},
        # Gravado como DATA BSON. Sem `$type`: no Mongo um `$gte` com um
        # limite `datetime` só casa com datas (type bracketing) e um
        # `$gte` com limite string só casa com strings — os dois ramos
        # excluem-se sozinhos, e é também assim que o duplo de teste se
        # comporta (compara e apanha o `TypeError`). Um `$type` seria
        # IGNORADO pelo duplo e o teste provaria menos do que parece.
        {caminho: {"$gte": inicio_dt, "$lt": fim_dt}},
    ]


def condicao_sem_titular2(seccao: str = SECCAO_DO_TITULAR2) -> dict:
    """"Não há 2.º titular" — sem `$nor` e sem `$not`.

    Um `{"$in": [None, ""]}` por chave de identidade casa com o campo
    AUSENTE, `null` e a string vazia (o que o formulário público grava), e
    é expressável com os operadores que tanto o Mongo como o duplo de
    teste já implementam. A negação explícita (`$nor`) seria ignorada
    pelo duplo — o teste de concordância ficaria verde a provar menos do
    que parece, que é a armadilha do duplo demasiado esperto.
    """
    return {
        "$and": [
            {f"{seccao}.{chave}": {"$in": [None, ""]}}
            for chave in CHAVES_DE_IDENTIDADE
        ]
    }


def condicao_sub35(
    hoje: Optional[date] = None, *, seccoes: Iterable[str] = SECCOES_DO_PROCESSO
) -> dict:
    """A condição Mongo "é Sub35", pelo MESMO limite do predicado.

    Estrutura (Lote 5):

        marca manual   OU   (titular 1 é Sub35   E   o 2.º não bloqueia)

    As marcas manuais ficam de fora do `$and` porque são uma afirmação
    sobre o processo inteiro — a mesma precedência do predicado.
    """
    inicio, fim = intervalo_de_nascimento(hoje)

    def ramos_das_datas(secs: Iterable[str]) -> list[dict]:
        ramos: list[dict] = []
        for seccao in secs:
            for campo in CAMPOS_DE_NASCIMENTO:
                ramos.extend(_ramos_do_campo(f"{seccao}.{campo}", inicio, fim))
        return ramos

    # Titular 1: nas secções pedidas e, em recurso, na raiz do documento.
    ramos_titular1 = ramos_das_datas(seccoes)
    for campo in CAMPOS_DE_NASCIMENTO:
        ramos_titular1.extend(_ramos_do_campo(campo, inicio, fim))

    # O 2.º titular não bloqueia: ou não existe, ou é ele próprio Sub35.
    titular2_ok = {
        "$or": [
            condicao_sem_titular2(),
            *ramos_das_datas([SECCAO_DO_TITULAR2]),
        ]
    }

    return {
        "$or": [
            *({campo: True} for campo in MARCAS_MANUAIS),
            {"$and": [{"$or": ramos_titular1}, titular2_ok]},
        ]
    }


def condicao_de_filtro(
    sub35: Optional[bool], hoje: Optional[date] = None, **kwargs
) -> Optional[dict]:
    """Traduz o parâmetro da listagem numa condição.

    `None` → sem filtro. `True` → só os Sub35.

    **`False` é deliberadamente tratado como "sem filtro".** "Não é
    Sub35" juntaria num só grupo quem tem mais de 35 anos e quem não tem
    data de nascimento na ficha — que é a maioria dos processos antigos.
    Um filtro que responde "estes não são elegíveis" sobre registos
    incompletos afirma o que não sabe.
    """
    if sub35 is not True:
        return None
    return condicao_sub35(hoje, **kwargs)
