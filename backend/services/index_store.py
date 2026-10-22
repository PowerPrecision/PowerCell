"""Persistência do módulo Index (Lote 12, Fase 2): metadados profissionais, entidades, alertas, ficheiros.

QUATRO COLECÇÕES, QUATRO REGRAS
===============================
* `process_professional_metadata` — UM documento por processo. É **recalculado**
  a partir do que cada recibo guardou (`document_metadata.index_job`), nunca
  acumulado às cegas: assim uma reanálise é idempotente e um recibo apagado
  deixa de contar. O que uma PESSOA escreveu (`edited_by_human`) sobrevive
  sempre à reanálise — a IA propõe, a pessoa dispõe.
* `employers` — directório GLOBAL (sem dados de clientes). Só entra uma entidade
  com NIF válido, nome, e **sem dúvida** (`needs_review` falso, ou confirmada por
  uma pessoa): um NIF mal lido, mas com dígito de controlo válido por azar, não
  pode poluir o que todos os Index vão pesquisar. O primeiro nome ganha: um
  recibo não renomeia uma entidade.
* `process_index_alerts` — um documento por alerta. Um alerta **dispensado** por
  uma pessoa não ressuscita quando a matriz volta a correr (a assinatura `key`
  é estável); um que deixou de ser verdade desaparece.
* `document_metadata` — o estado de cada ficheiro (impressão digital, factos,
  categoria). Nada pessoal: factos numéricos e o subtipo da identificação.

Nada aqui levanta por causa de dados maus: gravar é observar. As funções que
escrevem devolvem o que escreveram, para o job registar.
"""
from __future__ import annotations

import hashlib
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Iterable, Optional

from database import db
from models.index_module import (
    ALERTAS,
    CATEGORIA_IDENTIFICACAO,
    AlertaDaMatriz,
    CampoRevisavel,
    FonteDoCampo,
    ProfessionalMetadata,
    TrabalhoProfissional,
    decimal_do_valor,
    nif_e_valido,
    normalizar_nif,
)
from services.index_ai import (
    CATEGORIA_DO_TIPO,
    SUBTIPO_DA_DECLARACAO,
    TIPO_DECLARACAO,
    TIPO_EXTRATO,
    TIPO_IDENTIFICACAO,
    TIPO_RECIBO,
    ResultadoDaAnalise,
)
from services.index_matrix import nome_normalizado_da_entidade

logger = logging.getLogger(__name__)

CAMPOS_DO_TRABALHO = ("employer_nif", "employer_name", "job_title", "net_salary", "contract_type")

SUBCATEGORIAS = {
    TIPO_RECIBO: "Recibo de Vencimento",
    TIPO_EXTRATO: "Extrato Bancário",
    TIPO_DECLARACAO: "Declaração de Efetividade",
    "cc": "Cartão de Cidadão",
    "bi": "Bilhete de Identidade",
    "passaporte": "Passaporte",
    "titulo_residencia": "Título de Residência",
    TIPO_IDENTIFICACAO: "Identificação",
}


def _agora() -> datetime:
    return datetime.now(timezone.utc)


# ====================================================================
# TRABALHOS (puro)
# ====================================================================
def chave_do_trabalho(job: TrabalhoProfissional, document_id: Optional[str]) -> str:
    """NIF válido → nome normalizado → o próprio documento. Duas faturas da mesma empresa são UM trabalho."""
    nif = normalizar_nif(job.employer_nif.value)
    if nif and nif_e_valido(nif):
        return f"nif:{nif}"
    nome = nome_normalizado_da_entidade(job.employer_name.value)
    if nome:
        return f"nome:{nome}"
    return f"doc:{document_id or uuid.uuid4().hex}"


def job_id_da_chave(chave: str) -> str:
    return "job_" + hashlib.sha1(chave.encode(), usedforsecurity=False).hexdigest()[:12]  # identificador estável, não é segurança


def _mais_recente(a: Optional[str], b: Optional[str]) -> bool:
    """`True` se o período `a` é mais recente que `b` (sem período = o mais antigo)."""
    return (a or "") > (b or "")


def _chaves_da_entidade(nif: Any, nome: Any) -> set[str]:
    """As identidades por que uma entidade se reconhece: `nif:<válido>` e `nome:<normalizado>`."""
    chaves: set[str] = set()
    normal = normalizar_nif(nif)
    if normal and nif_e_valido(normal):
        chaves.add(f"nif:{normal}")
    nome_normal = nome_normalizado_da_entidade(nome)
    if nome_normal:
        chaves.add(f"nome:{nome_normal}")
    return chaves


def _declaracao_e_desta_entidade(declaracao: dict, membros: list[tuple[str, TrabalhoProfissional]]) -> bool:
    """A declaração é da entidade deste grupo? NIF válido primeiro; o nome só quando o NIF não discorda.

    Dois NIFs válidos DIFERENTES são duas entidades, mesmo que o nome coincida (uma sucursal, um grupo
    com a mesma designação): a identidade forte vence a fraca, senão uma declaração mandava no emprego errado.
    """
    nifs_da_declaracao = {c for c in _chaves_da_entidade(declaracao.get("employer_nif"), None)}
    nifs_do_grupo: set[str] = set()
    nomes_do_grupo: set[str] = set()
    for _, job in membros:
        for chave in _chaves_da_entidade(job.employer_nif.value, job.employer_name.value):
            (nifs_do_grupo if chave.startswith("nif:") else nomes_do_grupo).add(chave)
    if nifs_da_declaracao & nifs_do_grupo:
        return True
    if nifs_da_declaracao and nifs_do_grupo:
        return False  # os dois têm NIF e não é o mesmo
    nomes_da_declaracao = {c for c in _chaves_da_entidade(None, declaracao.get("employer_name"))}
    return bool(nomes_da_declaracao & nomes_do_grupo)


