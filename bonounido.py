# 📦 Importamos las bibliotecas necesarias:
import streamlit as st
import pandas as pd
import re
from PyPDF2 import PdfReader
from openpyxl import load_workbook
from openpyxl.styles import PatternFill
import tempfile

# 🎨 Configuración inicial
st.set_page_config(page_title="Comparador Bono Diferido 💲", layout="wide")
st.title("💲 Comparador de Datos Bono Diferido")

# 🧼 Función para limpiar valores
def limpiar(valor):
    return str(valor).replace(",", "").replace("\xa0", "").replace("\u200b", "").replace(" ", "").replace("%", "").strip()

# 🔍 Funciones específicas para cada idioma
def extraer_datos_es(texto):
    bono = re.search(r'asignado.*?([\d,.]+)', texto, re.IGNORECASE)
    factor = re.search(r'reportas.*?:\s*([\d]+)', texto, re.IGNORECASE)
    porcentaje = re.search(r'corresponden.*?:\s*([\d]+)', texto, re.IGNORECASE)
    salario = re.search(r'2024.*?:\s*([\d,]+(?:\.\d{2})?)', texto, re.IGNORECASE)
    if bono and factor and porcentaje and salario:
        return limpiar(bono.group(1)), limpiar(factor.group(1)), limpiar(porcentaje.group(1)), "{:.2f}".format(float(limpiar(salario.group(1))))
    return None

def extraer_nombre_es(texto):
    lineas = texto.splitlines()
    for i, linea in enumerate(lineas):
        if re.search(r'^Mayo\s+\d{4}$', linea.strip(), re.IGNORECASE):
            for j in range(i + 1, len(lineas)):
                siguiente = lineas[j].strip()
                if siguiente:
                    return siguiente
    return None

def extraer_datos_en(texto):
    bono = re.search(r'assigned\s+([\d,\.]+)', texto, re.IGNORECASE)
    factor = re.search(r'financial factor.*?(\d+)', texto, re.IGNORECASE)
    porcentaje = re.search(r'target bonus.*?(\d+(?:\.\d+)?)', texto, re.IGNORECASE)
    salario = re.search(r'December \d{4}.*?([\d,]+\.\d{2})', texto, re.IGNORECASE)
    if bono and factor and porcentaje and salario:
        return limpiar(bono.group(1)), limpiar(factor.group(1)), limpiar(porcentaje.group(1)), "{:.2f}".format(float(limpiar(salario.group(1))))
    return None

def extraer_nombre_en(texto):
    lineas = texto.splitlines()
    for i, linea in enumerate(lineas):
        normalizada = re.sub(r'\s+', '', linea.strip())
        if re.search(r'^May,\d{4}$', normalizada, re.IGNORECASE):
            for j in range(i + 1, len(lineas)):
                siguiente = lineas[j].strip()
                if siguiente:
                    return siguiente
    return None

# ✨ Comparación flexible
def comparar_valores(pdf_valor, csv_valor):
    pdf_valor = limpiar(pdf_valor)
    csv_valor = limpiar(csv_valor)
    try:
        return round(float(pdf_valor), 2) == round(float(csv_valor), 2)
    except ValueError:
        return pdf_valor == csv_valor

