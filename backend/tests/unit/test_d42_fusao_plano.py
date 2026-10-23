"""D-42/D-40 — o PLANO de fusão de clientes duplicados (puro, sem base de dados).

O que se protege:
  * quem é duplicado: ligados por NIF **ou** Email (transitivamente); o telemóvel não conta;
  * o que NUNCA se funde sozinho: dois NIFs diferentes ligados por um email;
  * o sobrevivente é determinístico (uma ordem total) — correr duas vezes dá o mesmo;
  * só se PREENCHE o que falta; a identidade do sobrevivente nunca é trocada;
  * as redes dos absorvidos viram associações do sobrevivente (a segregação mantém-se).
"""
from __future__ import annotations


from services.client_duplicates_audit import Registo
from services.client_merge_plan import (
    AMBIGUO,
    FUNDIR,
    Candidato,
    componentes,
    escolher_sobrevivente,
    planear,
    preencher_o_que_falta,
    resumir,
)


def _c(id_, rede="R1", nif=None, email=None, n=0, doc=None, **doc_extra):
    d = {"id": id_, **doc_extra, **(doc or {})}
    return Candidato(Registo(id=id_, rede=rede, nif=nif, email=email, nome=f"N{id_}"), d, n)


class TestOsGrupos:
    def test_mesmo_nif_forma_grupo(self):
        grupos = componentes([_c("a", nif="1"), _c("b", nif="1"), _c("c", nif="2")])
        assert [[c.registo.id for c in g] for g in grupos] == [["a", "b"]]

    def test_mesmo_email_forma_grupo(self):
        grupos = componentes([_c("a", email="x"), _c("b", email="x")])
        assert len(grupos) == 1

    def test_a_ligacao_e_transitiva(self):
        """a~b pelo NIF, b~c pelo email: é UMA pessoa a resolver."""
        grupos = componentes([_c("a", nif="1"), _c("b", nif="1", email="x"), _c("c", email="x"), _c("z", nif="9")])
        assert [[c.registo.id for c in g] for g in grupos] == [["a", "b", "c"]]

    def test_sem_nif_nem_email_nao_forma_grupo(self):
        assert componentes([_c("a"), _c("b")]) == []

    def test_o_mesmo_cliente_duas_vezes_nao_forma_grupo_consigo(self):
        assert componentes([_c("a", nif="1")]) == []


class TestOSobrevivente:
    def test_o_que_tem_mais_processos_fica(self):
        assert escolher_sobrevivente([_c("a", nif="1", n=1), _c("b", nif="1", n=3)]).registo.id == "b"

    def test_a_igualdade_de_processos_desempata_pelo_registo_completo(self):
        a = _c("a", nif="1", registration_completed=False)
        b = _c("b", nif="1", registration_completed=True)
        assert escolher_sobrevivente([a, b]).registo.id == "b"

    def test_depois_pelo_mais_antigo_e_depois_pelo_id(self):
        a = _c("a", nif="1", created_at="2026-05-01")
        b = _c("b", nif="1", created_at="2026-01-01")
        assert escolher_sobrevivente([a, b]).registo.id == "b"
        c = _c("c", nif="1", created_at="2026-01-01")
        assert escolher_sobrevivente([c, b]).registo.id == "b"

    def test_e_deterministico_seja_qual_for_a_ordem_de_entrada(self):
        cs = [_c(x, nif="1", n=1, created_at="2026-01-01") for x in "dcba"]
        assert escolher_sobrevivente(cs).registo.id == escolher_sobrevivente(list(reversed(cs))).registo.id == "a"


