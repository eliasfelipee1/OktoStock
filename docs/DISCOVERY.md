# Discovery: administrador da barraca de batata recheada

Respostas às duas primeiras perguntas do discovery. Os IDs citados vêm dos dados do sábado (`PG-`, `RD-`, `KT-`) e do pacote da barraca (schema `grupo01`). Os números marcados com (*) foram contados lendo os arquivos e precisam ser conferidos com as consultas do final.

## 1. Quem vocês querem ajudar? Por que essa pessoa?

**O administrador (gerente) da barraca de batata recheada**, que vende 5 sabores: calabresa, frango, bacon com cheddar, carne seca e vegetariano.

**Por quê:** a barraca é uma mini-operação de food service (compra, recebimento, estocagem, pré-preparo, montagem e venda, sobras e perdas). O administrador é quem decide quanto pré-preparar e quando repor. Cada erro dele vira falta (fila e venda perdida) ou sobra (ingrediente perecível jogado fora).

**O que mostra isso nos dados:**
- A barraca registra produção e sobra por turno e sabor (`producao`, ids 1 a 5, 11 a 15, 21 a 25 e 31 a 35).
- Em 4 dias a barraca registrou 4 perdas (`perdas`, ids 1 a 4), que somam R$ 266,10 (*): batata queimada, 13 kg (id 1); perda no preparo de bacon, 2,3 kg (id 2); sobra de frango no fim do turno, 3,1 kg (id 3); brócolis vencido, 1,2 kg (id 4).

**Suposição a testar:** "só o administrador precisa ter essa visão". O próprio modelo da barraca tem outros papéis (caixa, estoquista), e eles também usam parte dessa informação.

## 2. Qual acontecimento chamou a atenção? Que trabalho ele não consegue fazer bem?

**Acontecimento: o desfile das 16h.**
- `PG-04`: desfile oficial às 16:00 na Rua XV, confirmado.
- `RD-09` (15:55): Portão B com fila grande, "pessoal vindo do desfile". Cuidado: o relato é das 15:55, antes do início do desfile às 16:00, então ele sozinho não prova que o desfile causou a fila.
- `KT-14` a `KT-17` (16h) comparados com `KT-09` a `KT-12` (12h): a distribuição do consumo por pavilhão muda. Isso não prova que o total aumentou nem que a demanda da barraca aumentou.

**Trabalho que o administrador não consegue fazer bem nesse momento:** decidir quanto batata pré-assar e quanto recheio preparar para o turno, e quando repor, sem saber onde o público vai estar. O pico chega sem aviso, e a informação de que ele precisa está em lugares separados: saldo por insumo, o que já está pré-preparado e a estimativa de público.

**Por que a demanda é difícil de prever, nos dados da barraca:**

| Dia | Turnos | Vendas no dia (*) | Visitantes do evento | Clima |
|---|---|---|---|---|
| 08/10 | 3 e 4 | 150 | 30.199 | chuva |
| 15/10 | 17 e 18 | 150 | 32.066 | chuva |
| 11/10 | 9 e 10 | 351 | 62.965 | sol |

A mesma barraca vendeu de 150 a 351 unidades por dia no período (*), mais que o dobro. E os visitantes do evento não explicam sozinhos as vendas: em 12/10 (turnos 11 e 12) foram 177 vendas com 26.598 visitantes, e em 17/10 (turnos 21 e 22) foram 287 com 60.983.

**Produção contra vendas (os dias com produção registrada):**

| Dia | Produzido (*) | Sobra registrada (*) | Vendas no dia (*) | Sem explicação |
|---|---|---|---|---|
| 17/10 (turno 21) | 326 | 5 | 287 | 34 |
| 18/10 (turno 23) | 357 | 9 | 327 | 21 |
| 19/10 (turno 25) | 240 | 7 | 203 | 30 |
| 20/10 (turno 27) | 233 | 5 | 200 | 28 |

"Sem explicação" é produzido, menos sobra, menos vendas. Em todos os quatro dias sobram de 21 a 34 unidades (cerca de 10%) que nem foram vendidas nem registradas como sobra ou perda. Esse é um ponto concreto do trabalho do administrador: ele não consegue fechar a conta entre o que produziu e o que aconteceu.

## O que ainda precisamos descobrir

- A produção está registrada só no turno da manhã (turnos 21, 23, 25 e 27). Ela cobre o dia inteiro ou só a manhã? Se fosse só a manhã, as 326 unidades de 17/10 não bateriam com as 119 vendas da manhã (*). Perguntar a quem montou o pacote.
- Os dados da barraca (07/10 a 20/10, de 26.598 a 62.965 visitantes) e os do OktoberVerse (82 mil visitantes) são cenários diferentes. A ligação entre o desfile das 16h e a barraca é conceitual, não está nos mesmos registros.
- Os `visitantes_evento` são do evento inteiro, não dos compradores da barraca. O crescimento de 22% das consultas é um cenário de teste, não uma previsão validada.
- O consumo histórico está agregado por dia, e os lotes são didáticos. O saldo consolidado é a referência.

## Consultas para conferir os números (DBeaver, schema `grupo01`)

```sql
-- Vendas por dia
SELECT v.instante::date AS dia, count(*) AS vendas
FROM grupo01.vendas v GROUP BY 1 ORDER BY 1;

-- Produção, sobra e vendas dos dias com produção
SELECT t.data, sum(p.quantidade_preparada) AS produzido, sum(p.sobra) AS sobra,
       (SELECT count(*) FROM grupo01.vendas v WHERE v.instante::date = t.data) AS vendas
FROM grupo01.producao p JOIN grupo01.turnos t ON t.id = p.turno_id
GROUP BY t.data ORDER BY t.data;

-- Custo das perdas
SELECT sum(p.quantidade * i.custo_unitario) AS custo_total
FROM grupo01.perdas p JOIN grupo01.insumos i ON i.id = p.insumo_id;
```
