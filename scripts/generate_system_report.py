from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from xml.sax.saxutils import escape
from datetime import date

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'docs' / 'relatorio_tecnico_sistema_precificacao.docx'
OUT.parent.mkdir(parents=True, exist_ok=True)
body=[]

def para(text='', style=None, bold=False):
    ppr = f'<w:pPr><w:pStyle w:val="{style}"/></w:pPr>' if style else ''
    rpr = '<w:rPr><w:b/></w:rPr>' if bold else ''
    body.append(f'<w:p>{ppr}<w:r>{rpr}<w:t xml:space="preserve">{escape(str(text))}</w:t></w:r></w:p>')

def heading(text, level=1): para(text, f'Heading{level}')
def bullet(text): para('•  ' + text, 'Normal')
def table(headers, rows):
    def cell(v, header=False):
        fill = '<w:shd w:fill="17365D"/>' if header else ''
        color = '<w:color w:val="FFFFFF"/>' if header else ''
        return '<w:tc><w:tcPr><w:tcW w:w="0" w:type="auto"/>'+fill+'</w:tcPr><w:p><w:r><w:rPr>'+('<w:b/>' if header else '')+color+'</w:rPr><w:t xml:space="preserve">'+escape(str(v))+'</w:t></w:r></w:p></w:tc>'
    trs = '<w:tr>' + ''.join(cell(x, True) for x in headers) + '</w:tr>'
    for row in rows: trs += '<w:tr>' + ''.join(cell(x) for x in row) + '</w:tr>'
    body.append('<w:tbl><w:tblPr><w:tblW w:w="5000" w:type="pct"/><w:tblBorders><w:top w:val="single" w:sz="4" w:color="B4C6E7"/><w:left w:val="single" w:sz="4" w:color="B4C6E7"/><w:bottom w:val="single" w:sz="4" w:color="B4C6E7"/><w:right w:val="single" w:sz="4" w:color="B4C6E7"/><w:insideH w:val="single" w:sz="4" w:color="B4C6E7"/><w:insideV w:val="single" w:sz="4" w:color="B4C6E7"/></w:tblBorders></w:tblPr>'+trs+'</w:tbl>')

def pagebreak(): body.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

