"""
O `seed.py` tem uma cópia LOCAL de `UserRole` (não importa a app). Quando a
adenda de RBAC passou a conta de sistema a Master, o seed ganhou
`UserRole.MASTER` e a cópia não — o passo `python seed.py` do CI rebentou com
`AttributeError`, e nenhum teste unitário o viu porque nenhum corre o seed.

Duas guardas, por AST (o seed corre `asyncio.run(main())` ao ser importado
como script, por isso não se importa):
  * todo o `UserRole.X` usado no seed existe na classe local;
  * todo o valor da classe local que o seed usa é um perfil reconhecido.
"""
import ast
from pathlib import Path

from models.auth import PERFIS_DO_SISTEMA

SEED = Path(__file__).resolve().parents[2] / "seed.py"


def _arvore():
    return ast.parse(SEED.read_text(encoding="utf-8"))


def _classe_local(arvore) -> dict[str, str]:
    for no in arvore.body:
        if isinstance(no, ast.ClassDef) and no.name == "UserRole":
            return {
                alvo.id: ast.literal_eval(item.value)
                for item in no.body
                if isinstance(item, ast.Assign)
                for alvo in item.targets
                if isinstance(alvo, ast.Name)
            }
    raise AssertionError("classe UserRole não encontrada no seed.py")


def _usados(arvore) -> set[str]:
    return {
        no.attr
        for no in ast.walk(arvore)
        if isinstance(no, ast.Attribute)
        and isinstance(no.value, ast.Name)
        and no.value.id == "UserRole"
    }


def test_o_leitor_leu_mesmo_o_seed():
    arvore = _arvore()
    assert len(_classe_local(arvore)) >= 8
    assert {"ADMIN", "CONSULTOR"} <= _usados(arvore)


def test_todo_o_perfil_usado_no_seed_existe_na_classe_local():
    arvore = _arvore()
    em_falta = _usados(arvore) - set(_classe_local(arvore))
    assert em_falta == set(), f"UserRole.{sorted(em_falta)} usado no seed e ausente da cópia local"


def test_a_conta_de_sistema_do_seed_e_master():
    arvore = _arvore()
    assert _classe_local(arvore)["MASTER"] == "master"


def test_os_perfis_usados_no_seed_sao_perfis_do_sistema():
    arvore = _arvore()
    local = _classe_local(arvore)
    valores = {local[nome] for nome in _usados(arvore)}
    assert valores <= set(PERFIS_DO_SISTEMA), valores - set(PERFIS_DO_SISTEMA)
