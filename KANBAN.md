# Processo Kanban

O quadro fica no [GitHub Projects](https://github.com/Mariarauj/gestao-requisitos/projects). Cada cartão é uma issue.

## Colunas

| Coluna | Propósito |
|---|---|---|
| Backlog | Todas as tarefas identificadas, ainda não priorizadas. |
| A Fazer | Tarefas priorizadas e prontas para começar. |
| Em Andamento | Tarefas em execução. |
| Em Revisão | Prontas, aguardando revisão do outro membro (ortografia, conteúdo, código). |
| Concluído | Revisadas, aprovadas e salvas no repositório. |

## Regras

1. Todo trabalho vira cartão; nada é feito sem cartão.
2. Cartões novos entram no Backlog; os priorizados vão para A Fazer.
3. Quem assume o cartão move para Em Andamento, respeitando o WIP.
4. Ao terminar, o responsável move para Em Revisão e avisa o outro membro.
5. O outro membro revisa e move para Concluído, ou devolve para Em Andamento com comentário.
6. Cada membro mantém seus cartões atualizados.

## Informação de cada cartão

Título, descrição, artefato relacionado, responsável, prazo e critério de pronto (template em `.github/ISSUE_TEMPLATE/cartao.md`).
