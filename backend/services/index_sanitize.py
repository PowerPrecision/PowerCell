"""PDF limpo e purga dos originais do Index (Lote 12, Fase 5).

O QUE FAZ
---------
Os documentos que o **Index** carregou (e só esses — decisão da direcção) ganham um **PDF limpo**:
sem os metadados do ficheiro (autor, software, GPS e data do EXIF, XMP, JavaScript, anexos). O
original só desaparece passados `GRACA_DIAS` (30) e só depois de o PDF limpo ser CONFIRMADO outra
vez no armazenamento.

REGRAS QUE NÃO SE PODEM PERDER
------------------------------
1. **Um PDF limpo por documento DISTINTO.** Nunca se juntam todos os recibos num `recibos.pdf` nem
   todos os extratos num `extratos.pdf` (cada mês tem o seu). Só se funde quando os ficheiros são
   PARTES do mesmo documento exacto — e só se prova por factos que a análise já guardou:
     * extrato: mesmo IBAN e mesmo mês, TODAS as partes são imagens (fotos de páginas);
     * identificação: exactamente uma FRENTE e um VERSO do mesmo tipo (CC, BI, …). Duas frentes e
       dois versos (duas pessoas) não se juntam — não há como saber quem é quem, e juntar mal
       seria misturar duas pessoas num ficheiro;
     * um recibo nunca se junta a outro; um PDF nunca se junta a nada (já é um documento).
   Na dúvida, fica separado: um PDF a mais custa nada, um PDF com duas pessoas é um incidente.
2. **Nada se apaga sem verificação.** O PDF limpo é gravado, LIDO DE VOLTA da chave exacta e
   comparado (sha256, páginas, ausência de metadados) ANTES de qualquer registo mudar de estado.
   Na purga a verificação repete-se. Qualquer dúvida → o original fica (e diz-se no Log da IA).
3. **Falhar nunca estraga o que existe.** Sanitizar falhado = alerta `sanitizacao_falhou` (aviso) e
   originais intactos. Observa, não intercepta: nada daqui bloqueia a indexação.
4. **A purga está DESLIGADA por omissão** (`INDEX_PURGE_ENABLED=true` para ligar). Gerar o PDF limpo
   é aditivo (não apaga nada) e pode ligar-se sozinho; apagar é irreversível e exige decisão.
5. **O PDF limpo é um registo próprio** (`is_clean_pdf`): não se re-analisa (os factos ficam nos
   originais, senão contavam-se duas vezes) e o motor financeiro ignora-o.
6. **A chave do PDF limpo vive ao lado do original** (mesma pasta, dentro da raiz documental) e nunca
   sobrescreve nada: se o nome existe, ganha um sufixo.
"""
from __future__ import annotations

import asyncio
import hashlib
import io
import logging
import os
import re
import unicodedata
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import db
from services import index_store as store
from services.index_ai import (
    TIPO_EXTRATO,
    TIPO_IDENTIFICACAO,
    tipo_de_analise,
)
from services.process_ai_log import registar_accao_ia
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)

GRACA_DIAS_OMISSAO = 30
#: Acima disto o ficheiro não se converte (a conversão corre em memória).
TAMANHO_MAXIMO = 20 * 1024 * 1024
EXTENSOES_DE_IMAGEM = (".jpg", ".jpeg", ".png", ".webp")
EXTENSOES_SANITIZAVEIS = (".pdf", *EXTENSOES_DE_IMAGEM)


# ====================================================================
# INTERRUPTORES
# ====================================================================
def _ligado(nome: str, omissao: bool) -> bool:
    valor = os.environ.get(nome, "").strip().lower()
    if valor in ("true", "1", "yes"):
        return True
    if valor in ("false", "0", "no"):
        return False
    return omissao


def graca_em_dias() -> int:
    """Dias entre o PDF limpo e a eliminação do original. Valor inválido ou ≤0 cai nos 30 (nunca encurta)."""
    try:
        dias = int(os.environ.get("INDEX_PURGE_GRACE_DAYS", GRACA_DIAS_OMISSAO))
    except (TypeError, ValueError):
        return GRACA_DIAS_OMISSAO
    return dias if dias > 0 else GRACA_DIAS_OMISSAO


