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

# Función para normalizar nombres (quitar tildes, espacios, etc.)
def normalizar(texto):
    return unicodedata.normalize('NFKD', texto.strip().lower()).encode('ascii', 'ignore').decode('utf-8')

# Función recursiva para encontrar carpeta SSR por código
def buscar_carpeta_por_codigo(codigo, id_padre):
    codigo_normalizado = normalizar(codigo)
    query = f"'{id_padre}' in parents and trashed = false"
    resultados = drive_service.files().list(q=query, fields="files(id, name, mimeType)").execute().get("files", [])

    for archivo in resultados:
        if archivo["mimeType"] == "application/vnd.google-apps.folder":
            nombre_drive = normalizar(archivo["name"])
            if codigo_normalizado == nombre_drive:
                return archivo["id"]
    return None

def buscar_subcarpeta(nombre, id_padre):
    nombre_normalizado = normalizar(nombre)
    query = f"'{id_padre}' in parents and trashed = false"
    resultados = drive_service.files().list(q=query, fields="files(id, name, mimeType)").execute().get("files", [])

    for archivo in resultados:
        if archivo["mimeType"] == "application/vnd.google-apps.folder":
            if normalizar(archivo["name"]) == nombre_normalizado:
                return archivo["id"]
    return None

def crear_subcarpeta(nombre, id_padre):
    metadata = {
        'name': nombre,
        'mimeType': 'application/vnd.google-apps.folder',
        'parents': [id_padre]
    }
    carpeta = drive_service.files().create(body=metadata, fields='id').execute()
    return carpeta['id']

def subir_archivo_a_drive(archivo, nombre_archivo, id_carpeta):
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(archivo.getbuffer())
        tmp_path = tmp.name

    media = MediaFileUpload(tmp_path, resumable=True)
    metadata = {'name': nombre_archivo, 'parents': [id_carpeta]}
    drive_service.files().create(body=metadata, media_body=media, fields='id').execute()
    os.remove(tmp_path)

# ---------------------- CONFIGURACIÓN INICIAL ----------------------
st.set_page_config(layout="wide")

archivo_ssr = "listado_ssr_nombre_real.xlsx"
df = pd.read_excel(archivo_ssr)
df["Nombre combinado"] = df["Carpeta SSR"] + " - " + df["Nombre del sistema"]

# ---------------------- MODO ----------------------
modo = st.sidebar.radio("Selecciona una vista:", ["📤 Cargar documentos", "📚 Lector de documentos"])

if modo == "📤 Cargar documentos":
    st.header("📤 Cargar documentos SSR")
    busqueda = st.text_input("🔎 Buscar sistema SSR:")
    if busqueda:
        palabras = busqueda.lower().split()
        opciones = df[df["Nombre combinado"].str.lower().apply(lambda x: all(p in x for p in palabras))]
    else:
        opciones = df

    seleccionado = st.selectbox("Selecciona sistema SSR:", opciones["Nombre combinado"].tolist())
    carpeta_codigo = seleccionado.split(" - ")[0]
    tipo_doc = st.text_input("📁 Tipo documento (ej: Diagnóstico Terreno)")
    subnivel_1 = st.text_input("📁 Subnivel 1 (opcional)")
    subnivel_2 = st.text_input("📁 Subnivel 2 (opcional)")
    usuario = st.text_input("👤 Nombre colega que sube")
    archivos = st.file_uploader("📎 Sube uno o más archivos:", accept_multiple_files=True)

    if st.button("Subir") and archivos:
        id_ssr = buscar_carpeta_por_codigo(carpeta_codigo, DRIVE_FOLDER_ID)
        if not id_ssr:
            st.error(f"Carpeta SSR '{carpeta_codigo}' no encontrada en Drive.")
        else:
            id_doc = buscar_subcarpeta(tipo_doc, id_ssr) or crear_subcarpeta(tipo_doc, id_ssr)
            id_sub1 = buscar_subcarpeta(subnivel_1, id_doc) if subnivel_1 else id_doc
            if subnivel_1 and not id_sub1:
                id_sub1 = crear_subcarpeta(subnivel_1, id_doc)
            id_sub2 = buscar_subcarpeta(subnivel_2, id_sub1) if subnivel_2 else id_sub1
            if subnivel_2 and not id_sub2:
                id_sub2 = crear_subcarpeta(subnivel_2, id_sub1)

            for archivo in archivos:
                nombre_final = f"{carpeta_codigo}_{tipo_doc}_{datetime.now().strftime('%Y%m%d')}_{archivo.name}"
                subir_archivo_a_drive(archivo, nombre_final, id_sub2)
                st.success(f"✅ {nombre_final} cargado correctamente")

if modo == "📚 Lector de documentos":
    st.header("📚 Lector de documentos")
    busqueda = st.text_input("🔍 Buscar sistema SSR:", key="lector_busqueda")
    if busqueda:
        palabras = busqueda.lower().split()
        opciones = df[df["Nombre combinado"].str.lower().apply(lambda x: all(p in x for p in palabras))]
    else:
        opciones = df

    seleccionado = st.selectbox("Selecciona sistema SSR:", opciones["Nombre combinado"].tolist(), key="lector_ssr")
    carpeta_codigo = seleccionado.split(" - ")[0]
    id_ssr = buscar_carpeta_por_codigo(carpeta_codigo, DRIVE_FOLDER_ID)

    if id_ssr:
        nivel_1, archivos_1 = listar_subcarpetas_y_archivos(id_ssr)
        tipo_doc = st.selectbox("📁 Tipo documento:", [c['name'] for c in nivel_1])
        id_doc = next(c['id'] for c in nivel_1 if c['name'] == tipo_doc)

        nivel_2, archivos_2 = listar_subcarpetas_y_archivos(id_doc)
        if nivel_2:
            subnivel_1 = st.selectbox("📁 Subnivel 1:", [c['name'] for c in nivel_2])
            id_sub1 = next(c['id'] for c in nivel_2 if c['name'] == subnivel_1)

            nivel_3, archivos_3 = listar_subcarpetas_y_archivos(id_sub1)
            if nivel_3:
                subnivel_2 = st.selectbox("📁 Subnivel 2:", [c['name'] for c in nivel_3])
                id_sub2 = next(c['id'] for c in nivel_3 if c['name'] == subnivel_2)
                _, archivos_finales = listar_subcarpetas_y_archivos(id_sub2)
            else:
                archivos_finales = archivos_3
        else:
            archivos_finales = archivos_2

        if archivos_finales:
            st.markdown("**📂 Archivos encontrados:**")
            for archivo in archivos_finales:
                st.markdown(f"🔗 [{archivo['name']}]({archivo['webViewLink']})")
        else:
            st.info("📁 No hay archivos en esta carpeta.")
    else:
        st.error("No se encontró la carpeta SSR en Drive.")
