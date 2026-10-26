"""Modelos do módulo Index (Lote 12, Fase 1): metadados profissionais, entidades, alertas.

Princípios (ver `INDEX_MODULE_ARCHITECTURE.md`):

* **Nada disto vive no documento do processo** — o modelo do processo é
  `extra="allow"` e já vazou dados por aí. Cada colecção é separada e só a lêem
  módulos do Index (inventário por AST).
* **`value=None ⇒ needs_review=True`**: um campo que a IA não sabe nunca é
  silenciosamente «vazio».
* **`edited_by_human` blinda o campo contra a reanálise** (a IA propõe, a pessoa dispõe).
* **Mensagens e severidades de alertas vêm de uma tabela no código**
  (`ALERTAS`), nunca de texto livre de um modelo: um alerta com código fora da
  tabela não existe. Nenhum alerta bloqueia a indexação.
* **Dinheiro é `Decimal`**, nunca `float`.
"""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Generic, Literal, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from utils.validation import validate_nif

T = TypeVar("T")

Confianca = Literal["alta", "media", "baixa"]
TipoDeContrato = Literal["efetivo", "termo_certo", "termo_incerto", "outro"]
SubtipoDeIdentificacao = Literal["cc", "bi", "passaporte", "titulo_residencia"]
EstadoDoFicheiroLiteral = Literal["original", "sanitizado", "purgado"]

#: Todos os documentos de identificação ficam na MESMA categoria (decisão da direcção);
#: o tipo concreto é o subtipo.
CATEGORIA_IDENTIFICACAO = "Identificação"
SUBTIPOS_DE_IDENTIFICACAO = ("cc", "bi", "passaporte", "titulo_residencia")

_PERIODO = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def normalizar_nif(valor: Any) -> Optional[str]:
    """Só dígitos, ou `None` se não sobrar nada. NÃO valida o dígito de controlo."""
    if valor is None:
        return None
    digitos = re.sub(r"\D", "", str(valor))
    return digitos or None


def nif_e_valido(valor: Any) -> bool:
    """NIF português com dígito de controlo (a regra única do projecto, `utils.validation`)."""
    digitos = normalizar_nif(valor)
    if not digitos:
        return False
    return bool(validate_nif(digitos)[0])


# ====================================================================
# CAMPO REVISÁVEL
# ====================================================================
class FonteDoCampo(BaseModel):
    """De onde veio o valor: documento e página — NUNCA o texto lido."""

    model_config = ConfigDict(extra="forbid")

    document_id: Optional[str] = None
    page: Optional[int] = Field(default=None, ge=1)


class CampoRevisavel(BaseModel, Generic[T]):
    """Um valor extraído por IA com o estado da sua fiabilidade."""

    model_config = ConfigDict(extra="forbid")

    value: Optional[T] = None
    needs_review: bool = False
    confidence: Optional[Confianca] = None
    source: Optional[FonteDoCampo] = None
    edited_by_human: bool = False

    @model_validator(mode="before")
    @classmethod
    def _texto_vazio_e_nada(cls, dados: Any) -> Any:
        if isinstance(dados, dict):
            valor = dados.get("value")
            if isinstance(valor, str) and not valor.strip():
                dados = {**dados, "value": None}
        return dados

    @model_validator(mode="after")
    def _sem_valor_e_a_rever(self) -> "CampoRevisavel[T]":
        # Um campo em falta NUNCA é «tudo bem». Excepção: o que uma pessoa
        # deixou vazio de propósito (`edited_by_human`) já foi revisto.
        if self.value is None and not self.edited_by_human:
            self.needs_review = True
        return self


def campo_em_falta() -> "CampoRevisavel[Any]":
    """Campo que a IA não conseguiu ler: `value=None`, a rever."""
    return CampoRevisavel(value=None, needs_review=True)


