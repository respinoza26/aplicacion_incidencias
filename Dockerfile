# Usa una imagen base oficial de Python para Streamlit
FROM python:3.11-slim

# Instalar 'uv' para acelerar la instalación de dependencias
RUN pip install uv

# Establece el directorio de trabajo dentro del contenedor
WORKDIR /app

# Copia los archivos de configuración de Streamlit primero
# Esto permite configurar el ambiente antes de copiar la aplicación
COPY .streamlit/ .streamlit/

# Copia el archivo de requerimientos e instala las dependencias usando uv
COPY requirements.txt .
# FIX: Añadir --system para instalar dependencias globalmente (soluciona el error anterior)
RUN uv pip install --system --no-cache-dir -r requirements.txt

# Copia el código de la aplicación y el directorio de datos
COPY app_optimized.py .
COPY data ./data 
# AÑADIDO: Copia la carpeta de recursos estáticos ('assets')
COPY assets ./assets 

# Expone el puerto por defecto de Streamlit
EXPOSE 8501

# Comando de ejecución de la aplicación Streamlit
CMD ["streamlit", "run", "app_optimized.py", "--server.port", "8501", "--server.address", "0.0.0.0"]


# # Construir la imagen
# docker build -t mi-app-streamlit .

# # Crear el contenedor (se iniciará automáticamente)
# docker run -d --name mi_app_streamlit -p 8501:8501 --restart unless-stopped mi-app-streamlit

# # Si es fuera de horario o fin de semana, detenlo manualmente
# docker stop mi_app_streamlit