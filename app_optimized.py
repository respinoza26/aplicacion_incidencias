import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, date
import io
import os
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass
import hashlib
from pathlib import Path

# =============================================================================
# CONFIGURACIÓN DE RUTAS Y VARIABLES DE ENTORNO
# =============================================================================

# RUTAS BASE DEL PROYECTO
BASE_DIR = Path(__file__).resolve().parent  # Directorio donde está el script
DATA_DIR = BASE_DIR / "data"                # Carpeta de datos
ASSETS_DIR = BASE_DIR / "assets"            # Carpeta de recursos (logos, etc.)

# VARIABLES DE ENTORNO
MAESTROS_FILE = os.getenv('MAESTROS_FILE_PATH', str(DATA_DIR / 'maestros.xlsx'))  
# Archivo Excel maestro con datos de empleados, centros, tarifas
# Por defecto: data/maestros.xlsx

MAX_UPLOAD_SIZE = int(os.getenv('MAX_UPLOAD_SIZE_MB', '200'))  
# Tamaño máximo de archivos subidos en MB
# Por defecto: 200MB
# =============================================================================
# FUNCIONES DE ESTILO Y LOGO
# =============================================================================

def _add_logo_and_css():
    """
    Inyecta CSS personalizado en la aplicación Streamlit.
    
    Funcionalidad:
    - Oculta elementos no deseados del UI de Streamlit
    - Personaliza colores (azul #1670B7 para headers)
    - Ajusta espaciado de pestañas y contenedores
    - Oculta el menú principal y footer de Streamlit
    
    Sin parámetros de entrada
    Sin retorno
    """    
    st.markdown(
        """
        <style>
        /* ======== AJUSTES GENERALES ======== */
        .st-emotion-cache-1oe2kxr, 
        .st-emotion-cache-1dp5vir { 
            visibility: hidden !important;
            display: none !important; 
        }

        #MainMenu, footer {
            visibility: hidden;
        }

        h1 {
            color: #1670B7;
            margin-top: 0px;
        }

        /* ======== ANCHO DE PÁGINA ======== */
        div.block-container {
            padding-top: 2rem;
            max-width: 90% !important;   /* ✅ Recomendado para portátiles */
            padding-left: 2%;
            padding-right: 2%;
        }

        /* ======== TABS ======== */
        .stTabs [data-baseweb="tab-list"] {
            gap: 24px;
        }

        .stTabs [data-baseweb="tab"] {
            height: 50px;
            padding-left: 20px;
            padding-right: 20px;
        }

        /* ======== SCROLL EXTERNO EN TABLAS ======== */
        div[data-testid="stDataFrame"] > div {
            overflow: visible !important;
        }

        div[data-testid="stDataFrame"] div[role="table"] {
            overflow-x: visible !important;
        }

        section.main > div.block-container {
            overflow-x: auto !important;
        }

        /* ======== VISIBILIDAD Y ESTILO DE ENCABEZADOS ======== */
        div[data-testid="stDataFrame"] thead tr th {
            visibility: visible !important;
            background-color: #f5f6fa !important;
            color: #1c1c1c !important;
            font-weight: 600 !important;
            font-size: 14px !important;
            text-align: center !important;
            border-bottom: 2px solid #ccc !important;
            padding: 6px !important;
        }

        /* Mejor contraste de celdas alternadas */
        div[data-testid="stDataFrame"] tbody tr:nth-child(even) {
            background-color: #fafafa !important;
        }

        /* Bordes suaves y uniformes */
        div[data-testid="stDataFrame"] td {
            border-bottom: 1px solid #e0e0e0 !important;
            text-align: center !important;
        }

        /* Aumenta la legibilidad de los datos editables */
        div[data-testid="stDataFrame"] input {
            text-align: center !important;
            font-size: 13px !important;
        }
        </style>
        """,
        unsafe_allow_html=True
    )

# =============================================================================
# FUNCIONES DE CARGA OPTIMIZADAS
# =============================================================================

@st.cache_data
def _load_single_sheet(file_path: str, sheet_name: str, file_hash: str, **kwargs) -> pd.DataFrame:
    """
    Carga una hoja específica de un archivo Excel con caché.
    
    Parámetros:
    - file_path (str): Ruta completa al archivo Excel
    - sheet_name (str): Nombre de la hoja a cargar
    - file_hash (str): Hash MD5 del archivo para invalidar caché si cambia
    - **kwargs: Argumentos adicionales para pd.read_excel (ej: usecols, skiprows)
    
    Retorna:
    - pd.DataFrame: Datos de la hoja o DataFrame vacío si hay error
    
    Nota: Usa @st.cache_data para evitar recargas innecesarias
    """
    try:
        return pd.read_excel(file_path, sheet_name=sheet_name, engine="openpyxl", **kwargs)
    except Exception as e:
        st.error(f"Error cargando hoja '{sheet_name}': {e}")
        return pd.DataFrame()

@st.cache_data
def _get_sheet_names(file_path: str, file_hash: str) -> List[str]:
    """
    Obtiene lista de nombres de hojas en un Excel.
    
    Parámetros:
    - file_path (str): Ruta al archivo Excel
    - file_hash (str): Hash para control de caché
    
    Retorna:
    - List[str]: Lista de nombres de hojas o lista vacía si hay error
    """
    try:
        with pd.ExcelFile(file_path, engine="openpyxl") as xls:
            return xls.sheet_names
    except Exception:
        return []

@st.cache_data
def build_tarifa_lookup(file_path: str, file_hash: str) -> Dict[Tuple[str, str], float]:
    """
    Construye tabla de búsqueda O(1) para tarifas de nocturnidad.
    
    Parámetros:
    - file_path (str): Ruta al archivo maestro
    - file_hash (str): Hash para caché
    
    Retorna:
    - Dict[(categoria, convenio), tarifa]: 
      Diccionario con clave tupla (categoría normalizada, código convenio)
      y valor tarifa de nocturnidad
    
    Procesamiento:
    - Normaliza categorías a mayúsculas
    - Convierte códigos de convenio de notación científica a string
    - Elimina prefijos de categoría (ej: "h ASL" → "ASL")
    """
    # ✅ FIX 1: Cambiar skiprows=3 a skiprows=0 para leer headers correctos
    df_tarifas = _load_single_sheet(file_path, 'tarifas_incidencias', file_hash, usecols="A:C")
    lookup = {}
    
    if not df_tarifas.empty:
        df_tarifas.columns = [str(c).strip() for c in df_tarifas.columns]

    if {'Descripción', 'cod_convenio', 'tarifa_noct'}.issubset(df_tarifas.columns):
        for _, row in df_tarifas.iterrows():
            try:
                # Normalizar categoría
                categoria_norm = str(row['Descripción']).strip().upper()
                
                # ✅ FIX 2: Convertir convenio a entero para eliminar notación científica
                # Esto convierte "9.91002E+13" a "99100165012016"
                convenio_raw = row['cod_convenio']
                if pd.notna(convenio_raw):
                    try:
                        # Convertir a float primero, luego a int, luego a string
                        convenio_norm = str(int(float(convenio_raw)))
                    except:
                        convenio_norm = str(convenio_raw).strip()
                else:
                    convenio_norm = ""
                
                tarifa = float(row['tarifa_noct'])
                
                if categoria_norm and convenio_norm and pd.notna(tarifa):
                    lookup[(categoria_norm, convenio_norm)] = tarifa
            except Exception:
                continue    

    return lookup

@st.cache_data
def build_empleado_lookup(df_trabajadores: pd.DataFrame, file_hash: str) -> Dict[str, Dict]:
    """
    Construye diccionario de búsqueda rápida de empleados.
    
    Parámetros:
    - df_trabajadores (pd.DataFrame): DataFrame con datos de trabajadores
    - file_hash (str): Hash para caché
    
    Retorna:
    - Dict[nombre_empleado, info_dict]: 
      Diccionario donde la clave es el nombre del empleado
      y el valor es un dict con toda su información
    
    Valores por defecto en info_dict:
    - servicio: ''
    - cat_empleado: ''
    - cod_crown: ''
    - centro_preferente: ''
    - coste_hora: 0.0
    """
    lookup = {}
    if df_trabajadores is None or df_trabajadores.empty:
        return lookup

    df = df_trabajadores.copy()
    name_col = None
    for c in df.columns:
        if c.lower().strip() in ('nombre_empleado', 'nombre empleado', 'nombre'):
            name_col = c
            break
    if name_col is None:
        return lookup

    for _, empleado in df.iterrows():
        info = empleado.to_dict()
        default_values = {
            'servicio': '',
            'cat_empleado': '',
            'cod_crown': '',
            'centro_preferente': '',
            'nombre_centro_preferente': '',
            'nombre_jefe_ope': '',
            'coste_hora': 0.0,
            'cod_reg_convenio': '',
            'porcen_contrato': '',
            'cod_empresa': ''
        }
    # Construir la lista de diccionarios de una vez
    records = df.to_dict('records')
    for info in records:
        # Aplicar la lógica de valores por defecto de manera eficiente
        for key, default_value in default_values.items():
            if key not in info or pd.isna(info.get(key)) or info.get(key) == '':
                info[key] = default_value
        
        lookup_key = info.get(name_col, '')
        if lookup_key: # Asegurar que la clave no esté vacía
            lookup[lookup_key] = info

    return lookup

def _get_file_hash(file_path: str) -> str:
    """
    Calcula hash MD5 de un archivo para detectar cambios.
    
    Parámetros:
    - file_path (str): Ruta al archivo
    
    Retorna:
    - str: Hash MD5 hexadecimal o "FILE_NOT_FOUND"/"ERROR_HASH" si hay error
    
    Uso: Invalida caché cuando el archivo maestro cambia
    """
    try:
        if not Path(file_path).exists():
            return "FILE_NOT_FOUND"
        with open(file_path, 'rb') as f:
            data = f.read()
        return hashlib.md5(data).hexdigest()
    except Exception:
        return "ERROR_HASH"

