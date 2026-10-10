"""Que configurações pode um utilizador ver e escrever — por empresa.

O QUE CORREU MAL
================
`GET /system-config`, `PATCH /system-config/{secção}` e `/reveal-secrets`
estavam em `require_roles([ADMIN, CEO])` — que autoriza o VERBO — e o
`company_id` era um parâmetro livre da query string. Um CEO de uma ilha
(Domus) lia e escrevia a configuração da Power. E o `/reveal-secrets` nem
tinha `company_id`: devolvia sempre as chaves da configuração GLOBAL.

A REGRA (decisão do dono do produto, Out 2026)
==============================================
* **ADMIN** (o «master»: não existe um perfil `master` à parte, é o perfil
  de topo do sistema) — todas as empresas do CRM **e** a configuração
  global;
* **CEO** — só as empresas dele (UCR). A mesma rede NÃO chega: o CEO da
  Power não configura a Precision. **Nunca a global**, nem o CEO da rede
  principal;
* os restantes perfis não configuram nada (ler a lista devolve-lhes só
  as empresas onde trabalham, para o ecrã não mostrar o que não podem
  usar).

DUAS PERGUNTAS, NÃO UMA
=======================
1. *Esta EMPRESA é minha para configurar?* — o `company_id` pedido.
2. *A configuração GLOBAL (`default`) é minha?* — não é uma empresa, é a
   infraestrutura partilhada (bucket, SMTP do sistema, chave de IA).
   **Só o ADMIN.** (Uma versão anterior admitia o CEO da rede de omissão;
   o dono do produto retirou-o: a infra partilhada tem um único dono.)

Responde **404** a uma empresa que não é do utilizador (distinguir «não
existe» de «não é tua» confirmaria o id a quem adivinha) e **403** à
global, que não é segredo nenhum e à qual a mensagem explica o motivo.

UM `company_id` INVENTADO NÃO CRIA NADA
=======================================
`get_system_config(company_id)` CRIA e grava uma cópia da global para
qualquer id que não exista. Por isso a validação vem ANTES da leitura:
sem ela, qualquer pedido com um id novo escrevia um documento na base de
dados — e o do CEO escrevia-o para uma empresa que nem é dele.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from fastapi import HTTPException, Request

from database import db
from services.tenant_access_context import resolver_papel_efectivo
from services.role_scope import e_papel_global
from services.tenant_network import TenantScope, resolve_tenant_scope

logger = logging.getLogger(__name__)

#: O identificador da configuração global (o documento `_id: "main"`).
EMPRESA_GLOBAL = "default"

ERRO_EMPRESA_NAO_ENCONTRADA = "Empresa não encontrada"
ERRO_CONFIGURACAO_GLOBAL = (
    "A configuração global (infraestrutura partilhada) é exclusiva do "
    "perfil Master."
)


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor not in (None, "") else ""


def _e_master(papel: Any) -> bool:
    """O ÚNICO perfil que possui a configuração global (e todas as empresas)."""
    return e_papel_global(papel)


def _e_admin(papel: Any) -> bool:
    return _texto(papel).lower() == "admin"


def _e_ceo(papel: Any) -> bool:
    return _texto(papel).lower() == "ceo"


def _e_papel_de_configuracao(papel: Any) -> bool:
    return _e_master(papel) or _e_admin(papel) or _e_ceo(papel)


def e_empresa_global(company_id: Any) -> bool:
    """`default`, vazio ou ausente: a configuração global."""
    return _texto(company_id).lower() in {"", EMPRESA_GLOBAL}


@dataclass(frozen=True)
class AmbitoDeConfiguracao:
    """O que este utilizador pode configurar, resolvido UMA vez por pedido."""

    papel: str
    scope: TenantScope

    @property
    def e_master(self) -> bool:
        return _e_master(self.papel)

    @property
    def pode_a_global(self) -> bool:
        """A infra partilhada: só o Master. Nem o Admin, nem o CEO."""
        return self.e_master

    def empresa_e_minha(self, company_id: str) -> bool:
        """O `company_id` é uma das empresas (UCR) do utilizador?

        Compara com os IDS: é o `company_id` que dá nome ao documento de
        configuração (`company:<id>`). Aceitar o nome criaria um segundo
        documento para a mesma empresa.
        """
        alvo = _texto(company_id).lower()
        return bool(alvo) and alvo in {
            _texto(c).lower() for c in self.scope.company_ids
        }


async def carregar_ambito_de_configuracao(
    user: dict, request: Optional[Request] = None
) -> AmbitoDeConfiguracao:
    """Resolve o papel EFECTIVO e as redes do utilizador.

    O papel é o efectivo (UCR + `X-Active-Role`) e não o do JWT — a mesma
    regra do `history._is_stealth_user`. O `__all_roles__` traduz-se para
    o primeiro papel de configuração que o utilizador tem.
    """
    papel = await resolver_papel_efectivo(
        user, request, traduzir_todos_os_perfis=_e_papel_de_configuracao,
    )
    scope = await resolve_tenant_scope(user)
    return AmbitoDeConfiguracao(papel=papel, scope=scope)


async def _empresa_existe(company_id: str) -> bool:
    """O MASTER pode escolher qualquer empresa — desde que ela exista.

    Existe se está na colecção `companies` (pelo id) ou se já tem
    configuração própria gravada (empresas anteriores ao registo).
    """
    try:
        if await db.companies.find_one({"id": company_id}, {"_id": 0, "id": 1}):
            return True
        if await db.system_config.find_one(
            {"_id": f"company:{company_id}"}, {"_id": 1}
        ):
            return True
    except Exception as exc:
        # Falha FECHADO: sem poder confirmar, não se cria nada.
        logger.warning(
            "[system_config] Falha a verificar a empresa '%s' (%s); recusada.",
            company_id, exc,
        )
    return False


def exigir_configuracao_global(ambito: AmbitoDeConfiguracao) -> str:
    """Só quem possui a infra partilhada. Devolve `default`."""
    if not ambito.pode_a_global:
        raise HTTPException(status_code=403, detail=ERRO_CONFIGURACAO_GLOBAL)
    return EMPRESA_GLOBAL


async def exigir_empresa_configuravel(
    ambito: AmbitoDeConfiguracao, company_id: Optional[str]
) -> str:
    """Valida o `company_id` pedido e devolve o identificador canónico."""
    if e_empresa_global(company_id):
        return exigir_configuracao_global(ambito)

    alvo = _texto(company_id)
    if ambito.e_master:
        if await _empresa_existe(alvo):
            return alvo
        raise HTTPException(status_code=404, detail=ERRO_EMPRESA_NAO_ENCONTRADA)

    # Admin e CEO são perfis LOCAIS: só as empresas onde têm UCR. Empresa
    # alheia → 404, igual ao de «não existe» (não é um directório).
    if (_e_ceo(ambito.papel) or _e_admin(ambito.papel)) and ambito.empresa_e_minha(alvo):
        # Devolve o id tal como está nos UCR (a caixa pode diferir).
        return next(
            (c for c in ambito.scope.company_ids if _texto(c).lower() == alvo.lower()),
            alvo,
        )

    raise HTTPException(status_code=404, detail=ERRO_EMPRESA_NAO_ENCONTRADA)


async def resolver_empresa_pedida(
    user: dict, request: Optional[Request], company_id: Optional[str]
) -> str:
    """O ponto ÚNICO dos handlers: âmbito + validação num só passo."""
    ambito = await carregar_ambito_de_configuracao(user, request)
    return await exigir_empresa_configuravel(ambito, company_id)


async def resolver_configuracao_global(
    user: dict, request: Optional[Request]
) -> str:
    """Para as rotas que só existem a nível global (sem `company_id`)."""
    ambito = await carregar_ambito_de_configuracao(user, request)
    return exigir_configuracao_global(ambito)


async def resolver_empresa_para_leitura(
    user: dict, request: Optional[Request], company_id: Optional[str]
) -> str:
    """Leitura aberta a todos os perfis (permissão de exportação).

    A global é de todos (é um booleano que os botões consultam); uma
    empresa só se for a do utilizador — ou qualquer uma, para o ADMIN.
    Sem isto, qualquer sessão criava (via `get_system_config`) um
    documento por cada id que inventasse.
    """
    if e_empresa_global(company_id):
        return EMPRESA_GLOBAL
    ambito = await carregar_ambito_de_configuracao(user, request)
    alvo = _texto(company_id)
    if ambito.e_master and await _empresa_existe(alvo):
        return alvo
    if ambito.empresa_e_minha(alvo):
        return alvo
    raise HTTPException(status_code=404, detail=ERRO_EMPRESA_NAO_ENCONTRADA)


async def listar_empresas_configuraveis(ambito: AmbitoDeConfiguracao) -> list[dict]:
    """As empresas que o ecrã pode oferecer a este utilizador.

    * MASTER — a global e todas as empresas do CRM;
    * ADMIN e CEO — só as deles (nunca a global);
    * os outros — só as empresas onde trabalham, sem a global.
    """
    resultado: list[dict] = []
    if ambito.pode_a_global:
        resultado.append({"company_id": EMPRESA_GLOBAL, "company_name": "Global (Padrão)"})

    nomes: dict[str, str] = {}
    try:
        if ambito.e_master:
            cursor = db.companies.find({}, {"_id": 0, "id": 1, "name": 1})
            for empresa in await cursor.to_list(500):
                if _texto(empresa.get("id")):
                    nomes[_texto(empresa["id"])] = _texto(empresa.get("name")) or _texto(empresa["id"])
        else:
            proprios = [_texto(c) for c in ambito.scope.company_ids if _texto(c)]
            if proprios:
                cursor = db.companies.find(
                    {"id": {"$in": proprios}}, {"_id": 0, "id": 1, "name": 1}
                )
                encontradas = {
                    _texto(e.get("id")): _texto(e.get("name"))
                    for e in await cursor.to_list(100)
                }
                for cid in proprios:
                    nomes[cid] = encontradas.get(cid) or cid
    except Exception as exc:
        logger.warning(
            "[system_config] Falha a listar as empresas configuráveis (%s); "
            "a lista fica reduzida ao que se derivou dos UCR.", exc,
        )
        if not ambito.e_master:
            nomes = {_texto(c): _texto(c) for c in ambito.scope.company_ids if _texto(c)}

    for cid, nome in sorted(nomes.items(), key=lambda par: par[1].lower()):
        resultado.append({"company_id": cid, "company_name": nome})
    return resultado
