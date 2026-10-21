# Contrato da API

Base local: `http://127.0.0.1:8000`. Contrato completo gerado em `/docs` e `/openapi.json`. Cabeçalho: `Authorization: Bearer TOKEN_INDIVIDUAL`. UUIDs são strings. Não enviar `operacao_id` ou papel: ambos vêm da autenticação.

| Método/rota | Papel | Finalidade |
|---|---|---|
| GET /health | público | Verifica API e banco |
| GET /insumos, /produtos, /disponibilidade | todos autenticados | Cadastros e porções possíveis |
| POST /insumos | gerente, estoquista | Criar insumo |
| POST /produtos | gerente | Criar produto e ficha imutável |
| POST /produtos/{id}/desativar | gerente | Tirar do cardápio |
| POST /estoque/recebimentos | gerente, estoquista | Entrada por lote |
| GET /estoque/lotes | gerente, estoquista, ia | Saldos e validades |
| POST /estoque/perdas | gerente, estoquista | Baixa justificada |
| POST /turnos | gerente, caixa | Abrir turno próprio |
| POST /turnos/{id}/fechar | gerente, caixa proprietário | Fechar e totalizar vendas confirmadas |
| POST /vendas | gerente, caixa proprietário do turno | Venda e baixa atômicas |
| GET /vendas/{id} | gerente, ia, caixa proprietário | Snapshot, pagamentos e consumos |
| POST /vendas/{id}/estornar | gerente | Estorno interno sem devolver estoque |
| GET /relatorios/estoque | gerente, estoquista, ia | Estoque utilizável, vencido e mínimo |
| GET /relatorios/vendas | gerente, ia | Receita/custo por hora e status |
| GET /relatorios/produtos | gerente, ia | Quantidade e receita por produto/dia |
| GET /relatorios/consumo | gerente, ia | Saída por ingrediente/dia/tipo/motivo |

## Venda

```json
{
  "idempotency_key": "82c65b6e-5a64-4a41-86d6-dc0ae360b1d2",
  "turno_id": "UUID_RETORNADO_AO_ABRIR_TURNO",
  "itens": [{"produto_id": "UUID_DO_PRODUTO", "quantidade": 2}],
  "pagamentos": [{"forma": "pix", "valor": "60.00"}]
}
```

Troque os UUIDs simbólicos pelos reais. As formas aceitas são `pix`, `dinheiro`, `cartao`. O valor deve ser o valor aplicado à venda, sem troco. O exemplo presume preço de R$ 30. A API não confirma liquidação de Pix/cartão; o pagamento é informado pelo operador.

Resposta 201: `id`, `operacao_id`, `turno_id`, `usuario_id`, `chave`, `payload_hash`, `total`, `custo`, `status`, `criado_em`. Reenvios idênticos também retornam 201 e o mesmo ID. Um reenvio após estorno retorna a venda com status estornada; não cria nova venda.

Erro de negócio: `{"detail":{"codigo":"ESTOQUE_INSUFICIENTE"}}`. Validação Pydantic usa o formato padrão de erros 422 com localização do campo.

- 401/403: credencial inválida/ausente ou `SEM_PERMISSAO`.
- 404: recurso não encontrado na operação autenticada.
- 409: `ESTOQUE_INSUFICIENTE`, `TURNO_FECHADO`, `PRODUTO_INDISPONIVEL`, `PAGAMENTO_DIVERGENTE`, `CHAVE_REUTILIZADA_COM_OUTRO_CONTEUDO`.
- 422: campos inválidos, `INGREDIENTE_DUPLICADO`, `LOTE_VENCIDO` no recebimento.

Não acessar PostgreSQL diretamente nas telas. Para frontend em outra origem, DEV1 deve configurar CORS com as origens exatas de desenvolvimento/produção; esta base não libera CORS globalmente.

## Assistente IA

`GET /ia/status`, `GET /ia/contexto` e `POST /ia/perguntar` aceitam apenas gerente/ia. Parâmetros, respostas e erros: veja `IA.md`. A chave do provedor é definida no backend; clientes usam o mesmo token individual de autenticação da API.

O frontend estático é servido em `/painel/`, sem autenticação porque contém somente a estrutura visual e estados de espera, sem dados da operação. As rotas de dados continuam autenticadas.

## Perdas por receita e total

- `POST /estoque/perdas`: agora aceita receita, turno e chave de idempotência opcionais.
- `POST /estoque/perdas/receita`: registra porções descartadas ainda não baixadas, com baixa FEFO atômica e idempotência obrigatória.
- `GET /relatorios/perdas`: filtros `inicio`, `fim` e `turno_id`; retorna total em reais, porções, quantidades por unidade, agrupamentos por receita/insumo/motivo e percentuais.

Detalhes, payloads e regra para evitar dupla baixa: `PERDAS.md`. Aplicar migration 002 antes de usar estas rotas ou o contexto de Otto atualizado.
