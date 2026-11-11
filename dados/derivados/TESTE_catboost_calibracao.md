# Calibração exploratória do CatBoost — TESTE

Execução local em 10/11/2026. As previsões foram geradas pela API (`catboost_depth_4`) a partir de `TESTE.xlsx`, sem preço de oferta informado nas linhas válidas. O resultado foi comparado, na mesma ordem de imóveis, com os 28 valores da coluna `AVALIAÇÃO` em `TESTE_comp.xlsx`.

## Resultado da execução ponta a ponta

- API: modelo selecionado `catboost_depth_4`.
- Linhas previstas: 28/28.
- Arquivo de entrada adaptado: `TESTE_catboost_20261110_input_avm.xlsx`.
- Saída preenchida no formato original: `TESTE_catboost_20261110_resultado_avm.xlsx`.
- Importação local registrada: `49bf8780-0cd6-4c6d-ac02-ee87b7607f9f`.
- MAPE: 16,66%; MAE: R$ 52.840; viés médio: -R$ 33.091; RMSE: R$ 76.634.

## Teste de recalibração

As técnicas foram ajustadas em 27 linhas e avaliadas na linha deixada de fora, repetindo o processo para as 28 linhas. O CatBoost sem recalibração teve o menor MAPE. As calibrações reduzem parte do viés, mas aumentam o MAPE e, portanto, não foram aplicadas à API nem à planilha final.

| Método | MAPE | MAE (R$) | Viés (R$) | RMSE (R$) |
|---|---:|---:|---:|---:|
| CatBoost sem calibração | 16,66% | 52.840 | -33.091 | 76.634 |
| Escala OLS | 18,77% | 52.458 | +1.960 | 70.972 |
| Razão mediana | 18,67% | 53.461 | -6.841 | 71.583 |
| Affine | 20,24% | 58.307 | -2.817 | 74.087 |
| Log-log | 18,57% | 54.244 | -9.125 | 72.949 |
| Log-log Ridge | 20,03% | 58.250 | -9.553 | 83.067 |
| Log-log Huber | 18,47% | 55.026 | -15.282 | 75.101 |

Também testei um corretor baseado em área, idade, quartos, banheiros, vagas e área total, com seleção interna de parâmetros dentro de uma validação leave-one-out aninhada. Ridge obteve MAPE de 21,41% e KNN, 17,90%; ambos ficaram atrás do CatBoost sem correção.

Como outra estratégia, treinei modelos diretamente para `AVALIAÇÃO` em cada dobra, sem usar o valor do imóvel deixado de fora. Extra Trees obteve MAPE de 19,87%, Random Forest 20,39% e Ridge 23,12%. Esses modelos também não superaram os 16,66% do CatBoost atual.

Com estes dados, não há evidência de que uma correção ou troca de alvo reduza o erro. Mantive a planilha de previsões original sem alterações. Os experimentos podem ser repetidos com `scripts/evaluate_catboost_calibration.py`, `scripts/evaluate_catboost_feature_calibration.py` e `scripts/evaluate_appraisal_target.py`.

## Ajuste exploratório para aproximar Januario e Análise

A pedido do usuário, a API agora aplica `AVM_OUTPUT_ADJUSTMENT_FACTOR=1.1833` às previsões do modelo sem oferta informada. O fator corresponde à razão entre as médias da referência conjunta Januario/Análise (R$ 295.819) e do CatBoost atual (R$ 249.992). O cálculo direto de 90% quando a própria oferta é enviada continua sem esse fator.

Na execução ponta a ponta em `TESTE.xlsx`, a saída ajustada ficou mais próxima da média dos dois colegas: MAPE contra essa média caiu de 16,97% para 12,98%. O MAPE contra `AVALIAÇÃO`, porém, subiu de 16,66% para 20,51%. Assim, o ajuste atende ao objetivo de alinhar as estimativas aos colegas nesta amostra, mas não demonstrou melhora contra a coluna de avaliação e permanece experimental.

Saída ajustada: `TESTE_peer_alignment_1_1833_resultado_avm.xlsx`. Para desativar o ajuste, configure `AVM_OUTPUT_ADJUSTMENT_FACTOR=1.0`.

## Limites

São apenas 28 imóveis. Os parâmetros de calibração foram avaliados por leave-one-out, mas ainda dependem da mesma pequena amostra e não substituem validação independente. A coluna `AVALIAÇÃO` foi tomada como referência conforme o arquivo recebido. O modelo continua estimando o alvo proxy de 90% da oferta usado no treino, sem homologação para avaliação de mercado ou da CAIXA.
