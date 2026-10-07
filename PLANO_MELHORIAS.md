# Plano de melhorias — Sistema de Movimentação de Bens

Este documento registra as ideias iniciais para evoluir o projeto gradualmente. A ordem pode mudar conforme as prioridades e regras de negócio forem esclarecidas.

## Recomendações iniciais

1. **Segurança**
   - Retirar chaves e senhas do código e de arquivos versionados; usar variáveis de ambiente ou um gerenciador de segredos. Credenciais já publicadas devem ser rotacionadas.
   - Trocar o hash simples de senha por uma solução apropriada para senhas, como Argon2 ou bcrypt.
   - Rever autenticação, autorização e proteção das rotas e operações administrativas.
   - Rotacionar credenciais SMTP que tenham sido expostas e mantê-las fora do repositório.
2. **Organização do código**
   - Reduzir a responsabilidade concentrada em `app.py`, separando rotas, autenticação, serviços, acesso a dados e utilitários.
   - Preservar o comportamento existente durante a refatoração.
3. **Testes**
   - Criar testes para login, permissões, cadastro e movimentação de bens, férias e rotas principais.
   - Executar testes direcionados a cada mudança para evitar regressões.
4. **Persistência**
   - Avaliar a migração gradual de JSON/CSV para SQLite e, se necessário para produção ou múltiplos usuários, PostgreSQL.
   - Definir backup, restauração e integridade dos dados antes de migrar.
5. **Dados e auditoria**
   - Validar entradas, datas, identificadores e duplicidades.
   - Registrar quem realizou cada alteração e quando.
   - Melhorar cópias de segurança e retenção.
6. **Interface e relatórios**
   - Considerar paginação, filtros e feedback consistente nas telas.
   - Avaliar relatórios de inventário, bens sem responsável e equipamentos por departamento.
   - Reduzir estilos duplicados entre templates.
7. **E-mail e automações**
   - Separar os templates de e-mail, respeitar as opções de envio configuradas e melhorar o registro de falhas.
   - Avaliar tentativas automáticas de reenvio e execução programada confiável.

## Extensões e ferramentas a avaliar no VS Code

Instalar apenas o que for compatível com a versão do VS Code, as políticas da organização e as ferramentas já adotadas pelo projeto:

- **Python** e **Pylance** (Microsoft): suporte ao desenvolvimento e análise de Python.
- **Ruff**: lint e formatação Python, caso o projeto adote essa ferramenta.
- **Jinja** ou **Better Jinja**: realce e edição de templates Jinja/Flask.
- **SQLite Viewer**: inspeção local, caso o projeto passe a usar SQLite.
- **GitLens**: histórico e contexto de alterações Git.
- **REST Client**: testar endpoints HTTP com arquivos de requisição.
- **Live Preview**: pré-visualizar HTML estático; não substitui executar a aplicação Flask.

Extensões não alteram diretamente o modelo do assistente. Elas podem melhorar o contexto e as ferramentas disponíveis no VS Code; recursos de Copilot/agents dependem da versão, conta e configurações da instalação.

## Como vamos trabalhar

- Avançar em etapas pequenas, priorizadas pelo impacto para os usuários.
- Antes de mudanças estruturais, esclarecer regras de negócio e como o sistema é executado e publicado.
- Inspecionar o contexto relevante, fazer alterações focadas e validar cada etapa.
- Não migrar dados nem trocar tecnologias sem combinar previamente o escopo e o plano de segurança.

## Levantamento inicial

Prioridades confirmadas pelo usuário: considerar todas as frentes — confiabilidade do controle de bens e movimentações, segurança e acessos, inventário/busca/relatórios e redução de tarefas manuais.

Diretriz visual confirmada: preservar o padrão visual existente, com interface profissional, limpa e fácil de entender. Evitar emojis, elementos decorativos desnecessários ou soluções com aparência genérica/automatizada; manter os recursos e automações necessários, mesmo quando sua lógica for complexa, apresentando-os de forma clara e simples para o usuário.

Requisito de acesso informado: o administrador será da equipe de TI; outros usuários precisarão de contas e senhas, enquanto a equipe de TI define o que cada pessoa pode visualizar e quais ações pode executar.

Fluxo de contas escolhido: usuários solicitam acesso à TI; a TI cria a conta e atribui permissões.

Detalhamento das permissões: ainda em aberto; recomendar uma abordagem depois de mapear as telas e ações.

