# Contrato de integração proposto — validar com o dev responsável

Sem criar tabelas nesta etapa. Aceitar arquivos/tabelas de origem e construir um adaptador quando o esquema for combinado.

Cada registro precisa preservar: ID original, fonte, instante do evento com fuso, instante em que ficou disponível para a operação, localização/pavilhão/portão, tipo de observação, texto original ou medida, unidade e status de validação. Guardar vínculos entre fontes somente quando confirmados.

Para KT: esclarecer se mede pedidos, porções, pessoas ou consumo de insumos; se o valor é acumulado ou do intervalo; início/fim da janela; local; produto/sabor se houver. Não somar valores acumulados como se fossem novos eventos.

Para PG: início/fim previstos, local e eventuais alterações. Para RD: horário do relato versus horário do fato, local, natureza da observação e distinção entre estimativa e contagem.

Rejeitar ou sinalizar IDs duplicados conflitantes, horários sem contexto, medidas negativas indevidas, unidades incompatíveis e locais não mapeados. Não preencher lacunas com números inventados.

Dados adicionais para decisão: contagem utilizável de pré-assadas por lote e validade, produção em andamento e término previsto, capacidade livre, tempo de pré-assamento, rendimento, ingredientes disponíveis, margem definida pelo dono e demanda prevista com origem/intervalo de incerteza.

Para perdas: ID, horário, lote de origem, etapa, insumo/unidade, quantidade, motivo, responsável, turno, receita/versão quando efetivamente aplicável, custo histórico, destino e movimento de estoque associado. Vínculo com consumo já efetuado evita uma segunda baixa.

Validação temporal: ao simular uma decisão às 15h, usar apenas registros disponíveis até 15h. Dados de consumo das 16h servem para avaliar o resultado, não para fingir que eram conhecidos antes. Treino e avaliação devem respeitar a ordem temporal.

Critérios de entrada: IDs preservados; reconciliação de totais por intervalo/local; divergências explícitas; nenhum dado de outra operação; campos desconhecidos mantidos como pendências. Sem os dados recebidos, PG-04/RD-09/KT são apenas referências fornecidas pelo usuário.
