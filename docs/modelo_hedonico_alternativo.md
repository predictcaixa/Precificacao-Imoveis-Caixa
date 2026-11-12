# Sistema 2: modelo hedonic alternativo

## Desenho atual

O Sistema 2 usa regressao Ridge com splines quadraticas para atributos numericos, efeitos categoricos de distrito e prefixo CEP de cinco digitos. O Sistema 1 usa CatBoost. A diferenca de algoritmo e de processamento e preservada; resultados dos colegas nao entram no treino nem na predicao cotidiana.

O alvo v4 e o valor integral de oferta, reconstruido da coluna auditada `0,90*OFERTA`. Nao e valor de venda confirmado nem avaliacao CAIXA.

## Calibracao usada no deploy

O deploy2 aplica por padrao o fator de oferta `0.8484475849363369`, estimado como a mediana entre ofertas observadas e predicoes brutas em uma particao geografica separada. A calibracao nao usa resultados de colegas. Pode ser desabilitada com `ENABLE_OFFER_CALIBRATION=false` para diagnostico; a predicao calibrada e a saida de rotina solicitada.

No holdout geografico independente, o modelo bruto teve MAE R$249.270 e MAPE 24,56%. Com o fator aplicado, teve MAE R$304.509 e MAPE 27,58%. O fator foi mantido no deploy por decisao do projeto; a piora do holdout precisa permanecer visivel na revisao do modelo.

## Entrada e execucao

- Deploy: `deploy2/`; espelho: `deploy/hedonic-api/`.
- Envie uma planilha `.xlsx` estilo `TESTE.xlsx` para `POST /predict/upload`.
- A API preserva a planilha e preenche valor estimado, valor unitario, metodologia e observacoes nas quatro colunas finais.
- O processamento aceita ate 500 imoveis validos por planilha e nao abre arquivos de comparacao dos colegas.
- As rotas JSON `/predict` e `/predict/batch` usam a mesma calibracao padrao.
- Entradas relevantes: area privativa, idade, quartos, banheiros, vagas, elevador, area total, distrito e CEP. Campos ausentes continuam ausentes; nao sao convertidos em zero.
- Os codigos de ELEVADOR de TESTE sao tratados assim: `2` confirmado, `1` nao confirmado/ausente, `0` sem elevador.

O Sistema 2 permanece experimental; estimar oferta nao demonstra valor de venda ou avaliacao profissional.

## Comparacao de desenvolvimento

Planilhas de colegas podem ser utilizadas em validacoes de desenvolvimento, sempre identificadas como referencias externas. A conversao de uma previsao do Sistema 1 treinada em 90% da oferta para uma equivalencia de oferta integral e feita dividindo-a por `0.90`; isso nao cria uma nova predicao do Sistema 1. A coluna de calculo aritmetico `0.90 x oferta` e separada da coluna CatBoost.
