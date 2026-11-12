# Processo dos Sistemas 1 e 2

## Uso cotidiano

O arquivo de consumo e uma planilha `.xlsx` no formato `TESTE.xlsx`. O deploy do Sistema 2 recebe a planilha em `POST /predict/upload`, estima cada linha valida, preserva o workbook e devolve as quatro colunas finais preenchidas. O processamento diario nao requer nem consulta arquivos com resultados de colegas.

O Sistema 1 continua no pacote `deploy/api/`; o Sistema 2 fica em `deploy2/`, com espelho em `deploy/hedonic-api/`. Mantenha artefatos, rotas e identificadores de modelo separados.

## Definicoes dos modelos

| Item | Sistema 1 | Sistema 2 v4 |
|---|---|---|
| Metodo | CatBoost | Ridge hedonic com splines quadraticas |
| Alvo | 90% do valor de oferta | Valor integral de oferta |
| Localizacao | Inclui campos de localizacao e socioeconomicos do seu treinamento | Distrito e prefixo CEP de cinco digitos |
| Uso em deploy | API do Sistema 1 | API separada com calibracao de oferta v4 ativa por padrao |

O valor integral de oferta e um preco anunciado, nao uma venda confirmada nem avaliacao CAIXA. A calibracao do Sistema 2 usa apenas valores de oferta de uma particao geografica separada; nao usa previsoes de pares.

## Validacoes de desenvolvimento

Resultados de Januario, Analise Evolutiva e Guilherme podem apoiar validacoes e comparacoes durante o desenvolvimento. Devem permanecer fora da entrada de rotina, do treino e da calibracao dos modelos.

Na planilha de comparacao, a coluna do CatBoost de Guilherme e diferente da coluna aritmetica `0,90 x OFERTA`. Se for necessario comparar saidas na escala de oferta integral, converter apenas o CatBoost de alvo 90% dividindo sua saida por `0,90`; identificar como equivalencia aritmetica, nao como nova predicao. A coluna `0,90 x OFERTA` permanece uma referencia aritmetica separada.

A faixa de +/-7% em relacao ao valor de oferta e um diagnostico de proximidade, nao uma metrica de acuracia nem uma regra de ajuste forcado. A validacao principal deve usar dados rotulados e geograficamente separados, manter as metricas por variante e registrar as limitacoes.

## Calibracao v4 do Sistema 2

O fator padrao e `0.8484475849363369`, aprendido em particao geograficamente separada de ofertas. No holdout geografico independente, o resultado bruto teve MAE R$249.270 e MAPE 24,56%; o resultado calibrado teve MAE R$304.509 e MAPE 27,58%. A variante calibrada permanece padrao no deploy conforme solicitado, e essa diferenca deve ser considerada ao revisar os resultados.

## Verificacao e arquivos

- Treinamento e relatorio: `scripts/train_hedonic_avm.py`, `models/hedonic_avm/report.json`.
- API e upload XLSX: `deploy2/main.py`, rota `POST /predict/upload`.
- Artefato ativo: `models/hedonic_avm/hedonic_spline_ridge_v4_offer_calibrated.joblib`.
- Relatorios de comparacao e validacao: `scripts/process_test_workbook_system2.py` e arquivos `TESTE_system2_hedonic_v4_*` em `dados/derivados/`.

O Sistema 2 permanece experimental; nao esta aprovado como avaliacao de mercado, garantia ou credito.