def sanitizacao_automatica_ligada() -> bool:
    """O fecho da indexação gera o PDF limpo? Aditivo, logo ligado — salvo em `TESTING`."""
    return _ligado("INDEX_SANITIZE_ENABLED", os.environ.get("TESTING", "").strip().lower() != "true")


def purga_ligada() -> bool:
    """A eliminação do original está ligada? **DESLIGADA por omissão**, mesmo em produção."""
    return _ligado("INDEX_PURGE_ENABLED", False)


# ====================================================================
# AGRUPAR (puro): um PDF por documento distinto
# ====================================================================
def _sem_acentos(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texto or "") if unicodedata.category(c) != "Mn")


def _extensao(nome: Optional[str]) -> str:
    return os.path.splitext((nome or "").lower())[1]


def e_imagem(nome: Optional[str]) -> bool:
    return _extensao(nome) in EXTENSOES_DE_IMAGEM


def e_pdf(nome: Optional[str]) -> bool:
    return _extensao(nome) == ".pdf"


def e_sanitizavel(nome: Optional[str]) -> bool:
    return _extensao(nome) in EXTENSOES_SANITIZAVEIS


def _factos(doc: dict) -> dict:
    f = doc.get("index_facts")
    return f if isinstance(f, dict) else {}


def _tipo(doc: dict) -> Optional[str]:
    return tipo_de_analise(doc.get("ai_category"), doc.get("ai_subcategory"), doc.get("filename"))


def _ordem(doc: dict) -> tuple:
    return (str(doc.get("created_at") or ""), str(doc.get("filename") or ""), str(doc.get("id") or ""))


def chave_de_extrato(doc: dict) -> Optional[tuple]:
    """`("extrato", iban, "YYYY-MM")` ou `None` (sem IBAN ou sem período não se prova nada)."""
    f = _factos(doc)
    iban = re.sub(r"\s", "", str(f.get("iban") or "")).upper()
    inicio = str(f.get("period_start") or "")
    if not iban or not re.match(r"^\d{4}-\d{2}", inicio):
        return None
    return ("extrato", iban, inicio[:7])


def agrupar_em_documentos(docs: list[dict]) -> list[list[dict]]:
    """Divide os ficheiros em DOCUMENTOS: cada grupo vira um PDF limpo. Função pura e determinística.

    Só se funde o que se PROVA ser o mesmo documento (ver regra 1 no topo do módulo). A ordem das
    partes é a de carregamento (data, depois nome) — a ordem natural das páginas fotografadas.
    """
    ordenados = sorted(docs, key=_ordem)
    por_extrato: dict[tuple, list[dict]] = {}
    por_identificacao: dict[str, list[dict]] = {}
    grupos: list[list[dict]] = []

    for d in ordenados:
        tipo = _tipo(d)
        if e_imagem(d.get("filename")):
            if tipo == TIPO_EXTRATO and chave_de_extrato(d):
                por_extrato.setdefault(chave_de_extrato(d), []).append(d)
                continue
            subtipo = d.get("ai_subtype") or _factos(d).get("subtype")
            if tipo == TIPO_IDENTIFICACAO and subtipo:
                por_identificacao.setdefault(str(subtipo), []).append(d)
                continue
        grupos.append([d])  # PDF, recibo, tipo desconhecido ou sem chave: sozinho

    for membros in por_extrato.values():
        grupos.append(membros)
    for membros in por_identificacao.values():
        faces = [str(_factos(m).get("face") or "") for m in membros]
        # exactamente UMA frente e UM verso: é o mesmo cartão. Qualquer outra combinação
        # (duas frentes, face desconhecida, três ficheiros…) fica separada.
        if len(membros) == 2 and sorted(faces) == ["frente", "verso"]:
            grupos.append(membros)
        else:
            grupos.extend([m] for m in membros)

    return sorted(grupos, key=lambda g: _ordem(g[0]))


def _slug(texto: str) -> str:
    base = re.sub(r"[^a-zA-Z0-9._-]+", "_", _sem_acentos(texto)).strip("._-")
    return base[:80] or "documento"


