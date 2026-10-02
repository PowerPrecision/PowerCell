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

### D-2 · Segredo JWT partilhado entre o Portal e o staff
**Onde:** `backend/config.py` (`JWT_SECRET`), `services/portal_security.py`,
`services/auth.py`.

Os tokens do Portal do Cliente e os do staff são assinados com o **mesmo**
segredo. Até ao lote dos WebSockets externos, o que separava as duas famílias
era uma **coincidência**: o `sub` de um token de Portal é um `process_id`, que
não existe em `db.users`.

**Porque foi adiado:** separar os segredos invalida **todos** os magic links em
circulação — clientes a meio de um onboarding perdem o acesso e têm de pedir
um link novo. A mitigação escolhida foi tornar a claim `type` **autoritativa**
nos dois lados (`ws_client_identity.tipo_de_token_e_de_staff` /
`tipo_de_token_e_do_portal`), o que fecha o problema prático sem invalidar
nada.

**Quem é atingido:** com o `type` autoritativo, ninguém hoje. A dívida é de
**defesa em profundidade**: um segredo só significa que um erro futuro num
verificador de tipo volta a ser explorável, em vez de ser inofensivo.

**Para fechar:** `PORTAL_JWT_SECRET` próprio + rotação com janela de
sobreposição (aceitar os dois segredos durante o tempo de vida do magic link
mais longo), ou aceitar a invalidação numa janela de manutenção anunciada.

---

### D-4 · Varrimento de limites de pedidos nos restantes routers
**Onde:** `backend/routes/*.py`

Os três endpoints de upload do Portal não tinham `@limiter.limit` nenhum,
ao lado de um `/public/client-registration` com `5/hour` desde sempre. O
padrão foi encontrado no lote do Incidente P0 e corrigido **só** nesses três.
Não houve inventário dos restantes.

**Porque foi adiado:** o incidente P0 era um hotfix e alargá-lo a 60 ficheiros
de rotas tornava-o irrevisável.

**Quem é atingido:** qualquer endpoint autenticado mas sem limite é um vector
de varrimento ou de esgotamento de recursos.

**Para fechar:** inventário por AST de todos os `@router.<método>` sem
`@limiter.limit`, triado por superfície (público > Portal > staff), com um
teste-inventário como o de
`test_portal_upload_path_traversal.py::TestOsEndpointsDoPortalTemLimiteDePedidos`.

---

### D-10 · As definições de índices vivem dentro de `create_indexes`
**Onde:** `backend/services/db_indexes.py::create_indexes`

Os índices são 15 literais de lista **locais** dentro de uma função async de
~380 linhas, cada um seguido do seu ciclo de criação. Não há forma de um teste
(nem de um script de diagnóstico) obter as definições sem executar a função
contra uma base de dados.

Foi isso que permitiu o placebo: o `test_db_indexes.py` mantinha uma CÓPIA das
definições escrita à mão e injectava-a em `sys.modules['services.db_indexes']`,
substituindo o módulo inteiro. A cópia tinha 2 colecções e 6 índices de
`processes`; o módulo real tem 13 e 18. Hoje o teste lê o módulo por **AST** —
honesto, mas é uma leitura de texto a fazer o trabalho que uma estrutura de
dados faria.

**Porque foi adiado:** mover 380 linhas do caminho de ARRANQUE da aplicação, no
dia de um deploy, por um ganho que é de forma e não de comportamento. O AST
fecha o problema que importava (o teste passou a poder falhar) sem tocar em
produção.

**Quem é atingido:** ninguém em produção. Quem escrever o próximo teste ou
script sobre índices paga o preço: ou repete a leitura por AST, ou recria a
cópia que acabámos de apagar — e a cópia é o defeito.

**Para fechar:** extrair um `INDEX_DEFINITIONS: dict[str, list[dict]]` ao nível
do módulo, `create_indexes` passa a iterá-lo, e o leitor por AST do teste é
substituído por um import. A lista de colecções que o `get_index_stats` reporta
sai da mesma estrutura, em vez de ser uma segunda lista à mão.

---

## Correcção e modelo de dados

### D-12 · Os limiares de SLA guardam-se por empresa e leem-se globalmente
**Onde:** `backend/services/stats_sla.py::_limiares`,
`backend/models/system_config.py::DashboardSlaConfig`

O `SystemConfig` é por empresa e o `PATCH /api/system-config/dashboard_slas`
aceita `company_id`. Mas `_limiares()` chama `get_system_config()` **sem
argumento**, logo lê sempre a configuração `default`: a Domus não pode ter
limiares diferentes da Power, apesar de o modelo o prometer na docstring (que
foi corrigida).

**Porque foi adiado:** o ecrã de administração construído neste lote é
deliberadamente GLOBAL e diz-o ao utilizador — é a forma honesta de viver com
a limitação. Fazer a leitura por empresa obriga a decidir QUAL empresa: o
`run_get_sla` tem `user`, mas a "empresa activa" é contexto de pedido e
resolvê-la mal recria a confusão id/nome de 2026-09-21. Não é trabalho para
encaixar no fim de um lote.

**Quem é atingido:** redes com ritmos de negócio diferentes. Hoje ninguém, por
não haver limiares distintos configurados — mas o primeiro que os configurar
por empresa vai vê-los ignorados em silêncio.

