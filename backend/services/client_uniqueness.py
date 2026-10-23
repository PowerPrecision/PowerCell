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

D-42/D-40 (Out 2026): O TELEMÓVEL SAIU, A IDENTIDADE PASSOU A SER GLOBAL
  A direcção decidiu: **só NIF e Email definem o cliente único** (um telemóvel
  partilha-se: família, casal, o escritório de um mediador). E o cliente é uma
  entidade GLOBAL — o mesmo NIF/Email não aparece em dois documentos, seja em
  que rede for —, mas a SEGREGAÇÃO do CRM mantém-se: cada equipa só vê o
  processo da sua rede (a janela do `client_window`). O que isto muda aqui:

  * a procura é global (`encontrar_cliente_duplicado` já não tem `rede`): a
    mesma pessoa com processos em duas empresas é UM cliente, com dois processos;
  * `resolver_identidade` decide o que fazer quando o NIF/Email já existe:
    `mesma_rede` (a equipa já o vê: 409 com o cliente, como sempre), `associar`
    (existe NOUTRA rede e quem pede PROVA conhecê-lo — NIF **e** Email do mesmo
    cliente: a rede passa a `redes_associadas` e ganha a janela, nunca o
    documento) e `opaco` (existe noutra rede e não há prova: 409 genérico, sem
    id, sem nome, sem campo);
  * **o risco que a direcção aceitou e fica escrito:** existir noutra rede é
    uma informação. O 409 do registo público e o `opaco` dizem-no a quem
    tentar; um NIF sozinho nunca abre a ficha de outra rede (por isso a prova
    exige os DOIS campos). A unicidade em si é imposta pelos índices únicos
    parciais de `db_indexes` — este módulo evita chegar a eles, não os substitui.

  Na EDIÇÃO só se verifica o que MUDOU (`so_o_que_mudou`): um cliente que já
  tem o telemóvel igual ao de outro (a regra é nova, a base é antiga) tem de
  poder corrigir a morada sem levar 409 por um campo em que não tocou.
====================================================================
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException

from database import db
from services.encryption import generate_email_hash, generate_nif_hash
from services.tenant_network import (
    CAMPO_REDE,
    CAMPO_REDES_ASSOCIADAS,
    TenantScope,
    build_network_scope_condition,
    documento_no_ambito,
    empresas_das_minhas_redes,
    rede_de_omissao,
)

logger = logging.getLogger(__name__)

CAMPO_NIF = "nif"
CAMPO_EMAIL = "email"

#: Os campos que definem o cliente único (D-42: o telemóvel NÃO é critério).
CAMPOS_UNICOS = (CAMPO_NIF, CAMPO_EMAIL)
ROTULOS = {CAMPO_NIF: "NIF", CAMPO_EMAIL: "Email"}

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


