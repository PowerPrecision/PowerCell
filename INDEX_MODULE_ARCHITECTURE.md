# Módulo Index (Lote 12) — Arquitetura técnica

Estado: **proposta para aprovação** (nada disto está implementado). Escrita sobre o código que existe hoje; onde o pedido
colide com ele, está assinalado em **⚠ Decisão** e as perguntas que bloqueiam estão na secção 9.

## 0. Princípios (vindos do pedido e das respostas anteriores)

1. **Zero bloqueios.** Nenhum resultado de IA (falha, campo em dúvida, alerta da matriz) impede «Marcar como Indexado».
   Tudo o que a IA não consegue garantir vira aviso (`needs_review`, alerta), nunca recusa.
2. **Tudo em background.** Análise, extração, sanitização e purga correm como jobs (`TaskLog` + eventos `task_*` que já
   existem). O fim do job gera notificação ao indexador (um documento em `notifications` por destinatário).
3. **A IA propõe, a pessoa dispõe.** A IA automática **categoriza e extrai para os metadados do Index**; **nunca grava na
   ficha do cliente**. A ficha só é preenchida pelo botão «Extrair dados» + revisão (regra já em vigor).
4. **Um ficheiro que já passou pela IA não volta a passar** (impressão digital: `sha256` + versão do esquema).
5. **Sem fuga de dados de clientes.** A pesquisa global é sobre **entidades patronais**, não sobre trabalhadores (ver 3.3).
6. **O que se apaga primeiro tem cópia verificada.** Nunca se purga um original sem um PDF limpo gerado e verificado.

## 1. Estado do processo: `index_status`

Hoje há `is_indexed` (bool), `skip_index` (Via Verde) e `hub_triage.state` (fila). Há ~10 leitores de `is_indexed`
(`document_visibility`, `document_intake`, `network_triage`, `process_assignment`, `email_archive`…).

```
pending ──claim/abrir workstation──▶ in_review ──mark-indexed──▶ indexed
   ▲                                     │                          │
   └─────────── devolver à fila ─────────┘            set-indexed OFF (reabre; os originais purgados não regressam)
```

* `index_status ∈ {"pending","in_review","indexed"}` no documento do processo, **escrito por um único módulo**
  (`services/index_status.py`, ponto único como o `process_indexing`). `is_indexed` **mantém-se, derivado**
  (`is_indexed = index_status == "indexed"`), gravado no mesmo `$set`: os ~10 leitores não mudam.
* `skip_index` (Via Verde / rede sem Index) → `index_status="indexed"` + `index_skipped=true`. Nunca entra em fila nem
  em revisões; não há purga (não há originais particionados).
* Migração (`scripts/migrar_index_status.py`, só lê por omissão, `--aplicar`, idempotente): `is_indexed:true → indexed`;
  `false/ausente → pending`; `hub_triage` com indexador atribuído → `in_review`.
* `in_review` é transição **de conveniência** (o dashboard mostra «a ser tratado por X»); não bloqueia ninguém de abrir.

## 2. Esquemas de dados

### 2.1 Processo (campos novos, só estado e contadores — nada pessoal)

```python
class IndexEstado(BaseModel):                       # no documento do processo (denormalizado para a fila)
    index_status: Literal["pending", "in_review", "indexed"] = "pending"
    index_skipped: bool = False
    indexed_at: Optional[datetime] = None
    indexed_by: Optional[str] = None                # omitido para perfil silenciado (history._is_stealth_user)
    has_pending_review: bool = False                # ⇐ qualquer campo needs_review=True (ver 2.2)
    index_alerts_open: int = 0                      # nº de alertas da matriz ainda não dispensados
```

Índices (declarados em `db_indexes.py`, não à mão): `{network_id, index_status, created_at}` (Fila de Espera) e
`{network_id, has_pending_review, indexed_at}` (Revisões Pendentes).

### 2.2 Metadados profissionais — **colecção própria** `process_professional_metadata`

