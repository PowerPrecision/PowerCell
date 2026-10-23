"""
====================================================================
COLISÃO B2B (CROSS-NETWORK): QUEM É O MESMO CLIENTE NA REDE DE DESTINO
====================================================================
Quando um registo vindo de FORA da rede (hoje: a lead que um parceiro
submete a uma «Empresa de Destino») chega à equipa do destino, o cliente pode
já existir lá. Duas perguntas, duas regras.

1. QUEM É O MESMO CLIENTE — HIERARQUIA DE IDENTIFICAÇÃO
   * Procura-se **primeiro pelo NIF**. Se o NIF coincide, é o mesmo cliente.
   * Só se o NIF vier **vazio/ausente** se procura pelo **Email**.
   * Um NIF PRESENTE que não coincide com ninguém NÃO cai para o email:
     o NIF identifica a pessoa, e o mesmo email com outro NIF é outra pessoa
     (uma família partilha o email). Fica como «possível duplicado» para a
     triagem decidir — que é o que a submissão já fazia.
   * O telemóvel nunca identifica: partilha-se (família, escritório).
   * A procura vive na rede de destino e só vê clientes activos (a mesma
     condição do D-38, `client_uniqueness`).

2. O QUE SE FAZ COM UM MATCH — A REDE DE DESTINO É SOBERANA
   Associa-se o registo ao cliente existente, mas **nada do que está gravado
   no destino é alterado**: nem o email, nem o telemóvel, nem o NIF, nem o
   nome, nem o estado de lead. (Re-marcar o cliente como lead novo foi
   precisamente o defeito do formulário público que o D-32 corrigiu.)
   O que o destino fica a saber — só a equipa, nunca o parceiro — vai numa
   entrada ACRESCENTADA a `partner_leads`, com os NOMES dos campos em que os
   contactos enviados divergem dos gravados (nunca os valores: o destino já
   tem os seus, e os de fora são dados pessoais de quem a equipa não tem
   relação).

   O parceiro não vê diferença nenhuma: o registo dele passa a «submetido»
   como qualquer outro, sem o `id` do cliente existente (seria um oráculo
   de «este cliente já existe na rede X»).

O QUE NÃO SE FAZ
   * Não se **move** nem se **re-aponta** nada: os ficheiros que o parceiro
     enviou ficam na pasta do registo dele (mover objectos S3 foi o que
     partiu 205 ligações no Épico 10). A entrada guarda `pasta_dos_documentos`
     para a consolidação manual (`s3_relink`).
   * Não se atribui o parceiro ao cliente existente (`submitted_by_partner_id`):
     o parceiro passaria a ver, no portal dele, um cliente que não é seu.
====================================================================
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from services.client_uniqueness import (
    CAMPOS_UNICOS,
    campos_em_conflito,
    cliente_e_da_rede,
    encontrar_clientes_duplicados,
    telefones_candidatos,
    so_o_que_mudou,
)
from services.encryption import generate_telefone_hash

logger = logging.getLogger(__name__)

POR_NIF = "nif"
POR_EMAIL = "email"

#: Os contactos que a rede de destino preserva. O NIF e o nome também não se
#: tocam, mas só os contactos podem divergir sem que o NIF seja a chave.
CAMPOS_DE_CONTACTO = ("email", "telefone")


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def dados_de_identificacao(lead: dict) -> tuple[str, str, str]:
    """(NIF, email, telemóvel) de uma lead JÁ desencriptada, aparados."""
    dados = lead.get("dados_pessoais") or {}
    contacto = lead.get("contacto") or {}
    return _texto(dados.get("nif")), _texto(contacto.get("email")), _texto(contacto.get("telefone"))


class IdentidadeEmConflito(Exception):
    """O NIF/Email da lead já pertence a um cliente de OUTRA rede e a lead não prova conhecê-lo.

    Criar outro cliente quebraria a identidade global (D-42); associar sem prova
    daria a uma rede a janela sobre um cliente que não é dela. A lead fica retida.
    """


async def encontrar_cliente_de_destino(
    lead: dict, *, rede: Optional[str],
) -> tuple[Optional[dict], Optional[str]]:
    """O cliente que É este, e por que critério. O NIF decide primeiro; o email só entra sem NIF.

    ``lead`` vem desencriptada. Devolve ``(cliente, "nif"|"email")`` ou
    ``(None, None)``. A identidade é GLOBAL (D-42):

    * se o cliente é da rede de destino, associa-se (como sempre);
    * se é de OUTRA rede, só se associa com a prova de NIF **e** Email do mesmo
      cliente — e o chamador acrescenta a rede a ``redes_associadas``;
    * sem essa prova levanta ``IdentidadeEmConflito`` (nunca devolve o cliente
      de outra rede a quem não o provou).
    """
    nif, email, _telefone = dados_de_identificacao(lead)
    if nif:
        por, candidatos = POR_NIF, await encontrar_clientes_duplicados(nif, None)
    elif email:
        por, candidatos = POR_EMAIL, await encontrar_clientes_duplicados(None, email)
    else:
        return None, None
    if not candidatos:
        if nif and email and await encontrar_clientes_duplicados(None, email, limite=1):
            # NIF novo com o email de OUTRA pessoa: o email é único (D-42), logo não nasce um
            # segundo cliente com ele. Antes ficava «possível duplicado»; agora é um conflito
            # que uma pessoa resolve (a lead fica retida e a gestão é avisada).
            raise IdentidadeEmConflito(POR_EMAIL)
        return None, None

    for candidato in candidatos:
        if await cliente_e_da_rede(candidato, rede):
            return candidato, por

    if nif and email and len(candidatos) == 1:
        if len(campos_em_conflito(candidatos[0], nif, email)) == len(CAMPOS_UNICOS):
            return candidatos[0], por
    raise IdentidadeEmConflito(por)


def _telefone_diverge(existente: dict, telefone: Optional[str]) -> bool:
    """O telemóvel enviado difere do gravado? (O telemóvel já não identifica; continua a ser contacto.)"""
    candidatos = telefones_candidatos(telefone)
    if not candidatos:
        return False
    contacto = existente.get("contacto") or {}
    hashes = {generate_telefone_hash(c) for c in candidatos}
    return not (contacto.get("telefone_hash") in hashes or contacto.get("telefone") == str(telefone).strip())


def campos_divergentes(existente: dict, lead: dict) -> list[str]:
    """Quais dos contactos enviados DIFEREM dos gravados no destino (só nomes)."""
    _nif, email, telefone = dados_de_identificacao(lead)
    _n, email_novo = so_o_que_mudou(existente, None, email or None)
    divergentes = []
    if email_novo:
        divergentes.append("email")
    if _telefone_diverge(existente, telefone or None):
        divergentes.append("telefone")
    return divergentes


def entrada_de_associacao(
    *, lead: dict, existente: dict, por: str, comprovativo: Optional[dict], quando: str,
) -> dict:
    """A entrada acrescentada ao cliente existente. Sem NENHUM dado pessoal."""
    return {
        "lead_id": lead.get("id"),
        "partner_id": lead.get("submitted_by_partner_id"),
        "partner_name": lead.get("submitted_by_partner_name"),
        "empresa_destino": lead.get("company_name"),
        "associada_por": por,
        "campos_divergentes": campos_divergentes(existente, lead),
        "comprovativo": {
            "file_id": (comprovativo or {}).get("file_id"),
            "filename": (comprovativo or {}).get("filename"),
            "uploaded_at": (comprovativo or {}).get("uploaded_at"),
        },
        # Os ficheiros do parceiro ficam onde foram enviados (nada se move).
        "pasta_dos_documentos_do_lead": lead.get("id"),
        "em": quando,
    }


__all__ = [
    "CAMPOS_DE_CONTACTO",
    "IdentidadeEmConflito",
    "POR_EMAIL",
    "POR_NIF",
    "campos_divergentes",
    "dados_de_identificacao",
    "encontrar_cliente_de_destino",
    "entrada_de_associacao",
]
