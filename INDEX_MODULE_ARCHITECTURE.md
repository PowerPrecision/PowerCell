# Módulo Index (Lote 12) — Arquitetura técnica

Estado: **aprovada (Out 2026). Fases 1 (Dados) e 2 (Motor) implementadas; 3 (Endpoints+RBAC), 4 (Frontend) e 5
(Sanitização+purga) por fazer.** Escrita sobre o código que existe hoje; onde o pedido colide com ele, está assinalado em
**⚠ Decisão**. As divergências entre o desenho inicial e o que ficou implementado estão na secção 10.

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

## 10. O que ficou implementado nas Fases 1 e 2 — e onde divergiu do desenho (Out 2026)

**Fase 1 — Dados.** `services/index_status.py` (ponto único, derivação pura `derivar_estado`/`estado_apos`, `reivindicar`/
`devolver_a_fila`, `condicao_da_fila`, contadores), `models/index_module.py` (`CampoRevisavel`, `TrabalhoProfissional`,
`ProfessionalMetadata`, `Entidade`, `AlertaDaMatriz`, tabela `ALERTAS`), colecções e índices em `db_indexes.py`,
`scripts/migrar_index_status.py` (omissão só lê; `--aplicar`; idempotente; concorrência optimista). Os escritores de
`skip_index` (`aplicar_regime_de_indexacao` — o gancho dos cinco escritores de processos —, `process_update`, a triagem B2B) e de
`is_indexed` (`process_indexing`) passam todos pelo ponto único; guarda por AST proíbe um `index_status` escrito à mão.

Divergências:

1. **`is_indexed` NÃO é `index_status == "indexed"` para os dispensados.** O desenho dizia-o; aplicado aos processos de Via
   Verde / rede sem Index viraria `is_indexed` para `True` em todos e mudava, sem erro, o que as listas de «por indexar», o
   filtro e a fila do indexador devolvem. Fica `indexed` + `index_skipped=True` e `is_indexed` só é verdadeiro quando uma
   PESSOA indexou.
2. **Datas em ISO-8601 (texto)** nos campos de `processes` (como o resto da colecção), `datetime` nas colecções novas.
3. **Legado sem `index_status` lê-se como a derivação dá** (`condicao_da_fila` tolera o campo ausente): a migração é
   conveniência, não pré-requisito do deploy.
4. **Job activo único** por `task_logs.index_job_key` (índice único parcial `idx_index_job_activo_unico`), retirado ao terminar;
   um job morto liberta-se passados 30 minutos. Não há colecção nova de jobs.

**Fase 2 — Motor.** `services/index_ai.py` (esquemas por tipo, normalizadores, impressão digital, simulação),
`index_matrix.py` (pura), `index_store.py` (persistência), `index_jobs.py` (job + notificação).

Divergências e decisões:

1. **Nada pessoal do cliente é pedido ao modelo nem guardado** (decisão do dono do produto: «não preciso que os dados pessoais
   do cliente fiquem guardados»). Da identificação só saem o subtipo (`cc`/`bi`/`passaporte`/`titulo_residencia`, sempre na
   categoria «Identificação») e se está expirada; do recibo, a entidade patronal (NIF e nome), o cargo, o tipo de contrato e o
   líquido; do extrato, números e datas — a contraparte de um movimento reduz-se a uma impressão digital de 12 hex (para
   detectar «a mesma pessoa várias vezes») e o texto morre à entrada. **Consequência:** o ponto 5 da Luz Verde («identificação
   sem NIF → null + needs_review») aplica-se ao «Extrair dados» para a ficha (que já revê tudo), não aos metadados do Index.
2. **Os factos numéricos de cada ficheiro vivem em `document_metadata.index_facts`** (e o trabalho em `index_job`), não só em
   memória: a matriz cruza recibos com extratos e um ficheiro saltado por impressão digital continua a ter de contar. Os
   metadados profissionais são **recalculados** a partir deles em cada corrida (idempotente; um recibo apagado deixa de contar),
   e as edições humanas (`edited_by_human`) sobrevivem, casando por `job_id` OU documentos de origem em comum.
