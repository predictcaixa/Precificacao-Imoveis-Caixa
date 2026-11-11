# Busca de fontes de avaliações imobiliárias — Estado de São Paulo

**Data da verificação:** 25/10/2026  
**Objetivo:** encontrar registros de avaliações individuais de valor de mercado que possam, mediante autorização e validação, alimentar o alvo de avaliação escolhido para apartamentos em São Paulo.  
**Conclusão:** nas consultas realizadas não foi localizada uma base aberta estruturada com rótulos de avaliações individuais de apartamentos pronta para treinamento. Isso não prova que avaliações avulsas não estejam publicadas em processos ou portais; significa que ainda não há uma fonte identificada que entregue uma amostra adequada, licenciada e representativa.

## Fontes e resultados da verificação

| Fonte consultada | Resultado observado | Uso possível | Decisão para o AVM |
|---|---|---|---|
| [Portal de Dados Abertos do Estado de SP — busca por “avaliação imóvel”](https://dadosabertos.sp.gov.br/api/3/action/package_search?q=avalia%C3%A7%C3%A3o%20im%C3%B3vel) | A busca CKAN retornou 0 conjuntos para a expressão pesquisada. | Busca exploratória, sujeita a termos e indexação do catálogo. | Não fornece rótulos; repetir consultas com termos/órgãos diferentes se necessário. |
| [Portal de Dados Abertos do Estado de SP — busca por “laudo avaliação”](https://dadosabertos.sp.gov.br/api/3/action/package_search?q=laudo%20avalia%C3%A7%C3%A3o) | A busca CKAN retornou 0 conjuntos para a expressão pesquisada. | Busca exploratória, não prova inexistência de documentos avulsos. | Sem base de treino identificada. |
| [Portal de Dados Abertos da Prefeitura de São Paulo — busca por “laudo imóvel”](https://dados.prefeitura.sp.gov.br/api/3/action/package_search?q=laudo%20imovel) | A busca CKAN retornou 0 conjuntos. | Busca exploratória. | Sem base de treino identificada. |
| [Conjunto “Desapropriação — DER/SP”](https://dadosabertos.sp.gov.br/dataset/desapropriacao-der-sp) | Licença do catálogo: CC BY 4.0. O XLSX oficial tem 3.094 registros e 17 colunas; cabeçalho contém município, cartório, títulos de propriedade, áreas, anuência, condução/status, data de imissão, decreto e empreendimento. **Não há coluna de valor, preço ou avaliação.** | Pode apoiar estudo de áreas, locais/empreendimentos e procedimentos de desapropriação, sujeito à finalidade e à revisão dos dados. | **Não é rótulo de valor de avaliação** e não deve entrar no treino. A natureza de desapropriação/rodovia e a ausência de preço impedem tratá-lo como comparável direto de apartamento residencial. Não copiar títulos ou dados identificáveis para o AVM. |
| [Portal de imóveis à venda da CAIXA](https://venda-imoveis.caixa.gov.br/sistema/busca-imovel.asp) | Página de busca de imóveis; acesso automatizado retornou proteção anti-bot. Não foi confirmada uma exportação aberta com avaliações e documentos. | Inspeção manual de registros, caso a página indique explicitamente valor de avaliação, método/data/documento e condições de uso. | Não extrair em massa nem contornar proteção. Valor mínimo, preço de venda e lance não são automaticamente valor de avaliação. Leilões têm viés de seleção. |
| [Índice FipeZAP](https://www.fipe.org.br/pt-br/indices/fipezap/) | A Fipe descreve índice calculado com amostras de anúncios dos portais do Grupo OLX. | Contexto de tendência de preço de oferta. | Índice agregado baseado em anúncios; não é avaliação individual e não preenche o alvo. |

### O que a amostra pública do DER de fato contém

A planilha foi baixada do link XLSX divulgado pelo catálogo oficial e inspecionada somente quanto a nomes de abas, quantidade de linhas e cabeçalhos, sem exportar dados individuais. A aba principal tem 3.094 linhas de dados; suas 17 colunas não incluem valor de indenização, valor de mercado, valor de avaliação ou preço. Mesmo que documentos de processo de desapropriação associados tragam algum valor, seria preciso localizar e validar cada documento, distinguir valor proposto/ofertado/indenizado/decidido, confirmar licença/privacidade, finalidade e comparabilidade. Portanto, esse conjunto não resolve a lacuna de rótulos para apartamentos.

## Próximas fontes a solicitar formalmente

O caminho com maior probabilidade de produzir rótulos válidos é solicitar **dados históricos anonimizados à própria empresa, a parceiros avaliadores ou às entidades que elaboram avaliações**, mediante autorização escrita para desenvolvimento, teste, validação e auditoria. Perguntar às áreas competentes de órgãos públicos se existem relatórios de avaliação de imóveis urbanos, não apenas valores cadastrais ou de transação, nos seguintes contextos:

- avaliações patrimoniais de imóveis próprios/alienados por órgãos estaduais ou municipais;
- processos de aquisição, desapropriação e alienação, distinguindo avaliação inicial, proposta, acordo, valor homologado e pagamento final;
- avaliações judiciais disponíveis em processos públicos, observadas as regras de acesso, dados pessoais, finalidade e termos do Tribunal;
- avaliações anexas a editais/documentos de alienação da CAIXA, apenas caso o documento informe explicitamente valor de avaliação e seja autorizado para a finalidade de modelagem.

Um pedido de acesso à informação deve solicitar **documentos/dados existentes**. A Lei de Acesso à Informação não significa que o órgão tenha de criar um novo dataset ou produzir análises sob medida. Caso a informação contenha dados pessoais, pedir a versão já anonimizada ou a forma legalmente disponibilizável; não pedir CPF, nome de proprietário ou matrícula completa sem necessidade.

## Modelo de pedido de acesso à informação

> **Assunto: existência e acesso a avaliações de mercado de imóveis urbanos no Estado de São Paulo**
>
> Solicito informar se o órgão mantém base, planilha, relatório ou documentos já existentes com avaliações de valor de mercado de imóveis urbanos no Estado de São Paulo, especialmente apartamentos residenciais, realizadas no período de [informar período].
>
> Em caso positivo, solicito, se legalmente disponibilizável, versão anonimizada ou dados agregados por registro que preservem: identificador pseudonimizado; município e região/bairro quando permitidos; tipologia; data-base; finalidade da avaliação; método; natureza do valor (valor de mercado avaliado, valor fiscal, proposta, indenização, preço mínimo ou outro); valor em reais; tipo e definição da área; atributos do imóvel efetivamente observados; situação/revisão do laudo; e órgão responsável.
>
> Solicito também a referência do documento/laudo, base legal e licença ou condições de reutilização para pesquisa e desenvolvimento/validação de modelos estatísticos, incluindo eventuais restrições de redistribuição. Não solicito nomes, CPF, endereço completo, matrícula integral ou outros identificadores pessoais.
>
> Se não houver base estruturada, solicito indicar se existem relatórios já publicados ou canal oficial para consulta desses documentos. Não solicito que seja criada nova base nem que seja realizado estudo técnico novo.

Enviar pelo canal oficial de Acesso à Informação de cada órgão, registrando órgão destinatário, número do protocolo, data, resposta e condições de uso. Para a PMSP, endereçar ao órgão responsável por gestão patrimonial/avaliação; para o Estado, perguntar ao DER/SP, órgão patrimonial competente e Secretaria responsável. Conferir o canal oficial vigente no site institucional antes de enviar.

## Regras para aceitar um dado como rótulo

Um registro só pode ser considerado candidato a **valor de avaliação** quando houver evidência de que:

1. o documento contém avaliação concluída, não apenas anúncio, proposta, valor venal, preço mínimo de leilão ou valor pago;
2. o valor tem finalidade e data-base identificadas;
3. o imóvel é apartamento residencial dentro da abrangência, e a unidade foi associada sem ambiguidade;
4. a área e sua definição são explícitas;
5. método, status, responsável técnico e fonte documental podem ser revisados;
6. a autorização/licença permite uso no treino, validação e auditoria;
7. dados pessoais foram minimizados e a guarda dos documentos ocorre em ambiente autorizado.

O classificador do projeto pode registrar registros aprovados para revisão, mas não autentica documentos, decide legalidade, mede representatividade nem habilita treino. Usar `dados/derivados/avaliacoes_imoveis_template.csv`, revisar evidências e executar `python -B scripts\audit_evaluation_csv.py`. A autorização técnica para treinar continua uma decisão independente dos responsáveis.

## Fontes que permanecem separadas

- **ITBI/PMSP:** transações declaradas; útil para estudo comparativo de transações, não como rótulo de avaliação.
- **Anúncios:** preços pedidos; útil para um modelo de oferta separado, não como avaliação.
- **Valores fiscais:** valor venal/base de cálculo; não são avaliação de mercado individual.
- **Desapropriação/indenização:** processo e finalidade específicos; não misturar ao alvo de avaliação sem definição, comparabilidade, documentação e validação formal.

**Estado atual do projeto:** nenhuma avaliação individual autorizada foi incorporada; o template de avaliações e o template de ofertas permanecem vazios. Treinamento do alvo de avaliação continua bloqueado.
