# Roteiro de demonstração — Otto / OktoStock

## Proposta em uma frase

“Ajudamos o dono da barraca a decidir quanto pré-assar e quando repor, conciliando demanda, capacidade e perdas, com decisões explicáveis e rastreáveis.”

## Demonstração sugerida (5 minutos)

1. **Problema (45 s):** dono decide durante o movimento; informações dispersas. Mostrar os IDs citados como recorte de investigação, sem afirmar causalidade ainda não validada.
2. **Decisão (60 s):** abrir Produção. Explicar diferença entre pré-assadas prontas, em preparo e nova fornada. No Swagger, mostrar que parâmetros ausentes geram pendências. Usar dados reais recebidos quando disponíveis. Se usar um cenário de teste, identificá-lo explicitamente como sintético; nunca tratá-lo como sábado observado.
3. **Perdas (60 s):** mostrar relatório por receita, ingrediente e total. Demonstrar, em banco de teste, que uma perda fica vinculada aos lotes e que reenvio da mesma chave não duplica a baixa. Separar perda de base comum de perda de porção recheada.
4. **Engenharia (60 s):** explicar transação atômica, FEFO, precisão decimal, histórico de custo, isolamento por barraca e testes. Otto lê os agregados; não executa SQL livre nem altera estoque.
5. **Limites e próximos passos (45 s):** dados de sábado e produção ainda serão integrados. Frontend estático não é painel conectado. Não anunciar economia ou acurácia que ainda não foram medidas.

## Evidências para levar

- Enunciado do problema e mapa dos registros com IDs e horários, depois de recebidos.
- Resultado reproduzível dos testes; não depender somente de uma resposta do modelo.
- Uma decisão explicada com parâmetros, restrição identificada e informação pendente.
- Um descarte rastreável e total reconciliado entre movimentos e relatório.
- Lista curta do que está implementado e do que depende da integração.

## Como demonstrar valor depois de integrar

Comparar decisões em janelas equivalentes: falta de produto/minutos indisponíveis, descarte em quantidade e reais, sobra utilizável, tempo necessário para decidir e atendimento da demanda. Reportar duração, tamanho da amostra e limitações. Não usar apenas faturamento como prova de benefício: público, preços e mix também mudam.

Perguntas esperadas: Por que não basta uma média diária? Como saber que o desfile afetou esta barraca? Como evitar superprodução? Por que confiar no custo? O que acontece sem dados ou sem chave? Qual parte funciona hoje sem o modelo? Como o pré-assamento evita baixar a mesma batata duas vezes?

Responder com evidências do sistema e limites reais. A credibilidade técnica é mais importante que prometer previsão perfeita.
