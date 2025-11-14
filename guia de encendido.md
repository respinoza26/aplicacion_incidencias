# Guía: Encendido y Apagado Automático de Docker en Windows

**Objetivo:** Configurar un contenedor Docker para que se encienda automáticamente a las 7:00 AM y se apague a las 23:00 PM de lunes a viernes.

---

## 📋 Requisitos previos

- Windows 10/11 con Docker Desktop instalado
- Máquina virtual Windows (opcional, si trabajas con VM)
- Permisos de administrador

---

## 🐳 Paso 1: Preparar el Dockerfile

Usa este Dockerfile optimizado (sin cron interno):

```dockerfile
# Usa una imagen base oficial de Python para Streamlit
FROM python:3.11-slim

# Instalar 'uv' para acelerar la instalación de dependencias
RUN pip install uv

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos de configuración de Streamlit primero
COPY .streamlit/ .streamlit/

# Copia el archivo de requerimientos e instala las dependencias usando uv
COPY requirements.txt .
RUN uv pip install --system --no-cache-dir -r requirements.txt

# Copia el código de la aplicación y el directorio de datos
COPY app_optimized.py .
COPY data ./data
COPY assets ./assets

# Expone el puerto por defecto de Streamlit
EXPOSE 8501

# Inicia la aplicación Streamlit
CMD ["streamlit", "run", "app_optimized.py", "--server.port", "8501", "--server.address", "0.0.0.0"]
```

---

## 🔨 Paso 2: Crear el contenedor Docker

Abre PowerShell o CMD y ejecuta los siguientes comandos:

```powershell
# Construir la imagen
docker build -t mi-app-streamlit .

# Crear y ejecutar el contenedor
docker run -d --name mi_app_streamlit -p 8501:8501 --restart unless-stopped mi-app-streamlit

# Si es fuera de horario o fin de semana, detenlo manualmente
docker stop mi_app_streamlit
```

**Nota:** Reemplaza `mi_app_streamlit` con el nombre que prefieras para tu contenedor.

---

## ⏰ Paso 3: Configurar Tarea 1 - INICIAR (7:00 AM)

### 3.1 Abrir el Programador de Tareas

1. Presiona `Win + R`
2. Escribe `taskschd.msc`
3. Presiona Enter

### 3.2 Crear la tarea de inicio

1. En el panel derecho, clic en **"Crear tarea"** (NO "Crear tarea básica")

### 3.3 Pestaña General

- **Nombre:** `Iniciar App Streamlit`
- **Descripción:** `Inicia el contenedor Docker a las 7 AM de lunes a viernes`
- ✅ Selecciona: **"Ejecutar tanto si el usuario inició sesión como si no"**
- ✅ Marca: **"Ejecutar con los privilegios más altos"**

### 3.4 Pestaña Desencadenadores

1. Clic en **"Nuevo"**
2. **Iniciar la tarea:** Selecciona **"Según una programación"**
3. **Configuración:** Selecciona **"Semanalmente"**
4. **Hora de inicio:** `07:00:00`
5. **Repetir cada:** `1 semanas en:`
6. ✅ Marca SOLO estos días:
   - ☑ Lunes
   - ☑ Martes
   - ☑ Miércoles
   - ☑ Jueves
   - ☑ Viernes
7. Clic en **"Aceptar"**

### 3.5 Pestaña Acciones

1. Clic en **"Nueva"**
2. **Acción:** Selecciona **"Iniciar un programa"**
3. **Programa o script:** Escribe `docker`
4. **Agregar argumentos (opcional):** Escribe `start mi_app_streamlit`
5. Clic en **"Aceptar"**

### 3.6 Pestaña Condiciones

- ❌ **Desmarca:** "Iniciar la tarea solo si el equipo está conectado a la corriente alterna"
  - (Esto asegura que funcione aunque sea un portátil con batería)

### 3.7 Pestaña Configuración

- ✅ Marca: **"Permitir que la tarea se ejecute a petición"**
- ✅ Marca: **"Ejecutar la tarea lo antes posible después de perder un inicio programado"**
  - (Si el ordenador se enciende después de las 7 AM, ejecutará la tarea automáticamente)

### 3.8 Guardar

Clic en **"Aceptar"** para guardar la tarea.

---

## ⏰ Paso 4: Configurar Tarea 2 - DETENER (23:00 PM)

Repite exactamente los mismos pasos del Paso 3, pero con estos cambios:

### 4.1 Pestaña General

- **Nombre:** `Detener App Streamlit`
- **Descripción:** `Detiene el contenedor Docker a las 23:00 de lunes a viernes`

### 4.2 Pestaña Desencadenadores

- **Hora de inicio:** `23:00:00` (en lugar de 07:00:00)

### 4.3 Pestaña Acciones

- **Programa o script:** `docker`
- **Agregar argumentos:** `stop mi_app_streamlit` (usa **stop** en lugar de **start**)

*El resto de configuraciones (Condiciones, Configuración) son iguales.*

---

## ✅ Paso 5: Verificar que funciona

### 5.1 Probar manualmente las tareas

1. En el Programador de Tareas, busca tus tareas creadas
2. Clic derecho sobre **"Iniciar App Streamlit"** → **"Ejecutar"**
3. Verifica que el contenedor arrancó:
   ```powershell
   docker ps
   ```
   Deberías ver tu contenedor en la lista con estado "Up"

4. Clic derecho sobre **"Detener App Streamlit"** → **"Ejecutar"**
5. Verifica que se detuvo:
   ```powershell
   docker ps -a
   ```
   Deberías ver tu contenedor con estado "Exited"