def nome_do_pdf_limpo(grupo: list[dict]) -> str:
    """Nome legível e estável do PDF limpo (nunca o nome de um ficheiro de outro documento)."""
    primeiro = grupo[0]
    if len(grupo) > 1:
        tipo = _tipo(primeiro)
        if tipo == TIPO_EXTRATO:
            chave = chave_de_extrato(primeiro)
            return f"extrato_bancario_{chave[2]}_limpo.pdf"
        if tipo == TIPO_IDENTIFICACAO:
            subtipo = primeiro.get("ai_subtype") or _factos(primeiro).get("subtype") or "documento"
            return f"identificacao_{_slug(str(subtipo))}_limpo.pdf"
    stem = os.path.splitext(str(primeiro.get("filename") or "documento"))[0]
    return f"{_slug(stem)}_limpo.pdf"


# ====================================================================
# CONSTRUIR O PDF LIMPO (puro, síncrono — corre numa thread)
# ====================================================================
class ConversaoImpossivel(ValueError):
    """O ficheiro não se converte (corrompido, protegido por palavra-passe, formato estranho)."""


def _imagem_sem_metadados(conteudo: bytes) -> bytes:
    """Re-codifica a imagem do zero: o EXIF (GPS, câmara, autor), o ICC e os blocos de texto não passam.

    A orientação aplica-se antes (`exif_transpose`) para a foto não ficar de lado sem o EXIF.
    """
    from PIL import Image, ImageOps

    try:
        with Image.open(io.BytesIO(conteudo)) as bruta:
            imagem = ImageOps.exif_transpose(bruta)
            if imagem.mode not in ("RGB", "L"):
                imagem = imagem.convert("RGB")
            saida = io.BytesIO()
            imagem.save(saida, "JPEG", quality=92, optimize=True)
            return saida.getvalue()
    except Exception as exc:  # noqa: BLE001 — Pillow levanta de tudo
        raise ConversaoImpossivel("imagem ilegível") from exc


def _scrub(doc):
    """Limpa as páginas (anotações, formulários, anexos, miniaturas) e devolve um documento NOVO.

    O `scrub` do PyMuPDF não chega: deixa as acções ao nível do CATÁLOGO (`/OpenAction`, `/AA`,
    árvore `/Names` com JavaScript, XMP, `/PieceInfo`). Copiar só as PÁGINAS para um documento novo
    deixa tudo isso para trás — o catálogo nasce limpo. Medido: um PDF com `/OpenAction`
    JavaScript sobrevivia ao `scrub` sozinho.
    """
    import fitz

    doc.scrub(
        metadata=True, javascript=True, attached_files=True, embedded_files=True, xml_metadata=True,
        thumbnails=True, reset_fields=True, reset_responses=True,
        remove_links=False, hidden_text=False, redactions=False,
    )
    limpo = fitz.open()
    limpo.insert_pdf(doc)
    limpo.set_metadata({})
    _limpar_anotacoes(limpo)
    return limpo


#: Chaves de uma anotação que dizem QUEM a escreveu e QUANDO (o autor de um comentário é metadado).
_CHAVES_DE_AUTORIA = ("T", "Subj", "CreationDate", "M", "RC", "IRT")


def _limpar_anotacoes(doc) -> None:
    """Notas adesivas e popups saem (o texto delas não é visível na página impressa); as anotações
    VISÍVEIS (texto livre, realces, carimbos) ficam mas sem autor, assunto nem datas.

    O `scrub` e a cópia de páginas NÃO tocam nisto — medido: o autor de um realce sobrevivia aos dois.
    """
    import fitz

    for pagina in doc:
        for anotacao in list(pagina.annots() or []):
            if anotacao.type[0] in (fitz.PDF_ANNOT_TEXT, fitz.PDF_ANNOT_POPUP):
                pagina.delete_annot(anotacao)
                continue
            for chave in _CHAVES_DE_AUTORIA:
                doc.xref_set_key(anotacao.xref, chave, "null")


def _tem_javascript(doc) -> bool:
    """Procura JavaScript em TODOS os objectos (também os comprimidos): o texto cru do ficheiro não chega."""
    for xref in range(1, doc.xref_length()):
        try:
            objecto = doc.xref_object(xref, compressed=True)
        except Exception:  # noqa: BLE001 — um objecto ilegível não é prova de nada, mas é suspeito
            return True
        if "/JavaScript" in objecto or "/JS" in objecto or "/OpenAction" in objecto or "/Launch" in objecto:
            return True
    return False