@st.cache_data
def get_centros_lookup(file_path: str, file_hash: str) -> pd.DataFrame:
    """
    Carga y procesa el maestro de centros para búsqueda rápida.
    
    Parámetros:
    - file_path (str): Ruta al archivo maestro
    - file_hash (str): Hash para caché
    
    Retorna:
    - pd.DataFrame con columnas:
      - cod_centro_preferente: Código del centro
      - desc_centro_preferente: Descripción/nombre
      - nombre_centro_display: "Código - Descripción" para mostrar
    
    Procesamiento:
    - Convierte códigos a string sin decimales
    - Crea campo display combinado para selectboxes
    """
    df = preprocess_centros(_load_single_sheet(file_path, 'Centros', file_hash))
    if df.empty or len(df.columns) < 2:
        return pd.DataFrame({'cod_centro_preferente': [], 'desc_centro_preferente': []})
    
    if 'cod_centro_preferente' in df.columns and 'desc_centro_preferente' in df.columns:
        df['cod_centro_preferente'] = df['cod_centro_preferente'].apply(lambda x: str(int(float(x))) if pd.notna(x) and str(x).replace('.', '').replace('-', '').isdigit() else str(x))
        df['nombre_centro_display'] = df['cod_centro_preferente'] + ' - ' + df['desc_centro_preferente'].astype(str)
        return df[['cod_centro_preferente', 'desc_centro_preferente', 'nombre_centro_display']].drop_duplicates().reset_index(drop=True)
    return pd.DataFrame({'cod_centro_preferente': [], 'desc_centro_preferente': [], 'nombre_centro_display': []})

# =============================================================================
# PREPROCESS
# =============================================================================

def preprocess_centros(df: pd.DataFrame) -> pd.DataFrame:
    """
    Limpia y prepara datos de la hoja 'Centros'.
    
    Parámetros:
    - df (pd.DataFrame): DataFrame crudo de centros
    
    Retorna:
    - pd.DataFrame: DataFrame procesado
    
    Procesamiento:
    1. Filtra filas sin cod_centro_preferente
    2. Elimina centros con fecha_baja_centro
    3. Normaliza códigos (sin decimales)
    4. Elimina columnas innecesarias
    5. Excluye jefes específicos (Angel Alcalde, Esther Martin, Julio)
    6. Crea alias 'codigo_centro'
    """    
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.columns = [c.strip() for c in df.columns]
    
    # 1. FILTRAR: Eliminar filas sin cod_centro_preferente
    if 'cod_centro_preferente' in df.columns:
        df = df[df['cod_centro_preferente'].notna()]
        df = df[df['cod_centro_preferente'] != '']
    else:
        st.warning("⚠️ La hoja 'Centros' no contiene la columna 'cod_centro_preferente'")
        return pd.DataFrame()
    
    # 2. FILTRAR: Eliminar filas con fecha_baja_centro
    if 'fecha_baja_centro' in df.columns:
        df = df[df['fecha_baja_centro'].isna()]
    
    # 3. NORMALIZAR: cod_centro_preferente como string sin decimales
    df['cod_centro_preferente'] = df['cod_centro_preferente'].apply(
        lambda x: str(int(float(x))) if pd.notna(x) and str(x).replace('.', '').replace('-', '').isdigit() else str(x)
    )
    
    # 4. ELIMINAR COLUMNAS: fecha_alta_centro, fecha_baja_centro, almacen_centro
    columns_to_drop = ['fecha_alta_centro', 'fecha_baja_centro', 'almacen_centro']
    df = df.drop(columns=[col for col in columns_to_drop if col in df.columns], errors='ignore')
    df = df[~df['nombre_jefe_ope'].isin(['Angel Alcalde', 'Esther Martin Gonzalez','Julio'])]
    
    # 5. CREAR ALIAS: codigo_centro = cod_centro_preferente (para compatibilidad interna)
    df['codigo_centro'] = df['cod_centro_preferente']
    
    # 6. Verificar que existe nombre_jefe_ope
    if 'nombre_jefe_ope' not in df.columns:
        st.warning("⚠️ La hoja 'Centros' no contiene la columna 'nombre_jefe_ope'")
    
    return df

def preprocess_trabajadores(df: pd.DataFrame) -> pd.DataFrame:
    """
    Procesa datos de la hoja 'Trabajadores'.
    
    Parámetros:
    - df (pd.DataFrame): DataFrame crudo de trabajadores
    
    Retorna:
    - pd.DataFrame: DataFrame procesado
    
    Procesamiento:
    - Limpia nombres de columnas (quita saltos de línea)
    - Convierte nombres a mayúsculas
    - Asigna servicio según categoría:
      * Si contiene 'limp' o 'asl' → '020 Limpieza'
      * Sino → '010 Restauración'
    """    
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    df.columns = df.columns.str.strip().str.replace('\n', ' ')
    
    if 'nombre_empleado' in df.columns:
        df['nombre_empleado'] = df['nombre_empleado'].str.upper()

    if 'servicio' not in df.columns and 'cat_empleado' in df.columns:
        df['servicio'] = np.where(
            df['cat_empleado'].str.contains('limp|asl', case=False, na=False),
            '020 Limpieza',
            '010 Restauración'
        )
    return df

def preprocess_maestro_centros(df: pd.DataFrame) -> pd.DataFrame:
    """Procesa la hoja maestro_centros (si existe) - uso legacy."""
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    if len(df.columns) >= 3:
        df = df.iloc[:, :3]
        df.columns = ['codigo_centro', 'nombre_centro', 'cod_centro_preferente']
    else:
        df.columns = [c.strip() for c in df.columns]
    return df

def preprocess_tarifas_incidencias(df: pd.DataFrame) -> pd.DataFrame:
    return df if df is not None else pd.DataFrame()

# =============================================================================
# MODELO DE DATOS
# =============================================================================

@dataclass
class Incidencia:
    """
    Modelo de datos para una incidencia de personal.
    
    Atributos:
    - trabajador (str): Nombre del empleado
    - imputacion_nomina (str): Mes de imputación (ej: "01-Enero")
    - facturable (str): "Sí" o "No"
    - motivo (str): Motivo de la incidencia
    - codigo_crown_origen (str): Centro de origen del trabajador
    - codigo_crown_destino (str): Centro donde cubre
    - empresa_destino (str): Empresa del centro destino
    - incidencia_horas (float): Horas de incidencia
    - incidencia_precio (float): Precio por hora
    - nocturnidad_horas (float): Horas nocturnas
    - traslados_total (float): Horas de traslado
    - coste_hora (float): Coste/hora del empleado
    - fecha (date): Fecha de la incidencia
    - observaciones (str): Notas adicionales
    - centro_preferente (str): Centro base del trabajador
    - nombre_jefe_ope (str): Supervisor responsable
    - categoria (str): Categoría del empleado
    - servicio (str): Tipo de servicio
    - cod_reg_convenio (str): Código de convenio
    - nombre_crown_destino (str): Nombre del centro destino
    """
    
    trabajador: str = ""
    imputacion_nomina: str = ""
    facturable: str = ""
    motivo: str = ""
    codigo_crown_origen: str = ""
    codigo_crown_destino: str = ""
    empresa_destino: str = ""
    incidencia_horas: float = 0.0
    incidencia_precio: float = 0.0
    nocturnidad_horas: float = 0.0
    traslados_total: float = 0.0
    coste_hora: float = 0.0
    fecha: str = ""
    observaciones: str = ""
    centro_preferente: str = ""
    nombre_jefe_ope: str = ""
    categoria: str = ""
    servicio: str = ""
    cod_reg_convenio: str = ""
    nombre_crown_destino: str = ""

    def to_dict(self, precio_nocturnidad: float = 0.0) -> Dict:
        """
        Convierte la incidencia a diccionario para DataFrame.
        
        Parámetros:
        - precio_nocturnidad (float): Tarifa de nocturnidad calculada
        
        Retorna:
        - Dict: Diccionario con todos los campos formateados
        """
        return {
            "Borrar": False,
            "Trabajador": self.trabajador,
            #"Imputación Nómina": self.imputacion_nomina,
            "Facturable": self.facturable,
            "Motivo": self.motivo,
            "Código Crown Origen": self.codigo_crown_origen,
            "Código Crown Destino": self.codigo_crown_destino,
            "Empresa Destino": self.empresa_destino,
            "Incidencia_horas": self.incidencia_horas,
            "Incidencia_precio": self.incidencia_precio,
            "Nocturnidad_horas": self.nocturnidad_horas,
            "Precio_nocturnidad": precio_nocturnidad,
            "Traslados_total": self.traslados_total,
            "Coste hora empresa": self.coste_hora,
            "Fecha": self.fecha,
            "Observaciones": self.observaciones,
            "Centro preferente": self.centro_preferente,
            "Supervisor de operaciones": self.nombre_jefe_ope,
            "Categoría": self.categoria,
            "Servicio": self.servicio,
            "Cod_reg_convenio": self.cod_reg_convenio,
            "Nombre Crown Destino": self.nombre_crown_destino,
        }

    def is_valid(self) -> bool:
        """
        Valida si la incidencia tiene todos los campos requeridos.
        
        Campos obligatorios:
        - trabajador, imputacion_nomina, facturable
        - motivo, codigo_crown_destino, fecha, observaciones
        
        Retorna:
        - bool: True si todos los campos obligatorios están completos
        """
        required_fields = [
            self.trabajador,  self.facturable,
            self.motivo, self.codigo_crown_destino, self.fecha#, self.imputacion_nomina,self.observaciones
        ]
        return all(
            (field is not None and field != "")
            for field in required_fields
        )
    
    def clone(self) -> 'Incidencia':
        """
        Crea una copia profunda de la incidencia.
        
        Retorna:
        - Incidencia: Nueva instancia con los mismos valores
        """        
        return Incidencia(
            trabajador=self.trabajador,
            imputacion_nomina=self.imputacion_nomina,
            facturable=self.facturable,
            motivo=self.motivo,
            codigo_crown_origen=self.codigo_crown_origen,
            codigo_crown_destino=self.codigo_crown_destino,
            empresa_destino=self.empresa_destino,
            incidencia_horas=self.incidencia_horas,
            incidencia_precio=self.incidencia_precio,
            nocturnidad_horas=self.nocturnidad_horas,
            traslados_total=self.traslados_total,
            coste_hora=self.coste_hora,
            fecha=self.fecha,
            observaciones=self.observaciones,
            centro_preferente=self.centro_preferente,
            nombre_jefe_ope=self.nombre_jefe_ope,
            categoria=self.categoria,
            servicio=self.servicio,
            cod_reg_convenio=self.cod_reg_convenio,
            nombre_crown_destino=self.nombre_crown_destino,
        )