3. **A impressão digital é do CONTEÚDO**, não do caminho: o ficheiro lê-se do S3 (barato) e é o `sha256` que decide se há
   chamada paga. Um ficheiro substituído no mesmo caminho volta a ser analisado.
4. **Só entra no directório global de entidades** um NIF válido (dígito de controlo), com nome, e sem dúvida (ou confirmado por
   uma pessoa): um NIF mal lido não pode poluir o que todos os Index pesquisam. O primeiro nome ganha.
5. **Códigos de alerta acrescentados à tabela:** `saldo_nao_bate`, `extrato_em_falta` (informativo — falta de prova não é
   prova de falta), `analise_falhou` (informativo). Os achados da IA sobre extratos só valem se o valor (e a data) existirem num
   movimento; recorrência e saldo recalculam-se em código.
6. **Modelo:** tarefa `index_analysis` no painel de IA (`config.AI_CONFIG_DEFAULTS`); dev simula (`INDEX_AI_PROVIDER`).
7. **Ainda NÃO ligado:** os gatilhos automáticos (`mark-indexed` e upload depois de indexado — hoje a IA corre à entrada na
   pasta `Index`), os endpoints `/api/index/*`, o RBAC do perfil Index nas rotas de IA, o frontend, a sanitização e a purga.
   `iniciar_analise(process_id, user, force=, gatilho=)` é o ponto de entrada que a Fase 3 liga.

### Fase 3 — API, RBAC e fecho (Out 2026)

`routes/index_module.py` (`/api/index/*`, stubs finos) → `services/index_api.py` (fila, bancada, claim/release, analisar/extrair,
edição humana, dispensar alertas, directório) e `services/index_finalize.py` («marcar como indexado» + job de fecho).

Decisões e divergências:

1. **RBAC:** `PAPEIS_DE_IA_DO_INDEX` = os altos perfis + Indexação (Master/Admin/CEO/Diretor/Indexação), pelo perfil EFECTIVO.
   Consultor e Intermediário: 403 e o handler nunca corre. **A regra QA-5 não mudou** (`PAPEIS_DE_GESTAO_DA_IA` ainda não inclui a
   Indexação): o Index só tem IA nestas rotas novas. Marcar como indexado mantém a lista de sempre (Master/Admin/CEO/Indexação).
2. **Router:** rede (404) ANTES do estado fechado (403). Todas as rotas são limitadas e declaram `response: Response`.
3. **A fila segue o âmbito de PROCESSOS** (dono + convidadas, `build_tenant_process_condition`) e não traz metadados
   profissionais; a bancada traz-os. O directório de entidades é global PORQUE só tem NIF e nome.
4. **«Marcar como Indexado» nunca é bloqueado** (IA em baixo, campos em dúvida, alertas abertos). O diálogo dos NIFs é opcional;
   um NIF que não se aplica volta em `employers.rejected` e a indexação segue; a permissão vem ANTES de tocar nos metadados.
5. **O fecho (`INDEX_FINALIZE`)** é lançado por `run_mark_indexed_side_effects`, DEPOIS de libertar a pasta `Index` e do motor
   financeiro, e nunca condiciona a indexação: analisa o que falta (impressão digital), gera o PDF limpo, notifica.
   Um job activo por processo (mesmo índice único).
6. **Divergência assumida — a categorização à entrada da `Index` mantém-se.** O desenho dizia «a IA só corre ao marcar
   indexado»; a categorização (barata, QA-5) alimenta a libertação da pasta e os pedidos do Portal e já está provada. O que passou
   a ser condicional é a **extracção do Index** (a cara): só em «marcar como indexado», em uploads posteriores à indexação e a pedido.
7. **Uploads depois de indexar** (`document_upload`, `document_direct_upload`) criam o registo mínimo em `document_metadata`
   (um processo indexado não passa pela fila da IA, logo não havia registo) e lançam a análise; marcam `uploaded_by_index`.
   Limite: a análise lê a categoria/subcategoria/nome do ficheiro — sem categorização, só os nomes reconhecíveis são analisados.
