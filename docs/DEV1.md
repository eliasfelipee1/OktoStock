# DEV1 — backend e banco

Você mantém a API Python, o esquema PostgreSQL, as regras de negócio e a integração com os demais devs. O código desta pasta entrega um primeiro fluxo executável; não é toda a lista de funcionalidades do texto original.

## Regras implementadas

1. Quantidade em g/ml/un e custo por unidade base. Use strings decimais no JSON (`"0.008"` por grama), sem cálculos financeiros em float no cliente. Quantidades têm até 3 casas, custos até 6 e preços/pagamentos até 2. A API devolve números monetários; os clientes devem convertê-los para Decimal ou uma biblioteca decimal antes de calcular.
2. O cliente envia produto e quantidade. A API consulta preço e receita e confere a soma dos pagamentos. O recebimento registra saldo e movimento na mesma transação.
3. A venda consome lotes por validade, depois criação e UUID. Lote com validade de hoje é utilizável até o fim do dia no fuso configurado. Não há horário de vencimento nem controle de validade após abertura.
4. Cada mutação crítica bloqueia a operação e os lotes envolvidos. O MVP serializa escritas de estoque/vendas por barraca: simples e seguro para baixo volume; evoluir para locks mais granulares após testes de carga.
5. Reenvio de venda com mesma chave e payload retorna a venda original. Outra pessoa não recupera essa venda pelo reenvio, exceto gerente. Mesma chave com outro payload retorna conflito. Preserve exatamente o payload na fila do PDV (inclusive ordem dos itens e representação dos decimais).
6. Uma exceção desfaz venda, pagamentos, movimentações e saldo. A idempotência de vendas tem restrição única por operação no banco. Recebimentos e perdas ainda não têm chave de idempotência: não reenviar automaticamente após timeout; conferir lotes/movimentos primeiro.
7. Ficha técnica, nome, versão, preço e consumos ficam preservados. Para mudar receita ou preço, cadastre uma nova versão como novo produto e desative o anterior. A API não edita nem exclui fichas já cadastradas.
8. Estornar muda o status financeiro interno e registra auditoria. Não devolve comida ao estoque e não chama o provedor. Consumos continuam registrados. Não registrar novamente perda do mesmo alimento já consumido na venda; isso descontaria duas vezes. A perda separada é para saldo físico ainda existente.
9. Estoquista/IA não vendem. Caixa usa seu turno e consulta suas vendas. Gerente administra a operação. IA apenas lê; nenhum cliente recebe senha de PostgreSQL. A API resolve papel/operação a partir do hash do token.

## Cru e preparado

Neste MVP, cadastre a unidade efetivamente consumida pela ficha. Se a compra for de insumo cru e a venda consumir preparado, a equipe precisa definir um rendimento validado e converter antes do recebimento no estoque utilizável, ou implementar produção. Não misture gramas crus e preparados no mesmo insumo e não registre duas baixas para o mesmo preparo. O exemplo de batata usa peso bruto diretamente.

## Entrega para a equipe

- DEV2 recebe Swagger, token caixa, IDs do cardápio, contrato de vendas e códigos de erro. A disponibilidade é uma fotografia, não uma reserva. Offline precisa de política de conflito; este backend exige conexão para confirmar venda.
- DEV3 recebe token estoquista e endpoints de insumos, recebimentos, lotes, perdas e estoque.
- DEV4 recebe token `ia`, endpoints de relatórios e definição de cada indicador; veja `DEV4.md`.

## Próximas entregas sugeridas

1. Validar as fichas reais, unidades, rendimentos e preços dos cinco sabores com o responsável pela barraca.
2. Adicionar autenticação interativa e duração/revogação de sessões para o produto final.
3. Implementar adicionais e descontos com snapshots, composição de consumo e validação do total.
4. Acrescentar fornecedores/apresentações, conversão de compra e produção, com rastreabilidade entre lotes.
5. Tornar recebimentos/perdas idempotentes; expandir fechamento para conciliação por forma de pagamento, perdas, sangrias e divergências.
6. Implementar filtros/paginação e exportações dos relatórios, previsão por evento e restrições de validade.
7. Separar credenciais de schema/runtime, implantar backup/restauração e acompanhar logs antes do ambiente compartilhado.

Não altere migrations já aplicadas: crie `002_...sql` e rode o migrador. Evite editar saldo diretamente no pgAdmin, pois isso quebra a trilha de movimentações.
