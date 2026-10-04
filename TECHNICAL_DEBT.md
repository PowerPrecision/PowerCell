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


**Medido no Lote 9 (Fase B):** o `/portal/visits/request` ganhou limite
(fazia o servidor ir buscar um URL escolhido pelo cliente, sem tecto de
custo de IA). Ficavam **nove POST do Portal sem limite nenhum**, e o Portal
é a única superfície externa:
`portal_login`, `verify_portal_login`, `authenticate_portal`,
`update_client_profile`, `send_portal_message`, `fetch_financas_documents`,
`fetch_seguranca_social_documents`, `submit_mfa_code` e
`create_recommendations`. Os três primeiros são de autenticação (força
bruta de magic link) e os dois dos scrapers governamentais abrem ligações
de saída — são os de maior consequência.

**Fechado no Lote 10 (o Portal):** os nove ganharam `@limiter.limit` e
`response: Response`, e a guarda de inventário passou a afirmar a
PROPRIEDADE (nenhum endpoint de escrita de `routes/portal.py` sem limite),
derivada das rotas e não de uma lista
(`tests/unit/test_portal_forca_bruta_e_limites.py`). O login por email
passou a ter um ponto único (`services/portal_brute_force.py`) em vez de
~55 linhas à mão mais uma segunda cópia da política no
`_record_login_attempt`, no mesmo ficheiro.

**Correcção a uma afirmação deste mesmo lote:** disse que o
`run_verify_portal_login` prometia «5 tentativas, lockout de 15 min» na
docstring e não tinha código a contar tentativas. **Não era verdade** — o
travão vive em `portal_security.verify_client_credentials`, está completo e
diz exactamente esses números. Inventariei um módulo e concluí da
ausência; o travão que acrescentei era uma segunda política na mesma porta
e foi retirado.

**O que FICA ABERTO nesta dívida, e é o que importa agora**

O `@limiter.limit` é uma parede com uma porta: a chave vem de
`_get_rate_limit_key`, que nos endpoints **autenticados** resolve o `sub`
do JWT (assinado, não falsificável — no Portal é o `process_id`), mas nos
de **pré-autenticação** cai no IP. E o IP sai de `_get_client_ip`, que lê
o **primeiro** elemento do `X-Forwarded-For`:

```python
forwarded_for = request.headers.get("X-Forwarded-For")
if forwarded_for:
    return forwarded_for.split(",")[0].strip()
```

O primeiro elemento é o que o CLIENTE envia — qualquer proxy acrescenta ao
fim, não ao princípio. **Quem ataca muda-o a cada pedido e o limite por IP
não morde em lado nenhum do sistema**, não só no Portal. É a forma do
placebo do `build_company_scope_condition`: a verificação corre, parece
fechada, e o valor que compara é escolhido por quem se quer verificar.

É por isso que a força bruta do Portal foi fechada pelo eixo da
IDENTIDADE e não pelo do IP, e por isso é que esta dívida não fecha com
o Lote 10.

**Porque não se corrigiu agora:** o valor de confiança é contado a partir
da DIREITA, saltando o número de proxies conhecidos — e esse número
depende do deploy (Render sozinho é 1; Render atrás de Cloudflare é 2). Com
o número errado, todos os clientes colapsam numa só chave e o limite
tranca o sistema inteiro a 10 pedidos/minuto. Mudar isto sem saber a
topologia é trocar uma porta aberta por uma avaria.

**Para fechar:** `TRUSTED_PROXY_HOPS` (inteiro, explícito, por ambiente) +
`_get_client_ip` a contar da direita; sem a variável definida, usar o
`request.client.host` (o peer do socket, não falsificável) e **dizer no
log** que o limite por IP está a agrupar por proxy. Confirmar a topologia
do Render antes, e medir numa pré-publicação: a asserção é que dois
pedidos com `X-Forwarded-For` diferentes e o mesmo peer contam para a
MESMA chave.

**Segunda metade desta dívida, descoberta no Lote 10 — duas políticas de
força bruta para as duas portas do mesmo Portal**

| Porta | Onde | Tentativas | Bloqueio | Colecção |
|---|---|---|---|---|
| Login (email + código) | `portal_brute_force` | 8 | 10 min | `portal_login_attempts` |
| Verify (NIF + nº processo) | `portal_security` | 5 | 15 min | `portal_verify_attempts` |

