"""A etiqueta de processo no assunto de um email (QA-8, ponto 1).

Um email enviado a partir de um processo leva `[Ref: #<id>]` no fim do assunto; a resposta do
cliente traz-a de volta e a sincronização liga-a ao MESMO processo, mesmo que o cliente tenha
vários (o endereço sozinho não distingue). O formato antigo `[Proc-<id>]` continua a ser lido:
há emails já enviados em conversas em curso.

PURO onde pode: `extrair_id_da_etiqueta` e `etiqueta_do_processo` não tocam na base de dados;
`processo_da_etiqueta` só confirma que o processo existe (uma etiqueta inventada não liga nada).
"""
from __future__ import annotations

import re
from typing import Any, Optional

#: Os dois formatos lidos: o actual e o legado. O id é um uuid; a classe de caracteres é larga de
#: propósito para não depender do formato do id (ids antigos, `PROC-012`...).
_PADROES = (
    re.compile(r"\[\s*Ref\s*:\s*#\s*([^\]\s]+)\s*\]", re.IGNORECASE),
    re.compile(r"\[\s*Proc-([^\]\s]+)\s*\]", re.IGNORECASE),
)


def etiqueta_do_processo(process_id: str) -> str:
    """A etiqueta que se acrescenta ao assunto: `[Ref: #<id>]`."""
    return f"[Ref: #{process_id}]"


def extrair_id_da_etiqueta(assunto: Any) -> Optional[str]:
    """O id de processo nomeado no assunto, ou `None`. A primeira etiqueta ganha."""
    texto = str(assunto or "")
    achados = []
    for padrao in _PADROES:
        m = padrao.search(texto)
        if m:
            achados.append((m.start(), m.group(1).strip()))
    if not achados:
        return None
    return min(achados)[1] or None


def assunto_tem_a_etiqueta(assunto: Any, process_id: str) -> bool:
    """O assunto já nomeia ESTE processo (em qualquer dos formatos)? Evita etiquetar duas vezes."""
    return extrair_id_da_etiqueta(assunto) == str(process_id)


def sem_etiquetas(assunto: Any) -> str:
    """O assunto sem nenhuma etiqueta de processo (para reenvios a terceiros)."""
    texto = str(assunto or "")
    for padrao in _PADROES:
        texto = padrao.sub(" ", texto)
    return re.sub(r"\s{2,}", " ", texto).strip()


async def processo_da_etiqueta(database, assunto: Any) -> Optional[str]:
    """O processo a que a etiqueta do assunto aponta, se EXISTE; senão `None`."""
    candidato = extrair_id_da_etiqueta(assunto)
    if not candidato:
        return None
    existe = await database.processes.find_one({"id": candidato}, {"_id": 0, "id": 1})
    return candidato if existe else None
