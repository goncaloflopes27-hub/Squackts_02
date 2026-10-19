# Evidência de validação do SquackTS

Este documento acompanha o [relatório curto](../RELATORIO_IMPLEMENTACAO.md). Separa o que foi executado, o que o código contém e o que ainda precisa de ensaio. A referência inicial é `34d588a21561c8793616643806599c869cecf820`; a implementação está nos commits seguintes da branch de trabalho.

## Resultados executados

Em 20 de outubro de 2026, antes de criar os commits por área:

| Verificação | Resultado observado |
| --- | --- |
| `unittest discover -s tests -v` | 114 testes em 3,448 s; OK, sem testes ignorados |
| Ruff, incluindo UI | All checks passed |
| mypy | Sem erros em 65 ficheiros |

Log desta repetição: `/workspace/.cloud-setup/Squackts_02/pre-commit-tests.log`. Estes caminhos são evidência local deste ambiente, não artefactos já publicados no GitHub.

Na validação de implementação anterior passaram também `pip check`, compilação, `git diff --check`, arranque real com seis páginas e três atualizações do Painel, perfil vazio e perfil de demonstração. O pacote Linux foi aberto duas vezes fora do checkout; o ensaio verificou navegação, recursos e persistência SQLite.

| Ficheiro de testes | Quantidade |
| --- | ---: |
| test_core_flows.py | 32 |
| test_order_lifecycle.py | 16 |
| test_pod_inventory.py | 16 |
| test_data_recovery.py | 15 |
| test_background_jobs.py | 5 |
| test_reporting.py | 6 |
| test_final_regressions.py | 5 |
| test_ui_flows.py | 10 |
| test_ui_shell.py | 7 |
| test_distribution.py | 2 |

## Auditoria dos testes iniciais alterados

O ficheiro inicial `tests/test_core_flows.py` mantém 32 testes. Há três cenários alterados no diff em relação à referência:

| Teste | Antes | Agora e justificação |
| --- | --- | --- |
| `test_stock_rule_misto_partial_stock` | Um pedido superior ao stock disponível mantinha todo o disponível livre. | O disponível passa de 2 para 0, porque é reservado e o restante é produzido. É uma alteração de regra comercial, não apenas correção do teste. |
| `test_production_invalid_transition` → `test_production_repeated_command_is_idempotent` | Repetir o comando de iniciar produção lançava erro. | A repetição é aceite e mantém o estado `em_producao`. A intenção é permitir repetição segura; transições realmente inválidas continuam a ter testes próprios. |
| `test_production_valid_transition_chain` | O percurso chegava a expedida sem pagamento/tracking. | O cenário válido regista pagamento e tracking antes de expedir. Um novo teste verifica a recusa por todas as entradas quando esses dados faltam. |

Para rever a alteração exata:

```sh
git diff 34d588a21561c8793616643806599c869cecf820 c981b60 -- tests/test_core_flows.py
```

Os testes novos incluem `test_every_entry_point_rejects_dispatch_without_payment_and_tracking`, `test_catalog_change_and_commercial_revision_preserve_line_snapshot`, `test_explicit_reprice_only_drafts`, `test_concurrent_confirmations_do_not_oversell` e `test_two_connections_cannot_overreserve`. Os nomes identificam cenários concretos; o número total de testes não demonstra cobertura integral do produto.

## Concorrência e pesquisa: o que existe no código

O [arranque](../app.py) usa `QLockFile` em `<perfil>/.squackts.lock` e recusa outra instância normal do mesmo perfil. Serviços e scripts que acedam diretamente à base não adquirem automaticamente esse lock. A suite registada não contém um teste específico com dois processos a disputar esse lock.

Os serviços usam transações e os editores de produto/variante enviam apenas campos alterados. Os cenários de concorrência usam duas ligações SQLite locais. Não existe `row_version` nem condição geral de atualização do tipo `WHERE id = ? AND version = ?`; continua possível uma gravação obsoleta do mesmo campo por um acesso que contorne o uso de uma só instância. Isto não é suporte multiutilizador.

O [repositório de encomendas](../repositories/orders.py) regista uma função SQLite `CASEFOLD` e aplica-a aos campos pesquisados durante a consulta, com `LIKE '%termo%'`. Os parâmetros e os caracteres especiais de LIKE são tratados separadamente. Não existe FTS nem projeção de pesquisa normalizada. Uma coluna normalizada pode remover o custo da função, mas um índice B-tree comum não evita por si só a varredura em pesquisas com wildcard inicial. FTS exige ainda decidir se a pesquisa será por palavras, prefixos ou substrings.

