"""
====================================================================
UNICIDADE DE NIF E EMAIL DOS CLIENTES — UM PONTO ÚNICO
====================================================================
Lote 2, ponto 4.

O QUE ESTAVA FEITO, E O QUE FALTAVA
  `run_create_client` já recusava um NIF ou email repetido (409 com
  payload estruturado, PACOTE 10). `run_update_client` **não verificava
  nada** — sanitizava, encriptava e gravava. Bastava abrir um cliente,
  trocar o NIF para o de outro e gravar: ficavam dois clientes com o
  mesmo NIF, e nenhum erro em sítio nenhum.

  Pior do que o duplicado em si: é a EDIÇÃO que permite fabricar a
  colisão em cima de dados que já existem. A criação é a porta que
  estava fechada; a edição era a janela ao lado.

PORQUE É QUE ISTO VIVE NUM MÓDULO PRÓPRIO
  A regra é a mesma nas duas portas, logo não pode ser escrita duas
  vezes — é a forma do defeito que este projecto já viu em três eixos
  (campos de atribuição, papéis, chaves de cache). Escrita à mão na
  edição, divergiria da criação: bastava alguém acrescentar um ramo ao
  `$or` de um lado.

A PEÇA QUE DISTINGUE AS DUAS PORTAS: `excluir_id`
  Na edição, o cliente que se está a gravar **casa consigo próprio**.
  Sem `excluir_id`, gravar um cliente sem lhe tocar no NIF devolvia 409
  contra o próprio registo — uma guarda que impede a edição de tudo é
  pior do que guarda nenhuma, e é o erro óbvio de quem copia a condição
  da criação para a edição. É por isso o único parâmetro obrigatório a
  pensar, e tem teste próprio nos dois sentidos.

O ÍNDICE CEGO E O VALOR EM CLARO — OS DOIS RAMOS
  O NIF e o email são encriptados em repouso, com índice cego
  (`nif_hash` / `email_hash`) para dar para pesquisar. A condição leva
  os DOIS ramos: o hash apanha os registos migrados, o valor em claro
  apanha os antigos. Só o hash deixaria passar duplicados sobre dados
  não migrados, que são exactamente os mais velhos da base.

QUEM NÃO BLOQUEIA
  Clientes eliminados (`is_deleted=True` ou `status="eliminado"`) não
  bloqueiam: recriar um cliente apagado por engano não tem de obrigar a
  restaurá-lo primeiro. Regra herdada da criação, aqui preservada de
  propósito.

O QUE FICA DE FORA, E PORQUÊ
  O formulário PÚBLICO (`public_registration`) continua a inserir sem
  esta guarda. É uma decisão de produto e não um esquecimento: um 409
  numa porta externa perde a lead em vez de a tratar, e o que ali faz
  sentido é reaproveitar o cliente existente — o que muda o fluxo de
  negócio e não se decide aqui. Fica registado em `TECHNICAL_DEBT.md`
  com a decisão em aberto.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from services.encryption import generate_email_hash, generate_nif_hash

logger = logging.getLogger(__name__)

CAMPO_NIF = "nif"
CAMPO_EMAIL = "email"

# Um cliente eliminado não bloqueia a reutilização do NIF/email.
CONDICAO_NAO_ELIMINADO: dict[str, Any] = {
    "is_deleted": {"$ne": True},
    "status": {"$ne": "eliminado"},
}


def _email_normalizado(email: Optional[str]) -> Optional[str]:
    texto = (email or "").strip().lower()
    return texto or None


def _nif_normalizado(nif: Optional[str]) -> Optional[str]:
    texto = (nif or "").strip()
    return texto or None


def construir_condicoes_de_duplicado(
    nif: Optional[str],
    email: Optional[str],
) -> list[dict]:
    """Ramos ``$or`` que apanham um NIF/email já em uso.

    Os valores entram JÁ SANITIZADOS (quem chama passa pelo
    `sanitize_nif`/`sanitize_email`): esta função decide onde procurar,
    não o que é válido.
    """
    condicoes: list[dict] = []

    nif_limpo = _nif_normalizado(nif)
    if nif_limpo:
        hash_do_nif = generate_nif_hash(nif_limpo)
        if hash_do_nif:
            condicoes.append({"dados_pessoais.nif_hash": hash_do_nif})
        # Dados antigos, por migrar: o NIF ainda está em claro.
        condicoes.append({"dados_pessoais.nif": nif_limpo})

    email_limpo = _email_normalizado(email)
    if email_limpo:
        hash_do_email = generate_email_hash(email_limpo)
        if hash_do_email:
            condicoes.append({"contacto.email_hash": hash_do_email})
        condicoes.append({"contacto.email": email_limpo})

    return condicoes


def campos_em_conflito(
    existente: dict,
    nif: Optional[str],
    email: Optional[str],
) -> list[str]:
    """Quais dos dois campos colidem — para a UI dizer QUAL, não "um dos dois".

    Sem isto a mensagem é "NIF ou Email", e quem está a preencher não
    sabe qual dos campos corrigir.
    """
    dados = existente.get("dados_pessoais") or {}
    contacto = existente.get("contacto") or {}
    conflitos: list[str] = []

    nif_limpo = _nif_normalizado(nif)
    if nif_limpo:
        hash_do_nif = generate_nif_hash(nif_limpo)
        if (hash_do_nif and dados.get("nif_hash") == hash_do_nif) or dados.get("nif") == nif_limpo:
            conflitos.append(CAMPO_NIF)

    email_limpo = _email_normalizado(email)
    if email_limpo:
        hash_do_email = generate_email_hash(email_limpo)
        se_email = (hash_do_email and contacto.get("email_hash") == hash_do_email)
        if se_email or _email_normalizado(contacto.get("email")) == email_limpo:
            conflitos.append(CAMPO_EMAIL)

    return conflitos


async def encontrar_cliente_duplicado(
    nif: Optional[str],
    email: Optional[str],
    *,
    excluir_id: Optional[str] = None,
) -> Optional[dict]:
    """O cliente que já usa este NIF ou email, se existir.

    `excluir_id` é o cliente que está a ser gravado: na edição ele casa
    consigo próprio e tem de sair da pesquisa.
    """
    condicoes = construir_condicoes_de_duplicado(nif, email)
    if not condicoes:
        return None

    consulta: dict[str, Any] = {"$or": condicoes, **CONDICAO_NAO_ELIMINADO}
    if excluir_id:
        consulta["id"] = {"$ne": excluir_id}

    return await db.clients.find_one(consulta)


def construir_erro_de_duplicado(
    existente: dict,
    nif: Optional[str],
    email: Optional[str],
) -> HTTPException:
    """O 409 com o payload que os formulários já sabem ler.

    **409 e não 400**: o frontend precisa de distinguir "dados
    inválidos" de "cliente duplicado" para oferecer a acção "Usar
    cliente existente" em vez de pedir uma correcção que não existe.
    """
    nome_existente = existente.get("nome") or "Cliente existente"
    conflitos = campos_em_conflito(existente, nif, email) or [CAMPO_NIF, CAMPO_EMAIL]

    if conflitos == [CAMPO_NIF]:
        mensagem = f"Já existe um cliente com este NIF: {nome_existente}"
    elif conflitos == [CAMPO_EMAIL]:
        mensagem = f"Já existe um cliente com este Email: {nome_existente}"
    else:
        mensagem = f"Já existe um cliente com este NIF e Email: {nome_existente}"

    return HTTPException(
        status_code=409,
        detail={
            "message": mensagem,
            "existing_client_id": existente.get("id"),
            "existing_client_name": nome_existente,
            "matched_fields": conflitos,
        },
    )


async def assert_cliente_unico(
    nif: Optional[str],
    email: Optional[str],
    *,
    excluir_id: Optional[str] = None,
) -> None:
    """Recusa com 409 se o NIF ou o email já pertencerem a outro cliente."""
    existente = await encontrar_cliente_duplicado(nif, email, excluir_id=excluir_id)
    if not existente:
        return

    logger.info(
        "[UNICIDADE] Recusado: %s já em uso pelo cliente %s",
        campos_em_conflito(existente, nif, email) or ["nif/email"],
        existente.get("id"),
    )
    raise construir_erro_de_duplicado(existente, nif, email)
