# Registo de Dívida Técnica — PowerCell

Dívida **conhecida, avaliada e adiada de propósito**. Não é uma lista de
desejos nem um caderno de ideias: cada entrada foi encontrada a resolver outra
coisa, foi medida, e a decisão de não a fechar naquele momento foi tomada por
escrito.

Isto existe porque dívida que vive só em comentários de código não é um
registo — ninguém a lê toda, ninguém a prioriza, e ela reaparece como
incidente. Quando uma entrada for fechada, sai daqui e entra no `worklog.md`
com a iteração que a fechou.

**Ao acrescentar uma entrada:** o que está mal, por que razão foi adiado,
quem é atingido se explodir, e o que é preciso para a fechar. Sem estes
quatro, é um comentário e não uma dívida.

---

## Segurança

### D-24 · O registo público não carimba a rede, e a Sala de Triagem é global
**Onde:** `services/public_registration.py`, `services/client_registered.py`
(`build_tenant_pool_condition`)

**O que já fechou** (iteração `fronteira-da-carteira`, 2026-10-09): as três
superfícies de dados que esta entrada media — a carteira de angariações
(`db.properties`, DOZE módulos sem uma única ocorrência de `compan` ou
`network`), o Smart Match (o JOIN sem âmbito em nenhuma das pontas) e os
registos financeiros (`company_id` da query string como «fronteira»). Detalhe
no `worklog.md`.

**O que fica**, e fica porque depende de uma decisão de produto e não de
código: `public_registration.py` tem zero ocorrências de `resolve_tenant_stamp`.
Hoje funciona por o lead cair na pilha por carimbar — e a **Sala de Triagem é
uma POOL** (`build_tenant_pool_condition`), que por desenho mostra o que não
tem carimbo a **TODAS** as redes. É o *claim-based routing*: um registo
público ainda não é de ninguém, e escondê-lo de quem não é da rede de omissão
faz com que nunca seja reivindicado.

Somado a um **formulário público único**, que não sabe de que empresa é, a
consequência é directa: **todo o lead público fica visível às duas redes**, a
Domus incluída. Não é um defeito do isolamento, é o isolamento a aplicar uma
regra que foi escrita quando havia só um grupo.

**Porque está adiado:** as duas saídas são decisões de negócio opostas e
nenhuma é obviamente certa. (a) O formulário passa a saber a empresa — um link
por empresa/rede (`?company=`), e o lead nasce carimbado: a Pool deixa de ser
partilhada e cada rede trata dos seus. (b) A Pool continua global e passa a
ser uma SALA DE ENTRADA explícita, com os dados mínimos à vista até alguém
reivindicar — o que obriga a decidir que campos são «mínimos» (nome sem
contacto? sem NIF?).

**Quem é atingido:** com uma ilha no sistema, qualquer registo público. Hoje
não há utilizadores activos da Domus, logo não está a acontecer.

**Para fechar:** a decisão (a) ou (b); depois disso o carimbo na escrita é
pequeno (`resolve_tenant_stamp` no `public_registration`) e a Pool passa a
`build_tenant_condition` ou mantém-se com projecção reduzida.

---

## Correcção e modelo de dados

### D-15 · A data de nascimento é PII e está em claro
**Onde:** `backend/services/encryption.py` (`SENSITIVE_FIELDS`,
`CLIENT_SENSITIVE_FIELDS`), `personal_data.birth_date` /
`personal_data.data_nascimento`, `dados_pessoais.*`.

O NIF, o documento de identificação, a morada fiscal e o telefone são
encriptados em repouso. A **data de nascimento não está em nenhuma das duas
listas** — está em texto simples em `processes` e em `clients`. Com o nome,
é dos campos que mais contribui para identificar uma pessoa, e a avaliação
de impacto do RGPD trata-a como PII.

**Porque foi adiado (Lote 4):** encriptá-la **parte o filtro Sub35**. A
condição Mongo de `services/sub35.py` compara a data com um limite
(`$gte`/`$lt` sobre a data ISO), o que só funciona em claro. Encriptar
exigiria uma das três: (a) um blind index por FAIXA (um campo derivado
`nascimento_ano` ou `sub35_ate`, que tem de ser recalculado — e um valor
derivado gravado volta a ficar errado no dia do aniversário, que é o
defeito que o Lote 4 acabou de fechar); (b) filtrar em Python depois de
desencriptar, o que obriga a ler a colecção inteira; (c) aceitar que o
filtro deixa de existir.

**Decisão registada (Lote 5):** o dono do produto confirmou o adiamento —
fica para uma sprint dedicada à criptografia, de propósito, para não partir o
filtro Sub35 recém-construído.

**Medição disponível (Lote 5):** `python scripts/medir_datas_de_nascimento.py`
(só leitura, só contagens, nenhum valor no output) diz em que colecções e
campos a data existe, quantas estão em claro, quantas já estão cifradas e
quantas não são nem uma coisa nem outra (lixo que uma migração teria de tratar
à mão). Correr em produção antes da decisão.

**O que é preciso para fechar:** decidir entre o filtro e a encriptação, com
o DPO. Se a escolha for encriptar, a opção (a) com um campo `ano_de_nascimento`
(não a idade, não um booleano) é a única que não quebra a pesquisa nem precisa
de recálculo: o ano não muda, e o limiar de "menos de 36" calcula-se sobre ele
com uma margem de um ano a resolver em Python.

## Infraestrutura e custos

### D-13 · Custos do MongoDB Atlas: sem camadas de dados (Épico)
**Onde:** infraestrutura — colecções `processes`, `history`,
`system_error_logs`, `activities`, `audit_trail`, `emails`

A factura do Atlas passou de ~50 para ~100 USD/mês. Os índices e TTLs deste
lote atacam os **varrimentos**; o que falta é arquitectura: **tudo vive na
mesma camada quente**, incluindo dados que nunca mais são lidos.

Isto é um ÉPICO e não uma entrada normal: são várias mudanças independentes,
cada uma com o seu risco, e a ordem importa porque a barata mede o efeito da
caras.

**Porque foi adiado:** mexer em retenção e arquivo é irreversível por natureza
(dados movidos ou apagados não voltam) e exige uma decisão de negócio sobre
prazos legais de conservação — RGPD e obrigações de conservação de processos
de crédito não são as mesmas para um processo e para um log.

**Quem é atingido:** a factura, hoje. E a latência amanhã: uma colecção quente
que cresce sem limite acaba por não caber na RAM da instância, e aí a
degradação não é linear.

**Passos, do mais barato ao mais caro:**