def construir_pdf_limpo(partes: list[tuple[str, bytes]]) -> tuple[bytes, int]:
    """`(pdf, páginas)` a partir de `[(nome, bytes)]`. `ConversaoImpossivel` se não se consegue.

    * Um PDF isolado é limpo (sem metadados, XMP, JavaScript nem anexos).
    * Imagens viram páginas de um PDF novo (re-codificadas sem EXIF), uma página por imagem.
    Nunca mistura um PDF com imagens: o agrupamento já o garante, e aqui recusa-se.
    """
    import fitz

    if not partes:
        raise ConversaoImpossivel("sem ficheiros")
    if len(partes) == 1 and e_pdf(partes[0][0]):
        try:
            doc = fitz.open(stream=partes[0][1], filetype="pdf")
        except Exception as exc:  # noqa: BLE001
            raise ConversaoImpossivel("PDF ilegível") from exc
        if doc.is_encrypted or doc.needs_pass:
            raise ConversaoImpossivel("PDF protegido por palavra-passe")
        if doc.page_count < 1:
            raise ConversaoImpossivel("PDF sem páginas")
        limpo = _scrub(doc)
        return limpo.tobytes(garbage=4, deflate=True, clean=True), limpo.page_count

    if any(not e_imagem(nome) for nome, _ in partes):
        raise ConversaoImpossivel("só imagens se juntam num PDF")
    novo = fitz.open()
    for _, conteudo in partes:
        jpeg = _imagem_sem_metadados(conteudo)
        retangulo = fitz.open(stream=jpeg, filetype="jpeg")[0].rect
        pagina = novo.new_page(width=retangulo.width, height=retangulo.height)
        pagina.insert_image(retangulo, stream=jpeg)
    limpo = _scrub(novo)
    return limpo.tobytes(garbage=4, deflate=True, clean=True), limpo.page_count


def verificar_pdf_limpo(pdf: bytes, paginas_esperadas: int) -> tuple[bool, Optional[str]]:
    """`(ok, motivo)`: é um PDF legível, com as páginas certas e SEM metadados.

    É a verificação que decide se um original pode ser apagado: lê o PDF como o leitor mais exigente
    o leria. Corre sobre os bytes LIDOS DE VOLTA do armazenamento, não sobre os que se enviaram.
    """
    import fitz

    if not pdf or not pdf.startswith(b"%PDF"):
        return False, "não é um PDF"
    try:
        doc = fitz.open(stream=pdf, filetype="pdf")
    except Exception:  # noqa: BLE001
        return False, "PDF ilegível"
    if doc.is_encrypted or doc.needs_pass:
        return False, "PDF protegido"
    if doc.page_count != paginas_esperadas or doc.page_count < 1:
        return False, f"páginas: {doc.page_count} em vez de {paginas_esperadas}"
    meta = doc.metadata or {}
    sujos = [k for k in ("title", "author", "subject", "keywords", "creator", "producer", "creationDate", "modDate")
             if (meta.get(k) or "").strip()]
    if sujos:
        return False, f"metadados presentes: {', '.join(sujos)}"
    if doc.xref_xml_metadata():
        return False, "XMP presente"
    if doc.embfile_names():
        return False, "anexos embebidos"
    if _tem_javascript(doc):
        return False, "JavaScript ou acção automática presente"
    for pagina in doc:
        for anotacao in pagina.annots() or []:
            info = anotacao.info or {}
            if (info.get("title") or "").strip() or (info.get("subject") or "").strip():
                return False, "anotações com autor"
            if anotacao.type[0] == fitz.PDF_ANNOT_TEXT:
                return False, "notas adesivas presentes"
    return True, None


def _sha256(conteudo: bytes) -> str:
    return hashlib.sha256(conteudo).hexdigest()


# ====================================================================
# SANITIZAR UM PROCESSO (assíncrono)
# ====================================================================
def _agora() -> datetime:
    return datetime.now(timezone.utc)


async def candidatos_a_sanitizar(process_id: str) -> list[dict]:
    """Ficheiros que o INDEX carregou, ainda originais, num formato que se converte."""
    docs = await db.document_metadata.find(
        {
            "process_id": process_id, "uploaded_by_index": True,
            "is_clean_pdf": {"$ne": True},
            "$or": [{"file_state": {"$exists": False}}, {"file_state": None}, {"file_state": "original"}],
            "s3_path": {"$nin": [None, ""]},
        },
        {"_id": 0},
    ).to_list(500)
    return [d for d in docs if e_sanitizavel(d.get("filename") or d.get("s3_path"))]


