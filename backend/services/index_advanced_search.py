"""Pesquisa avançada de metadados do Index (Out 2026) — `GET /api/index/advanced-search`.

O Index precisa de CRUZAR o que a IA extraiu: recibos de um determinado valor, entidades de uma zona,
um tipo de contrato… A pesquisa lê `process_professional_metadata` (um documento por processo, com os
trabalhos) e o directório `employers`, e devolve **um resultado por trabalho** (um emprego), pronto para
alimentar uma futura interface de relatórios.

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **Os filtros valem TODOS para o MESMO trabalho** (`$unwind` antes do `$match`). Um `$elemMatch` por
   campo seria equivalente, mas um `$match` simples sobre os `jobs.*` deixaria «salário ≥ X» casar com
   um emprego e «contrato = efetivo» com outro do mesmo processo — um resultado que nenhum recibo tem.
2. **O salário é um número** — mas está GUARDADO como texto (`Decimal` em JSON). Uma comparação
   `$gte` sobre texto é lexicográfica («900» > «1500»), pelo que se converte (`$convert`, `onError:
   null`) ANTES de comparar. Um valor ilegível fica fora de qualquer intervalo, nunca dentro.
3. **A fronteira é a do PROCESSO** (dono + redes convidadas, `build_tenant_process_condition`): aplica-se
   no `$lookup` aos processos, que é também quem exclui os eliminados. O metadado leva só a rede do dono,
   e filtrar por ela esconderia a quem trabalha um processo partilhado o que a própria equipa indexou.
   Um processo fora do âmbito, eliminado ou inexistente NÃO aparece nem conta no total.
4. **Nada pessoal na resposta**: lista POSITIVA — o processo (id, número), a entidade patronal (NIF,
   nome, localidade), o cargo, o líquido, o contrato e o período. Nunca o nome do cliente.
5. **Texto sem acentos nem maiúsculas** (`regex_sem_acentos`): «joao» encontra «João». O nome da
   entidade consulta também o directório `employers` (a mesma entidade escrita de várias maneiras
   nos recibos), por NIF.
6. **Tectos**: página ≤ 50, `maxTimeMS`, e no máximo `MAXIMO_DE_NIFS_DO_DIRECTORIO` entidades
   resolvidas pelo nome — uma pesquisa por «a» não varre a colecção.
7. Faltar um filtro é «sem filtro»; um intervalo invertido (`min > max`) é 422, nunca «nada».

DUAS VISTAS (Out 2026)
----------------------
* **Sem `document_type`: por EMPREGO** (o que acima se descreve — o último recibo de cada entidade).
* **Com `document_type`: por DOCUMENTO** — `recibo`, `declaracao_efetividade` ou `extrato`. Lê
  `process_index_documents` (uma linha por ficheiro analisado, ver `index_store.projectar_documento`) e serve
  três perguntas que o agregado do emprego não responde: *recibos isolados* de um valor (um recibo antigo de 1.200 €
  não aparece no emprego, cujo líquido é o do recibo mais recente), *declarações de efetividade por região* e
  *extratos por banco*.
8. **Um filtro que não se aplica ao tipo é 422, nunca «nada».** `bank` só existe nos extratos; o salário e o cargo
   só nos recibos; `employer_*` e `contract_type` não existem num extrato. Devolver uma lista vazia diria «não há»
   quando a verdade é «a pergunta não faz sentido» — e ninguém repara numa lista vazia.
9. **Valor exacto = `min_salary == max_salary`.** O líquido está guardado como número e as duas pontas passam
   pelo mesmo `float(Decimal)`, logo a igualdade é exacta (não há `0.1 + 0.2`).
10. **O banco compara-se pela CHAVE** (`index_banks`): «cgd», «caixa geral» e «Caixa Geral de Depósitos, S.A.» são
    o mesmo banco. Um banco fora da tabela pesquisa-se pelo nome.
11. **`document_type=todos` (28/10/2026)** — os três tipos de uma vez. Aí TODOS os filtros se aceitam e cada um só
    casa com os tipos que têm o campo: «entidade X» devolve recibos e declarações dessa entidade (um extrato não
    tem entidade), «banco Y» só extratos, só um período devolve os três. Não é um 422 porque a pergunta faz sentido.
12. **O arquivo histórico diz se tem ficheiro** (`has_file`), nunca a chave S3. Sem ficheiro guardado (importações
    antigas, só com os dados) a linha continua a aparecer, sem «Ver documento».
"""
from __future__ import annotations