def aplicar_declaracoes(
    job: TrabalhoProfissional,
    membros: list[tuple[str, TrabalhoProfissional]],
    declaracoes: list[tuple[str, dict]],
) -> TrabalhoProfissional:
    """A Declaração de Efetividade tem PRECEDÊNCIA ABSOLUTA sobre os recibos (decisão da direcção, Out 2026).

    O tipo de contrato e a data de admissão que ela certifica sobrepõem-se a tudo o que se leu ou inferiu
    dos recibos. Regras que não se podem perder:

    * **só o que a declaração DIZ**: um campo que ela não traz (nulo) não apaga o dos recibos;
    * **a mais recente ganha** (período de emissão; sem data é a mais antiga; desempate pelo id);
    * **uma leitura com confiança «baixa» entra, mas a rever** (`needs_review`): vence os recibos e pede
      uma pessoa; a **admissão** não tem editor, logo uma leitura duvidosa dela não se propaga;
    * **uma pessoa vence tudo**: `aplicar_edicoes_humanas` corre depois e repõe o que ela escreveu.
    """
    candidatas = [(d, f) for d, f in declaracoes if _declaracao_e_desta_entidade(f, membros)]
    if not candidatas:
        return job
    documento, factos = max(candidatas, key=lambda par: (par[1].get("period") or "", par[0] or ""))
    certificou = False

    contrato = factos.get("contract_type")
    if contrato:
        confianca = factos.get("contract_confidence")
        job.contract_type = CampoRevisavel(
            value=contrato, needs_review=(confianca == "baixa"), confidence=confianca,
            source=FonteDoCampo(document_id=documento),
        )
        certificou = True
    if factos.get("admission_date") and factos.get("admission_confidence") != "baixa":
        job.admission_date = factos["admission_date"]
        certificou = True
    if certificou:
        job.certified_by_declaration = True
        if documento and documento not in job.source_document_ids:
            job.source_document_ids = sorted({*job.source_document_ids, documento})
    return job


def calcular_trabalhos(
    entradas: Iterable[tuple[str, TrabalhoProfissional]],
    declaracoes: Iterable[tuple[str, dict]] = (),
) -> list[TrabalhoProfissional]:
    """Agrupa os recibos por entidade. Em cada campo ganha o recibo MAIS RECENTE que o tem.

    Um salário muda ao longo do tempo (o último recibo é o que conta); um campo
    que o recibo mais recente não trouxe (cargo em falta) vem do anterior em
    vez de ficar vazio. Determinístico: não depende da ordem de entrada.

    As `declaracoes` (`(document_id, index_facts)`) de efetividade mandam no tipo de contrato e na
    admissão (`aplicar_declaracoes`); só enriquecem empregos que já existem por recibos — uma declaração
    sozinha não cria um emprego sem salário (continua pesquisável por documento).
    """
    declaracoes = list(declaracoes)
    grupos: dict[str, list[tuple[str, TrabalhoProfissional]]] = {}
    for document_id, job in entradas:
        grupos.setdefault(chave_do_trabalho(job, document_id), []).append((document_id, job))

    resultado: list[TrabalhoProfissional] = []
    for chave in sorted(grupos):
        # mais recente primeiro; desempate pelo id do documento (ordem estável)
        membros = sorted(grupos[chave], key=lambda m: (m[1].period or "", m[0] or ""), reverse=True)
        campos: dict[str, CampoRevisavel] = {}
        for nome in CAMPOS_DO_TRABALHO:
            escolhido = next((getattr(j, nome) for _, j in membros if getattr(j, nome).value is not None), None)
            campos[nome] = (escolhido or getattr(membros[0][1], nome)).model_copy(deep=True)
        job = TrabalhoProfissional(
            job_id=job_id_da_chave(chave),
            period=membros[0][1].period,
            # a localidade vem do recibo mais recente que a tem (como os restantes campos)
            employer_location=next((j.employer_location for _, j in membros if j.employer_location), None),
            source_document_ids=sorted({d for d, _ in grupos[chave] if d}),
            **campos,
        )
        resultado.append(aplicar_declaracoes(job, membros, declaracoes))
    return resultado


