"""A conta Master passa em TODAS as rotas declaradas só-Master, com qualquer chapéu (QA, Out 2026).

DECISÃO DO DONO DO PRODUTO
  «Um utilizador cuja conta base seja Master não deve encontrar barreiras de 403,
  independentemente do perfil/UCR activo no seletor de contexto.» A primeira passagem só tratou
  as rotas de `system-config`; as restantes ~120 rotas exclusivas de Master (logs, backups,
  índices, encriptação, S3, jobs, IA, migrações, diagnósticos, workflow, empresas…) continuavam a
  seguir o perfil activo: um Master que escolhesse trabalhar como Admin da Power levava 403 em
  coisas que são, por definição, dele.

COMO SE GARANTE
  O bypass é IMPLÍCITO numa guarda cuja lista é só `master` (`lista_e_so_master`). Não há flag para
  esquecer em 120 sítios nem um sítio novo que a esqueça. Este ficheiro percorre as rotas REAIS da
  aplicação (as dependências que o FastAPI monta), não o código-fonte: apanha também as guardas
  construídas a partir de constantes (`PAPEIS_QUE_ESCREVEM_O_CHANGELOG`) e as de nível de router.

O QUE NÃO MUDA
  O âmbito de DADOS continua a seguir o perfil activo (`test_hierarquia_de_perfis`): o Master a
  trabalhar como Admin vê o que um Admin vê. Aqui só se fala da guarda de PAPEL.
"""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from models.auth import UserRole
from services.auth import lista_e_so_master, require_roles

MASTER = {"id": "u-master", "name": "M", "email": "m@x.pt", "role": "master"}
ADMIN = {"id": "u-admin", "name": "A", "email": "a@x.pt", "role": "admin"}
CEO = {"id": "u-ceo", "name": "C", "email": "c@x.pt", "role": "ceo"}
CONSULTOR = {"id": "u-cons", "name": "K", "email": "k@x.pt", "role": "consultor"}

CHAPEUS = (
    {"X-Active-Role": "admin", "X-Company-Id": "cmp-power"},
    {"X-Active-Role": "ceo", "X-Company-Id": "cmp-power"},
    {"X-Active-Role": "consultor", "X-Company-Id": "cmp-precision"},
    {"X-Active-Role": "all"},
)


class Pedido:
    def __init__(self, cabecalhos=None):
        self.headers = cabecalhos or {}
        self.state = SimpleNamespace()


def _guardas_da_aplicacao():
    """Todas as guardas `require_roles` montadas nas rotas reais: {(caminho, métodos): guarda}."""
    os.environ.setdefault("TESTING", "true")
    import server

    achadas = {}

    def percorrer(dependant, chave):
        for dep in dependant.dependencies:
            chamada = dep.call
            if hasattr(chamada, "allowed_roles"):
                achadas[(chave, id(chamada))] = chamada
            percorrer(dep, chave)

    for rota in server.app.routes:
        dependant = getattr(rota, "dependant", None)
        if dependant is None:
            continue
        chave = (getattr(rota, "path", "?"), tuple(sorted(getattr(rota, "methods", None) or ())))
        percorrer(dependant, chave)
    return achadas


@pytest.fixture(scope="module")
def guardas():
    return _guardas_da_aplicacao()


def _so_master(guardas):
    return {k: g for k, g in guardas.items() if lista_e_so_master(g.allowed_roles)}


class TestListaESoMaster:
    @pytest.mark.parametrize("lista", [[UserRole.MASTER], ["master"], ["MASTER"], [UserRole.MASTER, "master"]])
    def test_so_master(self, lista):
        assert lista_e_so_master(lista) is True

    @pytest.mark.parametrize("lista", [
        [], None, [UserRole.MASTER, UserRole.ADMIN], [UserRole.ADMIN], [UserRole.DIRETOR, UserRole.MASTER],
    ])
    def test_nao_e_so_master(self, lista):
        assert lista_e_so_master(lista) is False


@pytest.mark.asyncio
class TestOMecanismo:
    @pytest.mark.parametrize("chapeu", CHAPEUS)
    async def test_master_com_qualquer_chapeu_passa_numa_guarda_so_master(self, chapeu):
        assert (await require_roles([UserRole.MASTER])(request=Pedido(chapeu), user=MASTER)) is MASTER

    async def test_continua_a_recusar_quem_nao_e_conta_master(self):
        for utilizador in (ADMIN, CEO, CONSULTOR):
            with pytest.raises(HTTPException) as erro:
                await require_roles([UserRole.MASTER])(request=Pedido(), user=utilizador)
            assert erro.value.status_code == 403

    async def test_um_admin_com_cabecalho_de_master_continua_a_ser_recusado(self):
        with pytest.raises(HTTPException):
            await require_roles([UserRole.MASTER])(
                request=Pedido({"X-Active-Role": "master"}), user=ADMIN,
            )

    def test_a_guarda_declara_o_que_e(self):
        guarda = require_roles([UserRole.MASTER])
        assert guarda.allowed_roles == (UserRole.MASTER,)
        assert guarda.conta_master_passa is True
        assert require_roles([UserRole.DIRETOR]).conta_master_passa is False
        assert require_roles([UserRole.MASTER, UserRole.ADMIN]).conta_master_passa is False
        assert require_roles([UserRole.MASTER, UserRole.ADMIN], conta_master_passa=True).conta_master_passa is True


@pytest.mark.asyncio
class TestAsRotasReais:
    def test_o_inventario_le_mesmo_as_rotas(self, guardas):
        """Contraprova: um leitor que devolva pouco faria as asserções seguintes passar por cegueira."""
        so_master = _so_master(guardas)
        assert len(guardas) >= 150, f"só leu {len(guardas)} guardas"
        assert len(so_master) >= 100, f"só leu {len(so_master)} guardas só-Master"

    def test_TODA_a_guarda_so_master_das_rotas_reais_tem_o_bypass_da_conta(self, guardas):
        sem = sorted({str(k[0]) for k, g in _so_master(guardas).items() if not g.conta_master_passa})
        assert sem == [], f"guardas só-Master sem o bypass da conta Master: {sem}"

    def test_as_guardas_mistas_de_system_config_continuam_com_a_flag_explicita(self, guardas):
        mistas = [
            g for (chave, _), g in guardas.items()
            if str(chave[0]).startswith("/api/system-config")
        ]
        assert mistas, "o leitor tem de encontrar as guardas de system-config"
        assert all(g.conta_master_passa for g in mistas)

    async def test_executa_CADA_guarda_so_master_com_o_chapeu_de_admin(self, guardas):
        executadas = 0
        for (chave, _), guarda in _so_master(guardas).items():
            resultado = await guarda(request=Pedido(CHAPEUS[0]), user=MASTER)
            assert resultado is MASTER, f"{chave} recusou a conta Master"
            executadas += 1
        assert executadas >= 100

    async def test_nenhuma_guarda_so_master_deixa_passar_um_admin(self, guardas):
        """A contraprova que importa: abrir ao Master não abriu a ninguém mais."""
        for (chave, _), guarda in _so_master(guardas).items():
            with pytest.raises(HTTPException) as erro:
                await guarda(request=Pedido(), user=ADMIN)
            assert erro.value.status_code == 403, f"{chave} deixou passar um Admin"
