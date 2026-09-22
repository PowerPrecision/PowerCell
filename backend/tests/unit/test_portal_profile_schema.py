"""
Perfil do Portal alinhado com o formulário interno (Lote 3, ponto 7).

O DEFEITO
---------
O formulário interno é CONFIGURÁVEL: o admin liga/desliga campos e define
obrigatoriedade em `form_config`. O do Portal era uma lista ESCRITA À MÃO
em `ClientPortal.jsx`, com um allowlist igualmente escrito à mão em
`portal_profile.py`. Consequências:

  - campos do formulário interno não existiam no Portal (`codigo_postal`,
    `niss`);
  - a obrigatoriedade não era sinalizada de todo;
  - e o pior: `if key in PROFILE_UPDATABLE_PERSONAL_FIELDS` descartava em
    SILÊNCIO qualquer campo fora do allowlist. O cliente preenchia,
    gravava, via "Perfil atualizado com sucesso!" — e o valor não existia.

A CORRECÇÃO
-----------
Uma única fonte: o `form_config`. O backend deriva dele o que renderizar
E o que aceita escrever, pelo que os dois não podem divergir.

REGRA DE NEGÓCIO CONFIRMADA
---------------------------
O NIF NUNCA é editável pelo cliente. É o campo que o identifica
fiscalmente; deixá-lo editável no Portal é uma decisão de risco, não de
interface. Continua oculto na leitura e bloqueado na escrita.
"""
from unittest.mock import AsyncMock, patch

import pytest

from services import portal_profile
from services.portal_profile import (
    ClientProfileUpdate,
    build_portal_profile_mongo_update,
    carregar_campos_editaveis,
)
from services.portal_profile_schema import (
    PORTAL_LOCKED_FIELDS,
    build_portal_profile_schema,
    destino_do_campo,
    portal_updatable_fields,
)

CAMPOS = [
    {"field_key": "name", "label": "Nome completo", "step": 1, "is_visible": True,
     "is_required": True, "field_type": "text", "order": 1, "data_path": "root"},
    {"field_key": "email", "label": "Email", "step": 1, "is_visible": True,
     "is_required": True, "field_type": "email", "order": 2, "data_path": "root"},
    {"field_key": "phone", "label": "Telemóvel", "step": 1, "is_visible": True,
     "is_required": True, "field_type": "tel", "order": 3, "data_path": "root"},
    {"field_key": "nif", "label": "NIF", "step": 1, "is_visible": True,
     "is_required": True, "field_type": "text", "order": 4, "data_path": "personal_data"},
    {"field_key": "documento_id", "label": "CC/Passaporte", "step": 1, "is_visible": True,
     "is_required": True, "field_type": "text", "order": 5, "data_path": "personal_data"},
    {"field_key": "morada_fiscal", "label": "Morada Fiscal", "step": 1, "is_visible": True,
     "is_required": True, "field_type": "text", "order": 9, "data_path": "personal_data"},
    {"field_key": "birth_date", "label": "Data de Nascimento", "step": 1, "is_visible": True,
     "is_required": True, "field_type": "date", "order": 10, "data_path": "personal_data"},
    {"field_key": "estado_civil", "label": "Estado Civil", "step": 1, "is_visible": True,
     "is_required": True, "field_type": "select", "order": 11, "data_path": "personal_data",
     "options": [{"value": "solteiro", "label": "Solteiro(a)"}]},
    {"field_key": "codigo_postal", "label": "Código Postal", "step": 1, "is_visible": True,
     "is_required": False, "field_type": "text", "order": 15, "data_path": "personal_data"},
    {"field_key": "profissao", "label": "Profissão", "step": 1, "is_visible": True,
     "is_required": False, "field_type": "text", "order": 16, "data_path": "personal_data"},
    {"field_key": "niss", "label": "NISS", "step": 1, "is_visible": True,
     "is_required": False, "field_type": "text", "order": 3, "data_path": "personal_data",
     "hint": "11 dígitos"},
    {"field_key": "altura", "label": "Altura", "step": 1, "is_visible": False,
     "is_required": False, "field_type": "number", "order": 17, "data_path": "personal_data"},
    # Campos de OUTROS passos — não pertencem ao perfil do titular.
    {"field_key": "titular2_name", "label": "Nome 2.º Titular", "step": 2,
     "is_visible": True, "is_required": False, "field_type": "text", "order": 1,
     "data_path": "titular2_data"},
    {"field_key": "finalidade", "label": "Finalidade", "step": 3, "is_visible": True,
     "is_required": True, "field_type": "select", "order": 1,
     "data_path": "real_estate_data"},
]


