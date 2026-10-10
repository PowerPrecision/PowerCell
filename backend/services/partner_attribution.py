"""
====================================================================
PORTAL DO PARCEIRO — A LEAD HERDA O PARCEIRO NO PROCESSO (V1)
====================================================================
Uma lead é um cliente com `submitted_by_partner_id`. Quando a equipa abre
o processo, o processo tem de nascer atribuído ao mesmo parceiro
(`assigned_parceiro_id`) — é por esse campo que o parceiro o vê. Se um
escritor de processos se esquecer, o caso **desaparece** do ecrã do
parceiro: deixa de ser lead (já tem processo) e ainda não é processo dele.
Um caso que desaparece não produz erro nenhum.

Esta é a mesma forma do defeito da atribuição (Lote 5/6): a regra existia
e **cada escritor repetia-a à mão**. Por isso:

  * a regra é UMA função pura (`aplicar_parceiro_do_cliente`), chamada por
    todos os escritores de processos do CRM;
  * há um inventário por AST (`test_parceiro_inventarios.py`) que falha por
    OMISSÃO para qualquer `db.processes.insert_one` novo em `services/`,
    com as excepções escritas e justificadas.

PURA, de propósito: recebe o cliente que o escritor já carregou. Uma
versão que lesse a base de dados faria falar com o `db` real os testes
que exercitam estes escritores com um duplo — a armadilha da ordem de
importação (AGENTS.md).

NUNCA SOBRESCREVE: um parceiro já atribuído pela equipa (ou por
`/assign`) vence a herança — a atribuição manual é uma decisão.
====================================================================
"""
from __future__ import annotations

from typing import Any, Mapping, Optional


def aplicar_parceiro_do_cliente(process_doc: dict, cliente: Optional[Mapping[str, Any]]) -> bool:
    """Herda o parceiro que submeteu o cliente. Devolve se escreveu.

    `cliente` pode ser o documento do cliente ou qualquer mapeamento que
    traga `submitted_by_partner_id` / `submitted_by_partner_name`.
    """
    if not cliente or process_doc.get("assigned_parceiro_id"):
        return False
    partner_id = str(cliente.get("submitted_by_partner_id") or "").strip()
    if not partner_id:
        return False
    process_doc["assigned_parceiro_id"] = partner_id
    nome = cliente.get("submitted_by_partner_name")
    if isinstance(nome, str) and nome.strip():
        process_doc["parceiro_name"] = nome.strip()
    return True


__all__ = ["aplicar_parceiro_do_cliente"]