para('RELATÓRIO TÉCNICO DO SISTEMA', 'Title')
para('Sistema de Precificação de Imóveis — versão de preparação para deploy', 'Subtitle')
para('Documento t\u00e9cnico preliminar | atualiza\u00e7\u00e3o de 11 de novembro de 2026')
para('Projeto: Precificacao-Imoveis-Caixa')
para('Escopo documentado: fluxo de importação de planilhas, previsão experimental, persistência de importações e geração de arquivo de saída com quatro campos.')
para('Situação: rascunho interno para revisão. Não é o Relatório do Modelo oficial assinado, não representa homologação CAIXA e não autoriza uso operacional.')
heading('Resumo executivo')
para('O projeto re\u00fane interface web (HTML/JavaScript), API FastAPI e artefatos experimentais de precifica\u00e7\u00e3o. O fluxo de planilha calcula diretamente 90% da oferta positiva; sem oferta v\u00e1lida, usa o AVM experimental. O m\u00e9todo aplicado fica identificado por linha no resultado e no hist\u00f3rico. O escopo atual de deploy\u00a0\u00e9 somente API em deploy/api, conectada ao PostgreSQL Supabase; a interface pode ser hospedada separadamente.')
para('O pipeline da base 30.10.2026.xlsx foi executado anteriormente pela API local: 12.762 linhas foram examinadas; 11.052 receberam estimativa e 1.710 n\u00e3o receberam previs\u00e3o por valida\u00e7\u00e3o/escopo, principalmente\u00a0\u00e1rea privativa fora do intervalo aceito. Em 11 de novembro de 2026, foi adicionada POST /predict/workbook e sincronizada com deploy/api. Isso n\u00e3o significa deploy remoto nem teste em navegador.')
para('A estimativa do AVM atual tem alvo experimental equivalente a 90% do preço anunciado (proxy com desconto uniforme), não a preço efetivamente transacionado nem a valor de avaliação CAIXA. O relatório de treinamento registra teste geográfico independente de 1.888 observações (MAE R$ 165.945,60; MAPE 18,04%; R² 0,740; viés médio −R$ 84.296,40). Isso não demonstra adequação operacional nem validação contra laudos de avaliação.')
heading('1. Objetivo, escopo e documentos consultados')
para('Este documento consolida a implementação observável no código, resultados de execução registrados no trabalho, organização para deploy e a conferência de requisitos dos documentos PDF disponíveis no repositório. O material PDF é usado como referência de requisitos e conteúdo técnico; não substitui a solicitação do usuário nem autoriza afirmações de conformidade.')
para('O roteiro da CAIXA anexado recomenda, preferencialmente, cerca de 80 páginas e explicita que a empresa precificadora é responsável pelas informações, assinaturas e evidências. Este documento é um relatório técnico resumido de situação do sistema; não satisfaz sozinho a extensão nem todos os campos do formulário oficial e não deve ser enviado como versão final.')
table(['Documento consultado','Uso nesta revisão'],[
('Relatório do Modelo de Precificação — Edital nº 012/2026 (PDF, 18 páginas)','Roteiro de conteúdo, rastreabilidade, limitações, assinaturas digitais, PDF/A e requisitos de apresentação.'),
('Respostas objetivas — IUP/IBAPE-SP (PDF, 3 páginas)','Referência de cautelas sobre escopo, uso de índices, fontes, saída auditável e responsabilidade profissional; respostas não tratadas como norma oficial.'),
('Índice de Unidades Padronizadas — IBAPE/SP, atualização 2019 (PDF, 44 páginas)','Referência técnica para apartamentos/escritórios na Região Metropolitana de São Paulo; não há evidência de que seus coeficientes estejam implementados neste pipeline.'),
('avaliacaoImovel.pdf (convocação de serviço)','Exemplo documental com identificadores e endereço; não é prova de que o sistema leia matrículas ou cumpra o fluxo operacional CAIXA.'),
('Docs e código local: avaliação de conformidade, rascunho do relatório, README, main.py, index.html, scripts e artefatos do modelo','Evidências técnicas locais e limitações registradas no repositório.')])
heading('2. Funcionalidades e ajustes recentes')
for t in [
'Interface permite selecionar planilhas .xlsx e processá-las individualmente; identifica cabeçalhos AVM conhecidos e adapta campos do formulário de comparação quando compatíveis.',
'Valida os campos conforme regras do endpoint; registra erros por linha e envia registros aceitos a POST /predict/batch em lotes de at\u00e9 500. POST /predict/workbook aceita manualmente a mesma lista de campos e devolve XLSX no layout do teste.',
'Registra importação e estado/resultado das linhas pelas rotas /avm/imports, incluindo status, dados de origem, estimativa ou erro, sujeito ao banco configurado na API.',
'Preserva as abas e os dados de origem na planilha de resultado; preenche ou acrescenta os quatro campos finais. Linhas não elegíveis ficam sem valor estimado e recebem estado/observação explicativa.',
'Scripts de execução em lote foram adicionados: scripts/process_comparison_workbook.py para o formulário comparativo e scripts/process_system_base.py para a base consolidada.',
'Pacote da API em deploy/api, com main.py, depend\u00eancias, modelos, Procfile e instru\u00e7\u00f5es; inclui a rota manual de download XLSX sem alterar a l\u00f3gica de previs\u00e3o.'
]: bullet(t)
heading('2.1 Campos finais do arquivo de saída')
table(['Coluna','Conteúdo'],[
('Valor estimado (R$)','Estimativa retornada pelo modelo para linha elegível.'),
('Valor unitário (R$/m²)','Valor estimado dividido pela área de entrada reconhecida.'),
('Metodologia','Identificação do modelo e indicação de caráter experimental/proxy.'),
('Observações','Limitações, validações, erros ou motivo para ausência de previsão.')])
para('O arquivo de entrada do teste mant\u00e9m esses quatro campos nas\u00a0\u00faltimas colunas (W\u2013Z). No upload, o sistema preserva o arquivo original e preenche essas colunas; na entrada manual, POST /predict/workbook gera planilha com os mesmos 26 cabe\u00e7alhos e quatro campos nas mesmas posi\u00e7\u00f5es. Campos n\u00e3o enviados ficam vazios.')
heading('3. Modelo, dados e resultado técnico')
heading('3.1 Alvo e algoritmo',2)
para('O relat\u00f3rio de treinamento registra xgboost_depth_6 como candidato de melhor valida\u00e7\u00e3o naquele experimento e define o alvo como 0,90 x pre\u00e7o de oferta. A API atual configura CatBoost como padr\u00e3o por AVM_DEFAULT_MODEL=catboost (catboost_depth_4); os tr\u00eas artefatos permanecem dispon\u00edveis. A taxa de 10% \u00e9 uniforme no conjunto de origem, n\u00e3o desconto regional validado. O valor n\u00e3o deve ser descrito como transa\u00e7\u00e3o realizada, valor fiscal ou avalia\u00e7\u00e3o profissional/CAIXA.')
para('O roteiro PDF consultado é delimitado a apartamentos na cidade de São Paulo/SP. O artefato confirma uma base de apartamentos, mas não contém neste resumo uma declaração suficiente de cobertura territorial validada para afirmar aderência ao recorte do edital; a cobertura e representatividade devem ser confirmadas na versão de dados submetida.')
para('Variáveis registradas no relatório de treinamento incluem latitude, longitude, idade, quartos, banheiros, vagas, elevador, rendas IBGE 2022, áreas, CEP, região, distrito, setor censitário e padrão IPTU. Colunas de preço/identificadores listadas como excluídas incluem oferta, valores fiscais/ITBI, endereço e matrícula. A disponibilidade preenchida não comprova origem ou validação independente de cada atributo.')
heading('3.2 Partições e métricas registradas',2)
table(['Partição','n','MAE','MAPE','R²','Viés'],[
('Validação usada na seleção','2.032','R$ 113.727,30','19,23%','0,840','R$ 9.439,17'),
('Teste geográfico independente','1.888','R$ 165.945,60','18,04%','0,740','−R$ 84.296,40')])
para('Parâmetros do XGBoost selecionado registrados no relatório: max_depth=6, n_estimators=500, learning_rate=0,05, subsample=0,8, colsample_bytree=0,8 e reg_lambda=1,0. Semente registrada: 42. O teste geográfico independente não foi usado para selecionar o candidato. As métricas descrevem o alvo de oferta proxy na partição disponível; não são metas de aceitação CAIXA e não substituem validação externa por avaliações concluídas.')
heading('3.3 Execução da base 30.10.2026',2)
table(['Indicador da execução registrada','Resultado'],[
('Linhas lidas','12.762'),('Estimativas retornadas','11.052'),('Linhas sem estimativa por validação/escopo','1.710'),('Modelo API informado','xgboost_depth_6'),('Identificador da importação','d47650d7-9477-41ef-a5d5-660f70913171'),('Arquivo de saída','dados/derivados/30.10.2026_resultado_avm.xlsx'),('Banco observado na execução','SQLite local')])
para('A base continha área privativa fora do intervalo aceito em grande parte das recusas. O requisito de área na rotina é 35 a 1.000 m²; idade também precisa ser informada e validada. A contagem observada na execução (11.052/1.710) difere da contagem no relatório de treinamento (11.055/1.707); essa diferença de três registros deve ser reconciliada por hash/versão da base e regra de elegibilidade antes de uma publicação formal.')
heading('3.4 Comparador ITBI separado')
para('O comparador experimental ITBI é outro recurso e não deve ser confundido com o AVM de oferta: usa mediana de valor declarado por m² segmentada por CEP/padrão IPTU, com fallback. O artefato registra teste temporal de 11.394 transações, MAE R$ 254.020,79, MdAPE 23,6348%, P90 do erro percentual absoluto 70,5847% e R² 0,553255. A fonte é ITBI declarada e não constitui rótulo de avaliação CAIXA. Esses números não são métricas do XGBoost de oferta.')
heading('4. Fluxo ponta a ponta e limites')
for t in [
'Usuário seleciona planilha; navegador reconhece cabeçalhos de oferta (VALOR OFERTA, OFERTA, VALOR OFERTA BRL e variantes normalizadas), identifica a aba e constrói registros para a API.',
'Com oferta numérica positiva, calcula 0,90 × oferta e arredonda o valor monetário a centavos. Esse cálculo não exige atributos do modelo. Uma oferta inválida é marcada para correção.',
'Sem oferta, valida área privativa (35–1.000 m²), idade (0–20 anos) e demais atributos e usa o AVM experimental; linhas não elegíveis recebem erro explicativo.',
'Registros elegíveis são enviados à API em lotes de até 500; a API decide por linha entre cálculo direto e modelo e registra resultados/status conforme o armazenamento configurado.',
'A interface monta workbook de sa\u00edda com abas/linhas originais e as quatro colunas de resultado; o usu\u00e1rio baixa o arquivo. A entrada manual em POST /predict/workbook produz XLSX com a mesma estrutura de 26 colunas do teste e sa\u00eddas nas quatro posi\u00e7\u00f5es finais.',
'Limite: a prova ponta a ponta registrada foi executada por script contra API local. A página web alterada e o pacote sincronizado não foram validados em navegador após atualização.'
]: bullet(t)
para('A execução local anterior usou SQLite. Embora requirements e instruções do backend contemplem PostgreSQL por AVM_DATABASE_URL, isso não prova que o deploy esteja ligado a uma instância PostgreSQL. A conexão de produção, CORS e URL pública do frontend precisam ser configurados no provedor.')
heading('5. Metodologias de precificação e respostas produzidas')
heading('5.1 AVM experimental do alvo de oferta',2)
para('Quando a requisi\u00e7\u00e3o cont\u00e9m valor_oferta_brl positivo, a API devolve diretamente 0,90 x oferta, arredondado a centavos por regra ROUND_HALF_UP. Nesse modo o c\u00e1lculo n\u00e3o passa pelo modelo; a resposta marca status calculado e metodologia de oferta x 0,9. Quando a oferta \u00e9 omitida, o fluxo usa o pacote AVM carregado, com CatBoost (catboost_depth_4) como padr\u00e3o atual configurado. O alvo de treino documentado \u00e9 0,90 x pre\u00e7o pedido no an\u00fancio e a resposta continua experimental. Nenhum dos modos converte oferta em transa\u00e7\u00e3o ou avalia\u00e7\u00e3o CAIXA.')
para('POST /predict e POST /predict/batch devolvem JSON com estimativa_alvo_brl e metodologia, al\u00e9m de status/modelo/algoritmo quando aplic\u00e1veis. POST /predict/workbook recebe uma lista manual no mesmo schema do lote e devolve XLSX no layout do teste, incluindo valor estimado, valor unit\u00e1rio calculado pela\u00a0\u00e1rea, metodologia e observa\u00e7\u00f5es. A rota n\u00e3o altera o modelo nem o alvo.')
table(['Entrada AVM','Obrigatoriedade e validação'],[
('valor_oferta_brl','Opcional; se informado, deve ser positivo e aciona o cálculo direto de 90% da oferta.'),
('area_privativa_m2','Obrigatória para AVM sem oferta; 35 a 1.000 m².'),('idade_anos','Obrigatória para AVM sem oferta; inteiro entre 0 e 20.'),
('quartos, banheiros, vagas','Opcionais; inteiros entre 0 e 10.'),('elevador','Opcional; inteiro 0/1.'),
('area_total_m2','Opcional; maior que 0 e até 2.000 m².'),('latitude/longitude','Opcionais; limites geográficos válidos.'),
('renda_mediana_mensal_brl / renda_media_mensal_brl','Opcionais; valores positivos.'),
('cep, regiao, distrito, setor_censitario, padrao_iptu','Opcionais; CEP de 5 ou 8 dígitos após normalização; demais campos textuais limitados pelo schema.')])
para('Para escolher outro bundle, as rotas de previsão aceitam o parâmetro de consulta modelo com random_forest, catboost ou xgboost, desde que o artefato correspondente esteja carregado. O schema rejeita propriedades não reconhecidas (extra=forbid). A API aplica validação estrutural, mas os valores opcionais e sua proveniência precisam ser conferidos no processo que prepara a entrada.')
heading('5.2 Comparador experimental de transações ITBI',2)
para('POST /referencia/estimativa usa valor declarado de compra e venda no ITBI, não valor fiscal, oferta ou avaliação. Requer area_construida_iptu_m2 (15 a 1.000 m²) e confirmar_area_iptu=true; CEP e código de padrão IPTU (20 a 25) são opcionais. A área é a Área Construída cadastral IPTU, não deve ser substituída pela área privativa. A estimativa é área × mediana observada de R$/m²; segmenta por CEP + padrão quando há suporte mínimo de 30 comparáveis, com fallback para perfil de padrão/CEP e, por fim, perfil municipal. Retorna suporte, período, referência temporal e faixa observada P10–P90; essa faixa não é intervalo de confiança individual.')
heading('5.3 Simulação exploratória com a base CAIXA',2)
para('POST /avaliacao/simulacao-exploratoria recebe area_privativa_m2 (10 a 2.000 m²) e calcula área × mediana de valor de avaliação por m² do recorte de imóveis retomados elegíveis. Retorna também P10/P90, contagem de registros candidatos, bairros e datas de coleta. A auditoria indica ausência de data-base de avaliação; a rota informa operational_prediction_enabled=false e qualifica o cálculo como simulação, não avaliação profissional ou preço de mercado validado.')
heading('5.4 O que a interface acrescenta ao arquivo Excel',2)
para('No fluxo de upload, o navegador transforma os dados da planilha no schema do AVM, chama /predict/batch em lotes de at\u00e9 500 im\u00f3veis e combina a resposta com a linha original. O valor unit\u00e1rio\u00a0\u00e9 estimativa dividida pela\u00a0\u00e1rea privativa reconhecida. A interface inclui metodologia e observa\u00e7\u00f5es; erros de valida\u00e7\u00e3o permanecem explicados no arquivo. POST /predict/workbook tamb\u00e9m permite entrada manual pelo Swagger /docs e devolve o XLSX padronizado do teste; /predict e /predict/batch preservam suas respostas JSON.')
heading('6. API REST: contrato e comportamento observado')
para('A aplicação usa FastAPI, declara versão 1.0.0 e expõe documentação interativa em /docs e schema OpenAPI em /openapi.json. O prefixo local usado na verificação foi http://127.0.0.1:8001. No deploy, a URL deve ser substituída pela URL pública HTTPS do backend.')
table(['Método e rota','Função','Comportamento/limite'],[
('GET /','Health check','Informa status, modelo carregado, disponibilidade experimental e aprovação operacional (false).'),
('POST /predict','Cálculo direto ou AVM individual','Com valor_oferta_brl positivo calcula 90% diretamente; sem oferta usa o AVM experimental.'),
('POST /predict/workbook','Entrada manual e arquivo XLSX','Mesmo schema do lote; devolve XLSX com 26 colunas do teste e quatro saidas nas posicoes finais W-Z.'),
('POST /predict/batch','Cálculo direto ou AVM em lote','Lista de 1 a 500; cada item escolhe cálculo direto se tiver oferta ou AVM se não tiver.'),
('POST /referencia/estimativa','Comparador ITBI','Requer confirmação explícita de Área Construída IPTU; responde faixa observada e suporte.'),
('POST /avaliacao/simulacao-exploratoria','Simulação CAIXA exploratória','Estimativa matemática por mediana e P10/P90; não habilita previsão operacional.'),
('GET /modelo/info','Estado do modelo e validações','Relata artefatos, métricas, auditorias e bloqueios; status de validação suspenso.'),
('GET /avaliacao/auditoria','Auditoria de rótulos','Expõe a triagem do CSV de avaliações.'),
('GET /avaliacao/validacao-caixa','Auditoria do lote CAIXA','Expõe cobertura, qualidade e validações exploratórias.'),
('GET /dados/catalogo','Catálogo de fontes','Retorna JSON do catálogo; pode responder 503 se o artefato não existir.'),
('GET /regioes/stats','Estatísticas regionais','Suspensa; responde HTTP 503 até validação.'),
('POST /relatorio','Geração de relatório','Suspensa; responde HTTP 503 até validação.'),
('POST /avm/imports','Abre importação','Registra nome de arquivo, modelo, total de linhas e status processing; total até 50.000.'),
('POST /avm/imports/{id}/rows','Salva linhas','Até 500 por chamada; registra dados de origem, previsão/status e erro.'),
('PATCH /avm/imports/{id}','Finaliza importação','Status completed ou failed e mensagem de erro opcional.'),
('GET /avm/imports','Lista importações','Até 100; informa contagens e backend de banco detectado.'),
('GET /avm/imports/{id}/rows','Consulta linhas','Paginação de até 500 linhas.'),
('DELETE /avm/imports/{id}','Exclui importação','Remove o registro e linhas associadas.'),
('GET /docs e /openapi.json','Documentação automática','Contrato OpenAPI publicado pelo FastAPI.')])
heading('6.1 Formato de resposta e erros',2)
para('Exemplo verificado após o ajuste: POST /predict com valor_oferta_brl=R$ 500.000,00 retornou status=calculado, metodologia “Valor de oferta informado × 0,9” e estimativa_alvo_brl=R$ 450.000,00. Em lote misto, item com oferta de R$ 150.000,00 retornou R$ 135.000,00 por cálculo direto; item sem oferta foi encaminhado ao modelo xgboost_depth_6 e retornou R$ 560.795,29 para os atributos sintéticos usados. A resposta mantém o aviso de que não é avaliação CAIXA.')
para('O FastAPI retorna erros de validação (normalmente HTTP 422), erro de bundle/artefato indisponível (HTTP 503), importação inexistente (HTTP 404) e conflitos de gravação (HTTP 409). Os limites de lote e esquema fazem parte do contrato. Não há garantia de valor quando os dados não passam validação ou o modelo/artefato não carrega.')
heading('6.2 Persistência e configuração da API',2)
para('O armazenamento de importações mantém metadados em avm_imports (arquivo, modelo, status, total/processadas/previstas/com erro e datas) e linhas em avm_import_rows (número de origem, JSON de entrada, previsão, status e erro). A implementação seleciona PostgreSQL se AVM_DATABASE_URL estiver definida e o driver psycopg estiver instalado; caso contrário, usa SQLite em dados/avm_uploads.sqlite3. A execução da base 30.10.2026 registrada no projeto usou SQLite local; PostgreSQL de produção permanece pendente de conexão e homologação.')
para('AVM_CORS_ORIGINS configura origens permitidas; o valor padrão no código é *. Não foi encontrado middleware de autenticação/autorização ou exigência de token nas rotas inspecionadas. Antes de exposição pública, restringir origens, proteger os endpoints de importação/consulta/exclusão com controle de acesso, gerir segredos no provedor e revisar logs, retenção, TLS, backups e privacidade. A configuração atual não deve ser tomada como evidência de segurança de produção.')
heading('6.3 Verificação local efetuada em 9/11/2026',2)
para('A API iniciada com o código atualizado respondeu a POST /predict e POST /predict/batch; o cálculo direto retornou exatamente 90% da oferta, incluindo lote misto com uma linha encaminhada ao modelo. O pacote AVM carregou xgboost_depth_6 no ensaio. A validação confirma a lógica das rotas, mas não valida a interface de upload no navegador, o deploy remoto, PostgreSQL nem a adequação do valor a um imóvel real.')
heading('6.4 Atualizacao da API e pacote em 11/11/2026',2)
para('Foi adicionada POST /predict/workbook para receber manualmente uma lista JSON com o mesmo schema de /predict/batch e devolver um arquivo .xlsx. A aba teste reproduz os 26 cabe\u00e7alhos do arquivo de refer\u00eancia; Valor estimado (R$), Valor unit\u00e1rio (R$/m\u00b2), Metodologia e Observa\u00e7\u00f5es ficam nas quatro posi\u00e7\u00f5es finais (W\u2013Z). Dados ausentes permanecem vazios. A coluna AVALIA\u00c7\u00c3O n\u00e3o\u00a0\u00e9 aceita como vari\u00e1vel do modelo.')
para('A rota chama a mesma rotina de previs\u00e3o em lote. AVM_DEFAULT_MODEL configura CatBoost como padr\u00e3o da API; os tr\u00eas artefatos continuam dispon\u00edveis para sele\u00e7\u00e3o. Uma oferta positiva aciona o c\u00e1lculo direto de 90% da oferta. O upload autom\u00e1tico continua preservando a planilha de origem e preenchendo as colunas de sa\u00edda reconhecidas.')
para('main.py e deploy/api/main.py foram sincronizados, e as instru\u00e7\u00f5es do pacote passaram a documentar a nova rota. A sintaxe Python foi verificada. A nova rota ainda n\u00e3o foi chamada end-to-end; n\u00e3o houve teste em navegador nem publica\u00e7\u00e3o remota nesta atualiza\u00e7\u00e3o.')
heading('7. Conferência dos PDFs e aderência do conteúdo')
table(['Tema solicitado nos PDFs','Situação identificada','Pendência para versão oficial'],[
('Identificação, controle de versão, vigência, empresa e responsáveis','Parcial: data/versão do projeto podem ser informadas; dados empresariais e assinaturas não estão no código.','Completar razão social/CNPJ/contrato, versão aprovada, vigência e qualificações/assinaturas dos quatro responsáveis.'),
('Origem, natureza e composição dos dados','Parcial: alvo oferta proxy documentado no artefato; comparador ITBI tem artefato separado.','Registrar autorização/licença, período, corte, cobertura, representatividade, hash e população da versão exata.'),
('Variáveis, localização e campos obrigatórios','Parcial: features constam no artefato; origem de alguns atributos enriquecidos não está comprovada.','Documentar dicionário, definição/unidade, fonte, cobertura validada, método geográfico e tratamento de ausências.'),
('Saneamento, outliers, ausências, leakage e exclusões','Parcial: há regras de validação e exclusões de colunas; o pipeline de upload tem filtros de elegibilidade.','Consolidar contagens por regra na mesma versão de entrada; registrar outliers, deduplicação, origem e revisão técnica.'),
('Transformações, codificação, normalização e seleção','Parcial: algoritmo/parâmetros e features estão no relatório do artefato.','Documentar pipeline completo e versões/licenças congeladas para o ambiente que será publicado.'),
('Treino, validação, teste e métricas','Evidência experimental em partições de oferta e backtest ITBI independente, com alvos distintos.','Declarar população e regras de split; ampliar validação de representatividade e não atribuir métricas ao alvo de avaliação.'),
('IUP/IBAPE e critérios de avaliação','PDF do IUP é referência de apartamentos/escritórios na RMSP; respostas objetivas alertam para confirmação formal de interpretações.','Não afirmar implementação/homologação do IUP; documentar decisão, tipologia, limites de uso e validação profissional.'),
('Segurança, infraestrutura, IA de matrícula e monitoramento','Não comprovados pelo repositório; não foi localizada implementação de leitura de matrícula.','Preencher controles e evidências empresariais; definir solução de IA, validação, exceções, guarda, segurança e monitoramento, ou registrar não implementação.'),
('Reprodutibilidade, logs, atualização e relatório por versão','Há scripts, artefatos JSON, API e registro de importação local.','Estabelecer retenção/backup, logs protegidos, hash/versão, seed, ambiente replicável, restauração e processo de novo relatório.'),
('Saída auditável por imóvel','Interface propõe valor, valor unitário, metodologia e observações.','O PDF também menciona dados identificadores e informações para relatório de precificação individual; confirmar schema completo e autorização do fluxo.')])
heading('8. Conferência específica do IUP/IBAPE-SP')
para('O PDF IUP 2019 afirma que os índices apoiam a comparação de padrões construtivos de apartamentos e escritórios na Região Metropolitana de São Paulo e podem compor proxy/código ajustado no Método Comparativo Direto, inclusive tratamento científico. O próprio documento limita o uso: não equivale a multiplicador simples de valor unitário; no tratamento por fatores, os efeitos devem incidir sobre parcela de benfeitoria e ser validados; não recomenda misturar apartamentos e escritórios na mesma amostra.')
para('As respostas objetivas anexas registram questões a confirmar (intervalos/tabelas, padrões divergentes, vida útil/depreciação, idade estimada, vagas, localização e responsabilidade técnica). Essas respostas não são, por si, fonte oficial do IBAPE ou da CAIXA. O código analisado não demonstra adoção do IUP/Ross-Heidecke no fluxo de previsão de planilha. Portanto, o relatório registra a referência e os limites, sem dizer que ela foi incorporada ao algoritmo.')
heading('9. Preparação para deploy')
table(['Componente','Estado nesta entrega','Configuração necessária no destino'],[
('Escopo do servi\u00e7o','API somente em deploy/api; a interface\u00a0\u00e9 hospedada\u00a0\u00e0 parte se necess\u00e1rio.','Configurar URL HTTPS da API e CORS para o cliente/frontend.'),
('Backend','deploy/api/main.py sincronizado com main.py; rota manual de XLSX documentada.','Definir DATABASE_URL PostgreSQL/Supabase, CORS, secrets e depend\u00eancias/modelos.'),
('Banco','API suporta armazenamento configurável; ensaio observado foi SQLite local.','Conectar e testar PostgreSQL real; conferir persistência, migrações, permissões, backup e restauração.'),
('Pacote','Pacote somente API em deploy/api atualizado com rota e documentacao.','Executar smoke test e teste de importacao em homologacao antes de publicar.')])
para('Status de publica\u00e7\u00e3o: pacote local preparado, n\u00e3o publicado. A conex\u00e3o PostgreSQL/Supabase e a URL p\u00fablica ainda precisam de configura\u00e7\u00e3o e valida\u00e7\u00e3o no provedor.')
heading('10. Pendências prioritárias antes de uso ou apresentação oficial')
for t in [
'Reconciliar a contagem de elegibilidade entre o run da base (11.052 previstas) e metadados do treino (11.055 candidatas), preservando hash e versão da planilha.',
'Executar teste em navegador para upload e POST /predict/workbook; conferir preserva\u00e7\u00e3o da planilha, 26 cabe\u00e7alhos, quatro colunas finais e download XLSX.',
'Executar homologação contra PostgreSQL e URL/CORS de produção; confirmar que segredos não estão no frontend nem no pacote.',
'Completar os requisitos do roteiro PDF: origem autorizada, qualidade/representatividade, variáveis, transformações, ambientes, segurança, IA de matrícula, monitoramento e recuperação.',
'Confirmar oficialmente edital/TR/retificações e interpretações do IUP; separar respostas recebidas informalmente de requisito comprovado.',
'Obter amostra de avaliações com rótulos autorizados e validação independente se a finalidade pretendida for avaliação; o alvo de oferta proxy e ITBI não são equivalentes.',
'Completar identificação empresarial e quatro responsáveis; revisão técnica e jurídica; assinatura digital e conversão ao formato PDF/A requerido pelo documento oficial.'
]: bullet(t)
heading('11. Conclusão')
para('Os ajustes documentados implementam previs\u00e3o por entrada manual ou planilha e gera\u00e7\u00e3o de XLSX com quatro campos finais. Com oferta positiva, o valor\u00a0\u00e9 o c\u00e1lculo direto de 90% da oferta; sem oferta, usa-se o AVM experimental quando os atributos obrigat\u00f3rios est\u00e3o v\u00e1lidos. POST /predict/workbook entrega as 26 colunas do modelo de teste, com as quatro sa\u00eddas nas posi\u00e7\u00f5es W\u2013Z. O escopo de deploy permanece API-only em deploy/api.')
para('A evidência disponível sustenta um protótipo técnico experimental. Não sustenta afirmar que o sistema está homologado, pronto para avaliação CAIXA, que o deploy já foi publicado, que PostgreSQL já foi validado, que a interface foi testada após os ajustes ou que os requisitos organizacionais dos PDFs estão atendidos. A versão oficial exige revisão, evidências empresariais, responsáveis e assinaturas.')
heading('Referências internas')
for f in ['dados/relatorio_Modelo_precificacao+202610011034.pdf','dados/respostas_objetivas_IUP_IBAPE.pdf','dados/Padrão Construtivo - FOTOS e características das Edificações - IBAPE SP .pdf','docs/avaliacao_conformidade_caixa.md','docs/relatorio_modelo_caixa_rascunho.md','models/offer_avm/avm_report.json','models/itbi_transaction_experiment.json','scripts/process_system_base.py','scripts/process_comparison_workbook.py','scripts/package_deploy.py']:
    bullet(f)