# =============================================================================
# DATA MANAGER OPTIMIZADO
# =============================================================================

class OptimizedDataManager:
    """
    Gestor centralizado de acceso a datos maestros con caché.
    
    Atributos:
    - file_path (str): Ruta al archivo maestros.xlsx
    - file_hash (str): Hash MD5 del archivo
    - _df_centros (DataFrame): Caché de datos de centros
    - _df_trabajadores (DataFrame): Caché de datos de trabajadores
    - _tarifa_lookup (Dict): Lookup de tarifas O(1)
    - _empleado_lookup (Dict): Lookup de empleados O(1)
    - _jefes_list (List): Lista de supervisores
    - _empleados_list (List): Lista de nombres de empleados
    - _centros_list (List): Lista de códigos de centros
    - centros_lookup_df (DataFrame): DataFrame para búsqueda de centros
    """
    def __init__(self, file_path: str = 'data/maestros.xlsx'):
        """
        Inicializa el gestor y construye cachés.
        
        Parámetros:
        - file_path (str): Ruta al archivo maestro
        """        
        
        self.file_path = file_path
        self._df_centros = None
        self._df_trabajadores = None
        self.file_hash = _get_file_hash(self.file_path)

        self._tarifa_lookup = None
        self._empleado_lookup = None
        self._jefes_list = None
        self._empleados_list = None
        self._centros_list = None
        
        self.centros_lookup_df = get_centros_lookup(self.file_path, self.file_hash)
        self._ensure_cache_built()

    @property
    def df_centros(self) -> pd.DataFrame:
        """
        Propiedad lazy-loading para datos de centros.
        Carga y procesa solo cuando se accede por primera vez.
        
        Retorna:
        - pd.DataFrame: DataFrame procesado de centros
        """
        if self._df_centros is None:
            df = _load_single_sheet(self.file_path, 'Centros', self.file_hash)
            df = preprocess_centros(df)
            self._df_centros = df
        return self._df_centros

    @property
    def df_trabajadores(self) -> pd.DataFrame:
        """
        Propiedad lazy-loading para datos de trabajadores.
        Realiza merge con centros para obtener jefe y nombre del centro.
        
        Retorna:
        - pd.DataFrame: DataFrame procesado con info completa
        """
        if self._df_trabajadores is None:
            df = _load_single_sheet(self.file_path, 'Trabajadores', self.file_hash)
            df = preprocess_trabajadores(df)

            if not df.empty and not self.df_centros.empty and 'centro_preferente' in df.columns:
                # Normalizar centro_preferente como string
                df['centro_preferente'] = df['centro_preferente'].apply(
                    lambda x: str(int(float(x))) if pd.notna(x) and str(x).replace('.', '').replace('-', '').isdigit() else str(x)
                )

                # ✅ FIX: Merge correcto con nombres exactos de columnas
                centros_temp = self.df_centros[['codigo_centro', 'nombre_jefe_ope', 'desc_centro_preferente']].copy()

                df = pd.merge(
                    df,
                    centros_temp,
                    left_on='centro_preferente',
                    right_on='codigo_centro',
                    how='left',
                    suffixes=('', '_from_centros')
                )
                
                # ✅ FIX: Sobrescribir nombre_jefe_ope con el del centro si existe
                if 'nombre_jefe_ope_from_centros' in df.columns:
                    df['nombre_jefe_ope'] = df['nombre_jefe_ope_from_centros'].fillna(df.get('nombre_jefe_ope', ''))
                    df = df.drop(columns=['nombre_jefe_ope_from_centros'], errors='ignore')
                
                # Renombrar desc_centro_preferente a nombre_centro_preferente
                if 'desc_centro_preferente' in df.columns:
                    df = df.rename(columns={'desc_centro_preferente': 'nombre_centro_preferente'})
                
                # Limpiar columnas duplicadas del merge
                df = df.drop(columns=[col for col in ['codigo_centro_x', 'codigo_centro_y', 'codigo_centro'] if col in df.columns], errors='ignore')

            self._df_trabajadores = df
            
        return self._df_trabajadores

    def _ensure_cache_built(self):
        if self._tarifa_lookup is None:
            self._tarifa_lookup = build_tarifa_lookup(self.file_path, self.file_hash)
        if self._empleado_lookup is None:
            self._empleado_lookup = build_empleado_lookup(self.df_trabajadores, self.file_hash)

        if self._jefes_list is None or self._centros_list is None:
            jefes = set()
            
            # Obtener jefes de la columna nombre_jefe_ope de la hoja Centros
            if not self.df_centros.empty and 'nombre_jefe_ope' in self.df_centros.columns:
                jefes.update(self.df_centros['nombre_jefe_ope'].dropna().unique())
            
            self._jefes_list = sorted(list(jefes))

            # Usar codigo_centro de la hoja Centros
            if not self.df_centros.empty and 'codigo_centro' in self.df_centros.columns:
                self._centros_list = sorted(self.df_centros['codigo_centro'].dropna().astype(str).unique().tolist())
            else:
                self._centros_list = []

        if self._empleados_list is None:
            if not self.df_trabajadores.empty:
                name_col = None
                for c in self.df_trabajadores.columns:
                    if c.lower().strip() in ('nombre_empleado', 'nombre empleado', 'nombre'):
                        name_col = c
                        break
                if name_col:
                    self._empleados_list = sorted(self.df_trabajadores[name_col].dropna().unique().tolist())
                else:
                    self._empleados_list = []
            else:
                self._empleados_list = []

    def get_precio_nocturnidad(self, categoria: str, cod_convenio: str) -> float:
        """
        Obtiene tarifa de nocturnidad con búsqueda O(1).
        
        Parámetros:
        - categoria (str): Categoría del empleado
        - cod_convenio (str): Código de convenio
        
        Retorna:
        - float: Tarifa de nocturnidad o 0.0 si no existe
        
        Procesamiento:
        - Normaliza categoría (mayúsculas, quita prefijos)
        - Convierte convenio de notación científica
        """
        # Normalizar categoría
        categoria_norm = str(categoria).strip().upper() if pd.notna(categoria) else ""
        
        # ✅ FIX 3: Remover prefijos comunes ('h ', 'g ', etc.)
        # Ejemplo: "h ASL" → "ASL"
        if categoria_norm:
            # Remover prefijos de una letra seguidos de espacio
            parts = categoria_norm.split(' ', 1)
            if len(parts) == 2 and len(parts[0]) == 1:
                categoria_norm = parts[1]
        
        # ✅ FIX 2: Normalizar convenio como entero (para eliminar notación científica)
        if pd.notna(cod_convenio) and cod_convenio != '':
            try:
                convenio_norm = str(int(float(cod_convenio)))
            except:
                convenio_norm = str(cod_convenio).strip()
        else:
            convenio_norm = ""
        
        if not categoria_norm or not convenio_norm:
            return 0.0
        
        return self._tarifa_lookup.get((categoria_norm, convenio_norm), 0.0)

    def get_empleado_info(self, nombre_empleado: str) -> Dict:
        """
        Obtiene información completa de un empleado.
        
        Parámetros:
        - nombre_empleado (str): Nombre del trabajador
        
        Retorna:
        - Dict: Información del empleado o dict vacío
        """
        return self._empleado_lookup.get(nombre_empleado, {})

    def get_jefes(self) -> List[str]:
        """
        Retorna lista de supervisores únicos.
        
        Retorna:
        - List[str]: Nombres de jefes ordenados alfabéticamente
        """
        return self._jefes_list or []

    def get_all_employees(self) -> List[str]:
        """
        Retorna lista de todos los empleados.
        
        Retorna:
        - List[str]: Nombres ordenados alfabéticamente
        """
        return self._empleados_list or []
    
    def get_all_employees_with_centro(self) -> List[str]:
        """
        Retorna empleados con formato 'código_centro - NOMBRE'.
        
        Retorna:
        - List[str]: Lista formateada sin duplicados
        """        
        if self.df_trabajadores.empty:
            return []
        
        name_col = None
        for c in self.df_trabajadores.columns:
            if c.lower().strip() in ('nombre_empleado', 'nombre empleado', 'nombre'):
                name_col = c
                break
        
        if name_col is None or 'centro_preferente' not in self.df_trabajadores.columns:
            return self.get_all_employees()
        
        # Crear set para evitar duplicados
        empleados_serie = (
            self.df_trabajadores['centro_preferente'].astype(str) + 
            ' - ' + 
            self.df_trabajadores[name_col].astype(str) # <--- 1. FIX: Asegurar que el nombre también es string        )
        )
        # Obtiene los valores únicos de la Serie y los convierte a lista
        empleados_list = empleados_serie.dropna().unique().tolist()                
        return sorted(empleados_list)
    
    def get_employees_by_centro(self, codigo_centro: str) -> List[str]:
        """
        Filtra empleados por centro.
        
        Parámetros:
        - codigo_centro (str): Código del centro
        
        Retorna:
        - List[str]: Empleados del centro especificado
        """        
        if self.df_trabajadores.empty or not codigo_centro:
            return []
        
        name_col = None
        for c in self.df_trabajadores.columns:
            if c.lower().strip() in ('nombre_empleado', 'nombre empleado', 'nombre'):
                name_col = c
                break
        
        if name_col is None or 'centro_preferente' not in self.df_trabajadores.columns:
            return []
        
        filtered_df = self.df_trabajadores[
            self.df_trabajadores['centro_preferente'] == str(codigo_centro)
        ]
        
        if filtered_df.empty:
            return []
        
        return sorted(filtered_df[name_col].dropna().unique().tolist())

    def get_centros_crown(self) -> List[str]:
        """
        Retorna códigos de centros para selectbox.
        
        Retorna:
        - List[str]: [""] + lista de códigos
        """
        return [""] + [str(centro) for centro in (self._centros_list or [])]
    
    def get_centros_crown_with_names(self) -> List[str]:
        """
        Retorna centros con formato 'Código - Nombre'.
        
        Retorna:
        - List[str]: Lista formateada para display
        """        
        if self.centros_lookup_df.empty:
            return [""]
        return [""] + sorted(self.centros_lookup_df['nombre_centro_display'].tolist())