def _chaves(schema):
    return [c["field_key"] for c in schema]


# ====================================================================
# 1. O NIF NUNCA É EDITÁVEL
# ====================================================================


class TestNifTrancado:
    def test_o_nif_esta_na_lista_de_trancados(self):
        assert "nif" in PORTAL_LOCKED_FIELDS

    def test_o_nif_nao_entra_no_esquema_do_portal(self):
        # Está no formulário interno como obrigatório; aqui não aparece.
        assert "nif" not in _chaves(build_portal_profile_schema(CAMPOS))

    def test_o_nif_nao_e_gravavel(self):
        campos = portal_updatable_fields(build_portal_profile_schema(CAMPOS))
        assert "nif" not in campos["dados_pessoais"]

    def test_o_nome_tambem_nao_e_editavel_pelo_cliente(self):
        # A identidade do cliente é gerida pela equipa, não pelo portal.
        assert "name" not in _chaves(build_portal_profile_schema(CAMPOS))


# ====================================================================
# 2. O QUE O PORTAL PASSA A MOSTRAR
# ====================================================================


class TestEsquema:
    def test_traz_os_campos_que_faltavam(self):
        chaves = _chaves(build_portal_profile_schema(CAMPOS))
        assert "codigo_postal" in chaves
        assert "niss" in chaves

    def test_ignora_campos_invisiveis(self):
        # `altura` tem is_visible=False no formulário interno.
        assert "altura" not in _chaves(build_portal_profile_schema(CAMPOS))

    def test_ignora_campos_de_outros_passos(self):
        chaves = _chaves(build_portal_profile_schema(CAMPOS))
        assert "titular2_name" not in chaves
        assert "finalidade" not in chaves

    def test_traz_contactos_do_passo_do_titular(self):
        chaves = _chaves(build_portal_profile_schema(CAMPOS))
        assert "email" in chaves
        assert "phone" in chaves

    def test_respeita_a_ordem_do_formulario_interno(self):
        schema = build_portal_profile_schema(CAMPOS)
        ordens = [c["order"] for c in schema]
        assert ordens == sorted(ordens)

    def test_transporta_rotulo_tipo_e_opcoes(self):
        schema = build_portal_profile_schema(CAMPOS)
        estado = next(c for c in schema if c["field_key"] == "estado_civil")
        assert estado["label"] == "Estado Civil"
        assert estado["field_type"] == "select"
        assert estado["options"][0]["value"] == "solteiro"

    def test_transporta_a_dica(self):
        schema = build_portal_profile_schema(CAMPOS)
        niss = next(c for c in schema if c["field_key"] == "niss")
        assert niss["hint"] == "11 dígitos"


# ====================================================================
# 3. DIVULGAÇÃO PROGRESSIVA
# ====================================================================


class TestDivulgacaoProgressiva:
    def test_obrigatorios_sao_principais(self):
        schema = build_portal_profile_schema(CAMPOS)
        for campo in schema:
            if campo["is_required"]:
                assert campo["is_primary"] is True, campo["field_key"]

    def test_opcionais_ficam_para_a_seccao_expansivel(self):
        schema = build_portal_profile_schema(CAMPOS)
        secundarios = [c["field_key"] for c in schema if not c["is_primary"]]
        assert "codigo_postal" in secundarios
        assert "profissao" in secundarios
        assert "niss" in secundarios

    def test_ha_sempre_pelo_menos_um_campo_principal(self):
        # Um formulário inteiro escondido atrás de um acordeão seria pior
        # do que não ter divulgação progressiva nenhuma.
        so_opcionais = [
            {**c, "is_required": False} for c in CAMPOS if c.get("is_visible")
        ]
        schema = build_portal_profile_schema(so_opcionais)
        assert any(c["is_primary"] for c in schema)


