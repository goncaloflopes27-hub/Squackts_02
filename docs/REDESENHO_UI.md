# Apresentação SquackTS 0.3.2

A interface passa a usar fundos neutros, ações laranja, detalhes vermelhos e Inter incluída na distribuição. O esquema comercial continua na versão 7: não foram alterados serviços, repositórios, transações, cálculos, migrações ou mecanismos de backup.

## Entregue

- **Tema e componentes:** tokens/QPalette em `ui/theme.py`, texto escuro sobre laranja, foco visível, tamanhos a partir de 12 px, SVG e fonte com licença OFL. A paleta calculada dá 7,66:1 ao texto secundário sobre a superfície e 7,95:1 aos botões primários; isto não é uma auditoria completa de acessibilidade.
- **Navegação:** sidebar 240/72 px, indicador vermelho animado, cabeçalho contextual, splash sem atraso artificial e transição de página por imagem em cache, sem efeitos de opacidade em widgets grandes. A marca tipográfica é provisória.
- **Páginas:** Hoje com métricas reutilizadas, contagem animada e navegação para encomendas; formulários/filtros adaptáveis; valores numéricos alinhados à direita; menos ações de criação duplicadas.
- **Interação:** comandos Ctrl+K para navegar, criar encomenda e encaminhar pesquisas para as listas; Ctrl+F pesquisa contextual, Ctrl+N criação contextual, Ctrl+S guardar no editor, Esc fecha o diálogo respeitando alterações. A pesquisa usa uma pausa de 250 ms.
- **Listas:** QTableView/QAbstractTableModel/QSortFilterProxyModel nas cinco listas principais, estados em chips, ordenação numérica correta, seleção ligada ao registo original mesmo após ordenar, seleção múltipla e cópia por Ctrl+C/barra de ações. Cabeçalhos permitem escolher colunas pelo botão direito e memorizar o layout. Encomendas/produção conservam a paginação existente; o editor de itens mantém uma pequena QTableWidget editável.
- **Formulários:** os erros preservam os campos; botão indica gravação/conclusão. Novas encomendas têm um rascunho de apresentação local, recuperável sem criar registos comerciais. É eliminado depois de guardar; sair mantém o rascunho. Não representa uma encomenda confirmada nem integra o backup comercial.
- **Feedback:** notificações no canto inferior direito, com texto/ícone e fecho; a API só apresenta Anular quando recebe uma operação reversível real. Não há anulação automática de pagamentos, stock ou cancelamentos. Skeleton durante tarefas de backup já assíncronas; diálogos com entrada discreta e fundo escurecido.
- **Preferências:** Completas, Reduzidas e Desligadas. Em Reduzidas removem-se movimentos/contagens, conservando apenas feedback curto das notificações. Fontes e ilustrações são locais. Ficheiros de rascunho/layout são lidos/escritos por um worker serializado; a thread Qt só acede aos widgets.
- **Distribuição:** Inter, licença, SVG e ilustrações incluídos no PyInstaller. O ensaio do executável compara os assets e exige Inter carregada. O instalador verifica atalhos, atualização desde 0.3.1-rc.8, reinstalação e desinstalação com dados preservados.

## Evidência

140 testes locais aprovados, Ruff aprovado e mypy sem erros em 77 ficheiros. Três regressões novas cobrem pesquisa/carregamento tardio, ordenação/seleção e recuperação do rascunho sem criar encomendas. Os testes de shell foram adaptados à paleta de comandos e às três opções de movimento; as regressões comerciais anteriores mantêm-se.

Capturas das seis páginas em `docs/screenshots/` (1440×900) e `docs/screenshots/1100x650/`. Ensaio adicional offscreen com escala Qt de 150%. `python -m scripts.capture_ui` recria capturas com dados fictícios num diretório temporário. A captura mostra a viewport inicial; tabelas e painéis continuam a permitir deslocação.

A execução Windows e o instalador resultante ficam ligados no PR #5. O ensaio nativo verifica o plugin windows, a fonte embebida, seis páginas e atualização. Offscreen a 150% não substitui ensaios manuais de DPI em monitores Windows reais. Não se certificam aqui 60 fps, arranque a frio inferior a 2 s nem todos os leitores de ecrã.

## Limites e trabalho seguinte

1. **Logótipo:** o anexo exige lenço vermelho e proíbe recoloração manual; a imagem fornecida tem lenço azul. Usa-se marca tipográfica e ícone provisórios. As duas ilustrações vazias são novas, não o logótipo final. Substituir pelo asset vermelho oficial quando existir.
2. **Consultas síncronas:** continuam nos serviços invocados por listas, detalhes e formulários, assim como certas preferências/diagnósticos. Não se afirma ausência total de SQLite/I/O na thread Qt. Generalizar workers com ligações próprias exige rever contratos/ciclo de vida dos serviços e fica fora desta alteração de apresentação. Não foram introduzidos índices nem alterada a base para o conseguir.
3. **Indicadores:** não se inventou “faturação do mês”, nem novos filtros de entregas de hoje. O painel apresenta os indicadores reais já disponíveis; valores registados não são faturação fiscal. Novos períodos/filtros devem ser fornecidos pela camada de consultas.
4. **Movimento:** não se introduziu stagger por linha nem animação em cada reordenação; preserva-se a leitura e evita-se piscar ao filtrar. O splash mostra progresso real de arranque, sem impor uma duração mínima.
5. **Rascunho:** existe um rascunho novo por perfil, sem histórico de versões; preços/disponibilidade voltam a ser validados pelos serviços ao guardar. O protetor de saída explica que o rascunho permanece. Campos de um produto/arte ainda não adicionados à lista de itens não são recuperados.
6. **Validação manual:** logótipo final, Windows físico a 125–200%, navegação assistiva, conforto em utilização prolongada e desempenho com bases grandes. O instalador continua sem assinatura digital. Pagamentos parciais/IVA continuam fora do âmbito.

Ficheiros principais: `ui/theme.py`, `ui/animations.py`, `ui/main_window.py`, `ui/sidebar.py`, `ui/topbar.py`, `ui/command_palette.py`, `ui/splash.py`, `ui/widgets/`, `ui/pages/`, `ui/dialogs/`, `ui/order_draft.py`, `ui/storage.py`, `ui/assets/`, scripts de captura/validação e configuração de empacotamento. `config.py` muda apenas a versão para 0.3.2.
