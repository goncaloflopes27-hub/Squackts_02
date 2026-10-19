# Plano de melhoria do SquackTS

Referência: branch `main`, commit `34d588a`. Retrato inicial baseado nos 48 ficheiros então versionados. As situações de partida e os 32 testes referem-se a esse commit; a implementação posterior tem verificações e evidência próprias.

**Propósito a preservar:** uma aplicação desktop local para gerir uma operação Print-on-Demand, desde o catálogo e os clientes até às encomendas, produção e expedição, com dados fiáveis e uma interface dark cuidada, consistente e rápida.

O objetivo da evolução é permitir que uma pessoa saiba o que precisa de fazer, execute a próxima ação e consiga explicar os valores, o stock e o estado de cada encomenda. A entrega A inclui já fundações visuais, hierarquia de ações e feedback dos formulários; a Fase 4 consolida o design system e os layouts completos na entrega B.

Este documento define o plano e os critérios de aceitação. A implementação autorizada segue estes critérios; os resultados executados são registados em RELATORIO_IMPLEMENTACAO.md. O nome da aplicação é SquackTS e o nome do negócio é Squack TS.

**Revisão de prioridades após a estabilização (20 de outubro de 2026):** o âmbito histórico abaixo adiava pagamentos parciais, mas a revisão comercial passou sinais/recebimentos, condições a prazo e levantamento em loja para a próxima entrega, juntamente com a definição explícita de IVA. A aplicação atual ainda não os suporta. O [relatório atualizado](RELATORIO_IMPLEMENTACAO.md) distingue a implementação existente destas prioridades e identifica também a falta de controlo de versão por registo, o custo da pesquisa e os ensaios pendentes em dados reais/Windows. Esta revisão prevalece sobre a classificação histórica de pagamentos parciais como extensão posterior; as políticas comerciais e fiscais ainda não foram presumidas.

**Decisões de base**

| Decisão proposta | Aplicação prática |
| --- | --- |
| Manter Python, PySide6, SQLite e Pillow | A stack serve a operação desktop local e já tem uma base funcional. |
| Preservar UI → Services → Repositories | A UI apresenta informação e recolhe ações; os serviços garantem regras e transações; os repositórios concentram SQL parametrizado. |
| Evoluir por entregas verificáveis | Cada entrega termina com um percurso utilizável e testes das regras afetadas. |
| Dar prioridade ao percurso completo | Catálogo e cliente → encomenda → produção/preparação → expedição → conclusão. |
| Manter dinheiro em cêntimos | Os cálculos usam inteiros e Decimal; a formatação monetária fica na apresentação. |
| Manter as seis áreas principais | Painel, Encomendas, Catálogo, Clientes, Produção e Sistema, com sidebar, topbar e QStackedWidget. |
| Preservar dados existentes | Mudanças de modelo exigem backup, migração testada e recuperação verificável. |
| Separar núcleo e expansão | A primeira versão melhorada consolida a operação atual; variantes, arte por item e tratamento parcial da encomenda entram depois. |

As interfaces dos serviços devem ficar estáveis antes de ligar os novos ecrãs. A exploração visual e os componentes comuns podem avançar em paralelo com o trabalho de dados.

**Situação inicial e prioridades**

P0 significa risco para a integridade dos dados ou uma operação comercial incorreta. P1 significa um percurso diário incompleto ou pouco fiável. P2 significa melhoria de eficiência ou expansão funcional.