São duas implementações independentes da mesma ideia, e foi essa
dispersão que me levou a declarar inexistente a segunda (procurei-a no
handler e ela está na camada abaixo).

**Porque não se consolidou agora:** a consolidação parece uma limpeza e
tem uma armadilha — **as constantes têm de ficar POR PORTA**. Escolher um
dos pares mudaria a política da outra em silêncio (apertar o login para 5
tentativas bloqueia um cliente que erra um código de 6 caracteres cinco
vezes; alargar o verify para 8/10 abre a porta que tem o espaço de busca
mais pequeno). Uma consolidação que muda a política não é uma
consolidação.

**Quem é atingido:** ninguém hoje — as duas portas estão protegidas. O
custo é de manutenção e de diagnóstico: uma correcção feita numa das
implementações não chega à outra, e já foi essa divergência a produzir um
engano de leitura.

**Para fechar:** `portal_brute_force` recebe a política por âmbito
(`POLITICAS = {porta: (tentativas, minutos, colecção)}`), com os valores
ACTUAIS de cada porta preservados; `portal_security` passa a chamá-lo e o
`_record_failed_attempt` desaparece. Teste de concordância a afirmar que
cada porta mantém os seus números depois da mudança — é essa asserção que
distingue uma consolidação de uma alteração de política.

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

**O que é preciso para fechar:** decidir entre o filtro e a encriptação, com
o DPO. Se a escolha for encriptar, a opção (a) com um campo `ano_de_nascimento`
(não a idade, não um booleano) é a única que não quebra a pesquisa nem precisa
de recálculo: o ano não muda, e o limiar de "menos de 36" calcula-se sobre ele
com uma margem de um ano a resolver em Python.

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

### D-18 · `co_buyers` tem dois significados
**Onde:** `backend/services/ai_document.py::build_update_data_from_extraction`
(mapeador do CPCV), `backend/services/process_clients_nm.py::build_add_client_update`.

O mesmo campo é escrito com dois significados diferentes:

* o mapeador do CPCV grava **TODOS** os compradores — o elemento 0 é o
  titular 1, e é dele que o mapeador copia o `personal_data`;
* o `build_add_client_update` grava apenas os compradores **ADICIONAIS**, e usa
  `co_buyers[0]` para construir o `titular2_data`.

Encontrado ao fechar a D-17: a regra Sub35 estrita conta "compradores a mais",
e sob o primeiro significado o titular 1 era contado duas vezes. Como um CPCV
português muitas vezes não indica datas de nascimento, isso retirava a etiqueta
a qualquer processo cujo CPCV tivesse sido analisado — **mesmo com um só
comprador**.

**Porque foi adiado:** a correcção óbvia (passar o mapeador a gravar
`compradores[1:]`) criaria um TERCEIRO significado durante a transição, porque
os documentos já gravados mantêm o primeiro. E o campo é lido por
`ai_bulk_clients`, `client_process_ops`, `gdpr`, `encryption` e
`process_service`, nenhum dos quais distingue os dois casos. A regra Sub35 foi
por isso escrita para ser correcta sob **os dois** significados, desduplicando
por identidade (`sub35.compradores_que_bloqueiam`) — o que é mais robusto do
que escolher um e migrar o resto.

**Quem é atingido se explodir:** qualquer regra nova que conte elementos de
`co_buyers` (número de compradores, LTV por comprador, rateio de comissões)
dá um resultado diferente conforme quem escreveu o array.

**O que é preciso para fechar:** decidir o significado único (o nome do campo e
o `titular2_data` apontam para "os adicionais"), migrar os documentos escritos
pelo mapeador do CPCV — identificáveis porque `co_buyers[0]` tem a identidade
do titular 1 — e só então simplificar a desduplicação.

## Fechadas

Ficam aqui só o número e a iteração que as fechou — o detalhe vive no
`worklog.md`, que é o histórico. Uma dívida fechada não volta a este registo.

| # | Dívida | Fechada em |
|---|---|---|
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
| D-7 | Relatório semanal do CEO com âmbito global | Iteração `motor-fila-e-agenda` — decisão de produto tomada (a Direcção quer o CONSOLIDADO, e fica a única excepção deliberada ao isolamento por rede); a dívida fechou com o defeito que ninguém tinha visto ao lado dela — o «às 06:00» vivia só na docstring e o relatório saía **24 vezes** à segunda-feira |