**Não** vão dentro do documento do processo: o modelo do processo é `extra="allow"` e já vazou dados por aí
(origem financeira, serviço do parceiro). Mesma regra: colecção separada, um documento por processo, só lida por módulos
do Index (inventário por AST).

Um processo pode ter **vários trabalhos** (vários recibos) ⇒ lista de entradas.

```python
Confianca = Literal["alta", "media", "baixa"]

class CampoRevisavel(BaseModel, Generic[T]):
    value: Optional[T] = None                       # null quando a IA não sabe
    needs_review: bool = False                      # True se inseguro OU em falta (value=None ⇒ sempre True)
    confidence: Optional[Confianca] = None
    source: Optional[FonteDoCampo] = None           # {document_id, page} — nunca o texto lido
    edited_by_human: bool = False                   # True ⇒ a IA nunca mais sobrescreve este campo

class TrabalhoProfissional(BaseModel):
    job_id: str
    employer_nif: CampoRevisavel[str]
    employer_name: CampoRevisavel[str]
    job_title: CampoRevisavel[str]
    net_salary: CampoRevisavel[Decimal]             # Decimal, não float
    contract_type: CampoRevisavel[Literal["efetivo", "termo_certo", "termo_incerto", "outro"]]
    period: Optional[str] = None                    # mês do recibo (YYYY-MM)
    source_document_ids: list[str] = []

class ProfessionalMetadata(BaseModel):
    process_id: str                                 # índice único
    network_id: str                                 # carimbo (a pesquisa fecha nele)
    jobs: list[TrabalhoProfissional] = []
    has_pending_review: bool                        # derivado de jobs[*].*.needs_review (recalculado ao gravar)
    analysis_fingerprint: str                       # sha256 dos ficheiros + versão do esquema ⇒ não volta a correr
    updated_at: datetime
    expire_at: Optional[datetime] = None            # TTL se a política de retenção o exigir (decisão RGPD)
```

Regras: `value=None ⇒ needs_review=True` (validador Pydantic); `edited_by_human=True` blinda o campo contra reanálise;
retirar a flag é um `PATCH` explícito do indexador (2.5), nunca implícito.

### 2.3 Diretório de entidades patronais — colecção `employers`

```python
class Entidade(BaseModel):
    nif: str                                        # índice ÚNICO; validado (9 dígitos + dígito de controlo mod 11)
    name: str
    first_seen_at: datetime
    # SEM referência a processos nem a clientes.
```

É isto que torna os dados «globalmente pesquisáveis» sem atravessar a fronteira de rede nem o RGPD: o Index digita/confirma
um NIF e o sistema devolve o nome (e vice-versa). Contagens («quantos processos desta rede têm este empregador») saem
de `process_professional_metadata` filtrado por `network_id` — nunca de fora.

⚠ **Decisão A — «globalmente pesquisável».** O pedido diz que `job_title` e `net_salary` ficam pesquisáveis globalmente.
Isso é dado pessoal do trabalhador atravessando redes (o Domus veria o salário de um cliente da Power) e contraria o
que ficou acordado («não preciso de ver os dados do cliente»). Desenho proposto: **entidade global, trabalhador por rede**
(`employers` global; `process_professional_metadata` pesquisável só dentro do `network_id`).

### 2.4 Ficheiros — estado por ficheiro (em `document_metadata`, já existente)

```python
class EstadoDoFicheiro(BaseModel):
    ai_category: Optional[str] = None               # categoria atribuída (todos os tipos de identificação → «Identificação»)
    ai_subtype: Optional[Literal["cc", "bi", "passaporte", "titulo_residencia"]] = None
    analysis_fingerprint: Optional[str] = None
    file_state: Literal["original", "sanitizado", "purgado"] = "original"
    clean_pdf_path: Optional[str] = None            # chave S3 do PDF limpo (quando existe)
    clean_pdf_sha256: Optional[str] = None
    purge_after: Optional[datetime] = None          # ver Decisão B
```

### 2.4.1 Matriz de verificação — colecção `process_index_alerts`

Um documento por alerta (não uma lista gigante no processo): permite dispensar, contar (`index_alerts_open`) e expirar.

