"""Sanar o `s3_folder` gravado com o tipo errado (Lote 8, ponto 1).

A ORIGEM, CONFIRMADA
====================
O relatório da D-19 em produção trouxe a forma exacta:

    gravado: [True, 'Documentação Clientes/Nome_do_Cliente']

É um `(sucesso, caminho)` — o par que `initialize_client_folders` e
`ensure_client_folder_mapping` devolvem. Alguém gravou o PAR em vez de
extrair a string. O campo é um caminho; passou a conter o resultado da
função que o calculou.

PORQUE É QUE ISTO NÃO É UM `valor[1]`
=====================================
O pedido foi «substituir a lista pelo valor do índice 1». Para a forma
acima é exactamente isso — mas um script de migração que escreve na base
de dados de produção não pode confiar numa forma que viu dez vezes. As
três maneiras de um `[1]` cego fazer mal:

1. **`[False, ...]`** — o par diz que a operação FALHOU. O caminho que
   está no índice 1 é o que o código tentou e não conseguiu usar;
   gravá-lo é cimentar um mapeamento que o próprio sistema rejeitou.
   Recusa-se, e um humano decide.

2. **Fora da raiz documental** — gravar `backups/dump.zip` aqui
   transformava a guarda de posse (`build_s3_valid_prefixes` →
   `assert_s3_file_belongs_to_process`) num passe para esse prefixo. É o
   «prefixo de dono ENVENENADO» da regra 1 do `s3_relink`, e é
   alcançável do Portal. **A validação da raiz não é zelo: é a parede.**

3. **Qualquer outra forma** — `[]`, `[None]`, três elementos, uma lista
   dentro de outra, um `dict`. O índice 1 de cada uma dá algo diferente
   e nenhum deles é um caminho.

Daí três veredictos, e só um escreve. É a mesma regra do
`assignment_drift`: a bandeira autoriza a escrita, **não substitui a
prova**.

ESTE MÓDULO NÃO SABE O QUE É MONGO
==================================
Recebe o valor cru e devolve o veredicto. Quem lê e escreve é o
`scripts/fix_s3_folder_anomalies.py`.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from services.s3_document_root import RAIZ, dentro_da_pasta, normalizar

#: Reparável: o par `(True, caminho)` dentro da raiz documental.
VEREDICTO_PAR_DE_SUCESSO = "par_de_sucesso"

#: O par declara FALHA. O caminho existe no valor mas o código disse que
#: não servia — escrevê-lo é inventar um mapeamento.
VEREDICTO_PAR_DE_FALHA = "par_de_falha"

#: Fora da raiz documental. Gravar isto arma a guarda de posse contra nós.
VEREDICTO_FORA_DA_RAIZ = "fora_da_raiz"

#: Nenhuma forma reconhecida. Não se adivinha.
VEREDICTO_IRRECONHECIVEL = "irreconhecivel"

#: Já é texto — não é anomalia nenhuma e o script não lhe toca.
VEREDICTO_JA_E_TEXTO = "ja_e_texto"

#: O único que o `--aplicar` escreve.
VEREDICTOS_REPARAVEIS = (VEREDICTO_PAR_DE_SUCESSO,)


@dataclass(frozen=True)
class Reparacao:
    """O que fazer com um valor, e porquê."""

    veredicto: str
    caminho: Optional[str] = None
    #: O valor como está na base de dados, para o relatório.
    valor_cru: str = ""
    #: Em linguagem humana, para quem lê o relatório e tem de decidir.
    motivo: str = ""

    @property
    def reparavel(self) -> bool:
        return self.veredicto in VEREDICTOS_REPARAVEIS and bool(self.caminho)


def _e_par(valor: Any) -> bool:
    """`[x, y]` ou `(x, y)` — a forma que `(sucesso, caminho)` tem.

    O BSON não tem tuplos: o driver devolve lista. Aceitam-se os dois
    porque o módulo também é chamado com valores de teste.
    """
    return isinstance(valor, (list, tuple)) and len(valor) == 2


def classificar(valor: Any) -> Reparacao:
    """O veredicto para um valor de `s3_folder`."""
    cru = repr(valor)

    if isinstance(valor, str):
        return Reparacao(
            veredicto=VEREDICTO_JA_E_TEXTO,
            caminho=valor,
            valor_cru=cru,
            motivo="já é texto — não é anomalia",
        )

    if not _e_par(valor):
        return Reparacao(
            veredicto=VEREDICTO_IRRECONHECIVEL,
            valor_cru=cru,
            motivo=(
                f"não é o par (sucesso, caminho): é {type(valor).__name__}"
                + (f" de {len(valor)} elementos" if isinstance(valor, (list, tuple, dict)) else "")
            ),
        )

    sucesso, caminho = valor[0], valor[1]

    if not isinstance(caminho, str) or not normalizar(caminho):
        return Reparacao(
            veredicto=VEREDICTO_IRRECONHECIVEL,
            valor_cru=cru,
            motivo=(
                "o segundo elemento não é um caminho utilizável: "
                f"{type(caminho).__name__}"
            ),
        )

    limpo = normalizar(caminho)

    # A raiz ANTES do sucesso: um caminho envenenado é um problema de
    # segurança e tem de ser nomeado como tal, mesmo que o par diga
    # `True`. Ao contrário, um `[True, "backups/x.zip"]` sairia
    # classificado como «falha» e alguém podia dar-lhe `--aplicar`.
    if not dentro_da_pasta(limpo, RAIZ) or limpo == normalizar(RAIZ):
        return Reparacao(
            veredicto=VEREDICTO_FORA_DA_RAIZ,
            valor_cru=cru,
            motivo=(
                f"o caminho não está dentro de «{RAIZ}» (ou é a raiz nua) — "
                "gravá-lo alargava a guarda de posse a esse prefixo"
            ),
        )

    if sucesso is not True:
        return Reparacao(
            veredicto=VEREDICTO_PAR_DE_FALHA,
            caminho=limpo,
            valor_cru=cru,
            motivo=(
                f"o par declara sucesso={sucesso!r}: o código que o produziu "
                "não conseguiu usar este caminho"
            ),
        )

    return Reparacao(
        veredicto=VEREDICTO_PAR_DE_SUCESSO,
        caminho=limpo,
        valor_cru=cru,
        motivo="par (True, caminho) dentro da raiz documental",
    )


def resumir(reparacoes) -> dict:
    """Contagens por veredicto, e quantos o `--aplicar` tocaria."""
    por_veredicto: dict[str, int] = {}
    reparaveis = 0
    for reparacao in reparacoes:
        por_veredicto[reparacao.veredicto] = (
            por_veredicto.get(reparacao.veredicto, 0) + 1
        )
        if reparacao.reparavel:
            reparaveis += 1
    return {
        "total": sum(por_veredicto.values()),
        "por_veredicto": por_veredicto,
        "reparaveis": reparaveis,
        "exigem_decisao": sum(por_veredicto.values()) - reparaveis
        - por_veredicto.get(VEREDICTO_JA_E_TEXTO, 0),
    }


__all__ = [
    "Reparacao",
    "VEREDICTOS_REPARAVEIS",
    "VEREDICTO_FORA_DA_RAIZ",
    "VEREDICTO_IRRECONHECIVEL",
    "VEREDICTO_JA_E_TEXTO",
    "VEREDICTO_PAR_DE_FALHA",
    "VEREDICTO_PAR_DE_SUCESSO",
    "classificar",
    "resumir",
]
