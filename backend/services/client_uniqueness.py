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

D-38 (Out 2026): TRÊS CAMPOS, UMA REDE, E O FORMULÁRIO PÚBLICO ENTROU
  A regra de negócio passou a ser **NIF, Email e Telemóvel não se repetem
  dentro da mesma REDE** — e a procura vive na rede de destino, não na base
  de dados inteira. Duas consequências que esta guarda corrige:

  * a verificação era GLOBAL: o 409 devolvia o `id` e o nome do cliente
    existente **de qualquer rede**, ou seja, um utilizador da Domus
    descobria clientes da Power só por tentar criar um com o mesmo NIF;
  * o formulário PÚBLICO ficou de fora ("reaproveitar o cliente existente")
    e era pior: um anónimo actualizava em silêncio os dados de quem já
    existia. Agora recusa com 409 — sem `id` nem nome, porque a porta é
    anónima — e o frontend diz o que se passou.

  `rede=None` (quem chama não sabe a rede) só alcança a pilha por carimbar:
  esquecer a rede fecha, não abre.

  Na EDIÇÃO só se verifica o que MUDOU (`so_o_que_mudou`): um cliente que já
  tem o telemóvel igual ao de outro (a regra é nova, a base é antiga) tem de
  poder corrigir a morada sem levar 409 por um campo em que não tocou.
====================================================================
"""
from __future__ import annotations

import logging
import re
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from services.encryption import generate_email_hash, generate_nif_hash, generate_telefone_hash
from services.tenant_network import (
    CAMPO_REDE,
    TenantScope,
    build_network_scope_condition,
    com_isolamento,
    empresas_das_minhas_redes,
    rede_de_omissao,
)

logger = logging.getLogger(__name__)

CAMPO_NIF = "nif"
CAMPO_EMAIL = "email"
CAMPO_TELEFONE = "telefone"

#: Os três campos que não se repetem na rede, pela ordem em que se dizem ao utilizador.
CAMPOS_UNICOS = (CAMPO_NIF, CAMPO_EMAIL, CAMPO_TELEFONE)
ROTULOS = {CAMPO_NIF: "NIF", CAMPO_EMAIL: "Email", CAMPO_TELEFONE: "Telemóvel"}

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


def telefones_candidatos(telefone: Optional[str]) -> list[str]:
    """As formas nacionais de um telemóvel que o índice cego pode ter guardado.

    O índice cego (`contacto.telefone_hash`) é calculado sobre os dígitos tal
    como foram escritos: `912 345 678` e `+351 912 345 678` dão hashes
    diferentes. A procura tenta as duas formas (com e sem o indicativo 351).
    Um valor com menos de 9 dígitos não identifica ninguém e não bloqueia.
    """
    digitos = re.sub(r"\D", "", str(telefone or ""))
    if digitos.startswith("00"):
        digitos = digitos[2:]
    if len(digitos) == 12 and digitos.startswith("351"):
        digitos = digitos[3:]
    if len(digitos) < 9:
        return []
    candidatos = [digitos]
    if len(digitos) == 9:
        candidatos.append("351" + digitos)
    return candidatos


async def ambito_de_unicidade(rede: Optional[str]) -> TenantScope:
    """Onde a procura de duplicados tem o direito de olhar (D-32/D-38).

    * a rede e as empresas dela (um cliente só com a empresa gravada, criado
      entre o carimbo da empresa e o da rede, ainda é da rede dela);
    * a pilha por carimbar, mas **só** quando a rede é a de omissão (é a ela
      que a pilha pertence); sem `TENANT_DEFAULT_NETWORK_ID` (dev/CI) mantém-se
      o comportamento anterior;
    * `rede=None` («não sei de que rede é») só alcança a pilha por carimbar.
    """
    rede = (rede or "").strip()
    if not rede:
        return TenantScope(inclui_rede_de_omissao=True)
    omissao = rede_de_omissao()
    empresas = await empresas_das_minhas_redes(TenantScope(network_ids=(rede,)))
    return TenantScope(
        network_ids=(rede,),
        company_ids=tuple(empresas),
        inclui_rede_de_omissao=(not omissao) or rede == omissao,
    )


async def condicao_de_unicidade(rede: Optional[str]) -> dict:
    return build_network_scope_condition(await ambito_de_unicidade(rede))


def rede_do_cliente(cliente: Optional[dict]) -> Optional[str]:
    """A rede de um cliente já gravado (a pilha por carimbar → a de omissão)."""
    carimbo = str((cliente or {}).get(CAMPO_REDE) or "").strip()
    return carimbo or (rede_de_omissao() or None)


def construir_condicoes_de_duplicado(
    nif: Optional[str],
    email: Optional[str],
    telefone: Optional[str] = None,
) -> list[dict]:
    """Ramos ``$or`` que apanham um NIF/email/telemóvel já em uso.

    Os valores entram JÁ SANITIZADOS (quem chama passa pelo
    `sanitize_nif`/`sanitize_email`/`sanitize_phone`): esta função decide onde
    procurar, não o que é válido.
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

    candidatos = telefones_candidatos(telefone)
    for candidato in candidatos:
        hash_do_telefone = generate_telefone_hash(candidato)
        if hash_do_telefone:
            condicoes.append({"contacto.telefone_hash": hash_do_telefone})
    if candidatos:
        # Dados antigos, por migrar: o telemóvel ainda está em claro, tal como foi escrito.
        condicoes.append({"contacto.telefone": str(telefone).strip()})

    return condicoes


