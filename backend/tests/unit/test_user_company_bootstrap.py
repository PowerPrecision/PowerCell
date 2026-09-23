"""
Atribuição Rápida — conta e acessos no mesmo acto (Lote 4, ponto 11).

O DEFEITO
  `run_create_user` gravava o utilizador e NUNCA criava um UCR. Escrevia
  `user_doc["company"] = data.company` — que é o NOME da empresa, não o
  `company_id` — e o formulário nem esse campo enviava: o payload do
  `UserCreateDialog` era `{name, email, phone, role, password}`. O próprio
  diálogo assumia-o na descrição: "Os acessos por empresa (UCR)
  definem-se depois em Gerir Acessos."

  Resultado: uma conta que existe e não pertence a lado nenhum. Como TUDO
  lê UCRs — ContextSwitcher, `get_effective_role_async`, config de email
  por empresa e, desde o ponto 10, o isolamento por rede —, entre o
  "Criar" e o "Gerir Acessos" o utilizador era um órfão. Ser apanhado
  pela rede de omissão não é pertencer a uma empresa.

REGRA DE NEGÓCIO (decidida pelo dono)
  A empresa é ESTRITAMENTE obrigatória na criação. A excepção são os
  parceiros, que são contas fantasma sem acesso à plataforma.

E PORQUE É QUE ISTO É ATÓMICO
  Fazer as duas chamadas a partir do frontend produziria exactamente o
  mesmo buraco quando a segunda falhasse — só que mais difícil de ver.
"""
from unittest.mock import patch

import pytest
from fastapi import HTTPException


POWER = {"company_id": "cmp-power", "company_name": "Power Real Estate"}
PRECISION = {"company_id": "cmp-precision", "company_name": "Precision Crédito"}


class TestNormalizacaoDosAcessos:
    def test_herda_o_perfil_principal_quando_a_linha_nao_traz_cargo(self):
        from services.user_company_bootstrap import normalizar_acessos

        acessos = normalizar_acessos([POWER], papel_principal="consultor")
        assert acessos[0]["role"] == "consultor"

    def test_cargo_explicito_vence_o_perfil_principal(self):
        """É o caso de uso do enunciado: Consultor numa empresa,
        Intermediário noutra."""
        from services.user_company_bootstrap import normalizar_acessos

        acessos = normalizar_acessos(
            [POWER, {**PRECISION, "role": "intermediario"}],
            papel_principal="consultor",
        )
        assert [a["role"] for a in acessos] == ["consultor", "intermediario"]

    def test_o_primeiro_acesso_fica_por_omissao(self):
        """Sem `is_default`, o login não sabe que empresa carregar."""
        from services.user_company_bootstrap import normalizar_acessos

        acessos = normalizar_acessos([POWER, PRECISION], papel_principal="consultor")
        assert [a["is_default"] for a in acessos] == [True, False]

    def test_so_um_acesso_pode_ser_o_de_omissao(self):
        from services.user_company_bootstrap import normalizar_acessos

        acessos = normalizar_acessos(
            [{**POWER, "is_default": True}, {**PRECISION, "is_default": True}],
            papel_principal="consultor",
        )
        assert sum(1 for a in acessos if a["is_default"]) == 1

    def test_respeita_o_default_escolhido_mesmo_nao_sendo_o_primeiro(self):
        from services.user_company_bootstrap import normalizar_acessos

        acessos = normalizar_acessos(
            [POWER, {**PRECISION, "is_default": True}], papel_principal="consultor",
        )
        assert acessos[0]["is_default"] is False
        assert acessos[1]["is_default"] is True

    def test_descarta_linhas_sem_empresa(self):
        from services.user_company_bootstrap import normalizar_acessos

        acessos = normalizar_acessos(
            [POWER, {"company_id": "  "}, {"company_name": ""}],
            papel_principal="consultor",
        )
        assert len(acessos) == 1

    def test_o_sentinel_default_nao_e_uma_empresa(self):
        """`"default"` é o sentinel de "sem empresa" (ver auth.py). Aceitá-lo
        aqui criaria um UCR que aponta para nada e daria o órfão por
        resolvido."""
        from services.user_company_bootstrap import normalizar_acessos

        assert normalizar_acessos(
            [{"company_id": "default"}], papel_principal="consultor",
        ) == []

    def test_a_mesma_empresa_com_o_mesmo_cargo_nao_duplica(self):
        """O índice composto de `user_company_roles` é único; duas linhas
        iguais fariam a criação rebentar a meio, depois de a conta existir."""
        from services.user_company_bootstrap import normalizar_acessos

        acessos = normalizar_acessos([POWER, dict(POWER)], papel_principal="consultor")
        assert len(acessos) == 1

    def test_a_mesma_empresa_com_cargos_diferentes_e_legitima(self):
        """Diretor E Consultor na mesma empresa é um caso suportado
        (ver models/user_company_role.py, Pacote EA)."""
        from services.user_company_bootstrap import normalizar_acessos

        acessos = normalizar_acessos(
            [{**POWER, "role": "diretor"}, {**POWER, "role": "consultor"}],
            papel_principal="consultor",
        )
        assert len(acessos) == 2

    def test_cargo_invalido_e_recusado(self):
        from services.user_company_bootstrap import normalizar_acessos

        with pytest.raises(HTTPException) as erro:
            normalizar_acessos(
                [{**POWER, "role": "presidente"}], papel_principal="consultor",
            )
        assert erro.value.status_code == 400


