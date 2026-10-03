"""O calendário: posse dos eventos e fronteira de rede (Lote 7, ponto 3).

OS TRÊS BURACOS QUE ESTES TESTES FECHAM
=======================================
1. `DELETE /deadlines/{id}` era `delete_one({"id": deadline_id})`. A rota
   tinha `require_roles` com todos os perfis de staff, logo um consultor da
   Domus — que é uma ilha — apagava um evento da Power sabendo o id.
2. `PUT /deadlines/{id}` lia por id e escrevia, e deixava **repontar
   `process_id`** para qualquer processo: o calendário da outra rede ganhava
   uma linha com o nome e o email do cliente.
3. `GET /deadlines?process_id=X` filtrava só por `process_id`, e ADMIN/CEO
   recebiam `query = {}` — todos os prazos de todas as redes, pelo papel do
   JWT (não o efectivo).

A classe `TestAExploracao` é o ataque, escrita para morder primeiro.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest
from fastapi import HTTPException

from services.deadline_scope import (
    e_papel_de_equipa,
    e_papel_sem_fronteira,
    esta_ligado_a_pessoa,
    evento_na_rede,
    pode_apontar_para_o_processo,
    pode_mexer_no_evento,
    rede_do_evento,
)

REDE_POWER = "grupo_power_precision"
REDE_DOMUS = "domus"


def _evento(**kw):
    # Os campos obrigatórios do `DeadlineResponse` entram todos: um fixture
    # incompleto dava um `ValidationError` que se lê como defeito do
    # serviço quando é defeito do teste.
    base = {
        "id": "ev1",
        "title": "Escritura Ana Martins",
        "due_date": "2026-11-20",
        "priority": "high",
        "completed": False,
        "created_at": "2026-10-01T09:00:00Z",
        "process_id": "proc-power",
        "created_by": "u-power",
        "assigned_user_ids": ["u-power"],
        "network_id": REDE_POWER,
        "company_id": "empresa-power",
    }
    base.update(kw)
    return base


# ════════════════════════════════════════════════════════════════════
#  A REGRA PURA
# ════════════════════════════════════════════════════════════════════
class TestAExploracao:
    """O ataque. Cada um destes passava antes do Lote 7."""

    def test_um_consultor_de_outra_rede_NAO_mexe_no_evento(self):
        assert pode_mexer_no_evento(
            _evento(),
            user_id="u-domus",
            papel="consultor",
            redes=(REDE_DOMUS,),
            processos_visiveis=("proc-domus",),
        ) is False

    def test_um_DIRETOR_de_outra_rede_tambem_nao(self):
        """O diretor é diretor da SUA rede, não da ilha ao lado.

        O bypass do produto é «acesso total à sua rede», e a tolerância de
        cruzamento entre redes é literalmente zero.
        """
        assert pode_mexer_no_evento(
            _evento(),
            user_id="u-domus",
            papel="diretor",
            redes=(REDE_DOMUS,),
        ) is False

    def test_nao_se_reponta_um_evento_para_um_processo_invisivel(self):
        assert pode_apontar_para_o_processo(
            "proc-domus", papel="diretor", processos_visiveis=("proc-power",),
        ) is False

    def test_um_evento_POR_CARIMBAR_nao_se_escreve_sem_ligacao(self):
        """A leitura aceita a pilha antiga; a ESCRITA exige prova.

        Assimetria deliberada, a mesma do `sub35`: ler de menos esconde
        eventos que existem (e isso nota-se), escrever de mais atravessa a
        fronteira (e isso não se nota).
        """
        assert pode_mexer_no_evento(
            _evento(network_id=None, company_id=None, process_id=None,
                    created_by="outro", assigned_user_ids=[]),
            user_id="u-domus",
            papel="diretor",
            redes=(REDE_DOMUS,),
        ) is False


class TestQuemPodeMexer:
    def test_o_AUTOR_pode_sempre_mexer_na_sua_marcacao(self):
        """Um evento pessoal não tem processo nem empresa — nenhuma
        condição de rede o alcança. Sem esta regra, o autor deixava de
        poder apagar a própria ausência, e isso nota-se.
        """
        assert pode_mexer_no_evento(
            _evento(process_id=None, network_id=None, assigned_user_ids=[],
                    created_by="u-power"),
            user_id="u-power",
            papel="consultor",
        ) is True

    def test_um_ATRIBUIDO_pode_mexer(self):
        assert pode_mexer_no_evento(
            _evento(created_by="outro", assigned_user_ids=["u-power"]),
            user_id="u-power",
            papel="consultor",
        ) is True

    def test_quem_VE_O_PROCESSO_pode_mexer_no_evento_dele(self):
        assert pode_mexer_no_evento(
            _evento(created_by="outro", assigned_user_ids=[]),
            user_id="u-colega",
            papel="consultor",
            processos_visiveis=("proc-power",),
        ) is True

    def test_um_papel_de_equipa_mexe_no_que_e_da_SUA_rede(self):
        assert pode_mexer_no_evento(
            _evento(created_by="outro", assigned_user_ids=[], process_id=None),
            user_id="u-diretor",
            papel="diretor",
            redes=(REDE_POWER,),
        ) is True

    def test_um_consultor_NAO_mexe_num_evento_da_sua_rede_que_nao_e_dele(self):
        """Contraprova do anterior: a rede não é, por si, autorização para
        um consultor. Senão a vista de equipa deixava de distinguir nada.
        """
        assert pode_mexer_no_evento(
            _evento(created_by="outro", assigned_user_ids=[], process_id=None),
            user_id="u-consultor",
            papel="consultor",
            redes=(REDE_POWER,),
        ) is False

    @pytest.mark.parametrize("papel", ["admin", "ceo", "ADMIN", " Ceo "])
    def test_a_administracao_reconcilia_a_pilha_inteira(self, papel):
        assert pode_mexer_no_evento(
            _evento(network_id=REDE_DOMUS), user_id="u-admin", papel=papel,
        ) is True

    def test_sem_evento_nao_se_mexe(self):
        for vazio in (None, {}):
            assert pode_mexer_no_evento(
                vazio, user_id="u", papel="admin",
            ) is False


class TestOsPrimitivos:
    def test_as_pessoas_do_evento_incluem_o_autor_e_os_responsaveis(self):
        from services.deadline_scope import pessoas_do_evento

        assert pessoas_do_evento(_evento(
            assigned_user_ids=["a", ""],
            created_by="b",
            assigned_consultor_id="c",
            assigned_mediador_id="d",
        )) == {"a", "b", "c", "d"}

    @pytest.mark.parametrize("valor", [None, "", "default"])
    def test_um_evento_sem_marca_de_rede_nao_pertence_a_rede_nenhuma(self, valor):
        assert rede_do_evento(_evento(network_id=valor)) == ""
        assert evento_na_rede(_evento(network_id=valor), (REDE_POWER,)) is False

    def test_esta_ligado_a_pessoa_recusa_um_id_vazio(self):
        """Senão um `user_id` ausente casava com qualquer evento."""
        assert esta_ligado_a_pessoa(_evento(), "") is False
        assert esta_ligado_a_pessoa(_evento(), None) is False

    def test_limpar_o_processo_e_sempre_permitido(self):
        """Transforma o evento num evento geral e não revela nada."""
        for vazio in (None, "", "   "):
            assert pode_apontar_para_o_processo(
                vazio, papel="consultor", processos_visiveis=(),
            ) is True

    def test_os_papeis_de_equipa_e_os_sem_fronteira_sao_conjuntos_distintos(self):
        assert e_papel_de_equipa("diretor") is True
        assert e_papel_sem_fronteira("diretor") is False, (
            "um diretor é diretor da SUA rede"
        )
        assert e_papel_sem_fronteira("admin") is True
        assert e_papel_de_equipa("consultor") is False


# ════════════════════════════════════════════════════════════════════
#  OS HANDLERS
# ════════════════════════════════════════════════════════════════════
class _Pedido:
    """Um `Request` suficiente: só os headers interessam ao papel efectivo."""

    def __init__(self, papel=None, empresa=None):
        self.headers = {}
        if papel:
            self.headers["X-Active-Role"] = papel
        if empresa:
            self.headers["X-Company-Id"] = empresa
        self.query_params = {}


async def _semear(fake_db):
    await fake_db.companies.insert_one(
        {"id": "empresa-power", "name": "Power", "network_id": REDE_POWER})
    await fake_db.companies.insert_one(
        {"id": "empresa-domus", "name": "Domus", "network_id": REDE_DOMUS})
    await fake_db.processes.insert_one({
        "id": "proc-power", "client_name": "Ana Martins",
        "client_email": "ana@exemplo.pt", "network_id": REDE_POWER,
        "company_id": "empresa-power", "status": "analise",
        "assigned_consultor_ids": ["u-power"],
    })
    await fake_db.processes.insert_one({
        "id": "proc-domus", "client_name": "Cliente Domus",
        "client_email": "domus@exemplo.pt", "network_id": REDE_DOMUS,
        "company_id": "empresa-domus", "status": "analise",
        "assigned_consultor_ids": ["u-domus"],
    })
    await fake_db.deadlines.insert_one(_evento())
    await fake_db.deadlines.insert_one(_evento(
        id="ev-domus", title="Escritura Domus", process_id="proc-domus",
        created_by="u-domus", assigned_user_ids=["u-domus"],
        network_id=REDE_DOMUS, company_id="empresa-domus",
    ))


DOMUS = {
    "id": "u-domus", "role": "consultor", "name": "Da Domus",
    "company": "empresa-domus", "active_company_id": "empresa-domus",
}
POWER = {
    "id": "u-power", "role": "consultor", "name": "Da Power",
    "company": "empresa-power", "active_company_id": "empresa-power",
}


class TestOEliminarComPosse:
    @pytest.mark.asyncio
    async def test_a_Domus_NAO_apaga_um_evento_da_Power(self, fake_async_db):
        from services import (
            deadlines_api_crud, deadlines_api_scope, tenant_network,
        )

        await _semear(fake_async_db)
        with patch.object(deadlines_api_crud, "db", fake_async_db), \
             patch.object(tenant_network, "db", fake_async_db), \
             patch.object(deadlines_api_scope, "db", fake_async_db):
            with pytest.raises(HTTPException) as exc:
                await deadlines_api_crud.run_delete_deadline(
                    "ev1", DOMUS, _Pedido(),
                )
        # 404 e não 403: distinguir "não existe" de "não é teu" confirma o id.
        assert exc.value.status_code == 404
        assert await fake_async_db.deadlines.find_one({"id": "ev1"}) is not None

    @pytest.mark.asyncio
    async def test_o_dono_apaga_o_seu_evento(self, fake_async_db):
        """Contraprova: recusar sempre também passava o teste de cima."""
        from services import (
            deadlines_api_crud, deadlines_api_scope, tenant_network,
        )

        await _semear(fake_async_db)
        with patch.object(deadlines_api_crud, "db", fake_async_db), \
             patch.object(tenant_network, "db", fake_async_db), \
             patch.object(deadlines_api_scope, "db", fake_async_db), \
             patch.object(deadlines_api_crud, "log_history", _nada):
            resposta = await deadlines_api_crud.run_delete_deadline(
                "ev1", POWER, _Pedido(),
            )
        assert resposta["message"] == "Prazo eliminado"
        assert await fake_async_db.deadlines.find_one({"id": "ev1"}) is None

    @pytest.mark.asyncio
    async def test_eliminar_deixa_rasto_mas_o_rasto_nunca_falha_a_operacao(
        self, fake_async_db,
    ):
        from services import (
            deadlines_api_crud, deadlines_api_scope, tenant_network,
        )

        await _semear(fake_async_db)
        chamadas = []

        async def _explode(*args, **kwargs):
            chamadas.append(args)
            raise RuntimeError("histórico em baixo")

        with patch.object(deadlines_api_crud, "db", fake_async_db), \
             patch.object(tenant_network, "db", fake_async_db), \
             patch.object(deadlines_api_scope, "db", fake_async_db), \
             patch.object(deadlines_api_crud, "log_history", _explode):
            resposta = await deadlines_api_crud.run_delete_deadline(
                "ev1", POWER, _Pedido(),
            )
        assert chamadas, "não registou a eliminação no histórico"
        assert resposta["message"] == "Prazo eliminado", (
            "o evento já saiu: levantar aqui mostrava um erro sobre uma "
            "operação que correu bem"
        )


class TestOEditarComPosse:
    @pytest.mark.asyncio
    async def test_a_Domus_NAO_edita_um_evento_da_Power(self, fake_async_db):
        from models.deadline import DeadlineUpdate
        from services import (
            deadlines_api_crud, deadlines_api_scope, tenant_network,
        )

        await _semear(fake_async_db)
        with patch.object(deadlines_api_crud, "db", fake_async_db), \
             patch.object(tenant_network, "db", fake_async_db), \
             patch.object(deadlines_api_scope, "db", fake_async_db):
            with pytest.raises(HTTPException) as exc:
                await deadlines_api_crud.run_update_deadline(
                    "ev1", DeadlineUpdate(title="Mexido"), DOMUS, _Pedido(),
                )
        assert exc.value.status_code == 404
        guardado = await fake_async_db.deadlines.find_one({"id": "ev1"})
        assert guardado["title"] == "Escritura Ana Martins"

    @pytest.mark.asyncio
    async def test_nao_se_reponta_um_evento_para_o_processo_de_outra_rede(
        self, fake_async_db,
    ):
        """O caso com consequência visível: o calendário da outra rede
        ganhava uma linha com o nome e o email do cliente.
        """
        from models.deadline import DeadlineUpdate
        from services import (
            deadlines_api_crud, deadlines_api_scope, tenant_network,
        )

        await _semear(fake_async_db)
        with patch.object(deadlines_api_crud, "db", fake_async_db), \
             patch.object(tenant_network, "db", fake_async_db), \
             patch.object(deadlines_api_scope, "db", fake_async_db):
            with pytest.raises(HTTPException) as exc:
                await deadlines_api_crud.run_update_deadline(
                    "ev1",
                    DeadlineUpdate(process_id="proc-domus"),
                    POWER,
                    _Pedido(),
                )
        assert exc.value.status_code == 404
        guardado = await fake_async_db.deadlines.find_one({"id": "ev1"})
        assert guardado["process_id"] == "proc-power"

    @pytest.mark.asyncio
    async def test_o_dono_edita_o_titulo(self, fake_async_db):
        from models.deadline import DeadlineUpdate
        from services import (
            deadlines_api_crud, deadlines_api_scope, tenant_network,
        )

        await _semear(fake_async_db)
        with patch.object(deadlines_api_crud, "db", fake_async_db), \
             patch.object(tenant_network, "db", fake_async_db), \
             patch.object(deadlines_api_scope, "db", fake_async_db):
            await deadlines_api_crud.run_update_deadline(
                "ev1", DeadlineUpdate(title="Escritura adiada"), POWER, _Pedido(),
            )
        guardado = await fake_async_db.deadlines.find_one({"id": "ev1"})
        assert guardado["title"] == "Escritura adiada"


class TestALeituraPorProcesso:
    @pytest.mark.asyncio
    async def test_pedir_os_prazos_de_um_processo_de_outra_rede_da_404(
        self, fake_async_db,
    ):
        from services import (
            deadlines_api_list, deadlines_api_scope, tenant_network,
        )

        await _semear(fake_async_db)
        with patch.object(deadlines_api_list, "db", fake_async_db), \
             patch.object(tenant_network, "db", fake_async_db), \
             patch.object(deadlines_api_scope, "db", fake_async_db):
            with pytest.raises(HTTPException) as exc:
                await deadlines_api_list.run_get_deadlines(
                    "proc-domus", POWER, _Pedido(),
                )
        assert exc.value.status_code == 404

    @pytest.mark.asyncio
    async def test_pedir_os_prazos_do_SEU_processo_funciona(self, fake_async_db):
        """Contraprova: recusar sempre tornava o endpoint inútil."""
        from services import (
            deadlines_api_list, deadlines_api_scope, tenant_network,
        )

        await _semear(fake_async_db)
        with patch.object(deadlines_api_list, "db", fake_async_db), \
             patch.object(tenant_network, "db", fake_async_db), \
             patch.object(deadlines_api_scope, "db", fake_async_db):
            linhas = await deadlines_api_list.run_get_deadlines(
                "proc-power", POWER, _Pedido(),
            )
        assert [linha.id for linha in linhas] == ["ev1"]


class TestOCarimboNaCriacao:
    @pytest.mark.asyncio
    async def test_o_evento_novo_leva_a_REDE_e_o_company_id_e_um_ID(
        self, fake_async_db,
    ):
        """Isto gravava `user.get("company")` — o NOME — em `company_id`.

        O calendário da equipa compara esse campo com o ID da empresa
        activa: o evento não casava com o ramo da empresa NEM com o do
        legado (que exige `null`/`""`/`default`), logo **desaparecia do
        calendário de todos**. E sem `network_id` caía na pilha por
        carimbar, que o ramo de legado aceita — um evento da Domus entrava
        no calendário da Power.
        """
        from models.deadline import DeadlineCreate
        from services import deadlines_api_crud, tenant_network

        await _semear(fake_async_db)
        with patch.object(deadlines_api_crud, "db", fake_async_db), \
             patch.object(tenant_network, "db", fake_async_db):
            await deadlines_api_crud.run_create_deadline(
                DeadlineCreate(
                    title="Reunião", due_date="2026-11-10", priority="medium",
                ),
                POWER,
                _Pedido(empresa="empresa-power"),
            )
        criado = await fake_async_db.deadlines.find_one({"title": "Reunião"})
        assert criado["network_id"] == REDE_POWER
        assert criado["company_id"] == "empresa-power", (
            "o campo tem de levar o ID da empresa, nunca o nome"
        )

    @pytest.mark.asyncio
    async def test_sem_rede_determinavel_nao_se_carimba_meio_carimbo(
        self, fake_async_db,
    ):
        """Carimbar a rede errada é permanente — pior do que não carimbar."""
        from models.deadline import DeadlineCreate
        from services import deadlines_api_crud, tenant_network

        orfao = {"id": "u-x", "role": "consultor", "name": "Sem Empresa"}
        with patch.object(deadlines_api_crud, "db", fake_async_db), \
             patch.object(tenant_network, "db", fake_async_db):
            await deadlines_api_crud.run_create_deadline(
                DeadlineCreate(
                    title="Sem rede", due_date="2026-11-10", priority="medium",
                ),
                orfao,
                _Pedido(),
            )
        criado = await fake_async_db.deadlines.find_one({"title": "Sem rede"})
        assert criado.get("network_id") in (None, "")
        assert criado.get("company_id") in (None, "")


class TestAFonteDoCalendario:
    """Guardas sobre o código-fonte: o ramo que falhava aberto não volta."""

    def _fonte(self, nome):
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        caminho = Path(__file__).resolve().parents[2] / "services" / nome
        return codigo_sem_comentarios(caminho.read_text(encoding="utf-8"))

    def test_o_calendario_envolve_a_consulta_na_condicao_de_rede(self):
        fonte = self._fonte("deadlines_api_calendar.py")
        assert "com_isolamento(" in fonte, (
            "o calendário voltou a consultar sem a fronteira de rede"
        )

    def test_as_listagens_tambem(self):
        fonte = self._fonte("deadlines_api_list.py")
        assert fonte.count("com_isolamento(") >= 3, (
            "uma das listagens de prazos perdeu o isolamento de rede"
        )

    def test_as_listagens_nao_decidem_mais_pelo_papel_do_JWT(self):
        """`user["role"] in [ADMIN, CEO]` era a isenção pelo token."""
        fonte = self._fonte("deadlines_api_list.py")
        assert 'user["role"] in [' not in fonte
        assert "UserRole.ADMIN" not in fonte, (
            "voltou a comparar o papel do JWT com uma lista escrita à mão"
        )
        # Contraprova: o papel efectivo é mesmo consultado.
        assert "contexto.papel" in fonte

    def test_o_crud_chama_a_guarda_de_posse_nos_DOIS_pontos(self):
        """Contraprova das guardas acima: sem isto, apagar as chamadas
        satisfazia tudo o que está à volta.
        """
        fonte = self._fonte("deadlines_api_crud.py")
        assert fonte.count("pode_mexer_no_evento(") == 2
        assert "pode_apontar_para_o_processo(" in fonte


async def _nada(*args, **kwargs):
    return None
