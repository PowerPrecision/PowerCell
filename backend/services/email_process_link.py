"""A etiqueta de processo no assunto de um email (QA-8, ponto 1).

Um email enviado a partir de um processo leva `[Ref: #<id>]` no fim do assunto; a resposta do
cliente traz-a de volta e a sincronização liga-a ao MESMO processo, mesmo que o cliente tenha
vários (o endereço sozinho não distingue). O formato antigo `[Proc-<id>]` continua a ser lido:
há emails já enviados em conversas em curso.

PURO onde pode: `extrair_id_da_etiqueta` e `etiqueta_do_processo` não tocam na base de dados;
`processo_da_etiqueta` só confirma que o processo existe (uma etiqueta inventada não liga nada).

ETIQUETA CURTA (Flavio, 2026-11-04, pergunta 11a)
=================================================
O uuid de 36 caracteres tornava o assunto comprido e feio para o cliente. A etiqueta passa a
`[Ref: #<n.º do processo>]` (`etiqueta_curta_do_processo`); a do uuid continua a ser lida.

Um número ADIVINHA-SE, um uuid não: qualquer pessoa que escrevesse `[Ref: #1233]` ligava o seu
email ao processo de outro cliente. Por isso a etiqueta numérica SÓ liga quando o email tem um
endereço do processo (cliente, 2.º titular ou monitorizado) e quando o número é de UM só processo
activo. As respostas de terceiros (bancos, intermediários) continuam a ligar-se pela conversa
(In-Reply-To/References), que não depende da etiqueta.
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
    """A etiqueta longa (uuid): `[Ref: #<id>]`. Usada quando o processo não tem número."""
    return f"[Ref: #{process_id}]"


def etiqueta_numerica(process_number: Any) -> Optional[str]:
    """`[Ref: #<n.º>]` para um número de processo válido; `None` se não houver número."""
    try:
        numero = int(str(process_number).strip())
    except (TypeError, ValueError):
        return None
    return f"[Ref: #{numero}]" if numero > 0 else None


def _numero(candidato: Optional[str]) -> Optional[int]:
    """O candidato é um número de processo (só dígitos)?"""
    texto = str(candidato or "").strip()
    return int(texto) if texto.isdigit() and int(texto) > 0 else None


async def etiqueta_curta_do_processo(database, process_id: str) -> str:
    """A etiqueta que se acrescenta ao assunto: `[Ref: #<n.º>]`, ou a do uuid se não houver número."""
    processo = await database.processes.find_one(
        {"id": process_id}, {"_id": 0, "process_number": 1}
    )
    return etiqueta_numerica((processo or {}).get("process_number")) or etiqueta_do_processo(process_id)


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


def assunto_tem_a_etiqueta(assunto: Any, process_id: str, process_number: Any = None) -> bool:
    """O assunto já nomeia ESTE processo (uuid, legado ou número)? Evita etiquetar duas vezes."""
    candidato = extrair_id_da_etiqueta(assunto)
    if candidato is None:
        return False
    if candidato == str(process_id):
        return True
    numero = _numero(candidato)
    return numero is not None and etiqueta_numerica(process_number) == f"[Ref: #{numero}]"


def sem_etiquetas(assunto: Any) -> str:
    """O assunto sem nenhuma etiqueta de processo (para reenvios a terceiros)."""
    texto = str(assunto or "")
    for padrao in _PADROES:
        texto = padrao.sub(" ", texto)
    return re.sub(r"\s{2,}", " ", texto).strip()


async def processo_da_etiqueta(database, assunto: Any, enderecos: Any = None) -> Optional[str]:
    """O processo a que a etiqueta do assunto aponta, se EXISTE; senão `None`.

    `enderecos` = os endereços do email (de, para, cc). Só a etiqueta NUMÉRICA precisa deles:
    sem um endereço do processo entre eles, o número não liga nada (ver o cabeçalho).
    """
    candidato = extrair_id_da_etiqueta(assunto)
    if not candidato:
        return None
    existe = await database.processes.find_one({"id": candidato}, {"_id": 0, "id": 1})
    if existe:
        return candidato
    numero = _numero(candidato)
    if numero is None:
        return None
    candidatos = await database.processes.find(
        {"process_number": numero, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "client_email": 1, "monitored_emails": 1,
         "titular2_data": 1, "client_id": 1, "second_client_id": 1},
    ).to_list(2)
    if len(candidatos) != 1:
        return None  # nenhum, ou número repetido: ambíguo, não liga
    processo = candidatos[0]
    do_email = _enderecos_do_email(enderecos)
    if not do_email:
        return None
    if do_email & await _enderecos_do_processo(database, processo):
        return processo["id"]
    return None


def _enderecos_do_email(enderecos: Any) -> set:
    from services.email_process_crud import normalize_participant_email

    vistos = set()
    for valor in enderecos or []:
        endereco = normalize_participant_email(valor)
        if endereco:
            vistos.add(endereco)
    return vistos


async def _enderecos_do_processo(database, processo: dict) -> set:
    from services.email_process_crud import (
        collect_emails_from_client_doc,
        collect_emails_from_process_doc,
    )

    enderecos = collect_emails_from_process_doc(processo)
    ids = [processo.get(k) for k in ("client_id", "second_client_id") if processo.get(k)]
    if ids:
        clientes = await database.clients.find(
            {"id": {"$in": ids}},
            {"_id": 0, "email": 1, "contacto.email": 1, "titular2_data.email": 1},
        ).to_list(10)
        for cliente in clientes:
            enderecos |= collect_emails_from_client_doc(cliente)
    return enderecos


def enderecos_de(email: dict) -> list:
    """De, para e cc de um email (dict do sync), numa lista — para `processo_da_etiqueta`."""
    email = email or {}
    return [email.get("from_email"), *(email.get("to_emails") or []), *(email.get("cc_emails") or [])]
