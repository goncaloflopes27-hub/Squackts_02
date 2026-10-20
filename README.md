> **Apresentação 0.3.2:** novo tema, fonte Inter incluída, Ctrl+K para comandos, Ctrl+F para pesquisa e rascunho local nas novas encomendas. O instalador continua a criar os atalhos automaticamente. [Alterações e limites](docs/REDESENHO_UI.md) · [Capturas da interface](docs/screenshots/).

# SquackTS

Aplicação desktop local para gerir Print-on-Demand: catálogo, clientes, encomendas,
reservas de stock, produção, expedição e recuperação de dados. A interface usa
PySide6 e os dados ficam em SQLite, sem depender de um servidor.

O [relatório de implementação](RELATORIO_IMPLEMENTACAO.md) resume os resultados e
as prioridades. A [evidência de validação](docs/VALIDACAO.md) identifica os testes
alterados, as medições e o que ainda não foi ensaiado.
As [respostas às revisões externas](docs/REVISAO_EXTERNA.md) registam as correções
da versão 0.3.1 e os limites que continuam pendentes.

## Limites comerciais atuais

O pagamento é um registo manual pendente/pago; a expedição exige pagamento integral
e tracking. Ainda não existem sinais/recebimentos parciais, venda a prazo ou um
percurso próprio de levantamento em loja. Estas são prioridades da próxima entrega
comercial. A aplicação também não calcula nem discrimina IVA e não identifica
estruturalmente se os preços incluem imposto. Os totais não são documentos fiscais;
não atribua retroativamente IVA aos valores antigos sem definir a regra comercial.

O arranque normal impede duas instâncias do mesmo perfil. Não existe controlo de
versão por registo para detetar todas as edições obsoletas nem suporte multiutilizador.

## Utilização no Windows

Use o instalador **SquackTS-Setup-<versão>-x64.exe** em Windows 10/11 de 64 bits.
Instala a aplicação e as dependências na conta atual, cria automaticamente atalhos
no Ambiente de Trabalho e no menu Iniciar e permite abrir o SquackTS no fim.
Não é necessário instalar Python, extrair pastas ou executar comandos.

Para voltar a abrir, use o atalho **SquackTS**. Para atualizar, feche a aplicação
e execute o instalador novo; os dados ficam numa pasta separada e não são apagados
pela reinstalação ou desinstalação. O instalador atual não tem assinatura digital;
o Windows pode apresentar um aviso de editor desconhecido.

A distribuição portátil em pasta continua disponível para ensaios técnicos:
mantenha `_internal` junto de `SquackTS.exe` e copie a pasta completa.

Para desenvolvimento a partir deste repositório, instale Python **3.11 ou 3.12**
com a opção de adicionar ao PATH e abra `abrir_squackts.bat`. O launcher cria
`.venv` e instala as versões fixadas. Volta a instalar quando `requirements.txt`
ou `constraints.txt` mudam; não atualiza o pip em cada arranque.

Para criar um atalho, execute `criar_atalho_squackts.ps1`. Também pode apontar o
parâmetro `-ProjectPath` para a pasta da distribuição que contém `SquackTS.exe`.

## Primeiro percurso

1. Em **Catálogo**, crie um produto com SKU único, preço e custo. Escolha POD,
   stock físico ou misto. Importe a imagem para ser gerida pela aplicação.
2. Em **Clientes**, crie o cliente com os contactos e dados de entrega.
3. Em **Encomendas**, escolha o cliente, produtos/variantes e quantidades. Confira
   os portes e o resumo. Guarde como rascunho ou confirme para iniciar o trabalho.
4. Em **Produção**, consulte o trabalho por encomenda e item. Aprove a arte quando
   necessária, execute a produção e confirme o controlo de qualidade. Pedidos
   exclusivamente de stock podem seguir para preparação do envio.
5. Quando a encomenda estiver pronta, marque o pagamento, indique o tracking e
   execute **Expedir**. Pagamento e tracking são obrigatórios para expedir em
   qualquer página. Depois da entrega pode concluir a encomenda.
6. Em **Sistema**, execute o diagnóstico e crie um backup. Guarde uma cópia desse
   ZIP fora do computador onde trabalha.

O pagamento é separado do estado operacional. Os valores ficam em cêntimos e os
preços/custos contratados são preservados ao editar notas ou tracking. Atualizar
preços a partir do catálogo é uma revisão comercial explícita.

Cancelar uma encomenda paga gera um **reembolso pendente**, conforme a política de
devolver sempre o valor. Depois de devolver o dinheiro fora da aplicação, use
**Confirmar dinheiro devolvido** no detalhe. A aplicação regista a confirmação e o
histórico; não executa transferências. O Painel distingue recebido, reembolsos
pendentes, reembolsado e recebido líquido, incluindo cancelamentos.