```python
class AlertaDaMatriz(BaseModel):
    id: str
    process_id: str
    network_id: str
    code: str                                       # fechado: ver tabela
    severity: Literal["info", "aviso", "alerta"]    # NENHUM bloqueia
    message: str                                    # pt-PT, gerada por código (nunca texto livre da IA)
    refs: list[RefDocumento] = []                   # {document_id, page}
    dismissed_by_human: bool = False
    created_at: datetime
    run_id: str                                     # a corrida que o gerou (substituível)
```

| code | verificação | quem calcula |
|---|---|---|
| `recibo_sem_credito` | o líquido do recibo (±tolerância) aparece como crédito no extrato do mês | código (determinístico) |
| `contas_nao_batem` | bruto − descontos ≠ líquido; taxa de SS ≠ 11 %/23,75 %; retenção de IRS fora do plausível | código |
| `nif_invalido` / `nif_entidade_incoerente` | dígito de controlo; NIF do recibo ≠ NIF da entidade já conhecida com esse nome | código + `employers` |
| `movimento_estranho` | levantamentos/depósitos em numerário atípicos, transferências recorrentes para a mesma pessoa, saldo que não bate com os movimentos | **IA**, validada por código (o valor/data citados têm de existir no extrato) |
| `recibo_irreal` | datas incoerentes, mês futuro, entidade sem NIF, IBAN do crédito ≠ IBAN do titular | código + IA |
| `identificacao_expirada` / `identificacao_ilegivel` | validade passada; tipo não reconhecido | código |

A IA devolve **achados estruturados**; as mensagens e as severidades vêm de uma tabela no código. Um achado que cite
um valor que não existe no documento é descartado (um modelo não é uma parede).

### 2.5 Jobs

Reutilizar `TaskLog` (tipo novo `INDEX_ANALYSIS`, `INDEX_SANITIZE`, `INDEX_FINALIZE`) e os eventos `task_*` que o frontend
já escuta. **Não criar uma fila nova.** Um job activo por (processo, tipo) (a lição do D-29: índice único parcial).

## 3. Backend — endpoints FastAPI

Router `routes/index_module.py` (`/api/index`), serviços `services/index_*.py` (rota fina + `run_*`, como o resto). Todas as
rotas com `{process_id}`: `exigir_processo_no_ambito` (404 uniforme) e `exigir_processo_editavel` conforme a tabela.
`@limiter.limit` + `response: Response` em todas as que escrevem ou chamam o modelo.

| Método e caminho | Quem | O que faz |
|---|---|---|
| `GET /index/queue?tab=pending\|reviews&page=` | Index, gestão | **Dashboard.** `pending` = `index_status ∈ {pending,in_review}`; `reviews` = `indexed ∧ has_pending_review`. Só a rede do utilizador. DTO positivo: nº do processo, nome do cliente, nº de ficheiros, nº de alertas — **sem** metadados profissionais. |
| `GET /index/processes/{id}` | Index, gestão | **Workstation.** Estado, jobs activos, metadados profissionais, alertas, ficheiros e estado de cada um. |
| `POST /index/processes/{id}/claim` | Index | `pending → in_review` (idempotente). |
| `POST /index/processes/{id}/analyze` | Index, gestão | Cria o job de análise (categoriza, extrai metadados, matriz). **202 + `task_id`.** `force=false` salta ficheiros com a mesma impressão digital. |
| `POST /index/processes/{id}/extract` | Index, gestão | O «Extrair dados» que já existe (`/processes/{id}/documents/extract`): devolve propostas para a ficha, **não grava**. Mantém-se tal como está. |
| `POST /index/processes/{id}/sanitize` | Index, gestão | Job que gera os PDF limpos (sem metadados do PDF). Idempotente. |
| `PATCH /index/processes/{id}/professional-metadata/{job_id}` | Index, gestão | Painel lateral. Body `{campo: {value, needs_review?}}`. Escrever um valor marca `edited_by_human` e, por omissão, `needs_review=false`; recalcula `has_pending_review`. |
| `POST /index/processes/{id}/mark-indexed` | Index, gestão | **Sempre permitido** (zero bloqueios). Body opcional `{employers: [{job_id, nif}]}` (o NIF por recibo, pré-preenchido pela IA). Grava `indexed`, dispara `INDEX_FINALIZE` e **devolve imediatamente**. |
| `POST /index/alerts/{id}/dismiss` | Index, gestão | Dispensa um alerta (rasto no trilho). |
| `GET /index/employers?q=` | Index, gestão | Pesquisa por NIF ou nome (diretório global, ver 2.3). |

