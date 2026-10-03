"""Ligar um email recebido à ficha do cliente — ponto único (Lote 7, ponto 4).

O QUE A AUDITORIA ENCONTROU
===========================
A pergunta era «o sistema liga as mensagens recebidas, pelo endereço, à ficha
do respectivo cliente?». A resposta era **não, na caixa que mais importa**.

Há dois sincronizadores e faziam coisas diferentes:

* **`sync_webmail_emails`** (as contas partilhadas `power`/`precision`)
  resolvia por endereço — mas com uma consulta escrita à mão que conhecia
  **só** `client_email` e `monitored_emails`.
* **`sync_user_emails`** (a caixa PESSOAL de cada consultor, que o worker
  sincroniza de 10 em 10 minutos) **não resolvia por endereço nenhum.** Só
  herdava o `process_id` do email-pai de uma conversa e lia a etiqueta
  `[PROC-xxx]` do assunto.

Ou seja: um email de um cliente para o consultor só entrava na ficha se a
conversa já estivesse ligada ou se alguém tivesse posto a etiqueta no assunto
— e eram esses dois caminhos a funcionar que escondiam o terceiro em falta
(a forma do `run_get_my_tasks`).

TRÊS DEFEITOS NO QUE EXISTIA
============================
1. **Só o titular 1.** O **2.º titular** é co-mutuário e escreve sobre o mesmo
   crédito; o seu endereço nunca ligava. E o sentido INVERSO da mesma relação
   — `email_process_crud.collect_emails_from_process_doc`, usado para listar os
   emails de um processo — conhecia `titular2_data.email` desde sempre. **As
   duas direcções da mesma relação conheciam conjuntos de campos diferentes**,
   e só a direcção menos usada estava certa.

2. **`find_one` sem unicidade.** O mesmo cliente com dois processos ficava
   ligado ao que o Mongo calhasse devolver, de forma permanente. «Não
   encontrei» e «encontrei dois» são respostas diferentes — é a lição do
   `run_auto_map_client_s3_folders`, e aqui o email entra na ficha errada.

3. **Sem noção de rede.** A consulta varria `processes` inteira.

A REGRA
=======
Um endereço resolve para UM processo ou para NENHUM. Com dois ou mais
candidatos o email fica **geral** — visível na caixa, sem ficha — porque entrar
na ficha errada é um cruzamento de dados e sair dela exige alguém que repare.

A ORDEM DOS CAMPOS É A DO ACORDO COM O INVERSO
==============================================
`CAMPOS_DE_ENDERECO_DO_PROCESSO` é comparado num teste com o que o
`collect_emails_from_process_doc` lê: as duas direcções têm de conhecer os
mesmos campos, senão volta a haver um endereço que lista e não liga.

O `network_id` É OPCIONAL — E A AUSÊNCIA NÃO É UM BURACO
========================================================
A sincronização pessoal sabe a rede (tem `user_id` + `company_id`); a das
contas partilhadas, que vêm de variáveis de ambiente, não tem utilizador
nenhum. Sem rede **a exigência de unicidade passa a valer sobre o sistema
inteiro**, o que é mais estrito e não menos: dois candidatos em redes
diferentes dão ambíguo e o email fica geral, em vez de entrar num deles em
silêncio. O carimbo de rede em `db.emails` continua a ser a D-8.

Cobertura: `tests/unit/test_email_client_match.py`.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from database import db

logger = logging.getLogger(__name__)

#: Os campos do processo que guardam um endereço de um cliente. Comparados
#: num teste com o `collect_emails_from_process_doc` — ver o cabeçalho.
CAMPOS_DE_ENDERECO_DO_PROCESSO = (
    "client_email",
    "monitored_emails",
    "titular2_data.email",
)

MOTIVO_TITULAR = "endereço do titular"
MOTIVO_MONITORIZADO = "endereço monitorizado"
MOTIVO_SEGUNDO_TITULAR = "endereço do 2.º titular"


@dataclass(frozen=True)
class Resolucao:
    """O resultado: um processo, nenhum, ou ambiguidade."""

    process_id: Optional[str] = None
    motivo: str = ""
    ambiguo: bool = False
    candidatos: list[str] = field(default_factory=list)


def normalizar_enderecos(enderecos: Iterable[Any]) -> list[str]:
    """Minúsculas, sem espaços, sem vazios e sem duplicados.

    A comparação é EXACTA. Um match aproximado entre endereços abriria a
    ligação, que é o sentido errado — foi um score de semelhança que
    produziu a colisão de pastas do Lote 6.
    """
    vistos: list[str] = []
    for valor in enderecos or []:
        texto = str(valor or "").strip().lower()
        if texto and texto not in vistos:
            vistos.append(texto)
    return vistos


def construir_condicao(enderecos: Iterable[str]) -> Optional[dict]:
    """`$or` sobre os três campos. Sem endereços devolve `None`.

    `None` e não `{}`: um `{}` casaria com o primeiro processo da colecção,
    e é exactamente a forma de defeito que esta função vem fechar.
    """
    limpos = normalizar_enderecos(enderecos)
    if not limpos:
        return None
    return {"$or": [
        {campo: {"$in": limpos}} for campo in CAMPOS_DE_ENDERECO_DO_PROCESSO
    ]}


def motivo_do_processo(processo: dict, enderecos: Iterable[str]) -> str:
    """Por que campo é que este processo casou — vai para o log.

    Sem isto, diagnosticar uma ligação errada obriga a reconstruir a
    consulta à mão (é a razão do `source` no `resolve_sending_account`).
    """
    limpos = set(normalizar_enderecos(enderecos))
    if str((processo or {}).get("client_email") or "").lower().strip() in limpos:
        return MOTIVO_TITULAR
    titular2 = (processo or {}).get("titular2_data") or {}
    if str(titular2.get("email") or "").lower().strip() in limpos:
        return MOTIVO_SEGUNDO_TITULAR
    for monitorizado in (processo or {}).get("monitored_emails") or []:
        if str(monitorizado or "").lower().strip() in limpos:
            return MOTIVO_MONITORIZADO
    return "endereço do processo"


async def _estados_terminais() -> list[str]:
    """As fases fechadas, ditadas pelo motor.

    Estava escrito à mão como `["concluido", "cancelado", "arquivado"]` — uma
    lista que inclui o typo legado `arquivado` e **não** o valor canónico
    `arquivo` (a D-6 com outro nome). Uma fase nova fechada pelo
    administrador também não entrava.
    """
    try:
        from services.workflow_phases import carregar_fases, nomes_terminais

        return nomes_terminais(await carregar_fases()) + ["arquivado"]
    except Exception as exc:
        logger.warning(
            "[EMAIL-MATCH] Falha a carregar as fases terminais (%s); "
            "a usar a lista legada.", exc,
        )
        return ["concluido", "cancelado", "arquivado"]


async def resolver_processo_por_endereco(
    enderecos: Iterable[Any],
    *,
    network_id: Optional[str] = None,
    limite: int = 5,
) -> Resolucao:
    """O processo ABERTO a que estes endereços pertencem, ou nenhum.

    Devolve `ambiguo=True` com dois ou mais candidatos: entrar na ficha
    errada é um cruzamento de dados, e sair dela exige alguém que repare.
    """
    condicao = construir_condicao(enderecos)
    if condicao is None:
        return Resolucao()

    consulta: dict = {**condicao, "status": {"$nin": await _estados_terminais()}}
    if network_id:
        consulta["network_id"] = str(network_id)

    try:
        candidatos = await db.processes.find(
            consulta,
            {"_id": 0, "id": 1, "client_email": 1, "monitored_emails": 1,
             "titular2_data": 1},
        ).to_list(limite)
    except Exception as exc:
        logger.warning("[EMAIL-MATCH] Falha a resolver o processo: %s", exc)
        return Resolucao()

    com_id = [c for c in candidatos if c.get("id")]
    if not com_id:
        return Resolucao()
    if len(com_id) > 1:
        return Resolucao(
            ambiguo=True, candidatos=[str(c["id"]) for c in com_id],
        )

    processo = com_id[0]
    return Resolucao(
        process_id=str(processo["id"]),
        motivo=motivo_do_processo(processo, enderecos),
    )


__all__ = [
    "CAMPOS_DE_ENDERECO_DO_PROCESSO",
    "MOTIVO_MONITORIZADO",
    "MOTIVO_SEGUNDO_TITULAR",
    "MOTIVO_TITULAR",
    "Resolucao",
    "construir_condicao",
    "motivo_do_processo",
    "normalizar_enderecos",
    "resolver_processo_por_endereco",
]
