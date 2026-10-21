"""Quem usa o módulo Index (Lote 12, Fase 3) — um ponto único.

REGRA
-----
O Index («data entry» da indexação) e a gestão trabalham nas rotas `/api/index/*`:
**Master, Admin, CEO, Diretor e Indexação**, pelo perfil EFECTIVO (`require_roles`) e sempre
DENTRO da fronteira de rede (o router leva `exigir_processo_no_ambito`: 404 igual ao de
«não existe»). **Consultor e Intermediário nunca** (403, o handler não corre) — não vêem o
trabalho técnico da indexação nem gastam IA.

POR QUE NÃO ALARGAR O `PAPEIS_DE_GESTAO_DA_IA`
  A regra QA-5 («IA manual só para os altos perfis») continua a valer nas rotas de IA do
  CRM (`/documents/ai-analyze`, `/rename-all-smart`, …). O Index é a única excepção, e só
  nestas rotas novas: abrir a constante geral deixaria o perfil Indexação chamar as outras
  por acidente. Há um teste a afirmar que as duas listas diferem num único papel.
"""
from __future__ import annotations

from models.auth import UserRole
from services.document_ai_access import PAPEIS_DE_GESTAO_DA_IA

PAPEIS_DE_IA_DO_INDEX = [*PAPEIS_DE_GESTAO_DA_IA, UserRole.INDEXACAO]

#: Quem pode MARCAR como indexado (regra já existente em `process_indexing`; o Diretor
#: trabalha o Index mas não fecha a indexação — decisão anterior, mantida).
PAPEIS_QUE_MARCAM_INDEXADO = (UserRole.MASTER, UserRole.ADMIN, UserRole.CEO, UserRole.INDEXACAO)


def e_upload_do_index(user: dict | None) -> bool:
    """O ficheiro foi carregado pelo perfil Indexação? (perfil EFECTIVO do pedido.)

    Só estes ficheiros são sanitizados (decisão da direcção): o que o cliente, o parceiro ou a
    restante equipa carrega não passa pelo PDF limpo.
    """
    if not user:
        return False
    papel = str(user.get("effective_role") or user.get("role") or "").strip().lower()
    return papel == UserRole.INDEXACAO
