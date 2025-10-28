

# 📋 Aplicación de Registro y Gestión de Incidencias (Guía Técnica)

Esta aplicación Streamlit está diseñada para la gestión rápida y concurrente de incidencias. Este documento sirve como una guía detallada de la arquitectura, lógica de clases y puntos de modificación clave para el mantenimiento del código (`app_optimized.py`).

## 🛠️ Arquitectura Lógica

La aplicación sigue un patrón de diseño orientado a objetos para separar la lógica de negocio (gestión de datos, cálculos) de la presentación (UI de Streamlit).

### 1. Clases y Dataclasses Principales

| Clase/Dataclass | Función y Ubicación |
| :--- | :--- |
| **`@dataclass Incidencia`** | **Líneas ~30-100.** Define la estructura de datos fundamental de **una sola incidencia**. Contiene todos los campos necesarios para la UI y los cálculos (ej: `incidencia_horas`, `traslados_total`, campos maestros). **Es el primer lugar donde debe añadir una nueva columna de datos.** |
| **`DataManager`** | **Líneas ~120-560.** Gestiona la carga y manipulación del archivo maestro (`maestros.xlsx`). Contiene funciones de caché (`@st.cache_data`) para la carga de datos y *lookups* optimizados (ej: `get_precio_nocturnidad`, `build_empleado_lookup`). |
| **`TablaOptimizada`** | **Líneas ~560-1200.** Es el controlador principal de la interfaz de usuario (UI) que interactúa con Streamlit. Contiene toda la lógica de renderizado, manejo de *callbacks*, adición/eliminación de filas y la función crítica de exportación. **Contiene la lógica de las columnas y la exportación.** |
| **`App`** | **Líneas ~1200-1350.** La clase de inicio de la aplicación. Inicializa `DataManager` y `TablaOptimizada`, gestiona el estado de sesión (`st.session_state`) y llama al método `run()` que renderiza la UI principal. |

### 2. Lógica de Flujo de Datos

1.  **Inicio:** `App.run()` inicializa la aplicación.
2.  **Carga Maestra:** `DataManager` carga `maestros.xlsx` en caché (solo una vez) y construye estructuras de búsqueda optimizadas (diccionarios).
3.  **Sesión:** Cuando un supervisor selecciona un nombre, `TablaOptimizada` carga o inicializa el DataFrame de incidencias en `st.session_state.incidencias`.
4.  **Renderizado:** `TablaOptimizada.render()` muestra la tabla (`st.data_editor`), formularios y botones.
5.  **Cálculo:** Las funciones dentro de `TablaOptimizada` realizan el **cálculo del Coste Simple y Coste con SS** basado en las horas y precios del maestro.

---

## 3. Guía para Modificación de Columnas (Mantenimiento)

La modificación de columnas afecta tres áreas críticas del código que deben ser sincronizadas. **Si añade una columna, debe tocar los tres puntos.**

### 3.1. Añadir/Eliminar una Columna de Datos Base (Modelo)

Para que el dato exista y persista en la memoria o se exporte, debe modificar el modelo de datos.

* **Ubicación:** **`@dataclass Incidencia`** (Líneas **~30-100**)
* **Acción:**
    * **Crear:** Añada el nuevo atributo (con el tipo de dato correcto) al `dataclass`.
    * **Ejemplo:** `nuevo_campo: Optional[str] = None`
* **Consecuencia:** El nuevo campo estará disponible en toda la lógica de la aplicación, incluyendo el DataFrame final de exportación.

### 3.2. Modificar Columnas en la Interfaz (Data Editor)

Para controlar cómo se muestra, edita y valida una columna en la UI.

* **Ubicación:** **`TablaOptimizada._render_table_page`** (Alrededor de las Líneas **~970-1005**)
* **Acción:**
    * **Crear/Modificar:** Añada un nuevo par `“Nombre_Interno”: st.column_config.TipoColumn(...)` o modifique la configuración existente (ej. acortar la etiqueta).
    * **Eliminar Columna de UI:** Simplemente **elimine la entrada** del diccionario `column_config` para esa columna. La columna seguirá existiendo internamente, pero estará oculta al usuario.

### 3.3. Modificar Columnas en el Excel/CSV Descargado (Exportación)

La tabla de exportación se construye tomando la sesión actual y añadiendo columnas de cálculo (costes) y campos maestros ocultos.

* **Ubicación:** **`TablaOptimizada._create_final_dataframe`** (Alrededor de las Líneas **~1050-1110**)
* **Acción:**
    1.  El código actual ya convierte la lista de objetos `Incidencia` en un DataFrame inicial (`df_final`). **Si añadió un campo en 3.1, ya estará aquí.**
    2.  Si desea **añadir una nueva columna calculada** (ej. una nueva suma de costes), debe agregar la lógica de cálculo y la asignación a `df_final` en esta sección.
    3.  Si desea **eliminar una columna del Excel final**, localice la columna en la creación de `df_final` o en la línea de selección de columnas y elimínela.

## 4. Gestión de Archivos y Entorno

* **`requirements.txt`:** Use `uv pip freeze > requirements.txt` para mantener las dependencias sincronizadas.
* **`maestros.xlsx`:** El archivo debe estar en la carpeta `/data`. Cualquier cambio en los nombres de hoja o columnas del maestro requiere actualizar la clase `DataManager`.