def aplicar_edicoes_humanas(
    existentes: list[dict], calculados: list[TrabalhoProfissional]
) -> list[TrabalhoProfissional]:
    """Os campos que uma pessoa escreveu (`edited_by_human`) sobrevivem à reanálise.

    O trabalho calculado casa com o existente pelo `job_id` OU por documentos de
    origem em comum — se a pessoa corrigiu o NIF, a chave de agrupamento muda,
    mas os recibos são os mesmos e o `job_id` antigo (e a edição) mantêm-se.
    Um trabalho que só existe porque uma pessoa o editou e já não tem documentos
    de origem desaparece: um recibo apagado deixa de contar.
    """
    resultado: list[TrabalhoProfissional] = []
    usados: set[int] = set()
    for novo in calculados:
        origem = set(novo.source_document_ids)
        alvo: Optional[int] = None
        for i, velho in enumerate(existentes):
            if i in usados:
                continue
            if velho.get("job_id") == novo.job_id or origem & set(velho.get("source_document_ids") or []):
                alvo = i
                break
        if alvo is None:
            resultado.append(novo)
            continue
        usados.add(alvo)
        velho = existentes[alvo]
        for nome in CAMPOS_DO_TRABALHO:
            campo_velho = velho.get(nome) or {}
            if campo_velho.get("edited_by_human"):
                setattr(novo, nome, CampoRevisavel.model_validate(campo_velho))
        if (velho.get("contract_type") or {}).get("edited_by_human"):
            # o contrato é agora o que uma pessoa escreveu, já não o da declaração (a admissão continua dela)
            novo.certified_by_declaration = bool(novo.admission_date)
        novo.job_id = velho.get("job_id") or novo.job_id
        # o código reforça mesmo o que uma pessoa escreveu (NIF sem dígito de controlo)
        resultado.append(TrabalhoProfissional.model_validate(novo.model_dump(mode="json")))
    return resultado


# ====================================================================
# METADADOS PROFISSIONAIS
# ====================================================================
async def carregar_metadados(process_id: str) -> Optional[dict]:
    return await db.process_professional_metadata.find_one({"process_id": process_id}, {"_id": 0})


async def gravar_metadados(
    process_id: str,
    network_id: Optional[str],
    trabalhos: list[TrabalhoProfissional],
    impressao: Optional[str],
) -> ProfessionalMetadata:
    """Substitui os trabalhos do processo (já com as edições humanas aplicadas)."""
    modelo = ProfessionalMetadata(
        process_id=process_id,
        network_id=network_id,
        jobs=trabalhos,
        analysis_fingerprint=impressao,
        updated_at=_agora(),
    )
    documento = modelo.model_dump(mode="json")
    documento["updated_at"] = modelo.updated_at
    await db.process_professional_metadata.update_one(
        {"process_id": process_id}, {"$set": documento}, upsert=True
    )
    return modelo


async def recalcular_metadados(process_id: str, network_id: Optional[str], impressao: Optional[str]) -> ProfessionalMetadata:
    """Recalcula os trabalhos a partir dos recibos que o processo TEM e grava."""
    entradas: list[tuple[str, TrabalhoProfissional]] = []
    cursor = db.document_metadata.find(
        # um original eliminado (`purgado`) continua a contar: os dados lidos dele não deixaram de ser verdade
        {"process_id": process_id, "is_clean_pdf": {"$ne": True}, "index_job": {"$exists": True, "$ne": None}},
        {"_id": 0, "id": 1, "index_job": 1},
    )
    for doc in await cursor.to_list(500):
        try:
            entradas.append((doc.get("id"), TrabalhoProfissional.model_validate(doc["index_job"])))
        except Exception as exc:  # noqa: BLE001 — um documento mal gravado não derruba os outros
            logger.warning("[INDEX] index_job ilegível em %s: %s", doc.get("id"), type(exc).__name__)
    declaracoes = await _declaracoes_do_processo(process_id)
    existente = await carregar_metadados(process_id)
    trabalhos = aplicar_edicoes_humanas(
        (existente or {}).get("jobs") or [], calcular_trabalhos(entradas, declaracoes)
    )
    return await gravar_metadados(process_id, network_id, trabalhos, impressao)


async def _declaracoes_do_processo(process_id: str) -> list[tuple[str, dict]]:
    """`(document_id, factos)` das declarações de efetividade analisadas do processo.

    Um original `purgado` conta (os DADOS não deixaram de ser verdade); o PDF limpo não (os factos
    vivem nos originais). Uma falha a ler NÃO derruba o recalcular: sem declarações o emprego fica como
    os recibos o dizem — e di-lo o log.
    """
    try:
        docs = await db.document_metadata.find(
            {"process_id": process_id, "is_clean_pdf": {"$ne": True}, "index_facts.tipo": TIPO_DECLARACAO},
            {"_id": 0, "id": 1, "index_facts": 1},
        ).to_list(100)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Declarações do processo %s não lidas: %s", process_id, type(exc).__name__)
        return []
    return [(d["id"], d["index_facts"]) for d in docs if d.get("id") and isinstance(d.get("index_facts"), dict)]


# ====================================================================
# ENTIDADES PATRONAIS
# ====================================================================
def entidades_a_registar(trabalhos: list[TrabalhoProfissional]) -> list[tuple[str, str]]:
    """`(nif, nome)` das entidades que podem entrar no directório global.

    NIF com dígito de controlo válido, nome presente, e sem dúvida: o campo do NIF
    não está a rever, OU uma pessoa o escreveu (`edited_by_human`).
    """
    saida: list[tuple[str, str]] = []
    for t in trabalhos:
        nif = normalizar_nif(t.employer_nif.value)
        nome = " ".join(str(t.employer_name.value or "").split())
        if not nif or not nif_e_valido(nif) or not nome:
            continue
        nif_certo = t.employer_nif.edited_by_human or not t.employer_nif.needs_review
        nome_certo = t.employer_name.edited_by_human or not t.employer_name.needs_review
        if nif_certo and nome_certo:
            saida.append((nif, nome))
    return saida