async def _chave_livre(pasta: str, nome: str) -> Optional[str]:
    """A primeira chave `pasta/nome[_n].pdf` AUSENTE. `None` se o armazenamento não responde."""
    base, ext = os.path.splitext(nome)
    for n in range(1, 20):
        chave = f"{pasta}/{base if n == 1 else f'{base}_{n}'}{ext}"
        estado, _ = await asyncio.to_thread(s3_service.head_object_metadata, chave)
        if estado == "ausente":
            return chave
        if estado == "erro":
            return None
    return None


async def _falhar(process_id: str, grupo: list[dict], motivo: str, user: Optional[dict], gatilho: str) -> None:
    for d in grupo:
        await registar_accao_ia(
            process_id=process_id, accao="sanitizar", estado="falha", gatilho=gatilho, user=user,
            ficheiro=d.get("filename"), s3_path=d.get("s3_path"), documento_id=d.get("id"), motivo=motivo,
        )


async def _sanitizar_grupo(
    process: dict, grupo: list[dict], user: Optional[dict], gatilho: str, agora: datetime,
    ler_ficheiro,
) -> Optional[dict]:
    """Gera, grava, RELÊ e só então regista. `None` se falhou (originais intactos)."""
    process_id = process["id"]
    partes: list[tuple[str, bytes]] = []
    for d in grupo:
        conteudo, motivo = await ler_ficheiro(d["s3_path"])
        if conteudo is None:
            await _falhar(process_id, grupo, "armazenamento_indisponivel" if motivo == "ilegivel" else "formato_nao_sanitizavel",
                          user, gatilho)
            return None
        partes.append((d.get("filename") or d["s3_path"], conteudo))

    try:
        pdf, paginas = await asyncio.to_thread(construir_pdf_limpo, partes)
    except ConversaoImpossivel:
        await _falhar(process_id, grupo, "formato_nao_sanitizavel", user, gatilho)
        return None
    except Exception:  # noqa: BLE001 — a conversão nunca derruba o fecho
        logger.exception("[INDEX] Conversão falhou no processo %s", process_id)
        await _falhar(process_id, grupo, "erro_interno", user, gatilho)
        return None

    ok, _ = verificar_pdf_limpo(pdf, paginas)
    if not ok or len(pdf) > TAMANHO_MAXIMO:
        await _falhar(process_id, grupo, "pdf_limpo_invalido", user, gatilho)
        return None

    pasta = grupo[0]["s3_path"].rsplit("/", 1)[0]
    chave = await _chave_livre(pasta, nome_do_pdf_limpo(grupo))
    if not chave:
        await _falhar(process_id, grupo, "armazenamento_indisponivel", user, gatilho)
        return None
    if not await asyncio.to_thread(s3_service.put_object_exact, chave, pdf, "application/pdf"):
        await _falhar(process_id, grupo, "armazenamento_indisponivel", user, gatilho)
        return None

    # RELER da chave exacta: o que foi gravado é o que se verifica.
    estado, lido = await asyncio.to_thread(s3_service.get_object_exact, chave, TAMANHO_MAXIMO)
    if estado != "ok" or lido is None or _sha256(lido) != _sha256(pdf) or not verificar_pdf_limpo(lido, paginas)[0]:
        await asyncio.to_thread(s3_service.delete_file, chave)  # a cópia má não fica
        await _falhar(process_id, grupo, "pdf_limpo_invalido", user, gatilho)
        return None

    sha = _sha256(lido)
    limite = (agora + timedelta(days=graca_em_dias())).isoformat()
    ids = [d["id"] for d in grupo]
    primeiro = grupo[0]
    registo_limpo = {
        "id": str(uuid.uuid4()), "process_id": process_id, "client_name": primeiro.get("client_name", ""),
        "s3_path": chave, "filename": chave.rsplit("/", 1)[-1],
        "ai_category": primeiro.get("ai_category"), "ai_subcategory": primeiro.get("ai_subcategory"),
        "ai_subtype": primeiro.get("ai_subtype"),
        "is_clean_pdf": True, "clean_of": ids, "is_categorized": True, "in_index_queue": False,
        "uploaded_by_index": False, "file_state": "original",
        "clean_pdf_sha256": sha, "clean_pdf_pages": paginas,
        "created_at": agora.isoformat(), "updated_at": agora.isoformat(),
    }
    await db.document_metadata.insert_one(registo_limpo)
    await db.document_metadata.update_many(
        {"id": {"$in": ids}},
        {"$set": {
            "file_state": "sanitizado", "clean_pdf_path": chave, "clean_pdf_sha256": sha,
            "clean_pdf_pages": paginas, "clean_pdf_id": registo_limpo["id"],
            "sanitized_at": agora.isoformat(), "purge_after": limite,
        }},
    )
    for d in grupo:
        await registar_accao_ia(
            process_id=process_id, accao="sanitizar", estado="sucesso", gatilho=gatilho, user=user,
            ficheiro=d.get("filename"), s3_path=d.get("s3_path"), documento_id=d.get("id"),
        )
    return {"clean_pdf_id": registo_limpo["id"], "path": chave, "paginas": paginas, "partes": len(grupo)}