# =============================================================================
# TABLA OPTIMIZADA CON PAGINACIÓN
# =============================================================================

class OptimizedTablaIncidencias:
    """
    Gestiona la interfaz de usuario para registro y edición de incidencias.
    
    Constantes:
    - ROWS_PER_PAGE = 50: Filas por página en la tabla
    
    Atributos:
    - data_manager: Referencia al gestor de datos
    """
    ROWS_PER_PAGE = 50

    def __init__(self, data_manager: OptimizedDataManager):
        """
        Inicializa la tabla y variables de sesión.
        
        Parámetros:
        - data_manager: Instancia del gestor de datos
        """
        self.data_manager = data_manager
        if 'selected_crown_code_origen' not in st.session_state:
            st.session_state.selected_crown_code_origen = ""
        if 'selected_crown_code_destino' not in st.session_state:
            st.session_state.selected_crown_code_destino = ""
        if 'selected_trabajadores_multi' not in st.session_state:
            st.session_state.selected_trabajadores_multi = []

    def render(self, selected_jefe: str) -> None:
        """
        Renderiza la interfaz completa de incidencias.
        
        Parámetros:
        - selected_jefe (str): Supervisor seleccionado
        
        Componentes:
        - Tabs para métodos de entrada
        - Tabla paginada de incidencias
        """
        st.header("📋 Registro de Incidencias de Personal")

        incidencias = st.session_state.incidencias

        # TABS para diferentes métodos de entrada
        tab1, tab2 = st.tabs([
            "🎯 Por Centro",
            "👤 Por Trabajador"
        ])
        
        with tab1:
            self._render_method_by_centro(selected_jefe)
        
        with tab2:
            self._render_method_by_trabajador(selected_jefe)

        if incidencias:
            st.markdown("---")
            self._render_main_table_paginated(incidencias, selected_jefe)
        else:
            st.info("💡 No hay incidencias registradas. Usa las pestañas superiores para agregar.")

    def _render_method_by_centro(self, selected_jefe: str):
        """
        Tab 1: Registro masivo por centro.
        
        Funcionalidad:
        - Seleccionar centro origen y destino
        - Agregar todos los trabajadores del centro
        - Agregar trabajador individual
        
        Parámetros:
        - selected_jefe (str): Supervisor actual
        """
        st.subheader("🎯 Registro por Centro Crown")
        st.info("💡 **Ideal para:** Registrar incidencias cuando múltiples trabajadores del mismo centro cubren en otro centro")
        
        centros_lookup_df = self.data_manager.centros_lookup_df
        
        if centros_lookup_df.empty:
            st.warning("No se pudo cargar el maestro de centros.")
            return
        
        centros_display_list = [""] + sorted(centros_lookup_df['nombre_centro_display'].tolist())
        
        col1, col2 = st.columns(2)
        
        with col1:
            st.markdown("**1️⃣ Centro de Origen**")
            selected_center_origen_display = st.selectbox(
                "Selecciona el centro de origen:",
                centros_display_list,
                key="method1_centro_origen"
            )
            
            if selected_center_origen_display:
                selected_row = centros_lookup_df[centros_lookup_df['nombre_centro_display'] == selected_center_origen_display]
                if not selected_row.empty:
                    crown_origen = str(selected_row['cod_centro_preferente'].iloc[0])
                    empleados_centro = self.data_manager.get_employees_by_centro(crown_origen)
                    
                    if empleados_centro:
                        st.success(f"✅ {len(empleados_centro)} trabajadores encontrados")
                    else:
                        st.warning("⚠️ No hay trabajadores en este centro")
                        return
                else:
                    return
            else:
                st.info("👆 Selecciona un centro de origen")
                return
        
        with col2:
            st.markdown("**2️⃣ Centro de Destino**")
            selected_center_destino_display = st.selectbox(
                "Selecciona el centro destino:",
                centros_display_list,
                key="method1_centro_destino"
            )
            
            if selected_center_destino_display:
                selected_row_dest = centros_lookup_df[centros_lookup_df['nombre_centro_display'] == selected_center_destino_display]
                if not selected_row_dest.empty:
                    crown_destino = str(selected_row_dest['cod_centro_preferente'].iloc[0])
                    st.success(f"✅ Destino: {crown_destino}")
                else:
                    crown_destino = ""
            else:
                crown_destino = ""
                st.info("👆 Selecciona un centro destino")
        
        # Reemplaza desde la línea ~598 hasta ~647
        st.markdown("---")
        st.markdown("### 3️⃣ Agregar a todos los trabajadores del Centro")

        # Botón PRINCIPAL para agregar todos
        if st.button("➕ Añadir TODO el Centro ", 
                    use_container_width=True, 
                    type="primary",
                    help="Agrega una incidencia para CADA trabajador del centro de origen a la Crown Destino."):
            
            if crown_destino and empleados_centro:
                self._add_all_employees_from_centro(empleados_centro, selected_jefe, crown_origen, crown_destino)
            else:
                st.warning("⚠️ Debes seleccionar un Centro de Origen (con trabajadores) y un Crown Destino.")

        st.markdown("---")
        st.markdown("### 4️⃣ Agregar Trabajador Individual (Opcional)")

        # Selector de trabajador individual
        trabajador_individual = st.selectbox(
            "Selecciona un trabajador:",
            [""] + empleados_centro if selected_center_origen_display else [""],
            key="method1_trabajador_individual",
            help="Selecciona un trabajador específico si no quieres agregar a todos."
        )

        # Botón SECUNDARIO para agregar individual
        if st.button("➕ Añadir Trabajador Individual", 
                    use_container_width=True,
                    disabled=not trabajador_individual,
                    help="Agrega una incidencia solo para el trabajador seleccionado."): 
            
            if trabajador_individual and crown_destino:
                self._add_incidencia(trabajador_individual, 1, selected_jefe, crown_origen, crown_destino)
            else:
                st.warning("⚠️ Selecciona un trabajador y el Crown Destino")

    def _render_method_by_trabajador(self, selected_jefe: str):
        """
        Tab 2: Registro individual por trabajador.
        
        Funcionalidad:
        - Seleccionar un trabajador
        - Definir múltiples destinos
        - Crear N incidencias para el mismo trabajador
        
        Parámetros:
        - selected_jefe (str): Supervisor actual
        """
        st.subheader("👤 Registro por Trabajador")
        st.info("💡 **Ideal para:** Un trabajador que tiene múltiples incidencias en diferentes centros destino durante el mes")
        
        empleados_con_centro = self.data_manager.get_all_employees_with_centro()
        centros_lookup_df = self.data_manager.centros_lookup_df
        centros_display_list = [""] + centros_lookup_df['nombre_centro_display'].tolist()
        
        st.markdown("**1️⃣ Selecciona el Trabajador**")
        
        col1, col2 = st.columns([3, 1])
        with col1:
            trabajador_con_centro = st.selectbox(
                "Trabajador:",
                [""] + empleados_con_centro,
                key="method2_trabajador",
                help="Formato: Código Centro - Nombre Trabajador"
            )
        
        if not trabajador_con_centro:
            st.info("👆 Selecciona un trabajador para continuar")
            return
        
        if " - " in trabajador_con_centro:
            cod_centro_visual, nombre_trabajador = trabajador_con_centro.split(" - ", 1)
        else:
            nombre_trabajador = trabajador_con_centro
            cod_centro_visual = ""
        
        empleado_info = self.data_manager.get_empleado_info(nombre_trabajador)
        if empleado_info:
            nombre_centro_pref = empleado_info.get('nombre_centro_preferente', '')
            if nombre_centro_pref:
                st.caption(f"🏢 Centro: {nombre_centro_pref}")
        
        st.markdown("---")
        st.markdown("**2️⃣ Define las Incidencias (Solo Centro Destino)**")
        st.caption("El origen se asigna automáticamente del centro preferente del trabajador.")
        
        num_incidencias = st.number_input(
            "¿Cuántas incidencias diferentes tuvo este trabajador?",
            min_value=1,
            max_value=10,
            value=1,
            key="method2_num_incidencias",
            help="Número de registros con diferentes centros destino"
        )
        
        incidencias_config = []
        
        for i in range(int(num_incidencias)):
            with st.expander(f"📍 Incidencia #{i+1}", expanded=(i==0)):
                destino = st.selectbox(
                    "Centro Destino:",
                    centros_display_list,
                    key=f"method2_destino_{i}",
                    help="Selecciona el centro donde el trabajador irá a cubrir"
                )
                
                if destino:
                    destino_code = centros_lookup_df[centros_lookup_df['nombre_centro_display'] == destino]['cod_centro_preferente'].iloc[0]
                    incidencias_config.append({
                        'destino': str(destino_code)
                    })
                    st.success(f"✅ Destino: {destino}")
        
        if st.button(f"➕ Añadir {len(incidencias_config)} Incidencia(s) para {nombre_trabajador}", type="primary", use_container_width=True):
            if incidencias_config:
                for config in incidencias_config:
                    self._add_incidencia(
                        nombre_trabajador,
                        1,
                        selected_jefe,
                        "",
                        config['destino']
                    )
                st.success(f"✅ Agregadas {len(incidencias_config)} incidencias para {nombre_trabajador}")
            else:
                st.warning("⚠️ Completa al menos una incidencia con centro destino")

    def _add_incidencia(self, nombre_trabajador: str, num_rows: int, selected_jefe: str, crown_origen: str, crown_destino: str) -> None:
        """
        Añade una o más incidencias para un trabajador.
        
        Parámetros:
        - nombre_trabajador (str): Nombre del empleado
        - num_rows (int): Número de filas a crear
        - selected_jefe (str): Supervisor
        - crown_origen (str): Centro origen
        - crown_destino (str): Centro destino
        """        
        if not nombre_trabajador:
            st.warning("⚠️ Por favor, selecciona un trabajador.")
            return

        incidents = st.session_state.incidencias

        for _ in range(num_rows):
            incidencia = Incidencia(imputacion_nomina=st.session_state.selected_imputacion)
            self._actualizar_datos_empleado(incidencia, nombre_trabajador, selected_jefe, crown_origen, crown_destino)
            incidents.append(incidencia)

        st.session_state.incidencias = incidents
        st.success(f"✅ Agregadas {num_rows} fila(s) para {nombre_trabajador}")
    
    def _add_all_employees_from_centro(self, empleados: List[str], selected_jefe: str, crown_origen: str, crown_destino: str) -> None:
        """
        Añade incidencias para todos los empleados de un centro.
        
        Parámetros:
        - empleados (List[str]): Lista de nombres
        - selected_jefe (str): Supervisor
        - crown_origen (str): Centro origen
        - crown_destino (str): Centro destino
        """        
        if not empleados:
            st.warning("⚠️ No hay empleados para agregar.")
            return
        
        incidents = st.session_state.incidencias
        new_incidents = []
        for empleado in empleados:
            incidencia = Incidencia(imputacion_nomina=st.session_state.selected_imputacion)
            self._actualizar_datos_empleado(incidencia, empleado, selected_jefe, crown_origen, crown_destino)
            new_incidents.append(incidencia)

        incidents.extend(new_incidents)
        st.session_state.incidencias = incidents
        st.success(f"✅ Agregados {len(new_incidents)} trabajadores del centro {crown_origen}")

    def _actualizar_datos_empleado(self, incidencia: Incidencia, nombre_trabajador: str, jefe: str, crown_origen: str, crown_destino: str):
        """
        Actualiza datos de incidencia con info del empleado.
        
        Parámetros:
        - incidencia (Incidencia): Objeto a actualizar
        - nombre_trabajador (str): Nombre del empleado
        - jefe (str): Supervisor
        - crown_origen (str): Centro origen
        - crown_destino (str): Centro destino
        
        Actualiza:
        - Categoría, servicio, convenio
        - Centro preferente
        - Coste hora
        - Nombre del centro destino
        """        
        if nombre_trabajador:
            empleado_info = self.data_manager.get_empleado_info(nombre_trabajador)
            if empleado_info:
                incidencia.trabajador = empleado_info.get('nombre_empleado', '')
                incidencia.categoria = empleado_info.get('cat_empleado', '')
                incidencia.servicio = empleado_info.get('servicio', '')
                
                centro_pref = empleado_info.get('centro_preferente', '')
                incidencia.centro_preferente = str(centro_pref) if centro_pref else ""
                
                incidencia.codigo_crown_origen = str(centro_pref) if centro_pref else ""
                incidencia.cod_reg_convenio = empleado_info.get('cod_reg_convenio', '')
                incidencia.nombre_jefe_ope = empleado_info.get('nombre_jefe_ope', 'N/A')
                
                if crown_destino:
                    incidencia.codigo_crown_destino = str(crown_destino)
                    
                    df_centros_lookup = self.data_manager.centros_lookup_df
                    match = df_centros_lookup[df_centros_lookup['cod_centro_preferente'] == str(crown_destino)]
                    if not match.empty:
                        incidencia.nombre_crown_destino = match['desc_centro_preferente'].iloc[0]
                    else:
                        incidencia.nombre_crown_destino = ""
                else:
                    incidencia.codigo_crown_destino = incidencia.codigo_crown_origen
                    df_centros_lookup = self.data_manager.centros_lookup_df
                    match = df_centros_lookup[df_centros_lookup['cod_centro_preferente'] == incidencia.codigo_crown_origen]
                    if not match.empty:
                        incidencia.nombre_crown_destino = match['desc_centro_preferente'].iloc[0]
                    else:
                        incidencia.nombre_crown_destino = ""

                incidencia.coste_hora = float(empleado_info.get('coste_hora', 0.0) or 0.0)

    def _render_main_table_paginated(self, incidencias: List[Incidencia], selected_jefe: str) -> None:
        """
        Renderiza tabla principal con paginación.
        
        Parámetros:
        - incidencias (List[Incidencia]): Lista completa
        - selected_jefe (str): Supervisor actual
        
        Características:
        - 50 filas por página
        - Navegación numérica
        - Edición inline
        """
        st.header("📊 Tabla de Incidencias")
        
        total_incidencias = len(incidencias)
        total_pages = (total_incidencias - 1) // self.ROWS_PER_PAGE + 1 if total_incidencias > 0 else 1

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            current_page = st.number_input(
                f"Página (Total: {total_pages})",
                min_value=1,
                max_value=total_pages,
                value=st.session_state.get('current_page', 1),
                key="current_page"
            )

        start_idx = (current_page - 1) * self.ROWS_PER_PAGE
        end_idx = min(start_idx + self.ROWS_PER_PAGE, total_incidencias)
        incidencias_pagina = incidencias[start_idx:end_idx]

        st.info(f"Mostrando {len(incidencias_pagina)} de {total_incidencias} incidencias (página {current_page} de {total_pages})")

        self._render_table_page(incidencias_pagina, selected_jefe, start_idx)

    def _render_table_page(self, incidencias_pagina: List[Incidencia], selected_jefe: str, start_idx: int) -> None:
        """
        Renderiza una página específica de la tabla.
        
        Parámetros:
        - incidencias_pagina (List[Incidencia]): Incidencias de la página
        - selected_jefe (str): Supervisor
        - start_idx (int): Índice inicial en la lista completa
        
        Columnas editables:
        - Borrar, Trabajador, Facturable, Motivo
        - Crown Destino, Empresa Destino
        - Horas, Precios, Fecha, Observaciones
        """
        cache_key = "table_data_hash"
        current_hash = self._get_incidencias_hash(incidencias_pagina)

        if cache_key not in st.session_state or st.session_state[cache_key] != current_hash:
            precios_nocturnidad = [
                self.data_manager.get_precio_nocturnidad(inc.categoria, inc.cod_reg_convenio)
                for inc in incidencias_pagina
            ]
            df_data = [inc.to_dict(precios_nocturnidad[i]) for i, inc in enumerate(incidencias_pagina)]
            df = pd.DataFrame(df_data)

            # if not df.empty and 'Fecha' in df.columns:
            #     df['Fecha'] = df['Fecha'].apply(self._format_fecha_safe)

            text_cols = [
                "Código Crown Origen", "Código Crown Destino", "Centro preferente","Fecha","Observaciones"
            ]
            for col in text_cols:
                if col in df.columns:
                    df[col] = df[col].astype(str).replace('nan', '').replace('None', '')

            numeric_cols = [
                "Incidencia_horas", "Incidencia_precio", "Nocturnidad_horas", 
                "Precio_nocturnidad", "Traslados_total", "Coste hora empresa"
            ]
            for col in numeric_cols:
                if col in df.columns:
                    df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

            st.session_state.cached_df = df
            st.session_state[cache_key] = current_hash
        else:
            df = st.session_state.cached_df.copy()

        if df.empty:
            st.info("No hay datos para mostrar")
            return

        todos_empleados = self.data_manager.get_all_employees()
        centros_crown = self.data_manager.get_centros_crown()

        column_config = {
            "Borrar": st.column_config.CheckboxColumn("Borrar", help="Selecciona las filas a borrar", default=False),
            "Trabajador": st.column_config.SelectboxColumn("Trabajador", options=[""] + todos_empleados, required=True, width="medium"),
            "Facturable": st.column_config.SelectboxColumn("Facturable", options=["", "Sí", "No"], required=True, width="small"),
            "Motivo": st.column_config.SelectboxColumn("Motivo", options=["Absentismo", "Refuerzo", "Eventos", "Festivos y Fines de Semana", "Permiso retribuido", "Puesto pendiente de cubrir","Formación","Otros","Nocturnidad"], required=True, width="medium"),
            "Código Crown Origen": st.column_config.TextColumn("Crown Origen", disabled=True, help="Centro preferente del trabajador"),
            "Código Crown Destino": st.column_config.SelectboxColumn("Crown Destino", options=centros_crown, required=True),
            "Nombre Crown Destino": st.column_config.TextColumn("Nombre Crown Destino", disabled=True, width="medium"),
            "Empresa Destino": st.column_config.SelectboxColumn("Empresa Destino", options=["", "ALGADI","SMI","DISTEGSA"]),
            "Incidencia_horas": st.column_config.NumberColumn("Cuantía Inc.",  min_value=0),
            "Incidencia_precio": st.column_config.NumberColumn("Precio Inc.", min_value=0,format="€%.2f"),
            "Nocturnidad_horas": st.column_config.NumberColumn("Cuantía Noct.",  min_value=0),
            "Precio_nocturnidad": st.column_config.NumberColumn("Precio Noct.",  min_value=0, disabled=True, format="€%.2f"),
            "Traslados_total": st.column_config.NumberColumn("Traslados",  min_value=0),
            "Coste hora empresa": st.column_config.NumberColumn("Coste/Hora", disabled=True,  format="€%.2f"),
            "Fecha": st.column_config.TextColumn("Fecha", help="Ingresa una fecha o periodo",default="",required=True, width="medium"),
            "Observaciones": st.column_config.TextColumn("Observaciones", required=True, width="medium"),
        }

        editable_cols = [
            "Borrar", "Trabajador", "Facturable", "Motivo", "Código Crown Destino", "Empresa Destino",
            "Incidencia_horas", "Incidencia_precio", "Nocturnidad_horas", "Traslados_total",
            "Fecha", "Observaciones"
        ]
        for col in editable_cols:
            if col in df.columns:
                df[col] = df[col].astype(object)


        # Columnas a eliminar de la vista de Tablas de Incidencias    
        df = df.drop(columns=["Cod_reg_convenio", "Categoría", "Centro preferente", "Coste hora empresa","Supervisor de operaciones","Servicio", "Nombre Crown Destino"], errors="ignore")  

        edited_df = st.data_editor(
            df,
            column_config=column_config,
            num_rows="fixed",
            key=f"unificado_editor_page_{st.session_state.get('current_page', 1)}"
        )

        # ===== MODIFICACIÓN: CAMBIAR DE 2 A 3 COLUMNAS =====
        col_save, col_delete_selected, col_delete_all = st.columns([2, 2, 1])

        with col_save:
            if st.button("💾 Guardar cambios", use_container_width=True, type="primary", key="btn_save_changes"):
                self._process_page_changes(start_idx, edited_df)

        # ===== NUEVO BOTÓN =====
        with col_delete_selected:
            if st.button("🗑️ Borrar Filas Marcadas", use_container_width=True, key="btn_delete_selected"):
                self._delete_selected_rows(start_idx, edited_df)

        with col_delete_all:
            if st.button("🗑️ Borrar Todas", use_container_width=True, key="btn_delete_all"):
                if st.session_state.incidencias:
                    st.session_state.incidencias = []
                    if "table_data_hash" in st.session_state:
                        del st.session_state["table_data_hash"]
                    if "cached_df" in st.session_state:
                        del st.session_state["cached_df"]
                    st.success("✅ Todas las incidencias han sido borradas")
                    st.rerun()
                else:
                    st.info("ℹ️ No hay incidencias para borrar")
    
    def _delete_selected_rows(self, start_idx: int, edited_df: pd.DataFrame) -> None:
        """
        Elimina filas marcadas con checkbox 'Borrar'.
        
        Parámetros:
        - start_idx (int): Índice inicial
        - edited_df (pd.DataFrame): DataFrame con marcas
        
        Funcionalidad:
        - Elimina sin necesidad de guardar
        - Ajusta paginación si es necesario
        """
        incidents = st.session_state.incidencias
        edited_rows = edited_df.to_dict('records')
        
        # Crear lista de índices globales a eliminar
        indices_to_delete = []
        for i, row_data in enumerate(edited_rows):
            if row_data.get("Borrar", False):
                global_idx = start_idx + i
                indices_to_delete.append(global_idx)
        
        # Verificar si hay filas marcadas
        if not indices_to_delete:
            st.warning("⚠️ No hay filas marcadas para borrar. Marca la casilla 'Borrar' de las filas que deseas eliminar.")
            return
        
        # Eliminar las incidencias marcadas (en orden inverso para mantener índices correctos)
        deleted_count = 0
        for idx in sorted(indices_to_delete, reverse=True):
            if 0 <= idx < len(incidents):
                del incidents[idx]
                deleted_count += 1
        
        # Actualizar el estado
        st.session_state.incidencias = incidents
        
        # Limpiar caché para forzar actualización de la tabla
        if "table_data_hash" in st.session_state:
            del st.session_state["table_data_hash"]
        if "cached_df" in st.session_state:
            del st.session_state["cached_df"]
        
        # Ajustar la página actual si es necesario
        total_incidencias = len(incidents)
        if total_incidencias > 0:
            total_pages = (total_incidencias - 1) // self.ROWS_PER_PAGE + 1
            if st.session_state.get('current_page', 1) > total_pages:
                st.session_state.current_page = total_pages
        
        # Establecer flag de cambios
        st.session_state.rows_deleted = True
        
        # Mensaje de confirmación
        if deleted_count > 0:
            st.success(f"✅ {deleted_count} fila(s) eliminada(s) correctamente. Interactúa con la aplicación para ver los cambios.")

    def _format_fecha_safe(self, fecha):
        """Formateo seguro de fechas, devuelve objeto date o pd.NaT"""
        if pd.isna(fecha):
            return pd.NaT
        if isinstance(fecha, date):
            return fecha
        if isinstance(fecha, datetime):
            return fecha.date()
        if isinstance(fecha, str):
            parsed = pd.to_datetime(fecha, dayfirst=True, errors='coerce')
            return parsed.date() if not pd.isna(parsed) else pd.NaT
        return pd.NaT

    def _get_incidencias_hash(self, incidencias: List[Incidencia]) -> str:
        data = []
        for inc in incidencias:
            data.append(f"{inc.trabajador}|{inc.motivo}|{inc.fecha}|{inc.incidencia_horas}|{inc.incidencia_precio}")
        return hashlib.md5("||".join(map(str, data)).encode()).hexdigest()

    def _process_page_changes(self, start_idx: int, edited_df: pd.DataFrame) -> None:
        """
        Procesa y guarda cambios de la página actual.
        
        Parámetros:
        - start_idx (int): Índice inicial
        - edited_df (pd.DataFrame): DataFrame editado
        
        Procesamiento:
        - Mapea columnas a campos del modelo
        - Actualiza incidencias en session_state
        - Recalcula datos si cambia el trabajador
        """
        incidents_to_update = st.session_state.incidencias
        edited_rows = edited_df.to_dict('records')

        column_to_field_map = {
            "Trabajador": "trabajador",
            "Facturable": "facturable",
            "Motivo": "motivo",
            "Código Crown Origen": "codigo_crown_origen",
            "Código Crown Destino": "codigo_crown_destino",
            "Empresa Destino": "empresa_destino",
            "Incidencia_horas": "incidencia_horas",
            "Incidencia_precio": "incidencia_precio",
            "Nocturnidad_horas": "nocturnidad_horas",
            "Traslados_total": "traslados_total",
            "Coste hora empresa": "coste_hora",
            "Fecha": "fecha",
            "Observaciones": "observaciones",
            "Centro preferente": "centro_preferente",
            "Supervisor de operaciones": "nombre_jefe_ope",
            "Categoría": "categoria",
            "Servicio": "servicio",
            "Cod_reg_convenio": "cod_reg_convenio",
            "Nombre Crown Destino": "nombre_crown_destino",
        }

        new_incidents = []
        changes_made = False
        
        for i, inc in enumerate(incidents_to_update):
            is_on_current_page = start_idx <= i < start_idx + self.ROWS_PER_PAGE
            if is_on_current_page:
                local_idx = i - start_idx
                row_data = edited_rows[local_idx]

                # Si está marcado para borrar, no lo incluimos
                if row_data.get("Borrar", False):
                    changes_made = True
                    continue

                filtered_data = {}
                for col_name, value in row_data.items():
                    if col_name in column_to_field_map:
                        field_name = column_to_field_map[col_name]

                        if field_name in ("incidencia_horas", "incidencia_precio", "nocturnidad_horas", "traslados_total", "coste_hora"):
                            try:
                                filtered_data[field_name] = float(value) if value not in (None, "") else 0.0
                            except Exception:
                                filtered_data[field_name] = 0.0
                        elif field_name in ("codigo_crown_origen", "codigo_crown_destino", "centro_preferente"):
                            try:
                                if value in (None, "", np.nan, "nan", "None"):
                                    filtered_data[field_name] = ""
                                else:
                                    val_str = str(value).replace('.0', '').strip()
                                    filtered_data[field_name] = val_str
                            except Exception:
                                filtered_data[field_name] = ""
                        elif field_name == "fecha":
                            # ✅ SOLUCIÓN: Forzar el valor a un string, tratando NaN/None como cadena vacía.
                            if value is None or (isinstance(value, (float, np.number)) and np.isnan(value)):
                                filtered_data[field_name] = ""
                            else:
                                filtered_data[field_name] = str(value).strip()
                        elif field_name == "fecha":
                            # Mantener la corrección anterior: forzar a string limpio
                            if value is None or (isinstance(value, (float, np.number)) and np.isnan(value)):
                                filtered_data[field_name] = ""
                            else:
                                filtered_data[field_name] = str(value).strip()
                                
                        else:
                            # ✅ SOLUCIÓN ROBUSTA para Facturable, Motivo y otros strings
                            # Asegura que cualquier nulo (None, NaN de pandas) se guarde como cadena vacía ""
                            if value is None or (isinstance(value, (float, np.number)) and np.isnan(value)) or str(value).lower() in ('nan', 'none', ''):
                                filtered_data[field_name] = ""
                            else:
                                filtered_data[field_name] = str(value).strip()
                new_inc = Incidencia()
                # Copiar todos los atributos originales
                for attr in vars(inc):
                    setattr(new_inc, attr, getattr(inc, attr))
                
                # Aplicar los cambios
                for k, v in filtered_data.items():
                    if hasattr(inc, k) and getattr(inc, k) != v:
                        changes_made = True
                    setattr(new_inc, k, v)

                # Si cambió el trabajador, actualizar sus datos
                if new_inc.trabajador and new_inc.trabajador != inc.trabajador:
                    current_destino = new_inc.codigo_crown_destino
                    self._actualizar_datos_empleado(new_inc, new_inc.trabajador, st.session_state.selected_jefe, "", current_destino)
                    changes_made = True

                new_incidents.append(new_inc)
            else:
                new_incidents.append(inc)

        # Actualizar las incidencias
        st.session_state.incidencias = new_incidents

        # Limpiar caché para forzar regeneración en el próximo render
        if "table_data_hash" in st.session_state:
            del st.session_state["table_data_hash"]
        if "cached_df" in st.session_state:
            del st.session_state["cached_df"]
        
        # Establecer un flag para indicar que se guardaron cambios
        st.session_state.changes_saved = True
        
        # Mensaje de éxito
        if changes_made:
            st.success("✅ ¡Cambios guardados con éxito! Los cambios se reflejarán al interactuar con la aplicación.")
        else:
            st.info("ℹ️ No se detectaron cambios para guardar.")
        st.rerun()