async def registar_entidades(trabalhos: list[TrabalhoProfissional], extra: Iterable[tuple[str, str]] = ()) -> int:
    """Upsert no directório; o primeiro nome ganha. Devolve quantas entidades NOVAS.

    `extra` são pares `(nif, nome)` já validados de outras fontes (as declarações de efetividade).
    """
    novas = 0
    vistos: set[str] = set()
    for nif, nome in [*entidades_a_registar(trabalhos), *extra]:
        if nif in vistos:
            continue
        vistos.add(nif)
        try:
            resultado = await db.employers.update_one(
                {"nif": nif},
                {"$setOnInsert": {
                    "nif": nif, "name": nome, "name_normalizado": nome_normalizado_da_entidade(nome),
                    "first_seen_at": _agora(),
                }},
                upsert=True,
            )
            novas += int(resultado.matched_count == 0)  # upsert que INSERIU: nada casou
        except Exception as exc:  # noqa: BLE001 — o directório é conveniência
            logger.warning("[INDEX] Entidade %s não registada: %s", nif, type(exc).__name__)
    return novas


async def entidades_conhecidas(nomes: Iterable[str]) -> dict[str, str]:
    """`{nome_normalizado: nif}` das entidades já conhecidas com estes nomes."""
    normais = sorted({nome_normalizado_da_entidade(n) for n in nomes if n} - {""})
    if not normais:
        return {}
    try:
        docs = await db.employers.find(
            {"name_normalizado": {"$in": normais}}, {"_id": 0, "nif": 1, "name_normalizado": 1}
        ).to_list(500)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Directório de entidades indisponível: %s", type(exc).__name__)
        return {}
    return {d["name_normalizado"]: d["nif"] for d in docs}


# ====================================================================
# ALERTAS
# ====================================================================
def chave_do_alerta(achado: dict) -> str:
    base = "|".join([
        achado["code"],
        ",".join(sorted(str(r.get("document_id")) for r in achado.get("refs") or [])),
        str(achado.get("periodo") or ""),
    ])
    return hashlib.sha1(base.encode(), usedforsecurity=False).hexdigest()[:16]  # assinatura estável, não é segurança


async def substituir_alertas(
    process_id: str, network_id: Optional[str], run_id: str, achados: list[dict]
) -> dict[str, int]:
    """Troca os alertas do processo pelos desta corrida, preservando os DISPENSADOS.

    * achado cuja assinatura já está dispensada → fica como está (não ressuscita);
    * achado novo → insere;
    * alerta antigo que já não é achado → desaparece (a condição deixou de existir).
    Devolve `{"abertos", "dispensados", "inseridos"}`; `abertos` é o contador do processo.
    """
    existentes = await db.process_index_alerts.find({"process_id": process_id}, {"_id": 0}).to_list(500)
    dispensados = {a["key"] for a in existentes if a.get("dismissed_by_human") and a.get("key")}
    produzidos = {chave_do_alerta(a) for a in achados}

    # o que já não é verdade (ou estava aberto) sai; os dispensados que ainda valem ficam
    for antigo in existentes:
        if antigo.get("dismissed_by_human") and antigo.get("key") in produzidos:
            continue
        await db.process_index_alerts.delete_one({"id": antigo["id"]})

    inseridos = 0
    for achado in achados:
        chave = chave_do_alerta(achado)
        if chave in dispensados:
            continue
        alerta = AlertaDaMatriz(
            id=str(uuid.uuid4()), process_id=process_id, network_id=network_id, code=achado["code"],
            refs=achado.get("refs") or [], run_id=run_id, key=chave, detail=achado.get("detalhe"),
        )
        documento = alerta.model_dump(mode="json")
        documento["created_at"] = _agora()
        documento["periodo"] = achado.get("periodo")
        await db.process_index_alerts.insert_one(documento)
        inseridos += 1
    return {"abertos": inseridos, "dispensados": len(dispensados & produzidos), "inseridos": inseridos}


async def acrescentar_alerta(process_id: str, network_id: Optional[str], achado: dict) -> bool:
    """Acrescenta UM alerta sem tocar nos outros (a matriz, que SUBSTITUI, não é o único emissor).

    Idempotente pela assinatura: se já existe (aberto OU dispensado) não se repete — um alerta
    dispensado não ressuscita. Devolve `True` se inseriu.
    """
    chave = chave_do_alerta(achado)
    if await db.process_index_alerts.find_one({"process_id": process_id, "key": chave}, {"_id": 0, "id": 1}):
        return False
    alerta = AlertaDaMatriz(
        id=str(uuid.uuid4()), process_id=process_id, network_id=network_id, code=achado["code"],
        refs=achado.get("refs") or [], run_id="avulso", key=chave, detail=achado.get("detalhe"),
    )
    documento = alerta.model_dump(mode="json")
    documento["created_at"] = _agora()
    documento["periodo"] = achado.get("periodo")
    await db.process_index_alerts.insert_one(documento)
    return True


async def contar_alertas_abertos(process_id: str) -> int:
    return await db.process_index_alerts.count_documents(
        {"process_id": process_id, "dismissed_by_human": {"$ne": True}}
    )