Na confirmação, o stock físico é reservado; na expedição é consumido; o cancelamento
liberta a reserva. Em pedidos mistos, o disponível é reservado e o restante é
produzido. Produtos ou clientes arquivados mantêm o histórico e deixam de ser
escolhas para novas encomendas. A margem apresentada é uma estimativa baseada nos
custos guardados nas linhas, sem constituir contabilidade fiscal.

## Dados, atualização e recuperação

Os dados são independentes da pasta do programa:

| Plataforma | Pasta por omissão |
| --- | --- |
| Windows | `%LOCALAPPDATA%\Squackts` |
| Linux | `$XDG_DATA_HOME/squackts`, ou `~/.local/share/squackts` |
| macOS | `~/Library/Application Support/Squackts` |

A pasta contém `data/pod_manager.db`, `images/`, `backups/` e `logs/`. Para uma
instalação isolada, defina `SQUACKTS_DATA_HOME` **antes** de arrancar. O caminho
efetivamente utilizado pode ser consultado em Sistema.

Antes de atualizar, crie um backup e feche a aplicação. Substitua os ficheiros da
distribuição, mantendo a pasta de dados do utilizador. O arranque aplica migrações
numeradas e recusa bases de versões mais recentes. Antes de migrar uma base
existente é criada uma cópia de segurança. Uma instalação antiga com
`data/pod_manager.db` junto do código pode ser importada no primeiro arranque; a
origem é preservada e um destino já existente nunca é substituído.

O backup ZIP contém a base SQLite consistente, imagens geridas e um manifesto com
checksums SHA-256. Em **Sistema → Restaurar**, selecione o backup, confira o resumo
e confirme a substituição. O conteúdo e a integridade são verificados antes de
escrever; o conjunto atual recebe um backup de recuperação. Reinicie a aplicação
após o restauro. Backups antigos apenas de SQLite continuam suportados, mas não
contêm imagens. Não copie apenas o ficheiro `.db` com a aplicação aberta: o SQLite
pode ter alterações confirmadas ainda no WAL.

As cópias mantidas no mesmo disco protegem contra erros de edição, mas a recuperação
de uma avaria do computador exige uma cópia guardada noutro local. A aplicação foi
preparada para uso local por uma operação; partilhar diretamente o SQLite numa
pasta de rede não constitui uma solução de colaboração entre máquinas.

### Passar de uma versão antiga para a instalada

Se os dados estavam noutra pasta/checkout, abra a versão antiga e crie um backup
completo ZIP em Sistema. Na instalada, use Sistema → Restaurar, confira o conteúdo
e confirme. Os dados atuais recebem uma cópia de recuperação. Reinicie depois.
Um backup apenas SQLite não inclui imagens. A aplicação não procura nem substitui
automaticamente bases em pastas arbitrárias do computador.

Para uma instalação que já usa AppData, execute o instalador novo com a aplicação
fechada. A base é migrada com cópia prévia. O ensaio automático compara dados
sintéticos entre 0.3.0 e a nova versão; não valida dados reais do utilizador.
Um restauro interrompido é detetado e recuperado no arranque.

## Desenvolvimento

```sh
python -m venv .venv
# Linux/macOS:
source .venv/bin/activate
# Windows PowerShell:
# .\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
python app.py
```

Python 3.11 e 3.12 são as versões de referência da matriz de CI. Dependências diretas
estão fixadas em `requirements*.txt`; `constraints.txt` fixa também a resolução
transitiva para essas versões de Python. A instalação mantém a verificação TLS
normal do pip. Linux precisa das bibliotecas de sistema do Qt; em Ubuntu:

```sh
sudo apt-get install libegl1 libopengl0 libxkbcommon0
```

Num ambiente sem ecrã, use `QT_QPA_PLATFORM=offscreen` para testes Qt; o modo normal
requer uma sessão gráfica. Este repositório é o checkout de trabalho; uma tarefa
cloud já é isolada e não necessita de outro worktree.

### Verificações

```sh
python -m pip check
python -m unittest discover -s tests -v
python -m ruff check .
python -m mypy
python -m compileall -q app.py config.py data_paths.py db.py pod_schema.py schema.py service_container.py utils.py repositories services ui scripts tests
```

`unittest` é a suite oficial e inclui testes de domínio, migração/recuperação e Qt.
Ruff cobre também a UI. Mypy verifica o arranque, a UI, as camadas de dados e
serviços, a configuração e as ferramentas. No Linux headless:

```sh
QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -v
```

O arranque também dispõe de verificações sem tocar no perfil normal:

```sh
python app.py --version
python app.py --smoke-test --screenshots .local/screenshots
# Perfil explícito para ensaiar persistência entre arranques:
python app.py --data-dir .local/test-profile
```

Sem `--data-dir`, `--smoke-test` usa dados temporários e fecha após percorrer as
seis páginas e repetir o refresh do Painel. As capturas indicadas em
`--screenshots` são guardadas antes de terminar. O arranque normal continua a
abrir o perfil persistente escolhido.

