# Otto — backend preparado

A integração inicial usa a Messages API da Anthropic. A tela do Otto consulta a API com token de usuário e envia perguntas. As demais telas permanecem estáticas. A base okto contém dados simulados identificados no contexto. Os endpoints abaixo já podem ser usados pelo Swagger ou por um cliente autorizado.

## Ativar depois

1. Se ainda não existir, copie `.env.example` para `.env` e configure o PostgreSQL como descrito no README.
2. Preencha no `.env` local:

```dotenv
ANTHROPIC_API_KEY=SUA_CHAVE_AQUI
AI_MODEL=claude-sonnet-4-6
```

3. Reinicie a API. A aplicação lê o `.env` na inicialização. Se o modelo não estiver disponível na sua conta, configure `AI_MODEL` com um modelo de texto compatível com a Messages API ao qual você tenha acesso.
4. Em `/docs`, autorize com o token de usuário `gerente` ou `ia` criado pelo DEV1. Esse token é diferente da chave Anthropic.
5. Consulte `GET /ia/status` e envie `POST /ia/perguntar`:

```json
{
  "pergunta": "Quais ingredientes precisam de reposição para os próximos três dias?",
  "dias_historico": 14,
  "dias_cobertura": 3
}
```

`configurado: true` indica somente presença de chave; não valida saldo, permissão do modelo nem conexão com o provedor. As chamadas reais usam a conta de API configurada. Os testes automatizados usam respostas simuladas. A configuração local também foi validada com chamada real à Anthropic em 21/10/2026.

## Rotas

| Rota | Função |
|---|---|
| GET /ia/status | Indica presença de configuração, modelo e modo somente leitura; nunca retorna a chave |
| GET /ia/contexto?dias_historico=7&dias_cobertura=3 | Retorna agregados e sugestões determinísticas, mesmo sem chave |
| POST /ia/perguntar | Monta contexto autorizado e solicita uma explicação ao modelo |

Todas exigem token `gerente` ou `ia`. A operação vem do usuário autenticado, nunca do payload. O modelo não recebe conexão ao banco, credenciais, nomes de usuários ou pagamentos individuais. Recebe nomes dos insumos e agregados operacionais da barraca, além da pergunta.

## Contexto e cálculos

- Uma transação PostgreSQL `REPEATABLE READ READ ONLY` garante leitura consistente, sem alterar tabelas.
- O período vai de hoje menos N dias até o início de hoje, no fuso configurado. O dia corrente é excluído; o estoque, por sua vez, é a fotografia atual.
- Receita exclui vendas estornadas. Custo de ingredientes inclui o que já foi consumido, mesmo se a venda foi estornada.
- Margem de ingredientes = receita − custo consumido. Perdas independentes aparecem separadamente. Nenhum desses valores é lucro líquido.
- Necessidade teórica (não recomendação de compra) = máximo entre zero e (consumo médio × cobertura + mínimo − saldo utilizável). Python usa `Decimal`; quantidades teóricas são arredondadas para cima em 3 casas.
- A média só é calculada se houver registros de consumo; sem histórico, retorna `null`. Dentro de uma janela com registros, dias sem consumo entram como zero, sem distinguir fechamento de demanda zero. Calendário, eventos, prazo do fornecedor, embalagens e validade futura precisam de evolução.
- O contexto contém até 100 insumos, em ordem de nome/ID. Quando há mais, `insumos_truncados=true`; os totais financeiros continuam sendo de toda a barraca. Não tratar a lista truncada como inventário completo.

## Comportamento do provedor

`app/ai.py` concentra consultas, cálculos e adaptador HTTP; o prompt do Otto está em `app/prompts/otto.txt`. O endpoint externo é fixo (`https://api.anthropic.com/v1/messages`), sem redirecionamentos. A chave fica somente no cabeçalho enviado pelo backend. Sem ferramentas de execução, sem SQL gerado e sem histórico persistido de conversa. Cada pergunta é independente. As respostas são texto não confiável: uma futura tela deve escapar conteúdo e nunca inserir HTML bruto retornado pelo modelo.

A chamada tem 5 segundos para conectar, 30 segundos de timeout de leitura e limite de 1.200 tokens de saída. Não há repetição automática em falha. Perguntas têm até 2.000 caracteres; histórico de 1–90 dias; cobertura de 1–30 dias. Antes de compartilhar em produção, estabelecer quotas e limites de requisição por usuário no gateway: esta versão ainda não aplica limite diário de chamadas.

## Erros

| HTTP | Código | Significado |
|---|---|---|
| 503 | IA_NAO_CONFIGURADA | Chave ausente; nenhum pedido externo é feito |
| 503 | IA_CREDENCIAL_RECUSADA | Provedor recusou a credencial/permissão |
| 503 | IA_LIMITE_DO_PROVEDOR | Provedor respondeu 429 |
| 504 | IA_TEMPO_ESGOTADO | Timeout da chamada |
| 502 | IA_INDISPONIVEL | Falha de rede ou resposta de erro do provedor |
| 502 | IA_RESPOSTA_INCOMPLETA / INVALIDA / VAZIA | Resultado sem texto completo válido |
| 422 | CONTEXTO_IA_MUITO_GRANDE | Contexto excede o limite definido |

Erros externos são sanitizados: a API não devolve corpo bruto do provedor, cabeçalhos ou chave. Não há resposta inventada quando o modelo falha. O acesso de leitura é garantido pela ausência de ferramentas de escrita, além das permissões da API; não depende apenas do prompt.

Referência usada: [Messages API — documentação oficial Anthropic](https://platform.claude.com/docs/en/api/messages/create).

## Dados reais e cadastros pendentes

`estado_dados`, `cadastros`, `sem_vendas_no_periodo` e `pendencias` distinguem tabelas sem registros de totais matematicamente iguais a zero. Insumos incluem número de lotes e registros de consumo. Produtos e composição das fichas vêm das tabelas `produtos` e `ingredientes`, nunca das receitas do documento de referência.

`compra_sugerida` permanece `null` enquanto não houver os parâmetros completos de reposição. `necessidade_teorica` é apenas uma conta de cobertura, quando há histórico, e não autoriza recomendação final. `pendencias_compra` lista informações ainda necessárias.

O texto completo fornecido pelo usuário está em `OTTO_REQUISITOS.md`, com o nome atualizado para Otto. Ele descreve também módulos futuros: custos adicionais, fatores de correção e restrições do fornecedor ainda precisam de estrutura própria. Otto deve declarar essas limitações; não simular registros nem afirmar que executou alterações. Nenhuma receita do documento foi cadastrada automaticamente.

Atualização: perdas por receita e total implementadas, com migration 002 e integração de agrupamentos no contexto do Otto. Leia `PERDAS.md` para distinguir descarte físico ainda não baixado de consumo já registrado em venda.

O contexto inclui `operacao` com premissas, vendas por dia, ranking de porções e preferência do relatório dominical. Veja [base okto](DEMONSTRACAO_OKTO.md).


## Alertas de reposição e propostas cadastradas

O Otto recebe `reposicao`, com a meta de 50 porções de cada sabor, fichas pendentes,
alertas por ingrediente e a melhor proposta calculada pelo servidor. O histórico
de consumo continua separado da meta de estoque; os dois valores não são somados.
O módulo determinístico grava alertas internos sem chamar o provedor. A IA continua
somente em leitura: não cria compras nem modifica saldos. Veja
[regra, cadastro e limitações](REPOSICAO_FORNECEDORES.md).