# ====================================================================
# O FICHEIRO
# ====================================================================
def campos_do_ficheiro(resultado: ResultadoDaAnalise, impressao: str) -> dict[str, Any]:
    """`$set` de `document_metadata` depois de uma análise bem sucedida. Nada pessoal."""
    sub = resultado.subtype if resultado.tipo == TIPO_IDENTIFICACAO else None
    if resultado.tipo == TIPO_DECLARACAO:
        # o subtipo pesquisável da declaração; a identificação mantém o seu (cc, bi…) e a categoria dela
        subtipo_gravado = SUBTIPO_DA_DECLARACAO
    else:
        subtipo_gravado = sub
    campos: dict[str, Any] = {
        "analysis_fingerprint": impressao,
        "ai_category": CATEGORIA_DO_TIPO[resultado.tipo],
        "ai_subcategory": SUBCATEGORIAS.get(sub or resultado.tipo),
        "ai_subtype": subtipo_gravado,
        "index_facts": resultado.factos,
        "index_job": resultado.job.model_dump(mode="json") if resultado.job is not None else None,
        "index_analyzed_at": _agora().isoformat(),
        "index_model": resultado.modelo,
        "index_origin": resultado.origem,
        "is_categorized": True,
        "updated_at": _agora().isoformat(),
    }
    if sub is not None:
        campos["ai_category"] = CATEGORIA_IDENTIFICACAO
    return campos


async def registar_ficheiro(document_id: str, resultado: ResultadoDaAnalise, impressao: str) -> None:
    await db.document_metadata.update_one({"id": document_id}, {"$set": campos_do_ficheiro(resultado, impressao)})


# ====================================================================
# PROJECÇÃO POR DOCUMENTO (a pesquisa avançada de recibos, declarações e extratos)
# ====================================================================
#: Valores de `doc_type` na projecção (o que a API aceita em `document_type`).
DOC_TYPE_RECIBO = "recibo"
DOC_TYPE_DECLARACAO = "declaracao_efetividade"
DOC_TYPE_EXTRATO = "extrato"
DOC_TYPES_PESQUISAVEIS = (DOC_TYPE_RECIBO, DOC_TYPE_DECLARACAO, DOC_TYPE_EXTRATO)
_DOC_TYPE_DO_TIPO = {TIPO_RECIBO: DOC_TYPE_RECIBO, TIPO_DECLARACAO: DOC_TYPE_DECLARACAO, TIPO_EXTRATO: DOC_TYPE_EXTRATO}


def _numero_do_texto(valor: Any) -> Optional[float]:
    """O líquido guardado como texto (`Decimal`) como número, para a pesquisa comparar valores."""
    d = decimal_do_valor(valor)
    return float(d) if d is not None else None


def projectar_documento(
    doc: dict, *, process_id: str, network_id: Optional[str], trabalho_do_documento: Optional[dict] = None
) -> Optional[dict]:
    """A linha pesquisável de UM ficheiro analisado, ou `None` (não é um tipo pesquisável). Função PURA.

    Lê só o que a análise guardou (`index_facts`, e no recibo o `index_job`): nunca chama a IA, nunca
    o ficheiro. **Nada pessoal**: nem o nome do ficheiro (leva o do cliente), nem o IBAN, nem a contraparte.

    `trabalho_do_documento` é o emprego (já com as edições humanas) a que o recibo/declaração pertence: se
    uma pessoa corrigiu o NIF ou o nome da entidade, a pesquisa vê o que ela validou — não o que a IA leu
    mal. Só as correcções humanas se sobrepõem; o resto vem do documento.
    """
    factos = doc.get("index_facts")
    if not isinstance(factos, dict):
        return None
    doc_type = _DOC_TYPE_DO_TIPO.get(factos.get("tipo"))
    if doc_type is None or not doc.get("id"):
        return None

    linha: dict[str, Any] = {
        "id": doc["id"], "process_id": process_id, "network_id": network_id, "doc_type": doc_type,
        "period": None, "net_salary": None, "net_salary_num": None,
        "employer_nif": None, "employer_name": None, "employer_location": None,
        "job_title": None, "contract_type": None, "admission_date": None,
        "bank": None, "bank_key": None, "needs_review": False,
    }
    if doc_type == DOC_TYPE_RECIBO:
        job = doc.get("index_job") if isinstance(doc.get("index_job"), dict) else {}
        liquido = (job.get("net_salary") or {}).get("value") if job else None
        liquido = liquido if liquido is not None else factos.get("net")
        linha.update(
            period=factos.get("period") or job.get("period"),
            net_salary=None if _numero_do_texto(liquido) is None else str(liquido),
            net_salary_num=_numero_do_texto(liquido),
            employer_nif=factos.get("employer_nif") or (job.get("employer_nif") or {}).get("value"),
            employer_name=factos.get("employer_name") or (job.get("employer_name") or {}).get("value"),
            employer_location=job.get("employer_location"),
            job_title=(job.get("job_title") or {}).get("value"),
            contract_type=(job.get("contract_type") or {}).get("value"),
            needs_review=any((job.get(c) or {}).get("needs_review") for c in CAMPOS_DO_TRABALHO),
        )
    elif doc_type == DOC_TYPE_DECLARACAO:
        linha.update(
            period=factos.get("period"), employer_nif=factos.get("employer_nif"),
            employer_name=factos.get("employer_name"), employer_location=factos.get("employer_location"),
            job_title=factos.get("job_title"), contract_type=factos.get("contract_type"),
            admission_date=factos.get("admission_date"), needs_review=bool(factos.get("needs_review")),
        )
    else:
        inicio = str(factos.get("period_start") or "")
        linha.update(
            period=inicio[:7] if re.match(r"^\d{4}-\d{2}", inicio) else None,
            bank=factos.get("bank"), bank_key=factos.get("bank_key"),
        )

    if trabalho_do_documento and doc_type != DOC_TYPE_EXTRATO:
        for campo, destino in (("employer_nif", "employer_nif"), ("employer_name", "employer_name")):
            revisto = trabalho_do_documento.get(campo) or {}
            if revisto.get("edited_by_human") and revisto.get("value"):
                linha[destino] = revisto["value"]
    return linha


