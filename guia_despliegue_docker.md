Guía de Despliegue para 'Registro de Incidencias'Esta guía detalla los pasos para desplegar la aplicación Streamlit 'Registro de Incidencias' en un servidor on-premise utilizando Docker Compose.Arquitectura: La aplicación se ejecuta en un contenedor Docker aislado. Utiliza uv para la gestión de dependencias y el Puerto 80 del host para el acceso.1. Requisitos Previos en el ServidorAsegúrese de que el servidor on-premise tenga instalados y funcionando los siguientes componentes:Docker Engine: El motor principal de contenedores.Docker Compose: La herramienta de orquestación de multi-contenedores (v1 o v2).Acceso a la red interna (LAN): La aplicación está diseñada para ser accedida internamente.2. Preparación de ArchivosCopie la estructura completa de su proyecto a un directorio en el servidor (ej: /home/user/app_incidencias/).La estructura de directorios debe ser la siguiente:app_incidencias/
├── app_optimized.py      # Aplicación Streamlit principal
├── Dockerfile            # Instrucciones de construcción de la imagen
├── docker-compose.yml    # Configuración de orquestación
├── requirements.txt      # Dependencias (pandas, streamlit, numpy, openpyxl)
├── data/                 # Contiene 'maestros.xlsx'
├── assets/               # Recursos estáticos (logos, etc.)
└── .streamlit/           # Archivos de configuración (config.toml)
3. Configuración del Firewall (¡Paso Crítico!)Debe abrir el Puerto 80 en el firewall de su servidor para permitir el acceso de las máquinas de la red interna a la aplicación.Verifique el estado del firewall (ejemplo UFW en Ubuntu/Debian):sudo ufw status
Abra el Puerto 80 (TCP):sudo ufw allow 80/tcp
sudo ufw reload  # Aplicar los cambios
4. Proceso de DespliegueSiga estos pasos desde el terminal del servidor, ubicado en el directorio principal del proyecto (app_incidencias/):Paso 4.1: Verificar Docker EngineAsegúrese de que el motor de Docker esté activo. Si no lo está, inícielo:sudo systemctl start docker
Paso 4.2: Construir e Iniciar la AplicaciónEjecute el comando de despliegue de Docker Compose. El flag --build es esencial para aplicar los cambios en el Dockerfile (incluyendo la instalación de uv).docker compose up -d --build
OpciónDescripción-dEjecuta el contenedor en modo "detached" (segundo plano).--buildFuerza la reconstrucción de la imagen (aplica Dockerfile y uv).Paso 4.3: Verificar Contenedor ActivoVerifique que el contenedor se haya levantado correctamente:docker ps
Busque un contenedor con el nombre incidencias_streamlit_prod (o similar) y confirme que el estado sea Up (running).5. Acceso a la AplicaciónLa aplicación es accesible desde cualquier máquina de la red local.Obtenga la IP de su servidor on-premise (ejemplo: ip a o ipconfig).Acceda desde un navegador de otra máquina:http://[IP_DEL_SERVIDOR]
6. Mantenimiento y ActualizacionesPara actualizar el código (app_optimized.py) o las dependencias (requirements.txt):Copie los archivos nuevos al directorio del proyecto en el servidor.Ejecute de nuevo el comando de despliegue:docker compose up -d --build
Docker se encargará de detener el contenedor antiguo, construir la nueva imagen e iniciar el servicio actualizado.