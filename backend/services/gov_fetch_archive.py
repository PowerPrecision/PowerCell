"""Arquivo dos documentos obtidos no Estado (Finanças / Segurança Social).

Extraído de `portal_gov_fetch`, onde existiam DUAS cópias de ~100 linhas
(uma por portal). O que as cópias faziam mal, e este módulo não faz
(Bloco 5, pontos 8 e 9):

* **Bloqueavam o event loop.** `s3_service.upload_file` é `boto3` síncrono e
  corria directamente dentro da corotina do `BackgroundTask`, que vive no
  processo web: durante o upload de cada PDF (centenas de KB) nenhum outro
  pedido era atendido. Agora `asyncio.to_thread`.
* **Registavam documentos que não existem.** Com o upload falhado
  (`s3_path` a `None`) a cópia escrevia o aviso «a criar registo sem S3
  path» e criava a mesma o registo `RECEIVED` — o cliente via «entregue» um
  documento sem ficheiro, e a recolha contava-o como obtido. Sem ficheiro, não
  há registo; e se NENHUM foi arquivado a recolha falha em vez de «terminar
  com 0 documentos».
* **Fechavam pedidos que não tinham nada a ver.** Um `update_many` marcava
  como entregue QUALQUER pedido pendente da categoria `Financeiros`: obter a
  Nota de Liquidação fechava o pedido de recibos de vencimento. Agora o
  pedido só fecha se o documento obtido é o que ele pede.
* **Duplicavam.** Repetir a recolha no mesmo dia (mesmo nome, mesma chave S3)
  criava outro registo para o mesmo ficheiro.
* **Aceitavam lixo como PDF.** O scraper guardava `>5000 bytes` sem
  cabeçalho `%PDF-` e que não parecesse HTML. Aqui nada que não seja PDF
  passa por PDF.
* **Mapeamento da pasta.** Sem `s3_folder` gravado o upload caía numa pasta
  derivada do id do PROCESSO como se fosse o do cliente. Agora resolve-se (e
  grava-se) o mapeamento pelo mesmo caminho do Portal.
"""
from __future__ import annotations

import asyncio
import io
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from database import db
from services.document_portal_fulfill import _norm
from services.pdf_validation import parece_pdf
from services.s3_document_root import pasta_gravada
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)

_PENDENTES = ("REQUESTED", "PENDING", "requested", "pending")


# (rótulo normalizado do documento) -> (palavras que o pedido pode ter,
# palavras que o pedido NÃO pode ter). «IRS» sozinho é a declaração; a nota
# de liquidação tem «liquidação» e não deve fechar o pedido da declaração.
_REGRAS_DE_PEDIDO: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("nota de liquidacao", ("liquidacao",), ()),
    ("declaracao de irs", ("irs",), ("liquidacao",)),
    ("situacao contributiva", ("contributiva", "seguranca social"), ()),
    ("extrato de remuneracoes", ("remuneracoes", "extrato"), ()),
)


def pedido_corresponde(rotulo_do_documento: str, pedido: dict) -> bool:
    """O pedido pendente pede ESTE documento?

    Compara pelo rótulo do pedido (e pela categoria, quando o rótulo falta).
    Um documento sem regra conhecida não fecha pedido nenhum — o contrário
    (fechar por categoria) é o defeito que isto corrige.
    """
    rotulo = _norm(rotulo_do_documento)
    texto = _norm(f"{pedido.get('custom_label') or ''} {pedido.get('notes') or ''} {pedido.get('category') or ''}")
    for nome, palavras, proibidas in _REGRAS_DE_PEDIDO:
        if nome in rotulo:
            if any(p in texto for p in proibidas):
                return False
            return any(p in texto for p in palavras)
    return False


# O que cada portal deve devolver. Uma recolha que traz só parte disto é
# PARCIAL e diz-se: a nota de liquidação em falta é precisamente o que o banco
# pede e o que ninguém repara que faltou quando o job aparece «com sucesso».
ROTULOS_ESPERADOS: dict[str, tuple[str, ...]] = {
    "financas": ("Declaração de IRS", "Nota de Liquidação IRS"),
    "seguranca_social": ("Situação Contributiva", "Extrato de Remunerações"),
}


def e_captura_de_ecra(rotulo: str) -> bool:
    """O recurso de último caso do scraper imprime a PÁGINA (`page.pdf()`).

    É um PDF válido e fica arquivado — melhor do que nada —, mas não é o
    documento: não fecha pedidos e conta como «em falta».
    """
    return "captura de ecra" in _norm(rotulo)


def rotulos_em_falta(fonte: str, registados: list[dict]) -> list[str]:
    """Os documentos esperados que não foram obtidos (capturas de ecrã não contam)."""
    obtidos = {_norm(r["label"]) for r in registados if not e_captura_de_ecra(r["label"])}
    return [rotulo for rotulo in ROTULOS_ESPERADOS.get(fonte, ()) if _norm(rotulo) not in obtidos]


@dataclass
class ResultadoDoArquivo:
    registados: list[dict] = field(default_factory=list)
    falhados: list[str] = field(default_factory=list)  # rótulos dos que não ficaram

    @property
    def total(self) -> int:
        return len(self.registados)


async def _resolver_pasta(process_id: str, processo: Optional[dict]) -> Optional[str]:
    """A pasta S3 do processo; cria e grava o mapeamento se não existir."""
    existente = pasta_gravada((processo or {}).get("s3_folder"), contexto=f"recolha governamental {process_id}")
    if existente:
        return existente
    from services.s3_mapping_on_create import ensure_s3_mapping_for_entity

    mapeamento = await ensure_s3_mapping_for_entity(
        collection=db.processes,
        entity_id=process_id,
        client_name=(processo or {}).get("client_name") or "cliente",
        owner_client_id=(processo or {}).get("client_id"),
        label="processo (recolha governamental)",
    )
    return mapeamento.get("s3_folder") if mapeamento.get("success") else None