class TestOPlano:
    def test_dois_clientes_com_o_mesmo_nif_fundem(self):
        (p,) = planear([_c("a", "R1", nif="1", n=2), _c("b", "R2", nif="1")])
        assert (p.veredicto, p.sobrevivente, p.absorvidos) == (FUNDIR, "a", ("b",))
        assert p.redes_a_associar == ("R2",)

    def test_a_mesma_rede_nao_cria_associacao(self):
        (p,) = planear([_c("a", "R1", nif="1", n=2), _c("b", "R1", nif="1")])
        assert p.redes_a_associar == ()

    def test_dois_emails_diferentes_com_o_mesmo_nif_sao_a_mesma_pessoa(self):
        (p,) = planear([_c("a", nif="1", email="x", n=1), _c("b", nif="1", email="y")])
        assert p.veredicto == FUNDIR

    def test_nif_ausente_num_deles_com_o_mesmo_email_funde(self):
        (p,) = planear([_c("a", nif="1", email="x", n=1), _c("b", email="x")])
        assert p.veredicto == FUNDIR and p.absorvidos == ("b",)

    def test_dois_nifs_diferentes_ligados_por_um_email_sao_ambiguos_e_nao_se_fundem(self):
        (p,) = planear([_c("a", nif="1", email="x"), _c("b", nif="2", email="x")])
        assert p.veredicto == AMBIGUO
        assert p.absorvidos == ()
        assert p.motivo == "nifs_diferentes_ligados_por_email"

    def test_um_grupo_de_tres_com_dois_nifs_e_ambiguo_inteiro(self):
        (p,) = planear([
            _c("a", nif="1", email="x"), _c("b", email="x"), _c("c", nif="2", email="x"),
        ])
        assert p.veredicto == AMBIGUO and set(p.membros) == {"a", "b", "c"}

    def test_o_telemovel_nao_agrupa(self):
        """O Registo nem tem telefone: a mutação que o reintroduzisse não tem onde se agarrar."""
        assert "telefone" not in Registo.__dataclass_fields__
        assert planear([_c("a", nif="1"), _c("b", nif="2")]) == []

    def test_os_fundiveis_vem_primeiro_e_os_maiores_antes(self):
        planos = planear([
            _c("a", nif="1", email="e1"), _c("b", nif="2", email="e1"),                        # ambíguo
            _c("c", nif="3"), _c("d", nif="3"), _c("e", nif="3"),                              # 3 a fundir
            _c("f", nif="4"), _c("g", nif="4"),                                                 # 2 a fundir
        ])
        assert [(p.veredicto, len(p.membros)) for p in planos] == [(FUNDIR, 3), (FUNDIR, 2), (AMBIGUO, 2)]

    def test_o_resumo_conta_e_so_diz_viavel_sem_nenhum_grupo(self):
        assert resumir([])["indice_unico_viavel"] is True
        r = resumir(planear([_c("a", nif="1", email="x"), _c("b", nif="2", email="x")]))
        assert r["ambiguos"] == 1 and r["a_fundir"] == 0 and r["indice_unico_viavel"] is False


class TestPreencher:
    def test_so_preenche_o_que_falta(self):
        sobrev = {"contacto": {"telefone": "ENC:a"}, "dados_pessoais": {"nacionalidade": "PT"}}
        absorv = {
            "contacto": {"telefone": "ENC:b", "telefone_secundario": "ENC:c"},
            "dados_pessoais": {"nacionalidade": "ES", "morada_fiscal": "ENC:m", "estado_civil": ""},
        }
        assert preencher_o_que_falta(sobrev, absorv) == {
            "contacto.telefone_secundario": "ENC:c",
            "dados_pessoais.morada_fiscal": "ENC:m",
        }

    def test_nunca_troca_a_identidade_do_sobrevivente(self):
        sobrev = {"contacto": {}, "dados_pessoais": {}}
        absorv = {
            "contacto": {"email": "ENC:e", "email_hash": "h"},
            "dados_pessoais": {"nif": "ENC:n", "nif_hash": "h"},
        }
        assert preencher_o_que_falta(sobrev, absorv) == {}

    def test_seccoes_em_falta_ou_de_tipo_errado_nao_rebentam(self):
        assert preencher_o_que_falta({}, {"contacto": None, "dados_pessoais": "x"}) == {}
        assert preencher_o_que_falta({"contacto": "lixo"}, {"contacto": {"telefone": "t"}}) == {"contacto.telefone": "t"}

    def test_o_plano_leva_os_preenchimentos_por_absorvido(self):
        a = _c("a", nif="1", n=2, doc={"dados_pessoais": {}})
        b = _c("b", nif="1", doc={"dados_pessoais": {"morada_fiscal": "ENC:m"}})
        (p,) = planear([a, b])
        assert p.preenchimentos == {"b": {"dados_pessoais.morada_fiscal": "ENC:m"}}


class TestGuardas:
    def test_o_modulo_e_puro(self):
        import ast
        import pathlib

        import services.client_merge_plan as m

        arvore = ast.parse(pathlib.Path(m.__file__).read_text(encoding="utf-8"))
        importados = {
            (n.module if isinstance(n, ast.ImportFrom) else a.name)
            for n in ast.walk(arvore) if isinstance(n, (ast.Import, ast.ImportFrom))
            for a in (n.names if isinstance(n, ast.Import) else [None])
        }
        assert "database" not in importados and not any((x or "").startswith("motor") for x in importados)
