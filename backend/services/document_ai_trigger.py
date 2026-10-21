"""
====================================================================
IA AUTOMÁTICA ao cair um ficheiro na pasta `Index` (Out 2026)
====================================================================
A direcção retirou o botão manual da IA aos perfis operacionais (custos da
API — `document_ai_access`). O fluxo normal tem por isso de andar SEM cliques:
quando um documento cai na `Index` a categorização/OCR corre sozinha, em
background, uma vez por ficheiro.

OS TRÊS ARRANQUES (e quem os dispara)
  1. **Staff / Indexador faz upload** — `document_upload` (multipart),
     `document_direct_upload` (pré-assinado) e o «Arquivar no Processo» do
     Webmail: o desvio inteligente (`document_intake.planear_entrada`) manda o
     ficheiro para a `Index` e para a fila da IA quando o processo ainda não
     passou a indexação. (Já existia.)
  2. **Parceiro** — `partner_upload_ops`, pelo mesmo desvio. (Já existia.)
  3. **Cliente submete pelo Portal** — `portal_upload_ops.run_confirm_portal_upload`.
     **Faltava**: o Portal força SEMPRE a `Index`, regista o documento e termina;
     nenhuma fila, nenhuma IA. Hoje chama `agendar_ia_da_entrada`.

REGRAS QUE NÃO SE PODEM PERDER
  * **Uma vez por ficheiro.** Um `confirm-upload` repetido (retry do browser,
    duplo clique) não paga duas chamadas ao modelo: se o ficheiro já está
    categorizado, salta-se.
  * **Tecto de tamanho.** O Portal recebe o que o cliente enviar (até ao limite
    do tipo) e a IA lê o ficheiro INTEIRO para memória; acima de
    `TAMANHO_MAXIMO_PARA_IA` fica na fila, sem IA, com `warning`.
  * **Nunca falha o upload.** O ficheiro já está gravado e validado quando isto
    corre; tudo é observação (registo da fila, leitura, IA) e nada propaga.
  * **No Portal a IA NÃO satisfaz pedidos** (`satisfazer_pedidos=False`): o
    cliente declarou a que pedido o ficheiro responde e o servidor já o tratou;
    deixar a IA procurar outro pedido pendente dava o mesmo ficheiro duas vezes.
  * **A IA só lê, nunca grava na ficha**: o resultado vai para
    `document_metadata`; quem aplica dados ao processo continua a ser o
    consultor, depois de confirmar no diálogo de revisão.
  * Referência forte à task (`spawn_background_task`): um `create_task` cru
    pode ser recolhido pelo GC a meio e o ficheiro ficava para sempre na fila.
====================================================================
"""
from __future__ import annotations

import asyncio
import logging
import os
from typing import Optional

from database import db
from services.background_tasks import spawn_background_task
from services.document_intake import registar_na_fila_da_ia
from services.process_ai_log import registar_accao_ia
from services.s3_storage import s3_service

logger = logging.getLogger(__name__)

#: Acima disto o ficheiro fica na fila SEM IA (a leitura é para memória e o custo,
#: por página). 20 MB cobre qualquer PDF/imagem de documentação real.
TAMANHO_MAXIMO_PARA_IA = 20 * 1024 * 1024


def ia_da_entrada_ligada() -> bool:
    """Interruptor. `TESTING=true` desliga-o (um upload simulado por outro teste não pode
    ir ao S3 nem ao modelo) salvo `IA_DA_ENTRADA_ENABLED=true`; `IA_DA_ENTRADA_ENABLED=false`
    desliga-o em qualquer ambiente (corte de custos de emergência, sem deploy de código)."""
    explicito = os.environ.get("IA_DA_ENTRADA_ENABLED", "").strip().lower()
    if explicito in ("true", "1", "yes"):
        return True
    if explicito in ("false", "0", "no"):
        return False
    return os.environ.get("TESTING", "").strip().lower() != "true"


async def _ja_foi_categorizado(s3_path: str) -> bool:
    try:
        existente = await db.document_metadata.find_one(
            {"s3_path": s3_path}, {"_id": 0, "is_categorized": 1}
        )
    except Exception as exc:  # pragma: no cover — degradação graciosa
        logger.warning("[IA-AUTO] Não foi possível verificar %s: %s", s3_path, exc)
        return False
    return bool(existente and existente.get("is_categorized") is True)


