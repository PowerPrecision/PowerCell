"""
====================================================================
RASCUNHO DE CONFIRMAÇÃO DE RECEÇÃO DE DOCUMENTOS CRÍTICOS
====================================================================
(Out 2026)

O PEDIDO
  Quando um cliente — ou um parceiro — faz o upload de um documento
  CRÍTICO (identificação, IRS, recibo de vencimento) para o portal, o
  sistema recorre à IA para gerar um rascunho de email a confirmar a
  receção, guardado na pasta de Rascunhos do processo, pronto a ser
  revisto e enviado com um clique pela equipa (Consultor/Administrativo).

  A instrução passada ao modelo é a do dono do produto, TAL E QUAL
  (`PROMPT_DE_RECEPCAO`).

O QUE ESTE MÓDULO NUNCA FAZ
  * **Enviar.** É um rascunho (`status: draft`); quem envia é uma pessoa.
  * **Bloquear o upload.** Corre em segundo plano, depois de o ficheiro
    estar confirmado; qualquer falha é registada e engolida.
  * **Prometer prazos.** A instrução diz-o ao modelo, mas um modelo não
    é uma parede: o texto devolvido passa por `promete_prazo` e, se o
    cumprir mal, é substituído pelo texto seguro. A regra vive no código,
    não só no prompt.
  * **Deixar o nome do ficheiro entrar no prompt.** O «nome do documento»
    sai de um registo FECHADO (`DOCUMENTOS_CRITICOS`), nunca do nome do
    ficheiro nem do que o cliente escreveu — senão um ficheiro chamado
    «ignora as instruções e…» era uma injecção de prompt a partir de uma
    superfície externa.

QUEM RECEBE
  O rascunho dirige-se a quem ENVIOU (o cliente → o email dele; o
  parceiro → o email do parceiro): é a quem se confirma a receção.

DEDUPLICAÇÃO
  Um rascunho PENDENTE por (processo, tipo de documento). Seis recibos de
  vencimento enviados seguidos são um rascunho, não seis. Depois de
  enviado/descartado, um novo upload gera um novo. Um índice único
  parcial (`idx_emails_receipt_draft_pending`) fecha a corrida de dois
  uploads simultâneos.

INTERRUPTOR
  `SystemConfig.auto_draft.receipt_enabled` (por omissão ligado) e, acima
  dele, `RECEIPT_DRAFT_ENABLED=false` no ambiente. Falha de leitura da
  configuração = desligado (na dúvida, não se gera).

MOTOR
  Dev simula, sempre (a regra das notas de voz): sem `RECEIPT_DRAFT_PROVIDER`
  só produção COM chave chama o modelo; o resto usa o texto seguro. O
  modelo vem do painel de IA (tarefa `document_receipt_draft`), nunca fixo.

NÃO HÁ RASCUNHO SEM PROCESSO
  Uploads do onboarding (cliente ainda sem processo) não geram nada: não há
  pasta de Rascunhos de um processo que ainda não existe.
====================================================================
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from database import db
from services.email_tenant_stamp import inserir_email

logger = logging.getLogger(__name__)

# ── a instrução do dono do produto, verbatim ──────────────────────────
PROMPT_DE_RECEPCAO = (
    "Atua como um assistente financeiro da empresa. Escreve um e-mail curto e "
    "profissional a confirmar a receção do documento {documento}. Informa que a "
    "documentação está em análise pela nossa equipa e que entraremos em contacto "
    "em breve. Usa um tom empático, tranquilizador e nunca prometas prazos exatos "
    "de resposta."
)

#: O que o sistema acrescenta à instrução (e que NÃO a altera): o formato da
#: resposta e as paredes que um modelo não deve ultrapassar.
SYSTEM_PROMPT = (
    "És o assistente de comunicação de uma empresa de intermediação de crédito "
    "habitação em Portugal. Escreves em português de Portugal (pt-PT). "
    "Devolves APENAS um objecto JSON válido, sem texto antes ou depois, no "
    'formato {"subject": "...", "body": "..."}, com o corpo em texto simples '
    "(sem HTML nem markdown). Não inventes factos: não menciones valores, "
    "nomes de pessoas além do destinatário, nem o conteúdo do documento. "
    "Não indiques nenhum prazo, data ou número de dias."
)

CHAVE_AI_CONFIG = "document_receipt_draft"
MODELO_OMISSAO = "gpt-4o-mini"
TIMEOUT_OMISSAO = 45.0

PROVIDER_OPENAI = "openai"
PROVIDER_MOCK = "mock"
PROVIDERS_VALIDOS = frozenset({PROVIDER_OPENAI, PROVIDER_MOCK})

KIND_DO_RASCUNHO = "document_receipt"

MAX_ASSUNTO = 150
MAX_CORPO = 2000

ORIGEM_CLIENTE = "cliente"
ORIGEM_PARCEIRO = "parceiro"


# ====================================================================
# O REGISTO FECHADO DOS DOCUMENTOS CRÍTICOS
# ====================================================================
@dataclass(frozen=True)
class DocumentoCritico:
    tipo: str
    rotulo: str


#: tipo → (rótulo que vai no email, marcas que o identificam). As marcas são
#: comparadas sobre a categoria/etiqueta NORMALIZADA (sem acentos, minúsculas,
#: `_`/`-` → espaço), como palavras inteiras.
_REGISTO: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("identificacao", "Documento de Identificação", (
        "cartao cidadao", "cartao de cidadao", "identificacao", "bilhete de identidade",
        "passaporte", "titulo de residencia", "cc",
    )),
    ("irs", "Declaração de IRS", (
        "irs", "declaracao de irs", "declaracao irs", "nota de liquidacao",
        "declaracao imposto renda", "declaracao de imposto",
    )),
    ("recibo_vencimento", "Recibo de Vencimento", (
        "recibo vencimento", "recibos vencimento", "recibo de vencimento",
        "recibos de vencimento",
    )),
)

DOCUMENTOS_CRITICOS: tuple[DocumentoCritico, ...] = tuple(
    DocumentoCritico(tipo, rotulo) for tipo, rotulo, _ in _REGISTO
)


def _normalizar(texto: Any) -> str:
    bruto = unicodedata.normalize("NFKD", str(texto or ""))
    sem_acentos = "".join(c for c in bruto if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", re.sub(r"[_\-/]+", " ", sem_acentos.lower())).strip()


def classificar_documento_critico(*candidatas: Any) -> Optional[DocumentoCritico]:
    """O primeiro documento crítico que alguma das candidatas identifica.

    As candidatas são categoria / etiqueta do PEDIDO — nunca o nome do
    ficheiro (ver o topo do módulo).
    """
    for candidata in candidatas:
        texto = _normalizar(candidata)
        if not texto:
            continue
        envolvido = f" {texto} "
        for tipo, rotulo, marcas in _REGISTO:
            if any(f" {marca} " in envolvido for marca in marcas):
                return DocumentoCritico(tipo, rotulo)
    return None


# ====================================================================
# PURO: prompt, resposta, texto seguro
# ====================================================================
def construir_mensagens(documento: DocumentoCritico, contexto: dict) -> list[dict]:
    """As mensagens para o modelo: a instrução verbatim + o contexto."""
    instrucao = PROMPT_DE_RECEPCAO.format(documento=documento.rotulo)
    linhas = []
    if contexto.get("nome_destinatario"):
        linhas.append(f"Destinatário (tratar pelo nome): {contexto['nome_destinatario']}")
    if contexto.get("empresa"):
        linhas.append(f"Empresa (assinar o email): {contexto['empresa']}")
    if contexto.get("processo"):
        linhas.append(f"Referência do processo: {contexto['processo']}")
    corpo_do_pedido = instrucao + ("\n\nContexto:\n" + "\n".join(linhas) if linhas else "")
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": corpo_do_pedido},
    ]


#: «Prometer prazos exatos»: números seguidos de unidade de tempo, «amanhã»,
#: «hoje», «até <dia>», «dentro de», «no próprio dia», «imediatamente»,
#: «24h»/«48 horas», dias da semana. Larga de propósito: um falso positivo
#: custa o texto seguro, um falso negativo custa uma promessa por escrito.
_PADROES_DE_PRAZO = re.compile(
    r"(\b\d+\s*(?:h\b|horas?|dias?|semanas?|meses|mes\b|minutos?|úteis|uteis)|"
    r"\bamanh[ãa]\b|\bhoje\b|\bdentro\s+de\b|\bat[ée]\s+(?:ao?s?\s+)?"
    r"(?:segunda|terça|terca|quarta|quinta|sexta|s[áa]bado|domingo|final|fim|\d)|"
    r"\bimediatamente\b|\bno\s+pr[óo]prio\s+dia\b|\bn[oa]s?\s+pr[óo]xim[oa]s?\s+\w+|"
    r"\best[ae]\s+(?:semana|tarde|manh[ãa]|m[êe]s)\b|"
    r"\bdias?\s+[úu]teis\b|\b(?:um|uma|dois|duas|tr[êe]s|quatro|cinco|seis|sete|oito|nove|dez|"
    r"quinze|vinte|trinta)\s+(?:horas?|dias?|semanas?|meses)\b)",
    re.IGNORECASE,
)


def promete_prazo(texto: str) -> bool:
    """O texto compromete a empresa com um prazo?"""
    return bool(_PADROES_DE_PRAZO.search(str(texto or "")))


def texto_seguro(documento: DocumentoCritico, contexto: dict) -> tuple[str, str]:
    """Assunto e corpo que nunca falham: servem de recuo e de motor simulado."""
    nome = (contexto.get("nome_destinatario") or "").strip()
    saudacao = f"Caro(a) {nome}," if nome else "Caro(a) cliente,"
    referencia = contexto.get("processo")
    sobre = f" referente ao processo {referencia}" if referencia else ""
    empresa = (contexto.get("empresa") or "").strip()
    assinatura = empresa or "A equipa"
    assunto = f"Confirmação de receção – {documento.rotulo}"
    corpo = (
        f"{saudacao}\n\n"
        f"Confirmamos a receção do documento «{documento.rotulo}»{sobre}.\n\n"
        "A documentação encontra-se agora em análise pela nossa equipa e entraremos "
        "em contacto consigo em breve.\n\n"
        "Agradecemos a sua confiança e a sua colaboração. Se tiver alguma questão "
        "entretanto, estamos ao seu dispor.\n\n"
        f"Com os melhores cumprimentos,\n{assinatura}"
    )
    return assunto, corpo


def interpretar_resposta(texto: str, documento: DocumentoCritico, contexto: dict) -> tuple[str, str, bool]:
    """Assunto, corpo e se a resposta do modelo foi aproveitada.

    Qualquer coisa fora do formato, vazia, comprida demais ou que prometa um
    prazo cai no texto seguro — com `False`, para o chamador o registar.
    """
    seguro_assunto, seguro_corpo = texto_seguro(documento, contexto)
    try:
        dados = json.loads(texto or "")
    except (TypeError, ValueError):
        return seguro_assunto, seguro_corpo, False
    if not isinstance(dados, dict):
        return seguro_assunto, seguro_corpo, False

    assunto = str(dados.get("subject") or "").strip()
    corpo = str(dados.get("body") or "").strip()
    if not assunto or not corpo:
        return seguro_assunto, seguro_corpo, False
    if len(assunto) > MAX_ASSUNTO or len(corpo) > MAX_CORPO:
        return seguro_assunto, seguro_corpo, False
    if "<" in corpo and ">" in corpo:  # HTML num campo de texto simples
        return seguro_assunto, seguro_corpo, False
    if promete_prazo(assunto) or promete_prazo(corpo):
        return seguro_assunto, seguro_corpo, False
    return assunto, corpo, True


# ====================================================================
# CONFIGURAÇÃO E MOTOR
# ====================================================================
_VERDADEIRO = {"1", "true", "yes", "sim", "on"}
_FALSO = {"0", "false", "no", "nao", "não", "off"}


def _env(ambiente, chave: str) -> str:
    return str((ambiente if ambiente is not None else os.environ).get(chave) or "").strip().lower()


def resolver_provider(ambiente=None) -> str:
    """`RECEIPT_DRAFT_PROVIDER` manda; sem ele, OpenAI só em produção COM chave."""
    declarado = _env(ambiente, "RECEIPT_DRAFT_PROVIDER")
    if declarado:
        if declarado in PROVIDERS_VALIDOS:
            return declarado
        logger.warning("[RASCUNHO-RECEÇÃO] RECEIPT_DRAFT_PROVIDER='%s' desconhecido; a usar '%s'",
                       declarado, PROVIDER_MOCK)
        return PROVIDER_MOCK
    producao = any(_env(ambiente, c) in {"production", "prod", "producao", "produção"}
                   for c in ("ENVIRONMENT", "APP_ENV"))
    tem_chave = bool(_env(ambiente, "OPENAI_API_KEY") or _env(ambiente, "EMERGENT_LLM_KEY"))
    return PROVIDER_OPENAI if producao and tem_chave else PROVIDER_MOCK


async def esta_activo(ambiente=None) -> bool:
    """O interruptor. Na dúvida (configuração ilegível), desligado."""
    declarado = _env(ambiente, "RECEIPT_DRAFT_ENABLED")
    if declarado in _FALSO:
        return False
    # Em testes (`TESTING=true`) a funcionalidade está DESLIGADA por omissão e
    # liga-se pedindo-a (`RECEIPT_DRAFT_ENABLED=true`): um upload simulado por
    # qualquer outro teste não pode ir à configuração nem criar rascunhos.
    if declarado not in _VERDADEIRO and _env(ambiente, "TESTING") in _VERDADEIRO:
        return False
    try:
        from services.system_config import get_system_config

        config = await get_system_config()
        return bool(getattr(config.auto_draft, "receipt_enabled", True))
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RASCUNHO-RECEÇÃO] Configuração ilegível (%s): rascunho não gerado.", exc)
        return False


async def resolver_modelo() -> str:
    """Modelo do painel de IA (tarefa `document_receipt_draft`), nunca fixo."""
    try:
        from services.ai_page_analyzer import get_ai_config

        configurado = (await get_ai_config() or {}).get(CHAVE_AI_CONFIG)
        if configurado:
            return str(configurado)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RASCUNHO-RECEÇÃO] Painel de IA indisponível (%s): modelo por omissão.", exc)
    return MODELO_OMISSAO


async def _chamar_modelo(mensagens: list[dict], modelo: str) -> str:
    from services.ai_document import get_openai_client

    cliente = get_openai_client()
    resposta = await asyncio.wait_for(
        cliente.chat.completions.create(
            model=modelo,
            messages=mensagens,
            temperature=0.4,
            max_tokens=700,
            response_format={"type": "json_object"},
        ),
        timeout=TIMEOUT_OMISSAO,
    )
    return resposta.choices[0].message.content or ""


async def gerar_texto(documento: DocumentoCritico, contexto: dict, *, ambiente=None) -> tuple[str, str, str]:
    """(assunto, corpo, origem do texto: `ia` | `simulado` | `recuo`)."""
    if resolver_provider(ambiente) != PROVIDER_OPENAI:
        assunto, corpo = texto_seguro(documento, contexto)
        return assunto, corpo, "simulado"
    try:
        modelo = await resolver_modelo()
        bruto = await _chamar_modelo(construir_mensagens(documento, contexto), modelo)
    except Exception as exc:  # noqa: BLE001 — a IA em baixo não pode parar o rascunho
        logger.warning("[RASCUNHO-RECEÇÃO] Falha do modelo (%s): texto seguro.", exc)
        assunto, corpo = texto_seguro(documento, contexto)
        return assunto, corpo, "recuo"
    assunto, corpo, aproveitada = interpretar_resposta(bruto, documento, contexto)
    if not aproveitada:
        logger.warning("[RASCUNHO-RECEÇÃO] Resposta do modelo recusada (formato/prazo): texto seguro.")
    return assunto, corpo, ("ia" if aproveitada else "recuo")


# ====================================================================
# ORQUESTRAÇÃO
# ====================================================================
_CAMPOS_DE_RESPONSAVEL = (
    "assigned_consultor_ids", "assigned_consultor_id", "consultor_id", "consultant_id",
    "assigned_mediador_ids", "assigned_mediador_id", "mediador_id",
)


def responsavel_do_processo(processo: Optional[dict]) -> Optional[str]:
    """Quem fica com o rascunho: o consultor primeiro, depois o intermediário."""
    for campo in _CAMPOS_DE_RESPONSAVEL:
        valor = (processo or {}).get(campo)
        for candidato in (valor if isinstance(valor, (list, tuple)) else [valor]):
            texto = str(candidato or "").strip()
            if texto:
                return texto
    return None


def _email_valido(valor: Any) -> Optional[str]:
    from utils.input_sanitization import sanitize_email

    return sanitize_email(str(valor or "")) or None


@dataclass(frozen=True)
class Destinatario:
    nome: str
    email: str


async def destinatario_do_cliente(processo: dict, cliente: Optional[dict]) -> Optional[Destinatario]:
    """O email de quem enviou (cliente): a ficha do titular, ou o do processo."""
    email = None
    nome = ""
    if cliente:
        try:
            from services.encryption import decrypt_client_data

            ficha = decrypt_client_data(dict(cliente))
            email = _email_valido((ficha.get("contacto") or {}).get("email"))
            nome = str(ficha.get("nome") or "").strip()
        except Exception as exc:  # noqa: BLE001
            logger.warning("[RASCUNHO-RECEÇÃO] Ficha do cliente ilegível (%s).", exc)
    email = email or _email_valido((processo or {}).get("client_email"))
    nome = nome or str((processo or {}).get("client_name") or "").strip()
    return Destinatario(nome, email) if email else None


def destinatario_do_parceiro(parceiro: Optional[dict]) -> Optional[Destinatario]:
    email = _email_valido((parceiro or {}).get("email"))
    return Destinatario(str((parceiro or {}).get("name") or "").strip(), email) if email else None


def _nome_da_empresa(processo: Optional[dict]) -> str:
    nome = str((processo or {}).get("company_name") or "").strip()
    if nome:
        return nome
    try:
        from services.email_v2 import COMPANY_NAME

        return str(COMPANY_NAME or "")
    except Exception:  # noqa: BLE001
        return ""


async def criar_rascunho_de_rececao(
    process_id: str,
    documento: DocumentoCritico,
    destinatario: Destinatario,
    *,
    origem: str,
    ambiente=None,
    db_handle=None,
) -> dict:
    """Cria o rascunho. Devolve `{"success": bool, "reason"|"draft_id": …}`.

    Nunca levanta: é chamado em segundo plano a seguir a um upload que já
    foi confirmado. `db_handle` é o do módulo que agenda (o que os testes
    patcham), nunca um `db` de importação própria.
    """
    base = db_handle if db_handle is not None else db
    try:
        if not await esta_activo(ambiente):
            return {"success": False, "reason": "disabled"}

        pendente = await base.emails.find_one({
            "process_id": process_id, "auto_draft_kind": KIND_DO_RASCUNHO,
            "auto_draft_doc_type": documento.tipo, "status": "draft",
        }, {"_id": 0, "id": 1})
        if pendente:
            return {"success": False, "reason": "duplicate", "existing_draft_id": pendente.get("id")}

        processo = await base.processes.find_one(
            {"id": process_id},
            {"_id": 0, "id": 1, "process_number": 1, "client_name": 1, "company_name": 1,
             "company_id": 1, "network_id": 1, **{c: 1 for c in _CAMPOS_DE_RESPONSAVEL}},
        )
        if not processo:
            return {"success": False, "reason": "process_not_found"}

        contexto = {
            "nome_destinatario": destinatario.nome,
            "empresa": _nome_da_empresa(processo),
            "processo": processo.get("process_number") or "",
        }
        assunto, corpo, fonte = await gerar_texto(documento, contexto, ambiente=ambiente)

        agora = datetime.now(timezone.utc)
        rascunho = {
            "id": str(uuid.uuid4()),
            "process_id": process_id,
            "direction": "sent",
            "from_email": "sistema@powercell.pt",
            "to_emails": [destinatario.email],
            "subject": assunto,
            "body": corpo,
            "status": "draft",
            "is_auto_draft": True,
            "auto_draft_kind": KIND_DO_RASCUNHO,
            "auto_draft_doc_type": documento.tipo,
            "auto_draft_doc_label": documento.rotulo,
            "auto_draft_origin": origem,
            "auto_draft_text_source": fonte,
            "created_at": agora.isoformat(),
            "updated_at": agora.isoformat(),
            "created_by": responsavel_do_processo(processo),
            "notes": "Rascunho gerado automaticamente — rever antes de enviar.",
            "is_important": False, "is_read": True, "is_starred": False, "is_archived": False,
            "labels": ["auto-draft", "confirmacao-de-rececao"],
        }
        if processo.get("company_id"):
            rascunho["company_id"] = processo["company_id"]
        from services.email_draft_service import stamp_draft_ttl_fields

        stamp_draft_ttl_fields(rascunho, now=agora)

        try:
            await inserir_email(base, rascunho)
        except Exception as exc:  # noqa: BLE001
            if "duplicate key" in str(exc).lower() or type(exc).__name__ == "DuplicateKeyError":
                return {"success": False, "reason": "duplicate"}
            raise

        await _registar_no_historico(process_id, documento, origem)
        logger.info("[RASCUNHO-RECEÇÃO] Rascunho %s criado (processo=%s, tipo=%s, texto=%s).",
                    rascunho["id"], process_id, documento.tipo, fonte)
        return {"success": True, "draft_id": rascunho["id"], "text_source": fonte}
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RASCUNHO-RECEÇÃO] Falha a criar o rascunho (processo=%s): %s", process_id, exc)
        return {"success": False, "reason": "error"}


async def _registar_no_historico(process_id: str, documento: DocumentoCritico, origem: str) -> None:
    try:
        from services.history import log_history

        await log_history(
            process_id,
            user={"id": None, "name": "Sistema", "role": "system"},
            action="AUTO_DRAFT_RECEIPT_CREATED",
            field="rascunho",
            old_value=None,
            new_value=f"Confirmação de receção: {documento.rotulo} ({origem})",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RASCUNHO-RECEÇÃO] Falha a registar no histórico: %s", exc)


# ====================================================================
# AS DUAS PORTAS (cliente do Portal e parceiro)
# ====================================================================
async def _candidatas_com_o_pedido(db_handle, categoria, custom_label, request_id) -> list:
    """Categoria e etiqueta do upload + as do PEDIDO a que responde, se houver.

    O pedido só se consulta quando o upload, por si, não identificou um
    documento crítico: o caso comum (upload solto, ou categoria já clara) não
    paga a ida à base de dados.
    """
    candidatas = [categoria, custom_label]
    if classificar_documento_critico(*candidatas) or not request_id:
        return candidatas
    pedido = await db_handle.documents.find_one(
        {"id": request_id}, {"_id": 0, "category": 1, "custom_label": 1, "label": 1},
    )
    return [*candidatas, *candidatas_de_um_pedido(pedido)]


async def agendar_apos_upload_do_cliente(
    db_handle,
    *,
    process: Optional[dict],
    client: Optional[dict],
    categoria: Any,
    custom_label: Any = None,
    request_id: Optional[str] = None,
) -> bool:
    """Agenda o rascunho se o upload do cliente for de um documento crítico.

    Devolve se agendou. NUNCA levanta: o upload já está confirmado.
    """
    try:
        process_id = (process or {}).get("id")
        if not process_id:
            return False  # sem processo não há pasta de Rascunhos
        candidatas = await _candidatas_com_o_pedido(db_handle, categoria, custom_label, request_id)
        documento = classificar_documento_critico(*candidatas)
        if not documento:
            return False
        agendar(
            lambda: _rascunho_do_cliente(db_handle, process, client, documento),
            nome=f"receipt-draft:{process_id}:{documento.tipo}",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RASCUNHO-RECEÇÃO] Não foi possível agendar (cliente): %s", exc)
        return False


async def agendar_apos_upload_do_parceiro(
    db_handle,
    *,
    process: Optional[dict],
    parceiro: Optional[dict],
    categoria: Any,
    request_id: Optional[str] = None,
) -> bool:
    """O mesmo, para o upload de um parceiro (o destinatário é o parceiro)."""
    try:
        process_id = (process or {}).get("id")
        if not process_id:
            return False
        candidatas = await _candidatas_com_o_pedido(db_handle, categoria, None, request_id)
        documento = classificar_documento_critico(*candidatas)
        if not documento:
            return False
        agendar(
            lambda: _rascunho_do_parceiro(db_handle, process_id, parceiro, documento),
            nome=f"receipt-draft:{process_id}:{documento.tipo}",
        )
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RASCUNHO-RECEÇÃO] Não foi possível agendar (parceiro): %s", exc)
        return False


async def _rascunho_do_cliente(db_handle, processo, cliente, documento) -> dict:
    destinatario = await destinatario_do_cliente(processo or {}, cliente)
    if not destinatario:
        return {"success": False, "reason": "no_recipient"}
    return await criar_rascunho_de_rececao(
        processo["id"], documento, destinatario, origem=ORIGEM_CLIENTE, db_handle=db_handle,
    )


async def _rascunho_do_parceiro(db_handle, process_id, parceiro, documento) -> dict:
    destinatario = destinatario_do_parceiro(parceiro)
    if not destinatario:
        return {"success": False, "reason": "no_recipient"}
    return await criar_rascunho_de_rececao(
        process_id, documento, destinatario, origem=ORIGEM_PARCEIRO, db_handle=db_handle,
    )


def agendar(coroutine_factory, *, nome: str) -> None:
    """Põe a geração em segundo plano com referência forte; nunca levanta."""
    try:
        from services.background_tasks import spawn_background_task

        spawn_background_task(coroutine_factory(), name=nome)
    except Exception as exc:  # noqa: BLE001
        logger.warning("[RASCUNHO-RECEÇÃO] Não foi possível agendar (%s).", exc)


def candidatas_de_um_pedido(pedido: Optional[dict]) -> list[Any]:
    """Os campos de um pedido de documentos que o identificam (nunca o ficheiro)."""
    return [(pedido or {}).get(c) for c in ("category", "custom_label", "label")]