async def sanitizar_processo(
    process_id: str, user: Optional[dict] = None, *, gatilho: str = "automatico", agora: Optional[datetime] = None,
    ler_ficheiro=None,
) -> dict[str, Any]:
    """PDF limpo dos ficheiros que o Index carregou. `{"candidatos","grupos","sanitizados","falhas"}`.

    Idempotente: um ficheiro já sanitizado não volta a ser candidato. Uma falha de um grupo não
    pára os outros e deixa o alerta `sanitizacao_falhou`. Nunca levanta.
    """
    from services import index_jobs

    ler = ler_ficheiro or index_jobs._ler_ficheiro
    agora = agora or _agora()
    resumo = {"candidatos": 0, "grupos": 0, "sanitizados": 0, "falhas": 0}
    try:
        processo = await db.processes.find_one({"id": process_id, "is_deleted": {"$ne": True}}, {"_id": 0})
        if not processo:
            return resumo
        docs = await candidatos_a_sanitizar(process_id)
        resumo["candidatos"] = len(docs)
        falhados: list[str] = []
        for grupo in agrupar_em_documentos(docs):
            resumo["grupos"] += 1
            try:
                feito = await _sanitizar_grupo(processo, grupo, user, gatilho, agora, ler)
            except Exception:  # noqa: BLE001 — um grupo mau não pára os outros
                logger.exception("[INDEX] Sanitização de um grupo falhou no processo %s", process_id)
                feito = None
            if feito:
                resumo["sanitizados"] += len(grupo)
            else:
                resumo["falhas"] += len(grupo)
                falhados.extend(d["id"] for d in grupo)
        await _assinalar_falhas(processo, falhados)
    except Exception:  # noqa: BLE001
        logger.exception("[INDEX] Sanitização do processo %s falhou", process_id)
        resumo["falhas"] += 1
    return resumo


async def _assinalar_falhas(processo: dict, falhados: list[str]) -> None:
    """`sanitizacao_falhou` (aviso) para os ficheiros que ficaram por limpar. Nunca levanta."""
    if not falhados:
        return
    try:
        await store.acrescentar_alerta(
            processo["id"], processo.get("network_id"),
            {"code": "sanitizacao_falhou", "refs": [{"document_id": d, "page": None} for d in sorted(falhados)],
             "periodo": None},
        )
        from services.index_status import gravar_contadores

        await gravar_contadores(processo["id"], index_alerts_open=await store.contar_alertas_abertos(processo["id"]))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Alerta de sanitização não gravado: %s", type(exc).__name__)


async def sanitizar_do_fecho(process: dict, user: Optional[dict]) -> dict[str, Any]:
    """O passo do `INDEX_FINALIZE`. Sem o interruptor automático não faz nada."""
    if not sanitizacao_automatica_ligada():
        return {}
    resumo = await sanitizar_processo(process["id"], user, gatilho="automatico")
    return {"sanitizados": resumo["sanitizados"], "sanitizacao_falhas": resumo["falhas"]}


