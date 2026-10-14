"""
Lote 5 — D-27 FECHADA: os defaults de capacidades por cargo sobrevivem a um reinício.

O DEFEITO
  `PUT /admin/permissions/role-defaults/{role}` alterava o dicionário em MEMÓRIA e escrevia uma cópia que
  nada lia de volta: a edição perdia-se no reinício, e com vários workers só o que recebeu o pedido a
  conhecia.

O DESENHO PROVADO AQUI
  * guarda-se o DESVIO em relação ao código (nunca o retrato completo — o retrato congelaria também os
    defaults do código e desfazia em silêncio qualquer correcção de um deploy);
  * um «reinício» (repor a matriz ao código e carregar da base de dados) devolve a edição;
  * o retrato antigo NÃO se aplica, mostra-se;
  * lixo na base de dados nunca vira permissão; falhar a ler mantém o que está em memória.
"""
from __future__ import annotations

import copy
from unittest.mock import AsyncMock, patch

import pytest

from models.permissions import CAPABILITIES, ROLE_CAPABILITY_DEFAULTS
from services import role_defaults_store as store

MASTER = {"id": "u-m", "role": "master", "name": "M", "email": "m@x.pt"}


@pytest.fixture
def matriz(fake_async_db):
    """Isola a matriz global (é estado de módulo) e liga o store à base de dados falsa."""
    guardada = copy.deepcopy(ROLE_CAPABILITY_DEFAULTS)
    store.invalidar_cache()
    with patch.object(store, "db", fake_async_db):
        yield fake_async_db
    for cargo in list(ROLE_CAPABILITY_DEFAULTS):
        ROLE_CAPABILITY_DEFAULTS[cargo].clear()
        ROLE_CAPABILITY_DEFAULTS[cargo].update(guardada[cargo])
    store.invalidar_cache()


def _uma_capacidade_de(cargo):
    """Uma capacidade cujo default do código é True para o cargo (para a podermos desligar)."""
    return next(c for c, v in store.DEFAULTS_DO_CODIGO[cargo].items() if v is True)


async def _editar(cargo, caps, bd):
    import services.admin_permissions as ap
    from services.admin_permissions import CapabilityUpdateRequest

    with patch.object(ap, "db", bd), patch.object(ap, "_audit_log", AsyncMock()):
        return await ap.run_update_role_defaults(cargo, CapabilityUpdateRequest(capabilities=caps), MASTER)


def _reiniciar():
    """O que um reinício faz à matriz: volta ao código."""
    store.aplicar({})


@pytest.mark.asyncio
class TestASobrevivenciaAoReinicio:
    async def test_a_edicao_sobrevive(self, matriz):
        cargo = "diretor"
        cap = _uma_capacidade_de(cargo)
        await _editar(cargo, {cap: False}, matriz)
        assert ROLE_CAPABILITY_DEFAULTS[cargo][cap] is False

        _reiniciar()
        assert ROLE_CAPABILITY_DEFAULTS[cargo][cap] is True, "premissa: sem a base de dados a edição perde-se"

        assert await store.refrescar(forcar=True) is True
        assert ROLE_CAPABILITY_DEFAULTS[cargo][cap] is False

    async def test_so_o_desvio_vai_para_a_base_de_dados(self, matriz):
        cargo = "diretor"
        cap = _uma_capacidade_de(cargo)
        await _editar(cargo, {cap: False}, matriz)
        doc = next(d for d in matriz.system_config.docs if d.get("key") == store.CHAVE)
        assert doc["overrides"] == {cargo: {cap: False}}, "nada do retrato completo"

    async def test_um_default_do_codigo_que_muda_num_deploy_chega_a_quem_nao_foi_editado(self, matriz):
        """O erro caro do retrato: congelava os defaults do código do dia em que foi tirado."""
        cargo, cap = "diretor", _uma_capacidade_de("diretor")
        outra = next(c for c, v in store.DEFAULTS_DO_CODIGO["consultor"].items() if v is True)
        await _editar(cargo, {cap: False}, matriz)
        _reiniciar()

        # «deploy»: o código passa a ter outro default para o consultor
        store.DEFAULTS_DO_CODIGO["consultor"][outra] = False
        try:
            await store.refrescar(forcar=True)
            assert ROLE_CAPABILITY_DEFAULTS["consultor"][outra] is False, "o código novo vence onde ninguém decidiu"
            assert ROLE_CAPABILITY_DEFAULTS[cargo][cap] is False, "e a decisão do administrador mantém-se"
        finally:
            store.DEFAULTS_DO_CODIGO["consultor"][outra] = True

    async def test_a_edicao_de_outro_worker_chega_a_este(self, matriz):
        cargo, cap = "diretor", _uma_capacidade_de("diretor")
        await matriz.system_config.insert_one({"key": store.CHAVE, "overrides": {cargo: {cap: False}}})
        store.invalidar_cache()
        await store.refrescar()
        assert ROLE_CAPABILITY_DEFAULTS[cargo][cap] is False

    async def test_um_override_apagado_na_base_de_dados_desaparece_da_memoria(self, matriz):
        cargo, cap = "diretor", _uma_capacidade_de("diretor")
        ROLE_CAPABILITY_DEFAULTS[cargo][cap] = False       # edição antiga em memória
        await store.refrescar(forcar=True)                 # a base de dados não tem override nenhum
        assert ROLE_CAPABILITY_DEFAULTS[cargo][cap] is True

    async def test_a_matriz_e_atualizada_no_mesmo_dicionario(self, matriz):
        """15 módulos guardam a referência a `ROLE_CAPABILITY_DEFAULTS`: tem de ser IN PLACE."""
        referencia = ROLE_CAPABILITY_DEFAULTS
        interno = ROLE_CAPABILITY_DEFAULTS["diretor"]
        cap = _uma_capacidade_de("diretor")
        store.aplicar({"diretor": {cap: False}})
        assert referencia is ROLE_CAPABILITY_DEFAULTS and referencia["diretor"] is interno
        assert interno[cap] is False


