# SquackTS — resultado da estabilização

O SquackTS mantém o propósito de gerir localmente catálogo, clientes, encomendas, produção POD e expedição. O núcleo foi melhorado e testado em Linux; a adequação comercial e a entrega Windows continuam incompletas.

**Código preservado:** commits locais de dependências (`9f58b11`), núcleo/dados (`c981b60`), interface (`47fcfcd`) e distribuição/CI (`d2b1d0b`), seguidos pela documentação e atualização do estado cloud. Consultar `git log -6 --oneline`. Não foi feito push; este histórico local não substitui uma cópia externa.

## 1. Evitar erros comerciais

Pagamento e estado operacional são independentes. Valores usam cêntimos; preços/custos históricos são preservados. A confirmação reserva stock, a expedição consome-o e o cancelamento liberta-o. Pedidos mistos reservam o disponível e produzem o restante. Variantes, personalização, arte e qualidade identificam o trabalho contratado.

**Lacunas:** o pagamento é apenas pendente/pago; expedir exige pagamento integral e tracking. Faltam sinais/recebimentos parciais, venda a prazo e levantamento em loja. Não existe cálculo de IVA, taxas, discriminação de imposto ou indicação estrutural de preços com/sem IVA. Os totais não são documentos fiscais; não se deve reinterpretar o histórico sem definir essas regras.

## 2. Dar clareza ao trabalho diário

As seis páginas e quatro editores partilham pesquisa contextual, mensagens recuperáveis, navegação por teclado e atualização após gravação. As listas principais têm paginação; a exportação respeita os filtros. O Painel separa valor confirmado, pago e por receber; a margem continua uma estimativa sem todas as despesas.

Com 10 000 encomendas/30 000 itens, a abertura da janela passou de 23,97 s para 0,39 s após paginação. A pesquisa piorou de 86,90 para 129,03 ms; normaliza Unicode durante a consulta, sem FTS/projeção normalizada. São medições locais.

Existe bloqueio de instância por perfil. As transações protegem reservas, mas falta versão por registo para detetar edições obsoletas. Não há suporte multiutilizador.

## 3. Recuperar e atualizar com segurança

Os dados ficam separados do programa. Migrações até à versão 6 criam cópia prévia e recusam versões futuras. Backups incluem SQLite consistente, imagens e checksums; o restauro valida o conteúdo e guarda uma cópia de recuperação. Não há backups agendados.

As migrações foram ensaiadas em bases temporárias/sintéticas, **não numa cópia identificada da tua base real**. Windows limpo, DPI e atualização também não foram ensaiados; CI/build estão preparados, sem execução no GitHub nesta tarefa. Não há instalador nem assinatura.

## Evidência e próximos passos

Em 20 de outubro de 2026 passaram 114 testes, Ruff e mypy (65 ficheiros). O executável Linux foi anteriormente aberto duas vezes com persistência. A [evidência técnica](docs/VALIDACAO.md) lista os três testes iniciais alterados, medições, comandos e limites.

Prioridade comercial: recebimentos/sinal, prazo e levantamento, juntamente com IVA explícito. Depois, controlo de versão e pesquisa otimizada; antes de fechar a distribuição, ensaio com cópia dos dados reais e Windows. As políticas de sinal, entrega a crédito e regime fiscal ainda precisam de definição. Integrações, expedições parciais e colaboração entre máquinas continuam por implementar.

**Ambiente cloud:** a consulta atual devolve a configuração publicada, com script de instalação e instruções de arranque, sem rascunho pendente. Podem ser revistos nas definições do ambiente. Um snapshot com estes novos commits exige nova publicação; essa publicação e a restauração numa tarefa nova não foram verificadas. Publicar o ambiente não faz push para o GitHub. O [README](README.md) contém os procedimentos de utilização e recuperação.