Ambiente informado: desenvolvimento local em `http://127.0.0.1:5000/` e produção em PythonAnywhere (`https://joaootaviolobo19.pythonanywhere.com`), com publicação manual após editar.

Fluxo de publicação informado: envia as alterações ao Git e depois atualiza o checkout conectado no console do PythonAnywhere. Alterações locais não afetam a produção até que o checkout seja atualizado e a aplicação recarregada.

Preparação de segurança para publicação: manter `FLASK_SECRET_KEY`, SMTP e token do cron fora do repositório. As variáveis de ambiente são opcionais: a configuração privada de e-mail pode permanecer em `dados/config_email.json` ou ser migrada para `dados/config_email.local.json`; o token do cron pode ficar em `dados/alertas_cron_token`. Preservar o cron-job existente de alertas: a aplicação mantém o endpoint `/api/rodar_alertas/<token>` e executa `enviar_alertas.py` quando o token configurado no servidor corresponde ao da URL agendada. Usuários existentes mantêm acesso; hashes SHA-256 legados migram para um hash de senha apropriado após autenticação bem-sucedida. Em uma instalação sem arquivo de usuários, criar o primeiro administrador somente com `BOOTSTRAP_ADMIN_USER` e `BOOTSTRAP_ADMIN_PASSWORD`. Não publicar nem compartilhar valores desses segredos. Alterações locais não afetam a produção até que o checkout seja atualizado e a aplicação recarregada.

Escala prevista: cerca de 10 usuários.

Concorrência e perfis: o site público terá acesso simultâneo; o ambiente local de desenvolvimento é usado apenas pelo responsável pelo projeto. A TI terá perfil administrador com acesso total. A recepção e outros perfis devem ver apenas as telas e informações autorizadas pela TI; exemplo informado para a recepção: funcionários e pessoas em férias.

Regra da recepção confirmada: acesso apenas de consulta às telas de funcionários e férias; não deve ver botões ou ações para cadastrar ou alterar funcionários nem férias. A TI mantém controle total.

Visibilidade dos campos: os campos exibidos serão definidos pelo perfil, com campos fixos para a Recepção conforme as regras confirmadas; não haverá configuração campo a campo pela TI nesta etapa.

Férias visíveis para a recepção: nome do funcionário, data de início e data de fim; sem outros detalhes por enquanto.
Na área de férias da recepção, mostrar somente períodos atualmente em andamento, não férias futuras nem encerradas.

Senhas: a TI deve controlar a redefinição pela área administrativa. Recomendação de segurança: não exibir nem guardar senhas legíveis; guardar somente um hash por usuário. Ao redefinir, substituir o hash anterior. Não será obrigatório exigir que o usuário troque a senha definida pela TI no primeiro acesso.

Fluxo de senhas confirmado: a TI terá uma área exclusiva para redefinir senhas, mas não poderá consultar a senha atual em texto; a senha antiga será substituída pelo novo hash.

Fonte e comportamento dos dados: o sistema consulta a planilha de bens, que também pode ser editada dentro do sistema. As demais áreas devem aproveitar esses dados e cruzá-los com as informações relacionadas, sem criar cópias divergentes. Exemplo dado: a tela de ramais deve mostrar, a partir dos dados existentes, se a pessoa tem telefone fixo e qual é seu ramal.

Fontes oficiais: variam por área e devem ser mapeadas uma de cada vez; não presumir que todos os cadastros venham da planilha.

Funcionários: a fonte oficial é uma planilha/arquivo separado, que é importado ou atualizado no sistema.

Férias: o RH informa à TI; a TI cadastra os períodos na aba Férias. Regra de alertas esclarecida: o e-mail de início deve ser enviado no dia em que o funcionário entra de férias; o aviso de retorno deve chegar um dia antes da volta para a TI providenciar o desbloqueio. O usuário verificou recentemente o alerta de retorno (volta em 08/10; e-mail recebido em 07/10) e confirmou que funcionou como previsto.

Fluxo de férias confirmado: o RH envia por e-mail os dados dos funcionários que entrarão de férias; a TI os cadastra manualmente na aba Férias e agenda o período.

Ramais: dados preenchidos na planilha de bens — ramal, funcionário e telefone fixo — devem alimentar automaticamente a aba Ramais, sem manter cópias divergentes. A lista também pode combinar ramais cadastrados diretamente pela TI para locais ou linhas compartilhadas que não constem na planilha, como a Portaria. Telefone fixo sem número de ramal não deve aparecer na lista. O funcionário terá um único ramal principal; locais/linhas compartilhados também podem aparecer.

