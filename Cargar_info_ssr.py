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

# Función recursiva para encontrar carpeta SSR donde sea que esté
def buscar_carpeta_por_nombre(nombre, id_padre):
    nombre_normalizado = normalizar(nombre)
    query = f"'{id_padre}' in parents and trashed = false"
    resultados = drive_service.files().list(q=query, fields="files(id, name, mimeType)").execute().get("files", [])

    st.write(f"Buscando: '{nombre}' (normalizado: '{nombre_normalizado}') dentro de ID: {id_padre}")
    st.write("Carpetas encontradas:")

    for archivo in resultados:
        if archivo["mimeType"] == "application/vnd.google-apps.folder":
            nombre_drive = normalizar(archivo["name"])
            st.write("-", archivo["name"], f"(normalizado: {nombre_drive})")
            if nombre_drive == nombre_normalizado:
                return archivo["id"]
            # Buscar también recursivamente usando el nombre normalizado
            subcarpeta = buscar_carpeta_por_nombre(nombre, archivo["id"])
            if subcarpeta:
                return subcarpeta
    return None

# Función auxiliar

def listar_subcarpetas_y_archivos(id_padre):
    query = f"'{id_padre}' in parents and trashed = false"
    resultados = drive_service.files().list(q=query, fields="files(id, name, mimeType, webViewLink)").execute()
    carpetas = [f for f in resultados.get("files", []) if f['mimeType'] == 'application/vnd.google-apps.folder']
    archivos = [f for f in resultados.get("files", []) if f['mimeType'] != 'application/vnd.google-apps.folder']
    return carpetas, archivos

def eliminar_archivo(file_id):
    drive_service.files().delete(fileId=file_id).execute()

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
    carpeta_ssr = tipo_ssr.strip()
    id_base = buscar_carpeta_por_nombre(carpeta_ssr, DRIVE_FOLDER_ID)

    if not id_base:
        st.error(f"No se encontró la carpeta en Drive para el sistema SSR '{carpeta_ssr}'. Verifica que exista dentro de la carpeta base.")
        id_base = st.text_input("🔒 Ingresar ID de carpeta manualmente si falla búsqueda automática")
        if not id_base:
            st.stop()

    if "ruta_actual" not in st.session_state:
        st.session_state.ruta_actual = [("Nivel 0", id_base)]

    if st.button("🔙 Subir un nivel") and len(st.session_state.ruta_actual) > 1:
        st.session_state.ruta_actual.pop()

    id_actual = st.session_state.ruta_actual[-1][1]
    nivel = len(st.session_state.ruta_actual)

    carpetas, archivos_sueltos = listar_subcarpetas_y_archivos(id_actual)
    if carpetas:
        opciones = [f['name'] for f in carpetas]
        seleccion = st.selectbox(f"📁 Nivel {nivel - 1}:", opciones, key=f"nivel_{nivel}")
        id_nuevo = next((f['id'] for f in carpetas if f['name'] == seleccion), None)
        if id_nuevo:
            st.session_state.ruta_actual.append((seleccion, id_nuevo))
            st.experimental_rerun()

    st.markdown("### 📌 Ruta actual:")
    st.markdown(" → ".join([nombre for nombre, _ in st.session_state.ruta_actual]))

    if archivos_sueltos:
        st.markdown("**📄 Archivos sueltos en esta carpeta:**")
        for archivo in archivos_sueltos:
            col1, col2 = st.columns([6, 1])
            with col1:
                st.markdown(f"🔗 [{archivo['name']}]({archivo['webViewLink']})")
            with col2:
                if st.button("🖑️", key=f"delete_{archivo['id']}"):
                    st.session_state.confirm_delete = archivo['id']
                    st.experimental_rerun()

        if "confirm_delete" in st.session_state:
            archivo_id = st.session_state.confirm_delete
            archivo_nombre = next((f['name'] for f in archivos_sueltos if f['id'] == archivo_id), None)
            st.warning(f"¿Estás seguro que deseas eliminar el archivo '{archivo_nombre}'?")
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✅ Sí, eliminar"):
                    eliminar_archivo(archivo_id)
                    del st.session_state.confirm_delete
                    st.success(f"Archivo '{archivo_nombre}' eliminado correctamente.")
                    st.experimental_rerun()
            with col_b:
                if st.button("❌ Cancelar"):
                    del st.session_state.confirm_delete
                    st.experimental_rerun()

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
    carpeta_ssr = tipo_ssr.strip()
    id_base = buscar_carpeta_por_nombre(carpeta_ssr, DRIVE_FOLDER_ID)

    if not id_base:
        st.error(f"No se encontró la carpeta en Drive para el sistema SSR '{carpeta_ssr}'. Verifica que exista dentro de la carpeta base.")
        id_base = st.text_input("🔒 Ingresar ID de carpeta manualmente si falla búsqueda automática", key="id_manual_lector")
        if not id_base:
            st.stop()

    if "ruta_actual_lector" not in st.session_state:
        st.session_state.ruta_actual_lector = [("Nivel 0", id_base)]

    if st.button("🔙 Subir un nivel", key="btn_subir_lector") and len(st.session_state.ruta_actual_lector) > 1:
        st.session_state.ruta_actual_lector.pop()

    id_actual = st.session_state.ruta_actual_lector[-1][1]
    nivel = len(st.session_state.ruta_actual_lector)

    carpetas, archivos = listar_subcarpetas_y_archivos(id_actual)
    if carpetas:
        opciones = [f['name'] for f in carpetas]
        seleccion = st.selectbox(f"📁 Nivel {nivel - 1}:", opciones, key=f"lector_nivel_{nivel}")
        id_nuevo = next((f['id'] for f in carpetas if f['name'] == seleccion), None)
        if id_nuevo:
            st.session_state.ruta_actual_lector.append((seleccion, id_nuevo))
            st.experimental_rerun()

    st.markdown("### 📌 Ruta actual:")
    st.markdown(" → ".join([nombre for nombre, _ in st.session_state.ruta_actual_lector]))

    _, archivos = listar_subcarpetas_y_archivos(id_actual)

    if archivos:
        st.markdown("**📄 Archivos disponibles en esta carpeta:**")
        for archivo in archivos:
            st.markdown(f"🔗 [{archivo['name']}]({archivo['webViewLink']})")
    else:
        st.info("📁 No hay archivos en esta carpeta.")