import logging
import re
import unicodedata
from decimal import Decimal
from typing import Any, Optional

from fastapi import HTTPException

from models.index_module import TipoDeContrato, nif_e_valido, normalizar_nif
from services import index_store as store
from services.index_banks import chave_do_filtro
from services.index_matrix import nome_normalizado_da_entidade
from services import tenant_network
from services.tenant_network import build_network_scope_condition, build_tenant_process_condition

logger = logging.getLogger(__name__)

TAMANHO_MAXIMO_DA_PAGINA = 50
TEMPO_MAXIMO_MS = 15_000
MAXIMO_DE_NIFS_DO_DIRECTORIO = 50
TAMANHO_MINIMO_DO_TEXTO = 2
MAXIMO_DE_DOCUMENTOS_POR_EMPREGO = 12
ORDENACOES = {
    "period_desc": [("jobs.period", -1), ("net_salary_num", -1), ("process_id", 1)],
    "salary_desc": [("net_salary_num", -1), ("jobs.period", -1), ("process_id", 1)],
    "salary_asc": [("net_salary_num", 1), ("jobs.period", -1), ("process_id", 1)],
}
CONTRATOS_VALIDOS = ("efetivo", "termo_certo", "termo_incerto", "outro")
_PERIODO = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")

# base → classe com as variantes acentuadas (minúsculas; a opção `i` cobre as maiúsculas)
_VARIANTES = {
    "a": "aàáâãäå", "e": "eèéêë", "i": "iìíîï", "o": "oòóôõö", "u": "uùúûü", "c": "cç", "n": "nñ",
}


def regex_sem_acentos(texto: str) -> str:
    """Expressão (para `$regex` + `i`) que encontra `texto` com ou sem acentos, escapado.

    O texto do utilizador NUNCA entra cru: cada carácter é escapado e só as letras com variantes
    acentuadas viram uma classe — um parêntese ou um `.*` na pesquisa não é uma expressão regular.
    """
    base = "".join(
        c for c in unicodedata.normalize("NFD", " ".join(str(texto or "").split()))
        if unicodedata.category(c) != "Mn"
    )
    saida: list[str] = []
    for c in base:
        variantes = _VARIANTES.get(c.lower())
        saida.append(f"[{variantes}]" if variantes else re.escape(c))
    return "".join(saida)


def _texto_valido(valor: Optional[str], nome: str) -> Optional[str]:
    if valor is None:
        return None
    limpo = " ".join(valor.split())
    if not limpo:
        return None
    if len(limpo) < TAMANHO_MINIMO_DO_TEXTO:
        raise HTTPException(status_code=422, detail=f"«{nome}» precisa de pelo menos {TAMANHO_MINIMO_DO_TEXTO} caracteres")
    return limpo