1. **MEDIR antes de mover.** *(Ferramenta pronta, Lote 5:
   `python scripts/medir_colecoes.py [--csv f]` — só leitura, `collStats` por
   colecção + idade por escalão 30/90/180/365 dias, contando datas
   `datetime` E texto ISO; falta CORRÊ-LA em produção e colar a tabela no
   `worklog.md`.)* `db.stats()` por colecção (tamanho de dados,
   tamanho de índices, contagem) e o *Performance Advisor* do Atlas. Sem isto
   arrisca-se arquivar a colecção errada: a intuição diz `history`, os números
   podem dizer `emails` (que guarda corpos de mensagens). **Nenhum passo
   seguinte começa sem esta tabela.**
2. **TTL nas colecções de diagnóstico.** `system_error_logs` já tem TTL de 30
   dias; `audit_trail` tem retenção por endpoint mas não TTL nativo. Um TTL é
   uma linha em `db_indexes.py` e o mongod faz o resto — é o melhor retorno
   por unidade de risco. **Excepção explícita: o `audit_trail` é conformidade**
   (IP e retenção legal) e a retenção dele é decisão jurídica, não técnica.
3. **`history` e `activities` para o S3, em vez de para o Mongo.** São
   *append-only*, lidas quase só na timeline de um processo e nunca agregadas.
   Candidatas a um ficheiro JSON por processo no bucket, com a leitura a cair
   para lá quando o documento não está no Mongo. **O risco real:** a timeline
   é a prova de quem fez o quê — uma escrita perdida é um buraco no histórico,
   por isso a escrita tem de continuar síncrona no Mongo e a migração só move
   o que já lá está e está fechado.
4. **Online Archive do Atlas para processos com mais de 1 ano em estado
   terminal.** `concluido`/`perdido` + `updated_at` há mais de 365 dias. O
   Archive é transparente para leitura (via *federated queries*) e muito mais
   barato. **Duas armadilhas:** as consultas federadas são LENTAS e não servem
   um ecrã interactivo — o CRM tem de saber que um processo arquivado abre com
   um aviso; e o critério tem de ser `updated_at`, não `created_at`, senão
   arquiva-se um processo antigo que voltou a mexer.
5. **Só depois, redimensionar a instância.** Mudar de tier antes de arrumar os
   dados é pagar mais pelo mesmo problema.

**Para fechar:** os cinco passos, cada um com a medição antes e depois no
`worklog.md`, e a decisão de negócio sobre prazos de conservação escrita antes
do passo 2.

---

## Produto e âmbito

### D-39 · Colisão B2B: os ficheiros do parceiro ficam na pasta do registo dele
**Onde:** `services/b2b_client_match.py`, `services/partner_drafts.py::_associar_a_cliente_existente`

Quando a lead de um parceiro corresponde a um cliente que já existe na rede de
destino (NIF primeiro, email só sem NIF), associa-se a ele em vez de nascer outro
— sem tocar nos contactos do destino. O que **não** se fez: os ficheiros que o
parceiro enviou antes da libertação ficam na pasta do **registo dele**
(`Documentação Clientes/{lead_id}/…`), não na do cliente existente. A entrada
`partner_leads` do cliente guarda `pasta_dos_documentos_do_lead` para a
consolidação manual.

**Porque foi adiado:** mover objectos S3 é a operação que partiu 205 ligações no
Épico 10; a pasta de posse deriva do id do cliente, logo re-apontar `db.documents`
sem mover faria o proxy recusar a chave (403). Qualquer das duas é uma decisão
sobre S3, não sobre a regra de identificação.

**Para fechar:** um passo explícito da equipa (religar/consolidar com
`s3_relink`) ou uma cópia controlada para a pasta do cliente, com `db.documents`
re-apontado no mesmo acto. Fica também por decidir se, sem correspondência por NIF
mas com email/telemóvel iguais aos de OUTRO cliente da rede, a libertação deve
mesmo criar o registo (hoje cria e marca `possible_duplicate_of`: o NIF diz que é
outra pessoa, e perder uma lead paga por um email partilhado é pior).

### D-40 · A unicidade de NIF/Email/Telemóvel é aplicacional (sem índice único)
**Onde:** `backend/services/client_uniqueness.py`; medição em `scripts/diagnose_client_duplicates.py`

A guarda do D-38 verifica antes de gravar. Dois pedidos simultâneos com o mesmo
contacto podem passar os dois (corrida residual). Só um índice único parcial por
rede sobre os blind indexes (`network_id` + `*_hash`, ignorando eliminados e
vazios) a fecha — e esse índice **recusa-se a nascer** enquanto houver duplicados
na base, porque a regra é nova e os dados são antigos.

**Porque foi adiado:** antes de decidir é preciso saber quantos casos existem.
O diagnóstico (só leitura) responde: corrê-lo em produção e ver «índice único
viável» ou o nº de casos a resolver à mão.

**Para fechar:** resolver os casos que o relatório listar (manter um cliente,
passar-lhe os processos, eliminar o outro — decisão humana) e declarar o índice
em `db_indexes.py` (nunca num passo de operações). O `network_id` por carimbar
(rede de omissão) e a rede da empresa sem carimbo têm de ser tratados no índice
(ou backfill prévio), senão a pilha antiga escapa-lhe.

### D-41 · Resto das acções destrutivas só-Master sem password
**Onde:** restauro de backups (`/restore*`), migrações e resets de processos (`admin_migration`, `admin_process_migration`), reset de permissões

A reautenticação por password (`reauth_password`) cobre hoje: repor ao modelo, eliminar uma
empresa, alterar o `network_id`, a anonimização em lote **e a individual** (`/gdpr/anonymize`,
fechada em Out 2026) — todas com UI (`ConfirmarComPasswordDialog`). Ficaram de fora, por não
estarem no pedido, as operações de infraestrutura que só o Master alcança: restauro de backups,
migrações/resets de processos e reset de permissões.

**Para fechar:** decidir quais merecem a mesma parede e acrescentá-las ao inventário
`test_accoes_destrutivas_com_password.py::TestInventario::COM_PASSWORD`; quem criar UI usa o
`ConfirmarComPasswordDialog`.

### D-18 · `co_buyers`: falta correr a migração dos dados em produção
**Onde:** `backend/scripts/migrar_co_buyers_adicionais.py`, `backend/services/co_buyers_migration.py`

O CÓDIGO está fechado (Lote 5): o mapeador do CPCV passou a gravar só os
compradores ADICIONAIS (`i > 0`), como o `build_add_client_update` sempre fez,
e o campo tem um só significado. Falta o DADO: os processos analisados pelo
mapeador antigo têm o titular 1 em `co_buyers[0]`.

**Porque está aberta:** a migração escreve em produção e só se pode correr com
a base de dados à frente. O script é conservador — remove `co_buyers[0]` só
quando a sua identidade normalizada (NIF/CC em dígitos, nome sem acentos) é
EXACTAMENTE a do titular 1; tudo o resto fica e é listado. A omissão só lê;
`--aplicar` escreve; idempotente.

