import streamlit as st
import pdfplumber
import pandas as pd
from PIL import Image, ImageOps
import io
import os
import re

# Função para extrair informações do PDF
def extract_pdf_info(pdf_file):
    with pdfplumber.open(pdf_file) as pdf:
        data = {
            'Material': [],
            'Und.': [],
            'NCM': [],
            'Qtde.': [],
            'Total c/ IPI': []
        }

        for page in pdf.pages:
            tables = page.extract_tables()
            for table in tables:
                for row in table[0:]:  # Comece a partir da segunda linha para ignorar os cabeçalhos
                    material_cell = '-'.join(row[1:2])  # Usar espaço para separar os valores da célula 'Material'
                    material_cell = re.sub(r'\s+', ' ', material_cell.replace('\n', ' '))  # Usar expressão regular para remover espaços extras
                    if all(row[i].strip() for i in [2, 3, 4, 10]):  # Verifica se todas as colunas relevantes não estão vazias
                        data['Material'].append(material_cell)
                        data['Und.'].append(row[2])
                        data['NCM'].append(row[3])
                        data['Qtde.'].append(row[4])
                        data['Total c/ IPI'].append(row[10])

    return pd.DataFrame(data)


# Interface do Streamlit
st.title('EXTRATOR DE DADOS')





def adicionar_contorno_imagem(nome_imagem, borda=10, cor_borda=(0, 0, 0), pasta_imagens='static/images'):
    """
    Adiciona um contorno a uma imagem.

    :param nome_imagem: Nome da imagem dentro do diretório especificado.
    :param borda: Largura da borda em pixels.
    :param cor_borda: Cor da borda em RGB.
    :param pasta_imagens: Caminho relativo ao diretório onde as imagens estão armazenadas.
    :return: Objeto Image com a borda.
    """
    # Constrói o caminho relativo para a imagem
    caminho_imagem = os.path.join(pasta_imagens, nome_imagem)

    # Carrega a imagem
    imagem = Image.open(caminho_imagem)

    # Adiciona a borda
    imagem_com_contorno = ImageOps.expand(imagem, border=borda, fill=cor_borda)

    return imagem_com_contorno

# Nome da sua imagem (mantenha suas imagens dentro de static/images ou um diretório similar)
nome_imagem = "Capturar.PNG"

# Adiciona o contorno à imagem
imagem_com_contorno = adicionar_contorno_imagem(nome_imagem, cor_borda='white')

# Exibe a imagem no Streamlit
st.image(imagem_com_contorno)



# aquii

uploaded_file = st.file_uploader('Faça o upload do seu arquivo PDF', type=['pdf'])

if uploaded_file is not None:
    pdf_data = extract_pdf_info(uploaded_file)

    st.subheader('Informações extraídas:')
    st.write(pdf_data)

    st.subheader('Download do arquivo EXCEL:')
    excel_data = io.BytesIO()
    with pd.ExcelWriter(excel_data, engine='xlsxwriter') as writer:
        pdf_data.to_excel(writer, sheet_name='informacoes_extraidas', index=False)

    st.download_button(
        label='Clique para baixar',
        data=excel_data.getvalue(),
        file_name='informacoes_extraidas.xlsx',
        key='excel_button'
    )