async def arquivar_documentos(
    process_id: str,
    documentos: list,
    *,
    origem: str,
    enviado_por: str,
) -> ResultadoDoArquivo:
    """Arquiva os PDFs no S3 e regista-os em `db.documents`.

    Cada documento é independente: o que falha fica em `falhados` e os
    restantes seguem. Nunca levanta por causa de um documento.
    """
    resultado = ResultadoDoArquivo()
    processo = await db.processes.find_one(
        {"id": process_id}, {"_id": 0, "client_name": 1, "client_id": 1, "s3_folder": 1}
    )
    pasta = await _resolver_pasta(process_id, processo)
    if not pasta:
        logger.error("[GOV-ARQUIVO] Sem pasta S3 para o processo %s: nada foi arquivado.", process_id)
        resultado.falhados = [getattr(d, "label", None) or "Documento" for d in documentos]
        return resultado

    nome_do_cliente = (processo or {}).get("client_name") or "cliente"
    for doc in documentos:
        rotulo = getattr(doc, "label", None) or "Documento"
        conteudo = getattr(doc, "content_bytes", None)
        if getattr(doc, "content_type", "application/pdf") == "application/pdf" and not parece_pdf(conteudo):
            logger.warning("[GOV-ARQUIVO] '%s' descartado: o conteúdo não é um PDF.", rotulo)
            resultado.falhados.append(rotulo)
            continue
        try:
            s3_path = await asyncio.to_thread(
                s3_service.upload_file,
                file_obj=io.BytesIO(conteudo),
                client_id=process_id,
                client_name=nome_do_cliente,
                category=doc.category,
                filename=doc.filename,
                content_type=doc.content_type,
                s3_folder=pasta,
            )
        except Exception as exc:
            logger.error("[GOV-ARQUIVO] Upload de '%s' falhou: %s", rotulo, type(exc).__name__, exc_info=True)
            s3_path = None
        if not s3_path:
            logger.error("[GOV-ARQUIVO] '%s' não ficou no S3 — sem registo.", rotulo)
            resultado.falhados.append(rotulo)
            continue

        agora = datetime.now(timezone.utc).isoformat()
        try:
            await db.documents.update_one(
                {"process_id": process_id, "s3_path": s3_path},
                {
                    "$set": {
                        "filename": doc.filename,
                        "original_filename": doc.filename,
                        "category": doc.category,
                        "custom_label": rotulo,
                        "status": "RECEIVED",
                        "source": origem,
                        "uploaded_at": agora,
                        "uploaded_by": enviado_por,
                        "content_type": doc.content_type,
                        "file_size": len(conteudo),
                        "auto_fetched": True,
                    },
                    "$setOnInsert": {"id": str(uuid.uuid4())},
                },
                upsert=True,
            )
        except Exception as exc:
            logger.error("[GOV-ARQUIVO] Registo de '%s' falhou: %s", rotulo, type(exc).__name__, exc_info=True)
            resultado.falhados.append(rotulo)
            continue
        resultado.registados.append({
            "filename": doc.filename,
            "content_bytes": conteudo,
            "content_type": doc.content_type,
            "label": rotulo,
            "s3_path": s3_path,
        })
        logger.info("[GOV-ARQUIVO] '%s' arquivado (%d bytes) em %s", rotulo, len(conteudo), s3_path)

    if resultado.registados:
        await marcar_pedidos_satisfeitos(process_id, resultado.registados, origem=origem, enviado_por=enviado_por)
    return resultado


async def marcar_pedidos_satisfeitos(
    process_id: str, registados: list[dict], *, origem: str, enviado_por: str
) -> int:
    """Fecha os pedidos pendentes que os documentos obtidos satisfazem.

    Nunca levanta: o arquivo já aconteceu e um pedido por fechar corrige-se à
    mão, ao contrário de um erro que apagasse uma recolha bem sucedida.
    """
    try:
        pendentes = await db.documents.find(
            {"process_id": process_id, "status": {"$in": list(_PENDENTES)}}, {"_id": 0}
        ).to_list(200)
    except Exception as exc:
        logger.warning("[GOV-ARQUIVO] Não foi possível ler os pedidos pendentes: %s", type(exc).__name__)
        return 0

    fechados = 0
    ja_usados: set[str] = set()
    for registado in registados:
        if e_captura_de_ecra(registado["label"]):
            continue
        for pedido in pendentes:
            pedido_id = pedido.get("id")
            if not pedido_id or pedido_id in ja_usados:
                continue
            if not pedido_corresponde(registado["label"], pedido):
                continue
            ja_usados.add(pedido_id)
            try:
                await db.documents.update_one(
                    {"id": pedido_id, "process_id": process_id, "status": {"$in": list(_PENDENTES)}},
                    {"$set": {
                        "status": "UPLOADED",
                        "filename": registado["filename"],
                        "s3_path": registado["s3_path"],
                        "uploaded_at": datetime.now(timezone.utc).isoformat(),
                        "uploaded_by": enviado_por,
                        "auto_fetched": True,
                        "source": origem,
                    }},
                )
                fechados += 1
            except Exception as exc:
                logger.warning("[GOV-ARQUIVO] Pedido %s por fechar: %s", pedido_id, type(exc).__name__)
            break
    if fechados:
        logger.info("[GOV-ARQUIVO] %d pedido(s) fechado(s) para o processo %s", fechados, process_id)
    return fechados
