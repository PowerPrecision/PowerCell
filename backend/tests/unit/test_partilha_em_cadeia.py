"""
Partilha B2B em cadeia, linhagem e o papel do Parceiro (Out 2026).

O PEDIDO
  Um «Parceiro» é um angariador (não executante). A Empresa Y (destino) pode partilhar em
  cadeia com a Empresa Z sem fricção nem aprovação do Parceiro:

    * o PARCEIRO vê onde o processo está (a Empresa Z);
    * a Empresa Z vê TODA a linhagem (Parceiro → Y → Z);
    * o ecrã mostra essa linhagem; o modelo de dados suporta a cadeia contínua sem
      perder a origem;
    * parceiros (freelancers) nunca aparecem — nem são aceites — nas atribuições de tarefas.

O QUE ESTES TESTES FIXAM
  1. A linhagem deriva do registo (nunca gravada), com a origem, a casa dona e cada elo;
  2. quem VÊ o processo pode passá-lo à frente (antes só a casa dona partilhava) e o elo guarda
     de quem veio e a que distância está;
  3. revogar um elo revoga os que dele derivam; a convidada só retira os seus;
  4. o parceiro vê o NOME de onde está — nunca redes, ids nem quem passou a quem;
  5. o servidor recusa tarefas atribuídas a parceiros (a lista do ecrã é cortesia).
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from services import process_lineage as lin
from services import process_sharing as ps
from services.partner_visibility import dto_do_processo

from tests.unit.helpers_tenant import REDE_DOMUS, REDE_INCUMBENTE
from tests.unit.test_triagem_por_rede_de_destino import (  # noqa: F401  (fixtures)
    BRUNO,
    CRIS,
    DINA,
    _processo,
    cliente_http,
    rede_de_omissao_incumbente,
)

OMEGA_REDE = "rede:omega"


def _elo(rede, nome, *, de=None, depth=1, company_id=None, em="2026-10-01T10:00:00+00:00"):
    entrada = {
        "company_id": company_id or f"cmp-{rede}", "company_name": nome, "network_id": rede,
        "added_at": em, "added_by": "u-x",
    }
    if de is not None:
        entrada["shared_from_network"] = de
        entrada["depth"] = depth
    return entrada


def _processo_base(**extra):
    return {
        "id": "p-1", "network_id": "rede-y", "company_id": "cmp-y", "company_name": "Empresa Y",
        "assigned_parceiro_id": "par-1", "parceiro_name": "João Angariador", **extra,
    }


# ====================================================================
# 1. A linhagem
# ====================================================================

class TestAlinhagem:
    def test_sem_partilhas_so_a_origem_e_a_casa_dona(self):
        linhagem = lin.construir_linhagem(_processo_base())
        assert linhagem["tem_cadeia"] is False
        assert linhagem["empresa_actual"] == ["Empresa Y"]
        (caminho,) = linhagem["caminhos"]
        assert [n["nome"] for n in caminho] == ["João Angariador", "Empresa Y"]
        assert linhagem["origem"] == {"tipo": "parceiro", "nome": "João Angariador", "nivel": 0}

    def test_parceiro_y_z_e_o_pedido_literal(self):
        processo = _processo_base(partner_companies=[_elo("rede-z", "Empresa Z", de="rede-y")])
        linhagem = lin.construir_linhagem(processo)
        (caminho,) = linhagem["caminhos"]
        assert [n["nome"] for n in caminho] == ["João Angariador", "Empresa Y", "Empresa Z"]
        assert [n["tipo"] for n in caminho] == ["parceiro", "empresa", "empresa"]
        assert linhagem["empresa_actual"] == ["Empresa Z"]
        assert linhagem["tem_cadeia"] is True
        z = caminho[-1]
        assert z["partilhado_por"] == "Empresa Y" and z["papel"] == "convidada" and z["nivel"] == 2

    def test_a_cadeia_e_continua_y_z_w(self):
        processo = _processo_base(partner_companies=[
            _elo("rede-z", "Empresa Z", de="rede-y", depth=1, em="2026-10-01T10:00:00+00:00"),
            _elo("rede-w", "Empresa W", de="rede-z", depth=2, em="2026-10-02T10:00:00+00:00"),
        ])
        linhagem = lin.construir_linhagem(processo)
        (caminho,) = linhagem["caminhos"]
        assert [n["nome"] for n in caminho] == ["João Angariador", "Empresa Y", "Empresa Z", "Empresa W"]
        assert linhagem["empresa_actual"] == ["Empresa W"]
        assert linhagem["profundidade"] == 3
        assert [p["partilhado_por"] for p in linhagem["partilhas"]] == ["Empresa Y", "Empresa Z"]

    def test_ramificacoes_dao_um_caminho_por_folha(self):
        processo = _processo_base(partner_companies=[
            _elo("rede-z1", "Z1", de="rede-y", em="2026-10-01T10:00:00+00:00"),
            _elo("rede-z2", "Z2", de="rede-y", em="2026-10-02T10:00:00+00:00"),
        ])
        linhagem = lin.construir_linhagem(processo)
        assert [c[-1]["nome"] for c in linhagem["caminhos"]] == ["Z1", "Z2"]
        assert linhagem["empresa_actual"] == ["Z1", "Z2"]

    def test_uma_entrada_antiga_sem_origem_foi_aberta_pela_casa_dona(self):
        # Os elos anteriores a esta funcionalidade não têm `shared_from_network`.
        processo = _processo_base(partner_companies=[_elo("rede-z", "Empresa Z")])
        linhagem = lin.construir_linhagem(processo)
        assert [n["nome"] for n in linhagem["caminhos"][0]] == ["João Angariador", "Empresa Y", "Empresa Z"]

    def test_um_elo_orfao_pendura_se_na_casa_dona_nunca_desaparece(self):
        # O pai (rede-sumida) já não está no registo: esconder o elo seria esconder um acesso.
        processo = _processo_base(partner_companies=[_elo("rede-w", "Empresa W", de="rede-sumida", depth=2)])
        linhagem = lin.construir_linhagem(processo)
        assert linhagem["empresa_actual"] == ["Empresa W"]
        assert linhagem["partilhas"][0]["partilhado_por"] == "Empresa Y"

    def test_sem_parceiro_angariador_nao_ha_origem(self):
        processo = _processo_base(partner_companies=[_elo("rede-z", "Z", de="rede-y")])
        processo.pop("assigned_parceiro_id")
        linhagem = lin.construir_linhagem(processo)
        assert linhagem["origem"] is None
        assert [n["nome"] for n in linhagem["caminhos"][0]] == ["Empresa Y", "Z"]

    def test_parceiro_sem_nome_conhecido_chama_se_parceiro(self):
        processo = _processo_base()
        processo.pop("parceiro_name")
        assert lin.construir_linhagem(processo)["origem"]["nome"] == "Parceiro"

    def test_o_nome_da_casa_dona_resolvido_pelo_chamador_vence_o_carimbo(self):
        linhagem = lin.construir_linhagem(_processo_base(), casa_dona="Y Resolvida")
        assert linhagem["dona"]["nome"] == "Y Resolvida"

    def test_um_ciclo_no_registo_nao_prende_o_calculo(self):
        # Dados corrompidos: Z diz ter vindo de W e W de Z. Tem de terminar.
        processo = _processo_base(partner_companies=[
            _elo("rede-z", "Z", de="rede-w", depth=2), _elo("rede-w", "W", de="rede-z", depth=2),
        ])
        linhagem = lin.construir_linhagem(processo)
        assert {p["nome"] for p in linhagem["partilhas"]} == {"Z", "W"}

    def test_documento_vazio_ou_com_tipo_errado_nao_rebenta(self):
        assert lin.construir_linhagem(None)["tem_cadeia"] is False
        assert lin.construir_linhagem({"partner_companies": "lixo"})["tem_cadeia"] is False


# ====================================================================
# 2. O que o parceiro vê: ONDE está
# ====================================================================

class TestOParceiroVeOndeEsta:
    def test_sem_partilhas_esta_na_empresa_de_destino(self):
        assert lin.empresas_onde_esta(_processo_base()) == ["Empresa Y"]

    def test_apos_a_cadeia_esta_na_ultima(self):
        processo = _processo_base(partner_companies=[
            _elo("rede-z", "Empresa Z", de="rede-y"),
            _elo("rede-w", "Empresa W", de="rede-z", depth=2, em="2026-10-02T10:00:00+00:00"),
        ])
        assert lin.empresas_onde_esta(processo) == ["Empresa W"]

    def test_o_dto_do_parceiro_leva_so_o_nome(self):
        processo = _processo_base(
            status="novo", process_number=3, client_name="Cliente",
            partner_companies=[_elo("rede-z", "Empresa Z", de="rede-y", company_id="cmp-z-secreto")],
        )
        dto = dto_do_processo(processo, "novo")
        assert dto["empresa_actual"] == "Empresa Z"
        bruto = json.dumps(dto)
        # Nem redes, nem ids, nem quem passou a quem, nem o nome do parceiro de outrem.
        for proibido in ("rede-z", "rede-y", "cmp-z-secreto", "cmp-y", "shared_from", "depth", "caminhos"):
            assert proibido not in bruto, proibido

    def test_dto_sem_dados_de_empresa_nao_inventa(self):
        dto = dto_do_processo({"id": "p", "status": "novo"}, "novo")
        assert dto["empresa_actual"] is None

    def test_a_projeccao_le_o_registo_mas_o_dto_nunca_o_devolve(self):
        from services.partner_visibility import PROJECCAO_DO_PROCESSO

        assert PROJECCAO_DO_PROCESSO["partner_companies"] == 1
        dto = dto_do_processo(_processo_base(partner_companies=[_elo("rede-z", "Z", de="rede-y")]), "novo")
        assert "partner_companies" not in dto and "linhagem" not in dto


# ====================================================================
# 3. Quem pode passar à frente e o que fica gravado
# ====================================================================

class TestAPartilhaEmCadeia:
    def test_a_casa_dona_abre_o_primeiro_elo_a_profundidade_1(self, cliente_http):
        c, db = cliente_http
        r = c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        assert r.status_code == 200, r.text
        (elo,) = _processo(db)["partner_companies"]
        assert elo["shared_from_network"] == REDE_DOMUS and elo["depth"] == 1
        assert elo["shared_from_company_name"]  # o nome de quem abriu o elo

    def test_a_convidada_passa_adiante_e_o_elo_vem_dela(self, cliente_http):
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador(CRIS)
        r = c.post("/processes/p-domus/partners", json={"network_id": OMEGA_REDE})
        assert r.status_code == 200, r.text
        omega = next(e for e in _processo(db)["partner_companies"] if e["network_id"] == OMEGA_REDE)
        assert omega["shared_from_network"] == REDE_INCUMBENTE
        assert omega["depth"] == 2
        assert "Precision" in omega["shared_from_company_name"] or "Power" in omega["shared_from_company_name"]
        # A casa dona não muda: a cadeia só acrescenta quem VÊ.
        assert _processo(db)["network_id"] == REDE_DOMUS
        assert set(_processo(db)["partner_network_ids"]) == {REDE_INCUMBENTE, OMEGA_REDE}

    def test_a_convidada_nao_pode_devolver_o_processo_a_casa_dona(self, cliente_http):
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador(CRIS)
        r = c.post("/processes/p-domus/partners", json={"network_id": REDE_DOMUS})
        assert r.status_code == 400
        assert len(_processo(db)["partner_companies"]) == 1

    def test_a_convidada_nao_se_partilha_a_si_propria(self, cliente_http):
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador(CRIS)
        r = c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        assert r.status_code == 400
        assert len(_processo(db)["partner_companies"]) == 1

    def test_o_destino_que_ja_tem_acesso_e_idempotente(self, cliente_http):
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador(CRIS)
        c.post("/processes/p-domus/partners", json={"network_id": OMEGA_REDE})
        r = c.post("/processes/p-domus/partners", json={"network_id": OMEGA_REDE})
        assert r.status_code == 200 and r.json()["ja_partilhado"] is True
        assert len(_processo(db)["partner_companies"]) == 2

    def test_os_destinos_oferecidos_excluem_a_rede_de_quem_partilha_e_a_dona(self, cliente_http):
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador(CRIS)
        r = c.get("/processes/p-domus/share-targets")
        assert r.status_code == 200, r.text
        redes = {d["network_id"] for d in r.json()["destinos"]}
        assert REDE_INCUMBENTE not in redes and REDE_DOMUS not in redes
        assert OMEGA_REDE in redes

    def test_quem_nao_ve_o_processo_continua_a_receber_404(self, cliente_http):
        c, db = cliente_http
        c.definir_utilizador(CRIS)  # a Precision ainda NÃO foi convidada
        r = c.post("/processes/p-domus/partners", json={"network_id": OMEGA_REDE})
        assert r.status_code == 404

    def test_o_consultor_convidado_continua_sem_poder_partilhar(self, cliente_http):
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador({"id": "u-cons", "role": "consultor", "effective_role": "consultor"})
        db.user_company_roles.docs.append(
            {"user_id": "u-cons", "company_id": "cmp-precision", "company_name": "Precision Crédito",
             "role": "consultor", "is_default": True})
        r = c.post("/processes/p-domus/partners", json={"network_id": OMEGA_REDE})
        assert r.status_code == 403

    def test_depth_conta_a_distancia_da_casa_dona_numa_cadeia_de_tres(self):
        registo = [_elo("rede-z", "Z", de="rede-y", depth=1)]
        assert ps.profundidade_do_elo(registo, "rede-y", "rede-y") == 1
        assert ps.profundidade_do_elo(registo, "rede-z", "rede-y") == 2
        # Quem partilha não está no registo (um Master a agir por uma rede): nunca nível 1.
        assert ps.profundidade_do_elo(registo, "rede-fantasma", "rede-y") == 2


# ====================================================================
# 4. Revogar: cascata e posse do elo
# ====================================================================

CADEIA = [
    _elo("rede-z", "Empresa Z", de="rede-y", depth=1, company_id="cmp-z"),
    _elo("rede-w", "Empresa W", de="rede-z", depth=2, company_id="cmp-w", em="2026-10-02T10:00:00+00:00"),
    _elo("rede-k", "Empresa K", de="rede-y", depth=1, company_id="cmp-k", em="2026-10-03T10:00:00+00:00"),
]


class TestRevogarEmCadeia:
    @pytest.mark.asyncio
    async def test_revogar_um_elo_revoga_os_que_dele_derivam(self, fake_async_db):
        fake_async_db.processes.docs.append({
            "id": "p-1", "network_id": "rede-y",
            "partner_companies": [dict(e) for e in CADEIA],
            "partner_network_ids": ["rede-z", "rede-w", "rede-k"],
        })
        with patch.object(ps, "db", fake_async_db), \
                patch("services.audit_trail_service.log_audit_event", AsyncMock()):
            retiradas = await ps.revogar_parceiro("p-1", company_id="cmp-z")
        assert {r["company_id"] for r in retiradas} == {"cmp-z", "cmp-w"}
        processo = fake_async_db.processes.docs[0]
        # O ramo K, irmão, fica; a W, descendente da Z, vai com ela.
        assert [e["company_id"] for e in processo["partner_companies"]] == ["cmp-k"]
        assert processo["partner_network_ids"] == ["rede-k"]

    @pytest.mark.asyncio
    async def test_revogar_uma_folha_nao_toca_nos_outros(self, fake_async_db):
        fake_async_db.processes.docs.append({
            "id": "p-1", "network_id": "rede-y", "partner_companies": [dict(e) for e in CADEIA],
            "partner_network_ids": ["rede-z", "rede-w", "rede-k"],
        })
        with patch.object(ps, "db", fake_async_db), \
                patch("services.audit_trail_service.log_audit_event", AsyncMock()):
            retiradas = await ps.revogar_parceiro("p-1", company_id="cmp-w")
        assert [r["company_id"] for r in retiradas] == ["cmp-w"]
        assert {e["company_id"] for e in fake_async_db.processes.docs[0]["partner_companies"]} == {"cmp-z", "cmp-k"}

    @pytest.mark.asyncio
    async def test_a_cascata_apanha_varios_niveis(self, fake_async_db):
        registo = [
            _elo("a", "A", de="rede-y", company_id="cmp-a"),
            _elo("b", "B", de="a", depth=2, company_id="cmp-b"),
            _elo("c", "C", de="b", depth=3, company_id="cmp-c"),
        ]
        fake_async_db.processes.docs.append({
            "id": "p-1", "network_id": "rede-y", "partner_companies": registo,
            "partner_network_ids": ["a", "b", "c"],
        })
        with patch.object(ps, "db", fake_async_db), \
                patch("services.audit_trail_service.log_audit_event", AsyncMock()):
            retiradas = await ps.revogar_parceiro("p-1", company_id="cmp-a")
        assert {r["company_id"] for r in retiradas} == {"cmp-a", "cmp-b", "cmp-c"}
        assert fake_async_db.processes.docs[0]["partner_network_ids"] == []

    def test_elo_e_meu_sobe_a_cadeia(self):
        # Eu sou a rede-z: abri a W; a K é irmã (da Y) e a Z veio da casa dona.
        registo = CADEIA
        minhas = {"rede-z"}
        por = {e["company_id"]: e for e in registo}
        assert ps.elo_e_meu(registo, por["cmp-w"], minhas, "rede-y") is True
        assert ps.elo_e_meu(registo, por["cmp-k"], minhas, "rede-y") is False
        assert ps.elo_e_meu(registo, por["cmp-z"], minhas, "rede-y") is False

    def test_elo_e_meu_descendentes_de_um_elo_meu_tambem_sao_meus(self):
        registo = [
            _elo("a", "A", de="rede-y", company_id="cmp-a"),
            _elo("b", "B", de="a", depth=2, company_id="cmp-b"),
            _elo("c", "C", de="b", depth=3, company_id="cmp-c"),
        ]
        por = {e["company_id"]: e for e in registo}
        assert ps.elo_e_meu(registo, por["cmp-c"], {"a"}, "rede-y") is True

    def test_a_casa_dona_nunca_conta_como_origem_propria_de_uma_convidada(self):
        registo = [_elo("rede-z", "Z", company_id="cmp-z")]  # entrada antiga: veio da dona
        assert ps.elo_e_meu(registo, registo[0], {"rede-z"}, "rede-y") is False

    def test_elo_e_meu_resiste_a_ciclos(self):
        registo = [_elo("a", "A", de="b", company_id="cmp-a"), _elo("b", "B", de="a", company_id="cmp-b")]
        assert ps.elo_e_meu(registo, registo[0], {"outra"}, "rede-y") is False


class TestRevogarPelaRota:
    def _cadeia_domus_precision_omega(self, c, db):
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador(CRIS)
        c.post("/processes/p-domus/partners", json={"network_id": OMEGA_REDE})

    def test_a_casa_dona_retira_o_elo_e_a_cascata_leva_a_omega(self, cliente_http):
        c, db = cliente_http
        self._cadeia_domus_precision_omega(c, db)
        c.definir_utilizador(BRUNO)
        r = c.delete("/processes/p-domus/partners/cmp-power")
        assert r.status_code == 200, r.text
        assert _processo(db)["partner_companies"] == []
        assert _processo(db)["partner_network_ids"] == []

    def test_a_convidada_retira_o_elo_que_abriu(self, cliente_http):
        c, db = cliente_http
        self._cadeia_domus_precision_omega(c, db)
        r = c.delete("/processes/p-domus/partners/cmp-omega")
        assert r.status_code == 200, r.text
        assert [e["network_id"] for e in _processo(db)["partner_companies"]] == [REDE_INCUMBENTE]

    def test_a_convidada_nao_retira_o_elo_da_casa_dona(self, cliente_http):
        c, db = cliente_http
        self._cadeia_domus_precision_omega(c, db)
        # A Precision tenta retirar-se a si própria (o elo foi aberto pela Domus).
        r = c.delete("/processes/p-domus/partners/cmp-power")
        assert r.status_code == 403, r.text
        assert len(_processo(db)["partner_companies"]) == 2

    def test_a_convidada_nao_retira_um_elo_alheio_irmao(self, cliente_http):
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.post("/processes/p-domus/partners", json={"network_id": OMEGA_REDE})  # aberto pela Domus
        c.definir_utilizador(CRIS)
        r = c.delete("/processes/p-domus/partners/cmp-omega")
        assert r.status_code == 403
        assert len(_processo(db)["partner_companies"]) == 2

    def test_empresa_que_nao_e_parceira_e_404(self, cliente_http):
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador(CRIS)
        assert c.delete("/processes/p-domus/partners/cmp-inexistente").status_code == 404

    def test_quem_nao_ve_o_processo_continua_a_receber_404(self, cliente_http):
        c, db = cliente_http
        c.definir_utilizador(CRIS)
        assert c.delete("/processes/p-domus/partners/cmp-power").status_code == 404

    def test_consultor_nao_revoga(self, cliente_http):
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador(DINA)
        assert c.delete("/processes/p-domus/partners/cmp-power").status_code == 403


# ====================================================================
# 5. O detalhe do processo leva a linhagem (e o que cada um pode retirar)
# ====================================================================

class TestADetalheLevaALinhagem:
    @pytest.mark.asyncio
    async def test_a_empresa_z_ve_toda_a_linhagem(self, cliente_http):
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador(CRIS)
        c.post("/processes/p-domus/partners", json={"network_id": OMEGA_REDE})
        processo = dict(_processo(db))
        processo["assigned_parceiro_id"] = "par-1"
        processo["parceiro_name"] = "João Angariador"

        # Quem vê o processo a partir da Omega (a ÚLTIMA empresa da cadeia).
        db.user_company_roles.docs.append(
            {"user_id": "u-omega", "company_id": "cmp-omega", "company_name": "Omega Crédito",
             "role": "diretor", "is_default": True})
        import services.tenant_network as tn

        with patch.object(tn, "db", db), patch("database.db", db):
            await lin.anexar_linhagem(processo, {"id": "u-omega", "role": "diretor"}, casa_dona="Domus")

        caminho = processo["linhagem"]["caminhos"][0]
        assert [n["nome"] for n in caminho][0] == "João Angariador"
        assert [n["nome"] for n in caminho][1] == "Domus"
        assert len(caminho) == 4  # parceiro, Domus, Power/Precision, Omega
        assert processo["linhagem"]["empresa_actual"] == ["Omega Crédito"]

    @pytest.mark.asyncio
    async def test_cada_um_so_ve_o_botao_dos_elos_que_pode_retirar(self, cliente_http):
        c, db = cliente_http
        c.post("/processes/p-domus/partners", json={"network_id": REDE_INCUMBENTE})
        c.definir_utilizador(CRIS)
        c.post("/processes/p-domus/partners", json={"network_id": OMEGA_REDE})
        import services.tenant_network as tn

        async def para(utilizador):
            processo = dict(_processo(db))
            with patch.object(tn, "db", db), patch("database.db", db):
                await lin.anexar_linhagem(processo, utilizador, casa_dona="Domus")
            return {p["network_id"]: p["pode_revogar"] for p in processo["linhagem"]["partilhas"]}

        assert await para(BRUNO) == {REDE_INCUMBENTE: True, OMEGA_REDE: True}  # a casa dona
        assert await para(CRIS) == {REDE_INCUMBENTE: False, OMEGA_REDE: True}  # só o que abriu

    @pytest.mark.asyncio
    async def test_falhar_a_linhagem_nao_estraga_o_detalhe(self):
        processo = {"id": "p-1"}
        with patch("services.tenant_network.resolve_tenant_scope", AsyncMock(side_effect=RuntimeError("x"))):
            await lin.anexar_linhagem(processo, {"id": "u"})
        assert processo["linhagem"] is None

    def test_o_detalhe_do_processo_chama_a_linhagem(self):
        from services import process_detail
        from tests.unit.helpers_fonte import codigo_da_funcao_sem_comentarios

        corpo = codigo_da_funcao_sem_comentarios(process_detail.run_get_process_detail)
        assert "anexar_linhagem(" in corpo


# ====================================================================
# 6. Parceiros nunca recebem tarefas
# ====================================================================

class TestParceirosNaoTemTarefas:
    @pytest.mark.asyncio
    async def test_um_utilizador_de_papel_parceiro_e_recusado(self, fake_async_db):
        from services.task_assignment_hygiene import (
            DETALHE_PARCEIRO_SEM_TAREFAS,
            exigir_responsaveis_atribuiveis,
        )

        fake_async_db.users.docs.append({"id": "u-par", "role": "parceiro"})
        with pytest.raises(HTTPException) as erro:
            await exigir_responsaveis_atribuiveis(["u-par"], base=fake_async_db)
        assert erro.value.status_code == 400
        assert erro.value.detail == DETALHE_PARCEIRO_SEM_TAREFAS

    @pytest.mark.asyncio
    async def test_uma_conta_do_portal_do_parceiro_tambem(self, fake_async_db):
        from services.task_assignment_hygiene import exigir_responsaveis_atribuiveis

        fake_async_db.partners.docs.append({"id": "par-1", "name": "João"})
        with pytest.raises(HTTPException):
            await exigir_responsaveis_atribuiveis("par-1", base=fake_async_db)

    @pytest.mark.asyncio
    async def test_um_cliente_nao_e_um_responsavel(self, fake_async_db):
        from services.task_assignment_hygiene import exigir_responsaveis_atribuiveis

        fake_async_db.users.docs.append({"id": "u-cli", "role": "cliente"})
        with pytest.raises(HTTPException):
            await exigir_responsaveis_atribuiveis(["u-cli"], base=fake_async_db)

    @pytest.mark.asyncio
    async def test_um_so_parceiro_numa_lista_de_staff_recusa_a_lista_toda(self, fake_async_db):
        from services.task_assignment_hygiene import exigir_responsaveis_atribuiveis

        fake_async_db.users.docs.extend([
            {"id": "u-1", "role": "consultor"}, {"id": "u-par", "role": "parceiro"},
        ])
        with pytest.raises(HTTPException):
            await exigir_responsaveis_atribuiveis(["u-1", "u-par"], base=fake_async_db)

    @pytest.mark.asyncio
    @pytest.mark.parametrize("papel", ["consultor", "intermediario", "diretor", "ceo", "indexacao",
                                       "administrativo", "admin"])
    async def test_o_staff_continua_a_poder(self, fake_async_db, papel):
        # Não pode regredir: só parceiros e clientes saem. Um admin com tarefas continua a ser possível.
        from services.task_assignment_hygiene import exigir_responsaveis_atribuiveis

        fake_async_db.users.docs.append({"id": "u-x", "role": papel})
        await exigir_responsaveis_atribuiveis(["u-x"], base=fake_async_db)

    @pytest.mark.asyncio
    async def test_sem_responsaveis_nao_faz_perguntas_a_base(self, fake_async_db):
        from services.task_assignment_hygiene import exigir_responsaveis_atribuiveis

        await exigir_responsaveis_atribuiveis([], base=None)
        await exigir_responsaveis_atribuiveis(None, base=None)

    @pytest.mark.asyncio
    async def test_criar_a_tarefa_recusa_antes_de_escrever(self, fake_async_db):
        from models.task import TaskCreate
        from services import task_api_crud as crud

        fake_async_db.users.docs.append({"id": "u-par", "role": "parceiro"})
        with patch.object(crud, "db", fake_async_db):
            with pytest.raises(HTTPException) as erro:
                await crud.run_create_task(
                    TaskCreate(title="Ligar ao cliente", assigned_to=["u-par"]),
                    {"id": "u-1", "name": "Ana", "role": "consultor"},
                )
        assert erro.value.status_code == 400
        assert await fake_async_db.tasks.count_documents({}) == 0

    @pytest.mark.asyncio
    async def test_reatribuir_a_um_parceiro_recusa_e_nao_altera_a_tarefa(self, fake_async_db):
        from models.task import TaskUpdate
        from services import task_api_crud as crud

        fake_async_db.users.docs.extend([{"id": "u-par", "role": "parceiro"}, {"id": "u-1", "role": "consultor"}])
        fake_async_db.tasks.docs.append(
            {"id": "t-1", "title": "T", "assigned_to": ["u-1"], "created_by": "u-1", "completed": False})
        with patch.object(crud, "db", fake_async_db):
            with pytest.raises(HTTPException):
                await crud.run_update_task(
                    "t-1", TaskUpdate(assigned_to=["u-1", "u-par"]),
                    {"id": "u-1", "name": "Ana", "role": "consultor"},
                )
        assert fake_async_db.tasks.docs[0]["assigned_to"] == ["u-1"]

    @pytest.mark.asyncio
    async def test_uma_tarefa_antiga_com_um_parceiro_nao_fica_impossivel_de_editar(self, fake_async_db):
        # «Só se valida o que ENTRA»: o parceiro já lá estava e não é novo.
        from models.task import TaskUpdate
        from services import task_api_crud as crud

        fake_async_db.users.docs.extend([
            {"id": "u-par", "name": "Pedro Parceiro", "role": "parceiro"},
            {"id": "u-1", "name": "Ana", "role": "consultor"},
        ])
        fake_async_db.tasks.docs.append(
            {"id": "t-1", "title": "T", "assigned_to": ["u-1", "u-par"], "created_by": "u-1",
             "completed": False, "created_at": "2026-10-01T10:00:00+00:00",
             "updated_at": "2026-10-01T10:00:00+00:00"})
        from services import task_api_helpers

        with patch.object(crud, "db", fake_async_db), patch.object(task_api_helpers, "db", fake_async_db):
            with patch.object(crud, "send_realtime_notification", AsyncMock()):
                await crud.run_update_task(
                    "t-1", TaskUpdate(assigned_to=["u-1", "u-par"], title="Novo título"),
                    {"id": "u-1", "name": "Ana", "role": "consultor"},
                )
        assert fake_async_db.tasks.docs[0]["title"] == "Novo título"

    def test_as_listas_de_atribuicao_continuam_a_excluir_o_parceiro(self):
        from services.staff_assignment import is_assignment_eligible_user

        assert not is_assignment_eligible_user({"role": "parceiro"})
        assert not is_assignment_eligible_user({"role": "parceiro", "additional_roles": ["consultor"]})
        assert is_assignment_eligible_user({"role": "consultor"})
