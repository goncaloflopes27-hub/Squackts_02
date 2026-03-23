Squackts POD Manager
====================

Aplicação desktop local para gestão de operação Print-on-Demand com UI dark premium,
arquitetura limpa e dados persistidos em SQLite.

Stack
-----
- Python 3.11+
- PySide6
- SQLite (sqlite3)
- Pillow

Arquitetura
-----------
- `ui/` -> interface (sem SQL direto)
- `services/` -> regras de negócio, validações, transações e logs
- `repositories/` -> SQL parametrizado
- `db.py`/`schema.py` -> infraestrutura de dados e migrações idempotentes

Estrutura principal
-------------------
- `app.py` -> entrypoint
- `config.py` -> tokens/configuração geral
- `db.py` -> conexão/transações/backup
- `schema.py` -> schema + migrações idempotentes
- `service_container.py` -> bootstrap de infraestrutura e DI simples
- `utils.py` -> utilitários comuns

Domínio implementado
--------------------
- Money em centavos (`*_cents`) com conversão segura e arredondamento `ROUND_HALF_UP`.
- Numeração anual de encomendas: `ENC-YYYY-0001` (continua além de 4 dígitos quando necessário).
- Fluxo de encomendas com criação, edição, duplicação, tracking e cancelamento idempotente.
- Estados iniciais permitidos na criação: `rascunho` e `confirmada`.
- Tracking permitido apenas a partir de `pronta_envio`, e obrigatório em `expedida`/`concluida`.
- Estados `paga`, `expedida` e `concluida` exigem `pago=1`.
- Edição bloqueada para `expedida`, `concluida` e `cancelada`.
- Regras de stock por tipo de produção:
  - `print_on_demand` -> não desconta stock
  - `stock_fisico` -> exige stock e desconta
  - `misto` -> desconta quando há stock suficiente
- Produção com transições válidas de estado e logging.
- Migração de schemas legados (REAL -> cents) com validação de foreign keys.

Setup rápido
------------
1. Criar ambiente virtual:
   - `python -m venv .venv`
2. Ativar ambiente:
   - Windows: `.venv\\Scripts\\activate`
   - Linux/macOS: `source .venv/bin/activate`
3. Instalar dependências runtime:
   - `pip install -r requirements.txt`
4. (Opcional, recomendado) instalar dependências de qualidade:
   - `pip install -r requirements-dev.txt`
5. Arrancar aplicação:
   - `python app.py`

No arranque a app:
- garante diretórios obrigatórios
- cria/abre base SQLite
- aplica schema e migrações automaticamente

Quality gates (recomendado no dia a dia)
----------------------------------------
1. **Validação sintática / compilação de módulos**
   - `python -m compileall .`
2. **Testes de regressão (suite principal)**
   - `python -m unittest discover -s tests -v`
3. **Lint leve e rápido (ruff)**
   - `python -m ruff check .`
4. **Typing básico e pragmático (mypy)**
   - `python -m mypy`

Notas dos checks
----------------
- `unittest` é a suite oficial do projeto.
- Configurações de `ruff` e `mypy` estão em `pyproject.toml`.
- `mypy` cobre camadas de domínio e infraestrutura (`services`, `repositories`, `db.py`, `schema.py`, `service_container.py`, `utils.py`) com foco pragmático.

Comandos recomendados (copiar/colar)
-------------------------------------
- `python -m compileall .`
- `python -m unittest discover -s tests -v`
- `python -m ruff check .`
- `python -m mypy`
