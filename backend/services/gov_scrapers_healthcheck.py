"""
====================================================================
HEALTH CHECK DIÁRIO DOS SCRAPERS DO ESTADO (D-30)
====================================================================
Os selectores do Portal das Finanças e da Segurança Social Direta só se
provam contra os portais reais — e um portal que muda o HTML parte o scraper
**sem erro nenhum do nosso lado**: o cliente pede os documentos, o pedido
falha, e só se descobre quando alguém repara. Este job faz o pedido ANTES do
cliente: uma vez por dia corre a extracção de produção (a MESMA função que o
Portal usa — nunca uma cópia dos selectores) com uma conta de teste e, se o
que partiu foram os selectores, avisa a gestão.

COMO SE CONFIGURA
  `GOV_TEST_NIF` e `GOV_TEST_PWD` (obrigatórias); `GOV_TEST_NISS` (opcional:
  a Segurança Social Direta entra por NISS — sem ele usa-se o NIF, e uma
  conta que não entra por aí aparece como `credenciais`, nunca como
  `selectores`). A conta é de TESTE: sem MFA e com documentos (IRS e nota de
  liquidação), senão o resultado é `mfa` / `selectores` por razões que não são
  dos selectores. Sem as variáveis o job diz-o — não finge que verificou.
  `GOV_HEALTHCHECK_ENABLED=false` desliga-o.

O QUE É UM VEREDICTO (e o que cada um faz)
  ok            — a extracção devolveu documentos.
  selectores    — o portal respondeu e a página já não é a que o scraper conhece
                  (`selector_desatualizado`, `sem_documentos`, ou um passo de
                  preenchimento/navegação que falhou). **Alerta CRÍTICO** a Master
                  e Admins, à primeira.
  credenciais   — a conta de teste foi recusada. Não é do scraper: aviso aos
                  Master para rever a conta. Nunca se repete o login (cada
                  tentativa é uma autenticação num serviço do Estado).
  mfa           — a conta de teste pede um segundo factor. Idem: o scraper não
                  pode ir além do login, logo NÃO se sabe se os selectores
                  aguentam — di-lo, sem o apresentar como saudável.
  rede          — tempo esgotado, bloqueio, browser indisponível. Só avisa à
                  segunda falha seguida (uma falha de rede isolada é ruído).
  nao_configurado — faltam as variáveis: aviso semanal aos Master.

O QUE NUNCA SE FAZ
  * Nunca se regista nem se envia a password, o NIF, o screenshot do portal ou o
    texto livre do erro — só o veredicto, o passo e o código do erro (o
    screenshot de uma página autenticada tem dados da conta).
  * Nunca levanta para o laço (a excepção do batimento é a do job; o relatório
    diz o que aconteceu).
  * Um aviso por estado: o mesmo veredicto não volta a avisar antes de
    `REPETIR_ALERTA_DIAS`; um veredicto diferente avisa logo.
  * Não corre mais de uma vez em `HORAS_MINIMAS_ENTRE_EXECUCOES`: o agendador
    corre todos os jobs ao arrancar, e cada deploy seria um login na conta de
    teste. «Forçar execução» no painel ignora este intervalo.
====================================================================
"""
from __future__ import annotations

import asyncio
import logging
import os
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from database import db

logger = logging.getLogger(__name__)

COLECCAO = "gov_scrapers_health"

PORTAL_FINANCAS = "financas"
PORTAL_SEG_SOCIAL = "seg_social"
PORTAIS = (PORTAL_FINANCAS, PORTAL_SEG_SOCIAL)
ROTULO_DO_PORTAL = {
    PORTAL_FINANCAS: "Portal das Finanças",
    PORTAL_SEG_SOCIAL: "Segurança Social Direta",
}

OK = "ok"
SELECTORES = "selectores"
CREDENCIAIS = "credenciais"
MFA = "mfa"
REDE = "rede"
NAO_CONFIGURADO = "nao_configurado"
FORA_DE_PRODUCAO = "fora_de_producao"
DESLIGADO = "desligado"

NIVEL_CRITICO = "critico"
NIVEL_AVISO = "aviso"

HORAS_MINIMAS_ENTRE_EXECUCOES = 20
REPETIR_ALERTA_DIAS = 3
REPETIR_AVISO_DE_CONTA_DIAS = 7
FALHAS_DE_REDE_PARA_AVISAR = 2
#: Tecto de uma verificação (o scraper tem o seu próprio orçamento; isto é a rede de segurança).
TEMPO_MAXIMO_SEGUNDOS = 15 * 60
MAX_DESTINATARIOS = 10