# ====================================================================
# METADADOS PROFISSIONAIS (colecção `process_professional_metadata`)
# ====================================================================
class TrabalhoProfissional(BaseModel):
    """Um emprego (um processo pode ter vários recibos de entidades diferentes)."""

    model_config = ConfigDict(extra="forbid")

    job_id: str
    employer_nif: CampoRevisavel[str] = Field(default_factory=campo_em_falta)
    employer_name: CampoRevisavel[str] = Field(default_factory=campo_em_falta)
    job_title: CampoRevisavel[str] = Field(default_factory=campo_em_falta)
    net_salary: CampoRevisavel[Decimal] = Field(default_factory=campo_em_falta)
    contract_type: CampoRevisavel[TipoDeContrato] = Field(default_factory=campo_em_falta)
    #: Localidade/concelho/distrito da sede da entidade patronal (dado da EMPRESA, não do cliente).
    #: Opcional e NÃO revisável: serve a pesquisa avançada por zona e nunca põe um trabalho «a rever».
    #: Análises anteriores à pesquisa avançada não a têm até serem extraídas outra vez.
    employer_location: Optional[str] = Field(default=None, max_length=80)
    #: Data de admissão (YYYY-MM-DD). Só vem de uma Declaração de Efetividade (um recibo não a traz) e
    #: não é revisável por pessoas (sem editor): se a declaração a leu com dúvida, não chega aqui.
    admission_date: Optional[str] = None
    #: O tipo de contrato (e a admissão) vêm da Declaração de Efetividade, que tem precedência
    #: absoluta sobre os recibos (decisão da direcção, Out 2026). Nunca editável: é um facto derivado.
    certified_by_declaration: bool = False
    #: De quem é o emprego (`titular1`/`titular2`), só em processos com 2.º titular: o titular dos documentos
    #: de origem (o marcador do ficheiro manda, não a conta que o enviou). `None` com um só comprador.
    titular: Optional[str] = Field(default=None, pattern=r"^titular[12]$")
    period: Optional[str] = None
    source_document_ids: list[str] = Field(default_factory=list)

    @field_validator("period")
    @classmethod
    def _periodo(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        if not _PERIODO.match(v):
            raise ValueError("período tem de ser YYYY-MM")
        return v

    @field_validator("admission_date")
    @classmethod
    def _admissao(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        try:
            return date.fromisoformat(v).isoformat()
        except ValueError as exc:
            raise ValueError("a data de admissão tem de ser YYYY-MM-DD") from exc

    @field_validator("employer_location", mode="before")
    @classmethod
    def _localidade(cls, v: Any) -> Optional[str]:
        """Texto simples numa linha, ou `None`: um texto longo ou vazio não é uma localidade."""
        if v is None:
            return None
        texto = " ".join(str(v).split())[:80]
        return texto or None

    @model_validator(mode="after")
    def _reforcar_nif(self) -> "TrabalhoProfissional":
        """O CÓDIGO reforça a IA: um NIF que não passa o dígito de controlo vai a rever."""
        campo = self.employer_nif
        if campo.value is not None:
            normal = normalizar_nif(campo.value)
            campo.value = normal
            if normal is None or not nif_e_valido(normal):
                campo.needs_review = True
        return self

    def campos_a_rever(self) -> list[str]:
        return [
            nome
            for nome in ("employer_nif", "employer_name", "job_title", "net_salary", "contract_type")
            if getattr(self, nome).needs_review
        ]


class ProfessionalMetadata(BaseModel):
    """Documento da colecção `process_professional_metadata` (um por processo)."""

    model_config = ConfigDict(extra="forbid")

    process_id: str
    network_id: Optional[str] = None
    jobs: list[TrabalhoProfissional] = Field(default_factory=list)
    has_pending_review: bool = False
    analysis_fingerprint: Optional[str] = None
    updated_at: Optional[datetime] = None
    expire_at: Optional[datetime] = None

    @model_validator(mode="after")
    def _derivar_has_pending_review(self) -> "ProfessionalMetadata":
        # Derivado, nunca declarado: uma flag à mão diverge dos campos.
        self.has_pending_review = any(j.campos_a_rever() for j in self.jobs)
        return self


def decimal_do_valor(valor: Any) -> Optional[Decimal]:
    """Converte texto/número em `Decimal`, ou `None` (não é um número). Aceita «1.234,56»."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, Decimal):
        return valor if valor.is_finite() else None
    if isinstance(valor, (int, float)):
        texto = str(valor)
    else:
        texto = re.sub(r"[^\d,.\-]", "", str(valor))
        if not texto:
            return None
        if "," in texto and "." in texto:
            # o ÚLTIMO separador é o decimal
            if texto.rfind(",") > texto.rfind("."):
                texto = texto.replace(".", "").replace(",", ".")
            else:
                texto = texto.replace(",", "")
        elif "," in texto:
            texto = texto.replace(",", ".")
    try:
        numero = Decimal(texto)
    except InvalidOperation:
        return None
    return numero if numero.is_finite() else None


# ====================================================================
# ENTIDADES PATRONAIS (colecção `employers`)
# ====================================================================
class Entidade(BaseModel):
    """Entidade patronal. Global (sem fronteira de rede) porque NÃO leva dados de clientes."""

    model_config = ConfigDict(extra="forbid")

    nif: str
    name: str
    first_seen_at: Optional[datetime] = None
    # SEM referência a processos nem a clientes. É isso que a torna pesquisável a todos.

    @field_validator("nif")
    @classmethod
    def _nif_valido(cls, v: str) -> str:
        normal = normalizar_nif(v)
        if not normal or not nif_e_valido(normal):
            raise ValueError("NIF inválido")
        return normal

    @field_validator("name")
    @classmethod
    def _nome(cls, v: str) -> str:
        v = " ".join((v or "").split())
        if not v:
            raise ValueError("nome vazio")
        return v


# ====================================================================
# MATRIZ DE VERIFICAÇÃO (colecção `process_index_alerts`)
# ====================================================================
Severidade = Literal["info", "aviso", "alerta"]

#: Tabela FECHADA: código → (severidade, mensagem em pt-PT). A mensagem nunca vem de um modelo.
ALERTAS: dict[str, tuple[str, str]] = {
    "recibo_sem_credito": (
        "aviso",
        "O líquido de um recibo de vencimento não aparece como crédito no extrato do mês.",
    ),
    "contas_nao_batem": (
        "aviso",
        "As contas de um recibo não batem certo (bruto, descontos e líquido).",
    ),
    "nif_invalido": ("alerta", "O NIF da entidade patronal não é válido."),
    "nif_entidade_incoerente": (
        "aviso",
        "O NIF do recibo não corresponde ao da entidade já conhecida com este nome.",
    ),
    "saldo_nao_bate": (
        "aviso",
        "O saldo de um extrato não bate certo com os movimentos listados.",
    ),
    "movimento_estranho": (
        "aviso",
        "Há movimentos no extrato que merecem confirmação (valores ou padrões atípicos).",
    ),
    "recibo_irreal": (
        "alerta",
        "Um recibo tem dados incoerentes com a realidade (datas, entidade ou IBAN).",
    ),
    "extrato_em_falta": (
        "info",
        "Não há extrato do mês de um recibo: não foi possível confirmar o crédito do ordenado.",
    ),
    "identificacao_expirada": ("aviso", "Um documento de identificação está fora de validade."),
    "identificacao_ilegivel": (
        "aviso",
        "Não foi possível reconhecer o tipo de um documento de identificação.",
    ),
    "analise_falhou": (
        "info",
        "A análise automática não terminou: os campos ficaram por preencher, a rever.",
    ),
    "sanitizacao_falhou": (
        "aviso",
        "Não foi possível gerar o PDF limpo: os originais foram mantidos.",
    ),
}
CODIGOS_DE_ALERTA = tuple(ALERTAS)


class RefDocumento(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: Optional[str] = None
    page: Optional[int] = Field(default=None, ge=1)


class AlertaDaMatriz(BaseModel):
    """Um alerta. NENHUM bloqueia a indexação (princípio 1)."""

    model_config = ConfigDict(extra="forbid")

    id: str
    process_id: str
    network_id: Optional[str] = None
    code: str
    severity: Severidade = "aviso"
    message: str = ""
    #: A JUSTIFICAÇÃO exacta do achado (valores, datas, diferenças), calculada pelo código a partir dos
    #: factos — a mensagem da tabela é genérica e, sozinha, não diz à pessoa o que confirmar. Não entra
    #: na assinatura (`key`): reescrevê-la nunca ressuscita um alerta dispensado. Nada pessoal.
    detail: Optional[str] = Field(default=None, max_length=600)
    refs: list[RefDocumento] = Field(default_factory=list)
    dismissed_by_human: bool = False
    created_at: Optional[datetime] = None
    run_id: str
    #: Assinatura estável do achado (código + documentos + período): é o que faz um alerta
    #: dispensado NÃO ressuscitar quando a matriz corre outra vez.
    key: Optional[str] = None

    @field_validator("detail", mode="before")
    @classmethod
    def _detalhe_limpo(cls, valor: Any) -> Optional[str]:
        """Texto simples, numa linha e com tecto: nunca HTML nem um texto longo vindo de fora."""
        if valor is None:
            return None
        texto = " ".join(str(valor).split())[:600]
        return texto or None

    @model_validator(mode="after")
    def _da_tabela(self) -> "AlertaDaMatriz":
        if self.code not in ALERTAS:
            raise ValueError(f"código de alerta desconhecido: {self.code!r}")
        # Severidade e mensagem vêm SEMPRE da tabela, venha o que vier no pedido.
        self.severity, self.message = ALERTAS[self.code]  # type: ignore[assignment]
        return self


# ====================================================================
# ESTADO DE CADA FICHEIRO (em `document_metadata`)
# ====================================================================
class EstadoDoFicheiro(BaseModel):
    model_config = ConfigDict(extra="forbid")

    ai_category: Optional[str] = None
    ai_subtype: Optional[SubtipoDeIdentificacao] = None
    analysis_fingerprint: Optional[str] = None
    file_state: EstadoDoFicheiroLiteral = "original"
    clean_pdf_path: Optional[str] = None
    clean_pdf_sha256: Optional[str] = None
    purge_after: Optional[datetime] = None

    @model_validator(mode="after")
    def _subtipo_so_na_identificacao(self) -> "EstadoDoFicheiro":
        # O subtipo só faz sentido na categoria Identificação; a categoria é única.
        if self.ai_subtype is not None:
            self.ai_category = CATEGORIA_IDENTIFICACAO
        return self