# =============================================================================
# EXPORT MANAGER OPTIMIZADO
# =============================================================================

class OptimizedExportManager:
    """
    Gestiona la exportación de incidencias a Excel.
    """
    @staticmethod
    def export_to_excel(incidencias: List[Incidencia], data_manager: OptimizedDataManager) -> Optional[bytes]:
        """
        Exporta incidencias válidas a Excel.
        
        Parámetros:
        - incidencias (List[Incidencia]): Lista completa
        - data_manager (OptimizedDataManager): Gestor de datos
        
        Retorna:
        - bytes: Archivo Excel en memoria o None si no hay válidas
        
        Procesamiento:
        1. Filtra solo incidencias válidas
        2. Calcula precios de nocturnidad
        3. Añade columnas calculadas
        4. Genera Excel con openpyxl
        """
        incidencias_validas = [inc for inc in incidencias if inc.is_valid()]
        if not incidencias_validas:
            return None

        unique_keys = set((i.categoria, i.cod_reg_convenio) for i in incidencias_validas)
        precios_nocturnidad = {
            key: data_manager.get_precio_nocturnidad(key[0], key[1]) for key in unique_keys
        }

        data = [
            {
                'Jefe de Operaciones': inc.nombre_jefe_ope,
                'Mes imputació nómina': inc.imputacion_nomina,
                'Facturable': inc.facturable,
                'Servicio': inc.servicio,
                'Motivo': inc.motivo,
                'Trabajador': inc.trabajador,
                'Empresa Destino': inc.empresa_destino,
                'Código Crown Destino': inc.codigo_crown_destino,
                'Centro Destino': inc.nombre_crown_destino,
                'Categoria': inc.categoria,
                'Cuantía': inc.incidencia_horas,
                'Precio': inc.incidencia_precio,
                'Cuantía nocturnidad': inc.nocturnidad_horas,
                'Precio_nocturnidad': precios_nocturnidad.get((inc.categoria, inc.cod_reg_convenio), 0.0),
                'Horas traslado': inc.traslados_total,
                'coste_hora': inc.coste_hora,
                'Empresa Origen': inc.centro_preferente,
                'Código Crown Origen': inc.codigo_crown_origen,
                'Fecha': inc.fecha,
                'Observaciones': inc.observaciones,
                "cod_reg_convenio": inc.cod_reg_convenio,
                'porcen_contrato': data_manager.get_empleado_info(inc.trabajador).get('porcen_contrato', ''),
                'cod_empresa': data_manager.get_empleado_info(inc.trabajador).get('cod_empresa', ''),
                'nombre_centro': data_manager.get_empleado_info(inc.trabajador).get('nombre_centro_preferente', ''),
            }
            for inc in incidencias_validas
        ]

        df = pd.DataFrame(data)
        
        for col in ['codigo_crown_origen', 'codigo_crown_destino', 'centro_preferente']:
            if col in df.columns:
                df[col] = df[col].astype(str).replace('nan', '').replace('None', '')
        
        OptimizedExportManager._add_calculated_columns(df)
        OptimizedExportManager._add_final_calculations(df)


        # # Columnas que no se exportan
        # df = df.drop(columns=["cod_reg_convenio", "porcen_contrato","categoria",
        #                     "centro_preferente","cod_empresa","nombre_centro","73_plus_sustitucion",
        #                     "72_incentivos","70_71_festivos","74_plus_nocturnidad"], errors="ignore")

        excel_buffer = io.BytesIO()
        df.to_excel(excel_buffer, index=False, engine='openpyxl')
        excel_buffer.seek(0)
        return excel_buffer.getvalue()

    @staticmethod
    def _add_calculated_columns(df: pd.DataFrame) -> None:
        """
        Añade columnas calculadas según motivo.
        
        Parámetros:
        - df (pd.DataFrame): DataFrame a procesar
        
        Columnas añadidas:
        - 73_plus_sustitucion
        - 72_incentivos
        - 70_71_festivos
        - 74_plus_nocturnidad
        
        Lógica:
        - Mapea motivos a códigos de cuenta
        - Calcula totales según categoría
        """
        try:
            df_motivos = _load_single_sheet('data/maestros.xlsx', 'cuenta_motivos', _get_file_hash('data/maestros.xlsx'))
            if df_motivos is None or df_motivos.empty:
                df_motivos = pd.DataFrame({'Motivo': [], 'desc_cuenta': []})
            else:
                df_motivos['Motivo'] = df_motivos.get('Motivo', pd.Series([], dtype=str)).fillna('')
                df_motivos['desc_cuenta'] = df_motivos.get('desc_cuenta', pd.Series([], dtype=str)).fillna('')
        except Exception:
            df_motivos = pd.DataFrame({'Motivo': [], 'desc_cuenta': []})

        motivo_to_cuenta = {}
        for _, row in df_motivos.iterrows():
            motivo = row.get('Motivo', '')
            desc_cuenta = str(row.get('desc_cuenta', ''))
            if '70/71' in desc_cuenta:
                codigo_cuenta = '70_71'
            elif desc_cuenta.startswith('73'):
                codigo_cuenta = '73'
            elif desc_cuenta.startswith('72'):
                codigo_cuenta = '72'
            elif desc_cuenta.startswith('74'):
                codigo_cuenta = '74'
            else:
                codigo_cuenta = None
            if codigo_cuenta:
                motivo_to_cuenta[motivo] = codigo_cuenta

        df['cuenta_codigo'] = df.get('Motivo', '').map(motivo_to_cuenta).fillna('Otros')
        df['total_incidencia'] = df.get('Precio', 0.0) * df.get('Cuantía', 0.0)

        df['73_plus_sustitucion'] = np.where(df['cuenta_codigo'] == '73', df['total_incidencia'], 0.0)
        df['72_incentivos'] = np.where(df['cuenta_codigo'] == '72', df['total_incidencia'], 0.0)
        df['70_71_festivos'] = np.where(df['cuenta_codigo'] == '70_71', df['total_incidencia'], 0.0)
        df['74_plus_nocturnidad'] = 0.0

        df.drop(['total_incidencia', 'cuenta_codigo'], axis=1, inplace=True, errors='ignore')

    @staticmethod
    def _add_final_calculations(df: pd.DataFrame) -> None:
        """
        Calcula costes totales con Seguridad Social.
        
        Parámetros:
        - df (pd.DataFrame): DataFrame a procesar
        
        Cálculos:
        - Coste incidencias = horas × precio
        - Coste nocturnidad = horas_noct × precio_noct
        - Coste con SS = (incidencias + nocturnidad) × 1.3195
        - Coste total = coste_con_ss + traslados
        """
        if 'Precio_nocturnidad' in df.columns and 'Cuantía nocturnidad' in df.columns:
            df['74_plus_nocturnidad'] = df['Precio_nocturnidad'] * df['Cuantía nocturnidad']
        else:
            df['74_plus_nocturnidad'] = 0.0

        required_cols_coste = ['Cuantía', 'Precio', 'Cuantía nocturnidad', 'Precio_nocturnidad', 'Horas traslado']
        if all(col in df.columns for col in required_cols_coste):
            coste_incidencias = df['Cuantía'] * df['Precio']
            coste_nocturnidad = df['Cuantía nocturnidad'] * df['Precio_nocturnidad']
            coste_con_ss = (coste_incidencias + coste_nocturnidad) * 1.3195
            df['Coste_total'] = coste_con_ss + df['Horas traslado']
        else:
            df['Coste_total'] = 0.0