async def correr_ia_da_entrada(
    *,
    process_id: Optional[str],
    client_name: str,
    s3_path: str,
    filename: str,
    tamanho: Optional[int] = None,
    satisfazer_pedidos: bool = True,
    origem: Optional[str] = None,
) -> str:
    """Lê o ficheiro e corre a categorização. Devolve o que fez (para o log e os testes):
    ``"categorizado"`` | ``"ja_categorizado"`` | ``"demasiado_grande"`` | ``"ilegivel"`` | ``"erro"``.
    Nunca levanta.
    """
    try:
        if await _ja_foi_categorizado(s3_path):
            logger.info("[IA-AUTO] %s já categorizado — sem nova chamada ao modelo", s3_path)
            await registar_accao_ia(
                process_id=process_id, accao="categorizar", estado="saltado", gatilho="automatico",
                ficheiro=filename, s3_path=s3_path, origem=origem, motivo="ja_categorizado",
            )
            return "ja_categorizado"

        if tamanho is None:
            estado, meta = await asyncio.to_thread(s3_service.head_object_metadata, s3_path)
            tamanho = (meta or {}).get("tamanho") if estado == "ok" else None
        if isinstance(tamanho, int) and tamanho > TAMANHO_MAXIMO_PARA_IA:
            logger.warning(
                "[IA-AUTO] %s tem %s bytes (> %s): fica na fila sem IA",
                s3_path, tamanho, TAMANHO_MAXIMO_PARA_IA,
            )
            await registar_accao_ia(
                process_id=process_id, accao="categorizar", estado="saltado", gatilho="automatico",
                ficheiro=filename, s3_path=s3_path, origem=origem, motivo="demasiado_grande",
            )
            return "demasiado_grande"

        conteudo = await asyncio.to_thread(s3_service.get_file_content, s3_path)
        if not conteudo:
            logger.warning("[IA-AUTO] Não foi possível ler %s para a IA", s3_path)
            await registar_accao_ia(
                process_id=process_id, accao="categorizar", estado="falha", gatilho="automatico",
                ficheiro=filename, s3_path=s3_path, origem=origem, motivo="ilegivel",
            )
            return "ilegivel"

        from services.document_auto_categorize import auto_categorize_document_background

        await auto_categorize_document_background(
            process_id=process_id,
            client_name=client_name,
            s3_path=s3_path,
            filename=filename,
            file_content=conteudo,
            satisfazer_pedidos=satisfazer_pedidos,
            origem=origem,
        )
        return "categorizado"
    except Exception as exc:
        logger.error("[IA-AUTO] Falha na IA de %s: %s: %s", s3_path, type(exc).__name__, exc)
        await registar_accao_ia(
            process_id=process_id, accao="categorizar", estado="falha", gatilho="automatico",
            ficheiro=filename, s3_path=s3_path, origem=origem, motivo="erro_interno",
        )
        return "erro"


async def agendar_ia_da_entrada(
    *,
    process_id: Optional[str],
    client_name: str,
    s3_path: str,
    filename: str,
    origem: str,
    tamanho: Optional[int] = None,
    satisfazer_pedidos: bool = True,
) -> None:
    """Regista o ficheiro na fila da IA e lança a categorização em background.

    Para os fluxos que NÃO têm os bytes à mão (o Portal: o cliente enviou-os
    directamente para o S3). Nunca levanta.
    """
    if not ia_da_entrada_ligada():
        logger.info("[IA-AUTO] Desligada (TESTING/IA_DA_ENTRADA_ENABLED): %s sem fila nem IA", s3_path)
        return
    try:
        await registar_na_fila_da_ia(
            process_id=process_id,
            client_name=client_name,
            s3_path=s3_path,
            filename=filename,
            origem=origem,
        )
        spawn_background_task(
            correr_ia_da_entrada(
                process_id=process_id,
                client_name=client_name,
                s3_path=s3_path,
                filename=filename,
                tamanho=tamanho,
                satisfazer_pedidos=satisfazer_pedidos,
                origem=origem,
            ),
            name=f"ia-da-entrada:{filename}",
        )
    except Exception as exc:  # pragma: no cover — degradação graciosa
        logger.warning("[IA-AUTO] Não foi possível agendar a IA de %s: %s", s3_path, exc)
