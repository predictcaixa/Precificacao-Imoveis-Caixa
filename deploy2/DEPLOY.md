# Deploy do Sistema 2

`deploy2/` e o pacote da API do Sistema 2. Ele recebe planilhas `.xlsx` no formato `TESTE.xlsx` pela rota `POST /predict/upload`, processa as linhas sem acessar arquivos de resultados dos colegas e devolve a planilha original preenchida nas quatro colunas de saida. Tambem mantem as rotas JSON `/predict`, `/predict/batch` e `/predict/workbook`.

A configuracao padrao usa a versao v4 calibrada para valor integral de oferta. O fator foi aprendido em uma particao geografica de ofertas, sem consultar resultados de outros sistemas. `ENABLE_OFFER_CALIBRATION=false` desativa o fator; por padrao ele fica ativo. A API fica habilitada por padrao; `ENABLE_EXPERIMENTAL_HEDONIC_AVM=false` pode desabilita-la.

O modelo usa Ridge hedonico com splines, atributos fisicos, distrito e prefixo de CEP com cinco digitos. O alvo e preco anunciado, nao venda confirmada nem avaliacao da CAIXA. No holdout geografico, a variante calibrada teve MAE R$304.509 e MAPE 27,58%, contra R$249.270 e 24,56% sem o fator. A calibracao permanece padrao por decisao do projeto e esse resultado deve acompanhar a revisao antes do uso operacional.

O deploy exige Python 3.13, scikit-learn 1.9.1, joblib 1.6.0 e dependencias em `requirements.txt`. O runtime valida versoes e SHA-256. Configure o diretorio raiz do servico como `deploy2/` e use o `Procfile` incluido.

A rota de upload exige planilha com cabecalho e colunas equivalentes a AREA PRIVATIVA, idade, bairro/distrito, CEP e quatro colunas finais de saida do arquivo TESTE. Limite: 20 MB e 500 imoveis validos. Na coluna ELEVADOR, os codigos do TESTE sao respeitados: `2` significa confirmado; `1` significa nao confirmado e e tratado como ausente; `0` indica ausencia de elevador.