def validar_filtros(
    *,
    min_salary: Optional[Decimal],
    max_salary: Optional[Decimal],
    contract_type: Optional[list[str]],
    employer_nif: Optional[str],
    employer_name: Optional[str],
    employer_location: Optional[str],
    job_title: Optional[str],
    period_from: Optional[str],
    period_to: Optional[str],
    sort: str,
    document_type: Optional[str] = None,
    bank: Optional[str] = None,
) -> dict[str, Any]:
    """Valida e normaliza os filtros. 422 com motivo; nunca um 500 nem «nada» por um intervalo trocado."""
    if document_type is not None and document_type not in TIPOS_DO_PEDIDO:
        raise HTTPException(
            status_code=422,
            detail=f"«document_type» desconhecido (válidos: {', '.join(TIPOS_DO_PEDIDO)})",
        )
    banco = _texto_valido(bank, "bank")
    if min_salary is not None and min_salary < 0 or max_salary is not None and max_salary < 0:
        raise HTTPException(status_code=422, detail="O salário não pode ser negativo")
    if min_salary is not None and max_salary is not None and min_salary > max_salary:
        raise HTTPException(status_code=422, detail="«min_salary» não pode ser superior a «max_salary»")
    for nome, valor in (("period_from", period_from), ("period_to", period_to)):
        if valor is not None and not _PERIODO.match(valor):
            raise HTTPException(status_code=422, detail=f"«{nome}» tem de ser YYYY-MM")
    if period_from and period_to and period_from > period_to:
        raise HTTPException(status_code=422, detail="«period_from» não pode ser posterior a «period_to»")
    contratos = sorted(set(contract_type or []))
    invalidos = [c for c in contratos if c not in CONTRATOS_VALIDOS]
    if invalidos:
        raise HTTPException(
            status_code=422,
            detail=f"«contract_type» desconhecido: {', '.join(invalidos)} (válidos: {', '.join(CONTRATOS_VALIDOS)})",
        )
    if sort not in ORDENACOES:
        raise HTTPException(status_code=422, detail=f"«sort» desconhecido (válidos: {', '.join(ORDENACOES)})")
    nif = None
    if employer_nif is not None and employer_nif.strip():
        nif = normalizar_nif(employer_nif)
        if not nif or len(nif) < 3:
            raise HTTPException(status_code=422, detail="«employer_nif» precisa de pelo menos 3 dígitos")
    filtros = {
        "min_salary": min_salary, "max_salary": max_salary, "contract_type": contratos,
        "employer_nif": nif,
        "employer_name": _texto_valido(employer_name, "employer_name"),
        "employer_location": _texto_valido(employer_location, "employer_location"),
        "job_title": _texto_valido(job_title, "job_title"),
        "period_from": period_from, "period_to": period_to, "sort": sort,
        "document_type": document_type, "bank": banco,
    }
    _exigir_filtros_do_tipo(filtros)
    return filtros


#: «Tudo»: os três tipos de documento de uma vez (regra 11).
DOC_TYPE_TODOS = "todos"
TIPOS_DO_PEDIDO = (*store.DOC_TYPES_PESQUISAVEIS, DOC_TYPE_TODOS)

#: filtro → tipos de documento em que existe. Um filtro fora do seu tipo é 422 (regra 8).
_FILTROS_POR_TIPO: dict[str, tuple[str, ...]] = {
    "min_salary": (store.DOC_TYPE_RECIBO,),
    "max_salary": (store.DOC_TYPE_RECIBO,),
    "job_title": (store.DOC_TYPE_RECIBO, store.DOC_TYPE_DECLARACAO),
    "contract_type": (store.DOC_TYPE_RECIBO, store.DOC_TYPE_DECLARACAO),
    "employer_nif": (store.DOC_TYPE_RECIBO, store.DOC_TYPE_DECLARACAO),
    "employer_name": (store.DOC_TYPE_RECIBO, store.DOC_TYPE_DECLARACAO),
    "employer_location": (store.DOC_TYPE_RECIBO, store.DOC_TYPE_DECLARACAO),
    "bank": (store.DOC_TYPE_EXTRATO,),
}


def _filtro_esta_ligado(filtros: dict[str, Any], nome: str) -> bool:
    return filtros.get(nome) not in (None, [], "")


def _exigir_filtros_do_tipo(filtros: dict[str, Any]) -> None:
    """422 para um filtro que não existe no tipo pedido (ou, sem tipo, para o `bank`, que só vive nos documentos)."""
    tipo = filtros.get("document_type")
    if tipo is None:
        if _filtro_esta_ligado(filtros, "bank"):
            raise HTTPException(status_code=422, detail="«bank» exige «document_type=extrato»")
        return
    if tipo == DOC_TYPE_TODOS:
        return  # cada filtro só casa com os tipos que têm o campo (regra 11)
    for nome, tipos in _FILTROS_POR_TIPO.items():
        if _filtro_esta_ligado(filtros, nome) and tipo not in tipos:
            raise HTTPException(
                status_code=422,
                detail=f"«{nome}» não se aplica a «{tipo}» (aplica-se a: {', '.join(tipos)})",
            )