# DOCX package (WordprocessingML)
xml_body=''.join(body)+'<w:sectPr><w:pgSz w:w="12240" w:h="15840"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134"/></w:sectPr>'
document=f'''<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><w:body>{xml_body}</w:body></w:document>'''
styles='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:sz w:val="20"/></w:rPr></w:rPrDefault><w:pPrDefault><w:pPr><w:spacing w:after="120" w:line="276" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults><w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:rPr><w:rFonts w:ascii="Aptos" w:hAnsi="Aptos"/><w:sz w:val="20"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:pPr><w:spacing w:before="2400" w:after="240"/></w:pPr><w:rPr><w:b/><w:color w:val="17365D"/><w:sz w:val="36"/><w:rFonts w:ascii="Aptos Display" w:hAnsi="Aptos Display"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Subtitle"><w:name w:val="Subtitle"/><w:rPr><w:color w:val="4472C4"/><w:sz w:val="26"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="320" w:after="120"/></w:pPr><w:rPr><w:b/><w:color w:val="17365D"/><w:sz w:val="28"/></w:rPr></w:style><w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/><w:pPr><w:keepNext/><w:spacing w:before="220" w:after="80"/></w:pPr><w:rPr><w:b/><w:color w:val="2F5597"/><w:sz w:val="23"/></w:rPr></w:style></w:styles>'''
content_types='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/><Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/></Types>'''
rels='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/></Relationships>'''
docrels='''<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/></Relationships>'''
with ZipFile(OUT,'w',ZIP_DEFLATED) as z:
 z.writestr('[Content_Types].xml',content_types)
 z.writestr('_rels/.rels',rels)
 z.writestr('word/document.xml',document)
 z.writestr('word/styles.xml',styles)
 z.writestr('word/_rels/document.xml.rels',docrels)
print(OUT)