class TestEmpresaObrigatoria:
    def test_sem_empresa_recusa_a_criacao(self):
        from services.user_company_bootstrap import assert_acessos_obrigatorios

        with pytest.raises(HTTPException) as erro:
            assert_acessos_obrigatorios("consultor", [])
        assert erro.value.status_code == 400
        assert "empresa" in str(erro.value.detail).lower()

    def test_parceiro_e_a_excepcao(self):
        """Parceiros são contas fantasma sem acesso à plataforma — não têm
        empresa onde trabalhar."""
        from services.user_company_bootstrap import assert_acessos_obrigatorios

        assert_acessos_obrigatorios("parceiro", [])

    def test_com_empresa_passa(self):
        from services.user_company_bootstrap import assert_acessos_obrigatorios

        assert_acessos_obrigatorios("consultor", [{"company_id": "cmp-power"}])


class TestCriacaoAtomica:
    @pytest.mark.asyncio
    async def test_grava_um_ucr_por_acesso(self, fake_async_db):
        import services.user_company_bootstrap as bootstrap

        acessos = bootstrap.normalizar_acessos(
            [POWER, {**PRECISION, "role": "intermediario"}],
            papel_principal="consultor",
        )
        with patch.object(bootstrap, "db", fake_async_db):
            await bootstrap.criar_acessos_iniciais("u-novo", acessos)

        gravados = fake_async_db.user_company_roles.docs
        assert len(gravados) == 2
        assert {g["company_id"] for g in gravados} == {"cmp-power", "cmp-precision"}
        assert all(g["user_id"] == "u-novo" for g in gravados)
        assert all(g.get("id") for g in gravados), "UCR sem id não é editável depois"

    @pytest.mark.asyncio
    async def test_completa_o_nome_da_empresa_a_partir_da_coleccao(self, fake_async_db):
        """O frontend envia o id; o `company_name` é denormalizado e usado
        por `_find_ucr` para casar por nome. Gravá-lo vazio parte a
        resolução de perfil de quem mandou só o id."""
        import services.user_company_bootstrap as bootstrap

        fake_async_db.companies.docs.append(
            {"id": "cmp-power", "name": "Power Real Estate"},
        )
        acessos = bootstrap.normalizar_acessos(
            [{"company_id": "cmp-power"}], papel_principal="consultor",
        )
        with patch.object(bootstrap, "db", fake_async_db):
            await bootstrap.criar_acessos_iniciais("u-novo", acessos)

        assert fake_async_db.user_company_roles.docs[0]["company_name"] == "Power Real Estate"


