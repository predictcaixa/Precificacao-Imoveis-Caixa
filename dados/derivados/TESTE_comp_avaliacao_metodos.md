# Avaliação exploratória de métodos — TESTE_comp.xlsx

Casos usados: 28. Referência: coluna AVALIAÇÃO. Área: coluna AREA PRIV. A coluna Guilherme registra o XGBoost anterior; a saída CatBoost da API, agora padrão, é lida do arquivo TESTE_catboost_resultado_avm.xlsx quando disponível.
As correções próprias foram pontuadas por leave-one-out: para cada linha, os parâmetros foram ajustados nos outros casos e avaliados somente na linha separada.
As previsões dos colegas são referências do mesmo conjunto de 28 casos, não validação independente nem comparação cega de protocolos.

| Método | N | MAE (R$) | MAPE | MdAPE | RMSE (R$) | Viés (R$) | Acima | Abaixo |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Referência colega: HILDER/ CatBoost | 28 | 27,767 | 9.76% | 9.12% | 35,184 | -961 | 15 | 13 |
| Referência colega: FERNANDO²/ Gradient boosting | 28 | 29,217 | 10.36% | 8.61% | 36,569 | -8,788 | 10 | 18 |
| Referência colega: FERNANDO¹/ Gradient boosting | 28 | 33,526 | 11.88% | 9.95% | 40,616 | -15,754 | 8 | 20 |
| Referência colega: JANUARIO/ CatBoost | 28 | 32,852 | 12.61% | 10.12% | 38,250 | +12,544 | 20 | 8 |
| API CatBoost novo padrao (inferencias; alvo proxy) | 28 | 52,840 | 16.66% | 12.73% | 76,634 | -33,091 | 10 | 18 |
| Razão mediana (LOOCV) | 28 | 54,130 | 18.42% | 16.29% | 76,307 | -13,041 | 14 | 14 |
| Referência colega: THIAGO/  CatBoost | 28 | 51,538 | 18.86% | 13.75% | 76,472 | +34,951 | 20 | 8 |
| Referência colega: ANALISE EVOLUTIVA/ Mediana dos modelos empatados no teste E Mediana das vendas próimas | 28 | 51,631 | 19.61% | 20.26% | 63,424 | +12,928 | 18 | 10 |
| Fator proporcional (LOOCV) | 28 | 56,144 | 20.00% | 17.15% | 77,123 | +842 | 16 | 12 |
| Correção linear intercepto + inclinação (LOOCV) | 28 | 62,202 | 21.64% | 18.41% | 85,790 | -3,261 | 16 | 12 |
| Área × mediana de R$/m² (LOOCV) | 28 | 58,996 | 21.81% | 17.97% | 70,894 | -2,284 | 14 | 14 |
| Regressão linear simples pela área (LOOCV) | 28 | 66,386 | 23.69% | 18.37% | 87,906 | -5,786 | 15 | 13 |
| Referência colega: LUCIANA/ XGBOOST | 28 | 85,826 | 33.17% | 28.25% | 101,536 | +40,676 | 18 | 10 |
| API XGBoost anterior (sem ajuste) | 28 | 254,371 | 101.27% | 99.03% | 264,760 | +254,371 | 28 | 0 |

## Limites

Esta amostra é pequena (28 apartamentos) e serve para triagem. A correção recalibrada não foi incorporada à API nem deve ser tratada como modelo aprovado. Um bom resultado aqui precisa ser confirmado em imóveis independentes, idealmente em outro período e região.
A coluna AVALIAÇÃO foi tratada como valor de referência conforme o arquivo recebido. Se representar outro conceito, a avaliação precisa ser refeita com o alvo apropriado.