# ====================================================================
# O JOB MANUAL («Apagar metadados do PDF»)
# ====================================================================
async def correr_sanitizacao(task_id: str, process_id: str, user: Optional[dict]) -> dict[str, Any]:
    """O trabalho do job manual. Termina SEMPRE o TaskLog e liberta a chave; nunca levanta."""
    from models.task_log import TaskStatus
    from services import index_jobs
    from services.task_log_service import TaskLogService

    try:
        await TaskLogService.update_task(task_id, status=TaskStatus.PROCESSING, progress=1,
                                         progress_message="A gerar os PDFs limpos…")
        resumo = await sanitizar_processo(process_id, user, gatilho="manual")
        await TaskLogService.update_task(task_id, status=TaskStatus.COMPLETED, progress=100,
                                         progress_message="PDFs limpos gerados.", result_data=resumo)
        await _notificar(process_id, user, resumo)
        return resumo
    except Exception:  # noqa: BLE001
        logger.exception("[INDEX] O job de sanitização do processo %s falhou", process_id)
        try:
            await TaskLogService.update_task(task_id, status=TaskStatus.FAILED,
                                             error_message="Não foi possível gerar os PDFs limpos. Os originais foram mantidos.")
        except Exception:  # noqa: BLE001
            pass
        return {}
    finally:
        await index_jobs.libertar_job(task_id)


