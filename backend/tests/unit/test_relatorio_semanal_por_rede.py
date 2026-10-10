"""
Relatório de segunda-feira: um por REDE, para a gestão dessa rede (adenda de RBAC).

O PEDIDO
  «Confirma que o e-mail automático de segunda-feira é enviado para os
  e-mails corretos da gestão local (CEO/Admin da respetiva empresa, e não
  cruzando dados). Confirma que a nova página 'Relatório Semanal' obedece a
  esta mesma barreira.»

O QUE HAVIA
  Um email CONSOLIDADO (D-7: «única excepção deliberada ao isolamento por
  rede») para `CEO_EMAIL` ou, na falta, para TODOS os utilizadores `ceo` do
  sistema. O CEO da Domus recebia os nomes e os números dos colaboradores da
  Power. A página (`/admin/executive-weekly`) já resolvia o âmbito pelo
  utilizador; o email é que não.

PORQUE É QUE ISTO TEM TESTES DE COMPORTAMENTO E NÃO SÓ DE FONTE
  «Não cruza dados» é uma propriedade do CONJUNTO (quem recebe o quê), e uma
  guarda sobre o código-fonte não a distingue de uma lista de destinatários
  partilhada. Aqui corre-se o `send_weekly_ceo_report` real com um `send_email`
  falso e afirma-se, email a email, QUEM recebeu QUE relatório.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

import pytest

from services import relatorio_semanal_agenda as agenda
from services import relatorio_semanal_destinos as destinos
from services.relatorio_semanal_destinos import (
    CHAVE_GLOBAL,
    agrupar_por_rede,
    chave_da_rede,
    destino_global,
)
from tests.unit.helpers_tenant import (  # noqa: F401  (fixture)
    REDE_DOMUS,
    REDE_INCUMBENTE,
    casa,
    rede_de_omissao_incumbente,
    semear,
    tenant_db,
)

EMPRESAS = [
    {"id": "cmp-power", "name": "Power Real Estate", "network_id": REDE_INCUMBENTE},
    {"id": "cmp-precision", "name": "Precision Crédito", "network_id": REDE_INCUMBENTE},
    {"id": "cmp-domus", "name": "Domus", "network_id": REDE_DOMUS},
]

UTILIZADORES = [
    {"id": "u-ceo-power", "name": "CEO Power", "email": "ceo@power.pt", "role": "ceo", "company": "Power Real Estate"},
    {"id": "u-adm-prec", "name": "Admin Precision", "email": "adm@precision.pt", "role": "admin", "company": "Precision Crédito"},
    {"id": "u-ceo-domus", "name": "CEO Domus", "email": "ceo@domus.pt", "role": "ceo", "company": "Domus"},
    {"id": "u-master", "name": "Master", "email": "master@x.pt", "role": "master"},
    {"id": "u-cons", "name": "Consultora", "email": "c@power.pt", "role": "consultor", "company": "Power Real Estate"},
]

ACESSOS = [
    {"user_id": "u-ceo-power", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "ceo"},
    {"user_id": "u-adm-prec", "company_id": "cmp-precision", "company_name": "Precision Crédito", "role": "admin"},
    {"user_id": "u-ceo-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "ceo"},
    {"user_id": "u-cons", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "consultor"},
]


def _por_rede(lista):
    return {d.chave: d for d in lista}


# ════════════════════════════════════════════════════════════════════
#  A DECISÃO: A QUEM VAI CADA RELATÓRIO (pura)
# ════════════════════════════════════════════════════════════════════
class TestAQuemVaiCadaRelatorio:
    def test_cada_rede_recebe_so_a_gestao_da_sua_rede(self):
        d = _por_rede(agrupar_por_rede(EMPRESAS, ACESSOS, UTILIZADORES))
        power = d[chave_da_rede(REDE_INCUMBENTE)]
        domus = d[chave_da_rede(REDE_DOMUS)]
        assert set(power.emails) == {"ceo@power.pt", "adm@precision.pt"}
        assert set(domus.emails) == {"ceo@domus.pt"}
        assert not set(power.emails) & set(domus.emails), "os destinatários das duas redes cruzam-se"

    def test_o_CEO_da_Domus_nunca_recebe_o_relatorio_da_Power(self):
        for destino in agrupar_por_rede(EMPRESAS, ACESSOS, UTILIZADORES):
            if destino.chave == chave_da_rede(REDE_INCUMBENTE):
                assert "ceo@domus.pt" not in destino.emails

    def test_o_ambito_de_cada_relatorio_e_a_sua_rede_e_nunca_global(self):
        for destino in agrupar_por_rede(EMPRESAS, ACESSOS, UTILIZADORES):
            assert destino.scope.sem_fronteira is False
            assert len(destino.scope.network_ids) == 1
        power = _por_rede(agrupar_por_rede(EMPRESAS, ACESSOS, UTILIZADORES))[chave_da_rede(REDE_INCUMBENTE)]
        assert set(power.scope.company_ids) == {"cmp-power", "cmp-precision"}
        assert "cmp-domus" not in power.scope.company_ids

    def test_Admin_e_CEO_recebem_um_consultor_nao(self):
        todos = {e for d in agrupar_por_rede(EMPRESAS, ACESSOS, UTILIZADORES) for e in d.emails}
        assert "c@power.pt" not in todos

    def test_o_master_nao_e_destinatario_de_um_relatorio_local(self):
        """O dele é o consolidado. Um Master com UCR de CEO numa empresa não
        pode receber o relatório local nem ser a porta do consolidado."""
        acessos = [*ACESSOS, {"user_id": "u-master", "company_id": "cmp-power",
                              "company_name": "Power Real Estate", "role": "ceo"}]
        todos = {e for d in agrupar_por_rede(EMPRESAS, acessos, UTILIZADORES) for e in d.emails}
        assert "master@x.pt" not in todos

    def test_quem_gere_duas_redes_recebe_dois_emails_separados(self):
        utilizadores = [*UTILIZADORES, {"id": "u-dupla", "name": "Dupla", "email": "dupla@x.pt", "role": "ceo"}]
        acessos = [*ACESSOS,
                   {"user_id": "u-dupla", "company_id": "cmp-power", "company_name": "Power Real Estate", "role": "ceo"},
                   {"user_id": "u-dupla", "company_id": "cmp-domus", "company_name": "Domus", "role": "admin"}]
        d = agrupar_por_rede(EMPRESAS, acessos, utilizadores)
        recebe = [x.chave for x in d if "dupla@x.pt" in x.emails]
        assert sorted(recebe) == sorted([chave_da_rede(REDE_INCUMBENTE), chave_da_rede(REDE_DOMUS)])

    def test_conta_antiga_sem_UCR_resolve_pelo_campo_legado_company(self):
        utilizadores = [{"id": "u-velho", "name": "Velho", "email": "velho@domus.pt",
                         "role": "ceo", "company": "Domus"}]
        d = agrupar_por_rede(EMPRESAS, [], utilizadores)
        assert [x.emails for x in d] == [["velho@domus.pt"]]
        assert d[0].chave == chave_da_rede(REDE_DOMUS)

    def test_uma_empresa_sem_rede_e_uma_ilha_com_o_seu_proprio_relatorio(self):
        empresas = [*EMPRESAS, {"id": "cmp-nova", "name": "Nova"}]
        utilizadores = [*UTILIZADORES, {"id": "u-n", "name": "N", "email": "n@nova.pt", "role": "ceo"}]
        acessos = [*ACESSOS, {"user_id": "u-n", "company_id": "cmp-nova", "company_name": "Nova", "role": "ceo"}]
        d = _por_rede(agrupar_por_rede(empresas, acessos, utilizadores))
        assert d[chave_da_rede("rede:cmp-nova")].emails == ["n@nova.pt"]
        assert "n@nova.pt" not in d[chave_da_rede(REDE_INCUMBENTE)].emails

    def test_uma_rede_sem_gestao_nao_gera_relatorio(self):
        d = agrupar_por_rede(EMPRESAS, ACESSOS[:1], UTILIZADORES[:1])
        assert [x.chave for x in d] == [chave_da_rede(REDE_INCUMBENTE)]

    def test_emails_invalidos_ou_de_parceiros_ficam_de_fora(self):
        utilizadores = [{"id": "u-x", "name": "X", "email": "parceiro_ab12@placeholder.internal",
                         "role": "ceo", "company": "Domus"},
                        {"id": "u-y", "name": "Y", "email": "", "role": "ceo", "company": "Domus"}]
        assert agrupar_por_rede(EMPRESAS, [], utilizadores) == []

    def test_a_rede_de_omissao_inclui_a_pilha_por_carimbar_so_na_rede_incumbente(self):
        d = _por_rede(agrupar_por_rede(EMPRESAS, ACESSOS, UTILIZADORES, rede_omissao=REDE_INCUMBENTE))
        assert d[chave_da_rede(REDE_INCUMBENTE)].scope.inclui_rede_de_omissao is True
        assert d[chave_da_rede(REDE_DOMUS)].scope.inclui_rede_de_omissao is False


class TestOConsolidadoEDoMaster:
    def test_so_os_master_recebem_o_consolidado(self):
        g = destino_global(UTILIZADORES)
        assert g.chave == CHAVE_GLOBAL
        assert g.emails == ["master@x.pt"]
        assert g.scope.sem_fronteira is True

    def test_um_CEO_EMAIL_que_nao_e_master_e_ignorado_e_avisado(self, caplog):
        """Era a porta pela qual o consolidado chegava a quem não devia."""
        with caplog.at_level(logging.WARNING):
            g = destino_global(UTILIZADORES, ["ceo@domus.pt", "master@x.pt"])
        assert g.emails == ["master@x.pt"]
        assert any("ceo@domus.pt" in r.message and "CEO_EMAIL" in r.message for r in caplog.records)

    def test_sem_master_nao_ha_consolidado(self):
        assert destino_global([u for u in UTILIZADORES if u["role"] != "master"]) is None

    def test_um_master_sem_email_valido_nao_recebe(self):
        assert destino_global([{"id": "m", "email": "", "role": "master"}]) is None


# ════════════════════════════════════════════════════════════════════
#  LER OS DADOS (fake de Mongo)
# ════════════════════════════════════════════════════════════════════
@pytest.mark.asyncio
class TestMontarDestinos:
    async def _mundo(self, fake_async_db, utilizadores=UTILIZADORES, acessos=ACESSOS):
        fake_async_db.companies.docs.extend(dict(e) for e in EMPRESAS)
        fake_async_db.users.docs.extend(dict(u) for u in utilizadores)
        fake_async_db.user_company_roles.docs.extend(dict(a) for a in acessos)
        return fake_async_db

    async def test_le_a_base_e_separa_por_rede(self, fake_async_db, monkeypatch):
        monkeypatch.delenv("CEO_EMAIL", raising=False)
        base = await self._mundo(fake_async_db)
        d = _por_rede(await destinos.montar_destinos(base))
        assert set(d) == {chave_da_rede(REDE_INCUMBENTE), chave_da_rede(REDE_DOMUS), CHAVE_GLOBAL}
        assert set(d[chave_da_rede(REDE_INCUMBENTE)].emails) == {"ceo@power.pt", "adm@precision.pt"}
        assert d[chave_da_rede(REDE_DOMUS)].emails == ["ceo@domus.pt"]
        assert d[CHAVE_GLOBAL].emails == ["master@x.pt"]

    async def test_um_CEO_so_com_cargo_de_consultor_numa_empresa_nao_recebe(self, fake_async_db, monkeypatch):
        """O papel que conta é o do UCR, não o da conta: quem tem `role=ceo`
        mas só um acesso de Consultor não é gestão dessa empresa. Sem esta
        regra, o campo legado `users.company` reabria a porta."""
        monkeypatch.delenv("CEO_EMAIL", raising=False)
        utilizadores = [{"id": "u-x", "name": "X", "email": "x@domus.pt", "role": "ceo", "company": "Domus"}]
        acessos = [{"user_id": "u-x", "company_id": "cmp-domus", "company_name": "Domus", "role": "consultor"}]
        base = await self._mundo(fake_async_db, utilizadores, acessos)
        assert await destinos.montar_destinos(base) == []

    async def test_empresas_inactivas_nao_geram_relatorio(self, fake_async_db, monkeypatch):
        monkeypatch.delenv("CEO_EMAIL", raising=False)
        base = await self._mundo(fake_async_db)
        next(c for c in base.companies.docs if c["id"] == "cmp-domus")["is_active"] = False
        d = _por_rede(await destinos.montar_destinos(base))
        assert chave_da_rede(REDE_DOMUS) not in d


# ════════════════════════════════════════════════════════════════════
#  O ENVIO REAL (send_email falso)
# ════════════════════════════════════════════════════════════════════
SEGUNDA_07H = datetime(2026, 10, 5, 7, 0, tzinfo=timezone.utc)


def _destino(rede, emails, nome):
    from services.tenant_network import TenantScope

    return destinos.DestinoDoRelatorio(
        chave=chave_da_rede(rede), rotulo=nome,
        scope=TenantScope(network_ids=(rede,), company_ids=(f"id-{rede}",)),
        destinatarios=[{"id": e, "name": e, "email": e} for e in emails],
    )


@pytest.fixture
def envio(fake_async_db, monkeypatch):
    """O serviço real, com email e gerador de relatório falsos."""
    from services import scheduled_tasks

    monkeypatch.setattr(agenda, "db", fake_async_db)
    emails_enviados: list[dict] = []
    ambitos_usados: list = []

    async def enviar(**kwargs):
        emails_enviados.append(kwargs)
        return {"success": kwargs["to_emails"] != ["falha@x.pt"]}

    async def gerar(db, period_start=None, period_end=None, user=None, user_ids=None, papeis=None, scope=None):
        ambitos_usados.append(scope)
        return {
            "period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
            "summary": {}, "users": [],
        }

    svc = scheduled_tasks.ScheduledTasksService()
    svc.db = fake_async_db
    return svc, emails_enviados, ambitos_usados, enviar, gerar


@pytest.mark.asyncio
class TestOEnvioRealNaoCruzaDados:
    async def _correr(self, envio, lista, *, forcado=True):
        svc, enviados, ambitos, enviar, gerar = envio
        with patch.object(destinos, "montar_destinos", AsyncMock(return_value=lista)), \
             patch("services.email_service.send_email", enviar), \
             patch("services.analytics_service.generate_weekly_team_report", gerar), \
             patch("services.analytics_service.format_report_html", lambda r: "<html/>"):
            return await svc.send_weekly_ceo_report(forcado=forcado)

    async def test_cada_email_vai_so_para_a_gestao_da_sua_rede(self, envio):
        lista = [
            _destino(REDE_INCUMBENTE, ["ceo@power.pt", "adm@precision.pt"], "Power + Precision"),
            _destino(REDE_DOMUS, ["ceo@domus.pt"], "Domus"),
        ]
        assert await self._correr(envio, lista) is True
        _, enviados, ambitos, _, _ = envio
        por_assunto = {tuple(sorted(e["to_emails"])): e["subject"] for e in enviados}
        assert set(por_assunto) == {("adm@precision.pt", "ceo@power.pt"), ("ceo@domus.pt",)}
        assert "Domus" in por_assunto[("ceo@domus.pt",)]
        assert "Domus" not in por_assunto[("adm@precision.pt", "ceo@power.pt")]
        todos = [a for e in enviados for a in e["to_emails"]]
        assert len(todos) == len(set(todos)), "o mesmo endereço recebeu dois relatórios"

    async def test_cada_relatorio_e_gerado_com_o_ambito_da_SUA_rede(self, envio):
        lista = [
            _destino(REDE_INCUMBENTE, ["ceo@power.pt"], "Power"),
            _destino(REDE_DOMUS, ["ceo@domus.pt"], "Domus"),
        ]
        await self._correr(envio, lista)
        _, _, ambitos, _, _ = envio
        redes = sorted(a.network_ids[0] for a in ambitos)
        assert redes == sorted([REDE_INCUMBENTE, REDE_DOMUS])
        assert all(a.sem_fronteira is False for a in ambitos), "um relatório local saiu com âmbito global"

    async def test_so_o_destino_global_e_gerado_sem_fronteira(self, envio):
        from services.tenant_network import TenantScope

        g = destinos.DestinoDoRelatorio(
            chave=CHAVE_GLOBAL, rotulo="Consolidado",
            scope=TenantScope(inclui_rede_de_omissao=True, sem_fronteira=True),
            destinatarios=[{"id": "m", "name": "m", "email": "master@x.pt"}],
        )
        await self._correr(envio, [g])
        _, enviados, ambitos, _, _ = envio
        assert enviados[0]["to_emails"] == ["master@x.pt"]
        assert ambitos[0].sem_fronteira is True

    async def test_a_falha_de_uma_rede_nao_marca_essa_rede_e_a_proxima_volta_so_a_ela(self, envio, fake_async_db):
        lista = [
            _destino(REDE_INCUMBENTE, ["ceo@power.pt"], "Power"),
            _destino(REDE_DOMUS, ["falha@x.pt"], "Domus"),
        ]
        assert await self._correr(envio, lista) is True
        marcas = {m["chave"] for m in fake_async_db[agenda.COLECCAO].docs}
        assert chave_da_rede(REDE_INCUMBENTE) in marcas
        assert chave_da_rede(REDE_DOMUS) not in marcas, "marcou como enviado um envio que falhou"

        _, enviados, _, _, _ = envio
        antes = len(enviados)
        await self._correr(envio, lista)
        novos = [e["to_emails"] for e in enviados[antes:]]
        assert novos == [["falha@x.pt"]], "voltou a mandar à rede que já tinha o relatório"

    async def test_uma_excepcao_numa_rede_nao_impede_as_outras(self, envio):
        svc, enviados, ambitos, enviar, _ = envio

        async def gerar_com_falha(db, period_start=None, period_end=None, user=None, user_ids=None,
                                  papeis=None, scope=None):
            if scope is not None and scope.network_ids == (REDE_DOMUS,):
                raise RuntimeError("Mongo")
            return {"period_start": period_start.isoformat(), "period_end": period_end.isoformat(),
                    "summary": {}, "users": []}

        lista = [_destino(REDE_DOMUS, ["ceo@domus.pt"], "Domus"),
                 _destino(REDE_INCUMBENTE, ["ceo@power.pt"], "Power")]
        with patch.object(destinos, "montar_destinos", AsyncMock(return_value=lista)), \
             patch("services.email_service.send_email", enviar), \
             patch("services.analytics_service.generate_weekly_team_report", gerar_com_falha), \
             patch("services.analytics_service.format_report_html", lambda r: "<html/>"):
            assert await svc.send_weekly_ceo_report(forcado=True) is True
        assert [e["to_emails"] for e in enviados] == [["ceo@power.pt"]]

    async def test_fora_da_janela_nao_envia_nada(self, envio):
        """A janela é fixada, não lida do relógio: o teste não pode passar a
        enviar emails numa segunda-feira de manhã."""
        lista = [_destino(REDE_DOMUS, ["ceo@domus.pt"], "Domus")]
        with patch.object(agenda, "esta_na_janela", return_value=False):
            assert await self._correr(envio, lista, forcado=False) is False
        assert envio[1] == []

    async def test_sem_destinos_nao_envia_e_nao_rebenta(self, envio):
        assert await self._correr(envio, []) is False
        assert envio[1] == []

    async def test_o_ciclo_horario_seguinte_nao_repete_o_que_ja_saiu(self, envio):
        lista = [_destino(REDE_DOMUS, ["ceo@domus.pt"], "Domus")]
        assert await self._correr(envio, lista) is True
        assert await self._correr(envio, lista) is False
        assert len(envio[1]) == 1


# ════════════════════════════════════════════════════════════════════
#  A PÁGINA «RELATÓRIO SEMANAL» (mesma barreira)
# ════════════════════════════════════════════════════════════════════
CEO_POWER = {"id": "u-ceo-power", "name": "CEO Power", "email": "ceo@power.pt", "role": "ceo", "effective_role": "ceo"}
CEO_DOMUS = {"id": "u-ceo-domus", "name": "CEO Domus", "email": "ceo@domus.pt", "role": "ceo", "effective_role": "ceo"}
ADMIN_PREC = {"id": "u-adm-prec", "name": "Admin Precision", "email": "adm@precision.pt", "role": "admin", "effective_role": "admin"}
MASTER = {"id": "u-master", "name": "Master", "email": "master@x.pt", "role": "master", "effective_role": "master"}


@pytest.fixture
def mundo_pagina(fake_async_db, rede_de_omissao_incumbente):
    semear(fake_async_db)
    fake_async_db.user_company_roles.docs.extend(dict(a) for a in ACESSOS)
    fake_async_db.users.docs.extend(dict(u) for u in UTILIZADORES)
    fake_async_db.users.docs.extend([
        {"id": "u-cons-domus", "name": "Cons Domus", "email": "cd@domus.pt", "role": "consultor", "company": "Domus"},
    ])
    fake_async_db.user_company_roles.docs.append(
        {"user_id": "u-cons-domus", "company_id": "cmp-domus", "company_name": "Domus", "role": "consultor"})
    return fake_async_db


@pytest.mark.asyncio
class TestAPaginaObedeceAMesmaBarreira:
    async def _ambito(self, mundo, user):
        import services.admin_users_scope as scope_mod
        from services import executive_report as er

        with tenant_db(mundo, scope_mod):
            return await er.resolver_ambito(user)

    async def _pessoas(self, mundo, ambito):
        return {u["id"] for u in mundo.users.docs if casa(u, ambito.consulta_de_utilizadores)} \
            if ambito.consulta_de_utilizadores else {u["id"] for u in mundo.users.docs}

    async def test_o_CEO_da_Domus_so_tem_pessoas_da_Domus_no_relatorio(self, mundo_pagina):
        ambito = await self._ambito(mundo_pagina, CEO_DOMUS)
        pessoas = await self._pessoas(mundo_pagina, ambito)
        assert "u-cons-domus" in pessoas and "u-ceo-domus" in pessoas
        assert not pessoas & {"u-ceo-power", "u-cons", "u-adm-prec"}, "colaboradores da Power no relatório da Domus"

    async def test_o_Admin_da_Precision_so_tem_pessoas_da_rede_Power_Precision(self, mundo_pagina):
        ambito = await self._ambito(mundo_pagina, ADMIN_PREC)
        pessoas = await self._pessoas(mundo_pagina, ambito)
        assert {"u-ceo-power", "u-adm-prec", "u-cons"} <= pessoas
        assert not pessoas & {"u-ceo-domus", "u-cons-domus"}

    async def test_o_CEO_da_Power_e_o_Admin_da_Precision_veem_as_mesmas_pessoas(self, mundo_pagina):
        """Mesma rede → a gestão da rede vê o mesmo relatório (a rede é a
        fronteira de dados; a empresa só decide a vista)."""
        a = await self._ambito(mundo_pagina, CEO_POWER)
        b = await self._ambito(mundo_pagina, ADMIN_PREC)
        assert await self._pessoas(mundo_pagina, a) == await self._pessoas(mundo_pagina, b)

    async def test_redes_diferentes_nunca_partilham_o_registo_nem_a_cache(self, mundo_pagina):
        a = await self._ambito(mundo_pagina, CEO_POWER)
        b = await self._ambito(mundo_pagina, CEO_DOMUS)
        assert a.chave != b.chave

    async def test_o_master_tem_o_consolidado_e_a_sua_chave_e_propria(self, mundo_pagina):
        m = await self._ambito(mundo_pagina, MASTER)
        assert m.consulta_de_utilizadores == {}
        assert m.chave not in {(await self._ambito(mundo_pagina, u)).chave for u in (CEO_POWER, CEO_DOMUS)}

    async def test_os_movimentos_da_pagina_filtram_pelos_processos_do_ambito(self, mundo_pagina):
        from services.tenant_network import processo_no_ambito

        ambito = await self._ambito(mundo_pagina, CEO_DOMUS)
        assert processo_no_ambito({"id": "x", "network_id": REDE_DOMUS}, ambito.scope)
        assert not processo_no_ambito({"id": "y", "network_id": REDE_INCUMBENTE}, ambito.scope)

    def test_a_pagina_so_resolve_o_ambito_pelo_utilizador_autenticado(self):
        """Nenhum handler de relatório aceita um `company_id`/`scope` do pedido."""
        import ast
        from pathlib import Path

        fonte = (Path(__file__).resolve().parents[2] / "services" / "executive_report_api.py").read_text(encoding="utf-8")
        arvore = ast.parse(fonte)
        for no in ast.walk(arvore):
            if isinstance(no, ast.AsyncFunctionDef) and no.name.startswith("run_"):
                nomes = {a.arg for a in no.args.args + no.args.kwonlyargs}
                assert not nomes & {"company_id", "network_id", "scope", "redes"}, (
                    f"{no.name} aceita um âmbito vindo do pedido: {nomes}"
                )
                assert "user" in nomes, no.name