### 5.2 Ver el historial de ejecuciones

1. En el Programador de Tareas, selecciona tu tarea
2. Ve a la pestaña **"Historial"** (parte inferior)
3. Verás un registro de todas las ejecuciones

### 5.3 Comprobar el estado de las tareas

```powershell
Get-ScheduledTask | Where-Object {$_.TaskName -like "*Streamlit*"}
```

Deberías ver ambas tareas con **Estado: "Preparado"**

---

## 📝 Preguntas Frecuentes

### ❓ ¿Tengo que levantar el Docker todos los días?

**No.** Es completamente automático. Una vez configurado, el sistema se encarga de:
- Encender el contenedor a las 7:00 AM (lunes a viernes)
- Apagar el contenedor a las 23:00 PM (lunes a viernes)

### ❓ ¿Las tareas tienen que estar en ejecución?

**No.** Las tareas NO están "corriendo" todo el tiempo. Son como alarmas:
- Estado normal: **"Preparado"** (esperando)
- Cuando llega la hora: Se activan, ejecutan el comando, y vuelven a "Preparado"

### ❓ ¿Tiene que estar encendido el ordenador?

**Sí.** El ordenador (o la máquina virtual) debe estar encendido a las 7:00 AM y 23:00 PM para que las tareas se ejecuten.

**Si el ordenador se enciende después:** Como configuraste la opción *"Ejecutar la tarea lo antes posible después de perder un inicio programado"*, la tarea se ejecutará automáticamente cuando enciendas el equipo.

### ❓ ¿Qué pasa si trabajo con una máquina virtual?

- **Docker y las tareas deben estar configuradas DENTRO de la VM**
- La VM debe estar encendida en los horarios programados
- **Recomendación:** Deja la VM encendida 24/7 (consumen pocos recursos en idle)

### ❓ ¿Qué pasa los fines de semana?

El contenedor **permanecerá apagado** porque solo configuramos las tareas para lunes a viernes.

### ❓ ¿Puedo cambiar los horarios?

Sí. Edita la tarea en el Programador de Tareas:
1. Clic derecho sobre la tarea → **"Propiedades"**
2. Ve a la pestaña **"Desencadenadores"**
3. Selecciona el desencadenador → **"Editar"**
4. Cambia la hora o los días

---

## 🔧 Solución de Problemas

### Error: "No se encuentra el comando docker"

Si al guardar la tarea te dice que no encuentra `docker`, usa la ruta completa:

**En el campo "Programa o script":**
```
C:\Program Files\Docker\Docker\resources\bin\docker.exe
```

### El contenedor no arranca

1. Verifica que Docker Desktop esté corriendo
2. Prueba manualmente:
   ```powershell
   docker start mi_app_streamlit
   ```
3. Revisa los logs del contenedor:
   ```powershell
   docker logs mi_app_streamlit
   ```

### La tarea no se ejecutó en el horario

1. Verifica que el ordenador estaba encendido
2. Revisa el historial de la tarea en el Programador de Tareas
3. Comprueba que la tarea está **Habilitada** (no deshabilitada)

### Ver logs detallados de las tareas

```powershell
# Ver últimas ejecuciones
Get-ScheduledTask -TaskName "Iniciar App Streamlit" | Get-ScheduledTaskInfo

Get-ScheduledTask -TaskName "Detener App Streamlit" | Get-ScheduledTaskInfo
```

---

## 📅 Cronología de ejemplo

```
Lunes 7:00 AM    → Docker arranca automáticamente ✅
Lunes 23:00 PM   → Docker se detiene automáticamente ✅
Martes 7:00 AM   → Docker arranca automáticamente ✅
Martes 23:00 PM  → Docker se detiene automáticamente ✅
...
Viernes 23:00 PM → Docker se detiene automáticamente ✅
Sábado           → Docker permanece apagado 🔴
Domingo          → Docker permanece apagado 🔴
Lunes 7:00 AM    → Docker arranca automáticamente ✅
```

---

## 📚 Comandos útiles de Docker

```powershell
# Ver contenedores en ejecución
docker ps

# Ver todos los contenedores (incluidos detenidos)
docker ps -a

# Iniciar contenedor manualmente
docker start mi_app_streamlit

# Detener contenedor manualmente
docker stop mi_app_streamlit

# Ver logs del contenedor
docker logs mi_app_streamlit

# Ver logs en tiempo real
docker logs -f mi_app_streamlit

# Acceder al navegador para ver la app
# Abre: http://localhost:8501

# Reiniciar contenedor
docker restart mi_app_streamlit

# Eliminar contenedor (debes detenerlo primero)
docker rm mi_app_streamlit

# Ver uso de recursos del contenedor
docker stats mi_app_streamlit
```

---

## ✨ Resumen

1. ✅ Crea el Dockerfile sin cron interno
2. ✅ Construye la imagen y crea el contenedor
3. ✅ Configura dos tareas en el Programador de Tareas:
   - Tarea 1: INICIAR a las 7:00 AM (lunes a viernes)
   - Tarea 2: DETENER a las 23:00 PM (lunes a viernes)
4. ✅ Verifica que las tareas funcionan ejecutándolas manualmente
5. ✅ Deja que el sistema trabaje automáticamente

**¡Y listo!** Tu aplicación Docker se gestionará sola de forma automática. 🎉

---

## 📞 Soporte adicional

Si tienes problemas:
- Revisa la sección "Solución de Problemas"
- Verifica el historial de tareas en el Programador de Tareas
- Comprueba los logs de Docker

---

**Fecha de creación:** Noviembre 2025  
**Versión:** 1.0