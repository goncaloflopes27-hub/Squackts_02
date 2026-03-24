Squackts POD Manager
====================

Aplicação desktop local para gestão de operação Print-on-Demand com UI dark premium,
arquitetura limpa e dados em SQLite local.

Stack
-----
- Python 3.11+
- PySide6
- SQLite (sqlite3)
- Pillow

Arquitetura
-----------
- `ui/` -> interface (não faz SQL)
- `services/` -> regras de negócio, validações, transações e logs
- `repositories/` -> SQL parametrizado
- `db.py` + `schema.py` -> infraestrutura de dados e migrações idempotentes

Funcionalidades principais
--------------------------
- Gestão de produtos, clientes, encomendas, produção e sistema.
- Numeração anual de encomendas (`ENC-YYYY-0001`) com fallback seguro ao máximo em DB.
- Regras de stock por tipo de produção (`print_on_demand`, `stock_fisico`, `misto`).
- Sistema de backups completo:
  - criar backup
  - listar backups com metadata (data/hora + tamanho)
  - restore por seleção com confirmação obrigatória
  - retenção automática configurável e persistida em settings
- Diagnóstico técnico no Sistema:
  - existência/tamanho da DB
  - `user_version`
  - estado de diretórios críticos
  - ligação ativa
- Logging técnico:
  - arranque e encerramento da app
  - hook global para exceções não tratadas
  - eventos de backup/restore/retenção
- Imagens de produto com Pillow:
  - seleção de ficheiro local no editor
  - validação robusta de imagem
  - normalização/cópia para `assets/images/products`
  - preview no editor e no detalhe do catálogo

Setup rápido
-----------
1. Criar venv:
   - `python -m venv .venv`
2. Ativar:
   - Windows: `.venv\Scripts\activate`
   - Linux/macOS: `source .venv/bin/activate`
3. Instalar runtime:
   - `pip install -r requirements.txt`
4. (Opcional) instalar checks:
   - `pip install -r requirements-dev.txt`
5. Arrancar:
   - `python app.py`

Windows helpers
---------------
- `abrir_squackts.bat`
- `abrir_squackts.ps1`
- `criar_atalho_squackts.ps1`

Checks obrigatórios
------------------
- `python -m compileall .`
- `python -m unittest discover -s tests -v`
- `python -m ruff check .`
- `python -m mypy`

Estrutura resumida
------------------
- `app.py` -> entrypoint + logging técnico
- `service_container.py` -> bootstrap e DI
- `services/backup_service.py` -> backup/restore/retenção/diagnóstico
- `services/product_service.py` -> domínio de catálogo + pipeline Pillow
- `ui/pages/system_page.py` -> operações de sistema completas
- `ui/dialogs/product_editor.py` -> fluxo de imagem local com preview

Quality gates esperados
-----------------------
- Projeto compila sem erros.
- Testes da suite principal verdes.
- Ruff sem erros.
- Mypy sem erros.
- Sem SQL direto na UI.
- Fluxo de backup/restore/retenção funcional via SystemPage.