async def reconstruir_documentos_do_index(process_id: str, network_id: Optional[str]) -> int:
    """Reconstrói a projecção pesquisável do processo a partir dos ficheiros já analisados. Devolve quantas linhas.

    **Recalcula, não acumula** (como os metadados profissionais): um ficheiro apagado deixa de constar e uma
    reanálise é idempotente. Faz-se por UPSERT de cada linha e só depois se apagam as que sobram — nunca um
    «apagar tudo e inserir», que deixaria a pesquisa sem estes documentos durante a escrita. Nunca levanta:
    a pesquisa é um reforço, e uma falha aqui não pode derrubar a análise (vira `warning`).
    """
    try:
        metadados = await carregar_metadados(process_id)
        trabalhos = (metadados or {}).get("jobs") or []
        # os originais eliminados (`purgado`) contam: os DADOS lidos deles não deixaram de ser verdade
        docs = await db.document_metadata.find(
            {"process_id": process_id, "is_clean_pdf": {"$ne": True}, "index_facts": {"$exists": True, "$ne": None}},
            {"_id": 0, "id": 1, "index_facts": 1, "index_job": 1},
        ).to_list(500)
        agora = _agora()
        ids: list[str] = []
        for doc in docs:
            trabalho = next((t for t in trabalhos if doc.get("id") in (t.get("source_document_ids") or [])), None)
            linha = projectar_documento(doc, process_id=process_id, network_id=network_id, trabalho_do_documento=trabalho)
            if linha is None:
                continue
            linha["updated_at"] = agora
            await db.process_index_documents.update_one({"id": linha["id"]}, {"$set": linha}, upsert=True)
            ids.append(linha["id"])
        await db.process_index_documents.delete_many({"process_id": process_id, "id": {"$nin": ids}})
        return len(ids)
    except Exception as exc:  # noqa: BLE001 — um reforço de pesquisa não derruba a análise
        logger.warning("[INDEX] Projecção pesquisável do processo %s não reconstruída: %s", process_id, type(exc).__name__)
        return 0


# ====================================================================
# ARQUIVO HISTÓRICO (importação de ZIPs, Out 2026)
# ====================================================================
#: Prefixo do `process_id` ARTIFICIAL das linhas históricas: não há processo nem cliente por detrás.
PREFIXO_DO_PROCESSO_HISTORICO = "historical_import_"


def processo_historico(import_id: str) -> str:
    return f"{PREFIXO_DO_PROCESSO_HISTORICO}{import_id}"


def linha_historica(
    resultado: ResultadoDaAnalise, *, document_id: str, import_id: str, network_id: str, label: Optional[str] = None
) -> Optional[dict]:
    """A linha pesquisável de UM documento do arquivo histórico, ou `None` (não é um tipo pesquisável). PURA.

    Passa pela MESMA `projectar_documento` dos documentos do CRM: o que a pesquisa lê não pode divergir entre
    os dois mundos. Acrescenta só o que distingue o arquivo — `historical`, `import_id` e a etiqueta — e **nada
    pessoal**: nem o nome do ficheiro nem o caminho no ZIP (levam o nome do cliente), nem o IBAN. Sem rede não
    há linha: uma linha histórica sem rede não teria quem a visse e, pior, daria vontade de a «tolerar».
    """
    if not network_id:
        return None
    pseudo = {
        "id": document_id,
        "index_facts": resultado.factos,
        "index_job": resultado.job.model_dump(mode="json") if resultado.job is not None else None,
    }
    linha = projectar_documento(pseudo, process_id=processo_historico(import_id), network_id=network_id)
    if linha is None:
        return None
    linha.update(historical=True, import_id=import_id, import_label=(label or None))
    return linha


async def ids_historicos_existentes(ids: Iterable[str]) -> set[str]:
    """Dos ids dados, os que JÁ estão no arquivo (para não pagar duas vezes a leitura do mesmo ficheiro)."""
    ids = [i for i in ids if i]
    if not ids:
        return set()
    achados = await db.process_index_documents.find(
        {"id": {"$in": ids}, "historical": True}, {"_id": 0, "id": 1}
    ).to_list(len(ids))
    return {a["id"] for a in achados}


async def gravar_documento_historico(linha: dict) -> bool:
    """Grava a linha se ainda não existe (idempotente). `True` se foi INSERIDA. Nunca sobrescreve uma existente."""
    if not linha.get("historical") or not linha.get("network_id") or not linha.get("import_id"):
        raise ValueError("só se gravam linhas históricas com rede e com importação (sem ela não se desfaz)")
    linha = {**linha, "updated_at": _agora()}
    r = await db.process_index_documents.update_one({"id": linha["id"]}, {"$setOnInsert": linha}, upsert=True)
    return r.matched_count == 0


