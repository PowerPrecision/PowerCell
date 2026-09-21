"""Guardar e enviar têm de usar a MESMA sub-configuração de email.

Incidente de 2026-09-21 (produção): o botão "Testar" dava verde e o envio
falhava com `535 Incorrect authentication data`, com a mesma conta.

Causa: o `email_config` de um utilizador pode ser ANINHADO por papel. O
envio (`_extract_role_email_config`) lê primeiro `config[<papel>]` e só
depois `config["default"]`; o guardar escrevia em `"default"` sempre que o
cabeçalho `X-Active-Role` coincidia com o papel base — o caso comum. Uma
sub-config antiga em `config["consultor"]` sombreava a password acabada de
guardar, e voltar a gravar não resolvia nada.

Estes testes fixam o invariante: a chave onde se escreve é a chave de onde
se lê.
"""
from services.email_config_resolver import _extract_role_email_config


PASSWORD_NOVA = "ENC:nova"
PASSWORD_VELHA = "ENC:velha"


def _config_aninhada():
    """`email_config` com uma sub-config por papel e uma `default`."""
    return {
        "default": {
            "email_address": "fernando@empresa.pt",
            "encrypted_password": PASSWORD_NOVA,
            "is_configured": True,
        },
        "consultor": {
            "email_address": "fernando@empresa.pt",
            "encrypted_password": PASSWORD_VELHA,
            "is_configured": True,
        },
    }


def test_leitura_prefere_o_papel_sobre_default():
    """É esta precedência que torna a escrita em 'default' invisível."""
    lido = _extract_role_email_config(_config_aninhada(), "consultor")
    assert lido["encrypted_password"] == PASSWORD_VELHA


def test_sem_papel_a_leitura_cai_em_default():
    lido = _extract_role_email_config(_config_aninhada(), None)
    assert lido["encrypted_password"] == PASSWORD_NOVA


def test_o_desencontro_das_chaves_e_o_bug():
    """Escrever em 'default' e ler por papel devolve credenciais DIFERENTES.

    É exactamente esta divergência que produzia verde no teste e 535 no
    envio. Se um dia as duas chaves coincidirem, este teste falha e obriga
    a rever a premissa — que é o que se quer.
    """
    config = _config_aninhada()
    escrito_pelo_guardar = _extract_role_email_config(config, None)
    lido_pelo_envio = _extract_role_email_config(config, "consultor")

    assert escrito_pelo_guardar["encrypted_password"] != lido_pelo_envio["encrypted_password"], (
        "se estes passarem a coincidir, o bug do sombreamento deixou de ser possível"
    )


def test_escrever_no_papel_do_envio_fica_visivel():
    """Com a correcção, o guardar escreve na chave que o envio lê."""
    config = _config_aninhada()
    papel_do_envio = "consultor"  # o que `resolve_active_ucr_role` devolveria

    # O guardar corrigido escreve nesta chave:
    config[papel_do_envio]["encrypted_password"] = PASSWORD_NOVA

    lido = _extract_role_email_config(config, papel_do_envio)
    assert lido["encrypted_password"] == PASSWORD_NOVA, (
        "voltar a gravar a password tem de passar a resolver o envio"
    )


def test_config_flat_legada_nao_e_afectada():
    """Quem tem config antiga (não aninhada) continua a ler o mesmo."""
    flat = {
        "email_address": "antigo@empresa.pt",
        "encrypted_password": PASSWORD_NOVA,
        "is_configured": True,
    }
    assert _extract_role_email_config(flat, "consultor") == flat
    assert _extract_role_email_config(flat, None) == flat


def test_papel_inexistente_cai_em_default():
    """Um papel sem sub-config própria não pode ficar sem credenciais."""
    lido = _extract_role_email_config(_config_aninhada(), "diretor")
    assert lido["encrypted_password"] == PASSWORD_NOVA


def test_handlers_resolvem_o_papel_pela_mesma_funcao():
    """Testar, Guardar e Enviar têm de usar `resolve_active_ucr_role`.

    Sem isto, cada um escolhe uma sub-config diferente e o teste volta a
    mentir sobre o envio.
    """
    from pathlib import Path

    origem = Path(__file__).resolve().parents[1]
    config_api = (origem.parent / "services" / "users_api_email_config.py").read_text()
    documentacao = (origem.parent / "services" / "email_documentation.py").read_text()

    # Contar ocorrências não chega: o import sozinho já as produzia e a
    # asserção passava com o guardar a escrever em "default" na mesma.
    # Afirma-se a ATRIBUIÇÃO concreta de cada um.
    assert "storage_role = await resolve_active_ucr_role(" in config_api, (
        "o guardar tem de escolher a chave com a resolução do envio, "
        "não com uma comparação de cabeçalhos"
    )
    assert "active_role = await resolve_active_ucr_role(" in config_api, (
        "o testar tem de resolver o papel como o envio, senão volta a "
        "testar uma config diferente da que envia"
    )
    assert 'storage_role = "default"' not in config_api, (
        "escrever sempre em 'default' é o bug: o envio lê primeiro pelo papel"
    )
    assert "resolve_active_ucr_role" in documentacao, (
        "o envio é a referência — se mudar de função, os outros têm de a seguir"
    )