TIPO_DA_NOTIFICACAO = "gov_scrapers_alert"

#: Erros que o scraper devolve e que são do PORTAL/REDE, não dos selectores.
ERROS_DE_REDE = frozenset({"timeout", "timeout_login", "unexpected_error", "scraper_ocupado"})
ERROS_DE_CREDENCIAIS = frozenset({"credenciais_invalidas"})
ERROS_DE_MFA = frozenset({
    "mfa_requerido", "mfa_timeout", "mfa_codigo_incorreto", "mfa_error", "mfa_no_input",
})
#: Passos em que uma falha (sem ser de rede) quer dizer «a página já não é esta».
PASSOS_DE_SELECTORES = frozenset({
    "select_nif_tab", "fill_nif", "fill_niss", "fill_password", "submit_login",
    "navigate_irs", "navigate_documents",
    "download_irs", "download_nota", "download_situacao", "download_extrato",
})
#: A página de login não carregou — rede/bloqueio, não selectores.
PASSOS_DE_REDE = frozenset({"init", "navigate_login", "semaphore_wait"})


# ════════════════════════════════════════════════════════════════════
#  PURAS
# ════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class Diagnostico:
    veredicto: str
    passo: str = ""
    erro: str = ""


_REGEX_DE_CODIGO = re.compile(r"[A-Za-z_][A-Za-z0-9_]{0,59}")


def _codigo(valor: Any) -> str:
    """Um identificador (``selector_desatualizado``, ``TimeoutError``), ou ``erro_desconhecido``.

    Texto livre do portal ou de uma excepção NUNCA passa: pode trazer o NIF, a password ou parte da
    página. Limpar os caracteres não chega (os dígitos de um NIF são alfanuméricos) — só se aceita
    o que já tem a forma de um código.
    """
    texto = str(valor or "").strip()
    if not texto:
        return ""
    return texto if _REGEX_DE_CODIGO.fullmatch(texto) else "erro_desconhecido"


def classificar(resultado: Any) -> Diagnostico:
    """O veredicto de um `ScraperResult` (ou de qualquer objecto com `success`/`error`/`step_failed`)."""
    if getattr(resultado, "success", False) and getattr(resultado, "documents", None):
        return Diagnostico(OK)
    if getattr(resultado, "success", False):
        # Sucesso sem documentos: o mock de dev ou uma extracção vazia — não prova nada.
        return Diagnostico(SELECTORES, "", "sem_documentos")

    erro = _codigo(getattr(resultado, "error", ""))
    passo = _codigo(getattr(resultado, "step_failed", ""))

    if erro in ERROS_DE_CREDENCIAIS:
        return Diagnostico(CREDENCIAIS, passo, erro)
    if erro in ERROS_DE_MFA or passo.startswith("mfa_"):
        return Diagnostico(MFA, passo, erro)
    if erro == "selector_desatualizado":
        return Diagnostico(SELECTORES, passo, erro)
    if erro in ERROS_DE_REDE or erro.endswith("TimeoutError") or passo in PASSOS_DE_REDE:
        return Diagnostico(REDE, passo, erro)
    if erro == "sem_documentos" or passo in PASSOS_DE_SELECTORES:
        return Diagnostico(SELECTORES, passo, erro)
    # Uma excepção que não conhecemos (Error de Playwright, etc.) é rede/ambiente até prova em contrário:
    # chamar-lhe «selectores» acordava a gestão por uma falha do browser.
    return Diagnostico(REDE, passo, erro)


@dataclass(frozen=True)
class Alerta:
    nivel: str
    portal: str
    veredicto: str
    passo: str
    erro: str
    #: ``True`` quando é o aviso de que voltou a funcionar.
    recuperou: bool = False