async def _nifs_do_directorio(nome: str) -> list[str]:
    """NIFs das entidades do directório cujo nome casa — a mesma empresa escrita de várias maneiras."""
    normal = nome_normalizado_da_entidade(nome)
    if len(normal) < TAMANHO_MINIMO_DO_TEXTO:  # a normalização tira a pontuação: vazio casaria com TUDO
        return []
    try:
        nifs = await store.nifs_das_entidades_pelo_nome(normal, MAXIMO_DE_NIFS_DO_DIRECTORIO)
    except Exception as exc:  # noqa: BLE001 — o directório é um reforço: sem ele, vale o nome do recibo
        logger.warning("[INDEX-SEARCH] Directório de entidades indisponível: %s", type(exc).__name__)
        return []
    return [n for n in nifs if nif_e_valido(n)]


def _condicoes_do_trabalho(filtros: dict[str, Any], nifs_do_nome: list[str]) -> list[dict]:
    """O `$match` sobre o trabalho (já com `$unwind`). Puro."""
    condicoes: list[dict] = []
    if filtros["min_salary"] is not None or filtros["max_salary"] is not None:
        intervalo: dict[str, Any] = {"$ne": None}
        if filtros["min_salary"] is not None:
            intervalo["$gte"] = float(filtros["min_salary"])
        if filtros["max_salary"] is not None:
            intervalo["$lte"] = float(filtros["max_salary"])
        condicoes.append({"net_salary_num": intervalo})
    if filtros["contract_type"]:
        condicoes.append({"jobs.contract_type.value": {"$in": filtros["contract_type"]}})
    if filtros["employer_nif"]:
        condicoes.append({"jobs.employer_nif.value": {"$regex": f"^{re.escape(filtros['employer_nif'])}"}})
    if filtros["employer_name"]:
        por_nome = {"jobs.employer_name.value": {"$regex": regex_sem_acentos(filtros["employer_name"]), "$options": "i"}}
        condicoes.append({"$or": [por_nome, {"jobs.employer_nif.value": {"$in": nifs_do_nome}}]} if nifs_do_nome else por_nome)
    if filtros["employer_location"]:
        condicoes.append({"jobs.employer_location": {"$regex": regex_sem_acentos(filtros["employer_location"]), "$options": "i"}})
    if filtros["job_title"]:
        condicoes.append({"jobs.job_title.value": {"$regex": regex_sem_acentos(filtros["job_title"]), "$options": "i"}})
    if filtros["period_from"]:
        condicoes.append({"jobs.period": {"$gte": filtros["period_from"]}})
    if filtros["period_to"]:
        condicoes.append({"jobs.period": {"$lte": filtros["period_to"], "$ne": None}})
    return condicoes


def construir_pipeline(
    filtros: dict[str, Any], nifs_do_nome: list[str], condicao_de_processos: dict, *, pagina: int, tamanho: int
) -> list[dict]:
    """O pipeline completo. Pura: não toca na base de dados (testável sem Mongo)."""
    condicoes = _condicoes_do_trabalho(filtros, nifs_do_nome)
    return [
        {"$unwind": "$jobs"},
        # o salário está guardado como TEXTO: converte-se antes de comparar (regra 2)
        {"$addFields": {"net_salary_num": {"$convert": {
            "input": "$jobs.net_salary.value", "to": "double", "onError": None, "onNull": None}}}},
        *([{"$match": {"$and": condicoes}}] if condicoes else []),
        # a fronteira: só processos do âmbito e não eliminados (regra 3)
        {"$lookup": {
            "from": "processes", "localField": "process_id", "foreignField": "id", "as": "proc",
            "pipeline": [
                {"$match": {"$and": [{"is_deleted": {"$ne": True}}, condicao_de_processos]}},
                {"$project": {"_id": 0, "id": 1, "process_number": 1, "status": 1, "company_name": 1}},
            ],
        }},
        {"$match": {"proc.0": {"$exists": True}}},
        {"$facet": {
            "items": [
                {"$sort": dict(ORDENACOES[filtros["sort"]])},
                {"$skip": (pagina - 1) * tamanho},
                {"$limit": tamanho},
                {"$project": {
                    "_id": 0, "process_id": 1, "net_salary_num": 1, "jobs": 1,
                    "proc": {"$arrayElemAt": ["$proc", 0]},
                }},
            ],
            "total": [{"$count": "n"}],
        }},
    ]