`mark-indexed` actual (`PATCH /processes/{id}/mark-indexed`) **passa a delegar** neste serviço: um só escritor do estado.

### 3.1 O pipeline `INDEX_FINALIZE` (corre depois de «Marcar como Indexado», em background)

```
1 libertar a pasta Index  (index_release: já existe — move para as categorias; sem IA)
2 analisar o que falta    (só ficheiros sem impressão digital; campos em dúvida ⇒ null + needs_review)
3 gerar PDF limpo         (por categoria; sem metadados do PDF)  → verificar (nº de páginas + sha256 relido do S3)
4 purga dos originais     (Guilhotina) — SÓ dos ficheiros cujo PDF limpo foi verificado no passo 3
5 notificar o indexador   (notifications + evento task_completed; resumo: «3 alertas, 2 campos a rever»)
6 motor financeiro        (já existe; corre sobre o PDF limpo)
```

Cada passo é idempotente e independente: se o 2 falha, os campos ficam `null`+`needs_review` e o pipeline **continua**;
se o 3 falha, o 4 **não corre** (originais intactos) e fica um alerta `sanitizacao_falhou`. Nunca se devolve erro a quem
clicou: a indexação já está gravada.

**Corrida a evitar:** «Marcar como Indexado» enquanto uma análise manual ainda corre. O passo 4 espera pelo job
activo de análise (tecto de espera) e, se expirar, purga na mesma **depois** de gravar `null+needs_review` nos campos em falta.
Nenhum job escreve metadados depois de o `run_id` ter sido substituído.

### 3.2 IA: Motor de Confiança (`services/index_ai.py`)

* Uma chamada por **tipo de documento** (recibos / extratos / identificação), com `tool_choice` forçado ao esquema
  `CampoRevisavel`. Sem Chain-of-Thought **persistido**: o raciocínio vai num campo `scratch` que se descarta antes de
  gravar (custo e privacidade — contém texto do documento).
* `needs_review=true` e `value=null` quando o modelo está inseguro ou o campo falta; **código** reforça: NIF que não
  passa o dígito de controlo ⇒ `needs_review`; valor monetário que não é número ⇒ `null`.
* Modelo escolhido no painel de admin (tarefa `index_analysis`), nunca fixo no código. Dev simula (`INDEX_AI_PROVIDER`);
  só produção com chave chama o modelo.
* Identificação: o modelo classifica **cc / bi / passaporte / titulo_residencia** (`ai_subtype`); a categoria é sempre
  «Identificação». Um esquema de campos por subtipo (BI e passaporte não têm NIF no mesmo sítio).
* Impressão digital: `sha256(conteúdo) + versão_do_esquema` ⇒ não se reanalisa.
* Gatilhos automáticos (mudam face ao que está em produção): **removida** a IA à entrada na pasta Index (Portal, Parceiro,
  staff). Passa a correr em dois momentos — `mark-indexed` (passo 2 do pipeline) e **upload depois de indexado** —, e só
  categoriza + extrai para os metadados do Index. `document_ai_trigger.agendar_ia_da_entrada` é adaptado, não apagado.

### 3.3 Pesquisa

* Entidades (`employers`): qualquer perfil Index/gestão, sem fronteira de rede (não há dados de clientes).
* Metadados profissionais: `build_network_scope_condition` sobre `process_professional_metadata.network_id`.
* Índices: `{employer_nif}` único em `employers`; `{network_id, jobs.employer_nif.value}`; `{process_id}` único.

