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

# Función auxiliar

def listar_subcarpetas_y_archivos(id_padre):
    query = f"'{id_padre}' in parents and trashed = false"
    resultados = drive_service.files().list(q=query, fields="files(id, name, mimeType, webViewLink)").execute()
    carpetas = [f for f in resultados.get("files", []) if f['mimeType'] == 'application/vnd.google-apps.folder']
    archivos = [f for f in resultados.get("files", []) if f['mimeType'] != 'application/vnd.google-apps.folder']
    return carpetas, archivos

# ---------------------- CONFIGURACIÓN INICIAL ----------------------
st.set_page_config(layout="wide")

archivo_ssr = "listado_ssr_nombre_real.xlsx"
df = pd.read_excel(archivo_ssr)
df["Nombre combinado"] = df["Carpeta SSR"] + " - " + df["Nombre del sistema"]

# ---------------------- MODO ----------------------
modo = st.sidebar.radio("Selecciona una vista:", ["📤 Cargar documentos", "📚 Lector de documentos"])

# ---------------------- CARGA ----------------------
if modo == "📤 Cargar documentos":
    st.subheader("📤 Cargar Documentos SSR")

    busqueda = st.text_input("🔎 Buscar sistema SSR por nombre o código:")
    if busqueda:
        palabras = busqueda.lower().split()
        opciones_filtradas = df[df["Nombre combinado"].str.lower().apply(lambda x: all(p in x for p in palabras))]
    else:
        opciones_filtradas = df

    tipo_ssr = st.selectbox("Selecciona el sistema SSR:", opciones_filtradas["Nombre combinado"].tolist())
    carpeta_ssr = tipo_ssr.split(" - ")[0]
    id_ssr = drive_service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and name = '{carpeta_ssr}' and trashed = false", fields="files(id)").execute()
    id_base = id_ssr['files'][0]['id'] if id_ssr['files'] else None

    if not id_base:
        st.error(f"No se encontró la carpeta en Drive para el sistema SSR '{carpeta_ssr}'. Verifica que exista dentro de la carpeta base.")
        st.stop()

    id_actual = id_base
    nivel = 1
    ruta_actual = [("Nivel 0", id_actual)]  # Ruta de navegación inicial

    while True:
        carpetas, archivos_sueltos = listar_subcarpetas_y_archivos(id_actual)
        if not carpetas:
            break
        opciones = [f['name'] for f in carpetas]
        seleccion = st.selectbox(f"📁 Nivel {nivel}:", opciones, key=f"nivel_{nivel}")
        id_actual = next((f['id'] for f in carpetas if f['name'] == seleccion), None)
        ruta_actual.append((seleccion, id_actual))
        nivel += 1

    # Mostrar ruta actual
    if ruta_actual:
        st.markdown("### 📌 Ruta actual:")
        st.markdown(" → ".join([nombre for nombre, _ in ruta_actual]))

    if archivos_sueltos:
        st.markdown("**📄 Archivos sueltos en esta carpeta:**")
        for archivo in archivos_sueltos:
            st.markdown(f"🔗 [{archivo['name']}]({archivo['webViewLink']})")

    nombre_usuario = st.text_input("Nombre del colega que sube el archivo")
    archivos = st.file_uploader("Sube uno o más archivos", accept_multiple_files=True, type=None)

    if st.button("Subir archivo(s)"):
        if not archivos:
            st.error("⚠️ Debes subir al menos un archivo.")
        else:
            for archivo in archivos:
                nombre_archivo = archivo.name
                fecha = datetime.now().strftime("%Y%m%d")
                nuevo_nombre = f"{carpeta_ssr}_Nivel{nivel-1}_{fecha}_{nombre_archivo}"

                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp.write(archivo.getbuffer())
                    tmp_path = tmp.name

                media = MediaFileUpload(tmp_path, resumable=True)
                archivo_metadata = {
                    'name': nuevo_nombre,
                    'parents': [id_actual]
                }

                drive_service.files().create(
                    body=archivo_metadata,
                    media_body=media,
                    fields='id'
                ).execute()

                st.success(f"✅ Archivo subido como: {nuevo_nombre}")
                os.remove(tmp_path)

# ---------------------- LECTOR ----------------------
if modo == "📚 Lector de documentos":
    st.subheader("📚 Lector de Documentos SSR")

    busqueda = st.text_input("🔎 Buscar sistema SSR por nombre o código:", key="busqueda_lector")
    if busqueda:
        palabras = busqueda.lower().split()
        opciones_filtradas = df[df["Nombre combinado"].str.lower().apply(lambda x: all(p in x for p in palabras))]
    else:
        opciones_filtradas = df

    tipo_ssr = st.selectbox("Selecciona el sistema SSR:", opciones_filtradas["Nombre combinado"].tolist(), key="lector_ssr")
    carpeta_ssr = tipo_ssr.split(" - ")[0]
    id_ssr = drive_service.files().list(q=f"'{DRIVE_FOLDER_ID}' in parents and name = '{carpeta_ssr}' and trashed = false", fields="files(id)").execute()
    id_base = id_ssr['files'][0]['id'] if id_ssr['files'] else None

    if not id_base:
        st.error(f"No se encontró la carpeta en Drive para el sistema SSR '{carpeta_ssr}'. Verifica que exista dentro de la carpeta base.")
        st.stop()

    id_actual = id_base
    nivel = 1
    ruta_actual = [("Nivel 0", id_actual)]

    while True:
        carpetas, archivos = listar_subcarpetas_y_archivos(id_actual)
        if not carpetas:
            break
        opciones = [f['name'] for f in carpetas]
        seleccion = st.selectbox(f"📁 Nivel {nivel}:", opciones, key=f"lector_nivel_{nivel}")
        id_actual = next((f['id'] for f in carpetas if f['name'] == seleccion), None)
        ruta_actual.append((seleccion, id_actual))
        nivel += 1

    if ruta_actual:
        st.markdown("### 📌 Ruta actual:")
        st.markdown(" → ".join([nombre for nombre, _ in ruta_actual]))

    _, archivos = listar_subcarpetas_y_archivos(id_actual)

    if archivos:
        st.markdown("**📄 Archivos disponibles en esta carpeta:**")
        for archivo in archivos:
            st.markdown(f"🔗 [{archivo['name']}]({archivo['webViewLink']})")
    else:
        st.info("📁 No hay archivos en esta carpeta.")
