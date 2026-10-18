"""Mapeamento S3: nomes legíveis, filtro «sem mapeamento» no servidor e contagens estáveis (QA-6)."""
from unittest.mock import patch

import pytest

from services import admin_s3_process_mappings as mod
from services.s3_folder_display import caminho_legivel

CID = "11111111-1111-4111-8111-111111111111"
PID = "22222222-2222-4222-8222-222222222222"
RAIZ = "Documentação Clientes/"


class TestCaminhoLegivel:
    def test_pasta_do_processo_por_id_vira_cliente_e_numero(self):
        assert caminho_legivel(
            f"{RAIZ}{CID}/processos/{PID}", nome_do_cliente="Ana Costa", numero_do_processo="12",
        ) == "Ana Costa › Processo n.º 12"

    def test_pasta_do_cliente_por_id(self):
        assert caminho_legivel(f"{RAIZ}{CID}", nome_do_cliente="Ana Costa") == "Ana Costa"

    def test_pasta_antiga_por_nome_perde_os_underscores(self):
        assert caminho_legivel(f"{RAIZ}Joao_Silva") == "Joao Silva"

    def test_nunca_mostra_o_uuid_mesmo_sem_nome(self):
        texto = caminho_legivel(f"{RAIZ}{CID}/processos/{PID}")
        assert CID not in texto and PID not in texto
        assert texto == "Cliente sem nome › Processo"

    @pytest.mark.parametrize("valor", [None, "", "   ", ["Documentação Clientes/x"], 3, RAIZ])
    def test_sem_pasta_ou_com_tipo_errado_e_vazio(self, valor):
        assert caminho_legivel(valor) == ""


def _processos(com_pasta):
    base = []
    for i in range(6):
        doc = {
            "id": f"p{i}", "process_number": str(i), "client_name": f"Cliente {i}",
            "status": "em_curso", "created_at": f"2026-10-0{i + 1}",
        }
        if i in com_pasta:
            doc["s3_folder"] = f"{RAIZ}{CID}/processos/p{i}"
        base.append(doc)
    return base


@pytest.fixture
def mundo(fake_async_db):
    async def _sem_condicao(_user):
        return {}

    with patch.object(mod, "db", fake_async_db), \
         patch("services.tenant_network.build_tenant_process_condition", _sem_condicao), \
         patch("services.s3_storage.s3_service.is_configured", return_value=False):
        yield fake_async_db


async def _listar(**kw):
    base = dict(search=None, status=None, has_mapping=None, include_closed=False,
                include_deleted=False, page=1, limit=50, user={"id": "u"}, request=None)
    base.update(kw)
    return await mod.run_get_process_s3_mappings(**base)


@pytest.mark.asyncio
async def test_so_sem_mapeamento_filtra_no_servidor_e_as_contagens_nao_mudam(mundo):
    await mundo.processes.insert_many(_processos(com_pasta={0, 1}))
    todos = await _listar()
    so_sem = await _listar(has_mapping=False)
    assert {p["id"] for p in so_sem["processes"]} == {"p2", "p3", "p4", "p5"}
    assert so_sem["stats"] == todos["stats"] == {"total": 6, "mapped": 2, "unmapped": 4}
    assert so_sem["total"] == 4


@pytest.mark.asyncio
async def test_pesquisa_e_filtro_de_mapeamento_valem_os_dois(mundo):
    """Antes o filtro de mapeamento escrevia no mesmo `$or` da pesquisa e apagava-a."""
    await mundo.processes.insert_many(_processos(com_pasta={0}))
    r = await _listar(has_mapping=False, search="Cliente 3")
    assert [p["id"] for p in r["processes"]] == ["p3"]


@pytest.mark.asyncio
async def test_cada_processo_traz_o_caminho_legivel(mundo):
    await mundo.processes.insert_many(_processos(com_pasta={0}))
    r = await _listar()
    por_id = {p["id"]: p for p in r["processes"]}
    assert por_id["p0"]["s3_folder_display"] == "Cliente 0 › p0"
    assert por_id["p0"]["s3_folder"].endswith("/processos/p0"), "o caminho cru fica intacto"
    assert por_id["p1"]["s3_folder_display"] == ""