`.github/workflows/quality.yml` executa estes checks em Ubuntu e Windows com
Python 3.11/3.12. Depois dos checks, constrói a distribuição Windows e abre o
executável duas vezes em modo de teste, numa pasta temporária, verificando também
a persistência. O artefacto `SquackTS-Windows-x64` fica disponível nessa execução.
Um workflow preparado localmente só produz essa evidência depois de executado no
GitHub; o build Linux não demonstra compatibilidade Windows.

### Demonstração separada

```sh
python -m scripts.demo --launch
# Opcional: escolher uma pasta nova para os dados fictícios
python -m scripts.demo --home /caminho/para/demo --launch
```

Por omissão usa `.demo/`, ignorada pelo Git. Cria dois clientes, três produtos e
oito encomendas fictícias. Reabrir mantém os registos existentes; o script recusa
uma pasta não vazia sem o marcador de demonstração. Nunca use essa pasta como
arquivo de dados reais.

### Medição de desempenho

```sh
python -m scripts.performance --orders 10000 --output .local/performance.json
# Incluir a janela e as operações reais de pesquisa, filtro e atualização:
python -m scripts.performance --orders 10000 --ui --output .local/performance-ui.json
```

Cria uma base **temporária**, com três itens por encomenda, usando os serviços do
domínio, e mede arranque, indicadores, encomendas e fila de produção. A base é
eliminada no fim; os dados reais não são abertos. O JSON permite comparar a mesma
carga na mesma máquina. Com `--ui`, mede também o arranque da janela, pesquisa,
filtro de pagamento e atualização das páginas Encomendas e Produção; num ambiente
sem ecrã usa o Qt offscreen. Estas medições não substituem uma avaliação visual nem
constituem um orçamento garantido de latência.

Na medição local de desenvolvimento com Python 3.12, Qt offscreen, 10 000
encomendas e 30 000 itens, foram obtidos estes resultados:

| Operação na interface | Antes da paginação | Versão atual |
| --- | ---: | ---: |
| Arranque da janela | 23 967,76 ms | 390,12 ms |
| Atualizar Encomendas, mediana | 289,97 ms | 13,60 ms |
| Pesquisar Encomendas, mediana | 86,90 ms | 129,03 ms |
| Filtrar pagamento, mediana | 221,38 ms | 25,33 ms |
| Atualizar Produção, mediana | 615,19 ms | 21,85 ms |

A versão atual inclui pesquisa sem distinguir maiúsculas Unicode; neste ensaio,
a pesquisa foi mais lenta. Estes resultados pertencem à carga sintética e ao
mesmo ambiente, e devem ser medidos novamente no computador de utilização.

### Distribuição

No Windows com o Python de desenvolvimento instalado:

```powershell
.\scripts\build_windows.ps1
```

O script instala dependências fixadas, corre checks e gera `dist\SquackTS\`.
`-SkipChecks` permite reutilizar checks acabados de executar. Também é possível:

```sh
python -m pip install -r requirements-build.txt
python -m PyInstaller --noconfirm --clean packaging/Squackts.spec
python -m scripts.smoke_bundle
```

Para gerar também o instalador, instale Inno Setup 6 no computador de build e execute:

```powershell
.\scripts\build_installer.ps1
# Se a distribuição já foi construída e verificada:
.\scripts\build_installer.ps1 -SkipBuild
python -m scripts.smoke_installer dist\installer\SquackTS-Setup-0.3.0-x64.exe
```

O último comando instala/reinstala/desinstala e cria/remove os atalhos da conta;
execute-o apenas num runner Windows descartável sem uma instalação existente.
Verifica arranque, dados e imagens preservados. A CI produz o artefacto
`SquackTS-Windows-Installer`, que contém o `.exe` a entregar ao utilizador.

O build deve correr no sistema de destino. A distribuição em diretório inclui o
runtime Python, plugins Qt, ícone e recursos; no Windows inclui metadados de versão.
O smoke test executa a aplicação a partir de outra pasta e confirma persistência
entre arranques. A validação final numa máquina Windows sem Python continua a ser
uma etapa de entrega, incluindo DPI, navegação por teclado e recuperação de backups.

## Arquitetura

- `ui/`: sidebar, topbar, páginas e diálogos PySide6; sem SQL direto.
- `services/`: regras, transações, eventos de alterações, ficheiros geridos e backups.
- `repositories/`: SQL parametrizado e consultas de leitura.
- `schema.py` / `pod_schema.py`: migrações e modelo persistente.
- `config.py` / `data_paths.py` / `db.py`: caminhos, migração de instalação e SQLite.
- `service_container.py`: composição e inicialização das dependências.
- `scripts/` / `packaging/`: demonstração, medições, distribuição e recursos.

As regras de implementação estão em [AGENTS.md](AGENTS.md). O plano e os seus
critérios de aceitação estão em [PLANO_MELHORIAS.md](PLANO_MELHORIAS.md).