8. **Achado:** `GET /index/employers` com pontuação («.*») devolvia o directório inteiro (a normalização tirava a pontuação e
   uma expressão vazia casa com tudo).
9. **Não feito (dito):** o cartão «Documentação validada» do Consultor (a rota seria nova, fora de `/api/index`, e o dono não
   pediu ver dados do cliente) e o painel «Agente» do desenho.

### Fase 4 — Frontend

`/index` (`IndexDashboardPage`: abas «Fila de Espera» e «Revisões Pendentes», estado no URL) e `/index/:processId`
(`IndexWorkstationPage`: documentos, metadados, matriz, painel lateral de revisão, diálogo de NIFs). Hooks com tempo real por
eventos `task_*` (o polling só corre enquanto há job activo E o WebSocket está em baixo). O menu mostra «Indexação» ao Index e
aos altos perfis; `App.rotasMenu.test.js` cruza menu e rotas (e o leitor passou a não deixar um spread de outro grupo apagar um
item literal do bloco do perfil).
Achado: **duas escritas funcionais seguidas ao URL pisam-se** (`setSeparador` + `setPagina(1)`): o react-router parte as duas do
URL do render actual. A mudança de aba faz UMA escrita.

### Fase 5 — PDF limpo e purga (decisão FINAL da direcção, 21 Out 2026)

`services/index_sanitize.py`.

1. **Um PDF limpo por documento distinto** — nunca `recibos.pdf` nem `extratos.pdf`. Só se funde o que se PROVA ser o mesmo
   documento, e só imagens: extrato = mesmo IBAN e mês (fotos de páginas); identificação = exactamente UMA frente e UM verso do
   mesmo tipo (a identificação passou a dizer a **face**, `ESQUEMA_VERSAO` = 2); recibos e PDFs nunca. Na dúvida, separado
   (duas frentes e dois versos = duas pessoas). Limite honesto: uma foto de uma página de extrato sem cabeçalho (sem IBAN/mês) não
   se consegue juntar às outras.
2. **Só os ficheiros que o Index carregou** (`document_metadata.uploaded_by_index`).
3. **Graça de 30 dias** (`INDEX_PURGE_GRACE_DAYS`; um valor inválido ou ≤0 cai nos 30 — nunca encurta).
4. **Aditivo primeiro:** gravar o PDF limpo ao lado do original (chave exacta, nunca sobrescreve), **relê-lo** do S3 e só então
   mudar o estado (`sanitizado`, `clean_pdf_path`, `clean_pdf_sha256`, `purge_after`). Qualquer falha deixa os originais intactos,
   apaga a cópia má e deixa o alerta `sanitizacao_falhou` (aviso) e uma linha no Log da IA.
5. **O PDF está mesmo limpo:** sem metadados, XMP, anexos, JavaScript (também ao nível do catálogo), EXIF (re-codifica a imagem)
   nem autor das anotações. **Medido** — e dois achados: o `scrub` do PyMuPDF deixa `/OpenAction` JavaScript (copia-se só as
   páginas para um documento novo) e deixa o autor de realces/comentários (apagam-se as notas adesivas e limpam-se as chaves
   de autoria das visíveis). `verificar_pdf_limpo` lê o PDF como o leitor mais exigente o leria.
6. **Purga DESLIGADA por omissão** (`INDEX_PURGE_ENABLED=true`, também em produção). Repete a verificação (hash + páginas +
   limpeza) à cópia limpa ANTES de apagar, só purga grupos inteiros vencidos, repõe os pedidos do Portal (sem duplicados) e só
   depois apaga o original do S3 (com repetição se o S3 falhar). Corre no `scheduled_tasks`.
7. **`file_state: purgado`** deixa de significar «já não conta»: os DADOS lidos de um original eliminado continuam verdadeiros
   (inverteu-se o teste da Fase 2); só os BYTES desapareceram, logo não se re-analisa. O PDF limpo é um registo próprio
   (`is_clean_pdf`) que a análise e o motor financeiro ignoram (senão contava-se duas vezes).
