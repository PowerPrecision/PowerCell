"""Guarda de ambiente para os scripts de dados simulados.

PORQUÊ
------
Os scripts de seed (`seed_massive_dev_data.py`, `seed_qa_ultimate.py`, …)
inserem centenas de clientes e processos FICTÍCIOS. Apontam para a base de
dados que estiver em `MONGO_URL`/`DB_NAME` — e nada, até aqui, os impedia de
correr contra PRODUÇÃO. Um `.env` errado no terminal bastava para poluir a
base de dados real com clientes falsos, sem confirmação e sem forma simples
de distinguir o que era dado real.

A infraestrutura do PowerCell é isolada por ambiente (serviço Render e bucket
S3 dedicados a dev, outros distintos para prod). Este guarda leva essa
separação até ao código que escreve na base de dados.

REGRA
-----
Abortar quando o ambiente parece produção, a não ser que o operador o declare
explicitamente com `ALLOW_SEED_IN_PRODUCTION=true`:

1. `ENVIRONMENT` ou `APP_ENV` em {production, prod} → produção;
2. `DB_NAME` a conter "prod" (e não "dev"/"test"/"staging") → produção.

Falha fechada: na dúvida, não escreve.
"""

import os
import sys

MARCADORES_DE_PRODUCAO = {"production", "prod", "live"}
MARCADORES_SEGUROS = ("dev", "test", "qa", "staging", "local", "sandbox")
VARIAVEL_DE_ESCAPE = "ALLOW_SEED_IN_PRODUCTION"


def _normalizar(valor) -> str:
    return str(valor or "").strip().lower()


def escape_autorizado(ambiente=None) -> bool:
    """True se o operador autorizou explicitamente a escrita em produção."""
    env = ambiente if ambiente is not None else os.environ
    return _normalizar(env.get(VARIAVEL_DE_ESCAPE)) in {"true", "1", "yes", "sim"}


def db_name_parece_producao(db_name) -> bool:
    """Heurística sobre o nome da base de dados.

    "powercell_prod" → True; "powercell_dev", "prod_test_db" → False (um
    marcador seguro explícito ganha, para não bloquear bases de teste que por
    acaso contenham a palavra).
    """
    nome = _normalizar(db_name)
    if not nome:
        return False
    if any(marcador in nome for marcador in MARCADORES_SEGUROS):
        return False
    return "prod" in nome


def detectar_producao(ambiente=None) -> tuple:
    """Diz se o ambiente actual parece produção.

    Returns:
        tuple[bool, str]: (é_produção, motivo legível). Motivo vazio se não for.
    """
    env = ambiente if ambiente is not None else os.environ

    for chave in ("ENVIRONMENT", "APP_ENV"):
        if _normalizar(env.get(chave)) in MARCADORES_DE_PRODUCAO:
            return True, f"{chave}={env.get(chave)}"

    db_name = env.get("DB_NAME")
    if db_name_parece_producao(db_name):
        return True, f"DB_NAME={db_name}"

    return False, ""


def require_non_production_db(nome_do_script: str, ambiente=None, saida=None) -> None:
    """Aborta o script se o ambiente parecer produção.

    Args:
        nome_do_script: nome mostrado na mensagem (ex.: "seed_qa_ultimate").
        ambiente: mapa de variáveis (injectável nos testes; default `os.environ`).
        saida: stream de erro (injectável nos testes; default `sys.stderr`).

    Raises:
        SystemExit: código 2 quando o ambiente é produção sem autorização.
    """
    env = ambiente if ambiente is not None else os.environ
    stream = saida if saida is not None else sys.stderr

    e_producao, motivo = detectar_producao(env)
    if not e_producao:
        return

    if escape_autorizado(env):
        print(
            f"⚠️  {nome_do_script}: ambiente de PRODUÇÃO detectado ({motivo}), "
            f"mas {VARIAVEL_DE_ESCAPE} está activo. A prosseguir por ordem explícita.",
            file=stream,
        )
        return

    print(
        f"\n❌ {nome_do_script} ABORTADO: ambiente de PRODUÇÃO detectado ({motivo}).\n"
        "   Este script insere dados SIMULADOS e nunca deve correr contra a base de dados real.\n"
        f"   Se souber mesmo o que está a fazer: {VARIAVEL_DE_ESCAPE}=true python -m scripts.{nome_do_script}\n",
        file=stream,
    )
    raise SystemExit(2)