# =============================================================================
# APLICACIÓN PRINCIPAL
# =============================================================================

class OptimizedIncidenciasApp:
    """
    Aplicación principal que orquesta todos los componentes.
    """
    def __init__(self):
        """
        Inicializa la aplicación y session_state.
        
        Variables de sesión:
        - app_initialized_optimized: Flag de inicio
        - selected_jefe: Supervisor actual
        - selected_imputacion: Mes seleccionado
        - incidencias: Lista de incidencias
        - data_manager: Instancia del gestor
        """
        if 'app_initialized_optimized' not in st.session_state:
            st.session_state.app_initialized_optimized = True
            st.session_state.selected_jefe = ""
            st.session_state.selected_imputacion = ""
            st.session_state.incidencias = []
            st.session_state.data_manager = OptimizedDataManager()
            st.session_state.selected_crown_code_origen = ""
            st.session_state.selected_crown_code_destino = ""

    def run(self):
        """
        Punto de entrada principal de la aplicación.
        
        Flujo:
        1. Verifica carga de datos
        2. Renderiza header con selectores
        3. Muestra tabla si hay jefe e imputación
        4. Habilita exportación si hay datos
        """
        data_manager = st.session_state.data_manager

        if data_manager.file_hash == "FILE_NOT_FOUND":
            st.error("⚠️ No se pudieron cargar los datos. Verifica que el archivo 'data/maestros.xlsx' exista.")
            return

        self._render_header(data_manager)

        if not st.session_state.selected_jefe or not st.session_state.selected_imputacion:
            st.warning("⚠️ Por favor, selecciona la imputación de nómina y un jefe para comenzar.")
            return

        tabla_optimizada = OptimizedTablaIncidencias(data_manager)
        tabla_optimizada.render(st.session_state.selected_jefe)

        self._render_export_section(data_manager)

    def _render_header(self, data_manager: OptimizedDataManager):
        """
        Renderiza cabecera con logo y selectores principales.
        
        Parámetros:
        - data_manager: Gestor de datos
        
        Componentes:
        - Logo empresa
        - Selector de mes (imputación)
        - Selector de supervisor
        
        Comportamiento:
        - Cambiar mes/jefe resetea las incidencias
        """
        col_title, col_logo = st.columns([0.8, 0.2]) 

        with col_title:
            st.title("Plantilla de Registro de Incidencias")
        
        with col_logo:
            st.image("assets/logo.png", width=200)

        imputacion_opciones = [""] + ["01-Enero", "02-Febrero", "03-Marzo", "04-Abril", "05-Mayo", "06-Junio", "07-Julio", "08-Agosto", "09-Septiembre", "10-Octubre", "11-Noviembre", "12-Diciembre"]
        jefes_list = data_manager.get_jefes()

        col1, col2 = st.columns(2)
        with col1:
            new_imputacion = st.selectbox(
                "📅 Imputación Nómina:",
                imputacion_opciones,
                index=imputacion_opciones.index(st.session_state.selected_imputacion) if st.session_state.selected_imputacion in imputacion_opciones else 0,
                key="imputacion_nomina_main"
            )

        with col2:
            new_jefe = st.selectbox(
                "👤 Seleccionar nombre de supervisor:",
                [""] + jefes_list,
                index=jefes_list.index(st.session_state.selected_jefe) + 1 if st.session_state.selected_jefe in jefes_list else 0,
                key="jefe_main"
            )

        if new_imputacion != st.session_state.selected_imputacion:
            st.session_state.selected_imputacion = new_imputacion
            st.session_state.incidencias = []
            st.session_state.selected_crown_code_origen = ""
            st.session_state.selected_crown_code_destino = ""

        if new_jefe != st.session_state.selected_jefe:
            st.session_state.selected_jefe = new_jefe
            st.session_state.incidencias = []
            st.session_state.selected_crown_code_origen = ""
            st.session_state.selected_crown_code_destino = ""

    def _render_export_section(self, data_manager: OptimizedDataManager):
        """
        Renderiza sección de exportación con métricas.
        
        Parámetros:
        - data_manager: Gestor de datos
        
        Muestra:
        - Total incidencias
        - Incidencias válidas/incompletas
        - Métricas económicas
        - Botón de descarga Excel
        
        Validaciones:
        - Verifica campos obligatorios
        - Muestra diagnóstico si hay problemas
        """
        
        st.markdown("---")
        st.header("📊 Exportar Datos")
        
        # Mostrar si hay cambios guardados recientemente
        if st.session_state.get('changes_saved', False):
            st.info("ℹ️ Cambios guardados. Los datos están actualizados.")
            st.session_state.changes_saved = False
        
        if st.session_state.get('rows_deleted', False):
            st.info("ℹ️ Filas eliminadas. Los datos están actualizados.")
            st.session_state.rows_deleted = False

        # Obtener todas las incidencias del estado actual
        todas_incidencias = st.session_state.incidencias
        
        # Mostrar contador de incidencias
        col1, col2, col3 = st.columns(3)
        with col1:
            st.metric("📝 Total Incidencias", len(todas_incidencias))
        
        if not todas_incidencias:
            st.warning("⚠️ No hay incidencias registradas.")
            st.info("💡 Añade incidencias usando las pestañas 'Por Centro' o 'Por Trabajador'")
            return
        
        # Filtrar incidencias válidas (con todos los campos obligatorios)
        incidencias_validas = [inc for inc in todas_incidencias if inc.is_valid()]
        
        with col2:
            st.metric("✅ Incidencias Válidas", len(incidencias_validas))
        
        with col3:
            incompletas = len(todas_incidencias) - len(incidencias_validas)
            if incompletas > 0:
                st.metric("⚠️ Incompletas", incompletas)
        
        # Si hay incidencias pero ninguna es válida, mostrar diagnóstico
        if todas_incidencias and not incidencias_validas:
            st.error("❌ No hay incidencias válidas para exportar")
            
            with st.expander("🔍 Ver por qué las incidencias no son válidas", expanded=True):
                st.write("**Campos obligatorios para exportar:**")
                st.write("✅ Trabajador | ✅ Imputación Nómina | ✅ Facturable | ✅ Motivo")
                st.write("✅ Código Crown Destino | ✅ Fecha ")
                st.write("---")
                
                # Mostrar las primeras 3 incidencias como ejemplo
                for i, inc in enumerate(todas_incidencias[:3]):
                    st.write(f"**Incidencia {i+1}:**")
                    problemas = []
                    if not inc.trabajador: problemas.append("❌ Falta Trabajador")
                    if not inc.imputacion_nomina: problemas.append("❌ Falta Imputación")
                    if not inc.facturable: problemas.append("❌ Falta Facturable")
                    if not inc.motivo: problemas.append("❌ Falta Motivo")
                    if not inc.codigo_crown_destino: problemas.append("❌ Falta Crown Destino")
                    if not inc.fecha: problemas.append("❌ Falta Fecha")
                    # if not inc.observaciones: problemas.append("❌ Falta Observaciones")
                    
                    if problemas:
                        for p in problemas:
                            st.write(f"  {p}")
                    else:
                        st.write("  ✅ Todos los campos completos")
                
                if len(todas_incidencias) > 3:
                    st.write(f"... y {len(todas_incidencias) - 3} incidencias más")
            
            st.info("💡 Completa los campos faltantes en la tabla y guarda los cambios para poder exportar")
            return

        # Si hay incidencias válidas, mostrar métricas y botón de descarga
        st.success(f"✅ {len(incidencias_validas)} incidencias listas para exportar")
        
        with st.spinner("Calculando métricas..."):
            metricas = self._calculate_metrics_optimized(incidencias_validas, data_manager)

        # Mostrar métricas
        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("📋 Total Incidencias", f"€{metricas['total_incidencias']:,.2f}")
        with col2:
            st.metric("🌙 Total Nocturnidad", f"€{metricas['total_nocturnidad']:,.2f}")
        with col3:
            st.metric("🚗 Total Traslados", f"€{metricas['total_traslados']:,.2f}")
        with col4:
            st.metric("💰 Total", f"€{metricas['total_simple']:,.2f}")
        with col5:
            st.metric("📊 Total coste", f"€{metricas['total_con_ss']:,.2f}")

        # Generar Excel
        with st.spinner("Generando Excel..."):
            try:
                excel_data = OptimizedExportManager.export_to_excel(incidencias_validas, data_manager)

                if excel_data:
                    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                    filename = f"incidencias_{str(st.session_state.selected_jefe).replace(' ', '_')}_{timestamp}.xlsx"

                    # BOTÓN DE DESCARGA
                    st.download_button(
                        label="💾 Descargar Excel de Incidencias",
                        data=excel_data,
                        file_name=filename,
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        help=f"Descarga {len(incidencias_validas)} incidencias válidas en formato Excel (.xlsx)"
                    )

                    st.success(f"✅ Archivo listo para descargar: {len(incidencias_validas)} incidencias válidas")
                else:
                    st.error("Error al generar el archivo Excel")
                    
            except Exception as e:
                st.error(f"Error durante la exportación: {str(e)}")
                with st.expander("Ver detalles del error"):
                    st.exception(e)


    def _calculate_metrics_optimized(self, incidencias_validas: List[Incidencia], data_manager: OptimizedDataManager) -> Dict[str, float]:
        """
        Calcula métricas económicas con caché.
        
        Parámetros:
        - incidencias_validas: Solo incidencias completas
        - data_manager: Gestor de datos
        
        Retorna Dict con:
        - total_incidencias: Coste de horas
        - total_nocturnidad: Coste nocturno
        - total_traslados: Coste traslados
        - total_simple: Suma sin SS
        - total_con_ss: Total con Seguridad Social (×1.3195)
        """
        precio_cache = {}
        monto_total_incidencias = 0.0
        monto_total_nocturnidad = 0.0
        monto_total_traslados = 0.0

        for inc in incidencias_validas:
            monto_total_incidencias += (inc.incidencia_precio or 0.0) * (inc.incidencia_horas or 0.0)
            key = (inc.categoria, inc.cod_reg_convenio)
            if key not in precio_cache:
                precio_cache[key] = data_manager.get_precio_nocturnidad(inc.categoria, inc.cod_reg_convenio)
            precio_noct = precio_cache[key]
            monto_total_nocturnidad += precio_noct * (inc.nocturnidad_horas or 0.0)
            monto_total_traslados += (inc.traslados_total or 0.0) * (inc.coste_hora or 0.0)

        total_simple = monto_total_incidencias + monto_total_nocturnidad + monto_total_traslados
        total_con_ss = (monto_total_incidencias + monto_total_nocturnidad) * 1.3195 + monto_total_traslados

        return {
            'total_incidencias': monto_total_incidencias,
            'total_nocturnidad': monto_total_nocturnidad,
            'total_traslados': monto_total_traslados,
            'total_simple': total_simple,
            'total_con_ss': total_con_ss
        }

