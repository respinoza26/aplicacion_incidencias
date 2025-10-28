"""
Aplicación de Gestión de Incidencias con Estructura Optimizada
"""

import streamlit as st
import pandas as pd
import subprocess
import sys
import json
from pathlib import Path
from datetime import datetime, date
import shutil
from typing import List, Dict, Any, Optional, Tuple
import io
import os
from dataclasses import dataclass, field

# ============================================================================
# CONFIGURACIÓN Y RUTAS
# ============================================================================

@st.cache_data
def load_config():
    """Carga configuración desde config.json"""
    config_file = Path(__file__).parent / "config.json"
    try:
        with open(config_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        st.error("Error: No se encontró config.json")
        return {}

CFG = load_config()

# Configurar Streamlit (Solo si CFG es válido)
if CFG:
    st.set_page_config(
        page_title=CFG.get('app', {}).get('titulo', 'Gestión de Incidencias'),
        page_icon=CFG.get('app', {}).get('icono', '📋'),
        layout=CFG.get('app', {}).get('layout', 'wide')
    )
    
    BASE_DIR = Path(__file__).parent
    DATA_DIR = BASE_DIR / CFG['rutas']['data']
    PERIODOS_DIR = BASE_DIR / CFG['rutas']['periodos']
    MAESTROS_FILE = BASE_DIR / CFG['rutas']['maestros']
    BACKUP_DIR = BASE_DIR / CFG['rutas']['backups']
    GENERATE_SCRIPT = BASE_DIR / "generate_maestros.py"
    ROWS_PER_PAGE = CFG['app']['filas_por_pagina']
    
    # Crear directorios
    for d in [DATA_DIR, PERIODOS_DIR, BACKUP_DIR]:
        d.mkdir(parents=True, exist_ok=True)
else:
    # Salir si la configuración falló
    sys.exit()

# ============================================================================
# MODELO DE DATOS
# ============================================================================

@dataclass
class Incidencia:
    """Clase para almacenar datos de una incidencia de forma estructurada."""
    # Datos de identificación
    nombre_trabajador: str
    fecha_incidencia: date
    # Datos del formulario
    tipo_incidencia: str
    horas_base: float
    horas_nocturnidad: float
    traslados_total: float
    incidencia_precio: float
    # Datos extraídos del maestro de trabajadores
    cod_empleado: str = ""
    coste_hora: float = 0.0
    categoria: str = ""
    cod_reg_convenio: str = ""
    # Mapeo y validación
    cuenta_contable: str = ""
    
    def is_valid(self) -> bool:
        """Verifica la validez mínima de la incidencia."""
        return bool(self.nombre_trabajador and self.fecha_incidencia)


# ============================================================================
# CLASES DE GESTIÓN DE DATOS OPTIMIZADAS
# ============================================================================

# ============================================================================
# CLASES DE GESTIÓN DE DATOS OPTIMIZADAS
# ============================================================================

class OptimizedDataManager:
    
    def __init__(self):
        # Propiedades de Carga Lenta (Lazy Loading)
        self._df_centros = None
        self._df_trabajadores = None
        self._df_motivos = None
        self._df_tarifas = None
        
        # Tablas de Lookup para O(1)
        self._tarifa_lookup = None
        self._empleado_lookup = None
        self._jefes_list = None
        self._empleados_list = None
        self._centros_list = None
        
        # Aseguramos que el cache se construya en la inicialización (si el maestro existe)
        if MAESTROS_FILE.exists():
            self._ensure_cache_built()
            
    # --- PROPIEDADES DE CARGA LENTA (DataFrames) ---
    @property
    def df_centros(self) -> pd.DataFrame:
        """Carga perezosa del maestro de centros, asegurando columna de jefe."""
        if self._df_centros is None:
            # Llama a la función cacheada que carga la hoja 'maestro_centros'
            df = self._load_single_sheet('maestro_centros') 
            
            # --- FIX: Lógica para asegurar la columna de Jefe ---
            EXPECTED_JEFES_COL = 'nombre_jefe_ope'
            
            if not df.empty:
                if EXPECTED_JEFES_COL not in df.columns:
                    # Buscar una columna alternativa que contenga 'jefe' o 'supervisor'
                    found_col = next((
                        col for col in df.columns 
                        if 'jefe' in col.lower() or 'supervisor' in col.lower()
                    ), None)
                    
                    if found_col:
                        # Renombrar la columna encontrada al nombre esperado
                        df.rename(columns={found_col: EXPECTED_JEFES_COL}, inplace=True)
                    # Si no se encuentra, df seguirá sin 'nombre_jefe_ope', pero el código de abajo manejará la excepción
                
                # Asegurar que codigo_centro es string para el merge
                if 'codigo_centro' in df.columns:
                    df['codigo_centro'] = df['codigo_centro'].astype(str)
            
            self._df_centros = df
            
        return self._df_centros

    @property
    def df_motivos(self) -> pd.DataFrame:
        if self._df_motivos is None:
            self._df_motivos = self._load_single_sheet('cuenta_motivos')
        return self._df_motivos
        
    @property
    def df_tarifas(self) -> pd.DataFrame:
        if self._df_tarifas is None:
            self._df_tarifas = self._load_single_sheet('tarifas_incidencias') 
        return self._df_tarifas

    @property
    def df_trabajadores(self) -> pd.DataFrame:
        """Carga perezosa y fusión de datos de trabajadores con centros."""
        if self._df_trabajadores is None:
            df = self._load_single_sheet('Trabajadores') 
            
            # Cálculo de coste_hora (Lógica anterior)
            if "Salario/hora" in df.columns:
                mult = CFG['transformaciones']['multiplicador_ss']
                df["coste_hora"] = (df["Salario/hora"] * mult).round(2)
            
            # --- Lógica de Merge con Centros para obtener JEFE Y NOMBRE DE CENTRO ---
            if not df.empty and not self.df_centros.empty and 'centro_preferente' in df.columns:
                
                df['centro_preferente'] = df['centro_preferente'].astype(str).str.split('.').str[0]
                self.df_centros['codigo_centro'] = self.df_centros['codigo_centro'].astype(str)

                # Merge: Añade 'nombre_jefe_ope' y 'nombre_centro' al df de trabajadores
                df = pd.merge(
                    df,
                    self.df_centros[['codigo_centro', 'nombre_jefe_ope', 'nombre_centro']],
                    left_on='centro_preferente',
                    right_on='codigo_centro',
                    how='left',
                    suffixes=('', '_centro_pref')
                ).rename(columns={
                    'nombre_jefe_ope': 'nombre_jefe_ope',
                    'nombre_centro_centro_pref': 'nombre_centro_preferente'
                }).drop(columns=['codigo_centro'])
            
            self._df_trabajadores = df
            
        return self._df_trabajadores

    # --- FUNCIONES DE CARGA Y LOOKUP CACHEADAS ---

    # NOTA: _load_single_sheet debe seguir estando definida fuera de esta clase

    @st.cache_data(ttl=CFG['app']['cache_segundos'])
    def _build_tarifa_lookup(_self) -> Dict[Tuple[str, str], float]:
        """Construir lookup table de tarifas - O(1) lookup. Usa df_tarifas."""
        
        # Necesitamos una instancia sin llamar al cache para evitar recursión.
        dm_ref = OptimizedDataManager() 
        df_tarifas = dm_ref.df_tarifas.copy() 
        
        lookup = {}
        
        # Asumo las columnas: 'Categoria', 'Regimen', 'Precio_Nocturnidad'
        if not df_tarifas.empty and 'Categoria' in df_tarifas.columns and 'Regimen' in df_tarifas.columns and 'Precio_Nocturnidad' in df_tarifas.columns:
            for _, row in df_tarifas.iterrows():
                categoria_norm = str(row['Categoria']).strip().upper()
                convenio_norm = str(row['Regimen']).strip()
                tarifa = row['Precio_Nocturnidad']
                
                if pd.notna(categoria_norm) and pd.notna(convenio_norm) and pd.notna(tarifa):
                    try:
                        lookup[(categoria_norm, convenio_norm)] = float(tarifa)
                    except (ValueError, TypeError):
                        continue
        
        return lookup

    @st.cache_data(ttl=CFG['app']['cache_segundos'])
    def _build_empleado_lookup(_self, df_trabajadores: pd.DataFrame) -> Dict[str, Dict]:
        """Construir lookup table de empleados - O(1) lookup."""
        lookup = {}
        if df_trabajadores.empty:
            return lookup
        
        cols_to_keep = ['nombre_empleado', 'cod_empleado', 'cat_empleado', 'cod_reg_convenio', 
                        'coste_hora', 'centro_preferente', 'nombre_jefe_ope']

        for _, empleado in df_trabajadores.iterrows():
            # Filtramos solo las columnas necesarias para el lookup
            info = empleado.filter(items=cols_to_keep).to_dict()
            
            # Asegurar valores por defecto
            for col in cols_to_keep:
                 if col not in info or pd.isna(info.get(col)):
                    info[col] = '' 

            if info.get('nombre_empleado'):
                lookup[info['nombre_empleado']] = info
        
        return lookup

    # --- MÉTODOS DE INICIALIZACIÓN Y GETTERS ---

    def _ensure_cache_built(self):
        """Construir todas las lookup tables si no existen (usa las propiedades)"""
        # La llamada a self.df_trabajadores activa todas las cargas perezosas y merges.
        df_trabajadores_ref = self.df_trabajadores 

        if self._tarifa_lookup is None:
            self._tarifa_lookup = self._build_tarifa_lookup() 
            
        if self._empleado_lookup is None:
            self._empleado_lookup = self._build_empleado_lookup(df_trabajadores_ref)
            
        # Generar listas de Jefes
        if self._jefes_list is None:
            jefes = set()
            # Unimos jefes del centro maestro y del trabajador maestro
            if 'nombre_jefe_ope' in self.df_centros.columns:
                jefes.update(self.df_centros['nombre_jefe_ope'].dropna().unique())
            if not df_trabajadores_ref.empty and 'nombre_jefe_ope' in df_trabajadores_ref.columns:
                 jefes.update(df_trabajadores_ref['nombre_jefe_ope'].dropna().unique())
            self._jefes_list = sorted([j for j in list(jefes) if j]) # Filtra vacíos
        
        # Generar lista de empleados
        if self._empleados_list is None and not df_trabajadores_ref.empty:
            self._empleados_list = sorted(df_trabajadores_ref['nombre_empleado'].dropna().unique())
        
        # Generar lista de centros
        if self._centros_list is None and not self.df_centros.empty:
            self._centros_list = sorted(self.df_centros['codigo_centro'].dropna().astype(str).unique().tolist())


    def get_precio_nocturnidad(self, categoria: str, cod_convenio: str) -> float:
        """Lookup O(1) optimizado"""
        if self._tarifa_lookup is None:
             self._ensure_cache_built()
        
        categoria_norm = str(categoria).strip().upper() if pd.notna(categoria) else ""
        convenio_norm = str(cod_convenio).strip() if pd.notna(cod_convenio) else ""
        
        if not categoria_norm or not convenio_norm:
            return 0.0
        
        return self._tarifa_lookup.get((categoria_norm, convenio_norm), 0.0)

    def get_empleado_info(self, nombre_empleado: str) -> Dict:
        """Lookup O(1) optimizado"""
        if self._empleado_lookup is None:
             self._ensure_cache_built()
             
        return self._empleado_lookup.get(nombre_empleado, {})

    def get_jefes(self) -> List[str]:
        """Lista pre-computada"""
        if self._jefes_list is None:
             self._ensure_cache_built()
             
        return self._jefes_list
    
    def get_trabajadores_by_jefe(self, jefe_nombre: str) -> pd.DataFrame:
        """Filtra trabajadores por su centro preferente asociado al jefe."""
        if self._jefes_list is None:
            self._ensure_cache_built()
            
        if not jefe_nombre:
            return pd.DataFrame()
        
        # Usamos el DataFrame de trabajadores (que ya tiene el campo nombre_jefe_ope)
        df_filtrado = self.df_trabajadores[
            self.df_trabajadores.get('nombre_jefe_ope', pd.Series()) == jefe_nombre
        ].copy()
        
        return df_filtrado
        
    # Otros getters...
    
    @st.cache_data(ttl=CFG['app']['cache_segundos'])
    def _load_single_sheet(_self, sheet_name: str, **kwargs) -> pd.DataFrame:
        """Carga una sola hoja del Excel maestro bajo demanda con kwargs"""
        try:
            # La variable MAESTROS_FILE es global y accesible
            df = pd.read_excel(str(MAESTROS_FILE), sheet_name=sheet_name, **kwargs)
            df.columns = df.columns.str.strip()
            return df
        except Exception:
            return pd.DataFrame()

            

class OptimizedTablaIncidencias:
    
    def __init__(self, data_manager: OptimizedDataManager):
        self.dm = data_manager
        self.rows_per_page = CFG['app']['filas_por_pagina']
        
    def render(self, jefe_nombre: str):
        """Renderiza el formulario de nueva incidencia y la tabla filtrada."""
        
        st.markdown("---")
        st.header("📝 Registro de Incidencias")
        
        trabajadores_filtrados = self.dm.get_trabajadores_by_jefe(jefe_nombre)
        
        if trabajadores_filtrados.empty:
            st.warning(f"⚠️ No hay trabajadores asignados al jefe: {jefe_nombre}. No se puede registrar.")
            return

        with st.expander("➕ Añadir nueva incidencia", expanded=True):
            self._formulario(trabajadores_filtrados)
        
        st.markdown("---")
        st.subheader("Tabla de Incidencias Registradas")
        self._display_table()

    def _formulario(self, trabajadores_df: pd.DataFrame):
        """Implementación del formulario detallado (basado en la última solicitud)."""
        with st.form("form_incidencia"):
            
            # --- DATOS GENERALES ---
            st.markdown("### Datos de Identificación")
            col1, col2 = st.columns(2)
            
            nombre_col = "nombre_empleado" 
            trabajador_options = trabajadores_df[nombre_col].dropna().tolist()

            with col1:
                trabajador = st.selectbox("👤 Trabajador", options=trabajador_options)
                
                # Obtener datos del trabajador seleccionado usando el LOOKUP O(1)
                trab_data = self.dm.get_empleado_info(trabajador)
                # NOTA: trab_data será {} si no se selecciona o no se encuentra.

                st.text_input(
                    "💼 Categoría", 
                    value=trab_data.get("cat_empleado", "N/D"), # Usa el lookup
                    disabled=True,
                    key="cat_display"
                )
                
            with col2:
                fecha = st.date_input("📅 Fecha incidencia", value=date.today())
                st.text_input(
                    "📜 Reg. Convenio", 
                    value=trab_data.get("cod_reg_convenio", "N/D"), # Usa el lookup
                    disabled=True,
                    key="reg_convenio_display"
                )
            # --- DETALLE DE HORAS Y COSTES ---
            st.markdown("### Horas y Motivo")
            col3, col4, col5 = st.columns(3)

            with col3:
                horas = st.number_input("⏱️ Horas Base", min_value=0.0, step=0.5, key="horas_base")
                nocturnidad_horas = st.number_input("🌙 Horas Nocturnidad", min_value=0.0, step=0.5, key="horas_nocturnidad")
                
            with col4:
                traslados_total = st.number_input("🚗 Traslados (Total €)", min_value=0.0, step=1.0, key="traslados")
                precio = st.number_input("💰 Precio por Incidencia", min_value=0.0, step=1.0, key="precio_incidencia")

            with col5:
                # Usar cuenta_motivos
                motivos_df = self.dm.df_motivos
                options_col = "Nombre"
                options = motivos_df[options_col].tolist() if not motivos_df.empty and options_col in motivos_df.columns else []
                
                tipo = st.selectbox(
                    "📌 Tipo incidencia",
                    options=options,
                    key="tipo_incidencia_select"
                )
            
            submitted = st.form_submit_button("Añadir incidencia", type="primary")
            
            if submitted:
                self._submit_incidencia(trabajador, fecha, horas, nocturnidad_horas, traslados_total, precio, tipo, trab_data)

    def _submit_incidencia(self, trabajador, fecha, horas, nocturnidad_horas, traslados_total, precio, tipo, trab_data):
        """Procesa y guarda la incidencia."""
        try:
            # Obtener coste por hora
            coste_hora = trab_data.get("coste_hora", 0.0)
            
            incidencia = Incidencia(
                nombre_trabajador=trabajador,
                fecha_incidencia=fecha,
                tipo_incidencia=tipo,
                horas_base=horas,
                horas_nocturnidad=nocturnidad_horas,
                traslados_total=traslados_total,
                incidencia_precio=precio,
                cod_empleado=trab_data.get("cod_empleado", ""),
                coste_hora=coste_hora,
                categoria=trab_data.get("cat_empleado", ""),
                cod_reg_convenio=trab_data.get("cod_reg_convenio", "")
            )
            
            st.session_state.incidencias.append(incidencia)
            st.success("✅ Incidencia añadida")
            st.session_state.page_number = 0
            st.rerun()
            
        except Exception as e:
            st.error(f"❌ Error al procesar la incidencia: {e}")

    def _display_table(self):
        """Muestra tabla con paginación de incidencias."""
        if not st.session_state.incidencias:
            st.info("No hay incidencias registradas para este supervisor/periodo.")
            return

        # Convertir a DataFrame para visualización
        data_dicts = [inc.__dict__ for inc in st.session_state.incidencias]
        df = pd.DataFrame(data_dicts).drop(columns=['cod_empleado', 'coste_hora'])
        
        # Limpiar y reordenar columnas para visualización
        df.rename(columns={
            "nombre_trabajador": "Trabajador",
            "fecha_incidencia": "Fecha",
            "tipo_incidencia": "Motivo",
            "horas_base": "Horas Base",
            "horas_nocturnidad": "H. Nocturnidad",
            "traslados_total": "Traslados (€)",
            "incidencia_precio": "Precio (€)",
            "categoria": "Categoría",
            "cod_reg_convenio": "Reg. Conv."
        }, inplace=True)
        
        # Paginación
        page = st.session_state.get("page_number", 0)
        total_pages = max(1, (len(df) - 1) // self.rows_per_page + 1)
        
        start = page * self.rows_per_page
        end = start + self.rows_per_page
        df_page = df.iloc[start:end].copy()
        
        st.data_editor(
            df_page,
            use_container_width=True,
            hide_index=True,
            num_rows="dynamic"
        )
        
        # Navegación
        col1, col2, col3 = st.columns([1, 2, 1])
        with col1:
            if st.button("⬅️ Anterior", disabled=page <= 0, key="prev_page"):
                st.session_state.page_number = max(0, page - 1)
                st.rerun()
        with col3:
            if st.button("Siguiente ➡️", disabled=page >= total_pages - 1, key="next_page"):
                st.session_state.page_number = min(total_pages - 1, page + 1)
                st.rerun()
        st.caption(f"Página {page + 1} de {total_pages}")


class OptimizedExportManager:
    
    @staticmethod
    def export_to_excel(incidencias: List[Incidencia], data_manager: OptimizedDataManager) -> Optional[bytes]:
        """Prepara y exporta datos a Excel."""
        if not incidencias:
            return None
        
        data_dicts = [inc.__dict__ for inc in incidencias]
        df = pd.DataFrame(data_dicts)
        
        # Mapear Cuenta Contable
        motivos_df = data_manager.df_motivos
        if "Nombre" in motivos_df.columns and "Cuenta contable" in motivos_df.columns:
            cuentas = dict(
                zip(motivos_df["Nombre"],
                    motivos_df["Cuenta contable"])
            )
            df["Cuenta contable"] = df["tipo_incidencia"].map(cuentas)
        
        # Cálculo de costes (incluyendo SS para la métrica)
        df["Coste_SS_Multiplicador"] = (df["incidencia_precio"] * df["horas_base"]) * 1.3195
        df["Coste_Nocturnidad_Sin_SS"] = df["horas_nocturnidad"] * data_manager.get_precio_nocturnidad(df["categoria"], df["cod_reg_convenio"])
        
        # Columnas finales de exportación (ajustar según el formato final deseado)
        export_cols = [
            'nombre_trabajador', 'fecha_incidencia', 'tipo_incidencia', 
            'horas_base', 'horas_nocturnidad', 'traslados_total', 
            'incidencia_precio', 'Cuenta contable', 'Coste_SS_Multiplicador', 
            'Coste_Nocturnidad_Sin_SS'
        ]
        
        export_df = df[[col for col in export_cols if col in df.columns]]

        # Exportar a BytesIO
        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            export_df.to_excel(writer, index=False, sheet_name="Incidencias_Export")
        
        return buffer.getvalue()


# ============================================================================
# CONSOLIDADOR (MANTENEMOS LA MODIFICACIÓN ANTERIOR)
# ============================================================================

class Consolidador:
    
    @staticmethod
    def get_periodos() -> List[str]:
        """Lista periodos que tienen los archivos RAW necesarios y verifica el archivo estático."""
        periodos = []
        if not PERIODOS_DIR.exists():
            return periodos
        
        # 1. Definir los archivos que deben ir en la carpeta RAW
        archivos_raw = [
            v for k, v in CFG['archivos_input'].items() 
            if k != 'tarifarios'
        ]
        
        # 2. Verificar si existe el archivo estático (tarifarios.xlsx) en la ruta data/
        tarifarios_file = DATA_DIR / CFG['archivos_input']['tarifarios']
        if not tarifarios_file.exists():
            st.sidebar.warning(f"⚠️ Falta el archivo estático: {tarifarios_file.name}")
            return []

        # 3. Buscar carpetas de periodo válidas
        for folder in sorted(PERIODOS_DIR.iterdir()):
            if folder.is_dir():
                raw = folder / "raw"
                
                # Verificar que existan los archivos RAW y la carpeta RAW
                if raw.exists() and all((raw / f).exists() for f in archivos_raw):
                    periodos.append(folder.name)
        
        return periodos
    
    @staticmethod
    def validar_archivos(periodo: str) -> Dict[str, bool]:
        """Verifica archivos del periodo (RAW) y el archivo estático (DATA/)."""
        raw = PERIODOS_DIR / periodo / "raw"
        validacion = {}
        
        # Archivos que van en raw/ (dinámicos)
        for key, filename in CFG['archivos_input'].items():
            if key != 'tarifarios':
                validacion[key] = (raw / filename).exists()

        # Archivo estático que va en data/ (global)
        tarifarios_file = DATA_DIR / CFG['archivos_input']['tarifarios']
        validacion['tarifarios'] = tarifarios_file.exists()
        
        return validacion
    
    @staticmethod
    def crear_backup() -> bool:
        """Backup del maestro actual"""
        if not MAESTROS_FILE.exists():
            return True
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = BACKUP_DIR / f"maestros_{timestamp}.xlsx"
        try:
            shutil.copy2(MAESTROS_FILE, backup)
            return True
        except:
            return False
    
    @staticmethod
    def consolidar(periodo: str) -> tuple[bool, str]:
        """Ejecuta consolidación"""
        periodo_folder = PERIODOS_DIR / periodo
        if not periodo_folder.exists():
            return False, f"No existe carpeta {periodo}"
        
        Consolidador.crear_backup()
        
        try:
            cmd = [sys.executable, str(GENERATE_SCRIPT), str(periodo_folder)]
            env = os.environ.copy()
            env['PYTHONIOENCODING'] = 'utf-8'
            
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=CFG['consolidacion']['timeout_segundos'],
                env=env
            )
            
            if result.returncode == 0:
                maestro_procesado = periodo_folder / "processed" / "maestros.xlsx"
                if maestro_procesado.exists():
                    shutil.copy2(maestro_procesado, MAESTROS_FILE)
                    return True, CFG['mensajes']['exito'].format(periodo=periodo)
                else:
                    return False, "No se generó maestros.xlsx"
            else:
                error_msg = result.stderr[:500] if result.stderr else "Error desconocido"
                error_msg = error_msg.encode('utf-8', errors='replace').decode('utf-8')
                return False, f"Error: {error_msg}"
                
        except subprocess.TimeoutExpired:
            return False, "Timeout excedido (5 min)"
        except Exception as e:
            error_str = str(e).encode('utf-8', errors='replace').decode('utf-8')
            return False, f"Error: {error_str}"


# ============================================================================
# APLICACIÓN PRINCIPAL OPTIMIZADA
# ============================================================================

class OptimizedIncidenciasApp:
    
    def __init__(self):
        if 'app_initialized_optimized' not in st.session_state:
            st.session_state.app_initialized_optimized = True
            st.session_state.selected_jefe = ""
            st.session_state.selected_imputacion = ""
            st.session_state.incidencias = []
            st.session_state.data_manager = OptimizedDataManager()
        
        # Recargar DataManager si el maestro se actualiza (e.g., por consolidación)
        if MAESTROS_FILE.exists() and MAESTROS_FILE.stat().st_mtime != st.session_state.data_manager.df_trabajadores.attrs.get('timestamp', 0):
            st.session_state.data_manager = OptimizedDataManager()

    def run(self):
        
        self._sidebar() # Lógica de consolidación
        
        data_manager = st.session_state.data_manager

        if data_manager.df_centros.empty and data_manager.df_trabajadores.empty:
            st.error("⚠️ No se pudieron cargar los datos maestros. Consolida los datos en el panel lateral.")
            return

        self._render_header(data_manager)
        
        if not st.session_state.selected_jefe or not st.session_state.selected_imputacion:
            st.warning("⚠️ Por favor, selecciona la imputación de nómina y un jefe para comenzar.")
            return
            
        tabla_optimizada = OptimizedTablaIncidencias(data_manager)
        tabla_optimizada.render(st.session_state.selected_jefe)
        
        self._render_export_section(data_manager)

    def _sidebar(self):
        """Panel de consolidación en sidebar (Mantenemos la lógica anterior)"""
        with st.sidebar:
            st.sidebar.title("🔧 Consolidación")
            
            periodos = Consolidador.get_periodos()
            
            if not periodos:
                st.sidebar.warning(CFG['mensajes']['sin_periodos'])
                # ... (texto informativo sobre archivos) ...
                return
            
            st.sidebar.success(f"✅ {len(periodos)} periodo(s) listos")
            
            periodo = st.sidebar.selectbox("📅 Periodo a consolidar", periodos)
            
            validacion = Consolidador.validar_archivos(periodo)
            
            st.sidebar.markdown("### 📄 Archivos Requeridos:")
            for key, existe in validacion.items():
                st.sidebar.text(f"{'✅' if existe else '❌'} {key}")
            
            todos_ok = all(validacion.values())
            
            if st.sidebar.button(
                "🚀 Consolidar",
                disabled=not todos_ok,
                type="primary",
                use_container_width=True
            ):
                with st.sidebar:
                    with st.spinner(CFG['mensajes']['consolidando'].format(periodo=periodo)):
                        exito, msg = Consolidador.consolidar(periodo)
                        if exito:
                            st.success(msg)
                            # Limpiar cache y recargar data manager
                            OptimizedDataManager._load_single_sheet.clear()
                            st.session_state.data_manager = OptimizedDataManager()
                            st.rerun()
                        else:
                            st.error(msg)
            
            if not todos_ok:
                st.sidebar.error(CFG['mensajes']['faltan_archivos'])
            
            if MAESTROS_FILE.exists():
                mod = datetime.fromtimestamp(MAESTROS_FILE.stat().st_mtime)
                st.sidebar.markdown("---")
                st.sidebar.info(f"📊 Último maestro:\n{mod.strftime('%Y-%m-%d %H:%M')}")
        
    def _render_header(self, data_manager: OptimizedDataManager):
        st.title("Plantilla de Registro de Incidencias")
        
        imputacion_opciones = [""] + ["01 Enero", "02 Febrero", "03 Marzo", "04 Abril", "05 Mayo", "06 Junio", "07 Julio", "08 Agosto", "09 Septiembre", "10 Octubre", "11 Noviembre", "12 Diciembre"]
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
        
        # Verificar cambios y actualizar estado
        if new_imputacion != st.session_state.selected_imputacion:
            st.session_state.selected_imputacion = new_imputacion
            st.session_state.incidencias = []
            
        if new_jefe != st.session_state.selected_jefe:
            st.session_state.selected_jefe = new_jefe
            st.session_state.incidencias = []

    def _render_export_section(self, data_manager: OptimizedDataManager):
        st.markdown("---")
        st.header("📊 Exportar Datos")
        
        incidencias_validas = [inc for inc in st.session_state.incidencias if inc.is_valid()]
        
        if not incidencias_validas:
            st.warning("⚠️ No hay incidencias válidas para exportar.")
            return
        
        # Pre-calcular métricas optimizadas
        with st.spinner("Calculando métricas..."):
            metricas = self._calculate_metrics_optimized(incidencias_validas, data_manager)

        col1, col2, col3, col4, col5 = st.columns(5)
        with col1:
            st.metric("📋 Total Incidencias", f"€{metricas['total_incidencias']:,.2f}")
        with col2:
            st.metric("✅ Total Nocturnidad", f"€{metricas['total_nocturnidad']:,.2f}")
        with col3:
            st.metric("⚠️ Total Traslados", f"€{metricas['total_traslados']:,.2f}")
        with col4:
            st.metric("🔧 Total Neto", f"€{metricas['total_simple']:,.2f}")
        with col5:
            st.metric("📊 Total Coste (c/SS)", f"€{metricas['total_con_ss']:,.2f}")

        # Botón de descarga optimizado
        with st.spinner("Generando Excel..."):
            excel_data = OptimizedExportManager.export_to_excel(incidencias_validas, data_manager)
        
        if excel_data:
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            jefe_name = st.session_state.selected_jefe.replace(' ', '_').replace('.', '')
            filename = f"incidencias_{jefe_name}_{timestamp}.xlsx"
            
            st.download_button(
                label="💾 Descargar Excel de Incidencias",
                data=excel_data,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                help="Descarga todas las incidencias válidas en formato Excel (.xlsx)"
            )
            
            st.success(f"✅ Listo para descargar: {len(incidencias_validas)} incidencias válidas")

    def _calculate_metrics_optimized(self, incidencias_validas: List[Incidencia], data_manager: OptimizedDataManager) -> Dict[str, float]:
        """Calcula métricas de forma optimizada con cache de precios."""
        
        monto_total_incidencias = 0.0
        monto_total_nocturnidad = 0.0
        monto_total_traslados = 0.0
        
        # Usar el multiplicador de SS del config (1.35 o el que tengas configurado)
        ss_multiplier = CFG['transformaciones'].get('multiplicador_ss', 1.35)

        # Crear cache de precios de nocturnidad
        precio_nocturnidad_cache = {}
        
        for inc in incidencias_validas:
            
            # Incidencias (Precio * Horas)
            monto_total_incidencias += inc.incidencia_precio * inc.horas_base
            
            # Nocturnidad 
            key = (inc.categoria, inc.cod_reg_convenio)
            if key not in precio_nocturnidad_cache:
                 # Esta función debe hacer el lookup en df_tarifas
                precio_nocturnidad_cache[key] = data_manager.get_precio_nocturnidad(inc.categoria, inc.cod_reg_convenio)
            
            precio_noct = precio_nocturnidad_cache[key]
            monto_total_nocturnidad += precio_noct * inc.horas_nocturnidad
            
            # Traslados (Ya es el coste total en euros)
            monto_total_traslados += inc.traslados_total
        
        # El 1.3195 en tu métrica original se mantiene para consistencia, pero usaré el valor de config.
        # total_con_ss = (monto_total_incidencias + monto_total_nocturnidad) * 1.3195 + monto_total_traslados
        total_con_ss = (monto_total_incidencias + monto_total_nocturnidad) * ss_multiplier + monto_total_traslados
        
        return {
            'total_incidencias': monto_total_incidencias, # Coste de la incidencia base
            'total_nocturnidad': monto_total_nocturnidad, # Coste de nocturnidad (sin SS)
            'total_traslados': monto_total_traslados, # Coste de traslados
            'total_simple': monto_total_incidencias + monto_total_nocturnidad + monto_total_traslados,
            'total_con_ss': total_con_ss
        }


# ============================================================================
# EJECUCIÓN
# ============================================================================

if __name__ == "__main__":
    app = OptimizedIncidenciasApp()
    app.run()