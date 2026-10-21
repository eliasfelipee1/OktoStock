# Perdas por receita e total

## Preparar o banco

Configure o `.env` com seu PostgreSQL e execute:

```sh
python -m scripts.migrate
```

A migration `002_perdas_receitas.sql` adiciona registros de perdas e vínculo nas movimentações, sem alterar migrations anteriores. Perdas antigas continuam no total, classificadas como **Sem receita vinculada**. Não há atribuição retroativa automática a sabores.

## 1. Perda de um ingrediente/lote

`POST /estoque/perdas` — gerente ou estoquista.

```json
{
  "lote_id": "UUID_DO_LOTE",
  "quantidade": "100",
  "motivo": "Sobra de recheio",
  "produto_id": "UUID_DA_RECEITA",
  "turno_id": "UUID_DO_TURNO",
  "idempotency_key": "UUID_UNICO_DESTA_PERDA"
}
```

`produto_id`, `turno_id` e `idempotency_key` são opcionais para manter compatibilidade com clientes antigos. Use sempre a chave em integrações novas. O ingrediente do lote deve fazer parte da receita informada. Tudo precisa pertencer à operação autenticada. Lotes vencidos podem ser descartados por esta rota.

O custo é quantidade × custo unitário histórico do lote. O registro guarda motivo, responsável, instante, turno opcional, nome e versão da receita. `saldo` na resposta é o saldo atual do lote, inclusive em reenvios.

## 2. Perda de porções completas

`POST /estoque/perdas/receita` — gerente ou estoquista.

```json
{
  "produto_id": "UUID_DA_RECEITA",
  "porcoes": "2",
  "motivo": "Batatas queimadas no preparo",
  "turno_id": "UUID_DO_TURNO",
  "idempotency_key": "UUID_UNICO_DESTA_PERDA"
}
```

A API multiplica a composição da ficha pelas porções e baixa ingredientes pelo FEFO, entre lotes não vencidos. Cada consumo preserva quantidade e custo. Se faltar qualquer ingrediente, nada é gravado. Uma porção fracionada só é aceita se o consumo de cada ingrediente puder ser representado nas três casas decimais do estoque.

Use esta rota somente quando esses ingredientes **ainda não foram baixados**: não existe reserva ou módulo de produção. A seleção dos lotes segue FEFO no instante do registro; para descarte de um lote físico específico, use a rota de ingrediente. Nunca registre novamente como perda os ingredientes já baixados em uma venda ou produção. Esta versão não reclassifica consumos de vendas como perda e não duplica seu custo; tal fluxo exige um módulo separado. O estorno financeiro continua preservando o consumo já ocorrido.

Não registre uma perda completa e depois os mesmos ingredientes individualmente. A idempotência impede repetir a mesma requisição com a mesma chave, mas não identifica dois relatos semanticamente iguais usando chaves diferentes.

## 3. Relatório

`GET /relatorios/perdas?inicio=2026-10-01&fim=2026-10-20&turno_id=UUID_OPCIONAL`

Acesso: gerente, estoquista e IA. Datas inicial e final são inclusivas, no fuso da aplicação. Sem datas, usa o dia atual. Limite de 366 dias. Se filtrar por turno, perdas sem turno (inclusive registros legados) não entram nesse recorte.

Retorna:

- `custo_total_perdas`: custo monetário de todas as movimentações de perda do recorte.
- `porcoes_perdidas_registradas`: porções explicitamente registradas; não converte perdas de insumos em porções.
- `quantidades_por_unidade`: g, ml e un separados; nunca soma grandezas incompatíveis.
- `por_receita`: ID, nome/versão preservados, custo, porções e quantidades por unidade. Ordenado por maior custo, incluindo grupo sem receita.
- `por_insumo`: quantidade, unidade e custo por ingrediente; ordenado por maior custo.
- `por_motivo`: custo por motivo registrado, sem inferir causas.
- `registros`: movimentos individuais, com data, lote, responsável e vínculo da perda.
- `percentual_sobre_faturamento_bruto`: perdas ÷ valor original das vendas no período (inclui estornadas) × 100.
- `percentual_sobre_receita_confirmada`: perdas ÷ vendas confirmadas × 100.
- `percentual_sobre_custo_ingredientes_vendidos`: perdas ÷ custo consumido das vendas, incluindo estornadas × 100; não é CMV completo com despesas adicionais.

Denominador zero gera `null`, não zero nem infinito. `sem_registros` identifica ausência de perdas no recorte; isso não garante que todas as perdas físicas foram cadastradas.

O relatório usa valores históricos das movimentações. Mudança posterior no custo do lote não altera perdas antigas. Quantidades não são somadas novamente pelo número de lotes: porções são contadas uma vez por registro.

## Tela e Otto

`frontend/perdas.html` contém os cartões de total, percentual e porções, além das tabelas por receita, ingrediente e histórico. O menu de todas as páginas oferece **Perdas**. Como o restante do frontend HTML/CSS, a tela ainda aguarda integração com dados reais; não realiza cadastro nem consulta automática. Use o Swagger para registrar e consultar perdas agora.

Otto recebe os totais e agrupamentos reais do mesmo relatório no intervalo do seu contexto, sem a lista individual de movimentos/responsáveis. Pode explicar perdas por sabor e total; não presume causa nem inventa registros.