| Prioridade | Situação identificada | Tratamento |
| --- | --- | --- |
| P0 | Produção pode expedir sem aplicar as verificações de pagamento e tracking usadas nas Encomendas. | Criar um único caminho de transição e aplicar as mesmas regras a todas as entradas. |
| P0 | Editar uma encomenda apaga/recria linhas com os preços atuais do catálogo. | Preservar IDs, preços, custos e snapshots; separar revisão comercial de alteração operacional. |
| P0 | Uma migração maior precisa de uma recuperação completa, incluindo ficheiros associados. | Preparar migrações numeradas, backup completo e restauro validado antes das alterações de schema. |
| P1 | O refresh repetido do Painel reutiliza uma tabela Qt já eliminada. | Corrigir a propriedade e atualização dos widgets e acrescentar regressão do ciclo de eventos. |
| P1 | O fecho dos três editores usa super() dentro de uma lambda sem argumentos. | Reproduzir o comportamento e corrigir o callback se confirmado; testar gravação e fecho reais. |
| P1 | A validação local pode apagar uma mensagem de erro devolvida pelo serviço. | Separar erros de campo, erros de submissão e estado de gravação. |
| P1 | A transição para concluída existe no domínio, mas falta uma operação pública utilizável para a executar. | Criar uma ação explícita para concluir encomendas expedidas. |
| P1 | Navegação não atualiza páginas afetadas por alterações noutras áreas. | Introduzir invalidação e atualização após operações confirmadas. |
| P1 | Botões sem ação, pesquisa de Sistema sem efeito e carregamento permanente. | Dar uma função concreta a cada controlo apresentado e estados de UI reais. |
| P1 | O total chamado receita inclui rascunhos e encomendas não pagas. | Definir indicadores e consultas com significado comercial explícito. |
| P2 | Stock misto funciona com desconto integral ou nenhum desconto. | Evoluir para quantidades reservadas e a produzir numa entrega posterior, com migração própria. |

No commit de referência, o erro do Painel foi confirmado em execução. Os restantes achados foram inicialmente identificados pela leitura e exigem regressões específicas. Os 32 testes iniciais passaram, mas não cobriam todos os P0/P1: o teste do percurso de produção aceitava chegar a expedida sem pagamento/tracking, e faltavam cenários de preservação de preços e do ciclo de eventos Qt. Nessa referência, Ruff excluía a UI e mypy cobria sobretudo domínio e infraestrutura; a implementação alarga essa cobertura.

**Fase 1 — estabilizar o que já existe**

Começar com uma base de demonstração isolada, com produtos POD, físicos e mistos, clientes e encomendas em diferentes estados. Guardar o resultado inicial dos testes e uma cópia dos dados antes de qualquer alteração. Introduzir logo o .gitignore para ambientes virtuais, caches, dados, backups e saídas de build, antes de gerar novos ficheiros locais. Antecipar nesta fase os tokens visuais comuns, o foco visível e a hierarquia de ações usados nas correções dos formulários; a Fase 4 completa a consolidação visual.

Centralizar os comandos de confirmar, iniciar produção, preparar envio, expedir, concluir e cancelar. ProductionService passa a usar o mesmo núcleo de operações que OrderService. A leitura do estado atual, a validação, os movimentos de stock e a auditoria decorrem dentro da mesma transação. Uma falha não pode deixar meia operação gravada.

Criar operações próprias para notas, tracking, pagamento e estado. Uma alteração operacional não deve apagar itens nem recalcular preços. A edição de quantidades preserva o preço unitário contratado; uma linha nova recebe o preço atual do catálogo. A atualização de preços do catálogo passa a ser uma ação explícita em rascunhos, com comparação antes/depois.

Corrigir o ciclo de vida da tabela do Painel. Nos editores, testar e uniformizar guardar, impedir submissão duplicada, apresentar erro, recuperar o botão e fechar após sucesso. Erros do serviço permanecem visíveis e os campos preenchidos são preservados após uma falha.

Uniformizar os textos das ações. “Pronta para envio” e “Expedida” são resultados diferentes. Uma ação aplicada à encomenda inteira deve dizê-lo, mesmo quando a seleção é uma linha de item.

**Critério de conclusão:** criar e editar cliente, produto e encomenda funciona; o Painel suporta atualizações repetidas; é possível chegar a concluída pelo percurso previsto; nenhuma entrada permite expedição inválida ou alteração silenciosa dos preços históricos.

**Fase 2 — preparar dados, recuperação e arquitetura para evoluir**

Mover os dados do utilizador para um diretório de aplicação, separado do código e do executável. Usar um caminho adequado ao sistema operativo, com opção documentada para o configurar. A transferência da localização antiga preserva a origem até a nova cópia estar verificada.

Tornar os ficheiros de imagem geridos pela aplicação: importação, validação, nome interno estável, miniatura e referência relativa. Alterar o nome de uma pasta externa não deve quebrar uma imagem já importada.

Introduzir migrações numeradas e sequenciais. A aplicação verifica a versão antes de escrever, recusa alterar uma base com versão superior à suportada e cria uma cópia consistente antes de migrar. Cada passo preserva IDs, montantes e relações e termina com verificações de integridade.