### 3.4 RBAC

| Perfil | Fila/Workstation | Analisar | Extrair | Sanitizar | Marcar indexado |
|---|---|---|---|---|---|
| Index (`indexacao`) | ✔ | ✔ | ✔ | ✔ | ✔ |
| Master / Admin / CEO / Diretor | ✔ (dentro da rede) | ✔ | ✔ | ✔ | ✔ |
| Consultor / Intermediário | ✘ | ✘ | ✘ | ✘ | ✘ |

Implementação: `PAPEIS_DE_IA_DO_INDEX = PAPEIS_DE_GESTAO_DA_IA + [INDEX]` numa constante; `document_ai_access` passa a
admitir o Index **só** nestas rotas (a regra QA-5 mantém-se para as restantes). O ecrã lê `pode_usar_ia_documentos` do
servidor, como hoje. O perfil Index continua **silencioso** (`history._is_stealth_user`): o log e o trilho não levam o nome.

### 3.5 Consultor

O consultor **não** vê metadados, matriz nem PDFs limpos antes de indexado: vê um cartão «Documentação» com o histórico de
submissão (quem enviou, quando) e, depois de `indexed`, «Documentação validada». A regra de visibilidade pré-indexação
(`document_visibility`) já faz o resto.

## 4. Frontend

```
pages/index/
  IndexDashboardPage.jsx          tabs «Fila de Espera» | «Revisões Pendentes»   (rota /index)
  IndexWorkstationPage.jsx        rota /index/:processId
components/index/
  IndexQueueTable.jsx             tabela pura (props), paginada, URL-state (kb_*-style: useEstadoNaUrl)
  IndexActionsBar.jsx             Analisar · Extrair dados · Sanitizar (apagar metadados) · Marcar como Indexado
  AlertMatrix.jsx                 lista por severidade; dispensar
  ProfessionalReviewPanel.jsx     <Sheet> lateral com os campos; amarelo quando needs_review
  RevisavelField.jsx              input + selo; editar ⇒ edited_by_human
  EmployerNifDialog.jsx           NIF por recibo ao marcar (pré-preenchido; pode saltar)
  JobProgressToast.jsx            liga a useTaskEvents (já existe)
components/processDetails/
  DocumentacaoValidadaCard.jsx    o que o consultor vê (histórico + conclusão)
hooks/queries/
  useIndexQueueQuery.js           chave com tab+página (o filtro vai SEMPRE na chave)
  useIndexWorkstationQuery.js
  useIndexMutations.js            analyze / sanitize / patch / mark / dismiss (skipErrorToast onde a recusa é esperada)
utils/
  indexRevisao.js                 PURO: campos a amarelo, `has_pending_review`, payload do PATCH só com o que mudou
```

* **Workstation:** o `S3FileManager` (DocManager) à esquerda, Matriz de Alertas e `IndexActionsBar` à direita; o
  painel lateral abre por cima. **Sem split-screen com o processo original.**
* **Anti-bloqueio:** «Marcar como Indexado» nunca fica `disabled` por causa de IA/validação; só durante o próprio pedido
  (sem duplo envio). O diálogo do NIF tem sempre «Marcar sem confirmar NIF».
* **Assíncrono:** `useTaskEvents` actualiza o estado do job; ao terminar, toast + notificação; o polling continua
  como recuo (regra do projecto: não apagar o fallback).
* **Revisões Pendentes:** abre o **PDF limpo** (`clean_pdf_path`, via proxy do backend — nunca URL pré-assinado), o
  painel mostra só os campos a amarelo primeiro; «Guardar» limpa a flag e o `has_pending_review` do processo.
* **Menu e rotas concordam** (`App.rotasMenu.test.js`): `/index` para `indexacao` + gestão, e nada para consultor/intermediário.
* **Falhas secundárias não sujam o ecrã:** as leituras auxiliares da workstation usam `skipErrorToast` (como acabámos de
  fazer no detalhe do processo).

## 5. Guilhotina S3 — como fazê-la sem perder dados

