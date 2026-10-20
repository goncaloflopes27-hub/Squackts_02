# Revisões Claude/Gemini — correções 0.3.1

Referência revista: `0351ce9`, instalador `v0.3.0-rc.5`. O utilizador definiu **reembolsar sempre** ao cancelar uma encomenda paga e confirmou que ainda usa dados de teste. A aplicação regista o reembolso pendente e a confirmação manual; não executa transferências.

## Claude: verificação por descoberta

| ID | Resultado e tratamento |
| --- | --- |
| F1 | Reproduzido: OperationalError escapava e deixava saving ativo. Os quatro editores usam agora captura de Exception, reposição em finally, mensagem visível e logs. Existe excepthook Qt de produção. Regressões verificam SQLite/overflow/erro inesperado, campos preservados, nova tentativa e saída. |
| F2 | Confirmado: os ensaios eram offscreen. O novo exige plugin windows, qwindows.dll, capturas e JSON com plugin/versão. A ausência de DISPLAY já não força offscreen no Windows. Não substitui DPI no equipamento físico. |
| F3 | Confirmado para um checkout numa pasta arbitrária. O README explica backup completo na versão antiga e restauro na instalada. O utilizador ainda não tem dados reais. AppData instalado tem um ensaio de atualização próprio; não se afirma ter migrado dados reais. |
| F4 | Confirmado. Cancelar uma paga cria reembolso pendente, mantém o pagamento histórico e permite confirmar a devolução integral. O Painel mostra recebido, a reembolsar, reembolsado e líquido. A migração 7 não inventa devoluções históricas. |
| F5 | Confirmado: merge ref e tag no head podiam divergir. Os jobs usam o mesmo SHA; build-info.json identifica commit/versão. Runtime e instalador têm versão RC distinta. Publicação verifica commit/versão/hash e exige workflow_dispatch ou a aplicação explícita da label publish-installer num PR da própria conta. Não depende do nome da branch nem publica em cada push. |
| F6 | Confirmado o pin incompleto. Os logs anteriores mostram 6.7.1. Fixou-se Inno Setup 6.7.1, URL oficial, SHA-256 e verificação do ISCC. |
| F7 | O novo ensaio usa o instalador 0.3.0 publicado, verificado por hash, cria schema 6/dados/imagem e instala a nova versão. Usa LOCALAPPDATA isolado e caminhos acentuados; verifica migração, reinstalação e desinstalação. Não altera o nome da conta do runner. |
| F8 | Já havia limite no preço; faltavam limites na quantidade agregada e no total com portes. Os excessos são agora ValueError com rollback. Quantidade inteira máxima: 999 999 por linha agregada. |
| F9 | Já existia confirmação manual por item. Corrigiu-se o texto em bloco: o operador confirma produção/qualidade de TODOS os itens; arte pendente bloqueia a ação. Reprovação/retrabalho não foi implementado. |
| F10 | Reproduzido: uma interrupção deixava base antiga/imagens novas. Um marcador durável com hash da cópia de recuperação permite recuperar o par anterior antes da UI. Regressões incluem os._exit(77) num processo separado e interrupção após copiar a base. Não garante recuperação de falha física do disco. Pastas temporárias de processos mortos podem permanecer; não são apagadas indiscriminadamente. |
| F11 | Regressões para rascunho pago, cancelar expedida, artes distintas no mesmo produto, variante arquivada, pesquisa literal %/_, limite de imagem e EXIF. Não foi repetida toda a campanha de mutações; não se afirma cobertura integral. |
| F12 | O mínimo fixo foi confirmado. A janela adapta-se à área útil com margem para a moldura; editores ajustam-se ao ecrã. Testa-se área útil 1366×728 e acesso à ação Guardar. |

## Gemini: hipóteses confrontadas

O relatório declara não ter recebido código nem executado comandos. Strings Inno/Delphi pertencem ao instalador e não demonstram problemas nos serviços Python.

| ID | Verificação |
| --- | --- |
| 01 | WAL, foreign_keys e busy_timeout já estavam ativos; escritas usam BEGIN IMMEDIATE/rollback. Dois escritores não demonstram, por si, corrupção SQLite. Falta de versão por registo é uma limitação distinta. |
| 02 | Reserva mista e tarefas já pertenciam à mesma transação, com regressões de rollback e duas ligações sem excesso de reserva. |
| 03 | Preços/custos são snapshots; arquivo impede novas utilizações. Proibir todos os UPDATE em encomendas antigas impediria notas/tracking válidos. |
| 04 | Backup/inspeção já usam worker com ligação própria. Pesquisa continua síncrona: eficiência a medir, não P0 demonstrado. |
| 05 | Validação temporária, checksums e cópia prévia já existiam. A interrupção entre recursos era o defeito real, reproduzido em F10. |

## Evidência e limites

Suite local: **137 testes aprovados**, incluindo 23 regressões novas; Ruff aprovado; mypy sem erros em **68 ficheiros**. Log: `/workspace/.cloud-setup/Squackts_02/review-acceptance-tests.log`. Exceções deliberadamente injetadas não são falhas esperadas contadas como aprovações.

Regressões: tests/test_editor_recovery.py, tests/test_restore_interruption.py e tests/test_review_core.py. O hash do compilador foi confrontado com a release oficial e os bytes descarregados. A prova Windows é a execução do CI do PR #5, capturas, smoke-report.json e build-info.json; definir o workflow não equivale a executá-lo.

Pendentes: dados reais, DPI no computador do utilizador, assinatura, backups agendados, pagamentos parciais/crédito, IVA, reprovação/retrabalho e edição entre máquinas. Sem IVA, os totais não são documentos fiscais; isso não impede necessariamente acompanhamento de produção ligado a um sistema fiscal separado.
