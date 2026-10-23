# Quatro sabores e reposição automática

Cardápio atual: Linguiça Blumenau, Strogonoff de frango, Bolonhesa e Vegetariana.
O responsável fornecerá as receitas e cotações reais. Nenhuma quantidade, fornecedor,
cotação ou venda real foi presumida. As quatro fichas começam como rascunhos inativos.

## Cadastro

1. Em **Fornecedores e compras**, cadastre os insumos nas unidades g, ml ou un.
2. Em **Fichas técnicas**, informe ingredientes por **uma porção**, preparo e preço.
   Uma receita para várias porções deve ser dividida pelo rendimento informado.
   Salve como rascunho ou valide para ativar. Uma ficha ativa/usada não é reescrita:
   revisões devem usar uma nova versão, preservando custos e fichas das vendas anteriores.
3. Em **Estoque**, registre os lotes realmente recebidos, validade, quantidade e custo
   por unidade-base. Esse custo é diferente do preço por embalagem da cotação.
4. Cadastre pelo menos três fornecedores reais e suas cotações. Informe tamanho da
   embalagem na unidade-base, preço, mínimo de embalagens, frete, prazo e validade.
   Frete ou prazo desconhecidos ficam pendentes, não são tratados como zero.

## Regra de mínimo

A meta é **50 porções de cada sabor simultaneamente**. Para cada insumo:

`mínimo conjunto = soma(quantidade por porção × 50) em todas as fichas ativas`

`necessidade de reposição = máximo(0, mínimo conjunto − saldo utilizável)`

Lotes vencidos não entram no saldo utilizável. Saldo igual à meta não dispara aviso.
A disponibilidade individual de cada sabor não pode ser somada quando há ingredientes
compartilhados. Fichas pendentes são mostradas explicitamente: não equivalem a estoque suficiente.
A meta não é previsão de demanda nem uma autorização de compra. A versão atual ainda
não registra transformação de matéria-prima em pré-assados; não faça dupla baixa.

## Mensagens automáticas

Triggers PostgreSQL recalculam alertas na mesma transação dos lotes, fichas, produtos e
configuração. O aviso só fica visível depois do commit. Existe no máximo um alerta aberto
por operação/insumo; novas leituras não geram mensagens duplicadas. A reposição encerra
esse alerta. Uma nova falta abre outro, preservando o histórico em `alertas_reposicao`.

O processo da API reavalia a cada 15 segundos para detectar vencimentos sem movimentação.
Os painéis recebem SSE e têm consulta de contingência a cada 15 segundos. A detecção de
movimentos é imediata no banco; o navegador atualiza após o evento. Não há estimativa de
consumo não registrado. Mantenha API e PostgreSQL ligados para monitoramento contínuo.
Os alertas não dependem da Anthropic e não consomem chamadas de IA. O chat do Otto recebe
o contexto desses alertas e das melhores propostas. Não há envio para WhatsApp/e-mail.

## Comparativo

Arredonda embalagens para cima, respeita o pedido mínimo e soma o frete por insumo.
O vencedor tem o menor total entregue entre propostas ativas, completas e dentro da
validade. Empates usam menor prazo e ID estável. Cotações reais têm prioridade sobre
simuladas, e simulações são identificadas. Uma nova cotação do mesmo fornecedor/insumo
inativa a anterior e conserva seu histórico. Inativar fornecedor o exclui do ranking.

Não é pesquisa de preços de mercado, reserva de estoque no fornecedor nem otimização
conjunta de frete. Confirmar disponibilidade, prazo, conservação e capacidade antes de comprar.

## API e isolamento

- `GET /reposicao`: gerente, estoquista ou IA da própria operação.
- `POST /fornecedores`, `PUT /fornecedores/{id}`, `POST /cotacoes`: gerente.
- `PUT /fichas/{id}`: cadastro de rascunho pelo gerente; valida ingredientes da mesma operação.
- Rotas `/demo/...` atendem o painel local. Escritas exigem loopback, JSON e origem
  compatível, mesmo se `DEMO_ACESSO_REMOTO` estiver ligado. A operação com cadastros reais
  locais nunca é liberada remotamente por essa opção. As alterações são auditadas.

Migration: `005_fornecedores_reposicao.sql`. Não altera migrations antigas.
`python -m scripts.prepare_four_flavors` cria uma operação local separada, com fichas
pendentes, e atualiza `.env` sem imprimir credenciais. O histórico simulado dos cinco
sabores permanece na operação anterior. O comando é idempotente e não apaga cadastros reais.

## Verificação

`python -m pytest -q` usa schemas isolados em `TEST_DATABASE_URL`.
Os testes cobrem mínimo compartilhado, limite exato, vencimento, resolução/reabertura,
custo entregue, propostas incompletas, validade, substituição de cotação, permissões,
isolamento e imutabilidade de ficha ativada. Testes não enviam mensagens externas.

## Atualização de 22/10/2026 — regra vigente

A regra de 50 porções acima foi substituída, na operação atual, por **pronta entrega**:
segunda a quarta, meta 250 por sabor e alerta <75; quinta a domingo, meta 1.000 e alerta
<300. A contagem é por produto pronto, não por capacidade teórica dos ingredientes.
`006_pronta_entrega.sql` mantém os registros antigos e adiciona lotes, movimentos e alertas
prontos. O controle antigo permanece somente como compatibilidade para outras operações.

A tela Produção registra contagem inicial física (inclusive zero), produção com baixa FEFO
dos ingredientes e descarte de lotes prontos. Os endpoints `/prontos/entradas` e
`/prontos/perdas` são idempotentes. Para produtos com controle pronto, `/vendas` baixa
somente o lote pronto e preserva seu custo. `/disponibilidade` retorna as porções prontas.
Lotes vencidos são excluídos da disponibilidade; o monitor verifica vencimentos a cada 15s.

As receitas foram importadas de `docs/OTTO_REQUISITOS.md`, conforme confirmação do usuário.
Os preços didáticos de venda/custo do catálogo não foram convertidos em preços reais.
A foto é referência e não comprova a composição exata da ficha. Os modos de preparo são
resumos propostos para revisão da cozinha; não estabelecem tempos de conservação.

Três redes reais presentes em Blumenau estão cadastradas: Bistek, Angeloni e Atacadão.
Os valores públicos e suas fontes estão em `scripts/data/fornecedores_blumenau.json`.
São referências online, com confirmação por loja/CEP ainda pendente; não são propostas
locais aprovadas. Não inventamos frete, prazo, mínimo comercial ou validade. O comparativo
não elege essas referências como menor custo entregue enquanto tais condições faltarem.

Banco verificado pela conexão da aplicação: `okto`, PostgreSQL em `localhost:5432`.
O servidor `PostgreSQL 18` cadastrado no pgAdmin aponta para o mesmo host/porta. A base
`postgres` no cadastro do pgAdmin é apenas o banco de manutenção da conexão; a aplicação
usa `okto`. Segredos ficam exclusivamente no `.env` local.
