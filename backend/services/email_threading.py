"""Threading de email conforme RFC 5322 — cabeçalhos e agrupamento.

PORQUÊ ESTE MÓDULO
------------------
O PowerCell já lia ``Message-ID`` / ``In-Reply-To`` / ``References`` do
IMAP e usava-os no *Smart Threading* (herdar o ``process_id`` do email
pai). Mas o que o CRM **envia** saía sem nenhum destes cabeçalhos:

* sem ``Message-ID`` próprio, a resposta do cliente à nossa mensagem não
  tinha a que se agarrar;
* sem ``In-Reply-To``, a nossa resposta nascia órfã da conversa.

Resultado: cada troca partia-se em mensagens soltas, no nosso Webmail e
no cliente de email do destinatário. Isto fecha o ciclo.

Funções puras (sem I/O, sem BD) — testáveis à parte.
"""
from __future__ import annotations

import re
from email.utils import make_msgid
from typing import Any, Dict, Iterable, List, Optional

# Prefixos de resposta/encaminhamento a remover no agrupamento por assunto.
# Cobre PT, EN e ES: os clientes de email localizam-nos e uma conversa não
# se pode partir só porque alguém respondeu a partir do Outlook espanhol.
_SUBJECT_PREFIX_RE = re.compile(
    r"^\s*(?:(?:re|rv|res|resposta|fw|fwd|enc|encaminhado|reenv)\s*(?:\[\d+\])?\s*:\s*)+",
    re.IGNORECASE,
)

# Um References pode crescer sem limite ao fim de muitas trocas. A RFC 5322
# permite truncar; a convenção (Thunderbird/Gmail) é guardar o primeiro (a
# raiz da conversa) e os últimos, que é o que identifica o ramo actual.
MAX_REFERENCES = 20


def normalize_message_id(value: Optional[str]) -> Optional[str]:
    """Devolve o Message-ID na forma canónica ``<id@dominio>``.

    Os servidores são inconsistentes a incluir os angle brackets. Comparar
    ``abc@x.pt`` com ``<abc@x.pt>`` como strings diferentes partia threads
    por uma razão puramente cosmética.

    Returns:
        O id entre ``<>``, ou ``None`` se não houver nada aproveitável.
    """
    if not value or not isinstance(value, str):
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    cleaned = cleaned.strip("<>").strip()
    if not cleaned:
        return None
    return f"<{cleaned}>"


def parse_references(value: Any) -> List[str]:
    """Normaliza um ``References`` (string com espaços ou lista) numa lista.

    Preserva a ordem e remove duplicados — a ordem é o que descreve a
    cadeia da conversa, da raiz para a folha.
    """
    if not value:
        return []
    if isinstance(value, str):
        candidates: Iterable[str] = value.replace(",", " ").split()
    elif isinstance(value, (list, tuple)):
        candidates = value
    else:
        return []

    seen = set()
    result: List[str] = []
    for item in candidates:
        norm = normalize_message_id(item if isinstance(item, str) else str(item))
        if norm and norm not in seen:
            seen.add(norm)
            result.append(norm)
    return result


def build_reference_chain(
    parent_message_id: Optional[str],
    parent_references: Any = None,
) -> List[str]:
    """Constrói o ``References`` de uma resposta ao email pai.

    Regra da RFC 5322: as referências do pai, seguidas do Message-ID do
    próprio pai.

    Args:
        parent_message_id: ``Message-ID`` do email a que se responde.
        parent_references: ``References`` do email pai.

    Returns:
        Cadeia normalizada, truncada a ``MAX_REFERENCES`` mantendo a raiz.
    """
    chain = parse_references(parent_references)
    parent = normalize_message_id(parent_message_id)
    if parent and parent not in chain:
        chain.append(parent)

    if len(chain) > MAX_REFERENCES:
        # Primeiro (raiz da conversa) + a cauda mais recente.
        chain = chain[:1] + chain[-(MAX_REFERENCES - 1):]
    return chain


def generate_message_id(domain: Optional[str] = None) -> str:
    """Gera um ``Message-ID`` único para uma mensagem que sai daqui.

    Usa ``email.utils.make_msgid`` (stdlib) — sem dependências novas.
    """
    if domain:
        clean = domain.strip().lstrip("@")
        if clean:
            return make_msgid(domain=clean)
    return make_msgid()


def domain_from_email(address: Optional[str]) -> Optional[str]:
    """Extrai o domínio de um endereço, para o Message-ID sair coerente."""
    if not address or "@" not in address:
        return None
    domain = address.rsplit("@", 1)[-1].strip().strip(">")
    return domain or None


def normalize_subject(subject: Optional[str]) -> str:
    """Remove prefixos ``Re:``/``Fwd:`` repetidos e normaliza espaços.

    Usado só como ÚLTIMO recurso no agrupamento: assuntos iguais entre
    interlocutores diferentes não são a mesma conversa, e quem chama tem
    de o ter em conta (ver ``thread_key``).
    """
    if not subject or not isinstance(subject, str):
        return ""
    previous = None
    current = subject.strip()
    # Repetido porque "Re: Fwd: Re:" precisa de várias passagens.
    while current != previous:
        previous = current
        current = _SUBJECT_PREFIX_RE.sub("", current).strip()
    return re.sub(r"\s+", " ", current)


def thread_key(email: Dict[str, Any]) -> str:
    """Chave de agrupamento de um email numa conversa.

    Preferência, da mais fiável para a menos:

    1. A raiz de ``references`` — identifica a conversa mesmo quando um
       interlocutor muda o assunto a meio.
    2. ``in_reply_to`` — resposta directa sem cadeia completa.
    3. O próprio ``message_id`` — a mensagem é a raiz de uma conversa nova.
    4. O assunto normalizado — último recurso, para servidores que não
       devolvem estes cabeçalhos (acontece com alguns IMAP antigos).
    """
    if not isinstance(email, dict):
        return ""

    refs = parse_references(email.get("references"))
    if refs:
        return refs[0]

    parent = normalize_message_id(email.get("in_reply_to"))
    if parent:
        return parent

    own = normalize_message_id(email.get("message_id"))
    if own:
        return own

    subject = normalize_subject(email.get("subject"))
    return f"subject:{subject.lower()}" if subject else ""
