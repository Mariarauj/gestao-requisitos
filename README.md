# Sistema de Gestão de Requisitos com Histórias de Usuário

Trabalho prático da disciplina de Engenharia de Software. O projeto é desenvolvido por processo iterativo e incremental, com gerenciamento por método Kanban.

## Sobre o projeto

Sistema de software que dá suporte à gestão de requisitos em projetos que usam **histórias de usuário** (metodologias ágeis, como Scrum). Ele permite organizar o trabalho de um projeto em backlogs, épicos e histórias, e priorizá-las com técnicas consagradas (story points, MoSCoW e RICE).

## Funcionalidades

- **Contas e autenticação:** cada usuário cria uma conta e se autentica para acessar os serviços.
- **Projetos:** criação, leitura, atualização e exclusão (CRUD).
- **Backlogs:** um *product backlog* por projeto e vários *sprint backlogs*.
- **Histórias de usuário:** CRUD no formato *Como [papel] eu quero [ação] para [benefício]*; criadas no product backlog e movimentáveis entre backlogs.
- **Épicos:** CRUD e vinculação de histórias a épicos.
- **Critérios de aceitação:** CRUD no formato *Dado [contexto] quando [ação] então [resultado]*.
- **Story points:** valores 0, 1, 2, 3, 5, 8, 13, 21, 34 ou 55.
- **MoSCoW:** etiqueta M, S, C ou W por história.
- **RICE:** Reach (nº de usuários), Impact (3, 2, 1, 0.5 ou 0.25), Confidence (100, 80 ou 50) e Effort (em story points), com pontuação calculada por `(R × I × C) / E`.

## Artefatos

| # | Artefato | Pasta |
|---|---|---|
| 1 | Processo de gerenciamento (Kanban) | `docs/01-processo-kanban` |
| 2 | Documento de visão e escopo | `docs/02-visao-escopo` |
| 3 | Requisitos não funcionais | `docs/03-requisitos-nao-funcionais` |
| 4 | Histórias de usuário | `docs/04-historias-de-usuario` |
| 5 | Architecture notebook | `docs/05-arquitetura` |
| 6 | Interface (storyboards e wireframes) | `docs/06-interface-wireframes` |
| 7 | Projeto físico do banco de dados | `docs/07-banco-de-dados` |
| 8 | Protótipo e vídeo de teste de sistema | `src/` e `docs/08-prototipo` |
| 9 | Infraestrutura de implantação | `docs/09-infraestrutura` |

## Estrutura do repositório

```
├── docs/      artefatos, uma pasta por artefato
├── src/       código do protótipo
└── README.md
```

## Gerenciamento

O projeto usa Kanban. O quadro fica no [GitHub Projects](https://github.com/Mariarauj/gestao-requisitos/projects); o propósito das colunas e as regras de uso estão em [`KANBAN.md`](docs/01-processo-kanban/KANBAN.md).

## Equipe

| Nome | Matrícula | Artefatos |
|---|---|---|
| Maria | 232023969 | 4, 5, 7, protótipo (backend e banco), autoria, ZIP |
| Pedro Ximenes | 200026071 | 1, 2, 3, 6, 9, protótipo (interface), vídeo |

## Tecnologias

Detalhes, justificativas e impacto das ferramentas no [architecture notebook](docs/05-arquitetura/architecture-notebook.docx).

| Item | Escolha |
|---|---|
| Interface | Gráfica (web) |
| Linguagem | Python |
| Framework | Streamlit |
| Banco de dados | PostgreSQL (SQLAlchemy e Alembic) |
| Autenticação | Própria (hash com bcrypt) |
| Testes | pytest |
| Implantação | Docker |

## Executando o protótipo

O código fica em `src/`. Pré-requisitos: Python 3.11 ou superior e PostgreSQL 16 (ou Docker).

```bash
cd src
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env                  # ajuste DATABASE_URL se necessário
docker compose up -d db               # PostgreSQL local (ou use um servidor próprio)
alembic upgrade head                  # cria as nove tabelas do artefato 7
streamlit run app.py                  # http://localhost:8501
```

Aplicação e banco juntos: `docker compose up --build` (dentro de `src/`).

Testes (apagam o conteúdo do banco indicado em `TEST_DATABASE_URL`):

```bash
createdb sgr_test                     # ou crie o banco de testes de outra forma
pytest
```

Estrutura de `src/`: `sgr/db` (conexão), `sgr/models` (tabelas), `sgr/repositories` (persistência), `sgr/services` (regras de negócio), `sgr/ui` (páginas do Streamlit), `migrations/` (Alembic) e `tests/`.