async def ids_historicos_conhecidos(ids: Iterable[str]) -> dict[str, str]:
    """`{id: estado}` do que o arquivo já sabe: `importado` (há linha) ou o veredicto negativo já pago
    (`identificacao`, `outro`, `sem_dados`) — para uma reexecução não voltar a pagar a leitura do mesmo ficheiro."""
    ids = [i for i in ids if i]
    if not ids:
        return {}
    conhecidos: dict[str, str] = {}
    for a in await db.index_historical_seen.find({"id": {"$in": ids}}, {"_id": 0, "id": 1, "estado": 1}).to_list(len(ids)):
        conhecidos[a["id"]] = str(a.get("estado") or "visto")
    for i in await ids_historicos_existentes(ids):
        conhecidos[i] = "importado"
    return conhecidos


async def marcar_visto_no_arquivo(document_id: str, import_id: str, estado: str) -> None:
    """Regista um veredicto NEGATIVO já pago. Só o estado e o id: nada do ficheiro."""
    await db.index_historical_seen.update_one(
        {"id": document_id},
        {"$setOnInsert": {"id": document_id, "import_id": import_id, "estado": estado, "em": _agora()}},
        upsert=True,
    )


async def contar_documentos_historicos(import_id: str) -> int:
    return await db.process_index_documents.count_documents({"historical": True, "import_id": import_id})


async def apagar_importacao_historica(import_id: str) -> int:
    """Desfaz UMA importação: apaga as suas linhas. O directório `employers` não se toca (é global e partilhado)."""
    if not import_id:
        return 0
    r = await db.process_index_documents.delete_many({"historical": True, "import_id": import_id})
    await db.index_historical_seen.delete_many({"import_id": import_id})
    return r.deleted_count


def entidades_das_declaracoes(factos: Iterable[dict]) -> list[tuple[str, str]]:
    """`(nif, nome)` das declarações que podem alimentar o directório: NIF válido, nome e sem dúvida."""
    saida: list[tuple[str, str]] = []
    for f in factos:
        if f.get("tipo") != TIPO_DECLARACAO or f.get("needs_review") or not f.get("nif_valido"):
            continue
        nif, nome = normalizar_nif(f.get("employer_nif")), " ".join(str(f.get("employer_name") or "").split())
        if nif and nif_e_valido(nif) and nome:
            saida.append((nif, nome))
    return saida


async def agregar_documentos_do_index(pipeline: list[dict], *, tempo_maximo_ms: int) -> list[dict]:
    """Corre um pipeline de LEITURA sobre `process_index_documents` (pesquisa avançada por documento)."""
    return await db.process_index_documents.aggregate(
        pipeline, maxTimeMS=tempo_maximo_ms, allowDiskUse=True,
    ).to_list(1)


# ====================================================================
# EDIÇÃO HUMANA, ALERTAS E DIRECTÓRIO (leitura/escrita para a API)
# ====================================================================
CAMPOS_EDITAVEIS = ("employer_nif", "employer_name", "job_title", "net_salary", "contract_type")


class EdicaoInvalida(ValueError):
    """O pedido de edição não é aplicável (job inexistente, campo desconhecido, valor sem forma)."""


def aplicar_edicao(
    trabalhos: list[dict], job_id: str, alteracoes: dict[str, Any]
) -> list[TrabalhoProfissional]:
    """Aplica `alteracoes` (`{campo: valor|None}`) ao trabalho `job_id`. Função PURA.

    Um campo editado por uma pessoa fica `edited_by_human=True` e, tendo valor,
    `needs_review=False` — a pessoa dispôs. Vazio de propósito (`None`) também
    conta como revisto. O CÓDIGO continua a reforçar: um NIF sem dígito de controlo
    volta a ficar `needs_review` (a pessoa pode ter escrito uma gralha).
    Levanta `EdicaoInvalida` para campo desconhecido, job inexistente ou valor sem forma.
    """
    desconhecidos = sorted(set(alteracoes) - set(CAMPOS_EDITAVEIS))
    if desconhecidos:
        raise EdicaoInvalida(f"Campo não editável: {desconhecidos[0]}")
    if not alteracoes:
        raise EdicaoInvalida("Nada para alterar.")
    modelos = [TrabalhoProfissional.model_validate(t) for t in trabalhos]
    alvo = next((t for t in modelos if t.job_id == job_id), None)
    if alvo is None:
        raise EdicaoInvalida("Trabalho não encontrado.")
    for nome, valor in alteracoes.items():
        actual = getattr(alvo, nome)
        if nome == "net_salary" and valor is not None:
            valor = decimal_do_valor(valor)
            if valor is None or valor < 0:
                raise EdicaoInvalida("O vencimento líquido não é um valor válido.")
        if nome == "employer_nif" and valor is not None:
            valor = normalizar_nif(valor)
        if isinstance(valor, str):
            valor = " ".join(valor.split()) or None
        novo = CampoRevisavel.model_validate({
            **actual.model_dump(mode="json"),
            "value": None if valor is None else (str(valor) if nome == "net_salary" else valor),
            "needs_review": False,
            "confidence": actual.confidence,
            "edited_by_human": True,
        })
        setattr(alvo, nome, novo)
    try:
        # volta a validar tudo (NIF reforçado, contrato dentro dos valores permitidos)
        validado = TrabalhoProfissional.model_validate(alvo.model_dump(mode="json"))
    except ValueError as exc:
        raise EdicaoInvalida("Valor inválido.") from exc
    return [validado if t.job_id == job_id else t for t in modelos]


