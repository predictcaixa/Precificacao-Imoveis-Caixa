# Levantamento de dúvidas — Sistema de Precificação de Imóveis
**Base:** "Índice – Unidades Padronizadas" (IBAPE/SP, 2019) · **Assunto:** aderência do sistema às exigências da Caixa

> Contexto: o estudo trata apenas de **Apartamentos** e **Escritórios** (18 padrões) na Região Metropolitana de São Paulo. Os índices (IUP) são números puros, para uso como variável proxy no Método Comparativo Direto. Nosso sistema hoje usa regressão Ridge e um dataset de referência próprio.

## A. Enquadramento normativo e escopo

1. **A Caixa exige ou aceita o IUP/IBAPE-SP 2019 como referência?** Existe norma interna, manual ou versão mais recente (a edição é de 2019) que devamos seguir?
2. **Qual o método de avaliação exigido?** O estudo só serve ao Método Comparativo Direto (itens 3.1 e 3.3.4 vedam o Evolutivo). Um preço estimado por Machine Learning é aceito, ou o resultado precisa vir de tratamento por fatores / tratamento científico (regressão com variáveis inferenciais)?
3. **Qual o grau de fundamentação/precisão exigido (NBR 14653)?** O item 3.1.4 remete ao item 10.6.4 da Norma IBAPE/SP 2011 para validar o efeito homogeneizante. Esse procedimento é obrigatório no nosso caso?
4. **O sistema deve cobrir só Apartamentos e Escritórios?** O estudo não traz Casas, Terrenos, Galpões etc. (esses estão no VEIU/2017). Quais tipologias a Caixa quer no escopo?
5. **A Caixa atua fora de São Paulo.** Os índices foram calculados com eventos de mercado da Região Metropolitana de SP (2015–2018). Podem ser usados em outras cidades? Existe estudo equivalente local ou fator de ajuste regional?

## B. Uso dos índices

6. **Qual valor usar dentro do intervalo (mínimo / médio / máximo)?** O estudo não diz como escolher. Usamos sempre o médio, ou o avaliador escolhe com justificativa?
7. **Como o IUP entra no cálculo?** O item 3.1.3 manda aplicar IUP e Foc "exclusivamente sobre a parcela de capital da benfeitoria", no elemento de pesquisa e no imóvel avaliado. Qual a fórmula do fator de homogeneização que a Caixa espera (ex.: razão entre IUP·Foc do avaliando e do elemento)?
8. **Como separar terreno e construção?** O Apêndice (item 8) cita percentuais de terreno baseados no estudo de TIR do IBAPE/SP 2017, mas não os apresenta. Onde obtê-los?
9. **Podemos usar IUP × CUB para estimar o valor da benfeitoria?** O Apêndice (Quadro A3/A4/A5) mostra que IUP = valor da benfeitoria nova ÷ CUB R8-N (SINDUSCON-SP), mas o texto proíbe tratar o IUP como múltiplo de valor unitário. Essa conta é permitida como conferência?
10. **Vagas de garagem:** o item 3.3.3 diz que os índices já contemplam a vaga "recorrente" do padrão. Como tratar unidades com mais ou menos vagas que o típico do padrão?

## C. Classificação de padrão e depreciação

11. **Quem define o padrão construtivo e como o sistema deve capturar isso?** Os critérios são qualitativos (acabamentos, hall, elevadores). Devemos usar seleção manual pelo avaliador, checklist ou classificação automática?
12. **Possíveis incoerências entre descrição e tabela de índices:**
    - Apartamento Padrão Médio e Superior descrevem edifícios "dotados de elevadores", porém existem índices "Sem elevador". Qual o critério de enquadramento?
    - Em Padrão Econômico/Simples de Escritório, a descrição diz "sem elevador", mas há índice "Com elevador" para o Simples.
13. **Ie (idade estimada):** o item 3.2.5 pede ponderar arquitetura, funcionalidade e materiais. A Caixa fornece critério objetivo ou fica a cargo do avaliador? Aceita limite Ie ≤ idade real (item 3.2.6)?
14. **Estado de conservação:** os estados A–H têm descrição textual extensa. A Caixa possui checklist de vistoria padronizado? Como tratar o estado I (ruína, Ec = 100%)? A Tabela 2 só vai até H.
15. **Tabela 2 vs. fórmula:** a tabela usa passos de 2% de Ie/Ir. Devemos calcular pela fórmula (valor contínuo) ou interpolar/arredondar para a linha da tabela? Os valores diferem na 4ª casa.
16. **Ie/Ir > 100%:** o estudo não prevê. Mantemos o piso do Foc em R = 20% (K = 0)?

## D. Inconsistências encontradas no documento (para confirmar com o IBAPE/SP ou a Caixa)

17. **Padrão Simples, Apto sem elevador, valor máximo:** 3,837 na pág. 17 × 3,827 na Tabela 5 e no Quadro A6 (pág. 29 e 37). Qual vale? *(o sistema usa 3,827, conforme a tabela-resumo.)*
18. **Padrão Superior, Apto com elevador, máximo = 7,089**, abaixo de médio + 10% (7,510), por ajuste para não sobrepor o Padrão Fino (mín. 7,090). Confirmar se é intencional.
19. **Escritório Padrão Luxo não tem valor máximo** ("–"). Como limitar o intervalo?
20. **Rotulagem:** o sumário chama a seção V de "Tabela de Coeficientes", mas o conteúdo é "Tabela de Índices"; a Tabela 2 cita "Equação 1" quando calcula K (Equação 2). Há errata?
21. **Amostra:** 1.199 elementos após saneamento (±30%). Os dados-base são acessíveis para auditoria ou atualização? Há previsão de nova edição com CUB mais recente?

## E. Dados e operação do sistema

22. **Fonte dos elementos comparáveis:** quais bases a Caixa autoriza (próprias, ITBI, anúncios, laudos anteriores)? Hoje nosso dataset é de referência e pequeno.
23. **Regiões:** nosso sistema usa Centro/Leste/Oeste/Norte/Sul. A Caixa define zonas ou bairros-padrão? O estudo cita bairros (ex.: Itaim Bibi, Mooca, Tatuapé) como referência de pesquisa por padrão.
24. **Saída esperada:** valor pontual, intervalo (hoje ±10%), memória de cálculo, relatório em formato específico (laudo)? Quais campos são obrigatórios?
25. **Responsabilidade técnica:** o resultado precisa de ART/RRT ou assinatura de engenheiro avaliador? O sistema será ferramenta de apoio ou emissor do valor final?