Alargar o backup para incluir SQLite, imagens e manifesto com versão, conteúdo e checksums. Continuar a usar a API de backup do SQLite para a base de dados com WAL. Os ficheiros geridos devem ter referências estáveis para que o conjunto capturado seja consistente.

Implementar restauro: validar primeiro num diretório temporário, mostrar o conteúdo e compatibilidade, guardar uma cópia de recuperação dos dados atuais e só depois substituir. Se a verificação falhar, o conjunto atual mantém-se utilizável. O restauro pede confirmação por substituir dados concretos.

Nos serviços, introduzir pedidos e resultados tipados com dataclasses, substituindo gradualmente dicionários genéricos e sqlite3.Row nas fronteiras com a UI. Distinguir erros de validação, operação proibida, stock insuficiente e entidade inexistente. Mover o SQL do DashboardService para repositórios de leitura.

Manter o domínio independente de Qt. Notificações de operações concluídas só são publicadas após commit; um adaptador da aplicação traduz essas notificações para a atualização da UI. Diretórios, relógio e criação de ligações ficam injetáveis para testes.

**Critério de conclusão:** uma base de cada versão suportada migra preservando os dados; uma falha provocada não corrompe a instalação; um backup com imagens é restaurado num diretório novo e a aplicação abre os mesmos registos.

**Fase 3 — tornar o modelo comercial coerente**

Separar o progresso operacional do pagamento.

O percurso operacional recomendado é:

`Rascunho → Confirmada → Em produção → Pronta para envio → Expedida → Concluída`

Encomendas compostas apenas por stock físico podem ir de confirmada a pronta para envio após a preparação. O cancelamento é permitido antes da expedição. Devoluções e reembolsos têm tratamento próprio numa evolução posterior.

O pagamento começa com dois estados claros: pendente e pago. Confirmar e iniciar produção sem pagamento continua permitido; expedir exige pagamento e tracking. O domínio define as ações permitidas, e a UI mostra essas ações e os motivos dos bloqueios.

Migrar o estado operacional antigo paga para o estado confirmada com a informação de pagamento preservada. Registos contraditórios são assinalados para reconciliação; não se inventam tracking, pagamentos ou datas históricas para satisfazer o novo modelo.

Definir quando as revisões comerciais deixam de ser permitidas. Recomendação: bloquear alteração de linhas e preços após o início da produção; permitir notas e correções de tracking através de operações próprias e auditadas. Alterações antes da produção apresentam diferenças de total e de stock antes da confirmação.

Arquivar produtos e clientes referenciados, mantendo o histórico. Registos inativos deixam de poder ser escolhidos em novas encomendas; encomendas antigas continuam legíveis.

Definir indicadores de forma verificável: valor de encomendas confirmadas, valor marcado como pago, montante pendente, quantidade por produzir e encomendas prontas para envio. Antes das tarefas da Fase 8, a quantidade por produzir é uma estimativa explícita do modelo de tudo ou nada: somar a quantidade integral das linhas POD ou mistas sem desconto de stock, em encomendas confirmadas/em produção; excluir linhas físicas e mistas já satisfeitas por stock. Depois da Fase 8, substituir essa estimativa pela soma das quantidades das tarefas ainda pendentes. Datas de pagamento só são usadas quando efetivamente conhecidas. Margens usam os custos guardados nas linhas e são apresentadas como estimativas.

**Critério de conclusão:** a mesma ação tem o mesmo resultado em qualquer página; mudar o catálogo não altera o passado; cada indicador concilia com uma lista de registos que explica o valor apresentado.

**Fase 4 — consolidar o design system e o ciclo de atualização**

Manter a paleta dark existente e formalizar tipografia, espaçamento, densidade, superfícies, bordas, foco e estados. Definir variantes consistentes de botões, cartões, tabelas, badges, formulários, confirmações e mensagens. Usar nomes legíveis para os estados apresentados ao utilizador.

Dividir components.py por responsabilidade, preservando interfaces estáveis: controlos básicos, formulários, tabelas, cartões e feedback. As páginas compõem esses componentes e os seus modelos de apresentação.

Adaptar a estrutura a diferentes larguras: sidebar compacta, ações secundárias num menu e painel de detalhe recolhível. Validar a janela mínima atual de 1280×800 e escalas de apresentação comuns no Windows. O conteúdo e as ações principais devem continuar acessíveis.

