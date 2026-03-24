# AGENTS.md

## Objetivo do projeto
Aplicação desktop local para gestão de uma empresa Print-on-Demand, com foco principal em interface premium, dark mode elegante, arquitetura limpa e consistência visual.

## Stack obrigatória
- Python 3.11+
- PySide6
- SQLite
- Pillow

## Regras obrigatórias
- Não usar Tkinter
- Não usar QTabWidget como navegação principal
- Não usar frameworks web
- Não usar Electron
- Não usar ORMs pesados
- Não criar ficheiros legacy nem estruturas duplicadas
- Não misturar abordagens antigas com novas
- A navegação principal deve ser por sidebar + topbar + páginas num QStackedWidget
- A UI é a prioridade máxima deste projeto
- Sempre priorizar consistência visual, design system e reutilização de componentes

## Arquitetura obrigatória
- UI nunca faz SQL
- Repositories fazem apenas SQL parametrizado
- Services contêm regras de negócio, validações, transações e logs
- UI fala apenas com Services

## Estrutura esperada
- app.py
- config.py
- db.py
- schema.py
- utils.py
- service_container.py
- requirements.txt
- README.txt
- repositories/
- services/
- ui/
- ui/pages/
- ui/dialogs/

## Direção visual obrigatória
- Dark mode moderno, premium e consistente
- Inspiração em Linear, Stripe Dashboard, Shopify Admin, Notion e Airtable
- Nunca usar preto puro
- Alto contraste
- Cantos arredondados elegantes
- Espaçamento consistente
- Hover states suaves
- Microinterações discretas
- Componentes reutilizáveis com estilo unificado

## Tokens visuais obrigatórios
- Background principal: `#0B1020`
- Superfícies: `#111827`, `#162033`, `#1B2740`
- Bordas: `#243244`, `#334155`
- Texto primário: `#E5E7EB`
- Texto secundário: `#94A3B8`
- Cor primária: `#3B82F6`
- Sucesso: `#22C55E`
- Aviso: `#F59E0B`
- Erro: `#EF4444`
- Destaque violeta: `#8B5CF6`

## Motion system
- Usar `QPropertyAnimation`, `QParallelAnimationGroup`, `QEasingCurve` e `QGraphicsOpacityEffect` quando útil
- Durações padrão:
  - ultra_fast: 120ms
  - fast: 180ms
  - normal: 240ms
  - slow: 320ms
- Easing padrão:
  - OutCubic
  - InOutCubic
  - OutQuart
- Não exagerar nas animações
- Animações devem reforçar qualidade, não distrair

## Páginas principais
- Painel
- Encomendas
- Catálogo
- Clientes
- Produção
- Sistema

## Componentes reutilizáveis esperados
- PageHeader
- AppCard
- ElevatedCard
- PrimaryButton
- SecondaryButton
- GhostButton
- DangerButton
- SearchInput
- FilterBar
- StatusBadge
- KPIWidget
- MetricTile
- DetailPanel
- EmptyState
- InfoRow
- Toolbar
- LoadingState
- ConfirmationDialog base

## Estilo de código
- `typing` em todo o projeto
- `dataclasses` quando fizer sentido
- Classes pequenas
- Funções curtas
- Responsabilidade única
- Nomes claros
- Sem ficheiros gigantes monolíticos

## Regras para todas as próximas tarefas
- Trabalhar sempre em cima desta arquitetura
- Reutilizar componentes antes de criar novos
- Preservar consistência visual
- Manter imports limpos
- Não inventar outra stack
- No final de cada tarefa, correr os checks adequados e corrigir erros
- Sempre deixar o projeto num estado coerente