# ====================================================================
# 4. O DESTINO NA FICHA
# ====================================================================


class TestDestinoNaFicha:
    def test_email_vai_para_contacto(self):
        assert destino_do_campo({"field_key": "email", "data_path": "root"}) == (
            "contacto", "email",
        )

    def test_telemovel_e_renomeado_para_telefone(self):
        # O formulário chama-lhe `phone`; a ficha do cliente guarda
        # `contacto.telefone`. Sem o mapeamento, gravava num campo novo.
        assert destino_do_campo({"field_key": "phone", "data_path": "root"}) == (
            "contacto", "telefone",
        )

    def test_data_de_nascimento_usa_o_nome_da_ficha(self):
        # `birth_date` no formulário, `data_nascimento` na ficha — e é este
        # que o CRM lê primeiro em `PersonalInfoTab`.
        assert destino_do_campo(
            {"field_key": "birth_date", "data_path": "personal_data"}
        ) == ("dados_pessoais", "data_nascimento")

    def test_campo_pessoal_sem_mapeamento_mantem_o_nome(self):
        assert destino_do_campo(
            {"field_key": "profissao", "data_path": "personal_data"}
        ) == ("dados_pessoais", "profissao")

    def test_campo_de_outro_data_path_nao_tem_destino(self):
        assert destino_do_campo(
            {"field_key": "finalidade", "data_path": "real_estate_data"}
        ) is None


# ====================================================================
# 5. O ALLOWLIST DERIVA DO ESQUEMA (não pode divergir)
# ====================================================================


class TestAllowlistDerivado:
    def test_tudo_o_que_e_mostrado_e_gravavel(self):
        # Era esta a divergência: o Portal mostrava um campo e o backend
        # descartava-o em silêncio ao gravar.
        schema = build_portal_profile_schema(CAMPOS)
        campos = portal_updatable_fields(schema)
        for entrada in schema:
            grupo, nome = entrada["destino"]
            assert nome in campos[grupo], f"{entrada['field_key']} não é gravável"

    def test_nada_alem_do_esquema_e_gravavel(self):
        schema = build_portal_profile_schema(CAMPOS)
        campos = portal_updatable_fields(schema)
        assert "s3_folder" not in campos["dados_pessoais"]
        assert "nif" not in campos["dados_pessoais"]

    def test_contactos_extra_do_portal_continuam_a_funcionar(self):
        # O Portal já oferecia email/telefone secundários, que não existem
        # no formulário interno. Não podem desaparecer nesta mudança.
        campos = portal_updatable_fields(build_portal_profile_schema(CAMPOS))
        assert "email_secundario" in campos["contacto"]
        assert "telefone_secundario" in campos["contacto"]

    def test_os_contactos_extra_tambem_sao_DESENHADOS(self):
        # Estarem só no allowlist não chega: a UI desenha a partir do
        # esquema, e sem entrada nele o cliente perdia os campos.
        chaves = _chaves(build_portal_profile_schema(CAMPOS))
        assert "email_secundario" in chaves
        assert "telefone_secundario" in chaves

    def test_os_contactos_extra_sao_secundarios(self):
        schema = build_portal_profile_schema(CAMPOS)
        extra = next(c for c in schema if c["field_key"] == "email_secundario")
        assert extra["is_primary"] is False

    def test_formulario_vazio_nao_abre_a_porta_a_tudo(self):
        # Degradação segura: sem configuração, nada é gravável em vez de
        # tudo ser gravável.
        campos = portal_updatable_fields(build_portal_profile_schema([]))
        assert campos["dados_pessoais"] == set()


