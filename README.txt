SquackTS
===================

Gestão desktop local de Print-on-Demand com Python, PySide6 e SQLite.
Catálogo -> Clientes -> Encomendas -> Produção -> Expedição -> Conclusão.

Windows, distribuição compilada:
  Extraia a pasta completa e execute SquackTS.exe.
  Mantenha a pasta _internal junto do executável. Não necessita de Python.

Windows, desenvolvimento:
  Instale Python 3.11 ou 3.12 e abra abrir_squackts.bat.

Instalação manual:
  python -m venv .venv
  Ative .venv (Scripts\Activate.ps1 no Windows; bin/activate no Linux/macOS).
  python -m pip install -r requirements-dev.txt
  python app.py

Teste sem dados reais:
  python -m scripts.demo --launch

Dados no Windows: %LOCALAPPDATA%\Squackts
Outras pastas e instalação isolada: consulte README.md / SQUACKTS_DATA_HOME.
Crie backups em Sistema e guarde uma cópia fora do computador.
Atualize apenas os ficheiros da aplicação, preservando a pasta de dados.

Checks:
  python -m unittest discover -s tests -v
  python -m ruff check .
  python -m mypy

Guia completo de operação, migração, backups/restauro, desenvolvimento,
distribuição Windows, CI e desempenho: README.md.
