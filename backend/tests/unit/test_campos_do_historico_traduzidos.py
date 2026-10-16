"""Todo o campo que o histórico grava tem tradução no ecrã (Lote 7.3).

A Timeline mostrava `assigned_mediador_ids` e `portal_access` tal e qual: o servidor grava a CHAVE técnica
(é o contrato do histórico) e o ecrã não a traduzia. O dicionário vive no frontend
(`utils/rotulosDoHistorico.js`); este teste inventaria por AST os `field` literais de TODAS as chamadas a
`log_history` e exige que cada um esteja lá — um escritor novo com um campo novo falha aqui em vez de
aparecer em inglês de base de dados a quem lê o histórico. As chaves dinâmicas (variáveis, constantes) têm
um recurso legível por regra no frontend e não entram neste inventário.
"""
import ast
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]
DICIONARIO = RAIZ.parent / "frontend" / "src" / "utils" / "rotulosDoHistorico.js"
NOMES_DA_FUNCAO = {"log_history", "log_history_fn", "_log_history"}

#: Campos literais que não precisam de entrada própria — com o motivo.
DISPENSADOS: dict[str, str] = {}


def _campos_gravados() -> dict[str, str]:
    encontrados: dict[str, str] = {}
    for pasta in ("services", "routes"):
        for ficheiro in (RAIZ / pasta).rglob("*.py"):
            try:
                arvore = ast.parse(ficheiro.read_text(encoding="utf-8"))
            except SyntaxError:
                continue
            for no in ast.walk(arvore):
                if not isinstance(no, ast.Call):
                    continue
                nome = getattr(no.func, "id", None) or getattr(no.func, "attr", None)
                if nome not in NOMES_DA_FUNCAO:
                    continue
                campo = next((k.value for k in no.keywords if k.arg == "field"), None)
                if campo is None and len(no.args) >= 4:
                    campo = no.args[3]
                if isinstance(campo, ast.Constant) and isinstance(campo.value, str):
                    encontrados.setdefault(campo.value, f"{ficheiro.relative_to(RAIZ)}:{no.lineno}")
    return encontrados


def _chaves_do_dicionario() -> set[str]:
    texto = DICIONARIO.read_text(encoding="utf-8")
    bloco = texto[texto.index("CAMPOS_DO_HISTORICO = {"):texto.index("/** Segmentos")]
    return set(re.findall(r"^  ([a-z0-9_]+): \{ rotulo", bloco, flags=re.M))


def test_o_leitor_leu_mesmo_os_dois_lados():
    """Contraprova: sem ela, dois leitores vazios davam um verde que não prova nada."""
    assert len(_campos_gravados()) >= 30
    assert {"status", "portal_access", "assigned_mediador_ids"} <= _chaves_do_dicionario()


def test_todo_o_campo_gravado_tem_traducao():
    em_falta = {
        campo: onde
        for campo, onde in _campos_gravados().items()
        if campo not in _chaves_do_dicionario() and campo not in DISPENSADOS
    }
    assert not em_falta, (
        "campos gravados no histórico sem tradução em frontend/src/utils/rotulosDoHistorico.js: "
        + ", ".join(f"{c} ({o})" for c, o in sorted(em_falta.items()))
    )
