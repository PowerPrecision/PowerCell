"""Eliminar um cliente deixa rasto no trilho de auditoria (D-16, Lote 5).

O QUE FALTAVA
A eliminação gravava `deleted_at`/`deleted_by` nos documentos afectados —
e isso é o que o RESTAURO lê, não um trilho consultável. Para responder a
"quem apagou este cliente?" era preciso ir ao documento eliminado; para
"o que foi apagado esta semana?" não havia resposta. O
`run_delete_client_registration` do painel de admin, que faz muito menos,
já escrevia.

PORQUE É QUE O TESTE COBRE OS DOIS CAMINHOS
`run_delete_client` tem DOIS pontos de saída — o cliente pode estar em
`db.processes` (modelo unificado) ou em `db.clients` (legado) — cada um
com o seu `return`. Um registo escrito só num deles é exactamente a forma
de defeito que este código produz há seis lotes: metade a funcionar
esconde a outra metade. Daí haver um teste por ramo e um a afirmar que
são DOIS.

NOTA SOBRE O `db`: o `audit_trail_service` faz `from database import db`
ao nível do módulo, logo tem a SUA referência ao proxy. Patchar só o
`client_delete` deixava a escrita a ir ao Mongo real — é a regra do
AGENTS.md sobre a ordem de importação.
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from tests.unit.helpers_fonte import codigo_sem_comentarios  # noqa: E402

SERVICO = BACKEND / "services" / "client_delete.py"

DIRETOR = {"id": "u-dir", "name": "Dina Direção", "email": "dina@exemplo.pt", "role": "diretor"}


class PedidoFalso:
    """O mínimo que o `log_audit_event` lê para extrair o IP."""

    def __init__(self, ip="203.0.113.7"):
        self.headers = {"X-Forwarded-For": ip}
        self.client = type("C", (), {"host": ip})()


async def _eliminar(fake_async_db, *, papel_efectivo="diretor", request=None):
    from services import audit_trail_service, client_delete

    with patch.object(client_delete, "db", fake_async_db), \
         patch.object(audit_trail_service, "db", fake_async_db):
        return await client_delete.run_delete_client(
            "c-1", DIRETOR, papel_efectivo=papel_efectivo, request=request,
        )


async def _registos(fake_async_db):
    return await fake_async_db.audit_trail.find({}).to_list(None)


class TestOCaminhoDoProcesso:
    """Cliente que vive em `db.processes` (modelo unificado)."""

    @pytest.fixture(autouse=True)
    def _semear(self, fake_async_db):
        fake_async_db.processes.docs.append({
            "id": "c-1",
            "client_name": "Ana Martins",
            "status": "pre_registo",
        })

    @pytest.mark.asyncio
    async def test_escreve_um_registo_de_auditoria(self, fake_async_db):
        await _eliminar(fake_async_db)
        registos = await _registos(fake_async_db)
        assert len(registos) == 1, registos

    @pytest.mark.asyncio
    async def test_o_registo_diz_QUEM_e_O_QUE(self, fake_async_db):
        await _eliminar(fake_async_db)
        (registo,) = await _registos(fake_async_db)
        # "Registo de Cliente X eliminado por Utilizador Y"
        assert "Ana Martins" in registo["action"]
        assert registo["user_id"] == "u-dir"
        assert registo["user_name"] == "Dina Direção"
        assert registo["field"] == "client_delete"
        assert registo["old_value"] == "Ana Martins"

    @pytest.mark.asyncio
    async def test_guarda_o_PAPEL_EFECTIVO_e_nao_so_o_do_JWT(self, fake_async_db):
        """Quem autorizou a operação foi o perfil ACTIVO. O
        `log_audit_event` grava `user["role"]` (o do JWT) no campo
        partilhado; o efectivo vai em `metadata` para não mudar a
        semântica desse campo para os outros chamadores."""
        utilizador_com_dois_papeis = {**DIRETOR, "role": "consultor"}
        from services import audit_trail_service, client_delete

        with patch.object(client_delete, "db", fake_async_db), \
             patch.object(audit_trail_service, "db", fake_async_db):
            await client_delete.run_delete_client(
                "c-1", utilizador_com_dois_papeis, papel_efectivo="diretor",
            )

        (registo,) = await _registos(fake_async_db)
        assert registo["user_role"] == "consultor"          # o do JWT
        assert registo["metadata"]["papel_efectivo"] == "diretor"

    @pytest.mark.asyncio
    async def test_guarda_o_IP_quando_ha_pedido(self, fake_async_db):
        await _eliminar(fake_async_db, request=PedidoFalso())
        (registo,) = await _registos(fake_async_db)
        assert registo["ip_address"] == "203.0.113.7"

    @pytest.mark.asyncio
    async def test_sem_pedido_nao_rebenta(self, fake_async_db):
        """A rota passa o `request`, mas um chamador interno pode não ter."""
        await _eliminar(fake_async_db, request=None)
        (registo,) = await _registos(fake_async_db)
        assert registo["ip_address"] is None

    @pytest.mark.asyncio
    async def test_diz_de_QUE_colecao_veio(self, fake_async_db):
        await _eliminar(fake_async_db)
        (registo,) = await _registos(fake_async_db)
        assert registo["metadata"]["origem"] == "processes"


class TestOCaminhoDoClienteLegado:
    """Cliente que vive em `db.clients` — o OUTRO `return`."""

    @pytest.fixture(autouse=True)
    def _semear(self, fake_async_db):
        fake_async_db.clients.docs.append({
            "id": "c-1",
            "nome": "Bruno Costa",
            "process_ids": [],
        })

    @pytest.mark.asyncio
    async def test_tambem_escreve_o_registo(self, fake_async_db):
        """Era aqui que um registo escrito num ramo só deixaria de haver
        rasto — e é o ramo da POOL, onde o botão novo vive."""
        await _eliminar(fake_async_db)
        registos = await _registos(fake_async_db)
        assert len(registos) == 1, registos
        assert "Bruno Costa" in registos[0]["action"]
        assert registos[0]["metadata"]["origem"] == "clients"


class TestAAuditoriaNUNCAFalhaAEliminacao:
    @pytest.mark.asyncio
    async def test_um_erro_a_escrever_nao_propaga(self, fake_async_db):
        """O registo é escrito DEPOIS de a eliminação estar feita:
        propagar aqui deixava o cliente eliminado e a resposta em erro —
        o pior dos dois mundos."""
        fake_async_db.clients.docs.append({"id": "c-1", "nome": "Carla", "process_ids": []})

        from services import audit_trail_service, client_delete

        async def explode(*a, **kw):
            raise RuntimeError("audit em baixo")

        with patch.object(client_delete, "db", fake_async_db), \
             patch.object(audit_trail_service, "db", fake_async_db), \
             patch.object(audit_trail_service, "log_audit_event", explode):
            resultado = await client_delete.run_delete_client(
                "c-1", DIRETOR, papel_efectivo="diretor",
            )

        assert resultado["success"] is True
        # E o cliente FICOU eliminado.
        doc = await fake_async_db.clients.find_one({"id": "c-1"})
        assert doc["is_deleted"] is True

    @pytest.mark.asyncio
    async def test_um_cliente_inexistente_nao_deixa_registo(self, fake_async_db):
        """404 antes de qualquer escrita: um trilho com eliminações que
        não aconteceram é pior do que um trilho vazio."""
        from fastapi import HTTPException

        with pytest.raises(HTTPException):
            await _eliminar(fake_async_db)
        assert await _registos(fake_async_db) == []


class TestOsDoisRamosEstaoLigados:
    def test_ha_DOIS_registos_de_auditoria_no_servico(self):
        """Inventário: o serviço tem dois pontos de saída e os dois têm de
        escrever. Se aparecer um terceiro `return` de sucesso, este número
        falha e obriga a decidir."""
        # `codigo_sem_comentarios` passa pelo `ast.unparse`, que NORMALIZA
        # as aspas: `"success"` chega aqui como `'success'`. É a regra do
        # AGENTS.md sobre guardas de fonte, e falhei-a ao escrever este
        # teste — comparar sem aspas.
        fonte = codigo_sem_comentarios(SERVICO.read_text(encoding="utf-8")).replace("'", '"')
        assert fonte.count("await _registar_eliminacao_na_auditoria(") == 2
        assert fonte.count('"success": True') == 2

    def test_CONTRAPROVA_o_helper_chama_mesmo_o_trilho(self):
        """Sem isto, um helper vazio satisfazia o teste acima."""
        fonte = codigo_sem_comentarios(SERVICO.read_text(encoding="utf-8")).replace("'", '"')
        assert "from services.audit_trail_service import log_audit_event" in fonte
        assert "await log_audit_event(" in fonte