@pytest.mark.asyncio
class TestOQueNuncaSeAplica:
    async def test_o_retrato_antigo_nao_e_aplicado_mas_e_mostrado(self, matriz):
        cap = _uma_capacidade_de("diretor")
        retrato = {c: dict(d) for c, d in store.DEFAULTS_DO_CODIGO.items()}
        retrato["diretor"][cap] = not store.DEFAULTS_DO_CODIGO["diretor"][cap]
        await matriz.system_config.insert_one({"key": store.CHAVE_LEGADA, "value": retrato})

        await store.refrescar(forcar=True)
        assert ROLE_CAPABILITY_DEFAULTS["diretor"][cap] is True, "o retrato NÃO é aplicado"

        diferencas = await store.diferencas_do_legado()
        assert diferencas == [{
            "cargo": "diretor", "capacidade": cap, "retrato_antigo": False, "codigo": True,
        }]

    @pytest.mark.parametrize("lixo", [
        None, "x", [], {"diretor": "x"}, {"desconhecido": {"PROCESS_CREATE": True}},
        {"admin": {"PROCESS_CREATE": False}}, {"diretor": {"NAO_EXISTE": True}},
        {"diretor": {"PROCESS_CREATE": "false"}}, {"diretor": {"PROCESS_CREATE": 0}},
    ])
    def test_lixo_nunca_vira_permissao(self, lixo):
        assert store.limpar_overrides(lixo) == {}

    def test_um_booleano_valido_passa(self):
        assert store.limpar_overrides({"diretor": {"PROCESS_CREATE": False}}) == {"diretor": {"PROCESS_CREATE": False}}

    async def test_falhar_a_ler_nao_repoe_nem_derruba(self, matriz):
        cap = _uma_capacidade_de("diretor")
        ROLE_CAPABILITY_DEFAULTS["diretor"][cap] = False
        with patch.object(store, "_ler_overrides_da_base", AsyncMock(side_effect=RuntimeError("mongo em baixo"))):
            assert await store.refrescar(forcar=True) is False
        assert ROLE_CAPABILITY_DEFAULTS["diretor"][cap] is False, "mantém o que estava em memória"

    async def test_admin_e_ceo_nunca_sao_editaveis(self, matriz):
        for cargo in ("admin", "ceo", "master"):
            assert store.limpar_overrides({cargo: {"PROCESS_CREATE": False}}) == {}


class TestALigacao:
    def test_o_get_current_user_refresca(self):
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios((Path(__file__).resolve().parents[2] / "services" / "auth.py").read_text(encoding="utf-8"))
        assert "role_defaults_store" in fonte and "refrescar_defaults_por_cargo()" in fonte

    def test_o_arranque_carrega(self):
        from pathlib import Path

        from tests.unit.helpers_fonte import codigo_sem_comentarios

        fonte = codigo_sem_comentarios((Path(__file__).resolve().parents[2] / "server.py").read_text(encoding="utf-8"))
        assert "carregar_defaults_por_cargo()" in fonte

    def test_o_escritor_ja_nao_grava_o_retrato(self):
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "services" / "admin_permissions.py").read_text(encoding="utf-8")
        assert '"value": {r: d for r, d in ROLE_CAPABILITY_DEFAULTS.items()}' not in fonte
        assert "guardar_overrides_actuais" in fonte

    def test_o_leitor_le_mesmo_os_cargos(self):
        assert "diretor" in store.DEFAULTS_DO_CODIGO and len(CAPABILITIES) > 10


@pytest.mark.asyncio
async def test_uma_leitura_falhada_nao_se_repete_a_cada_pedido(fake_async_db):
    """Sem o intervalo, uma base de dados em baixo atrasava TODOS os pedidos autenticados."""
    store.invalidar_cache()
    leitura = AsyncMock(side_effect=RuntimeError("mongo em baixo"))
    with patch.object(store, "_ler_overrides_da_base", leitura):
        await store.refrescar()
        await store.refrescar()
        await store.refrescar()
    assert leitura.await_count == 1
    store.invalidar_cache()
