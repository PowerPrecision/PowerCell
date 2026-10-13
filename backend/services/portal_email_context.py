"""Contexto de REDE dos emails que o cliente recebe do Portal (boas-vindas, convite, acesso).

O PROBLEMA
==========
Os emails de boas-vindas saíam todos como se o cliente fosse da Power:
o corpo dizia «Power Real Estate» / «Power Precision», o remetente era a
conta global do sistema (``account_name="power"``) e o link do Portal nem
chegava ao template. Num sistema multi-rede isso é uma fuga de identidade —
o cliente da Domus recebia um email da Power.

A REGRA
=======
O contexto vem do **registo**, nunca de uma constante:

    * a EMPRESA do cliente (``company_id`` / ``company_name`` gravados no
      cliente, o carimbo do link público, ou a empresa de quem o criou) dá o
      nome e o logótipo — ``resolve_company_branding_strict``, sem recurso
      global;
    * o REMETENTE é o email geral configurado para essa rede (a Caixa Geral
      da empresa; depois a de outra empresa da MESMA rede). Sem ele, o email
      de sistema genérico (``no-reply``) com o nome da empresa — **nunca** a
      conta de outra rede. Só a rede de omissão (a do grupo incumbente) pode
      usar a configuração global, porque é dela;
    * o LINK do Portal é sempre um URL absoluto.

Falha FECHADA no que identifica: quando não se sabe a empresa, o nome é
neutro («Portal do Cliente») e a caixa geral não é adivinhada.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)

#: Falhas de CONFIGURAÇÃO do remetente: acontecem antes de qualquer entrega.
CODIGOS_ANTES_DA_ENTREGA = frozenset({"smtp_auth", "smtp_password_unreadable", "SMTP_NOT_CONFIGURED"})

#: Nome usado quando não se consegue determinar a empresa. Neutro de propósito.
NOME_NEUTRO = "Portal do Cliente"

#: Como se diz a empresa num TEXTO CORRIDO quando não se sabe qual é («…equipa da
#: nossa empresa», «…escolher a nossa empresa»): nunca a marca de outra.
EMPRESA_NEUTRA_NO_TEXTO = "nossa empresa"

#: Origens possíveis do remetente (vão para o log e para os testes).
ORIGEM_CAIXA_DA_EMPRESA = "caixa_geral_da_empresa"
ORIGEM_CAIXA_DA_REDE = "caixa_geral_da_rede"
ORIGEM_CAIXA_GLOBAL = "caixa_geral_da_rede_de_omissao"
ORIGEM_SISTEMA = "sistema"
ORIGEM_NENHUMA = "nenhuma"


@dataclass(frozen=True)
class ContextoDoEmailDoPortal:
    """Tudo o que um email do Portal precisa de saber sobre a rede do cliente."""

    company_id: Optional[str] = None
    company_name: Optional[str] = None
    network_id: Optional[str] = None
    logo_url: Optional[str] = None
    #: ``EmailAccount`` da caixa geral da rede, ou ``None`` (→ email de sistema).
    account: Any = None
    account_source: str = ORIGEM_SISTEMA
    #: URL absoluto da página de entrada do Portal (ou ``""`` se não se sabe o domínio).
    portal_url: str = ""

    @property
    def nome(self) -> str:
        return self.company_name or NOME_NEUTRO

    @property
    def equipa(self) -> str:
        """A assinatura de um email: «Equipa Domus», ou «A nossa equipa» sem empresa."""
        return f"Equipa {self.company_name}" if self.company_name else "A nossa equipa"

    def assunto(self, resto: str) -> str:
        """«Domus - <resto>»; sem empresa só o resto (nunca «Portal do Cliente - …»)."""
        return f"{self.company_name} - {resto}" if self.company_name else resto


def _texto(valor: Any) -> str:
    return str(valor).strip() if valor is not None else ""


def url_base_do_frontend(frontend_url: Optional[str] = None) -> str:
    """Domínio do frontend: o que o chamador sabe, depois ``FRONTEND_URL``."""
    return (_texto(frontend_url) or _texto(os.environ.get("FRONTEND_URL"))).rstrip("/")


def url_do_portal(frontend_url: Optional[str] = None, *, portal_url: Optional[str] = None) -> str:
    """URL absoluto do Portal do Cliente (``…/portal``), ou ``""`` sem domínio.

    Um link relativo num email não leva a lado nenhum, por isso sem domínio
    devolve-se vazio — e diz-se no log, porque um email sem botão não produz
    erro nenhum.
    """
    explicito = _texto(portal_url)
    if explicito:
        return explicito
    base = url_base_do_frontend(frontend_url)
    if not base:
        logger.error(
            "[PORTAL-EMAIL] Sem domínio do frontend (nem Referer/Origin nem FRONTEND_URL): "
            "o email de boas-vindas sai SEM o link do Portal. Definir FRONTEND_URL."
        )
        return ""
    return f"{base}/portal"


# ─────────────────────────────────────────────────────────────────────
# EMPRESA DO REGISTO
# ─────────────────────────────────────────────────────────────────────

_PROJECCAO_EMPRESA = {"_id": 0, "id": 1, "name": 1, "network_id": 1}


async def _empresa_por_id(company_id: str) -> Optional[dict]:
    return await db.companies.find_one({"id": company_id}, _PROJECCAO_EMPRESA)


async def _empresa_por_nome(nome: str) -> Optional[dict]:
    return await db.companies.find_one({"name": nome}, _PROJECCAO_EMPRESA)


async def _empresa_unica_da_rede(rede: str) -> Optional[dict]:
    """A empresa da rede, só quando é UMA: com várias não se adivinha qual."""
    if rede.startswith("rede:"):
        return await _empresa_por_id(rede[len("rede:"):])
    candidatas = await db.companies.find(
        {"network_id": rede, "is_active": {"$ne": False}}, _PROJECCAO_EMPRESA,
    ).to_list(3)
    return candidatas[0] if len(candidatas) == 1 else None


async def _empresa_do_registo(
    *,
    company_id: Optional[str],
    company_name: Optional[str],
    network_id: Optional[str],
    client_id: Optional[str],
    user: Optional[dict],
) -> tuple[Optional[dict], Optional[str]]:
    """``(empresa | None, rede | None)`` a que este registo pertence.

    Ordem: o que o chamador diz → o carimbo gravado no cliente → a empresa de
    quem o criou → a rede, se tiver uma só empresa.
    """
    cid, nome, rede = _texto(company_id), _texto(company_name), _texto(network_id)

    if client_id and not (cid or nome):
        cliente = await db.clients.find_one(
            {"id": client_id},
            {"_id": 0, "company_id": 1, "company_name": 1, "network_id": 1},
        ) or {}
        cid = _texto(cliente.get("company_id"))
        nome = _texto(cliente.get("company_name"))
        rede = rede or _texto(cliente.get("network_id"))

    empresa: Optional[dict] = None
    if cid:
        empresa = await _empresa_por_id(cid)
    if empresa is None and nome:
        empresa = await _empresa_por_nome(nome)

    if empresa is None and not (cid or nome or rede) and user:
        from services.tenant_network import resolve_tenant_stamp

        carimbo = await resolve_tenant_stamp(user) or {}
        if carimbo.get("company_id"):
            empresa = await _empresa_por_id(carimbo["company_id"])
        rede = rede or _texto(carimbo.get("network_id"))

    if empresa is None and rede:
        empresa = await _empresa_unica_da_rede(rede)

    if empresa is not None:
        from services.tenant_network import resolve_network_id

        rede = resolve_network_id(empresa) or rede
    return empresa, (rede or None)


# ─────────────────────────────────────────────────────────────────────
# EMAIL GERAL DA REDE
# ─────────────────────────────────────────────────────────────────────


def _conta_da_configuracao(email_cfg: Optional[dict], nome: str):
    """``EmailAccount`` a partir da secção ``email`` de um system_config, ou ``None``."""
    from services.email_config_resolver import decrypt_email_secret
    from services.email_service import EmailAccount

    cfg = email_cfg or {}
    utilizador = _texto(cfg.get("imap_user") or cfg.get("smtp_user"))
    palavra_passe = decrypt_email_secret(
        cfg.get("imap_password") or cfg.get("smtp_password") or "",
        f"portal-email caixa geral user={utilizador}",
    )
    servidor_smtp = _texto(cfg.get("smtp_server") or cfg.get("imap_server"))
    if not (utilizador and palavra_passe and servidor_smtp):
        return None
    return EmailAccount(
        name=nome,
        imap_server=_texto(cfg.get("imap_server")) or servidor_smtp,
        imap_port=int(cfg.get("imap_port") or 993),
        smtp_server=servidor_smtp,
        smtp_port=int(cfg.get("smtp_port") or 465),
        email=utilizador,
        password=palavra_passe,
    )


async def _email_do_documento(doc_id: str) -> Optional[dict]:
    try:
        doc = await db.system_config.find_one({"_id": doc_id}, {"_id": 0, "email": 1})
    except Exception as exc:  # noqa: BLE001 - degradação graciosa
        logger.warning("[PORTAL-EMAIL] Falha a ler system_config %s: %s", doc_id, exc)
        return None
    email = (doc or {}).get("email")
    return email if isinstance(email, dict) else None


def _utilizador(cfg: Optional[dict]) -> str:
    return _texto((cfg or {}).get("imap_user") or (cfg or {}).get("smtp_user")).lower()


async def _caixa_geral_da_rede(
    company_id: Optional[str], rede: Optional[str],
) -> tuple[Any, str]:
    """``(EmailAccount | None, origem)`` — o email geral que esta rede configurou.

    Ordem: a caixa da própria empresa → a de outra empresa da MESMA rede →
    (só a rede de omissão) a configuração global. Uma configuração por
    empresa cujo utilizador é igual ao da global é a cópia que o
    ``get_system_config`` grava por herança, ou seja, a caixa de OUTRA rede:
    fora da rede de omissão não conta.
    """
    from services.tenant_network import rede_de_omissao

    if not (company_id or rede):
        # Nem empresa nem rede: não há de quem ser a caixa (e não se adivinha).
        return None, ORIGEM_SISTEMA

    omissao = rede_de_omissao()
    e_rede_de_omissao = bool(rede and omissao and rede == omissao)
    global_cfg = await _email_do_documento("main")
    utilizador_global = _utilizador(global_cfg)

    candidatas: list[tuple[str, str]] = []
    if company_id:
        candidatas.append((company_id, ORIGEM_CAIXA_DA_EMPRESA))
    if rede and not rede.startswith("rede:"):
        try:
            irmas = await db.companies.find(
                {"network_id": rede, "is_active": {"$ne": False}}, {"_id": 0, "id": 1},
            ).to_list(50)
        except Exception as exc:  # noqa: BLE001
            logger.warning("[PORTAL-EMAIL] Falha a listar as empresas da rede %s: %s", rede, exc)
            irmas = []
        for irma in sorted(irmas, key=lambda c: _texto(c.get("id"))):
            if irma.get("id") and irma["id"] != company_id:
                candidatas.append((irma["id"], ORIGEM_CAIXA_DA_REDE))

    for cid, origem in candidatas:
        cfg = await _email_do_documento(f"company:{cid}")
        if not cfg:
            continue
        herdada = bool(utilizador_global) and _utilizador(cfg) == utilizador_global
        if herdada and not e_rede_de_omissao:
            continue
        conta = _conta_da_configuracao(cfg, "caixa_geral_da_rede")
        if conta is not None:
            return conta, origem

    if e_rede_de_omissao:
        conta = _conta_da_configuracao(global_cfg, "caixa_geral_da_rede")
        if conta is not None:
            return conta, ORIGEM_CAIXA_GLOBAL
    return None, ORIGEM_SISTEMA


async def resolver_contexto(
    *,
    company_id: Optional[str] = None,
    company_name: Optional[str] = None,
    network_id: Optional[str] = None,
    client_id: Optional[str] = None,
    user: Optional[dict] = None,
    frontend_url: Optional[str] = None,
    portal_url: Optional[str] = None,
    incluir_link: bool = True,
) -> ContextoDoEmailDoPortal:
    """Resolve o contexto de rede de um email do Portal. **Nunca levanta.**

    Qualquer falha cai no contexto NEUTRO (sem nome de empresa, sem caixa
    geral): é o degradado seguro — um email com um nome genérico incomoda,
    um email com o nome de outra empresa é uma fuga.
    """
    # Um email sem botão (estado de uma recolha) não precisa de domínio nem deve
    # gritar nos logs por não o ter.
    link = url_do_portal(frontend_url, portal_url=portal_url) if incluir_link else ""
    try:
        empresa, rede = await _empresa_do_registo(
            company_id=company_id, company_name=company_name, network_id=network_id,
            client_id=client_id, user=user,
        )
        cid = _texto((empresa or {}).get("id")) or None
        nome = _texto((empresa or {}).get("name")) or None

        from services.email_branding import resolve_company_branding_strict

        marca_nome, logo = await resolve_company_branding_strict(cid)
        conta, origem = await _caixa_geral_da_rede(cid, rede)
        return ContextoDoEmailDoPortal(
            company_id=cid,
            company_name=nome or marca_nome,
            network_id=rede,
            logo_url=logo,
            account=conta,
            account_source=origem,
            portal_url=link,
        )
    except Exception as exc:  # noqa: BLE001 - degradação graciosa
        logger.warning(
            "[PORTAL-EMAIL] Falha a resolver a rede do email (cliente %s): %s. "
            "A usar o contexto neutro.", client_id, exc,
        )
        return ContextoDoEmailDoPortal(portal_url=link, account_source=ORIGEM_NENHUMA)


async def nome_da_empresa_do_registo(
    *,
    company_id: Optional[str] = None,
    company_name: Optional[str] = None,
    network_id: Optional[str] = None,
    client_id: Optional[str] = None,
) -> Optional[str]:
    """O nome da empresa a que o registo pertence, ou ``None`` — **sem** procurar caixas.

    Para texto que só precisa do nome (a mensagem de boas-vindas DENTRO do
    Portal, lida a cada 15 s): o contexto completo faria leituras de
    configuração que aqui não servem. Nunca levanta.
    """
    try:
        empresa, _rede = await _empresa_do_registo(
            company_id=company_id, company_name=company_name, network_id=network_id,
            client_id=client_id, user=None,
        )
        return _texto((empresa or {}).get("name")) or None
    except Exception as exc:  # noqa: BLE001 - degradação graciosa
        logger.warning("[PORTAL-EMAIL] Falha a resolver o nome da empresa (%s): %s", client_id, exc)
        return None


# ─────────────────────────────────────────────────────────────────────
# ENVIO
# ─────────────────────────────────────────────────────────────────────


async def _conta_de_sistema_generica(rede: Optional[str]):
    """A conta de sistema (``no-reply``), sem nunca cair na conta de outra rede.

    O ``send_email`` tem um último recurso — as contas de AMBIENTE
    (``POWER_EMAIL``…) — que numa rede que não é a de omissão seria enviar em
    nome da Power. Resolve-se aqui, sem esse recurso: só a rede de omissão
    pode deixá-lo ao ``send_email``.
    """
    from services.email import get_system_transporter
    from services.email_service import EmailAccount, _resolve_system_smtp_account

    # **Nunca levanta.** Uma configuração de email de sistema que não se consegue
    # ler (porta gravada como texto, campo em falta, base de dados com um soluço)
    # é, para quem vai enviar, uma conta que não existe. Antes só a segunda
    # metade estava protegida: a primeira (`_resolve_system_smtp_account` faz
    # `int(smtp_port)` fora de qualquer `try`) furava o `verificar_remetente`,
    # que corre ANTES do bloco que traduz erros — e o utilizador via um 500 nu.
    try:
        conta = await _resolve_system_smtp_account()
    except Exception as exc:  # noqa: BLE001
        logger.error(
            "[PORTAL-EMAIL] A configuração do email de sistema (Bloco A) não é utilizável: "
            "%s: %s. Tratada como não configurada.", type(exc).__name__, exc,
        )
        conta = None
    if conta is None:
        conta = await _conta_do_bloco_a_em_bruto()
    if conta is not None:
        return conta
    try:
        transporte = await get_system_transporter("NOTIFICATIONS")
        if transporte.get("error") or transporte.get("source") != "db":
            return None
        return EmailAccount(
            name="system_notifications",
            imap_server=transporte["host"], imap_port=transporte["port"],
            smtp_server=transporte["host"], smtp_port=transporte["port"],
            email=transporte.get("from_email") or transporte["user"],
            password=transporte["password"],
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[PORTAL-EMAIL] Sem email de sistema para NOTIFICATIONS: %s", exc)
        return None


#: Nome da empresa que, na plataforma, é a «dona» da infraestrutura. O Master que escolhe
#: trabalhar como «Sistema» no seletor de contexto edita a configuração desta empresa (e não a
#: do documento global); o «Email do Sistema (Transacional)» pode lá ter ficado gravado.
NOME_DA_EMPRESA_DO_SISTEMA = "Sistema"


def _conta_do_bloco(bloco):
    """`EmailAccount` a partir de um bloco `system_smtp` em bruto (ou `None`)."""
    from models.system_config import SystemSMTPConfig
    from services.email_service import EmailAccount

    if not isinstance(bloco, dict) or not bloco:
        return None
    cfg = SystemSMTPConfig(**bloco)
    if cfg.resend_api_key:
        return EmailAccount(
            name="system_smtp", imap_server="resend", imap_port=0,
            smtp_server="resend", smtp_port=0,
            email=cfg.smtp_from_email or "", password=cfg.resend_api_key,
        )
    if cfg.smtp_host and cfg.smtp_username:
        return EmailAccount(
            name="system_smtp", imap_server=cfg.smtp_host, imap_port=int(cfg.smtp_port or 587),
            smtp_server=cfg.smtp_host, smtp_port=int(cfg.smtp_port or 587),
            email=cfg.smtp_from_email or cfg.smtp_username, password=cfg.smtp_password or "",
        )
    return None


async def _conta_do_bloco_a_em_bruto():
    """O «Email do Sistema (Transacional)», lido SEM validar o resto do documento.

    ``get_system_config`` valida o documento INTEIRO e, se um campo qualquer (de
    qualquer secção) não validar, devolve a configuração por omissão do ambiente —
    ou seja, SEM o Bloco A, ainda que ele esteja gravado e certo. Para um email
    transacional (o link do Portal, as boas-vindas) isso era «a empresa não tem
    e-mail» por causa de um campo que nada tem a ver com o envio. Aqui lê-se só o
    bloco ``system_smtp``. Mesma fonte, mesma regra, menos acoplamento.

    Ordem: o documento GLOBAL e, se ali não houver conta utilizável, o da empresa
    «Sistema» (o Master que configurou o cartão com esse perfil activo grava lá).
    Nunca levanta.
    """
    for obter_bloco in (_bloco_do_documento_global, _bloco_do_documento_da_empresa_sistema):
        try:
            conta = _conta_do_bloco(await obter_bloco())
        except Exception as exc:  # noqa: BLE001
            logger.warning("[PORTAL-EMAIL] Leitura em bruto do Email do Sistema falhou: %s: %s",
                           type(exc).__name__, exc)
            continue
        if conta is not None:
            return conta
    return None


async def _bloco_do_documento_global():
    doc = await db.system_config.find_one({"_id": "main"}, {"_id": 0, "system_smtp": 1})
    return (doc or {}).get("system_smtp")


async def _bloco_do_documento_da_empresa_sistema():
    from utils.input_sanitization import escape_regex

    empresa = await db.companies.find_one(
        {"name": {"$regex": f"^{escape_regex(NOME_DA_EMPRESA_DO_SISTEMA)}$", "$options": "i"}},
        {"_id": 0, "id": 1},
    )
    if not empresa or not empresa.get("id"):
        return None
    doc = await db.system_config.find_one(
        {"_id": f"company:{empresa['id']}"}, {"_id": 0, "system_smtp": 1}
    )
    return (doc or {}).get("system_smtp")


def mensagem_sem_remetente(contexto: "ContextoDoEmailDoPortal") -> str:
    """O que se diz a quem tenta enviar numa rede sem email configurado."""
    return (
        f"A empresa «{contexto.nome}» não tem e-mail configurado. Configure o email "
        "geral da empresa ou o «Email do Sistema (Transacional)» (Contas de Email) e tente novamente."
        if contexto.company_name else
        "A empresa não tem e-mail configurado. Configure o email geral da empresa "
        "ou o «Email do Sistema (Transacional)» (Contas de Email) e tente novamente."
    )


async def verificar_remetente(contexto: "ContextoDoEmailDoPortal") -> Optional[str]:
    """``None`` se há de onde enviar; senão a mensagem para o utilizador (FAIL FAST).

    É a MESMA decisão que o ``enviar_email_do_portal`` toma ao enviar, feita
    ANTES de qualquer efeito (emitir o link, gravar o histórico, enfileirar um
    retry): uma rede sem email geral nem email de sistema não envia — e não
    tem de gastar um token, escrever «enviou o link» no histórico nem entrar
    num ciclo de retries que nunca poderá ter sucesso. Só a rede de omissão
    pode ainda contar com o último recurso do ``send_email`` (as contas de
    ambiente), por isso não se lhe antecipa uma recusa.
    """
    from services.tenant_network import rede_de_omissao

    if contexto.account is not None:
        return None
    # `_conta_de_sistema_generica` não levanta; o `rede_de_omissao` é uma leitura
    # de ambiente. Esta verificação corre antes do bloco que traduz erros e por
    # isso não pode, ela própria, ser uma fonte de excepções.
    if await _conta_de_sistema_generica(contexto.network_id) is not None:
        return None
    omissao = rede_de_omissao()
    if not omissao:
        # Dev/CI sem `TENANT_DEFAULT_NETWORK_ID`: não há rede a que atribuir o
        # último recurso, e o comportamento anterior ao isolamento mantém-se
        # (o critério das outras colecções). Em produção a variável existe.
        return None
    if contexto.network_id and contexto.network_id == omissao:
        return None
    return mensagem_sem_remetente(contexto)


async def enviar_email_do_portal(
    contexto: ContextoDoEmailDoPortal,
    *,
    to_emails: list[str],
    subject: str,
    body: str,
    body_html: Optional[str] = None,
    attachments: Optional[list] = None,
    process_id: Optional[str] = None,
    created_by: Optional[str] = None,
    system_purpose: str = "NOTIFICATIONS",
) -> dict:
    """Envia um email do Portal em nome da rede do cliente.

    * Com caixa geral da rede: sai dela (e é respondível — sem rodapé de
      «não responda»).
    * Sem ela: email de sistema genérico, com o NOME da empresa e sem a
      assinatura global do sistema.
    Em ambos os casos o nome do remetente é o da empresa do registo.
    """
    from services.email_service import send_email
    from services.tenant_network import rede_de_omissao

    comum = dict(
        to_emails=to_emails, subject=subject, body=body, body_html=body_html,
        from_name_override=contexto.nome, use_system_signature=False,
    )
    if attachments:
        comum["attachments"] = attachments
    if process_id:
        comum["process_id"] = process_id
    if created_by:
        comum["created_by"] = created_by
    if contexto.account is not None:
        try:
            resultado = await send_email(
                account_name="caixa_geral_da_rede", account_override=contexto.account, **comum,
            )
        except ValueError as exc:  # configuração da caixa (não infraestrutura)
            resultado = {"success": False, "error": str(exc), "error_code": "SMTP_NOT_CONFIGURED"}
        if (resultado or {}).get("success") or (resultado or {}).get("error_code") not in CODIGOS_ANTES_DA_ENTREGA:
            return resultado
        # Um email TRANSACIONAL não pode ficar refém de uma caixa da rede com a password
        # expirada: o «Email do Sistema (Transacional)» existe para isto. Só se recua
        # para falhas de CONFIGURAÇÃO (acontecem antes de qualquer entrega — repetir não
        # duplica); uma falha genérica pode ter acontecido depois de enviar.
        conta_do_sistema = await _conta_de_sistema_generica(contexto.network_id)
        if conta_do_sistema is None:
            return resultado
        logger.warning(
            "[PORTAL-EMAIL] A caixa geral da rede %s falhou (%s): a enviar pelo Email do Sistema "
            "(Transacional).", contexto.network_id, resultado.get("error_code"),
        )
        return await send_email(
            account_name="sistema", account_override=conta_do_sistema,
            force_system=True, system_purpose=system_purpose, **comum,
        )

    conta = await _conta_de_sistema_generica(contexto.network_id)
    omissao = rede_de_omissao()
    if conta is None and not (contexto.network_id and omissao and contexto.network_id == omissao):
        logger.error(
            "[PORTAL-EMAIL] Rede %s sem email geral nem email de sistema: não se envia em "
            "nome de outra rede.", contexto.network_id,
        )
        return {
            "success": False,
            "error": "Sem email geral da rede nem email de sistema configurado.",
            "error_code": "SMTP_NOT_CONFIGURED",
        }
    return await send_email(
        account_name="sistema", account_override=conta,
        force_system=True, system_purpose=system_purpose, **comum,
    )