**Enquanto não correr:** a desduplicação por identidade em `sub35.py` mantém-se
(é o que impede a regra de se desligar a si mesma). Depois de uma passagem
limpa pode simplificar-se.

**Para fechar:** `python scripts/migrar_co_buyers_adicionais.py` (ver o plano),
`--aplicar`, repetir até «0 a migrar», e então remover a desduplicação.

### D-28 · O `history` não leva carimbo de rede
**Onde:** colecção `history`, `services/executive_report.py`

As CONTAGENS de mudanças de fase do relatório executivo são por pessoa do âmbito
(o mesmo contrato do relatório que existia antes): uma pessoa que trabalha em
duas redes tem na rede A as mudanças que fez na rede B. A lista de movimentos já
filtra pelos processos do âmbito; as contagens não. Fechar exige carimbar
`history` (escritor único `log_history`) e migrar o legado — adiado por ser um
escritor central e por o impacto ser só em quem trabalha em duas redes.

### D-30 · Os scrapers do Estado e dos portais só se provam em produção
**Onde:** `services/gov_scraper.py`, `services/scraper.py`

Sem rede nem credenciais reais, tudo o que se prova é a orquestração (política,
estado, arquivo, MFA) e a camada estruturada contra HTML de fixture. Os
selectores do Portal das Finanças e da Segurança Social Direta (`FINANCAS_SEL`,
`SEG_SOCIAL_SEL`) continuam a ser os do código anterior e **não foram
validados contra os portais**; o `gov_scraper` tem ~3 000 linhas num módulo só,
com dois fluxos inner quase gémeos. O que fecha isto: um relatório de
selectores falhados por execução (passo e selector, sem credenciais) e uma
rotina de verificação mensal com uma conta de teste; só depois faz sentido
partir o módulo.

### D-34 · Conteúdo global escrito por perfis locais (o fecho do processo fechado está concluído)
**Onde:** `routes/changelog.py`; guarda em `services/process_closed_guard.py`

**Fechado (Out 2026):** a equipa não altera nem escreve num processo em fase
terminal (403) em nenhuma superfície: campos, ficheiros e notas; mover no
Kanban (mesmo entre fases terminais), mensagens ao cliente, link do Portal,
origem financeira, serviço do parceiro, registos financeiros, `unlink-process`
e — na última passagem — **emails/modelos** (`routers emails e templates`,
`send-documentation`, rascunhos), **análise e geração de documentos por IA**
(`ai_analysis`, `document_extraction`) e **`link-process`**. Sem excepção por
cargo: reabre-se com `POST /processes/{id}/reopen`.

**As excepções são QUATRO, escritas e afirmadas por igualdade num teste:**
reabrir, eliminar o processo, revogar uma partilha e `POST /emails/sync/{id}`
(só lê do servidor de email — não decide nada sobre o processo). A excepção de
**pagamentos** é a única de negócio e vive no estado financeiro, não na rota:
confirmar um pagamento (pendente/faturado → pago) é permitido com o processo
fechado, porque as comissões se pagam no fim; o resto das finanças continua
fechado (ver AGENTS.md).

**O que continua aberto, de propósito e dito:** as **semanas já fechadas** do
relatório executivo guardam os números com que foram registadas (ainda com
Admin/Master nas linhas) — um registo é um registo.

**Fechado (Out 2026):** a geração por IA (`POST /system/changelog/generate-ai`),
o diagnóstico (`/diagnose`) e a marca Premium são **só-Master**. Admin e CEO
são perfis locais e o conteúdo é global (todas as redes veem as mesmas
novidades). As três rotas partilham UMA constante,
`PAPEIS_QUE_ESCREVEM_O_CHANGELOG`, em `services/changelog_api_premium.py`, e um
inventário por AST falha se uma rota de escrita nova a esquecer. Ler continua a
ser de toda a equipa.

### D-36 · Directório de redes no diálogo «Partilhar com…»
**Onde:** `services/process_sharing_api.py::run_list_share_targets`, `PartilharComRedeDialog.jsx`

Para escolher a rede de destino, quem pode partilhar (master/admin/ceo/diretor/
administrativo da casa dona) vê o **nome das empresas das outras redes** que têm
Index. Num modelo multi-fornecedor isso é necessário, mas significa que a
existência e o nome de uma empresa-cliente do sistema é visível a outra. Se uma
rede não quiser ser listada, falta um interruptor `listavel_para_partilha` na
empresa (ou uma lista de fornecedores aprovados por rede). **Decisão de produto.**

### D-37 · Workflow por rede: o que ficou de fora (a parte dos formulários FECHOU)
**Onde:** `services/workflow_scope.py`, `services/form_config_scope.py`

Os **formulários** (`form_config`) fecharam na iteração `formularios-por-rede-e-mercado-b2b`
(ver «Fechadas»). Do **workflow** por rede ficam, assumidos:
(a) um processo **convidado** (partilhado) mostra as colunas/rótulos com as fases
de QUEM OLHA, e a semântica (fechado, portal) com as da rede dona;
(b) os contadores de carga dos pools usam a união das fases terminais de todas as
redes (aproximação); (c) não há ainda botão «repor ao modelo» — apagar a cópia de
uma rede à mão repõe a leitura do modelo; (d) editar o MODELO (`network_id`
ausente) só se faz por script.
**Novos, da iteração dos formulários:** (e) um link de registo **sem** `?empresa=`
(links antigos) cai no formulário da rede de omissão e deixa o cliente por
carimbar (Pool) — mantém os links existentes a funcionar, mas é o que se deve
substituir pelos links por empresa; (f) o directório «Empresa de Destino» do
Portal do Parceiro expõe o nome das empresas das redes com Index a qualquer
parceiro activo (o mesmo compromisso do D-36); (g) ~~a **Via Rápida**~~ — **extinta** (Out 2026, ver «Fechadas»).
**Em aberto, da iteração da Via Rápida:** (h) ~~`GET /users/{id}` devolvia qualquer utilizador a qualquer staff~~ — **fechada** (Out 2026): 404 fora do âmbito, ver «Fechadas»; (i) os processos que a Via Rápida antiga já partilhou mantêm a partilha até alguém a revogar à mão — não se migra, por decisão de produto; (j) ~~a dropdown do Master listava todos~~ — **fechada** (Out 2026): `?process_id=` limita-a ao alcance do processo, ver «Fechadas».

### D-35 · Bloco A/B/C: o que ficou de fora, dito
**Onde:** `services/network_triage.py` (ex-`hub_triage.py`; o Hub único acabou — ver AGENTS.md), `services/partner_drafts.py`, `services/financial_validation.py`, `services/tenant_network.py`