# ====================================================================
# A VISTA POR DOCUMENTO
# ====================================================================
ORDENACOES_DE_DOCUMENTOS = {
    "period_desc": [("period", -1), ("net_salary_num", -1), ("id", 1)],
    "salary_desc": [("net_salary_num", -1), ("period", -1), ("id", 1)],
    "salary_asc": [("net_salary_num", 1), ("period", -1), ("id", 1)],
}


def _condicoes_do_documento(filtros: dict[str, Any], nifs_do_nome: list[str]) -> list[dict]:
    """O `$match` sobre a projecção por documento. Puro. Começa SEMPRE pelo tipo (os índices são por tipo)."""
    tipo = filtros["document_type"]
    condicoes: list[dict] = [
        {"doc_type": {"$in": list(store.DOC_TYPES_PESQUISAVEIS)}} if tipo == DOC_TYPE_TODOS else {"doc_type": tipo}
    ]
    if filtros["min_salary"] is not None or filtros["max_salary"] is not None:
        intervalo: dict[str, Any] = {"$ne": None}
        if filtros["min_salary"] is not None:
            intervalo["$gte"] = float(filtros["min_salary"])
        if filtros["max_salary"] is not None:
            intervalo["$lte"] = float(filtros["max_salary"])
        condicoes.append({"net_salary_num": intervalo})
    if filtros["contract_type"]:
        condicoes.append({"contract_type": {"$in": filtros["contract_type"]}})
    if filtros["employer_nif"]:
        condicoes.append({"employer_nif": {"$regex": f"^{re.escape(filtros['employer_nif'])}"}})
    if filtros["employer_name"]:
        por_nome = {"employer_name": {"$regex": regex_sem_acentos(filtros["employer_name"]), "$options": "i"}}
        condicoes.append({"$or": [por_nome, {"employer_nif": {"$in": nifs_do_nome}}]} if nifs_do_nome else por_nome)
    if filtros["employer_location"]:
        condicoes.append({"employer_location": {"$regex": regex_sem_acentos(filtros["employer_location"]), "$options": "i"}})
    if filtros["job_title"]:
        condicoes.append({"job_title": {"$regex": regex_sem_acentos(filtros["job_title"]), "$options": "i"}})
    if filtros["bank"]:
        chave = chave_do_filtro(filtros["bank"])
        por_nome = {"bank": {"$regex": regex_sem_acentos(filtros["bank"]), "$options": "i"}}
        # um banco da tabela compara-se pela chave (cgd = caixa geral = Caixa Geral de Depósitos, S.A.)
        condicoes.append({"$or": [{"bank_key": chave}, por_nome]} if chave else por_nome)
    if filtros["period_from"]:
        condicoes.append({"period": {"$gte": filtros["period_from"]}})
    if filtros["period_to"]:
        condicoes.append({"period": {"$lte": filtros["period_to"], "$ne": None}})
    return condicoes


