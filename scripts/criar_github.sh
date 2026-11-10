#!/usr/bin/env bash
# Requer: GitHub CLI (gh) instalado e `gh auth login` feito.
# Uso: ./scripts/criar_github.sh NOME_DO_REPO
set -e
REPO=${1:-gestao-requisitos}
gh repo create "$REPO" --private --source=. --remote=origin --push
OWNER=$(gh api user -q .login)
gh auth refresh -s project >/dev/null 2>&1 || true
NUM=$(gh project create --owner "$OWNER" --title "Kanban - $REPO" --format json -q .number)
gh project link "$NUM" --owner "$OWNER" --repo "$OWNER/$REPO"

ARTEFATOS=(
"Processo de gerenciamento (Kanban)"
"Documento de visão e escopo"
"Requisitos não funcionais"
"Histórias de usuário"
"Architecture notebook"
"Storyboards com wireframes"
"Projeto físico do banco de dados"
"Protótipo do sistema"
"Vídeo de teste de sistema"
"Infraestrutura de implantação"
"Documento de autoria por membro"
"Revisão ortográfica final"
"Gerar e testar ZIP de entrega"
)
for t in "${ARTEFATOS[@]}"; do
  URL=$(gh issue create --title "$t" --body "Artefato do trabalho de ES." | tail -1)
  gh project item-add "$NUM" --owner "$OWNER" --url "$URL"
done
echo "Pronto! Abra: https://github.com/users/$OWNER/projects/$NUM"
echo "Obs: as colunas padrão são Todo/In Progress/Done; renomeie/adicione as de KANBAN.md no campo Status."