**Fechado (Out 2026):** as listagens de «Os Meus Clientes» e mais seis superfícies passaram a perguntar a rede; o Hub & Spoke (triagem no Hub, Via Verde); o filtro de viabilidade do Parceiro; a validação financeira; a expiração aos 60 dias.

**O que continua aberto, de propósito:**
1. **`TENANT_DEFAULT_NETWORK_ID` por definir em produção** deixa a pilha por carimbar visível a todas as redes (agora é `error` no log). Verificar o serviço de deploy. E uma conta **órfã** (sem empresa nenhuma, só possível em contas antigas) herda a rede de omissão — desenho do Lote 4, para não cegar contas antigas; novas contas nunca nascem órfãs.
2. **`via_verde` é lida na altura da partilha.** Ligá-la depois de o processo ter entrado na triagem do Hub não o tira de lá (o primeiro registo ganha). Uma partilha revogada à mão e refeita NÃO repete a triagem. **A Via Verde não atribui um consultor do Hub**: a partilha nasce da atribuição de alguém do Hub, e assume-se que é essa pessoa quem trata da consultoria; se a pessoa atribuída for só mediador, o processo fica sem consultor do Hub até alguém o atribuir (acrescentar um segundo consultor automaticamente mexe nos campos canónicos de atribuição — a família do `assignment_drift`).
3. **Rejeitar um PROCESSO fecha-o por escrita directa** (`transicao_de_fase` + `montar_update`), não pelo movimento do Kanban: não dispara as automações de entrada na fase. É deliberado (uma rejeição não é um avanço de negócio) mas é uma segunda via para fechar um processo.
4. **Uma lead expirada não se revive**: o parceiro submete uma nova (o duplo clique dos 10 minutos não a apanha). Reactivar é uma decisão de produto.
5. **O que existe em `db.clients` de parceiros ANTES desta mudança** não tem `validacao_financeira` (sem selo) — tratado como já aceite.
6. **Inventário das superfícies que LISTAM:** fica com excepções escritas (`SEM_CONDICAO_DE_REDE_POR_DESENHO`); `GET /documents/client/{id}/*`, `/task-logs/{id}` e `/portal/{id}/verify` continuam na D-31.
**O que fecha isto:** confirmar a variável em produção; decidir 2–4 com o dono do produto.

### D-31 · Rotas «por id» sem pergunta de rede: fechadas as de clientes, tarefas, restauro, rascunhos, documentos e task-logs
**Onde:** `services/by_id_scope.py`, `services/document_path_scope.py`, `routes/clients.py`, `routes/tasks.py`, `routes/restore.py`, `routes/documents.py`, `services/task_logs_api_actions.py`, `services/email_templates_drafts.py`

**Fechado (Out 2026):** `GET/PUT/DELETE /clients/{id}` (e as restantes rotas
com `{client_id}`), `GET/PUT/DELETE /tasks/{id}` (e `complete`/`reopen`), os
três `/…/restore` por id e `PUT/POST send/DELETE /emails/drafts/{id}` +
`POST /emails/drafts/create` respondem **404 igual ao de «não existe»** para
um objecto de outra rede. Duas dependências de router
(`exigir_cliente_no_ambito`, `exigir_tarefa_no_ambito`) mais o
`exigir_processo_no_ambito` que já existia; testes montam os routers REAIS.
**Três ramos que NÃO são «a rede do carimbo» e existem por motivo escrito:**
a Pool (registo público sem carimbo, sem processo, por reivindicar —
claim-based routing); o cliente que é titular de um processo MEU (porque
`POST /clients` não carimbava e o cartão do titular do `ProcessDetails` abre
`GET /clients/{id}`) — a rede convidada de uma partilha conta só para
ler/editar, nunca para eliminar, atribuir ou criar processo; e, nas tarefas,
as atribuídas a mim ou criadas por mim. `POST /clients` passou a carimbar.

**Fechado (Out 2026, fecho da varredura por caminho):** `/documents/**` e
`/task-logs/{id}`, e a análise de `/portal/{client_id}/verify`.

* **`/documents/client/{client_id}/*`** (files, upload, init-folders, download,
  delete, bulk-delete) — o `{client_id}` é «flexível» (processo, cliente ou
  `client_id` de um processo) e a dependência `exigir_alvo_do_documento_no_ambito`
  resolve-o pela mesma ordem do handler, **incluindo o processo para onde o
  cliente aponta** (um cliente meu com vínculo a um processo de outra rede
  também fecha). O `init-folders` nem recebia o utilizador: escrevia
  `s3_folder` no processo de outra rede sabendo só o id. O router passou a
  levar `exigir_processo_no_ambito` + `exigir_alvo_do_documento_no_ambito`
  **antes** da guarda de processo fechado, o que também cobre todas as rotas
  com `{process_id}` (a guarda de visibilidade respondia **403**, que
  confirmava o id) e `{doc_id}` (`/{doc_id}/ai-analyze-review`, `apply-ai-review`,
  `reject-ai-review`: um registo sem dono não se prova meu — só o Master).
* **Os mesmos ficheiros pela chave S3** — `/documents/proxy/{path}`,
  `/documents/download-url/{path}` e `bulk-download` serviam qualquer chave
  dentro de `Documentação Clientes/` (a parede da raiz impede o
  `backups/*.zip`, não o cliente do vizinho). `services/document_path_scope.py`
  resolve o dono da chave (pasta mapeada ou id no caminho) e decide como a
  fronteira de documentos: rede convidada conta; sem dono → só o Master;
  reclamada por duas redes → ninguém; 404. O `process_id` do corpo do
  `bulk-download` também é um alvo (escrevia no histórico de outro processo).
  A guarda corre antes de perguntar ao S3 se a chave existe (sem oráculo).
* **`/task-logs/{id}`** — a excepção era `role in [master, admin, ceo]`, o
  cargo da conta sem pergunta de rede: o CEO da Domus lia, cancelava e
  apagava os registos da Power (que levam `process_name`). Hoje: o dono, o
  Master, ou Admin/CEO só para donos do seu âmbito
  (`carregar_utilizador_gerivel`); o resto é 404 (era 403).
* **`/portal/{client_id}/verify`** — **não há guarda de rede a pôr**: é uma
  porta pública, sem utilizador nem rede em contexto; a parede é a credencial
  (NIF + nº do processo) e o travão 5/15. O que se pode afirmar, e agora tem
  teste, é que a resposta **não distingue** «cliente de outra rede», «não
  existe», «NIF errado» e «processo alheio» (todos 401 com a mesma mensagem) e
  que o travão não distingue ids reais de inexistentes.