8. **Antes de ligar a purga em produção:** auditar as referências a um original que não sejam o `document_metadata` e os
   pedidos do Portal (ficheiros do Parceiro por `file_id`, a Origem Financeira; o Explorador mostra ambos os ficheiros durante a graça).

### Afinações (Out 2026)

Resumo; o detalhe e as lições estão no `AGENTS.md` («Afinações do Index»).

1. **Fila:** só processos activos (fase não terminal no workflow da rede dona) e coluna «Empresa/Origem» (`company`).
2. **Documentos:** o Index lê os pedidos do Portal (`GET /documents/portal-requests/{id}`); escritas continuam fechadas.
3. **Saída da Index sem consultor forçado:** a omissão deixou de atribuir; só a configuração explícita da fase atribui.
4. **Menu lateral:** o grupo da rota activa abre-se a partir do próprio menu e o estado sobrevive à navegação.
5. **Bancada:** nome e nº do processo são ligações para o detalhe (novo separador); cada alerta tem `detail` calculado pelo código
   (a IA só dá uma nota saneada, anexada a um movimento verificado). A contraparte continua sem ser guardada.
6. **Pesquisa avançada:** `GET /api/index/advanced-search` (um resultado por emprego; salário numérico; fronteira de processos
   no `$lookup`). Novo campo opcional `employer_location`. (As declarações de efetividade entraram depois: ver abaixo.)

### Pesquisa por documento: declarações, recibos isolados e extratos por banco (Out 2026)

Resumo; o detalhe e as lições estão no `AGENTS.md` («Pesquisa avançada por DOCUMENTO»).

1. **Tipo novo `declaracao_efetividade`:** só dados da entidade e do vínculo (NIF, nome, localidade, `admission_date`, contrato
   certificado). Não gera «emprego»; alimenta o directório `employers`. `ai_subtype` = slug, `ai_subcategory` = rótulo.
2. **Extrato:** `bank_name` obrigatório no esquema; `services/index_banks.py` canonicaliza (chave estável, palavras inteiras,
   banco desconhecido guardado como lido, IBAN só como recurso e nunca guardado).
3. **Colecção `process_index_documents`:** uma linha por ficheiro analisado (líquido numérico), reconstruída — não acumulada —
   no fim de cada análise e em cada correcção humana; nada pessoal.
4. **`GET /index/advanced-search?document_type=recibo|declaracao_efetividade|extrato&bank=…`:** vista por documento
   (`view: "documents"`); sem `document_type` a vista por emprego fica igual. Filtro que não existe no tipo = 422.
5. **Sem reanálise retroactiva:** `ESQUEMA_VERSAO` não mudou. `scripts/backfill_index_documentos.py` reconstrói a projecção
   do que já foi analisado, sem IA.

### Precedência da declaração e «Ver documento» (Out 2026)

Detalhe e lições no `AGENTS.md` («Declaração de Efetividade manda no emprego…»).

1. **Precedência absoluta:** `contract_type` e `admission_date` da declaração mandam sobre os recibos no emprego
   (`index_store.aplicar_declaracoes`). Só enriquece empregos existentes; casa por NIF válido e depois por nome; a mais
   recente ganha; confiança «baixa» → `needs_review` / admissão não propagada; a edição humana vence. Novos campos do emprego:
   `admission_date`, `certified_by_declaration`.
2. **`GET /index/documents/{document_id}/content`:** pré-visualização por id (recibo/extrato/declaração), 404 uniforme fora do
   âmbito, posse da chave S3, streaming partilhado com o da lead (`previsualizacao_de_ficheiros`).
3. **`/index/pesquisa`:** ecrã da pesquisa avançada com o «Ver documento» num `Dialog` sobreposto; o payload leva
   `document_id` (vista por documento) / `document_ids` (vista por emprego), nunca nomes de ficheiro.