**Para fechar:** `_limiares(user)` a resolver o âmbito pelo mesmo caminho que
as restantes leituras por empresa, o ecrã a ganhar um selector, e um teste a
afirmar que o que a UI grava é o que o leitor lê (o padrão do
`test_email_config_write_read_key.py`).

---

### D-6 · `INACTIVE_STATUSES` é resíduo legado, não definição
**Onde:** `backend/services/process_status.py`,
`services/my_clients_api_helpers.py`, `services/client_list_search.py`

Quem define o que está "fechado" é a flag `is_active` da fase no **motor de
workflow** (`workflow_phases.nomes_terminais`). O `INACTIVE_STATUSES` é uma
lista cravada em código que sobrevive como **recurso** para quando o motor não
é injectado — e continua a ser o caminho usado em `client_list_search`.

**Porque foi adiado:** substituí-lo exige passar o motor por funções que são
**puras** de propósito (é isso que as torna testáveis sem Mongo no
`backend-fast`), e cada chamador tem de o injectar.

**Quem é atingido:** uma fase nova marcada como terminal no painel de admin
não é reconhecida como fechada nos caminhos que ainda usam a lista — os
números de "carteira activa" divergem do quadro.

**Para fechar:** injectar `terminais=` em todos os chamadores (o
`my_clients_api_helpers` já o aceita) e reduzir o `INACTIVE_STATUSES` a um
recurso de arranque, com um teste a afirmar que nenhum caminho de produção o lê
sem tentar o motor primeiro.

---

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

1. **MEDIR antes de mover.** `db.stats()` por colecção (tamanho de dados,
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

### D-8 · `db.emails` não tem carimbo de rede
**Onde:** colecção `emails`

Os processos, clientes e leads têm `network_id`; os emails não. Pertence ao
lote do webmail.

**Para fechar:** carimbo na escrita (`resolve_tenant_stamp`) + backfill com a
regra do `rede_consensual` (recusa adivinhar quando há mais de uma candidata).

---

### D-14 · O formulário público pode criar um cliente com NIF repetido
**Onde:** `backend/services/public_registration.py` (`db.clients.insert_one`)

O Lote 2 (ponto 4) fechou a unicidade de NIF/Email nas duas portas do CRM —
criação e edição — com o ponto único `services/client_uniqueness.py`. O
formulário **público** continua a inserir sem essa guarda, pelo que a
invariante não é uma invariante: um cliente que se registe duas vezes pelo
site cria o duplicado que a edição já não deixa fabricar.

**Porque foi adiado:** não é esquecimento, é uma decisão de produto que não se
toma dentro de uma correcção técnica. Um 409 numa porta EXTERNA perde a lead
em vez de a tratar, e o que ali faz sentido é reaproveitar o cliente
existente — o que muda o fluxo de negócio (a quem fica atribuído? o que
acontece aos dados novos que ele submeteu? e aos documentos?).

**Para fechar:** decidir entre (a) reaproveitar o cliente existente e anexar a
submissão nova ao registo que já existe, (b) criar sempre e sinalizar para a
Sala de Triagem fundir, ou (c) recusar com uma mensagem que mande o cliente
usar o Portal. Qualquer das três reutiliza `encontrar_cliente_duplicado`, que
já existe e é o que a criação e a edição usam.

---

## Fechadas

Ficam aqui só o número e a iteração que as fechou — o detalhe vive no
`worklog.md`, que é o histórico. Uma dívida fechada não volta a este registo.

| # | Dívida | Fechada em |
|---|---|---|
| D-9 | Portal do Cliente em polling das mensagens | Iteração `ws-portal-ui` — ligado a `/api/ws/portal` com o polling mantido como recurso |
| D-5 | Tolerância a tokens de staff sem `type` | Iteração `slas-e-sourcemaps` — 24h após o deploy que unificou os três produtores; o ramo do `None` saiu e os dois testes foram INVERTIDOS (um token sem `type` é agora recusado no WebSocket e na API) |
| D-11 | Sourcemaps servidos em produção | Iteração `slas-e-sourcemaps` — `utils/buildSourcemap.js`: sem `SENTRY_AUTH_TOKEN` um build de produção não gera mapas (provado com o build real: 0 `.map` em `dist/`) |
| D-1 | `confirm-upload` do CRM sem posse nem quarentena | Iteração `posse-e-segredo-gov` — era **escalada de privilégio** e não integridade de dados: sem guarda de posse e a devolver `temporary_url` pré-assinado para a chave do corpo do pedido (o Incidente P0 do Portal, no CRM) |
| D-3 | `GOV_AUTH_JWT_SECRET` com valor por omissão | Iteração `posse-e-segredo-gov` — fail-closed em produção, segredo efémero em dev, e o ramo que aceitava tokens por assinar removido dos dois lados |
| D-7 | Relatório semanal do CEO com âmbito global | Iteração `motor-fila-e-agenda` — decisão de produto tomada (a Direcção quer o CONSOLIDADO, e fica a única excepção deliberada ao isolamento por rede); a dívida fechou com o defeito que ninguém tinha visto ao lado dela — o «às 06:00» vivia só na docstring e o relatório saía **24 vezes** à segunda-feira |
