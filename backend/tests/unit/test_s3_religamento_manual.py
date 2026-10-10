"""Religamento manual de pastas S3 — a válvula humana (Lote 6, ponto 2).

PORQUE É QUE ISTO TEM DE EXISTIR
================================
A identidade da pasta passou a derivar do ID, e o automatismo deixou de
adivinhar: quando não sabe, **recusa**. Isso está certo e deixa casos em
aberto que só uma pessoa resolve:

  * o mapeamento ficou a apontar para uma pasta legada errada (a colisão que
    deu origem a tudo isto);
  * duas fichas partilham a mesma pasta e é preciso separar uma (D-19);
  * um `rename` antigo deixou a ligação partida (205 medidas no Épico 10);
  * uma pasta nova aparece como uuid e o administrador quer consolidá-la numa
    pasta existente com histórico.

A ferramenta anterior só sabia religar **processos**. Um cliente da Pool que
nunca chegou a ter processo não tinha como ser religado — e é precisamente ele
que vive sozinho na raiz documental.

REGRAS QUE OS TESTES FIXAM
==========================
1. só ADMIN (não CEO, não Direcção): é uma escrita sobre a fronteira de posse
   de documentos, e `assert_s3_file_belongs_to_process` passa a autorizar tudo
   o que estiver na pasta escolhida;
2. a pasta tem de estar DENTRO da raiz documental — um `backups/` aqui
   transformava a guarda de posse num passe para o bucket inteiro;
3. a raiz NUA é recusada (autorizaria a árvore toda);
4. apontar para uma pasta que já tem dono é PERMITIDO (é como se consolida) mas
   vem com AVISO — quem decide tem de saber que vai partilhar;
5. deixa rasto no trilho de auditoria, com o papel EFECTIVO;
6. remover o mapeamento é uma operação legítima e explícita.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services.s3_document_root import pasta_do_cliente

pytestmark = pytest.mark.asyncio

CID = "11111111-1111-4111-8111-111111111111"
PID = "22222222-2222-4222-8222-222222222222"
LEGADA = "Documentação Clientes/Carolina_Silva"
ADMIN = {"id": "u-admin", "role": "admin", "name": "Admin"}


async def _semear(fake_async_db):
    await fake_async_db.processes.insert_one({
        "id": PID, "client_id": CID, "client_name": "Carolina Agostinho da Silva",
        "s3_folder": pasta_do_cliente(CID) + "/processos/" + PID,
    })
    await fake_async_db.clients.insert_one({
        "id": CID, "nome": "Carolina Agostinho da Silva",
        "s3_folder": pasta_do_cliente(CID),
    })


def _patch(mod, fake_async_db):
    return patch.object(mod, "db", fake_async_db)


class TestOReligamento:
    async def test_religa_um_PROCESSO_a_uma_pasta_legada(self, fake_async_db):
        from services import s3_relink as mod

        await _semear(fake_async_db)
        with _patch(mod, fake_async_db), patch.object(
            mod, "_registar_na_auditoria", AsyncMock()
        ):
            r = await mod.run_set_s3_mapping(
                tipo="processo", entity_id=PID, s3_folder=LEGADA, user=ADMIN,
            )

        assert r["success"] is True
        doc = await fake_async_db.processes.find_one({"id": PID})
        assert doc["s3_folder"] == LEGADA

    async def test_religa_um_CLIENTE_da_Pool(self, fake_async_db):
        """O caso que a ferramenta antiga não cobria: a rota de "cliente" era
        um alias que recebia `process_id`."""
        from services import s3_relink as mod

        await _semear(fake_async_db)
        with _patch(mod, fake_async_db), patch.object(
            mod, "_registar_na_auditoria", AsyncMock()
        ):
            r = await mod.run_set_s3_mapping(
                tipo="cliente", entity_id=CID, s3_folder=LEGADA, user=ADMIN,
            )

        assert r["success"] is True
        doc = await fake_async_db.clients.find_one({"id": CID})
        assert doc["s3_folder"] == LEGADA

    async def test_remover_o_mapeamento_e_explicito(self, fake_async_db):
        from services import s3_relink as mod

        await _semear(fake_async_db)
        with _patch(mod, fake_async_db), patch.object(
            mod, "_registar_na_auditoria", AsyncMock()
        ):
            r = await mod.run_set_s3_mapping(
                tipo="cliente", entity_id=CID, s3_folder=None, user=ADMIN,
            )

        assert r["success"] is True
        doc = await fake_async_db.clients.find_one({"id": CID})
        assert doc["s3_folder"] is None

    async def test_entidade_inexistente_da_404(self, fake_async_db):
        from services import s3_relink as mod

        with _patch(mod, fake_async_db):
            with pytest.raises(HTTPException) as e:
                await mod.run_set_s3_mapping(
                    tipo="processo", entity_id="nao-existe",
                    s3_folder=LEGADA, user=ADMIN,
                )
        assert e.value.status_code == 404

    async def test_tipo_desconhecido_da_400(self, fake_async_db):
        from services import s3_relink as mod

        with _patch(mod, fake_async_db):
            with pytest.raises(HTTPException) as e:
                await mod.run_set_s3_mapping(
                    tipo="utilizador", entity_id=CID,
                    s3_folder=LEGADA, user=ADMIN,
                )
        assert e.value.status_code == 400


class TestAPastaQueSeRecusa:
    @pytest.mark.parametrize(
        "mau",
        [
            "backups/dump-2026-09-01.zip",
            "backups/",
            "companies/logo.png",
            "Documentação Clientes",      # a raiz NUA
            "Documentação Clientes/",
            "../backups",
            "/",
        ],
    )
    async def test_fora_da_raiz_documental_ou_a_raiz_nua(self, fake_async_db, mau):
        from services import s3_relink as mod

        await _semear(fake_async_db)
        with _patch(mod, fake_async_db):
            with pytest.raises(HTTPException) as e:
                await mod.run_set_s3_mapping(
                    tipo="cliente", entity_id=CID, s3_folder=mau, user=ADMIN,
                )
        assert e.value.status_code == 400

        # E nada foi gravado.
        doc = await fake_async_db.clients.find_one({"id": CID})
        assert doc["s3_folder"] == pasta_do_cliente(CID)

    async def test_a_barra_final_e_normalizada_e_nao_recusada(self, fake_async_db):
        from services import s3_relink as mod

        await _semear(fake_async_db)
        with _patch(mod, fake_async_db), patch.object(
            mod, "_registar_na_auditoria", AsyncMock()
        ):
            await mod.run_set_s3_mapping(
                tipo="cliente", entity_id=CID, s3_folder=LEGADA + "/", user=ADMIN,
            )
        doc = await fake_async_db.clients.find_one({"id": CID})
        assert doc["s3_folder"] == LEGADA


class TestOAvisoDaPartilha:
    async def test_apontar_para_uma_pasta_COM_DONO_avisa_mas_permite(
        self, fake_async_db
    ):
        from services import s3_relink as mod

        await _semear(fake_async_db)
        await fake_async_db.processes.insert_one({
            "id": "outro", "client_name": "Outro Cliente", "s3_folder": LEGADA,
        })

        with _patch(mod, fake_async_db), patch.object(
            mod, "_registar_na_auditoria", AsyncMock()
        ):
            r = await mod.run_set_s3_mapping(
                tipo="cliente", entity_id=CID, s3_folder=LEGADA, user=ADMIN,
            )

        assert r["success"] is True
        assert r["aviso"]
        assert "Outro Cliente" in r["aviso"]

    async def test_pasta_livre_nao_inventa_aviso(self, fake_async_db):
        from services import s3_relink as mod

        await _semear(fake_async_db)
        with _patch(mod, fake_async_db), patch.object(
            mod, "_registar_na_auditoria", AsyncMock()
        ):
            r = await mod.run_set_s3_mapping(
                tipo="cliente", entity_id=CID, s3_folder=LEGADA, user=ADMIN,
            )
        assert not r["aviso"]


class TestORasto:
    async def test_grava_no_trilho_de_auditoria(self, fake_async_db):
        from services import s3_relink as mod

        await _semear(fake_async_db)
        espia = AsyncMock()
        with _patch(mod, fake_async_db), patch.object(
            mod, "_registar_na_auditoria", espia
        ):
            await mod.run_set_s3_mapping(
                tipo="cliente", entity_id=CID, s3_folder=LEGADA, user=ADMIN,
            )
        espia.assert_awaited_once()

    async def test_a_auditoria_a_falhar_NAO_desfaz_o_religamento(
        self, fake_async_db
    ):
        """A operação já aconteceu quando se escreve o registo. Levantar aqui
        mostraria um erro sobre algo bem sucedido — a lei do
        `document_portal_revoke` e do rasto da eliminação."""
        from services import s3_relink as mod

        await _semear(fake_async_db)
        with _patch(mod, fake_async_db), patch.object(
            mod, "log_audit_event", AsyncMock(side_effect=RuntimeError("trilho em baixo"))
        ):
            r = await mod.run_set_s3_mapping(
                tipo="cliente", entity_id=CID, s3_folder=LEGADA, user=ADMIN,
            )
        assert r["success"] is True
        doc = await fake_async_db.clients.find_one({"id": CID})
        assert doc["s3_folder"] == LEGADA


class TestAListagem:
    async def test_traz_processos_E_clientes(self, fake_async_db):
        from services import s3_relink as mod

        await _semear(fake_async_db)
        with _patch(mod, fake_async_db), patch(
            "services.s3_storage.s3_service"
        ) as s3:
            s3.is_configured.return_value = False
            r = await mod.run_get_s3_relink(
                search=None, tipo=None, apenas_por_resolver=False,
                page=1, limit=50, user=ADMIN,
            )

        tipos = {e["tipo"] for e in r["entidades"]}
        assert tipos == {"processo", "cliente"}

    async def test_marca_quem_aponta_para_uma_pasta_por_ID(self, fake_async_db):
        from services import s3_relink as mod

        await _semear(fake_async_db)
        with _patch(mod, fake_async_db), patch(
            "services.s3_storage.s3_service"
        ) as s3:
            s3.is_configured.return_value = False
            r = await mod.run_get_s3_relink(
                search=None, tipo="cliente", apenas_por_resolver=False,
                page=1, limit=50, user=ADMIN,
            )

        cliente = next(e for e in r["entidades"] if e["id"] == CID)
        assert cliente["pasta_por_id"] is True
        assert cliente["nome"] == "Carolina Agostinho da Silva"

    async def test_apenas_por_resolver_filtra_quem_ja_esta_bem(
        self, fake_async_db
    ):
        from services import s3_relink as mod

        await _semear(fake_async_db)
        await fake_async_db.clients.insert_one({
            "id": "sem-pasta", "nome": "Sem Pasta Nenhuma",
        })

        with _patch(mod, fake_async_db), patch(
            "services.s3_storage.s3_service"
        ) as s3:
            s3.is_configured.return_value = False
            r = await mod.run_get_s3_relink(
                search=None, tipo="cliente", apenas_por_resolver=True,
                page=1, limit=50, user=ADMIN,
            )

        ids = {e["id"] for e in r["entidades"]}
        assert "sem-pasta" in ids
        assert CID not in ids

    async def test_a_pesquisa_e_por_NOME(self, fake_async_db):
        from services import s3_relink as mod

        await _semear(fake_async_db)
        await fake_async_db.clients.insert_one({"id": "c2", "nome": "Rui Pereira"})

        with _patch(mod, fake_async_db), patch(
            "services.s3_storage.s3_service"
        ) as s3:
            s3.is_configured.return_value = False
            r = await mod.run_get_s3_relink(
                search="Rui", tipo="cliente", apenas_por_resolver=False,
                page=1, limit=50, user=ADMIN,
            )

        assert {e["id"] for e in r["entidades"]} == {"c2"}


# ════════════════════════════════════════════════════════════════════
# AS ROTAS — a porta, e a ligação ao serviço
# ════════════════════════════════════════════════════════════════════

class TestAsRotasDeAdministracao:
    """Exclusivo da Administração, afirmado sobre a FONTE da rota.

    Montar a app inteira para provar um `Depends` é caro e frágil; o que
    importa é que o decorador declara exactamente este perfil — e que não
    declara os outros. A contraprova está ao lado: sem ela, apagar o
    `require_roles` satisfazia o guarda.
    """

    @staticmethod
    def _rotas():
        import ast
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[2] / "routes" / "admin_storage.py"
        ).read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        por_nome = {}
        for no in ast.walk(arvore):
            if isinstance(no, (ast.AsyncFunctionDef, ast.FunctionDef)):
                por_nome[no.name] = ast.unparse(no).replace("'", '"')
        return por_nome

    def test_as_duas_rotas_existem(self):
        rotas = self._rotas()
        assert "get_s3_relink" in rotas
        assert "set_s3_relink" in rotas

    def test_so_o_MASTER_entra(self):
        """Mover a fronteira de posse de um cliente é uma escrita GLOBAL:
        depois dela, a guarda autoriza tudo o que estiver na pasta escolhida,
        de qualquer empresa. Por isso é do Master — um Admin local podia
        apontar a pasta de um cliente seu para a de um cliente de outra empresa."""
        rotas = self._rotas()
        for nome in ("get_s3_relink", "set_s3_relink"):
            fonte = rotas[nome]
            assert "require_roles([UserRole.MASTER])" in fonte, nome
            for outro in ("ADMIN", "CEO", "DIRETOR", "CONSULTOR", "ADMINISTRATIVO"):
                assert f"UserRole.{outro}" not in fonte, f"{nome} abriu a {outro}"

    def test_a_escrita_resolve_o_papel_EFECTIVO_e_passa_o_request(self):
        """O trilho tem de registar quem AUTORIZOU, e quem autoriza é o perfil
        activo — o `user["role"]` do JWT pode ser outro (a forma do
        `history._is_stealth_user` e do eliminar cliente)."""
        fonte = self._rotas()["set_s3_relink"]
        assert "get_effective_role_async(request, user)" in fonte
        assert "papel_efectivo=papel" in fonte
        assert "request=request" in fonte

    def test_as_rotas_sao_stubs_que_chamam_o_servico(self):
        rotas = self._rotas()
        assert "run_get_s3_relink(" in rotas["get_s3_relink"]
        assert "run_set_s3_mapping(" in rotas["set_s3_relink"]


class TestOServicoNaoEstaOrfao:
    """Contraprova da guarda acima: o módulo está LIGADO.

    Um serviço perfeito que nenhuma rota chama é código morto — e este
    projecto já apagou um componente órfão por isso.
    """

    def test_a_rota_importa_o_servico(self):
        from pathlib import Path

        fonte = (
            Path(__file__).resolve().parents[2] / "routes" / "admin_storage.py"
        ).read_text(encoding="utf-8")
        assert "from services.s3_relink import" in fonte