Escolher uma pesquisa contextual por página, com filtros coerentes. Guardar consulta, seleção, posição e filtros ao atualizar. Uma operação concluída marca as áreas afetadas como desatualizadas; a página visível atualiza e as restantes atualizam ao entrar.

Distinguir lista vazia, pesquisa sem resultados, erro recuperável, carregamento e gravação em curso. Tabelas de consulta são apenas de leitura; a edição só acontece nos campos explicitamente preparados para persistir alterações.

Incluir navegação por teclado, ordem de tabulação, foco visível, labels acessíveis, contraste verificável e preferência de reduzir animações. Animações não podem bloquear o fecho ou a gravação de um formulário.

**Critério de conclusão:** criar uma encomenda atualiza lista, indicadores e fila sem reiniciar; nenhuma célula aparenta guardar uma edição que desaparece; os percursos principais funcionam por teclado e os estados da interface são consistentes.

**Fase 5 — melhorar cada página e os três editores**

| Área | Melhoria funcional proposta | Resultado esperado |
| --- | --- | --- |
| Painel | Pendências de confirmação, pagamento, produção e envio; prazos; stock baixo; indicadores com definição e período. Alertas abrem listas filtradas. | O operador percebe o que fazer a seguir e consegue explicar cada número. |
| Encomendas | Filtros por estado operacional, pagamento, cliente e datas; detalhe com itens, valores, prazos, tracking e atividade; próxima ação permitida. Exportação acompanha filtros. | Acompanhar uma encomenda desde a criação até à conclusão sem procurar ações noutras páginas. |
| Catálogo | Miniaturas reais, pesquisa por nome/SKU, filtros por produção/ativo/stock; preço, custo e margem; importação de imagem; arquivo. | Identificar rapidamente produtos e a disponibilidade relevante, preservando históricos. |
| Clientes | Perfil com contactos, moradas, notas e encomendas associadas; “Nova encomenda para este cliente”; tratamento claro de duplicados. | Reduzir repetição de dados e facilitar acompanhamento comercial. |
| Produção | Agrupar por encomenda com itens visíveis, distinguir produção de separação de stock, mostrar prazo e quantidade e explicitar o âmbito das ações. | Executar trabalho sem alterar uma encomenda inteira por engano. |
| Sistema | Diagnóstico executado de verdade, resultado e data; logs pesquisáveis; backups verificados; restauro; preferências funcionais. | Conseguir verificar o estado da aplicação e recuperar dados com um procedimento claro. |

A expedição começa como uma vista de encomendas prontas para envio. O operador indica tracking, confirma o pagamento existente e executa uma ação de expedir; o domínio valida a operação.

O editor de cliente organiza identificação, contactos, dados fiscais, moradas e notas. As regras de obrigatoriedade e de duplicados são partilhadas entre o serviço e a ajuda apresentada no formulário.

O editor de produto organiza identificação/SKU, preço/custo, modo de tratamento, stock relevante e imagem. A imagem é escolhida e importada com preview. Campos de stock deixam de induzir a ideia de que um produto POD exige produto acabado disponível.

O editor de encomenda tem pesquisa de cliente e produto, criação rápida de cliente, itens e quantidades, data prevista, pagamento, portes, notas e resumo persistente. “Guardar rascunho” e “Confirmar encomenda” apresentam consequências claras. Os valores finais são calculados pelo serviço e coincidem com a pré-visualização.

Todos os editores partilham ações persistentes, foco no primeiro erro, proteção contra duplo clique, preservação de dados após falha e aviso ao sair com alterações por guardar.

**Critério de conclusão:** o percurso comercial completo é executado numa base representativa; o registo criado fica selecionado; erros são recuperáveis; listagens, resumo financeiro e base de dados coincidem.

**Fase 6 — automatizar a qualidade e medir desempenho**

Os testes acompanham todas as fases anteriores. Nesta etapa, consolidar a execução automática em CI, com o Python mínimo suportado, Linux para testes do domínio e Qt headless, e Windows para as verificações específicas de distribuição.

Preservar os cenários de regressão válidos dos 32 testes iniciais. Rever explicitamente as expectativas que validavam um comportamento incorreto, como a expedição sem pagamento/tracking no percurso de produção, e acrescentar testes que recusem esse comportamento. Acrescentar cobertura dos casos que não existiam: preços históricos, transações falhadas, callbacks Qt, restauro e concorrência local. Alargar Ruff à UI por incrementos e melhorar a tipagem dos contratos e páginas. Fixar a resolução de dependências para reproduzir instalações.