# =============================================================================
# EJECUCIÓN
# =============================================================================

if __name__ == "__main__":
    
    ## 🔄 Flujo de Datos

#     '''
#         1. INICIO
#         ├── Carga maestros.xlsx
#         ├── Construye cachés (tarifas, empleados)
#         └── Inicializa session_state

#         2. ENTRADA DE DATOS
#         ├── Método 1: Por Centro
#         │   ├── Selecciona origen/destino
#         │   └── Agrega todos o individual
#         └── Método 2: Por Trabajador
#             ├── Selecciona empleado
#             └── Define N destinos

#         3. EDICIÓN
#         ├── Tabla paginada (50 filas)
#         ├── Edición inline
#         ├── Validación automática
#         └── Guardado en session_state

#         4. EXPORTACIÓN
#         ├── Filtra incidencias válidas
#         ├── Calcula tarifas nocturnidad
#         ├── Añade columnas calculadas
#         └── Genera Excel descargable
#     '''

#     ## 📊 Estructura de Datos Clave

#     ### Archivo maestros.xlsx
#     '''
#     Hojas requeridas:
#     ├── Centros
#     │   ├── cod_centro_preferente
#     │   ├── desc_centro_preferente
#     │   ├── nombre_jefe_ope
#     │   └── fecha_baja_centro
#     │
#     ├── Trabajadores
#     │   ├── nombre_empleado
#     │   ├── centro_preferente
#     │   ├── cat_empleado
#     │   ├── cod_reg_convenio
#     │   └── coste_hora
#     │
#     ├── tarifas_incidencias
#     │   ├── Descripción (categoría)
#     │   ├── cod_convenio
#     │   └── tarifa_noct
#     │
#     └── cuenta_motivos
#         ├── Motivo
#         └── desc_cuenta
# '''
    _add_logo_and_css()
    app = OptimizedIncidenciasApp()
    app.run()

    