def construir_pipeline_de_documentos(
    filtros: dict[str, Any], nifs_do_nome: list[str], condicao_de_processos: dict, *, pagina: int, tamanho: int,
    condicao_dos_historicos: Optional[dict] = None,
) -> list[dict]:
    """O pipeline da vista por documento. Pura. O `$match` vem antes do `$lookup`: filtra-se barato primeiro.

    `condicao_dos_historicos` é a fronteira das linhas do ARQUIVO HISTÓRICO (importação de ZIPs): não têm processo,
    logo o `$lookup` nunca as encontra e seriam descartadas; entram pelo ramo `historical` — que exige a marca E a
    rede do âmbito de quem pergunta. Sem ela (omissão) o arquivo não aparece: **falha fechada**.
    """
    so_com_processo = {"proc.0": {"$exists": True}}
    return [
        {"$match": {"$and": _condicoes_do_documento(filtros, nifs_do_nome)}},
        # a fronteira: só processos do âmbito e não eliminados (regra 3)
        {"$lookup": {
            "from": "processes", "localField": "process_id", "foreignField": "id", "as": "proc",
            "pipeline": [
                {"$match": {"$and": [{"is_deleted": {"$ne": True}}, condicao_de_processos]}},
                {"$project": {"_id": 0, "id": 1, "process_number": 1, "status": 1, "company_name": 1}},
            ],
        }},
        {"$match": {"$or": [so_com_processo, condicao_dos_historicos]} if condicao_dos_historicos else so_com_processo},
        {"$facet": {
            "items": [
                {"$sort": dict(ORDENACOES_DE_DOCUMENTOS[filtros["sort"]])},
                {"$skip": (pagina - 1) * tamanho},
                {"$limit": tamanho},
                {"$project": {"_id": 0, "proc": {"$arrayElemAt": ["$proc", 0]}, **{c: 1 for c in _CAMPOS_DO_DOCUMENTO}}},
            ],
            "total": [{"$count": "n"}],
        }},
    ]


_CAMPOS_DO_DOCUMENTO = (
    "id", "process_id", "doc_type", "period", "net_salary_num", "employer_nif", "employer_name",
    "employer_location", "job_title", "contract_type", "admission_date", "bank", "needs_review",
    "historical", "import_label", "s3_path",
)


def resultado_do_documento(doc: dict) -> dict[str, Any]:
    """O DTO de UM documento: lista positiva (regra 4). Só o que o TIPO tem — o resto nem aparece."""
    proc = doc.get("proc") or {}
    tipo = doc.get("doc_type")
    historico = doc.get("historical") is True
    saida: dict[str, Any] = {
        "document_id": doc.get("id"),
        "document_type": tipo,
        # o arquivo histórico não tem processo (o id artificial não leva a lado nenhum) nem ficheiro para abrir
        "process_id": None if historico else doc.get("process_id"),
        "process_number": proc.get("process_number"),
        "company_name": proc.get("company_name"),
        "period": doc.get("period"),
        "needs_review": bool(doc.get("needs_review")),
        "historical": historico,
    }
    if historico:
        saida["import_label"] = doc.get("import_label")
        # se o ficheiro foi guardado na importação (regra 12) — a chave nunca sai
        saida["has_file"] = isinstance(doc.get("s3_path"), str) and bool(doc.get("s3_path"))
    if tipo == store.DOC_TYPE_EXTRATO:
        saida["bank"] = doc.get("bank")
        return saida
    saida["employer"] = {"nif": doc.get("employer_nif"), "name": doc.get("employer_name"),
                         "location": doc.get("employer_location")}
    saida["job_title"] = doc.get("job_title")
    saida["contract_type"] = doc.get("contract_type")
    if tipo == store.DOC_TYPE_RECIBO:
        saida["net_salary"] = _numero(doc.get("net_salary_num"))
    else:
        saida["admission_date"] = doc.get("admission_date")
    return saida


def _numero(valor: Any) -> Optional[float]:
    return float(valor) if isinstance(valor, (int, float)) and not isinstance(valor, bool) else None


def resultado_do_trabalho(doc: dict) -> dict[str, Any]:
    """O DTO de UM resultado: lista positiva (regra 4)."""
    job = doc.get("jobs") or {}
    proc = doc.get("proc") or {}

    def valor(campo: str) -> Any:
        return (job.get(campo) or {}).get("value")

    return {
        "process_id": doc.get("process_id"),
        "process_number": proc.get("process_number"),
        "company_name": proc.get("company_name"),
        "job_id": job.get("job_id"),
        "employer": {
            "nif": valor("employer_nif"),
            "name": valor("employer_name"),
            "location": job.get("employer_location"),
        },
        "job_title": valor("job_title"),
        "net_salary": _numero(doc.get("net_salary_num")),
        "contract_type": valor("contract_type"),
        "period": job.get("period"),
        "needs_review": any(
            (job.get(c) or {}).get("needs_review")
            for c in ("employer_nif", "employer_name", "job_title", "net_salary", "contract_type")
        ),
        "admission_date": job.get("admission_date"),
        "certified_by_declaration": bool(job.get("certified_by_declaration")),
        "source_documents": len(job.get("source_document_ids") or []),
        # a referência exacta dos documentos que sustentam este emprego («Ver documento» na pesquisa)
        "document_ids": [d for d in (job.get("source_document_ids") or []) if isinstance(d, str)][:MAXIMO_DE_DOCUMENTOS_POR_EMPREGO],
    }