# ====================================================================
# 6. A GRAVAÇÃO DEIXA DE SER SILENCIOSA
# ====================================================================


PERMITIDOS = {
    "contacto": {"email", "telefone"},
    "dados_pessoais": {"morada_fiscal", "codigo_postal"},
}


class TestGravacaoReportada:
    def test_campo_fora_do_allowlist_e_reportado(self):
        # O defeito: era descartado em silêncio e o cliente via
        # "Perfil atualizado com sucesso!".
        recusados = []
        build_portal_profile_mongo_update(
            ClientProfileUpdate(dados_pessoais={"inventado": "x"}),
            {}, "2026-09-22T00:00:00Z",
            campos_editaveis=PERMITIDOS, recusados=recusados,
        )
        assert recusados == ["inventado"]

    def test_o_nif_e_recusado_e_nao_gravado(self):
        recusados = []
        update = build_portal_profile_mongo_update(
            ClientProfileUpdate(dados_pessoais={"nif": "999999999"}),
            {}, "2026-09-22T00:00:00Z",
            campos_editaveis=PERMITIDOS, recusados=recusados,
        )
        assert "nif" in recusados
        assert not any("nif" in chave for chave in update)

    def test_campo_novo_do_form_config_passa_a_ser_gravado(self):
        # `codigo_postal` não existia no allowlist escrito à mão.
        update = build_portal_profile_mongo_update(
            ClientProfileUpdate(dados_pessoais={"codigo_postal": "4000-100"}),
            {}, "2026-09-22T00:00:00Z",
            campos_editaveis=PERMITIDOS, recusados=[],
        )
        assert update["dados_pessoais.codigo_postal"] == "4000-100"

    def test_sem_allowlist_usa_as_listas_de_recurso(self):
        # Retrocompatibilidade: quem chama sem o parâmetro continua a
        # gravar o que gravava.
        update = build_portal_profile_mongo_update(
            ClientProfileUpdate(dados_pessoais={"profissao": "Engenheira"}),
            {}, "2026-09-22T00:00:00Z",
        )
        assert update["dados_pessoais.profissao"] == "Engenheira"

    def test_campos_protegidos_continuam_bloqueados(self):
        # A rede de segurança do hotfix S3 mantém-se por cima de tudo.
        update = build_portal_profile_mongo_update(
            ClientProfileUpdate(dados_pessoais={"morada_fiscal": "Rua A"}),
            {}, "2026-09-22T00:00:00Z",
            campos_editaveis={
                "contacto": set(),
                "dados_pessoais": {"morada_fiscal"},
            },
            recusados=[],
        )
        assert "s3_folder" not in update
        assert "process_ids" not in update


class TestDegradacaoDoAllowlist:
    @pytest.mark.asyncio
    async def test_form_config_inacessivel_usa_o_recurso(self):
        # Um erro a ler a configuração não pode deixar o Portal sem
        # conseguir gravar nada.
        with patch(
            "services.public_form_config.load_merged_form_fields",
            AsyncMock(side_effect=RuntimeError("mongo em baixo")),
        ):
            campos = await carregar_campos_editaveis()
        assert "morada_fiscal" in campos["dados_pessoais"]

    @pytest.mark.asyncio
    async def test_form_config_vazio_usa_o_recurso(self):
        with patch(
            "services.public_form_config.load_merged_form_fields",
            AsyncMock(return_value=[]),
        ):
            campos = await carregar_campos_editaveis()
        assert campos["dados_pessoais"]

    @pytest.mark.asyncio
    async def test_com_form_config_manda_o_form_config(self):
        with patch(
            "services.public_form_config.load_merged_form_fields",
            AsyncMock(return_value=CAMPOS),
        ):
            campos = await carregar_campos_editaveis()
        assert "codigo_postal" in campos["dados_pessoais"]
        assert "niss" in campos["dados_pessoais"]
        assert "nif" not in campos["dados_pessoais"]