⚠ **Decisão B — a purga é irreversível e toca em seis sítios que hoje apontam para os originais:**
(1) `attached_files[].s3_path` dos pedidos do Portal (o cliente vê/descarrega); (2) `document_metadata.s3_path`;
(3) o `index_release` (que MOVE os originais para as categorias — a purga acontece depois); (4) o motor financeiro
(lê `s3_path`); (5) `set-indexed OFF` (reabrir não repõe nada); (6) o Parceiro (descarrega por `file_id`).
Desenho: **purga em dois tempos** — o passo 4 marca `file_state="purgado"` e grava `purge_after = agora + GRACA`
(por omissão 0 se o dono confirmar «imediata»); um job apaga o objecto S3 depois da graça. Em ambos os casos
os registos passam a apontar para `clean_pdf_path`, e `purgado=true` fica visível no Log da IA. Sem verificação
do PDF limpo, **não há purga**. Interruptor `INDEX_PURGE_ENABLED` (desligado até validar em dev).

## 6. Fases de entrega (cada uma com os seus testes e mutações)

1. **Dados:** `index_status` (+ migração + ponto único + derivação de `is_indexed`), colecções e índices.
2. **Motor:** `index_ai` (esquema por tipo, subtipos de identificação, impressão digital), matriz determinística, jobs.
3. **Endpoints + RBAC** (Index nas rotas de IA), `mark-indexed` delegado, pipeline `INDEX_FINALIZE` sem purga.
4. **Frontend:** dashboard, workstation, painel de revisão, cartão do consultor.
5. **Sanitização + purga** (atrás do interruptor, só depois de aprovada a Decisão B).

Testes que não podem faltar: «Marcar como Indexado» responde 200 com a IA em baixo, com campos em falta e com alertas
abertos; nenhum original é purgado sem PDF limpo verificado (mutação: remover a verificação); a reanálise não corre sobre o
mesmo `analysis_fingerprint`; um campo `edited_by_human` nunca é sobrescrito; uma pesquisa de um Index da rede A nunca
devolve metadados da rede B; o consultor e o intermediário recebem 403 nas rotas do Index (o handler nunca corre).

## 7. O que já existe e se reutiliza

`index_release` (mover da pasta Index), `document_intake.planear_entrada`, `document_ai_access`, `process_indexing`
(passa a delegar), `TaskLog` + `task_events`, `useTaskEvents`, `document_vision_extract` («Extrair dados»), `process_ai_log`
(regista cada acção do Index), `S3FileManager`, `DocumentReviewModal`/`SugestoesIADrawer` (padrão de revisão), `NotaDoPedido`.

## 8. O que deixa de existir / muda

* IA à entrada na pasta Index (Portal/Parceiro/staff): removida (`document_ai_trigger` passa a ser chamado só no
  `mark-indexed` e em uploads pós-indexação).
* `is_indexed` deixa de ter escritores directos (só `index_status.py`).
* O Index ganha os botões de IA que hoje são só da gestão (QA-5 mantém-se para os outros perfis).

## 9. Perguntas que bloqueiam (com a minha proposta por omissão)

1. **«PDF limpo»:** é **um PDF por categoria** (recibos.pdf, extratos.pdf, identificação.pdf) ou um por ficheiro original?
   *Proposta: um por categoria, para o consultor e o Portal verem um documento coerente; o Portal do cliente passa a
   mostrar o PDF limpo no lugar dos originais.*
2. **Purga:** imediata ou com graça (p. ex. 30 dias)? *Proposta: graça configurável, 30 dias por omissão; «imediata» é só `GRACA=0`.*
3. **Pesquisa global:** confirma «entidades globais, trabalhadores por rede» (Decisão A)?
4. **Retenção** dos metadados profissionais (salário líquido, cargo): prazo? *Proposta: o mesmo do processo; TTL por `expire_at`.*
5. **Identificação sem NIF** (passaporte, título de residência): quando o NIF do titular só vier do recibo/ficha, a IA
   propõe-o com `needs_review=true`, correcto?