class TestCriacaoDeUtilizador:
    @pytest.mark.asyncio
    async def test_utilizador_novo_nasce_com_acessos(self, fake_async_db):
        from models.auth import UserCreate
        import services.admin_users as admin_users
        import services.user_company_bootstrap as bootstrap

        fake_async_db.companies.docs.append(
            {"id": "cmp-power", "name": "Power Real Estate"},
        )
        dados = UserCreate(
            email="nova@power.pt", password="Segura123!", name="Nova Pessoa",
            role="consultor", companies=[{"company_id": "cmp-power"}],
        )

        # `send_email` é importado DENTRO da função, por isso o patch
        # tem de ser no módulo de origem — senão o teste tenta um envio
        # SMTP a sério (foi o que fez esta bateria demorar 31s).
        import services.email_service as email_service

        with patch.object(admin_users, "db", fake_async_db), \
             patch.object(bootstrap, "db", fake_async_db), \
             patch.object(email_service, "send_email", _envio_falso), \
             patch.object(admin_users, "_audit_log", _sem_efeito):
            await admin_users.run_create_user(dados, {"id": "u-admin", "name": "Admin"})

        assert len(fake_async_db.users.docs) == 1
        assert len(fake_async_db.user_company_roles.docs) == 1
        criado = fake_async_db.users.docs[0]
        # O campo legado continua preenchido: `_find_ucr` e várias
        # listagens ainda casam por NOME de empresa.
        assert criado["company"] == "Power Real Estate"

    @pytest.mark.asyncio
    async def test_sem_empresa_nao_chega_a_criar_a_conta(self, fake_async_db):
        """A recusa tem de vir ANTES do insert. Criar e depois rejeitar
        deixaria a conta órfã que isto existe para evitar."""
        from models.auth import UserCreate
        import services.admin_users as admin_users

        dados = UserCreate(
            email="nova@power.pt", password="Segura123!", name="Nova Pessoa",
            role="consultor",
        )

        with patch.object(admin_users, "db", fake_async_db):
            with pytest.raises(HTTPException) as erro:
                await admin_users.run_create_user(dados, {"id": "u-admin"})

        assert erro.value.status_code == 400
        assert fake_async_db.users.docs == []

    @pytest.mark.asyncio
    async def test_parceiro_continua_a_poder_nascer_sem_empresa(self, fake_async_db):
        from models.auth import UserCreate
        import services.admin_users as admin_users

        dados = UserCreate(name="Notário Silva", role="parceiro")

        with patch.object(admin_users, "db", fake_async_db), \
             patch.object(admin_users, "_audit_log", _sem_efeito):
            await admin_users.run_create_user(dados, {"id": "u-admin"})

        assert len(fake_async_db.users.docs) == 1
        assert fake_async_db.user_company_roles.docs == []

    @pytest.mark.asyncio
    async def test_falha_a_gravar_acessos_desfaz_a_conta(self, fake_async_db):
        """Atomicidade: meia criação é exactamente o estado que este ponto
        existe para eliminar. Sem conta, o admin repete; com conta e sem
        acessos, ninguém dá por isso."""
        from models.auth import UserCreate
        import services.admin_users as admin_users
        import services.user_company_bootstrap as bootstrap

        dados = UserCreate(
            email="nova@power.pt", password="Segura123!", name="Nova Pessoa",
            role="consultor", companies=[{"company_id": "cmp-power"}],
        )

        async def rebenta(*_a, **_kw):
            raise RuntimeError("índice duplicado")

        with patch.object(admin_users, "db", fake_async_db), \
             patch.object(admin_users, "criar_acessos_iniciais", rebenta), \
             patch.object(bootstrap, "db", fake_async_db), \
             patch.object(admin_users, "_audit_log", _sem_efeito):
            with pytest.raises(HTTPException) as erro:
                await admin_users.run_create_user(dados, {"id": "u-admin"})

        assert erro.value.status_code == 500
        assert fake_async_db.users.docs == [], "a conta ficou órfã na base de dados"


async def _envio_falso(*_a, **_kw):
    return {"success": True}


async def _sem_efeito(*_a, **_kw):
    return None