**Remate (Out 2026) — fechados os dois pontos que ficaram em aberto:**

* **Rotas com o `process_id` no corpo/query** — `services/by_id_scope.exigir_process_id_do_pedido_no_ambito`,
  4.ª dependência do router `/documents` (antes da guarda de processo fechado).
  Lê o `process_id` do **corpo JSON** e da **query** (nunca de multipart: o
  ficheiro inteiro não pode ficar em RAM antes do handler) e responde 404 igual
  ao de «não existe». Cobre `check-upload-conflict`, `generate-upload-url`,
  `confirm-upload`, `check-move-conflict`, `search`, `POST/GET /expiry` e
  `GET /categories`. Um `process_id` que não é texto (`{"$ne": null}`) é
  **400**, não ignorado: os handlers fazem `find_one({"id": ...})` e o operador
  devolvia o primeiro processo de qualquer rede. Achados ao varrer: o
  `check-move-conflict` **não tinha guarda nenhuma nem recebia o utilizador**
  (oráculo de «este ficheiro existe?»); e o `/search` **sem `process_id`
  percorria os metadados de todas as redes e devolvia URLs pré-assinados** —
  agora recortado aos processos do âmbito (`ids_de_processos_no_ambito`, rede
  convidada incluída, tecto de 5000 que corta para FECHADO). O `GET /categories`
  tinha o mesmo defeito (contagens de todas as redes).
* **`portal_verify_attempts` com TTL** — o registo ganha `expire_at` (BSON Date;
  o TTL ignora strings ISO) a cada falha, 30 min depois (`VERIFY_ATTEMPTS_TTL_MINUTES`,
  **maior que o bloqueio de 15** — um prazo menor desbloqueava o alvo a meio),
  e o índice `ttl_portal_verify_attempts` (`expireAfterSeconds: 0`) vive em
  `db_indexes.TTL_INDEXES`. Registos antigos: `scripts/backfill_portal_attempts_ttl.py`
  (omissão só lê; `--aplicar`; idempotente; nunca antes do fim de um bloqueio
  em curso) — **correr uma vez depois do deploy**.
  *Efeito colateral dito:* antes, quem esgotava as 5 tentativas ficava trancado
  **para sempre** (com `attempts >= 5` cada pedido renovava o bloqueio antes de
  olhar para a credencial); agora o contador volta a zero ≤ 30 min depois da
  última falha. Troca assumida: um atacante persistente tem 5 tentativas por
  30 min por `client_id` em vez de zero, mas o cliente legítimo deixa de ficar
  preso sem intervenção na base de dados.

**Remate 2 (Out 2026) — as duas dívidas finais do remate:**

* **TTL também no login por email** — `portal_login_attempts` (`portal_brute_force`)
  leva `expire_at` (BSON Date, deslizante) e o índice `ttl_portal_login_attempts`
  (`expireAfterSeconds: 0`). O prazo é **UMA constante para as duas portas**
  (`portal_brute_force.MINUTOS_DE_VIDA_DO_REGISTO` = 30; o `verify` deriva dela),
  maior que qualquer bloqueio (10 e 15). O bloqueio sem fim do login era o mesmo
  do `verify` (`esgotou_as_tentativas` re-trancava depois de `locked_until`).
  `scripts/backfill_portal_attempts_ttl.py` (ex-`backfill_portal_verify_ttl`)
  percorre as DUAS colecções (`COLECCOES_DE_TENTATIVAS`, com teste a exigir que
  coincida com as colecções que têm TTL em `expire_at`).
* **Pesquisa e categorias globais com a regra fina** — `/documents/search` e
  `/documents/categories` sem `process_id` já não recortam só por rede:
  `document_visibility.ids_de_processos_com_documentos_visiveis` aplica, por
  processo, a MESMA função pura da guarda individual
  (`user_can_view_process_documents`: rede com a convidada, bypass da gestão,
  pré-indexação, atribuição por todos os campos canónicos e relação com o cliente),
  e há um teste de **concordância** com `assert_can_view_process_documents`.
  As categorias passaram a aplicar também a guarda ao `?process_id=` (403 por
  indexar, 404 se não existe — antes devolvia contagens de qualquer processo da
  rede) e a parede da pasta `Index` a quem não a vê (contagem em memória; quem a
  vê continua na agregação do Mongo). Verificado contra `mongod` real
  (`tests/integration/test_pesquisa_pre_indexacao_mongo.py`): o duplo escondia
  a projecção.

**O que continua aberto (dito):**

* O recorte por processo enumera até 5000 processos do âmbito (e as categorias
  contam até 20000 documentos em memória para quem não vê a `Index`): ao cortar,
  vê-se menos, nunca mais, e há `warning`. Uma rede maior que isso precisa de um
  índice de visibilidade por documento.
* `/task-logs/{id}`: «cancelar» por um gestor que não é o dono responde 400 (o
  serviço filtra por `user_id`) — comportamento anterior, agora só acessível
  dentro do âmbito. E a excepção de gestão lê o cargo da CONTA, não o perfil
  efectivo (a rota não tem `Request`).
* `/admin/migration/run-single/{client_id}` é só-Master (sem fronteira de
  dados): não é fuga.

**Relacionado — fronteira de dados é a REDE, não a empresa.** Power e
Precision partilham rede por decisão do Lote 4, logo um Admin da Power vê os
dados da Precision. A gestão de utilizadores, os UCR, as configs de email e o
relatório de segunda-feira seguem a rede; só `system_config` é por empresa. Se
o dono do produto quiser isolamento por EMPRESA dentro da mesma rede, é um
carimbo novo em todas as colecções, não uma correcção desta adenda.

## Fechadas

Ficam aqui só o número e a iteração que as fechou — o detalhe vive no
`worklog.md`, que é o histórico. Uma dívida fechada não volta a este registo.