Ramal por funcionário: um único ramal principal. A lista deve também suportar itens como Portaria, que não são necessariamente funcionários nem bens associados na planilha.

Formato desejado para a listagem de ramais: colunas “Ramal”, “Funcionário” e “Departamento”.

Exemplo para linha compartilhada: “RAMAL - PORTARIA - PORTARIA” (ramal, nome/identificação e departamento).

Duplicidades e conflitos de ramais: mostrar uma única linha por funcionário quando os dados forem consistentes. Se houver ramais diferentes para a mesma pessoa, sinalizar o conflito para a TI no sino de notificações do painel e exibir todos os ramais conflitantes, sem escolher um automaticamente. A TI resolve corrigindo os dados na Planilha; o aviso desaparece automaticamente quando não houver mais conflito.

Exportação de Ramais: PDF disponível somente para a TI. A Recepção pode consultar e buscar/filtrar a lista, mas não pode alterá-la nem exportar ou imprimir.

Cadastro de funcionários: a aba Planilha é editável no sistema e pode ser exportada/importada em CSV; a aba Funcionários também permite cadastrar funcionários, mas esse cadastro não altera a planilha de bens. Tratar essas duas fontes/áreas como distintas até esclarecer quando devem ser relacionadas.

Novos funcionários: o RH informa por e-mail e a TI os cadastra manualmente na aba Funcionários.

Campos definidos: aba Funcionários mantém nome, cargo e departamento. Aba Ramais mantém funcionário, departamento e ramal.

Identificação de bens: patrimônio pode ficar em branco quando não houver número patrimonial. A planilha principal reúne dados de bens e informações associadas, como responsável, departamento, telefones/impressoras e ramais.

ID de bem: confirmado ID interno permanente, independente do patrimônio, que continua opcional.

Exibição do ID: manter a coluna técnica persistente no CSV e ocultá-la da grade editável padrão.

Busca na Planilha: oferecer um único campo de busca que procure o texto em todos os campos do bem, não apenas nos campos usados na busca atual.

Volume atual: contagem da planilha feita em 07/10/2026 encontrou 513 registros de bens. O CSV tem cabeçalhos repetidos (“Departamento”), então ferramentas de leitura que exigem cabeçalhos únicos podem falhar; preservar a compatibilidade com esse formato ao implementar busca/importação.

Relação funcionário-bens: o sistema pode sugerir possíveis vínculos/alterações quando necessário, mas não deve modificar os bens automaticamente; a TI confirma ou faz o vínculo manualmente.

Saída do funcionário: ao excluir o cadastro na aba Funcionários, a TI também retira manualmente a pessoa da planilha principal. É importante verificar os bens atribuídos antes de essa informação ser retirada da planilha.

Ao excluir funcionário: permitir a exclusão do cadastro e criar alerta persistente no dashboard com os bens ainda atribuídos; a TI redistribui e resolve depois.

Resolução do alerta: a TI pode marcá-lo manualmente como resolvido após conferir, sem bloqueio automático baseado no estado dos bens.

Concorrência: pode haver vários usuários administrativos da TI editando dados no site simultaneamente.

Edição concorrente: se o mesmo bem mudar após a tela ter sido aberta, avisar sobre conflito e exigir recarregar antes de salvar, evitando sobrescrita silenciosa.

Auditoria: não é necessário manter log genérico de quem editou cada cadastro; o histórico de movimentações de bens é necessário.

Planilha oficial de bens: trata-se de `Levantamento Geral1(controle).csv`, no diretório do projeto. A aplicação lê esse arquivo e grava nele as edições feitas pela tela Planilha, fazendo uma cópia datada em `_backup_csv` antes de salvar.

O usuário pediu para continuar o levantamento sem tratar agora do risco do repositório público; manter o risco anotado como pendência crítica, sem repetir a discussão em cada pergunta.

Saída de funcionário: alertar a TI para redistribuir os bens, sem movimentação automática.

Detecção de saída: se a TI remover o funcionário da planilha de funcionários ou da aba Funcionários, o sistema deve verificar se ainda há bens atribuídos a essa pessoa e notificar a TI no próprio sistema. Não alterar automaticamente a atribuição dos bens.

Alerta de funcionário removido: exibir no dashboard da TI e manter até um administrador marcar como resolvido.

