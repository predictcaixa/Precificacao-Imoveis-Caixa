# Arquivo de artefatos legados

Esta pasta preserva resultados do treinamento antigo para consulta histórica. Esses arquivos não são dependências dos modelos AVM atuais e não devem ser usados para predição, avaliação ou retreinamento.

## `models/`

- `metadata.json`: métricas e metadados do treinamento legado; a API o lê somente para informar sua presença histórica.
- `modelo_gradient_boosting.pkl`, `modelo_linear.pkl` e `modelo_random_forest.pkl`: modelos serializados sem validação adequada.
- `importancia_features.png` e `scatter_predicoes.png`: gráficos produzidos pelo treinamento legado.

O AVM experimental vigente está separado em `../models/offer_avm/`. Os dados-fonte e arquivos de auditoria não foram movidos.
