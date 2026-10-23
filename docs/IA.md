# Otto: dados da operação e pesquisa externa

O Otto usa a Messages API da Anthropic. A cada pergunta, o backend consulta o PostgreSQL em uma transação somente leitura e envia contexto estruturado ao modelo. A ferramenta `web_search_20250305` permite pesquisar informações públicas quando necessário, usando a mesma chave da API.

## Configuração

No `.env` do servidor:

```dotenv
ANTHROPIC_API_KEY=SUA_CHAVE_AQUI
AI_MODEL=claude-sonnet-4-6
OTTO_WEB_SEARCH=1
```

Reinicie a API depois de alterar a configuração. `OTTO_WEB_SEARCH=0` desabilita a ferramenta. A pesquisa depende da disponibilidade do modelo e da permissão da organização na Anthropic. A busca pode gerar cobrança adicional à dos tokens, conforme o provedor. `configurado` indica presença da chave, não crédito ou conectividade. `pesquisa_web_habilitada` indica a configuração local, não comprova disponibilidade no provedor.

## O que perguntar

- “Pesquise fornecedores de batata em Blumenau e cite as fontes oficiais.”
- “Busque referências do Sebrae para reduzir desperdício em uma pequena cozinha.”
- “Pesquise a programação oficial da Oktoberfest e indique a data da informação.”
- “Quais insumos estão abaixo da meta no meu estoque?” usa o banco e não precisa de pesquisa externa.

Otto distingue dados da operação, resultados externos e sugestões. Preços da web são referências, não cotações locais aprovadas. Uma consulta pode preparar propostas de preço para revisão. Somente a confirmação explícita no painel grava a cotação. Não altera fichas nem realiza compras. Resultados externos não substituem saldos ou vendas registrados.

## Fontes e interface

A resposta mantém `resposta` em texto e acrescenta `blocos` com referências, `fontes_web` com URL e título, `pesquisa_web_utilizada` e `avisos`. As citações nativas do provedor aparecem junto ao trecho correspondente e em uma lista de links. Apenas URLs HTTP/HTTPS sem credenciais são aceitas. O navegador cria texto e links com DOM, nunca injeta HTML do modelo.

A interface distingue pesquisa efetivamente realizada de respostas que não usaram a web. Erros da ferramenta dentro de HTTP 200 geram avisos. Uma pesquisa sem citações não é apresentada como confirmação externa. Consultas de busca, resultados cifrados e índices internos do provedor não são enviados ao navegador.

## Dados internos e limites

- `GET /ia/status`, `GET /ia/contexto` e `POST /ia/perguntar` exigem usuário `gerente` ou `ia`. A operação vem da autenticação.
- O painel local usa `/demo/ia/perguntar` para a operação configurada no servidor, com limite de perguntas e restrição de acesso local por padrão.
- O modelo recebe agregados, fichas e nomes dos insumos. Não recebe credenciais, nomes de usuários ou pagamentos individuais.
- O prompt proíbe enviar contexto privado nas buscas e instrui ignorar comandos encontrados em páginas externas. Essas instruções não constituem uma garantia formal contra vazamento pelo modelo.
- Estoque, porções prontas e reposição refletem o momento da consulta. O histórico usa dias completos até ontem, separadamente da fotografia do estoque.
- As metas são 250 por sabor de segunda a quarta e 1.000 de quinta a domingo. O alerta de prontos ocorre estritamente abaixo de 30%. O monitor funciona independentemente da IA.
- Cálculos de consumo, custos e reposição permanecem determinísticos no servidor. Margem de ingredientes não é lucro líquido. Ausência de dados não comprova demanda zero.
- Cada pergunta é independente. Não há memória persistida, ferramentas de escrita, SQL livre, MCP ou recuperador documental.

## Integração e falhas

O endpoint Anthropic é fixo e não segue redirecionamentos. A conexão tem timeout de 5 segundos. A leitura tem timeout de 60 segundos com pesquisa e 30 segundos sem pesquisa. A saída tem limite de 2.400 tokens com pesquisa e 1.200 sem pesquisa. Há até três buscas por chamada ao provedor. Um `pause_turn` permite uma única continuação, preservando os blocos cifrados, portanto no máximo duas chamadas e até seis buscas por pergunta. Não há repetição automática de falhas de rede.

Erros de credencial, limite, timeout e configuração são sanitizados. `IA_PESQUISA_CONFIGURACAO` indica que o provedor recusou a requisição com busca habilitada e exige verificar modelo, permissões e configuração. Não há fallback silencioso que alegue pesquisa bem-sucedida.

Referência: [documentação oficial da pesquisa web Anthropic](https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool).

## Confirmação de preços pesquisados

Quando encontra preço e embalagem identificados, com fonte citada e correspondência em fornecedores e insumos cadastrados, Otto oferece uma proposta. O painel mostra fornecedor, insumo, produto da pesquisa, embalagem, preço anterior, novo preço e fonte. O usuário escolhe **Confirmar atualização** ou **Não alterar**. Um “sim” em texto não grava preços.

O backend persiste a proposta por 24 horas, sem modificar a cotação. Os IDs vêm do catálogo da operação e a fonte precisa constar nas citações da pesquisa. Na confirmação, exige gerente (ou acesso local autorizado), valida operação, prazo e se a cotação original continua igual. A confirmação é idempotente: um clique repetido não duplica o registro. Propostas canceladas não podem ser aplicadas.

Uma confirmação cria uma nova cotação pública, desativa a anterior desse par fornecedor/insumo e preserva o histórico. Frete, prazo, mínimo e validade ficam pendentes. Aceitar o cadastro não significa confirmar condições comerciais da loja. Há auditoria com usuário, proposta, fonte e cotações envolvidas. Custos de estoque recebido, vendas, perdas e preços de venda permanecem históricos.

As notificações PostgreSQL atualizam a lista e o comparativo de fornecedores. A dashboard inclui uma tabela de preços atuais que acompanha as mesmas notificações, sem misturar referências de compra com margens realizadas.

Rotas: `POST /ia/propostas-precos/{id}/confirmar` com `{"confirmar":true}` e `POST /ia/propostas-precos/{id}/cancelar`. O painel local usa as equivalentes sob `/demo/ia/`. Migration: `007_propostas_precos_otto.sql`.
