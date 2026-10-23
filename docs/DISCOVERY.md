# Discovery: administrador da barraca de batata recheada

Respostas às duas primeiras perguntas do discovery. Os IDs do OktoberVerse (`PG-`, `RD-`, `KT-`) vêm dos dados do sábado. Os números da barraca vêm da base de demonstração "okto" (`docs/DEMONSTRACAO_OKTO.md`), criada pelo time a pedido do dono e **simulada**: não representa vendas reais. O pacote `grupo01`, usado em uma versão anterior deste documento, foi descartado pelo time. Todos os números abaixo foram calculados no banco `okto` (consultas no final).

## 1. Quem vocês querem ajudar? Por que essa pessoa?

**O administrador (gerente) da barraca de batata recheada**, que vende 4 sabores: Linguiça Blumenau, Strogonoff de frango, Bolonhesa e Vegetariana.

**Por quê:** a barraca é uma mini-operação de food service (compra, recebimento, estocagem, pré-preparo, montagem e venda, sobras e perdas). O administrador é quem decide quanto pré-preparar e quando repor. Cada erro dele vira falta (fila e venda perdida) ou sobra (ingrediente perecível jogado fora).

**O que mostra isso nos dados da barraca:**
- A operação tem 30 insumos, 4 fichas técnicas, 14 turnos e 1.280 vendas (3.200 porções), de 07/10 a 20/10.
- Foram registrados 420 movimentos de perda, que somam **R$ 322,66**. Os maiores: batata inglesa, R$ 83,52 (cerca de 26%); muçarela ralada, R$ 58,24 (cerca de 18%); linguiça Blumenau sem pele, R$ 41,47 (cerca de 13%).

**Suposição a testar:** "só o administrador precisa ter essa visão". O modelo da barraca tem outros papéis (caixa, estoquista), que também usam parte dessa informação.

## 2. Qual acontecimento chamou a atenção? Que trabalho ele não consegue fazer bem?

**Acontecimento: o desfile das 16h.**
- `PG-04`: desfile oficial às 16:00 na Rua XV, confirmado.
- `RD-09` (15:55): Portão B com fila grande, "pessoal vindo do desfile". Cuidado: o relato é das 15:55, antes do início do desfile às 16:00, então ele sozinho não prova que o desfile causou a fila.
- `KT-14` a `KT-17` (16h) comparados com `KT-09` a `KT-12` (12h): a distribuição do consumo por pavilhão muda. Isso não prova que o total aumentou nem que a demanda da barraca aumentou.

**Trabalho que o administrador não consegue fazer bem nesse momento:** decidir quanto batata pré-assar e quanto recheio preparar para o turno, e quando repor, sem saber onde o público vai estar. O pico chega sem aviso, e a informação de que ele precisa está em lugares separados: saldo por insumo, o que já está pré-preparado e a estimativa de público.

**Por que a demanda é difícil de prever, nos dados da barraca (vendas por dia):**

| Dia | Vendas | | Dia | Vendas |
|---|---|---|---|---|
| 07/10 (qua) | 40 | | 14/10 (qua) | 40 |
| 08/10 (qui) | 72 | | 15/10 (qui) | 64 |
| 09/10 (sex) | 144 | | 16/10 (sex) | 96 |
| 10/10 (sáb) | 176 | | 17/10 (sáb) | 128 |
| 11/10 (dom) | 160 | | 18/10 (dom) | 120 |
| 12/10 (seg) | 72 | | 19/10 (seg) | 64 |
| 13/10 (ter) | 48 | | 20/10 (ter) | 56 |

- A mesma barraca vendeu de 40 a 176 porções por dia, **4,4 vezes mais** no dia de pico do que no dia mais fraco.
- Quinta a domingo concentram 960 das 1.280 vendas (75%), em linha com a premissa do dono de que esses são os dias fortes.
- O fim de semana de 09 a 11/10 vendeu 480 porções, e o de 16 a 18/10 vendeu 344 (28% a menos; ou, visto ao contrário, o primeiro vendeu cerca de 40% a mais).
- A segunda-feira 12/10 (feriado, 72 vendas) vendeu mais que a segunda seguinte, 19/10 (64 vendas), o que combina com a premissa do dono de que esse fim de semana merece reforço.

Ou seja, existe um padrão por dia da semana, mas a amplitude entre os dias é grande, e o administrador precisa decidir o pré-assamento antes de ver o movimento do dia.

## O que ainda precisamos descobrir

- **Pré-preparo:** as tabelas de pronta entrega (`lotes_prontos`, `movimentos_prontos`) existem, mas estão vazias na carga básica da base okto, então ainda não dá medir sobra de batata pré-assada. O próprio `DEMONSTRACAO_OKTO.md` diz que a transformação física em lotes pré-assados continua pendente.
- **Perdas:** os 420 movimentos têm todos o mesmo motivo ("Demonstração simulada"). Não dá para dizer o que causou cada perda, nem distinguir queima, validade ou sobra. Motivo registrado não comprova causa raiz.
- **Público:** a base não traz visitantes por dia. A premissa do dono é de 500 mil pessoas na festa inteira, sem inferência sobre os clientes da barraca. Não transformar público em vendas sem uma taxa de conversão observada.
- **Ligação com o OktoberVerse:** a base da barraca (07/10 a 20/10) e os dados do sábado do OktoberVerse são cenários diferentes. A relação entre o desfile das 16h e a barraca é conceitual, não está nos mesmos registros.
- **Dados simulados:** os volumes e o mix de sabores são hipóteses didáticas e não servem para medir preferência real por sabores.

## Consultas para conferir os números (DBeaver, banco `okto`, schema `public`)

```sql
-- Vendas por dia
SELECT criado_em::date AS dia, to_char(criado_em, 'Dy') AS dia_semana, count(*) AS vendas
FROM vendas GROUP BY 1, 2 ORDER BY 1;

-- Total de perdas (movimentos) e custo
SELECT count(*) AS movimentos, round(sum(-quantidade * custo_unitario), 2) AS custo_total
FROM movimentacoes WHERE tipo = 'perda';

-- Perdas por insumo
SELECT i.nome, round(sum(-m.quantidade * m.custo_unitario), 2) AS custo
FROM movimentacoes m JOIN lotes l ON l.id = m.lote_id JOIN insumos i ON i.id = l.insumo_id
WHERE m.tipo = 'perda' GROUP BY 1 ORDER BY 2 DESC;
```
