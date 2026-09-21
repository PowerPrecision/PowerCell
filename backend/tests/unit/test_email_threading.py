"""Épico 5 — threading RFC 5322: cabeçalhos de saída e agrupamento.

Fecha o elo que faltava: o CRM lia Message-ID/In-Reply-To do IMAP mas
enviava sem eles, partindo cada troca em mensagens soltas.
"""
from services.email_threading import (
    MAX_REFERENCES,
    build_reference_chain,
    domain_from_email,
    generate_message_id,
    normalize_message_id,
    normalize_subject,
    parse_references,
    thread_key,
)


# ====================================================================
# normalize_message_id
# ====================================================================

def test_normalize_message_id_adds_angle_brackets():
    assert normalize_message_id("abc@dominio.pt") == "<abc@dominio.pt>"


def test_normalize_message_id_is_idempotent():
    assert normalize_message_id("<abc@dominio.pt>") == "<abc@dominio.pt>"


def test_normalize_message_id_tolerates_whitespace():
    assert normalize_message_id("  <abc@x.pt>  ") == "<abc@x.pt>"


def test_normalize_message_id_rejects_empty():
    for vazio in (None, "", "   ", "<>", "< >"):
        assert normalize_message_id(vazio) is None, vazio


# ====================================================================
# parse_references
# ====================================================================

def test_parse_references_splits_header_string():
    assert parse_references("<a@x.pt> <b@x.pt>") == ["<a@x.pt>", "<b@x.pt>"]


def test_parse_references_accepts_list():
    assert parse_references(["a@x.pt", "<b@x.pt>"]) == ["<a@x.pt>", "<b@x.pt>"]


def test_parse_references_preserves_order_and_dedupes():
    # A ordem descreve a cadeia (raiz → folha); duplicar partiria a contagem.
    assert parse_references("<a@x.pt> <b@x.pt> <a@x.pt>") == ["<a@x.pt>", "<b@x.pt>"]


def test_parse_references_empty():
    assert parse_references(None) == []
    assert parse_references("") == []
    assert parse_references(123) == []


# ====================================================================
# build_reference_chain
# ====================================================================

def test_build_reference_chain_appends_parent():
    chain = build_reference_chain("<pai@x.pt>", "<avo@x.pt>")
    assert chain == ["<avo@x.pt>", "<pai@x.pt>"]


def test_build_reference_chain_without_parent_references():
    assert build_reference_chain("<pai@x.pt>", None) == ["<pai@x.pt>"]


def test_build_reference_chain_does_not_duplicate_parent():
    chain = build_reference_chain("<pai@x.pt>", "<avo@x.pt> <pai@x.pt>")
    assert chain == ["<avo@x.pt>", "<pai@x.pt>"]


def test_build_reference_chain_truncates_keeping_root():
    """Uma conversa longa não pode inchar o cabeçalho sem limite."""
    longa = [f"<m{i}@x.pt>" for i in range(50)]
    chain = build_reference_chain("<pai@x.pt>", longa)

    assert len(chain) == MAX_REFERENCES
    assert chain[0] == "<m0@x.pt>", "a raiz da conversa nunca se perde"
    assert chain[-1] == "<pai@x.pt>", "o pai imediato é o último"


def test_build_reference_chain_empty_when_nothing_to_thread():
    assert build_reference_chain(None, None) == []


# ====================================================================
# Message-ID de saída
# ====================================================================

def test_generate_message_id_is_unique_and_well_formed():
    a, b = generate_message_id("empresa.pt"), generate_message_id("empresa.pt")
    assert a != b
    assert a.startswith("<") and a.endswith(">")
    assert a.endswith("@empresa.pt>")


def test_generate_message_id_without_domain():
    msg_id = generate_message_id(None)
    assert msg_id.startswith("<") and msg_id.endswith(">")


def test_domain_from_email():
    assert domain_from_email("geral@empresa.pt") == "empresa.pt"
    assert domain_from_email("sem-arroba") is None
    assert domain_from_email(None) is None


# ====================================================================
# normalize_subject
# ====================================================================

def test_normalize_subject_strips_reply_prefixes():
    assert normalize_subject("Re: Crédito Habitação") == "Crédito Habitação"
    assert normalize_subject("RE: RE: Crédito") == "Crédito"


def test_normalize_subject_strips_mixed_and_localized_prefixes():
    # Um cliente a responder do Outlook PT/ES não pode partir a conversa.
    assert normalize_subject("Fwd: Re: Enc: Proposta") == "Proposta"
    assert normalize_subject("RES: Proposta") == "Proposta"
    assert normalize_subject("Re[2]: Proposta") == "Proposta"


def test_normalize_subject_collapses_whitespace():
    assert normalize_subject("  Crédito    Habitação  ") == "Crédito Habitação"


def test_normalize_subject_empty():
    assert normalize_subject(None) == ""
    assert normalize_subject("Re:") == ""


# ====================================================================
# thread_key — a regra de agrupamento
# ====================================================================

def test_thread_key_prefers_references_root():
    """A raiz identifica a conversa mesmo se alguém mudar o assunto."""
    key = thread_key({
        "references": "<raiz@x.pt> <meio@x.pt>",
        "in_reply_to": "<meio@x.pt>",
        "message_id": "<folha@x.pt>",
        "subject": "Assunto mudado a meio",
    })
    assert key == "<raiz@x.pt>"


def test_thread_key_falls_back_to_in_reply_to():
    key = thread_key({"in_reply_to": "<pai@x.pt>", "message_id": "<eu@x.pt>"})
    assert key == "<pai@x.pt>"


def test_thread_key_uses_own_id_when_root_of_new_thread():
    assert thread_key({"message_id": "<eu@x.pt>", "subject": "Novo"}) == "<eu@x.pt>"


def test_thread_key_falls_back_to_subject_without_headers():
    """Alguns IMAP antigos não devolvem estes cabeçalhos."""
    key = thread_key({"subject": "Re: Crédito Habitação"})
    assert key == "subject:crédito habitação"


def test_thread_key_groups_reply_with_original_by_subject():
    original = thread_key({"subject": "Crédito Habitação"})
    resposta = thread_key({"subject": "RE: Crédito Habitação"})
    assert original == resposta != ""


def test_thread_key_empty_for_unusable_input():
    assert thread_key({}) == ""
    assert thread_key({"subject": ""}) == ""
    assert thread_key(None) == ""
