# OktoStock — Python + PostgreSQL

MVP de backend para uma barraca: recebimento por lote → ficha técnica → venda → baixa FEFO → custo histórico → relatórios. DEV1 cuida da API e banco; DEV4 usa os relatórios para dashboard e previsão.

O PostgreSQL armazena os dados. O pgAdmin administra o PostgreSQL. O VS Code edita, executa e depura o Python. Esta implementação substitui a arquitetura Supabase do texto por uma API própria; não depende de Supabase.

## 1. Abrir no VS Code

Abra esta pasta com `code .`. Instale as extensões recomendadas de Python e Python Debugger. Use Python 3.11+ em uma instalação nova; o código também foi testado no Python 3.9 disponível neste computador.

No terminal integrado, macOS/Linux:

```sh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

No Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

No VS Code, execute **Python: Select Interpreter** e escolha `.venv`. No Windows, selecione `.venv\Scripts\python.exe`, pois o caminho sugerido em `settings.json` é para macOS/Linux.

## 2. Criar banco no pgAdmin

Instale/inicie PostgreSQL 14+ e conecte o pgAdmin ao servidor. Em **Login/Group Roles**, crie `oktostock`, defina uma senha e habilite apenas login. Em **Databases → Create → Database**, crie `oktostock`, com owner `oktostock`.

Alternativa no Query Tool, conectado como administrador, executar separadamente e com auto-commit habilitado:

```sql
CREATE ROLE oktostock LOGIN PASSWORD 'SUBSTITUA_POR_SENHA_LOCAL';
```

```sql
CREATE DATABASE oktostock OWNER oktostock;
```

Edite `.env` com host, porta e senha reais:

```dotenv
DATABASE_URL=postgresql://oktostock:SENHA@localhost:5432/oktostock
APP_TIMEZONE=America/Sao_Paulo
```

Caracteres especiais da senha precisam de percent-encoding na URL. `.env` não entra no Git. O token da API e a senha do banco são credenciais diferentes.

## 3. Criar tabelas e usuário gerente

```sh
python -m scripts.migrate
python -m scripts.create_user --nome "DEV1" --papel gerente --nova-operacao "Barraca de teste"
```

Guarde o ID da operação e o token exibido. A criação de usuário é administrativa, pelo terminal; clientes da API não escolhem sua permissão ou operação. O banco guarda apenas SHA-256 de tokens aleatórios de alta entropia.

Para DEV4:

```sh
python -m scripts.create_user --nome "DEV4" --papel ia --operacao UUID_DA_OPERACAO
```

Para DEV2/DEV3, use papéis `caixa` e `estoquista`. Cada pessoa/integração recebe token próprio. Para revogar uma credencial, o administrador define `usuarios.ativo=false` no pgAdmin. Esta versão não implementa login por senha, expiração automática ou recuperação de conta.

## 4. Executar e experimentar

```sh
python -m uvicorn app.main:app --reload
```

Ou pressione **F5 → OktoStock API** no VS Code. Abra [Swagger](http://127.0.0.1:8000/docs), clique em **Authorize** e cole apenas o token, sem `Bearer`. O Swagger monta o cabeçalho.

Fluxo manual: `POST /insumos` → `POST /produtos` com ingredientes → `POST /estoque/recebimentos` → `POST /turnos` → `POST /vendas`. Os UUIDs vêm das respostas anteriores. Consulte `GET /vendas/{id}` para conferir ingredientes, lotes e custo.

Os dados serão cadastrados posteriormente pelas rotas administrativas ou pelo fluxo definido pela equipe. Nenhum dado demonstrativo é criado automaticamente.

## 5. Testes

Crie um banco separado `oktostock_test`, com owner `oktostock`, e execute:

```sh
export TEST_DATABASE_URL='postgresql://oktostock:SENHA@localhost:5432/oktostock_test'
python -m pytest -q
```

No PowerShell use `$env:TEST_DATABASE_URL='postgresql://...'`. Cada teste cria e remove seu próprio schema nesse banco. Sem a variável, os testes de integração são marcados como ignorados. Não use banco de produção.

Cobertura: FEFO, custo histórico, rollback, venda duplicada e concorrente, disputa pelo último saldo, lote vencido, isolamento entre barracas, permissões, pagamentos, turno fechado, perdas e estorno.

## Arquivos e responsabilidades

- `app/main.py`: API e transações do DEV1.
- `app/schemas.py`: contrato e validação dos payloads.
- `migrations/001_initial.sql`: tabelas, índices e restrições.
- `scripts/migrate.py`: aplicação versionada e verificação de migrations.
- `docs/DEV1.md`: regras e próximos passos do backend.
- `docs/DEV4.md`: tarefas de dashboard/IA e critérios de aceite.
- `docs/API.md`: contrato para DEV2, DEV3 e DEV4.
- `scripts/dev4_compras.py`: exemplo Python de sugestão de compras, somente leitura.

## Escopo desta entrega

Implementado: insumos, ficha técnica por produto/versão, lotes, recebimento, turnos, venda com pagamentos informados, FEFO, perdas, estorno interno, disponibilidade, relatórios e tokens por papel/operação.

Ainda não implementado: integração dinâmica do frontend, login interativo, adicionais, descontos, conversão de embalagens, produção de insumos preparados, pedidos de compra, confirmação de pagamentos no provedor, devolução financeira automática, conciliação de caixa completa, sincronização offline e modelos preditivos treinados. Os endpoints rejeitam campos desconhecidos para não ignorar recursos ainda indisponíveis.

Esta base é para desenvolvimento do MVP. Antes de exposição pública, separar usuário de migrations do usuário runtime, configurar HTTPS, gestão de identidade/expiração de credenciais, limites de requisição, backups e observabilidade. O banco não deve ser acessível pelos frontends: as permissões por barraca são aplicadas pela API, sem RLS nesta versão. Relatórios ainda não têm paginação/filtros de período; devem recebê-los antes de grande volume.

Referências técnicas: [transações Psycopg](https://www.psycopg.org/psycopg3/docs/basic/transactions.html), [bloqueios PostgreSQL](https://www.postgresql.org/docs/current/explicit-locking.html), [segurança FastAPI](https://fastapi.tiangolo.com/tutorial/security/).

## Frontend e assistente IA

Frontend criado em **HTML e CSS**, com cinco telas responsivas: visão geral, estoque, vendas, fichas técnicas e assistente. Abra `frontend/index.html` diretamente ou, com a API ativa, acesse [painel](http://127.0.0.1:8000/painel/). As telas não exibem dados fictícios: mostram estados de espera pela integração. Continuam sem JavaScript e sem consultas reais ao banco pelo navegador.

O backend do assistente **Otto** já está preparado em `app/ai.py`. Para ativar posteriormente, defina `OPENAI_API_KEY` no `.env` e reinicie a API. O modelo é configurável por `AI_MODEL` (padrão `gpt-4.1-mini`). Não coloque a chave no frontend nem no Git.

- `GET /ia/status`: presença de configuração.
- `GET /ia/contexto`: indicadores e sugestões de compra; funciona sem chave.
- `POST /ia/perguntar`: pergunta com contexto autorizado; requer chave válida e token gerente/ia.

Adicionar a chave ativa a chamada no backend; o chat HTML permanece uma prévia até integrar a tela à API. Consulte [guia do frontend](docs/FRONTEND.md) e [configuração do agente](docs/IA.md). Testes do provedor são simulados, sem consumo real de API.

O prompt do Otto está em `app/prompts/otto.txt`. O contexto consulta cadastros reais e informa pendências quando faltam registros. A especificação recebida está em `docs/OTTO_REQUISITOS.md`; ela não é usada como seed de receitas ou preços.

## Perdas por receita e total

Disponível no menu **Perdas**, com API para registrar perdas de ingredientes vinculadas à receita ou porções completas. O relatório retorna totais por receita, ingrediente, motivo e período. Otto também recebe esses dados.

Execute `python -m scripts.migrate` para aplicar `002_perdas_receitas.sql`. Veja [guia de perdas](docs/PERDAS.md). A tela HTML/CSS mantém estados vazios até ser conectada à API; use `/docs` para cadastrar e consultar os dados reais.