def _instante(valor: Any) -> Optional[datetime]:
    if isinstance(valor, datetime):
        return valor if valor.tzinfo else valor.replace(tzinfo=timezone.utc)
    if not valor:
        return None
    try:
        d = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def decidir_alerta(
    portal: str, anterior: Optional[dict], diagnostico: Diagnostico, *, agora: datetime,
) -> Optional[Alerta]:
    """Avisa quando há o que dizer e não já se disse. Sem I/O.

    ``anterior`` é o estado gravado ANTES desta execução (com ``falhas_seguidas`` já contando esta).
    """
    anterior = anterior or {}
    alertado_veredicto = anterior.get("alertado_veredicto")
    alertado_em = _instante(anterior.get("alertado_em"))

    if diagnostico.veredicto == OK:
        if alertado_veredicto and alertado_veredicto != OK:
            return Alerta(NIVEL_AVISO, portal, OK, "", "", recuperou=True)
        return None

    if diagnostico.veredicto == REDE and int(anterior.get("falhas_seguidas") or 0) < FALHAS_DE_REDE_PARA_AVISAR:
        return None

    nivel = NIVEL_CRITICO if diagnostico.veredicto == SELECTORES else NIVEL_AVISO
    dias = REPETIR_ALERTA_DIAS if nivel == NIVEL_CRITICO else REPETIR_AVISO_DE_CONTA_DIAS
    if (
        alertado_veredicto == diagnostico.veredicto
        and alertado_em is not None
        and agora - alertado_em < timedelta(days=dias)
    ):
        return None
    return Alerta(nivel, portal, diagnostico.veredicto, diagnostico.passo, diagnostico.erro)


_O_QUE_FAZER = {
    SELECTORES: (
        "O portal respondeu mas a página já não é a que o scraper conhece. É manutenção preventiva: "
        "rever os selectores em services/gov_scraper.py ({tabela}) antes de os clientes darem por isso. "
        "Se a conta de teste não tiver documentos disponíveis, o resultado é o mesmo — confirmar à mão."
    ),
    CREDENCIAIS: (
        "A conta de teste (GOV_TEST_NIF/GOV_TEST_PWD) foi recusada. Rever as credenciais; o scraper "
        "NÃO foi dado como avariado e o login não será repetido."
    ),
    MFA: (
        "A conta de teste pede um segundo factor, por isso o scraper não passa do login: NÃO se sabe se "
        "os selectores aguentam. Usar uma conta de teste sem MFA."
    ),
    REDE: (
        "Falhas seguidas por tempo esgotado ou bloqueio do portal (ou browser indisponível no worker). "
        "Pode ser o portal em baixo ou um bloqueio anti-bot ao IP do servidor."
    ),
    NAO_CONFIGURADO: (
        "O health check dos scrapers do Estado não está configurado: definir GOV_TEST_NIF e GOV_TEST_PWD "
        "no serviço worker. Até lá nenhuma mudança nos portais é detectada antes dos clientes."
    ),
}
_TABELA_DE_SELECTORES = {
    PORTAL_FINANCAS: "FINANCAS_SEL",
    PORTAL_SEG_SOCIAL: "SEG_SOCIAL_SEL",
}


def mensagem_do_alerta(alerta: Alerta) -> tuple[str, str]:
    """``(assunto, corpo)`` em texto simples. Sem dados da conta, do portal ou de clientes."""
    portal = ROTULO_DO_PORTAL.get(alerta.portal, alerta.portal)
    if alerta.recuperou:
        return (
            f"✅ Scraper do Estado recuperado — {portal}",
            f"A verificação diária voltou a obter documentos do {portal}. Nada a fazer.",
        )
    if alerta.veredicto == NAO_CONFIGURADO:
        assunto = "ℹ️ Health check dos scrapers do Estado por configurar"
    elif alerta.nivel == NIVEL_CRITICO:
        assunto = f"🚨 Scraper do Estado a precisar de manutenção — {portal}"
    else:
        assunto = f"⚠️ Scraper do Estado — {portal}: {alerta.veredicto}"

    detalhe = []
    if alerta.passo:
        detalhe.append(f"passo: {alerta.passo}")
    if alerta.erro:
        detalhe.append(f"código: {alerta.erro}")
    linhas = [
        f"Verificação diária — {portal}.",
        f"Resultado: {alerta.veredicto}" + (f" ({'; '.join(detalhe)})" if detalhe else "") + ".",
        "",
        _O_QUE_FAZER.get(alerta.veredicto, "").format(tabela=_TABELA_DE_SELECTORES.get(alerta.portal, "")),
        "",
        "Esta é uma notificação automática do CRM. Não inclui dados da conta de teste.",
    ]
    return assunto, "\n".join(linhas).strip()


def credenciais_de_teste(ambiente: Optional[dict] = None) -> dict[str, Optional[tuple[str, str]]]:
    """``{portal: (utilizador, password) | None}`` a partir do ambiente. ``None`` = não configurado."""
    env = ambiente if ambiente is not None else os.environ
    nif = (env.get("GOV_TEST_NIF") or "").strip()
    pwd = env.get("GOV_TEST_PWD") or ""
    niss = (env.get("GOV_TEST_NISS") or "").strip()
    if not nif or not pwd:
        return {PORTAL_FINANCAS: None, PORTAL_SEG_SOCIAL: None}
    return {PORTAL_FINANCAS: (nif, pwd), PORTAL_SEG_SOCIAL: (niss or nif, pwd)}


