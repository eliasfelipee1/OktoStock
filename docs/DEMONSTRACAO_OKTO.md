# Base okto — demonstração de outubro de 2026

Dados simulados, criados a pedido do dono. Não representam vendas reais nem números oficiais da festa.

## Conteúdo

- Período histórico: 07 a 20/10/2026; estoque de abertura em 21/10/2026.
- 5 sabores e 29 linhas de ficha técnica do catálogo didático Grupo01.
- 15 insumos; conversão explícita de kg para g e l para ml, inclusive nos custos unitários.
- 1.600 vendas, 3.200 porções, 1.600 pagamentos, 14 turnos fechados, 225 lotes e 210 perdas.
- Receita bruta: R$ 111.040; quinta a domingo: R$ 83.280 (75%). Não é lucro.
- Fim de semana de 9–11/10 tem mais movimento que 16–18/10; 12/10 também tem reforço em relação à segunda seguinte.
- Cada lote concilia entrada, venda, perda e saldo. Perdas representam descarte independente de insumos não vendidos; não são baixadas de novo por receita.

Os volumes e o mix fixo de sabores são hipóteses didáticas escolhidas para materializar as regras. A simulação não serve para medir preferência real por sabores. O script original de massa histórica não foi executado: ele apaga tabelas e usa uma estrutura diferente da API. Seu catálogo foi preservado em `scripts/data/catalogo_grupo01.json`. O schema usado pela API é `public`.

## Premissas do dono

Público total da festa: 500 mil, sem inferência automática sobre clientes da barraca. Dias fortes: quinta, sexta, sábado e domingo. O fim de semana associado a 12 de outubro merece reforço. Pré-preparos devem terminar até quarta à noite. Falta definir horário, capacidade e conservação por preparo; esse prazo não garante validade de alimentos até domingo. A transformação física em lotes pré-assados continua pendente.

O contexto JSON separa as premissas dos agregados medidos. A janela padrão da IA passou a 14 dias. Outros períodos podem apresentar participação diferente de 75%. Recebimentos, validades e custos deste conjunto são simulados; não são parâmetros sanitários validados. Nenhum visitante fictício foi registrado como cliente.

## Uso

O `.env` local contém `DATABASE_URL` e `OKTO_DEMO_TOKEN`. A chave Anthropic é distinta do token de usuário. Não compartilhe o `.env` nem o inclua em commits.

Abra `/painel/agente.html`, cole o valor de `OKTO_DEMO_TOKEN` no campo de token e clique em Conectar operação. O token fica apenas na memória da página, sem localStorage. A tela consulta dados reais da base simulada. Visão geral, estoque, vendas, receitas, perdas e planejamento agora consultam a API. A demonstração local de leitura é habilitada por LOCAL_DEMO_OPERATION_ID no .env, apenas para a operação marcada como simulada, com conexão e origem locais. Não expõe tokens nem permite alterações. Fora desse modo, o painel exige token de gerente/IA e o mantém apenas na sessão da aba.

O dono pode responder à pergunta sobre relatórios aos domingos à noite. O aceite/recusa é persistido por operação em `PUT /ia/preferencias/relatorio-semanal` (gerente), com `{"deseja_receber": true}` ou `false`. Após a resposta, a interface não repete a pergunta. Não há agendamento automático: horário, canal e serviço de envio continuam pendentes. A resposta em texto livre no chat não salva essa preferência; use os botões.

## Reproduzir em um banco vazio dedicado

Configure a conexão e um token aleatório local, depois execute:

```sh
python -m scripts.migrate
python -m scripts.seed_okto
```

A carga é transacional e usa um ID fixo. Nova execução reconhece a carga existente sem duplicar ou apagar registros; não atualiza uma carga anterior. Em banco com outras operações, recusa a carga. Não há TRUNCATE. O banco `okto_test` é separado e utilizado exclusivamente pelos testes.

Perguntas sugeridas: “Quais sabores mais venderam?”, “Qual a participação de quinta a domingo?”, “Como o feriado de 12 de outubro aparece no histórico?” e “O que falta para planejar os pré-preparos até quarta à noite?”.

## Encontrar os registros no pgAdmin

Abra PostgreSQL 18 → Databases → okto → Schemas → public → Tables. As fichas estão em produtos e ingredientes; as vendas em vendas e venda_itens. Clique com o botão direito na tabela e escolha View/Edit Data. Expandir Columns mostra apenas a estrutura. Atualize a árvore com Refresh.