Usar os recursos QtTest disponíveis na stack para testar eventos reais: gravação, timers, fecho de diálogos, sinais, refresh e seleção. As verificações headless exercitam comportamento; a aparência é avaliada separadamente com a aplicação aberta e capturas reais.

Medir listas com uma base sintética de aproximadamente 10 000 encomendas e vários itens por encomenda. Registar tempos de arranque, pesquisa, filtro e atualização no mesmo ambiente. Definir o orçamento de desempenho com essa referência antes de alegar ganhos.

Se as medições justificarem, substituir preenchimento integral de QTableWidget por modelos Qt, paginação e pesquisa/ordenação nos repositórios; introduzir debounce e índices orientados às consultas reais. Evitar carregar imagens e históricos completos para construir uma listagem.

Operações demoradas, como importação, backup e geração de miniaturas, passam a workers com progresso e tratamento de erro. Cada worker usa uma ligação SQLite própria; widgets continuam a ser alterados na thread da UI.

**Critério de conclusão:** verificações automáticas detetam os erros corrigidos nas fases anteriores; a interface mantém-se utilizável durante tarefas demoradas; as medições mostram o comportamento com volume superior ao de demonstração.

**Fase 7 — entregar uma aplicação Windows utilizável no dia a dia**

Preparar empacotamento com dependências, plugins Qt, ícones e versão da aplicação. Começar com uma distribuição em diretório para verificar o conteúdo e o arranque; acrescentar instalador quando a instalação estiver reproduzível.

Validar num ambiente Windows limpo, sem Python previamente instalado: instalação, arranque, diretórios do utilizador, persistência, atualização e recuperação. Atualizar a aplicação não pode substituir a base de dados nem as imagens.

Manter os scripts de desenvolvimento coerentes com a instalação documentada e verificar que o .gitignore introduzido na Fase 1 continua a abranger os novos artefactos de distribuição.

Preparar uma base de demonstração separada e um guia curto de primeiro uso: criar produto e cliente, receber encomenda, produzir, expedir e criar/restaurar backup. Documentar o suporte a uso local; uma futura edição para várias máquinas terá requisitos próprios.

**Critério de conclusão:** uma pessoa instala e percorre a operação principal num Windows limpo, reinicia e encontra os mesmos dados; uma atualização preserva-os; o restauro foi ensaiado.

**Fase 8 — expandir as capacidades específicas de POD**

Esta fase acrescenta funcionalidades ao produto depois de a operação atual estar estável e distribuível.

**Variantes e personalização.** Separar produto de variante com SKU, tamanho/cor, preço/custo e disponibilidade. Migrar cada produto atual para uma variante base preservando referências históricas. Separar modo de tratamento da encomenda — POD, físico ou misto — de técnica de produção, como DTF ou bordado.

Associar a cada item de encomenda a personalização e a versão do ficheiro de impressão. A imagem de catálogo serve a apresentação; o ficheiro de produção identifica o trabalho contratado. Criar aprovação de arte, preparação, produção, controlo de qualidade e embalagem com checklist simples.

**Stock e reservas.** Evoluir para físico, reservado e disponível, com movimentos que expliquem entradas, ajustes, reservas, libertações e consumos. A confirmação da encomenda reserva unidades. A expedição consome as unidades reservadas. O cancelamento liberta as reservas ainda existentes. Uma repetição da ação não duplica movimentos.

A recomendação para novas encomendas mistas é usar o disponível e produzir o restante: dez unidades pedidas com seis disponíveis reservam seis e geram produção de quatro. Esta é uma mudança explícita em relação ao comportamento atual de desconto integral ou nenhum desconto.

Guardar quantidades por origem e por tarefa. A migração tem de considerar que o sistema antigo já descontava stock ao confirmar, evitando descontar novamente. Preservar o disponível existente e assinalar situações ambíguas para reconciliação; não reconstruir um histórico físico desconhecido como se tivesse sido registado.

**Produção por item.** Introduzir tarefas e quantidades por item; o resumo da encomenda resulta do trabalho efetivo. A encomenda só fica pronta quando todas as quantidades necessárias estão prontas ou separadas. Unidades produzidas para um pedido não entram automaticamente no stock livre; a sua incorporação exige uma operação explícita.