def campos_em_conflito(
    existente: dict,
    nif: Optional[str],
    email: Optional[str],
    telefone: Optional[str] = None,
) -> list[str]:
    """Quais dos campos colidem — para a UI dizer QUAL, não "um dos três".

    Sem isto a mensagem é genérica, e quem está a preencher não sabe qual dos
    campos corrigir.
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

    candidatos = telefones_candidatos(telefone)
    if candidatos:
        hashes = {generate_telefone_hash(c) for c in candidatos}
        if contacto.get("telefone_hash") in hashes or contacto.get("telefone") == str(telefone).strip():
            conflitos.append(CAMPO_TELEFONE)

    return conflitos


def so_o_que_mudou(
    cliente: dict,
    nif: Optional[str],
    email: Optional[str],
    telefone: Optional[str],
) -> tuple[Optional[str], Optional[str], Optional[str]]:
    """Na EDIÇÃO, os valores submetidos que DIFEREM do que o cliente já tem.

    Compara pelo índice cego (o valor em base está encriptado) e, sem índice,
    pelo valor em claro. Um campo em que não se tocou não pode devolver 409 só
    porque a base antiga já tem o duplicado.
    """
    dados = cliente.get("dados_pessoais") or {}
    contacto = cliente.get("contacto") or {}

    nif_limpo = _nif_normalizado(nif)
    if nif_limpo and (
        (generate_nif_hash(nif_limpo) and dados.get("nif_hash") == generate_nif_hash(nif_limpo))
        or dados.get("nif") == nif_limpo
    ):
        nif_limpo = None

    email_limpo = _email_normalizado(email)
    if email_limpo and (
        (generate_email_hash(email_limpo) and contacto.get("email_hash") == generate_email_hash(email_limpo))
        or _email_normalizado(contacto.get("email")) == email_limpo
    ):
        email_limpo = None

    telefone_limpo = (telefone or "").strip() or None
    if telefone_limpo:
        hashes = {generate_telefone_hash(c) for c in telefones_candidatos(telefone_limpo)}
        if contacto.get("telefone_hash") in hashes or contacto.get("telefone") == telefone_limpo:
            telefone_limpo = None

    return nif_limpo, email_limpo, telefone_limpo


async def encontrar_cliente_duplicado(
    nif: Optional[str],
    email: Optional[str],
    telefone: Optional[str] = None,
    *,
    rede: Optional[str] = None,
    excluir_id: Optional[str] = None,
) -> Optional[dict]:
    """O cliente DA MESMA REDE que já usa este NIF, email ou telemóvel, se existir.

    `rede` é a rede de destino (a do carimbo do cliente a gravar); sem ela só
    se alcança a pilha por carimbar. `excluir_id` é o cliente que está a ser
    gravado: na edição ele casa consigo próprio e tem de sair da pesquisa.
    """
    condicoes = construir_condicoes_de_duplicado(nif, email, telefone)
    if not condicoes:
        return None

    consulta: dict[str, Any] = {"$or": condicoes, **CONDICAO_NAO_ELIMINADO}
    if excluir_id:
        consulta["id"] = {"$ne": excluir_id}

    return await db.clients.find_one(com_isolamento(await condicao_de_unicidade(rede), consulta))


def _frase_dos_campos(campos: list[str]) -> str:
    rotulos = [ROTULOS[c] for c in CAMPOS_UNICOS if c in campos]
    if not rotulos:
        return "NIF, Email ou Telemóvel"
    if len(rotulos) == 1:
        return rotulos[0]
    return ", ".join(rotulos[:-1]) + " e " + rotulos[-1]


def construir_erro_de_duplicado(
    existente: dict,
    nif: Optional[str],
    email: Optional[str],
    telefone: Optional[str] = None,
) -> HTTPException:
    """O 409 com o payload que os formulários da EQUIPA já sabem ler.

    **409 e não 400**: o frontend precisa de distinguir "dados
    inválidos" de "cliente duplicado" para oferecer a acção "Usar
    cliente existente" em vez de pedir uma correcção que não existe.
    Só para a equipa: a porta anónima usa `erro_publico_de_duplicado`.
    """
    nome_existente = existente.get("nome") or "Cliente existente"
    conflitos = campos_em_conflito(existente, nif, email, telefone) or [CAMPO_NIF, CAMPO_EMAIL]
    frase = _frase_dos_campos(conflitos)

    return HTTPException(
        status_code=409,
        detail={
            "message": f"Já existe um cliente com este {frase}: {nome_existente}",
            "existing_client_id": existente.get("id"),
            "existing_client_name": nome_existente,
            "matched_fields": conflitos,
        },
    )


#: A mensagem da porta anónima. Genérica de propósito: não diz QUAL dos três
#: campos coincidiu nem quem é o cliente (a porta é pública).
MENSAGEM_PUBLICA_DE_DUPLICADO = "Já existe um registo associado a este NIF, Email ou Telemóvel."
CODIGO_PUBLICO_DE_DUPLICADO = "DUPLICATE_CLIENT"


def erro_publico_de_duplicado() -> dict:
    """O corpo do 409 do formulário público: sem `id`, sem nome, sem campos."""
    return {
        "success": False,
        "code": CODIGO_PUBLICO_DE_DUPLICADO,
        "detail": MENSAGEM_PUBLICA_DE_DUPLICADO,
    }


async def assert_cliente_unico(
    nif: Optional[str],
    email: Optional[str],
    telefone: Optional[str] = None,
    *,
    rede: Optional[str] = None,
    excluir_id: Optional[str] = None,
) -> None:
    """Recusa com 409 se o NIF, email ou telemóvel já pertencerem a outro cliente DA REDE."""
    existente = await encontrar_cliente_duplicado(
        nif, email, telefone, rede=rede, excluir_id=excluir_id,
    )
    if not existente:
        return

    logger.info(
        "[UNICIDADE] Recusado: %s já em uso pelo cliente %s",
        campos_em_conflito(existente, nif, email, telefone) or ["nif/email/telefone"],
        existente.get("id"),
    )
    raise construir_erro_de_duplicado(existente, nif, email, telefone)