O alerta deve listar os bens pendentes (patrimônio, hostname e categoria) e permitir abrir os detalhes do bem.

Permissões de leitura: a TI deve escolher quais telas cada usuário pode consultar; para a recepção, o exemplo atual é Funcionários e Férias.
Recepção também pode consultar a lista de Ramais (Ramal, Funcionário e Departamento), em modo somente leitura: sem adicionar/remover ramais e sem exportar/imprimir PDF.
Busca/filtro na tela de Ramais da recepção é permitida; bloquear apenas alterações e exportação/impressão.
Na tela de funcionários da recepção, mostrar Nome, Cargo, Departamento e Ramal, com indicação visual de quem está de férias.

Permissões: usar perfis reutilizáveis e ajustáveis pela TI, atribuídos aos usuários.

Perfis iniciais: somente TI (administrador) e recepção. A arquitetura deve permitir criar outros logins/perfis com especificações definidas pela TI quando surgir necessidade, sem implementar perfis adicionais agora.
Login da recepção: uma conta individual por pessoa, todas atribuídas ao perfil Recepção (não uma senha compartilhada).
Qualquer usuário com perfil da TI pode administrar tudo, incluindo criar contas e gerenciar permissões.
Saída de usuário do sistema: preferência informada por apagar a conta e os dados de acesso, em vez de desativá-la. Preservar separadamente os registros históricos de movimentações já realizados.

Movimentações: somente a TI executa e registra transferências de bens.

Auditoria das movimentações: registrar conta logada da TI, bem, origem e destino, departamentos, data/hora e observação.
Esclarecimento: o histórico deve identificar a conta individual da TI que realizou a movimentação, ainda que as permissões administrativas sejam controladas pela TI.

Status dos bens: manter os valores existentes na planilha, mas permitir à TI configurar a lista de status.

CSV de bens: não há rotina recorrente de importação. O arquivo foi usado como carga inicial; desde então, a TI edita os registros existentes pela Planilha do sistema. Não projetar uma importação/substituição de CSV sem necessidade confirmada.

Gestão de bens: a TI precisa cadastrar bens, editar os existentes e excluir bens.

Exclusão de bem: a preferência informada é apagar definitivamente o bem e todas as movimentações associadas. É uma exclusão irreversível no sistema; considerar confirmação clara e backup antes de executar.

Proteção para exclusão: antes de apagar, mostrar o bem e a quantidade de movimentações que também serão excluídas, e pedir confirmação explícita.

Dashboard: o usuário quer alertas, gráficos e informações úteis, e pediu que eu recomende indicadores depois de entender melhor o fluxo. Recomendações candidatas a validar: bens sem responsável; distribuição por categoria/departamento; status de manutenção/descarte; movimentações recentes; avisos de funcionários removidos ainda com bens; próximos retornos de férias.

Dashboard atual: já mostra gráficos, sino de alertas de funcionários e métricas de total de bens, funcionários, departamentos, movimentações e bens sem responsável. Existem 8 bens sem responsável porque impressoras são atribuídas a departamentos, não a pessoas; esse número não deve ser tratado automaticamente como erro/anomalia. A métrica deve manter o total e separar bens sem responsável pessoa daqueles alocados a departamentos.

Métrica de bens sem responsável: manter o indicador atual (total 8), mesmo incluindo impressoras atribuídas a departamentos, e acrescentar a separação entre bens sem responsável pessoa e bens alocados a departamentos.

Gráficos do dashboard: manter os três atuais (bens por categoria, bens por departamento e movimentações nos últimos 12 meses); a TI autoriza acrescentar outros gráficos úteis sem retirar esses.

Sino do dashboard: já apresenta alertas de férias e retorno, além de alertas de funcionários. Preservar essa funcionalidade existente ao evoluir o painel.

Backup e versionamento: o usuário acredita que PythonAnywhere/Git mantém cópias automáticas. Verificação local mostrou que os arquivos em `dados/` estão rastreados pelo Git, incluindo a configuração de e-mail com uma credencial. É urgente rotacionar essa credencial e planejar a retirada segura de segredos/dados operacionais do versionamento; alteração do `.gitignore` sozinha não remove arquivos já rastreados ou do histórico. Confirmar visibilidade do repositório e política de backup/restauração antes de editar dados de produção.