| # | Dívida | Fechada em |
|---|---|---|
| D-2 | Segredo JWT partilhado entre o Portal e o staff | Iteração `lote5-zero-debt` — `PORTAL_JWT_SECRET` próprio e OPCIONAL (`services/portal_jwt_secret.py`): definido, os tokens do Portal passam a ser assinados com ele e o verificador aceita os dois segredos durante a janela (`PORTAL_JWT_ACCEPT_LEGACY`, por omissão ligada), pelo que **nada se invalida**. Sem a variável, comportamento anterior. **Operação:** definir `PORTAL_JWT_SECRET` no serviço web e, passados ~90 dias (tempo de vida do magic link mais longo), pôr `PORTAL_JWT_ACCEPT_LEGACY=false`. Cobre também o WebSocket do Portal e o rate limit. `test_lote5_d2_segredo_proprio_do_portal.py` (23) |
| D-4 | Duas políticas de força bruta para as duas portas do Portal | Iteração `lote5-zero-debt` — a política é DADO (`Politica` por âmbito: login 8/10 min, verify 5/15 min, colecção própria) num só motor; o `verify` passou a usar o mesmo mecanismo que o login (ordem: recusar antes de olhar para a credencial; 400 não gasta tentativas; sucesso limpa; ler falha aberto). `test_lote5_d4_politicas_de_forca_bruta.py` (14) |
| D-6 | `INACTIVE_STATUSES` era resíduo legado e ainda decidia em `client_list_search` | Iteração `lote5-zero-debt` — as fases fechadas vêm do MOTOR (por rede) em `client_list_search`, `admin_observability`, `document_delete`, `client_me` e `process_kanban_diagnose`; a lista fica só como recurso de arranque. `test_lote5_d6_estados_fechados_vem_do_motor.py` (8) |
| D-10 | As definições de índices viviam dentro de `create_indexes` | Iteração `lote5-zero-debt` — `INDEX_DEFINITIONS` ao nível do módulo (`_definir`), `create_indexes` itera-o e `colecoes_com_indices` sai da mesma estrutura. **Equivalência provada** (gravando as chamadas ao driver antes e depois: os mesmos índices) e 113 índices criados e idempotentes num `mongod` real; o leitor por AST do teste foi substituído por um import |
| D-12 | Os limiares de SLA guardavam-se por empresa e liam-se globalmente | Iteração `lote5-zero-debt` — fechada pelo lado da ESCRITA: `dashboard_slas` é uma secção só-global (`SECCOES_SO_GLOBAIS`) e uma escrita por empresa é recusada, logo o que o ecrã grava é o que o leitor lê. **Decisão registada:** NÃO se construiu o leitor por empresa; se o negócio quiser limiares por rede, reabre-se com `_limiares(user)` e um selector. `test_lote5_d12_sla_so_global.py` (7) |
| D-27 | Os defaults por cargo do registo de capacidades não persistiam | Iteração `lote5-zero-debt` — `role_defaults_store`: os defaults persistem como overrides sobre os do código, relidos com TTL de 30 s no `get_current_user` (throttled para não pendurar pedidos com o Mongo em baixo); guarda-se só o DESVIO (`role_capability_defaults_v2`), nunca o retrato, para um deploy que mude um default do código não ser desfeito em silêncio. **O documento antigo NÃO se aplica** (não distingue edição de administrador de default da altura): mostra-se no log do arranque e no registo de capacidades (`legado_por_rever`) para o administrador repetir pelo ecrã o que ainda quer, e depois apaga-se. `test_lote5_d27_defaults_por_cargo_persistem.py` (24) |
| D-29 | Um job activo por processo não era atómico | Iteração `lote5-zero-debt` — índice único parcial `idx_scraper_job_activo_unico` (`process_id`, filtro `active: true`) + `JobJaActivo` no `DuplicateKeyError`; `active` desliga-se em TODA a saída de um estado activo. Provado contra `mongod` real com pedidos simultâneos (o duplo não implementa índices parciais): `tests/integration/test_d29_job_activo_atomico_mongo.py` (8) |
| D-38 | O registo público actualizava, sem prova de posse, um cliente já existente da mesma rede | Iteração `d38-duplicados-por-rede` — **NIF, Email e Telemóvel não se repetem dentro da rede**: o formulário público responde 409 genérico (`DUPLICATE_CLIENT`, sem id, nome nem campo — a porta é anónima) e não cria nem altera nada; o ramo de upsert foi apagado, não desligado. A criação e a edição do CRM passaram do âmbito GLOBAL para o da rede (o 409 devolvia o id e o nome de clientes de OUTRAS redes) e verificam também o telemóvel (com e sem indicativo, via blind index); na edição só se verifica o que MUDOU. `services/client_uniqueness.py` é o ponto único. Cobertura: `test_d38_duplicados_por_rede.py` (39), `tests/integration/test_duplicados_por_rede_mongo.py` (8, MongoDB real), `PublicClientForm.duplicado.test.jsx`. 14 mutações medidas, todas mortas |
| D-41 (parcial) | A anonimização individual (`/gdpr/anonymize`) era irreversível e não pedia password | Iteração `accoes-destrutivas-ui`: `AnonymizeRequest.password` exigida fora do `dry_run` (que é FALSO por omissão neste pedido, ao contrário do lote), depois da fronteira de rede (404 antes do 403) e antes de qualquer escrita; painel «Compliance › Anonimização» com diálogo. O resto das acções de infraestrutura continua em aberto (secção D-41) |
| D-14 | O formulário público podia criar um cliente com NIF repetido | Iteração `d38-duplicados-por-rede` — fechada pelo mesmo ponto: opção (c) (recusar com mensagem clara). Limite dito: o portal do parceiro (`partner_leads`) não recusa — marca `possible_duplicate_of` e a colisão B2B (D-39) resolve-se na libertação |
| D-8 | `db.emails`: faltavam as caixas partilhadas por cargo | Iteração `d8-caixas-partilhadas-por-rede` — o carimbo dos emails já estava fechado na escrita; faltava o que o impedia nas caixas partilhadas: a configuração era UMA por cargo para o sistema inteiro (o Admin da Domus editava, e ligava por OAuth, a Indexação da Power) e a regra «caixa partilhada do seu cargo» dava a todo o `indexacao` de todas as redes os emails de todas as redes. A caixa passa a identificar-se por **(cargo, rede)**: `shared_mailbox_scope` é o ponto único (administração pela rede da empresa activa; o email herda a rede da caixa; leitura só dentro do âmbito; o aviso em tempo real só a quem tem o email no âmbito, incluindo o da Caixa Geral). A pilha antiga (sem `network_id`) é da rede de omissão — nada se apaga nem se move. Backfill `scripts/backfill_shared_mailbox_network_id.py` (recusa-se sem rede) |
| D-32 | O registo público procurava e actualizava clientes em todas as redes | Iteração `d8-caixas-partilhadas-por-rede` — `POST /public/client-registration` é anónimo e escreve: procurava o email em toda a base de dados e **actualizava** o cliente encontrado (de qualquer rede), re-marcava-o como lead novo e devolvia o `client_id` e `is_new_client` (um oráculo). A procura vive agora na rede do link (`ambito_do_registo`: a rede + as suas empresas; a pilha por carimbar só conta para a rede de omissão); a mesma pessoa em duas redes são dois clientes; o aviso à gestão (push + email com nome, email e telefone) ia ao «primeiro admin da base de dados» e passa a ir só à gestão da rede do link; `is_new_client` saiu |
| D-34 (changelog) | Geração por IA e diagnóstico do changelog aceitavam Admin e CEO | Iteração `d8-caixas-partilhadas-por-rede` — só-Master, por uma constante única e inventário por AST |
| — | A Via Rápida (partilha implícita ao atribuir alguém de outra rede), antes ponto (g) da D-37 | Iteração `via-rapida-extinta` — apagada, não desligada. `assignment_network_guard` recusa a atribuição directa fora da rede (403 que aponta «Partilhar com Empresa…»), a lista de atribuíveis sai do servidor já filtrada (`/users` e `/users/staff` não tinham filtro de rede) e a Partilha Explícita é o único caminho para outra rede, com distribuição pelas regras do destino |
| — | `GET /users/{id}` devolvia o perfil de qualquer utilizador a qualquer staff que soubesse o id (ponto (h) da Via Rápida) | Iteração `users-fronteira-de-rede` — o pedido por id passa por `carregar_utilizador_gerivel` (o próprio, o Master, ou alguém das empresas da minha rede; perfil global invisível a um local). **404 e nunca 403**, igual ao de «não existe». Não havia chamadores no frontend. `tests/unit/test_users_fronteira_de_rede.py::TestAExploracao`. |
| — | A dropdown de atribuição mostrava todos os utilizadores ao Master (ponto (j) da Via Rápida) | Iteração `users-fronteira-de-rede` — `GET /users` e `/users/staff` aceitam `?process_id=`; para o Master a lista sai limitada ao alcance do processo (dono + convidadas), mantendo quem já está na equipa; é a MESMA pergunta (`redes_permitidas` + `pode_atribuir`) que o servidor faz ao gravar, com teste de concordância. `ProcessDetails` e `AssignUsersModal` passam o id (o modal passou de `fetch` cru a Axios: o `fetch` não envia `X-Active-Role`, que decide se o Master tem fronteira). |
| D-37 (formulários) | `form_config` global; registo público sem rede | Iteração `formularios-por-rede-e-mercado-b2b` — `form_config` tem `network_id` com o mesmo molde do workflow (modelo sem rede, copy-on-write, leitura própria → modelo → omissões) num ponto único, `form_config_scope`; o registo público carrega `?empresa=<company_id>` e abre estritamente o formulário dessa rede (empresa desconhecida/inactiva = 404, nada é criado); o Portal e o Portal do Parceiro derivam o esquema da rede do cliente/destino. A administração edita só a rede em contexto (Axios, não `fetch`). Migração: `scripts/migrar_formularios_por_rede.py` |
| — | Tipificação rígida do serviço partilhado entre empresas (o «D-33» da directiva de Out 2026; o registo público a que um pedido posterior chamou D-32/D-33 está na linha D-32) | **Fora de âmbito por decisão do dono do produto (Out 2026):** a empresa A partilha com a B sem tipificar o serviço contratado |
| — | O Hub único (`is_hub`), parte da D-35 | Iteração `multi-fornecedor` — a flag global saiu; quem tem Index deriva da equipa e a partilha escolhe a rede de destino (`network_triage`). A migração `--limpar-is-hub` retira o resíduo |
| D-26 | A guarda de documentos não conhecia redes | Iteração `partilha-e-documentos` — encontrada a medir a D-24 e **só podia fechar com a D-25**: a guarda certa É a resposta da partilha. `user_can_view_process_documents` tinha ZERO ocorrências de `network` e abria por duas linhas — o bypass ABSOLUTO de {admin, ceo, **diretor**, administrativo} verificado antes de tudo, e `if not is_document_visibility_restricted(process): return True`, que tornava um processo **já indexado** (o caso NORMAL) visível a qualquer sessão autenticada. Do outro lado estava a pasta documental do cliente: cartão de cidadão, IRS, recibos, extractos, alcançável sabendo só um `process_id`. A fronteira entra **antes** do bypass (um bypass de cargo que corra primeiro é um bypass de rede — a mutação que a move para depois mata quatro testes) e usa o `processo_no_ambito`, que conta a rede convidada. O `scope` é PARÂMETRO das puras e as guardas `async` resolvem-no sempre, falhando FECHADO. Corrigiu também uma afirmação minha: o custo não-óbvio da D-25 **não** era a parede do S3 — `build_s3_valid_prefixes` deriva do PROCESSO e não da rede |
| D-25 | Um processo em PARTILHA entre duas redes não tinha modelo | Iteração `partilha-e-documentos` — `partner_network_ids` acrescenta quem VÊ sem mudar de quem É (`network_id` continua o carimbo de propriedade), e o âmbito é o PROCESSO e não a rede: é essa a diferença face ao atalho do UCR nas duas empresas, que abria a rede INTEIRA. `build_process_scope_condition` é função SEPARADA e DERIVADA da genérica — pôr o ramo no construtor comum fá-lo-ia viajar para 33 superfícies onde nenhum documento tem o campo — com inventário por AST que falha por OMISSÃO e excepções ESCRITAS (as agregações de estatísticas ficam de fora de propósito: **ver, sim; contar, não**). A sincronização DERIVA do documento gravado e não de um diff, porque são cinco os escritores de atribuições. Via Rápida com revogação MANUAL (decisão do dono do produto), e por isso **visível e auditada**: trilho, histórico e etiqueta, que é o único sítio onde uma abertura que ninguém aprovou se vê. Um defeito meu que o teste apanhou: a etiqueta nomeava a empresa POR OMISSÃO do utilizador, pelo que para quem trabalha em duas redes rotulava a partilha com a empresa errada |
| D-23 | O mapeador do scraper descartava campos que a IA extrai | Iteração `motor-de-visitas` — eram **DOIS** mapeadores escritos à mão (o do CRM em `visit_helpers` e o do Portal em `portal_client_visits`) para os MESMOS campos, e **já divergiam**: o do Portal guardava `raw_data`, o do CRM não, pelo que uma visita criada no CRM perdia também quartos, casas de banho, certificado energético, ano de construção, descrição e referência. E a lista de ONZE chaves do `property_scraper`, sobre ~30 devolvidas, perdia o **`estado`** do imóvel — que o prompt da IA pede pelo nome desde sempre. Hoje `services/visit_property_extract.ficha_do_imovel` é o ponto único e o `raw_data` **DERIVA** do dicionário devolvido: um campo novo no prompt chega ao mesmo destino sem ninguém se lembrar. Ganhou um **terceiro veredicto** (`sem_dados`): um anúncio que responde 200 com tudo vazio contava como sucesso e a visita ficava sem um único dado, indistinguível de um imóvel sem informação |
| D-21 | `db.visits` sem isolamento de rede nem posse nas escritas | Iteração `isolamento-das-visitas` — as TRÊS formas do defeito ao mesmo tempo. As duas listagens (e o Kanban, que tem construtor SEPARADO — a lição do `build_kanban_query`) passaram a derivar do mesmo contexto de acesso e do mesmo `com_isolamento`; a posse vive em `visit_scope.py` (puro) com `exigir_visita_acessivel` ligada à leitura, ao `PATCH` e ao cancelamento, e responde **404 e nunca 403**. A reatribuição ganhou a pergunta do DESTINO (`pode_atribuir_a_consultor`), sem a qual um editor legítimo entregava a um consultor de outra rede o nome, o email e o telefone de um cliente. O carimbo passou a derivar do **PROCESSO** num ponto único (`carimbo_da_visita`): havia dois escritores com origens diferentes para o mesmo campo e uma delas — `user.get("company_id")` — não existe no documento de utilizador, logo toda a visita da equipa nascia sem carimbo. **O `administrativo` ENTROU na vista de equipa** (o back-office coordena visitas) e por isso o âmbito dele estreita de «todas as redes» para «a sua rede» |
| D-22 | O modelo de IA do scraper estava fixo no código | Iteração `isolamento-das-visitas` — o modelo configurado era lido, **escrito no log** («Usando modelo configurado: X») e depois ignorado: a chamada era `genai.GenerativeModel("gemini-2.0-flash")`, literal, e o `ai_usage_tracker` recebia o mesmo literal, pelo que o relatório de custos atribuía a despesa ao modelo errado. **O log a dizer o contrário é o que tornava isto difícil de ver.** A omissão continua no `_get_ai_model_for_scraping`, que é onde ela pertence; o teste é ao nível da CHAMADA (asserção sobre o parâmetro que sai para o SDK, não sobre o resultado — regra do «duplo demasiado esperto») |
| D-19 | Homónimos exactos a partilhar pasta na leitura legada | Iteração `fim-do-recurso-por-nome` — **medida antes de apagada**: o `diagnose_s3_name_fallback.py` contra produção contou **zero** fichas a perder documentos, e só então o recurso por nome foi apagado do `s3_storage` (`_find_client_folder_combined`, `_find_client_folder`, `_nomes_de_pasta_candidatos`, `_get_possible_client_paths`) — apagado, não desligado. A medição respondia a UMA pergunta («que fichas não têm `s3_folder`?») e o corte dependia de outra que ela não cobria: **«que chamadores se esquecem de o passar?»** — e havia dois, ambos já partidos em produção (`run_categorize_all_documents` e o `move_file` do «organizar após análise»: para uma ficha mapeada por ID o nome não resolve pasta nenhuma, logo processavam ZERO documentos em silêncio desde o Lote 6). Fechou também a metade de SEGURANÇA, que não estava no enunciado: `build_s3_valid_prefixes` derivava prefixos de posse do NOME, logo dois homónimos exactos autorizavam os ficheiros um do outro, alcançável do **Portal**; o prefixo passou a derivar do ID. Os testes legados foram **invertidos** (a concordância com o oráculo de produção, as grafias candidatas e os dois da guarda de posse), nunca apagados |
| D-9 | Portal do Cliente em polling das mensagens | Iteração `ws-portal-ui` — ligado a `/api/ws/portal` com o polling mantido como recurso |
| D-5 | Tolerância a tokens de staff sem `type` | Iteração `slas-e-sourcemaps` — 24h após o deploy que unificou os três produtores; o ramo do `None` saiu e os dois testes foram INVERTIDOS (um token sem `type` é agora recusado no WebSocket e na API) |
| D-11 | Sourcemaps servidos em produção | Iteração `slas-e-sourcemaps` — `utils/buildSourcemap.js`: sem `SENTRY_AUTH_TOKEN` um build de produção não gera mapas (provado com o build real: 0 `.map` em `dist/`) |
| D-1 | `confirm-upload` do CRM sem posse nem quarentena | Iteração `posse-e-segredo-gov` — era **escalada de privilégio** e não integridade de dados: sem guarda de posse e a devolver `temporary_url` pré-assinado para a chave do corpo do pedido (o Incidente P0 do Portal, no CRM) |
| D-3 | `GOV_AUTH_JWT_SECRET` com valor por omissão | Iteração `posse-e-segredo-gov` — fail-closed em produção, segredo efémero em dev, e o ramo que aceitava tokens por assinar removido dos dois lados |
| D-16 | Eliminar um cliente não deixava entrada no trilho de auditoria | Iteração `sub35-estrito-e-auditoria` — `audit_trail_service.log_audit_event` nos **dois** pontos de saída do `run_delete_client` (o cliente pode viver em `processes` ou em `clients`, e um registo escrito só num ramo era a forma de defeito desta casa); com IP, papel EFECTIVO em `metadata` (o campo partilhado guarda o do JWT) e os ids da cascata. O registo é escrito DEPOIS da eliminação e nunca a faz falhar |
| D-20 | A Listagem de Processos e o Kanban sem teste que monte a página | Iteração `medicao-d19-e-paginas-montadas` — `ProcessesPage.test.jsx` (14) e `KanbanPage.test.jsx` (14, com o `KanbanBoard` REAL). Apanharam três defeitos que nenhum teste de componente podia ver: uma coluna sem `processes` rebentava o quadro (`filter` de `undefined` — havia `|| []` nos dois sítios do arrasto e em nenhum dos quatro do caminho normal), o botão «Exportar Excel» do cabeçalho do quadro tinha ficado FORA do fecho dos botões fantasma (sem gate, e exporta NIF/telefone/email), e o `BotaoComPermissao` dava nome acessível «Acção — sem permissão» a TODOS os botões bloqueados do sistema (o `typeof children === "string"` nunca é verdadeiro com ícone + rótulo) |
| D-17 | Os `co_buyers` não tinham data de nascimento | Iteração `identidade-documental-e-d17` — a data entrou no esquema de extracção do CPCV (opcional, e com instrução explícita de NÃO inferir: uma data inventada é pior do que nenhuma) e a regra estrita estendeu-se aos compradores, em Python e na condição Mongo (`$nor` + `$elemMatch`, porque o quantificador é «todos» e no Mongo isso não tem forma positiva). A desduplicação por identidade é o que impede a regra de se desligar a si mesma — ver D-18 |
| D-7 | Relatório semanal do CEO com âmbito global | Iteração `motor-fila-e-agenda` — decisão de produto tomada (a Direcção quer o CONSOLIDADO, e fica a única excepção deliberada ao isolamento por rede) — **revista na adenda de RBAC (Out 2026): o consolidado passou a ser só do Master e cada rede recebe o seu (`relatorio_semanal_destinos`)**; a dívida fechou com o defeito que ninguém tinha visto ao lado dela — o «às 06:00» vivia só na docstring e o relatório saía **24 vezes** à segunda-feira |
