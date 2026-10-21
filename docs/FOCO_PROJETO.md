# OktoStock / Otto — recorte para apresentação

## Pessoa e problema

O dono da barraca decide quanto de **batata pré-assada** preparar e quando repor. Ele precisa conciliar movimento esperado, saldo pronto, produção em andamento e desperdício, em meio ao atendimento.

**Enunciado:** O dono da barraca tem dificuldade para dimensionar e repor as batatas pré-assadas durante variações no movimento, pois as informações de demanda, produção e perdas não chegam consolidadas a tempo da decisão.

Hipótese de consequência: falta durante o pico e sobra após o movimento. Ainda não há evidência importada no projeto para afirmar que isso ocorreu, nem para quantificar impacto.

## Evidências recebidas e limites

O usuário citou PG-04 (desfile às 16h na Rua XV), RD-09 (fila no Portão B às 15h55, com referência ao desfile) e KT-14 a KT-17 comparados com KT-09 a KT-12 (distribuição do consumo às 16h versus meio-dia). Os arquivos serão entregues por outro desenvolvedor.

Esses IDs ainda não foram importados, conciliados ou validados. O relato das 15h55 antecede o início informado do desfile; não atribuir causalidade automaticamente. Mudança na distribuição do consumo não prova aumento do total nem identifica demanda da barraca. Não transformar número de visitantes em vendas sem taxa de conversão observada e contexto espacial.

## Fluxo que precisa ser modelado quando as tabelas forem definidas

Batata crua → limpeza → pré-assamento → lote de batatas pré-assadas → montagem por sabor → venda ou descarte.

- O início da produção consome a matéria-prima; a conclusão gera lote preparado, rendimento e horário.
- A venda consome a base preparada e os recheios; não consome novamente a batata crua.
- Descarte de base pré-assada consome o lote preparado, sem imputar ingredientes de recheios.
- Uma base comum não tem sabor até a montagem ou atribuição explícita.
- Não combinar o futuro fluxo de produção com a ficha atual que baixa batata crua diretamente. A transição precisa de nova versão da receita e testes de reconciliação.
- Validade e condições de conservação devem ser fornecidas pelo responsável técnico/operacional, nunca inventadas pelo agente.

## Perdas no centro da decisão

| Etapa | Registro necessário | Cuidado |
|---|---|---|
| Limpeza | Peso bruto, líquido e descarte real | Rendimento previsto não é uma segunda baixa |
| Pré-assamento | Queima, fora do padrão, lote e quantidade | Registrar o insumo/base, não uma receita completa |
| Espera | Sobra ou validade do lote preparado | Não atribuir sabor que ainda não existe |
| Montagem | Receita/versão e consumos reais | Separar base e recheios |
| Pós-venda | Devolução e destino do alimento | Não baixar de novo algo consumido na venda |

Implementado hoje: perdas físicas por lote, vínculo opcional a receita, perda de porções ainda não baixadas, total histórico em reais, quantidades por unidade, agrupamentos e percentuais sobre vendas. Ainda pendentes: transformação em lotes preparados, etapa estruturada, perda atribuída à produção, reclassificação pós-venda e custo de produção com despesas adicionais.

Medir separadamente desperdício por quantidade (mesmo insumo/unidade), custo de descarte, indisponibilidade e sobra utilizável. Uma sobra de pré-assadas não é automaticamente perda: depende de destino e validade. Motivo registrado não comprova causa raiz.

## Entregas priorizadas

1. Receber e validar registros de sábado com IDs, horários e localização; mapear quais medem consumo, fila, programação ou vendas.
2. Definir tabelas de produção e lotes preparados, incluindo perdas por etapa e prevenção de dupla baixa.
3. Integrar o cálculo de uma fornada aos dados reais, com uma previsão de demanda identificada e validada.
4. Integrar as telas HTML/CSS à API (templates Python e formulários permitem continuar sem JavaScript).
5. Validar alertas e registrar decisão do dono e resultado; só depois medir benefício.

## Calculadora já implementada, sem tabelas novas

`POST /planejamento/pre-assadas`, acesso gerente/ia. Recebe os nove campos de `app/planning.py`. Ausência de qualquer parâmetro devolve `dados_pendentes`; zero informado é distinto de ausente. Não grava produção nem chama o modelo.

Necessidade = max(0, demanda prevista + margem definida pelo dono − pré-assadas utilizáveis − produção já em andamento disponível no prazo).

Nova fornada fica limitada à capacidade **livre agora** do forno, insumos e espaço disponível. Se não terminar antes do atendimento, não conta como atendimento da demanda desse horizonte. Mostra déficit da demanda separado do déficit da margem de segurança.

O contrato usa porções-base equivalentes (uma base para uma batata recheada), não gramas. O adaptador futuro precisa converter com rendimento cadastrado e verificar que as três quantidades de oferta não se sobrepõem. A entrada `em_preparo_prontas_no_prazo` não inclui o novo lote calculado. O prazo é relativo ao instante da requisição; fila do forno e tempo completo de disponibilização devem estar incluídos nos parâmetros.

`pre_assadas_utilizaveis` deve excluir vencidas, reservadas para outras demandas e lotes que não possam ser usados no horizonte. `espaco_disponivel_porcoes` deve considerar o que já está ocupado/reservado. Não há calendário de fornadas sucessivas nesta versão. A demanda e validade são fornecidas na entrada: não são estimadas ou verificadas pelo cálculo.

Otto explica a decisão e as pendências. O cálculo funciona sem chave Anthropic; sua conexão automática com as fontes de produção ainda depende das tabelas. Não apresentar esta calculadora como previsão treinada ou como automação da cozinha.