async def editar_trabalho(
    process_id: str, network_id: Optional[str], job_id: str, alteracoes: dict[str, Any]
) -> ProfessionalMetadata:
    """Grava a edição de uma pessoa e recalcula o directório. `EdicaoInvalida` se não se aplica."""
    existente = await carregar_metadados(process_id)
    if not existente:
        raise EdicaoInvalida("Ainda não há metadados profissionais neste processo.")
    trabalhos = aplicar_edicao(existente.get("jobs") or [], job_id, alteracoes)
    modelo = await gravar_metadados(process_id, network_id, trabalhos, existente.get("analysis_fingerprint"))
    await registar_entidades(modelo.jobs)
    # a pesquisa por documento vê o que a pessoa validou (NIF/nome da entidade), não o que a IA leu mal
    await reconstruir_documentos_do_index(process_id, network_id)
    return modelo


async def alertas_do_processo(process_id: str) -> list[dict]:
    """Os alertas do processo (abertos primeiro). Mensagem e severidade vêm da tabela."""
    docs = await db.process_index_alerts.find({"process_id": process_id}, {"_id": 0}).to_list(200)
    ordem = {"alerta": 0, "aviso": 1, "info": 2}
    docs.sort(key=lambda a: (bool(a.get("dismissed_by_human")), ordem.get(a.get("severity"), 3)))
    return docs


async def dispensar_alerta(process_id: str, alert_id: str, user_id: Optional[str]) -> Optional[dict]:
    """Dispensa um alerta DESTE processo (idempotente). `None` se não existe neste processo."""
    alerta = await db.process_index_alerts.find_one({"id": alert_id, "process_id": process_id}, {"_id": 0})
    if not alerta:
        return None
    if not alerta.get("dismissed_by_human"):
        await db.process_index_alerts.update_one(
            {"id": alert_id, "process_id": process_id},
            {"$set": {"dismissed_by_human": True, "dismissed_by": user_id, "dismissed_at": _agora()}},
        )
    return {**alerta, "dismissed_by_human": True}


async def procurar_entidades(texto: str, limite: int = 20) -> list[dict]:
    """Directório GLOBAL de entidades patronais (`{nif, name}`). Sem dados de clientes."""
    texto = (texto or "").strip()
    if len(texto) < 2:
        return []
    digitos = normalizar_nif(texto)
    if digitos and len(digitos) >= 3 and digitos == texto.replace(" ", ""):
        filtro: dict[str, Any] = {"nif": {"$regex": f"^{re.escape(digitos)}"}}
    else:
        normal = nome_normalizado_da_entidade(texto)
        # a normalização tira a pontuação: «.*» fica vazio, e uma expressão vazia casa com TUDO
        if len(normal) < 2:
            return []
        filtro = {"name_normalizado": {"$regex": re.escape(normal)}}
    docs = await db.employers.find(filtro, {"_id": 0, "nif": 1, "name": 1}).to_list(max(1, min(limite, 50)))
    return [{"nif": d["nif"], "name": d["name"]} for d in docs]


async def nifs_das_entidades_pelo_nome(nome_normalizado: str, limite: int) -> list[str]:
    """NIFs do directório global cujo nome (normalizado) contém o texto. LEITURA para a pesquisa avançada.

    Levanta se o directório falhar: quem chama decide o degradado (é um reforço, não uma condição).
    """
    docs = await db.employers.find(
        {"name_normalizado": {"$regex": re.escape(nome_normalizado)}}, {"_id": 0, "nif": 1},
    ).to_list(max(1, min(limite, 200)))
    return [d["nif"] for d in docs if d.get("nif")]


async def agregar_metadados_profissionais(pipeline: list[dict], *, tempo_maximo_ms: int) -> list[dict]:
    """Corre um pipeline de LEITURA sobre `process_professional_metadata` (a pesquisa avançada).

    O pipeline é construído (e a fronteira de processos aplicada) por `index_advanced_search`; aqui só
    se executa, com o tecto de tempo — o único sítio, além da escrita, que toca na colecção.
    """
    return await db.process_professional_metadata.aggregate(
        pipeline, maxTimeMS=tempo_maximo_ms, allowDiskUse=True,
    ).to_list(1)


async def factos_do_processo(process_id: str) -> list[dict]:
    """Os factos de TODOS os ficheiros do processo já analisados (incluindo os saltados nesta corrida)."""
    docs = await db.document_metadata.find(
        {"process_id": process_id, "is_clean_pdf": {"$ne": True}, "index_facts": {"$exists": True, "$ne": None}},
        {"_id": 0, "index_facts": 1},
    ).to_list(500)
    return [d["index_facts"] for d in docs if isinstance(d.get("index_facts"), dict)]


__all__ = [
    "ALERTAS", "calcular_trabalhos", "aplicar_edicoes_humanas", "recalcular_metadados",
    "registar_entidades", "entidades_conhecidas", "substituir_alertas", "campos_do_ficheiro",
    "registar_ficheiro", "factos_do_processo", "contar_alertas_abertos",
    "nifs_das_entidades_pelo_nome", "agregar_metadados_profissionais",
    "projectar_documento", "reconstruir_documentos_do_index", "entidades_das_declaracoes",
    "agregar_documentos_do_index", "DOC_TYPES_PESQUISAVEIS",
]
