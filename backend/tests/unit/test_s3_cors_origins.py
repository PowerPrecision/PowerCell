"""Origens CORS do bucket S3 — devem vir do ambiente, não de uma lista fixa.

CONTEXTO (Set 2026): `_ensure_cors_configured` importava `backend.config`, um
pacote que NÃO existe em runtime (a app corre com `backend/` na raiz do
sys.path). O import falhava sempre em silêncio e o bucket — incluindo o de
DEV — era configurado com a lista hardcoded de produção, ignorando por
completo a variável `CORS_ORIGINS`. Estes testes fecham a porta a essa
regressão.
"""

import ast
import pathlib
from unittest.mock import MagicMock

import pytest

from services.s3_storage import S3Service

RAIZ_BACKEND = pathlib.Path(__file__).resolve().parents[2]
FICHEIRO_S3 = RAIZ_BACKEND / "services" / "s3_storage.py"


@pytest.fixture
def servico_s3():
    """S3Service com cliente falso, sem tocar em boto3 nem na rede."""
    servico = S3Service.__new__(S3Service)
    servico.s3_client = MagicMock()
    servico.bucket_name = "bucket-de-dev"
    return servico


def _origens_aplicadas(servico) -> list:
    """Extrai as origens explícitas (Regra 1) do put_bucket_cors."""
    chamada = servico.s3_client.put_bucket_cors.call_args
    assert chamada is not None, "put_bucket_cors não foi chamado"
    regras = chamada.kwargs["CORSConfiguration"]["CORSRules"]
    return regras[0]["AllowedOrigins"]


def test_origens_vem_do_config_do_ambiente(servico_s3, monkeypatch):
    """As origens aplicadas ao bucket são as de CORS_ORIGINS, não as fixas."""
    import config

    monkeypatch.setattr(
        config, "CORS_ORIGINS", ["https://dev.exemplo.pt", "http://localhost:3000"], raising=False
    )

    servico_s3._ensure_cors_configured()

    origens = _origens_aplicadas(servico_s3)
    assert origens == ["https://dev.exemplo.pt", "http://localhost:3000"]
    assert "https://powercell.pt" not in origens, "caiu no fallback de produção"


def test_curinga_continua_na_segunda_regra(servico_s3):
    """A Regra 2 (curinga para previews) mantém-se — bucket privado + URLs pre-assinadas."""
    servico_s3._ensure_cors_configured()

    regras = servico_s3.s3_client.put_bucket_cors.call_args.kwargs["CORSConfiguration"]["CORSRules"]
    assert len(regras) == 2
    assert regras[1]["AllowedOrigins"] == ["*"]


def test_sem_cliente_ou_bucket_nao_chama_o_s3():
    """Graceful degradation: sem cliente configurado, não há chamada nem excepção."""
    servico = S3Service.__new__(S3Service)
    servico.s3_client = None
    servico.bucket_name = None

    servico._ensure_cors_configured()  # não levanta


def test_erro_do_s3_nao_propaga(servico_s3):
    """Um ClientError do put_bucket_cors é registado, não rebenta o arranque."""
    from botocore.exceptions import ClientError

    servico_s3.s3_client.put_bucket_cors.side_effect = ClientError(
        {"Error": {"Code": "AccessDenied", "Message": "sem permissão"}}, "PutBucketCors"
    )

    servico_s3._ensure_cors_configured()  # não levanta


def test_o_import_partido_nao_volta():
    """Guarda sobre o código-fonte: `backend.config` não existe em runtime.

    Sem esta guarda, um `from backend.config import ...` reintroduzido voltaria
    a falhar em silêncio — o pior modo de falha, porque o fallback mascara-o.
    """
    fonte = FICHEIRO_S3.read_text(encoding="utf-8")
    arvore = ast.parse(fonte)

    # Só imports reais — um comentário que mencione o erro antigo é legítimo.
    imports_do_pacote_backend = [
        no for no in ast.walk(arvore)
        if isinstance(no, ast.ImportFrom) and (no.module or "").split(".")[0] == "backend"
    ] + [
        no for no in ast.walk(arvore)
        if isinstance(no, ast.Import)
        and any(alias.name.split(".")[0] == "backend" for alias in no.names)
    ]
    assert not imports_do_pacote_backend, (
        "o pacote `backend` não existe em runtime — o import falharia em silêncio"
    )

    importa_config = any(
        isinstance(no, ast.ImportFrom) and no.module == "config" and
        any(alias.name == "CORS_ORIGINS" for alias in no.names)
        for no in ast.walk(arvore)
    )
    assert importa_config, "_ensure_cors_configured deixou de ler CORS_ORIGINS do config"