def esta_ligado(ambiente: Optional[dict] = None) -> bool:
    env = ambiente if ambiente is not None else os.environ
    return (env.get("GOV_HEALTHCHECK_ENABLED") or "true").strip().lower() not in ("false", "0", "no", "off")


# ════════════════════════════════════════════════════════════════════
#  A EXTRACÇÃO (a de produção)
# ════════════════════════════════════════════════════════════════════
async def _extrair(portal: str, utilizador: str, password: str) -> Any:
    """Corre a extracção REAL. O screenshot do resultado é deitado fora aqui mesmo."""
    from services import gov_scraper

    funcao = gov_scraper.fetch_financas_documents if portal == PORTAL_FINANCAS else gov_scraper.fetch_seg_social_documents
    try:
        resultado = await asyncio.wait_for(funcao(utilizador, password, process_id=None), timeout=TEMPO_MAXIMO_SEGUNDOS)
    except asyncio.TimeoutError:
        return Diagnostico(REDE, "", "timeout")
    except Exception as exc:  # noqa: BLE001 — nada sobe com a password no texto
        return Diagnostico(REDE, "", _codigo(type(exc).__name__))
    # O screenshot de uma página autenticada tem dados da conta: nunca sai desta função.
    if hasattr(resultado, "screenshot_b64"):
        resultado.screenshot_b64 = None
    return classificar(resultado)


# ════════════════════════════════════════════════════════════════════
#  ESTADO
# ════════════════════════════════════════════════════════════════════
async def _estado(portal: str) -> dict:
    return await db[COLECCAO].find_one({"portal": portal}, {"_id": 0}) or {}


async def _guardar_estado(portal: str, anterior: dict, diagnostico: Diagnostico, agora: datetime, alerta: Optional[Alerta]) -> dict:
    falhou = diagnostico.veredicto not in (OK,)
    falhas = (int(anterior.get("falhas_seguidas") or 0) + 1) if falhou else 0
    novo = {
        "portal": portal,
        "veredicto": diagnostico.veredicto,
        "passo": diagnostico.passo,
        "erro": diagnostico.erro,
        "ultima_execucao": agora.isoformat(),
        "falhas_seguidas": falhas,
        "desde": (
            anterior.get("desde")
            if anterior.get("veredicto") == diagnostico.veredicto and anterior.get("desde")
            else agora.isoformat()
        ),
        "alertado_em": anterior.get("alertado_em"),
        "alertado_veredicto": anterior.get("alertado_veredicto"),
    }
    if alerta is not None:
        novo["alertado_em"] = agora.isoformat()
        novo["alertado_veredicto"] = None if alerta.recuperou else alerta.veredicto
    await db[COLECCAO].update_one({"portal": portal}, {"$set": novo}, upsert=True)
    return novo


async def _estado_com_falhas_contadas(portal: str, diagnostico: Diagnostico) -> dict:
    """O estado ANTERIOR com ``falhas_seguidas`` já a contar esta execução (é o que `decidir_alerta` lê)."""
    anterior = await _estado(portal)
    if diagnostico.veredicto != OK:
        return {**anterior, "falhas_seguidas": int(anterior.get("falhas_seguidas") or 0) + 1}
    return anterior


# ════════════════════════════════════════════════════════════════════
#  AVISAR
# ════════════════════════════════════════════════════════════════════
async def _enviar_email(email: str, assunto: str, corpo: str) -> bool:
    from services.email_service import send_email

    try:
        resultado = await asyncio.wait_for(
            send_email(
                account_name="sistema", to_emails=[email], subject=assunto, body=corpo,
                force_system=True, system_purpose="NOTIFICATIONS",
            ),
            timeout=40,
        )
        return bool((resultado or {}).get("success"))
    except Exception as exc:  # noqa: BLE001 — avisar nunca derruba o job
        logger.warning("[GOV-HEALTH] Email de alerta não enviado (%s).", type(exc).__name__)
        return False