# 🧩 Función principal para comparar
def comparar(csv_file, pdf_files, columnas, extraer_nombre, extraer_datos):
    df = pd.read_csv(csv_file)
    if not all(col in df.columns for col in columnas):
        st.error(f"⚠️ El CSV debe tener las columnas: {columnas}")
        return

    df[columnas[1:]] = df[columnas[1:]].applymap(limpiar)
    df[columnas[0]] = df[columnas[0]].astype(str).str.upper().str.strip()

    errores_por_fila = {}
    comentarios = {}
    iconos_df = df.copy()
    iconos_df["ORIGEN PDF"] = ""
    notas = []
    procesados = []

    for file in pdf_files:
        reader = PdfReader(file)
        texto = ''.join(page.extract_text() for page in reader.pages if page.extract_text())
        if not texto.strip():
            continue

        nombre_pdf = extraer_nombre(texto)
        if not nombre_pdf:
            continue

        nombre_pdf = nombre_pdf.upper().strip()
        if nombre_pdf not in df[columnas[0]].values:
            continue

        idx = df[df[columnas[0]] == nombre_pdf].index[0]
        fila = df.loc[idx]
        datos = extraer_datos(texto)
        if not datos:
            continue

        errores = []
        for campo, extraido, esperado in zip(columnas[1:], datos, [fila[col] for col in columnas[1:]]):
            if not comparar_valores(extraido, esperado):
                errores.append(campo)
                comentarios[(idx, campo)] = f"{campo}: En el EXCEL: {esperado}// En el PDF: {extraido}"
                iconos_df.at[idx, campo] = f"❌ {fila[campo]}"
            else:
                iconos_df.at[idx, campo] = f"✅ {fila[campo]}"

        if errores:
            errores_por_fila[idx] = errores
        else:
            for campo in columnas[1:]:
                iconos_df.at[idx, campo] = f"✅ {fila[campo]}"

        iconos_df.at[idx, "ORIGEN PDF"] = file.name
        procesados.append(idx)

    for idx in iconos_df.index:
        fila_notas = [comentarios[(idx, col)] for col in iconos_df.columns if (idx, col) in comentarios]
        notas.append(" | ".join(fila_notas))
    iconos_df["NOTAS"] = notas

    def resaltar(row):
        idx = row.name
        return ['background-color: #FFCCCC' if col in errores_por_fila.get(idx, []) else ''
                for col in iconos_df.columns]

    iconos_filtrados = iconos_df.loc[procesados] if procesados else pd.DataFrame()
    st.subheader("📊 Resultados comparados")

    if not iconos_filtrados.empty:
        st.dataframe(iconos_filtrados.style.apply(resaltar, axis=1), use_container_width=True)
    else:
        st.warning("⚠️ No se encontraron coincidencias válidas entre los PDFs y los nombres del CSV.")

    if st.button("💾 Descargar Excel con errores marcados", key=f"descargar_{columnas[0]}"):
        if procesados:
            export_df = df.loc[procesados].copy()
            export_df["ORIGEN PDF"] = iconos_df.loc[procesados]["ORIGEN PDF"]
            export_df["NOTAS"] = iconos_df.loc[procesados]["NOTAS"]
            with tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False) as tmp:
                ruta_excel = tmp.name
                export_df.to_excel(ruta_excel, index=False)
                wb = load_workbook(ruta_excel)
                ws = wb.active
                red_fill = PatternFill(start_color="FF9999", end_color="FF9999", fill_type="solid")
                for idx in errores_por_fila:
                    excel_row = list(procesados).index(idx) + 2
                    for col in errores_por_fila[idx]:
                        col_idx = list(export_df.columns).index(col) + 1
                        ws.cell(row=excel_row, column=col_idx).fill = red_fill
                wb.save(ruta_excel)
            with open(ruta_excel, "rb") as f:
                st.download_button("📥 Descargar resultado_comparado.xlsx", f, file_name="resultado_comparado.xlsx")
        else:
            st.error("⚠️ No hay filas válidas para exportar.")

# 🗂️ Interfaz con pestañas
tab_es, tab_en = st.tabs(["🇪🇸 Bono Español", "🇺🇸 Bono Inglés"])

with tab_es:
    st.header("📂 Comparador Bono Diferido Español")
    csv_file_es = st.file_uploader("📂 Sube tu archivo CSV", type=["csv"], key="csv_es")
    pdf_files_es = st.file_uploader("📥 Sube tus PDFs", type=["pdf"], accept_multiple_files=True, key="pdf_es")
    if csv_file_es and pdf_files_es:
        columnas_es = ['NOMBRE', 'BONO DIFERIDO', 'FACTOR FINANCIERO', 'DIAS BONO', 'SALARIO DIARIO']
        comparar(csv_file_es, pdf_files_es, columnas_es, extraer_nombre_es, extraer_datos_es)

with tab_en:
    st.header("📂 Deferred Bonus Comparator (English)")
    csv_file_en = st.file_uploader("📂 Upload your CSV file", type=["csv"], key="csv_en")
    pdf_files_en = st.file_uploader("📥 Upload your PDF files", type=["pdf"], accept_multiple_files=True, key="pdf_en")
    if csv_file_en and pdf_files_en:
            columnas_en = ['NAME', 'DEFERRED BONUS', 'FINANCIAL FACTOR', 'TARGET BONUS', 'ANNUAL SALARY']
            comparar(csv_file_en, pdf_files_en, columnas_en, extraer_nombre_en, extraer_datos_en)