def construir_condicoes_de_duplicado(nif: Optional[str], email: Optional[str]) -> list[dict]:
    """Ramos ``$or`` que apanham um NIF/email já em uso (o telemóvel NÃO conta: D-42).

    Os valores entram JÁ SANITIZADOS (quem chama passa pelo
    `sanitize_nif`/`sanitize_email`): esta função decide onde procurar, não o
    que é válido.
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


def campos_em_conflito(existente: dict, nif: Optional[str], email: Optional[str]) -> list[str]:
    """Quais dos campos colidem — para a UI dizer QUAL, não "um dos dois"."""
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


def so_o_que_mudou(
    cliente: dict, nif: Optional[str], email: Optional[str],
) -> tuple[Optional[str], Optional[str]]:
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

    return nif_limpo, email_limpo


def _consulta_de_duplicados(nif: Optional[str], email: Optional[str], excluir_id: Optional[str]) -> Optional[dict]:
    condicoes = construir_condicoes_de_duplicado(nif, email)
    if not condicoes:
        return None
    consulta: dict[str, Any] = {"$or": condicoes, **CONDICAO_NAO_ELIMINADO}
    if excluir_id:
        consulta["id"] = {"$ne": excluir_id}
    return consulta


async def encontrar_clientes_duplicados(
    nif: Optional[str],
    email: Optional[str],
    *,
    excluir_id: Optional[str] = None,
    limite: int = 5,
) -> list[dict]:
    """Os clientes (de QUALQUER rede) que já usam este NIF ou email.

    A identidade é global (D-42): é a procura que a unicidade em base de dados
    também faz. Quem usa o resultado decide o que pode DIZER dele — este
    módulo devolve o documento inteiro e `resolver_identidade` é quem o filtra.
    """
    consulta = _consulta_de_duplicados(nif, email, excluir_id)
    if not consulta:
        return []
    return await db.clients.find(consulta, {"_id": 0}).to_list(limite)


async def encontrar_cliente_duplicado(
    nif: Optional[str],
    email: Optional[str],
    *,
    excluir_id: Optional[str] = None,
) -> Optional[dict]:
    """O cliente (de qualquer rede) que já usa este NIF ou email, se existir.

    `excluir_id` é o cliente que está a ser gravado: na edição ele casa
    consigo próprio e tem de sair da pesquisa.
    """
    candidatos = await encontrar_clientes_duplicados(nif, email, excluir_id=excluir_id, limite=1)
    return candidatos[0] if candidatos else None


async def cliente_e_da_rede(cliente: dict, rede: Optional[str]) -> bool:
    """O cliente é visível à equipa desta rede (carimbo no âmbito, ou pilha por carimbar da rede de omissão)?"""
    return documento_no_ambito(cliente, await ambito_de_unicidade(rede))


# Veredictos de `resolver_identidade`.
IDENTIDADE_NOVA = "novo"
IDENTIDADE_DA_MESMA_REDE = "mesma_rede"
IDENTIDADE_ASSOCIAR = "associar"
IDENTIDADE_OPACA = "opaco"


@dataclass(frozen=True)
class ResolucaoDeIdentidade:
    veredicto: str
    #: Só preenchido para `mesma_rede` (a equipa já vê o cliente) e `associar` (a prova foi dada).
    #: Em `opaco` é sempre `None`: o cliente de outra rede nunca sai desta função.
    cliente: Optional[dict] = None


async def resolver_identidade(
    nif: Optional[str],
    email: Optional[str],
    *,
    rede: Optional[str],
    excluir_id: Optional[str] = None,
) -> ResolucaoDeIdentidade:
    """O que fazer quando se quer criar um cliente com este NIF/email (D-42).

    1. nenhum cliente com NIF/email → ``novo``;
    2. algum é da MINHA rede → ``mesma_rede`` (a equipa já o vê; é o 409 de sempre,
       e ganha sempre a um de outra rede que também coincida);
    3. todos são de OUTRA rede:
         * há UM cliente que coincide nos DOIS campos (NIF e Email submetidos,
           os dois do mesmo cliente) → ``associar``: quem pede prova que conhece
           a pessoa, não só o número;
         * senão → ``opaco``. Um NIF sozinho nunca dá acesso à ficha de outra rede.
    """
    candidatos = await encontrar_clientes_duplicados(nif, email, excluir_id=excluir_id)
    if not candidatos:
        return ResolucaoDeIdentidade(IDENTIDADE_NOVA)

    for candidato in candidatos:
        if await cliente_e_da_rede(candidato, rede):
            return ResolucaoDeIdentidade(IDENTIDADE_DA_MESMA_REDE, candidato)

    if _nif_normalizado(nif) and _email_normalizado(email):
        provados = [c for c in candidatos if len(campos_em_conflito(c, nif, email)) == len(CAMPOS_UNICOS)]
        if len(provados) == 1 and len(candidatos) == 1:
            return ResolucaoDeIdentidade(IDENTIDADE_ASSOCIAR, provados[0])
    return ResolucaoDeIdentidade(IDENTIDADE_OPACA)


async def associar_rede_ao_cliente(client_id: str, rede: Optional[str]) -> bool:
    """Regista que a equipa desta rede passou a poder abrir a ficha deste cliente (como visitante).

    Só acrescenta (``$addToSet``): nunca reescreve um campo do cliente. Sem rede
    não há nada a registar — e `False` diz que a associação não aconteceu.
    """
    rede = (rede or "").strip()
    if not rede:
        return False
    resultado = await db.clients.update_one(
        {"id": client_id}, {"$addToSet": {CAMPO_REDES_ASSOCIADAS: rede}},
    )
    return bool(getattr(resultado, "matched_count", 1))


def _frase_dos_campos(campos: list[str]) -> str:
    rotulos = [ROTULOS[c] for c in CAMPOS_UNICOS if c in campos]
    if not rotulos:
        return "NIF ou Email"
    if len(rotulos) == 1:
        return rotulos[0]
    return ", ".join(rotulos[:-1]) + " e " + rotulos[-1]


def construir_erro_de_duplicado(
    existente: dict, nif: Optional[str], email: Optional[str],
) -> HTTPException:
    """O 409 com o payload que os formulários da EQUIPA já sabem ler.

    **409 e não 400**: o frontend precisa de distinguir "dados
    inválidos" de "cliente duplicado" para oferecer a acção "Usar
    cliente existente" em vez de pedir uma correcção que não existe.
    Só para o cliente DA MESMA REDE: para os outros, `erro_opaco_de_duplicado`.
    """
    nome_existente = existente.get("nome") or "Cliente existente"
    conflitos = campos_em_conflito(existente, nif, email) or [CAMPO_NIF, CAMPO_EMAIL]
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


#: A mensagem das portas sem direito a saber quem é. Genérica de propósito: não
#: diz QUAL dos campos coincidiu nem quem é o cliente (a porta é pública, ou o
#: cliente é de outra rede).
MENSAGEM_PUBLICA_DE_DUPLICADO = "Já existe um registo associado a este NIF ou Email."
CODIGO_PUBLICO_DE_DUPLICADO = "DUPLICATE_CLIENT"


def erro_publico_de_duplicado() -> dict:
    """O corpo do 409 do formulário público: sem `id`, sem nome, sem campos."""
    return {
        "success": False,
        "code": CODIGO_PUBLICO_DE_DUPLICADO,
        "detail": MENSAGEM_PUBLICA_DE_DUPLICADO,
    }


def erro_opaco_de_duplicado() -> HTTPException:
    """O 409 da equipa quando o cliente existe NOUTRA rede: sem `id`, sem nome, sem campos."""
    return HTTPException(
        status_code=409,
        detail={
            "message": MENSAGEM_PUBLICA_DE_DUPLICADO,
            "code": CODIGO_PUBLICO_DE_DUPLICADO,
        },
    )


async def assert_cliente_unico(
    nif: Optional[str],
    email: Optional[str],
    *,
    rede: Optional[str] = None,
    excluir_id: Optional[str] = None,
) -> None:
    """Recusa com 409 se o NIF ou email já pertencerem a outro cliente (EDIÇÃO).

    A identidade é global, mas o que se DIZ depende de quem pergunta: um cliente
    da mesma rede é nomeado (a equipa já o vê); o de outra rede é o 409 opaco.
    """
    candidatos = await encontrar_clientes_duplicados(nif, email, excluir_id=excluir_id)
    if not candidatos:
        return

    for candidato in candidatos:
        if await cliente_e_da_rede(candidato, rede):
            logger.info(
                "[UNICIDADE] Recusado: %s já em uso pelo cliente %s",
                campos_em_conflito(candidato, nif, email) or ["nif/email"],
                candidato.get("id"),
            )
            raise construir_erro_de_duplicado(candidato, nif, email)

    logger.info("[UNICIDADE] Recusado: NIF/email já em uso noutra rede (resposta opaca).")
    raise erro_opaco_de_duplicado()
