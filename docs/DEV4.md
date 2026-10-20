# DEV4 — dashboard, previsão e recomendações

Seu papel é transformar os dados da API em informação para o gerente. DEV1 mantém saldo, custo e regras transacionais. DEV4 não deve alterar saldo, criar vendas ou comprar automaticamente.

## Etapa 1: integração

Peça ao DEV1 a URL da API e um token com papel `ia`, da barraca correta. Use o token no servidor do dashboard; não incorpore uma credencial compartilhada no JavaScript público. Para um dashboard de usuário final, alinhe a autenticação individual com DEV1.

Comece consumindo os relatórios e exibindo estados de carregamento, sem dados e erro. O contrato detalhado está em `API.md` e no Swagger.

| Dado/indicador | Endpoint | Regra |
|---|---|---|
| Estoque disponível e mínimo | /relatorios/estoque | Saldo utilizável exclui vencidos |
| Lotes próximos de vencer | /estoque/lotes | Filtrar saldo > 0 e horizonte configurável |
| Porções possíveis | /disponibilidade | Limite por ingrediente; produtos compartilham estoque |
| Receita | /relatorios/vendas | Somar total apenas com status confirmada |
| Custo consumido | /relatorios/vendas | Incluir custos de confirmadas e estornadas se alimento foi consumido |
| Margem sobre ingredientes | /relatorios/vendas | Soma de margem_ingredientes; estornos têm receita zero e custo preservado |
| Produtos mais vendidos | /relatorios/produtos | Quantidades por produto/dia, sem estornadas |
| Consumo e perdas | /relatorios/consumo | Separar tipo venda de perda; perdas por motivo |

O campo `total` do relatório de vendas em linhas estornadas é o valor original para auditoria, não receita atual. A margem não desconta perdas independentes, taxas, embalagem, mão de obra, aluguel etc. Se exibir um indicador após perdas, subtraia o custo de tipo `perda` uma única vez e nomeie claramente. Não chame margem de lucro líquido.

## Etapa 2: entregar o dashboard

Monte cartões de receita, custo de ingredientes, margem e perdas; ranking por sabor; evolução por hora/dia; tabela de estoque abaixo do mínimo e lotes próximos da validade. Use o fuso America/Sao_Paulo. Explique unidades (g/ml/un) e período. Filtros de período são locais nesta base; solicite filtros no servidor antes de grande volume.

Critérios de aceite:

- Totais conciliam com uma venda de teste e suas movimentações.
- Um estorno não aumenta estoque nem conta como receita.
- Período sem vendas mostra zero, sem divisão por zero.
- Token de IA não consegue efetuar POST de venda ou recebimento.
- Dados de outra barraca não aparecem.

## Etapa 3: previsão inicial sem IA generativa

Há um ponto de partida em `scripts/dev4_compras.py`:

```sh
export API_TOKEN='TOKEN_IA'
python -m scripts.dev4_compras --data 2026-10-20 --historico 7 --cobertura 3
```

Use a data atual da barraca. O script calcula média de consumo de vendas em dias completos, incluindo dias sem consumo como zero, e sugere `max(0, média × dias de cobertura + estoque mínimo − saldo utilizável)`. Só consulta a API e imprime JSON; não grava compras.

Este método é uma referência simples, não uma previsão validada. Ele assume histórico completo e dias comparáveis. Não distingue barraca fechada de demanda zero, não projeta vencimento futuro, não calcula múltiplos de embalagem ou prazo do fornecedor e não considera o estoque na data histórica informada — o saldo consultado é sempre atual.

Sua tarefa é evoluir isso: calendário de abertura, feriados/eventos, prazo de reposição, validade durante o horizonte, lote mínimo do fornecedor, dias suficientes de histórico e incerteza. Compare a previsão com uma média simples em janelas temporais separadas (sem usar o futuro para prever o passado). Meça erro absoluto em unidades e impacto de falta/sobra; não prometa precisão sem validação.

## Etapa 4: assistente opcional

Depois que os indicadores estiverem corretos, um modelo de linguagem pode explicar os números e responder perguntas sobre eles. Envie somente agregados necessários, mantenha cálculos em Python/SQL, cite período/dados usados e não dê acesso de escrita nem SQL livre ao modelo. Chaves de provedores ficam no backend do DEV4.

Entregáveis: dashboard funcional, definição dos indicadores, módulo de previsão testado, relatório de comparação com a baseline e documentação de como executar. A escolha da biblioteca de dashboard/IA pode ser feita com a equipe; nenhuma integração externa é necessária para iniciar.

## Estrutura já preparada nesta entrega

O backend do assistente está em `app/ai.py`, com leitura por operação, agregados, sugestão determinística de compra, prompt consultivo, chamada à Responses API e tratamento de falhas. A configuração fica em `.env`; instruções em `IA.md`. O frontend visual está em `frontend/agente.html`, sem envio de mensagens nesta etapa. Sua próxima entrega é integrar a experiência autenticada e avaliar a qualidade das respostas e previsões com dados reais.

Atualização: o assistente chama-se **Otto**. O frontend não usa mais valores demonstrativos. No contexto do agente, médias sem histórico são nulas e compras finais ficam pendentes dos parâmetros de demanda, validade, perdas, armazenamento e fornecedor; o script de baseline é apenas uma referência de cálculo, não uma recomendação aprovada. Consulte `OTTO_REQUISITOS.md` e `IA.md`.
