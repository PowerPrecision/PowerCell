"""O email novo criado a partir de um processo — assunto e dados do cliente (Flavio, 2026-11-04).

O PEDIDO
========
«Quando crio um email [na tab Emails do processo] o assunto tem de vir já preenchido e os dados do
cliente na mensagem.» Respostas às perguntas do documento de revisão:

* 1a — assunto `Processo #<n.º> — <Nome do cliente>`. A etiqueta de ligação (`[Ref: #<n.º>]`) NÃO
  vai aqui: é acrescentada no envio, como sempre, para não aparecer duas vezes.
* 2a — nome, NIF, telemóvel, email e n.º do processo; o 2.º titular também, se existir.
* 3a — um bloco «Dados do cliente» no TOPO da mensagem, editável; a assinatura entra no fim, no envio.
* 4a — o bloco vai sempre, mesmo quando o email é para o próprio cliente (quem escreve apaga).

Os dados vêm DECIFRADOS (`decrypt_sensitive_data`): um NIF `ENC:...` no corpo de um email seria lixo
para quem o lê. Por isso este texto nunca viaja no URL — o compositor pede-o ao servidor.

`montar_rascunho` é PURA (sem base de dados): o teste por regra corre sobre ela.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import HTTPException

from database import db

TITULO_DO_BLOCO = "Dados do cliente"


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def _numero_do_processo(processo: dict) -> str:
    numero = processo.get("process_number")
    return _texto(numero)


def _titular1(processo: dict) -> dict:
    pessoal = processo.get("personal_data") or {}
    return {
        "nome": _texto(pessoal.get("nome_completo") or pessoal.get("nome") or processo.get("client_name")),
        "nif": _texto(pessoal.get("nif") or processo.get("client_nif")),
        "telemovel": _texto(pessoal.get("telefone") or pessoal.get("phone") or processo.get("client_phone")),
        "email": _texto(pessoal.get("email") or processo.get("client_email")),
    }


def _titular2(processo: dict) -> Optional[dict]:
    t2 = processo.get("titular2_data") or {}
    nome = _texto(t2.get("nome_completo") or t2.get("name") or t2.get("nome"))
    if not nome:
        return None
    return {
        "nome": nome,
        "nif": _texto(t2.get("nif")),
        "telemovel": _texto(t2.get("telefone") or t2.get("phone")),
        "email": _texto(t2.get("email")),
    }


def assunto_do_processo(processo: dict) -> str:
    """`Processo #<n.º> — <Nome>` (1a). Sem número ou sem nome, fica a parte que existe."""
    numero = _numero_do_processo(processo)
    nome = _titular1(processo)["nome"]
    partes = []
    if numero:
        partes.append(f"Processo #{numero}")
    if nome:
        partes.append(nome)
    return " — ".join(partes)


def _linhas_do_titular(titular: dict) -> list[str]:
    linhas = []
    for rotulo, chave in (("Nome", "nome"), ("NIF", "nif"), ("Telemóvel", "telemovel"), ("Email", "email")):
        if titular.get(chave):
            linhas.append(f"{rotulo}: {titular[chave]}")
    return linhas


def bloco_dados_do_cliente(processo: dict) -> str:
    """O bloco «Dados do cliente» (2a). Campos vazios ficam de fora (nada de «N/A»)."""
    linhas = [f"{TITULO_DO_BLOCO}:"]
    numero = _numero_do_processo(processo)
    if numero:
        linhas.append(f"N.º do processo: {numero}")
    linhas.extend(_linhas_do_titular(_titular1(processo)))
    t2 = _titular2(processo)
    if t2:
        linhas.append("")
        linhas.append("2.º titular:")
        linhas.extend(_linhas_do_titular(t2))
    return "\n".join(linhas)


def montar_rascunho(processo: dict) -> dict:
    """Assunto + mensagem do email novo de um processo (já decifrado). PURA.

    A mensagem é o bloco no topo e duas linhas em branco para o utilizador escrever (3a).
    """
    return {
        "subject": assunto_do_processo(processo),
        "body": f"{bloco_dados_do_cliente(processo)}\n\n\n",
    }


async def run_compose_prefill(process_id: str, current_user: dict) -> dict:
    """O rascunho para o «+ Novo» da tab Emails. O acesso ao processo é verificado no router."""
    from services.process_service import decrypt_sensitive_data
    from services.role_scope import papel_concreto_do_utilizador

    papel = papel_concreto_do_utilizador(current_user) or current_user.get("role", "")
    if papel == "indexacao":
        raise HTTPException(status_code=403, detail="O perfil Index não tem acesso ao Webmail.")

    processo = await db.processes.find_one(
        {"id": process_id, "is_deleted": {"$ne": True}},
        {"_id": 0, "id": 1, "process_number": 1, "client_name": 1, "client_email": 1,
         "client_phone": 1, "client_nif": 1, "personal_data": 1, "titular2_data": 1,
         "company_id": 1},
    )
    if not processo:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
    rascunho = montar_rascunho(decrypt_sensitive_data(processo))
    rascunho["process_id"] = process_id
    rascunho["company_id"] = processo.get("company_id") or None
    return rascunho
