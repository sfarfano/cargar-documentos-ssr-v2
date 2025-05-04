import streamlit as st
import pandas as pd
import os
import zipfile
from datetime import datetime
import tempfile
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
import json
import unicodedata

# ---------------------- CONFIGURACIÓN DRIVE ----------------------
DRIVE_FOLDER_ID = '1ilGOnX3CrZUcBfzpCXBeZwAvXRmnFJ-O'
LOG_FILE = "registro_subidas.csv"

# Leer credenciales desde st.secrets
service_account_info = json.loads(st.secrets["GOOGLE_SERVICE_ACCOUNT_JSON"])
credentials = service_account.Credentials.from_service_account_info(
    service_account_info,
    scopes=["https://www.googleapis.com/auth/drive"]
)
drive_service = build('drive', 'v3', credentials=credentials)

# ---------------------- FUNCIONES ÚTILES ----------------------
def normalizar(texto):
    return unicodedata.normalize('NFKD', texto.strip().lower()).encode('ascii', 'ignore').decode('utf-8')

def buscar_carpeta_por_codigo(codigo, id_padre):
    codigo_normalizado = normalizar(codigo)
    query = f"'{id_padre}' in parents and trashed = false"
    resultados = drive_service.files().list(q=query, fields="files(id, name, mimeType)").execute().get("files", [])
    st.markdown("### 📂 Carpetas encontradas:")
    for archivo in resultados:
        if archivo["mimeType"] == "application/vnd.google-apps.folder":
            st.markdown(f"- `{archivo['name']}`")
            nombre_drive = normalizar(archivo["name"])
            if nombre_drive.startswith(codigo_normalizado):
                return archivo["id"]
    return None

def listar_subcarpetas_y_archivos(id_padre):
    query = f"'{id_padre}' in parents and trashed = false"
    resultados = drive_service.files().list(q=query, fields="files(id, name, mimeType, webViewLink)").execute().get("files", [])
    carpetas = [f for f in resultados if f["mimeType"] == "application/vnd.google-apps.folder"]
    archivos = [f for f in resultados if f["mimeType"] != "application/vnd.google-apps.folder"]
    return carpetas, archivos

def subir_archivo_a_drive(archivo, nombre_archivo, id_carpeta):
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(archivo.getbuffer())
        tmp_path = tmp.name
    media = MediaFileUpload(tmp_path, resumable=True)
    metadata = {'name': nombre_archivo, 'parents': [id_carpeta]}
    drive_service.files().create(body=metadata, media_body=media, fields='id').execute()
    os.remove(tmp_path)

# ---------------------- INTERFAZ STREAMLIT ----------------------
st.set_page_config(layout="wide")

archivo_ssr = "listado_ssr_nombre_real.xlsx"
df = pd.read_excel(archivo_ssr)
df["Nombre combinado"] = df["Carpeta SSR"] + " - " + df["Nombre del sistema"]

modo = st.sidebar.radio("Selecciona una vista:", ["📤 Cargar documentos", "📚 Lector de documentos"])

if modo == "📤 Cargar documentos":
    st.header("📤 Cargar documentos SSR")

    busqueda = st.text_input("🔎 Buscar sistema SSR:")
    opciones = df[df["Nombre combinado"].str.lower().apply(lambda x: all(p in x for p in busqueda.lower().split()))] if busqueda else df
    seleccionado = st.selectbox("Selecciona sistema SSR:", opciones["Nombre combinado"].tolist())

    carpeta_codigo = seleccionado.split(" - ")[0]
    id_ssr = buscar_carpeta_por_codigo(carpeta_codigo, DRIVE_FOLDER_ID)

    if id_ssr:
        carpetas_doc, _ = listar_subcarpetas_y_archivos(id_ssr)
        opciones_doc = [c['name'] for c in carpetas_doc]
        tipo_doc = st.selectbox("📁 Tipo documento (ej: Diagnóstico Terreno)", opciones_doc) if opciones_doc else ""
        id_doc = next((c['id'] for c in carpetas_doc if c['name'] == tipo_doc), id_ssr)

        carpetas_sub1, _ = listar_subcarpetas_y_archivos(id_doc)
        if carpetas_sub1:
            opciones_sub1 = [c['name'] for c in carpetas_sub1]
            subnivel_1 = st.selectbox("📁 Subnivel 1 (opcional)", opciones_sub1)
            id_sub1 = next((c['id'] for c in carpetas_sub1 if c['name'] == subnivel_1), id_doc)
        else:
            subnivel_1 = ""
            id_sub1 = id_doc

        carpetas_sub2, _ = listar_subcarpetas_y_archivos(id_sub1)
        if subnivel_1 and carpetas_sub2:
            opciones_sub2 = [c['name'] for c in carpetas_sub2]
            subnivel_2 = st.selectbox("📁 Subnivel 2 (opcional)", opciones_sub2)
            id_sub2 = next((c['id'] for c in carpetas_sub2 if c['name'] == subnivel_2), id_sub1)
        else:
            subnivel_2 = ""
            id_sub2 = id_sub1

        usuario = st.text_input("👤 Nombre colega que sube")
        archivos = st.file_uploader("📎 Sube uno o más archivos:", accept_multiple_files=True)

        if st.button("Subir") and archivos:
            for archivo in archivos:
                nombre_final = f"{carpeta_codigo}_{tipo_doc}_{datetime.now().strftime('%Y%m%d')}_{archivo.name}"
                subir_archivo_a_drive(archivo, nombre_final, id_sub2)
                st.success(f"✅ {nombre_final} cargado correctamente")
    else:
        st.error(f"Carpeta SSR '{carpeta_codigo}' no encontrada en Drive.")