async def _condicao_dos_historicos(user: dict) -> dict:
    """A fronteira do arquivo histórico: a marca E a rede no âmbito de quem pergunta (o Master vê todas).

    Deriva do MESMO construtor das outras superfícies (`build_network_scope_condition`). **Falha fechada**: se o
    âmbito não se resolve, o arquivo não aparece (a pesquisa por processos já falhou alto, e o arquivo é um reforço).
    """
    try:
        scope = await tenant_network.resolve_vista_scope(user)
        return {"$and": [{"historical": True}, build_network_scope_condition(scope)]}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX-SEARCH] Âmbito do arquivo histórico não resolvido (%s): sem arquivo.", type(exc).__name__)
        return {"id": {"$in": []}}


async def run_advanced_search(
    user: dict,
    *,
    min_salary: Optional[Decimal] = None,
    max_salary: Optional[Decimal] = None,
    contract_type: Optional[list[str]] = None,
    employer_nif: Optional[str] = None,
    employer_name: Optional[str] = None,
    employer_location: Optional[str] = None,
    job_title: Optional[str] = None,
    period_from: Optional[str] = None,
    period_to: Optional[str] = None,
    sort: str = "period_desc",
    page: int = 1,
    size: int = 25,
    document_type: Optional[str] = None,
    bank: Optional[str] = None,
) -> dict[str, Any]:
    filtros = validar_filtros(
        min_salary=min_salary, max_salary=max_salary, contract_type=contract_type,
        employer_nif=employer_nif, employer_name=employer_name, employer_location=employer_location,
        job_title=job_title, period_from=period_from, period_to=period_to, sort=sort,
        document_type=document_type, bank=bank,
    )
    por_documento = filtros["document_type"] is not None
    pagina = max(1, page)
    tamanho = max(1, min(size, TAMANHO_MAXIMO_DA_PAGINA))
    nifs = await _nifs_do_directorio(filtros["employer_name"]) if filtros["employer_name"] else []
    # a condição de processos FALHA FECHADA: se não se calcula, a excepção sobe (nunca «sem filtro»)
    condicao = await build_tenant_process_condition(user)
    try:
        if por_documento:
            historicos = await _condicao_dos_historicos(user)
            pipeline = construir_pipeline_de_documentos(
                filtros, nifs, condicao, pagina=pagina, tamanho=tamanho, condicao_dos_historicos=historicos,
            )
            saida = await store.agregar_documentos_do_index(pipeline, tempo_maximo_ms=TEMPO_MAXIMO_MS)
        else:
            pipeline = construir_pipeline(filtros, nifs, condicao, pagina=pagina, tamanho=tamanho)
            saida = await store.agregar_metadados_profissionais(pipeline, tempo_maximo_ms=TEMPO_MAXIMO_MS)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX-SEARCH] Pesquisa falhou: %s: %s", type(exc).__name__, exc)
        raise HTTPException(status_code=503, detail="A pesquisa não terminou a tempo. Estreite os filtros e tente de novo.")
    bloco = (saida or [{}])[0]
    total = ((bloco.get("total") or [{}])[0]).get("n", 0)
    montar = resultado_do_documento if por_documento else resultado_do_trabalho
    return {
        "view": "documents" if por_documento else "jobs",
        "items": [montar(d) for d in bloco.get("items") or []],
        "total": total,
        "page": pagina,
        "size": tamanho,
        "filters": {k: (str(v) if isinstance(v, Decimal) else v) for k, v in filtros.items() if v not in (None, [], "")},
    }


__all__ = ["DOC_TYPE_TODOS", "run_advanced_search", "validar_filtros", "construir_pipeline", "construir_pipeline_de_documentos",
           "regex_sem_acentos"]