## Migração e recuperação

Os [testes de recuperação](../tests/test_data_recovery.py) criam bases temporárias, versões anteriores e condições de falha. Incluem preservação de flags de pagamento, reconciliação, rollback, migração de valores REAL para cêntimos, recusa de versões futuras, imagens e restauro. Os [testes POD](../tests/test_pod_inventory.py) incluem adoção do stock já descontado pelo modelo antigo.

Não foi ensaiada uma cópia identificada como base real do utilizador. Os dados sintéticos demonstram os cenários codificados, não a ausência de anomalias no histórico real.

Antes de migrar uma instalação real: criar uma cópia consistente com a API de backup SQLite, preservar imagens, executar a migração num perfil separado e comparar contagens, IDs, relações, totais em cêntimos, reservas e referências de imagens. Inspecionar os registos de reconciliação, ensaiar restauro e obter validação operacional antes de substituir o perfil de trabalho. Não copiar apenas o `.db` de uma aplicação aberta com WAL.

## Medição de volume

Carga sintética: 10 000 encomendas, três itens por encomenda; mesmo ambiente Linux, Python 3.12 e Qt offscreen. A comparação é antes/depois da paginação durante esta implementação; não é apresentada como medição do commit inicial intacto.

| Operação Qt | Antes da paginação | Depois |
| --- | ---: | ---: |
| Construir e mostrar a janela preenchida | 23 967,76 ms | 390,12 ms |
| Atualizar Encomendas | 289,97 ms | 13,60 ms |
| Filtrar por pagamento | 221,38 ms | 25,33 ms |
| Atualizar Produção | 615,19 ms | 21,85 ms |
| Pesquisar | 86,90 ms | 129,03 ms |

Os tempos de lista/pesquisa são medianas locais. A pesquisa ficou aproximadamente 48,5% mais lenta; inclui a correção de maiúsculas Unicode. Os resultados não são garantias para Windows nem para o equipamento de utilização.

Reproduzir a carga atual:

```sh
QT_QPA_PLATFORM=offscreen python -m scripts.performance --orders 10000 --ui --output /tmp/squackts-performance.json
```

## Interface e distribuição

Foram capturadas e inspecionadas as seis páginas preenchidas em 1280×800, o Painel em 1600×1000, quatro editores, erro de submissão visível e pesquisa sem resultados. O perfil vazio foi exercitado. Capturas offscreen não demonstram comportamento de DPI ou integração com um desktop Windows.

A distribuição verificada é uma pasta Linux com executável e dependências. O workflow `.github/workflows/quality.yml` prepara checks Linux/Windows em Python 3.11/3.12 e build/smoke Windows, mas não foi executado no GitHub nesta tarefa. Não há instalador Windows, assinatura, ensaio de atualização Windows nem prova de instalação sem Python numa máquina Windows limpa.

## Comandos para repetir as verificações

Com as dependências de desenvolvimento instaladas, a partir da raiz do projeto:

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
python -m ruff check .
python -m mypy
python -m pip check
python -m compileall -q app.py config.py data_paths.py db.py pod_schema.py schema.py service_container.py utils.py repositories services ui scripts tests
git diff --check
QT_QPA_PLATFORM=offscreen python app.py --smoke-test
```

O smoke usa um perfil temporário por omissão. Empacotar exige `requirements-build.txt`, `python -m PyInstaller --noconfirm --clean packaging/Squackts.spec` e `QT_QPA_PLATFORM=offscreen python -m scripts.smoke_bundle`.

## Ficheiros locais da execução

Em `/workspace/.cloud-setup/Squackts_02/`: `full-tests.log`, `pre-commit-tests.log`, `app-smoke-final.log`, `app-smoke-empty.log`, `performance-ui-baseline.json`, `performance-ui-final.json`, `build-final.log`, `bundle-smoke-final.log`, `screenshots-final/`, `screenshots-empty/` e `bundle-screenshots/`.

O snapshot `pre-commit-source-20261020.tar.gz` preserva os fontes anteriores à criação dos commits. Ambos o snapshot e os commits continuam neste ambiente; não são uma cópia externa nem uma publicação no GitHub.