Visibilidade informada: o remoto está público atualmente e a intenção é torná-lo privado após a fase de programação. Como dados e uma credencial estão versionados, não adiar a privatização nem a rotação da credencial até essa fase; considerar os dados expostos e seguir a política interna da empresa para incidentes de dados.

Prazo informado: por volta das 13h, o usuário pretende enviar dados atualizados ao remoto para atualizar o site. Não enviar arquivos de dados/credenciais a um remoto público. Antes desse envio, tornar o repositório privado e confirmar que PythonAnywhere mantém acesso, ou usar um canal privado separado para dados/deploy. Privatizar o remoto pode exigir configurar autenticação do checkout no PythonAnywhere; verificar o fluxo sem expor credenciais.

## Implementado localmente nesta etapa

- A TI pode criar contas individuais com perfil inicial de TI ou Recepção, redefinir senhas e excluir contas. A exclusão da própria conta em uso e do último administrador é bloqueada; o histórico de movimentações permanece separado das contas.
- Perfis reutilizáveis podem receber permissões de consulta, edição e exportação por tela. Transferências de bens e impressão/exportação de Ramais permanecem exclusivas da TI, inclusive para perfis personalizados.
- As edições da Planilha, do cadastro de bens e das transferências validam a versão mais recente do registro sob bloqueio de escrita compartilhado. Se outro usuário alterou o bem, a operação é recusada e a tela pede recarga.
- O CSV recebe a coluna técnica `ID interno` na primeira gravação feita pelo sistema. Ela não aparece como campo editável da Planilha, não depende do patrimônio e preserva a identidade do bem após exclusões. Os cabeçalhos repetidos existentes são mantidos.
- A exclusão de um bem mostra sua identificação e quantas movimentações serão removidas. Antes da exclusão, o sistema exige que consiga criar cópias de segurança do inventário e do histórico.
- Novas movimentações guardam o nome da conta da TI que as registrou. Históricos antigos recebem a coluna nova sem atribuir retroativamente um responsável desconhecido; a cópia anterior é preservada em backup.
- A TI pode manter a lista de status dos bens. A tela de Bens é paginada, seus filtros usam o inventário completo e a busca da Planilha considera também campos que não estão visíveis na grade.
- A edição de férias valida datas, períodos duplicados e status, preservando o status legado “Férias iniciada”. As gravações JSON/CSV são atômicas; os alertas por e-mail validam destinatários, registram falhas e repetem falhas transitórias.
- Foram adicionados testes de regressão para permissões, rotas sem mapeamento, exportação, transferência e status de férias. A cobertura de operações e de envio de e-mail ainda precisa ser ampliada.
- Após a revisão visual, a Central de Atendimento deixa de ser concedida implicitamente ao perfil TI: somente Recepção e perfis aos quais a TI atribuir explicitamente essa permissão podem vê-la e abri-la. A situação “Em férias” aparece junto ao nome na Central.
- Foi removido o atalho global da chave e a troca da própria senha por esse modal; a redefinição de senha continua na tela Usuários e perfis. O menu lateral tem transições ajustadas e comportamento distinto para desktop e celular.
- A exportação de Ramais foi refeita para seguir a referência enviada: página A4 retrato, lista em duas colunas e áreas prioritárias no início. A impressão do Organograma agora expande a hierarquia, usa folha A4 paisagem e oferece controles para expandir/recolher os níveis na visualização.

Essas alterações ainda são locais: não foram enviadas ao GitHub nem publicadas no PythonAnywhere. Migração de persistência, retenção/restauração de backups, separação arquitetural de `app.py`, cobertura de testes mais ampla e inspeção visual no navegador continuam pendentes; não fazem parte de uma migração automática nesta etapa.

**Agendamento de e-mails:** foi mantido o endpoint e o horário compatíveis com o cron-job existente. A rotina envia alertas de início no próprio dia e de retorno no dia anterior, conforme as opções de e-mail. O token pode ser mantido em `dados/alertas_cron_token` no PythonAnywhere (não é obrigatório criar variável de ambiente). A configuração SMTP antiga continua sendo lida em `dados/config_email.json`; por estar rastreada no Git local e marcada para remoção, fazer uma cópia privada fora do caminho versionado antes do `git pull`, preferencialmente `dados/config_email.local.json`, também suportado. Não incluir segredos no Git. Após publicar, validar uma execução de teste e conferir o histórico do Cron-job. Como o token da URL foi compartilhado durante a conversa, considerar sua rotação após planejar a atualização correspondente no Cron-job.