async def _notificar(process_id: str, user: Optional[dict], resumo: dict) -> None:
    """Notificação in-app só com números. Nunca levanta."""
    if not (user or {}).get("id"):
        return
    try:
        from services.realtime_notifications import send_realtime_notification

        partes = [f"{resumo.get('sanitizados', 0)} ficheiro(s) com PDF limpo"]
        if resumo.get("falhas"):
            partes.append(f"{resumo['falhas']} não puderam ser limpos (originais mantidos)")
        await send_realtime_notification(
            user_id=user["id"], title="PDF limpo concluído", message="; ".join(partes) + ".",
            notification_type="index_sanitize_done", link=f"/index/{process_id}", process_id=process_id,
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[INDEX] Notificação da sanitização não enviada: %s", type(exc).__name__)


async def iniciar_sanitizacao(process_id: str, user: Optional[dict]) -> dict[str, Any]:
    """«Apagar metadados»: cria o job e DEVOLVE JÁ. `{"task_id", "iniciado"}`."""
    from models.task_log import TaskType
    from services import index_jobs
    from services.background_tasks import spawn_background_task

    task_id, existente = await index_jobs.reivindicar_job(
        process_id, TaskType.INDEX_SANITIZE, (user or {}).get("id") or "system", metadata={"gatilho": "manual"},
    )
    if task_id is None:
        return {"task_id": existente, "iniciado": False}
    spawn_background_task(correr_sanitizacao(task_id, process_id, user), name=f"index-sanitizar-{process_id}")
    return {"task_id": task_id, "iniciado": True}


# ====================================================================
# A PURGA (só depois da graça, só com a cópia limpa CONFIRMADA)
# ====================================================================
async def _repontar_referencias(origem: str, destino: str) -> None:
    """Os pedidos do Portal que apontavam para o original passam a apontar para o PDF limpo.

    Reaproveita a repontagem da libertação da `Index` (um só sítio sabe onde o Portal guarda o
    caminho) e tira os duplicados: três fotos fundidas num PDF deixavam três entradas iguais.
    """
    from services.index_release import _repontar_pedidos_do_portal

    await _repontar_pedidos_do_portal(origem, destino)
    candidatos = await db.documents.find({"attached_files": {"$elemMatch": {"s3_path": destino}}}, {"_id": 0}).to_list(50)
    for doc in candidatos:
        vistos: set[str] = set()
        unicos = []
        for a in doc.get("attached_files") or []:
            caminho = a.get("s3_path") if isinstance(a, dict) else None
            if caminho and caminho in vistos:
                continue
            if caminho:
                vistos.add(caminho)
            unicos.append(a)
        if doc.get("id") and len(unicos) != len(doc.get("attached_files") or []):
            await db.documents.update_one({"id": doc["id"]}, {"$set": {"attached_files": unicos}})


async def _copia_limpa_confirmada(caminho: str, sha: Optional[str], paginas: Optional[int]) -> bool:
    estado, lido = await asyncio.to_thread(s3_service.get_object_exact, caminho, TAMANHO_MAXIMO)
    if estado != "ok" or lido is None or not sha or _sha256(lido) != sha:
        return False
    return verificar_pdf_limpo(lido, int(paginas or 0))[0]


def _dentro_da_raiz(caminho: str) -> bool:
    from fastapi import HTTPException

    from services.document_process_resolve import assert_path_within_document_root

    try:
        assert_path_within_document_root(caminho)
        return True
    except HTTPException:
        return False


async def _purgar_grupo(partes: list[dict], agora: datetime) -> bool:
    limpo = partes[0]["clean_pdf_path"]
    process_id = partes[0].get("process_id")
    if not await _copia_limpa_confirmada(limpo, partes[0].get("clean_pdf_sha256"), partes[0].get("clean_pdf_pages")):
        for d in partes:
            await registar_accao_ia(process_id=process_id, accao="purgar", estado="falha", gatilho="automatico",
                                    ficheiro=d.get("filename"), documento_id=d.get("id"), motivo="purga_adiada")
        return False

    for d in partes:
        original = d.get("s3_path")
        if not original or original == limpo:
            continue  # nada a repontar nem a apagar (e NUNCA apagar a chave do PDF limpo)
        await db.document_metadata.update_one(
            {"id": d["id"]},
            {"$set": {"file_state": "purgado", "s3_path": limpo, "s3_path_original": original,
                      "purged_at": agora.isoformat(), "original_deleted": False}},
        )
        await _repontar_referencias(original, limpo)
    await _apagar_originais_pendentes([d["id"] for d in partes])
    for d in partes:
        await registar_accao_ia(process_id=process_id, accao="purgar", estado="sucesso", gatilho="automatico",
                                ficheiro=d.get("filename"), documento_id=d.get("id"))
    return True


async def _apagar_originais_pendentes(ids: Optional[list[str]] = None) -> int:
    """Apaga do S3 os originais de registos já `purgado` com `original_deleted` falso. Devolve quantos."""
    filtro: dict[str, Any] = {"file_state": "purgado", "original_deleted": False,
                              "s3_path_original": {"$nin": [None, ""]}}
    if ids is not None:
        filtro["id"] = {"$in": ids}
    apagados = 0
    for d in await db.document_metadata.find(filtro, {"_id": 0}).to_list(500):
        original = d["s3_path_original"]
        if original == d.get("s3_path") or original == d.get("clean_pdf_path") or not _dentro_da_raiz(original):
            continue
        if await asyncio.to_thread(s3_service.delete_file, original):
            await db.document_metadata.update_one({"id": d["id"]}, {"$set": {"original_deleted": True}})
            apagados += 1
    return apagados


async def purgar_originais_vencidos(agora: Optional[datetime] = None, limite: int = 200) -> dict[str, Any]:
    """Elimina os originais cuja graça acabou e cujo PDF limpo se CONFIRMA outra vez. Nunca levanta.

    Desligada por omissão (`INDEX_PURGE_ENABLED`). Um grupo só se purga INTEIRO e quando todas as
    suas partes estão vencidas; qualquer dúvida adia-o (o original fica e o Log da IA di-lo).
    """
    resumo = {"ligada": purga_ligada(), "purgados": 0, "adiados": 0, "reapagados": 0}
    if not resumo["ligada"]:
        return resumo
    agora = agora or _agora()
    try:
        vencidos = await db.document_metadata.find(
            {"file_state": "sanitizado", "purge_after": {"$lte": agora.isoformat()},
             "clean_pdf_path": {"$nin": [None, ""]}}, {"_id": 0},
        ).to_list(limite)
        por_limpo: dict[str, list[dict]] = {}
        for d in vencidos:
            por_limpo.setdefault(d["clean_pdf_path"], []).append(d)
        for caminho, partes in por_limpo.items():
            todas = await db.document_metadata.find(
                {"file_state": "sanitizado", "clean_pdf_path": caminho}, {"_id": 0}).to_list(50)
            if len(todas) != len(partes):  # há partes ainda dentro da graça: o grupo não se divide
                resumo["adiados"] += len(partes)
                continue
            if await _purgar_grupo(partes, agora):
                resumo["purgados"] += len(partes)
            else:
                resumo["adiados"] += len(partes)
        resumo["reapagados"] = await _apagar_originais_pendentes()
    except Exception:  # noqa: BLE001
        logger.exception("[INDEX] A purga dos originais falhou")
    return resumo