async def avisar(alerta: Alerta) -> dict[str, int]:
    """Notificação in-app + email. Critico → Master e Admins; o resto → só Master. Nunca levanta."""
    from services.alert_audience import destinatarios_de_infraestrutura
    from services.realtime_notifications import send_realtime_notification

    resumo = {"destinatarios": 0, "notificacoes": 0, "emails": 0}
    try:
        destinatarios = await destinatarios_de_infraestrutura(incluir_admins=alerta.nivel == NIVEL_CRITICO)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[GOV-HEALTH] Destinatários não resolvidos (%s).", type(exc).__name__)
        return resumo
    destinatarios = destinatarios[:MAX_DESTINATARIOS]
    resumo["destinatarios"] = len(destinatarios)
    if not destinatarios:
        logger.warning("[GOV-HEALTH] Alerta %s/%s sem destinatários (nenhum Master/Admin activo).", alerta.portal, alerta.veredicto)
        return resumo

    assunto, corpo = mensagem_do_alerta(alerta)
    for destinatario in destinatarios:
        try:
            await send_realtime_notification(
                user_id=destinatario["id"], title=assunto, message=" ".join(corpo.split("\n\n")[:2]).replace("\n", " "),
                notification_type=TIPO_DA_NOTIFICACAO, link="/admin",
            )
            resumo["notificacoes"] += 1
        except Exception as exc:  # noqa: BLE001
            logger.warning("[GOV-HEALTH] Notificação não enviada (%s).", type(exc).__name__)
        if destinatario.get("email") and await _enviar_email(destinatario["email"], assunto, corpo):
            resumo["emails"] += 1
    return resumo


# ════════════════════════════════════════════════════════════════════
#  O JOB
# ════════════════════════════════════════════════════════════════════
def _agora() -> datetime:
    return datetime.now(timezone.utc)


async def _correu_ha_pouco(agora: datetime) -> bool:
    limite = timedelta(hours=HORAS_MINIMAS_ENTRE_EXECUCOES)
    for portal in PORTAIS:
        ultima = _instante((await _estado(portal)).get("ultima_execucao"))
        if ultima is not None and agora - ultima < limite:
            return True
    return False


async def correr_healthcheck(*, respeitar_intervalo: bool = True, agora: Optional[datetime] = None) -> dict[str, Any]:
    """Corre a verificação dos dois portais. Devolve ``{portal: veredicto}`` (e razões de salto).

    Levanta só o cancelamento; qualquer outra falha fica no relatório.
    """
    agora = agora or _agora()
    relatorio: dict[str, Any] = {}

    if not esta_ligado():
        return {"saltado": DESLIGADO}
    if os.environ.get("ENVIRONMENT", "dev") != "production":
        # Fora de produção o scraper devolve um resultado simulado: verificar seria fingir.
        return {"saltado": FORA_DE_PRODUCAO}

    credenciais = credenciais_de_teste()
    if not any(credenciais.values()):
        diagnostico = Diagnostico(NAO_CONFIGURADO)
        for portal in PORTAIS:
            anterior = await _estado_com_falhas_contadas(portal, diagnostico)
            alerta = decidir_alerta(portal, anterior, diagnostico, agora=agora)
            await _guardar_estado(portal, await _estado(portal), diagnostico, agora, alerta)
            relatorio[portal] = NAO_CONFIGURADO
            if alerta is not None and portal == PORTAL_FINANCAS:
                # Um só aviso para os dois portais.
                await avisar(alerta)
        logger.warning("[GOV-HEALTH] GOV_TEST_NIF/GOV_TEST_PWD por definir — nada foi verificado.")
        return relatorio

    if respeitar_intervalo and await _correu_ha_pouco(agora):
        return {"saltado": "recente"}

    for portal in PORTAIS:
        utilizador, password = credenciais[portal]
        diagnostico = await _extrair(portal, utilizador, password)
        anterior = await _estado(portal)
        contado = await _estado_com_falhas_contadas(portal, diagnostico)
        alerta = decidir_alerta(portal, contado, diagnostico, agora=agora)
        if alerta is not None:
            await avisar(alerta)
        await _guardar_estado(portal, anterior, diagnostico, agora, alerta)
        relatorio[portal] = diagnostico.veredicto
        logger.info(
            "[GOV-HEALTH] %s: %s (passo=%s, código=%s)%s", ROTULO_DO_PORTAL[portal], diagnostico.veredicto,
            diagnostico.passo or "-", diagnostico.erro or "-", " — alerta enviado" if alerta else "",
        )
    return relatorio


async def estado_dos_portais() -> dict[str, dict]:
    """O último estado de cada portal (para um painel ou para o script)."""
    return {portal: await _estado(portal) for portal in PORTAIS}


__all__ = [
    "CREDENCIAIS", "MFA", "NAO_CONFIGURADO", "OK", "REDE", "SELECTORES",
    "Alerta", "Diagnostico", "avisar", "classificar", "correr_healthcheck", "credenciais_de_teste",
    "decidir_alerta", "estado_dos_portais", "mensagem_do_alerta",
]