**Critério de conclusão:** uma encomenda com variantes e artes distintas produz os ficheiros e quantidades corretos; a soma entre stock e produção satisfaz o pedido; cancelamentos e revisões conservam o histórico e a disponibilidade.

**Cenários de aceitação**

| Cenário | Resultado obrigatório |
| --- | --- |
| Expedir sem pagamento ou tracking, por qualquer entrada | A operação é recusada e não deixa alterações parciais. |
| Alterar o preço do catálogo e depois editar notas de uma encomenda | IDs das linhas, preços contratados e total são preservados. |
| Atualizar o Painel e pesquisar repetidamente | Sem objetos Qt eliminados, componentes duplicados ou resultados desatualizados. |
| Gravar cliente/produto/encomenda com erro de domínio | Erro legível, campos preservados e possibilidade de corrigir e tentar novamente. |
| Duplo clique numa confirmação ou repetição de cancelamento | Sem encomendas duplicadas ou movimentos de stock repetidos. |
| Criar encomenda e navegar para Painel/Produção | Indicadores e fila refletem a operação concluída. |
| Arquivar um produto já vendido | Histórico continua legível; produto deixa de estar disponível para novas linhas. |
| Falhar uma migração a meio | Recuperação deixa a instalação e os dados num estado conhecido e utilizável. |
| Restaurar backup com imagens e WAL ativo na origem | Registos, relações e ficheiros são recuperados e a aplicação abre. |
| Somar 0,10 € e 0,20 € | Total exato de 0,30 €, incluindo depois de gravar e voltar a abrir. |
| Confirmar pedidos locais sobrepostos com stock limitado | O total reservado/descontado não excede o disponível. |
| Percorrer os formulários por teclado e com DPI aumentado | Ações alcançáveis, foco visível e conteúdo legível. |
| Instalar e atualizar num Windows limpo | Arranque funcional e dados preservados. |

A concorrência deste cenário é local: duplos cliques e repetição de pedidos devem ser idempotentes, e os testes abrem duas ligações SQLite com escritas sobrepostas na mesma máquina. Os workers de backup/inspeção também têm ligações próprias, mas não fazem confirmações de encomendas. Estes testes de integridade não pressupõem utilização multi-máquina.

As capturas de validação visual devem cobrir as seis páginas e os três editores, em 1280×800 e numa janela maior, com estados vazios, erros, nomes longos, listas preenchidas e imagens ausentes. A avaliação visual exige essas capturas; a leitura do código não a substitui.

**Entregas, dependências e âmbito**

| Entrega | Conteúdo | Condição para avançar |
| --- | --- | --- |
| A — operação fiável | Fases 1 a 3; fundações visuais antecipadas da Fase 4, feedback e hierarquia de ações; testes das invariantes; migração e recuperação preparadas. | Percurso atual completo, preços preservados e transições consistentes. |
| B — experiência e distribuição | Fases 4 e 5, consolidação da fase 6 e distribuição da fase 7. | Operação confortável, visualmente validada e instalada num Windows limpo. |
| C — POD aprofundado | Fase 8, com migrações e testes próprios. | Variantes, arte, quantidades e stock conciliam com o trabalho executado. |

A automação e os testes começam na entrega A. A distribuição deve ser ensaiada antes da conclusão da entrega B. As fundações visuais começam na Fase 1; os layouts completos da Fase 4 avançam em paralelo depois de definidos os contratos dos serviços; a ligação funcional das páginas acompanha a estabilização desses contratos.

Integrações com lojas e transportadoras, importação em massa, pagamentos parciais, devoluções, expedições parciais e colaboração entre máquinas são extensões posteriores, priorizadas pelo uso real. Exigem regras e, quando aplicável, acessos próprios. O plano principal concentra-se na gestão operacional local.

Cada alteração deve ser pequena o suficiente para rever e terminar com evidência adequada: comportamento corrigido, teste relevante, efeito nos dados e capturas quando houver alterações visuais. Mudanças de schema devem ser verificadas antes da publicação de uma versão que as use.

Não se fixa um prazo de calendário nesta fase. Os checkpoints são as condições de aceitação de cada entrega; as estimativas podem ser feitas por conjunto de alterações depois de reproduzidos os erros pendentes e preparada a primeira migração.

