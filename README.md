# MT.IA - Plataforma tipo ChatGPT (Open WebUI + Ollama Local)

Este repositorio contiene la configuración para desplegar la plataforma **Open WebUI** conectada al servidor Ollama en la red local (`http://192.168.42.21:11434`).

## 📁 Archivos del Proyecto

- [`docker-compose.yml`](file:///c:/Users/onunez/OneDrive%20-%20MT%20INDUSTRIAL%20S.A.C/Escritorio/Antigravity/MT.IA/docker-compose.yml): Configuración para desplegar Open WebUI conectado a `http://192.168.42.21:11434`.
- [`.env`](file:///c:/Users/onunez/OneDrive%20-%20MT%20INDUSTRIAL%20S.A.C/Escritorio/Antigravity/MT.IA/.env): Variables de entorno del puerto y backend.
- [`test_ollama_connection.js`](file:///c:/Users/onunez/OneDrive%20-%20MT%20INDUSTRIAL%20S.A.C/Escritorio/Antigravity/MT.IA/test_ollama_connection.js): Script para probar conectividad directa con Ollama.

---

## ⚙️ Habilitar conexiones externas en Ollama (Servidor Linux `192.168.42.21`)

Por defecto, Ollama en Linux se escucha únicamente en `127.0.0.1` (localhost). Para permitir que Open WebUI o la red local se conecten a `192.168.42.21:11434`, realiza estos pasos en el servidor Linux:

1. **Editar la configuración del servicio Ollama:**
   ```bash
   sudo systemctl edit ollama.service
   ```
2. **Agregar las siguientes líneas bajo la sección `[Service]`:**
   ```ini
   [Service]
   Environment="OLLAMA_HOST=0.0.0.0:11434"
   Environment="OLLAMA_ORIGINS=*"
   ```
3. **Guardar, recargar y reiniciar el servicio:**
   ```bash
   sudo systemctl daemon-reload
   sudo systemctl restart ollama
   ```
4. **Verificar el puerto en Linux:**
   ```bash
   sudo netstat -tulpn | grep 11434
   # Debe mostrar 0.0.0.0:11434
   ```

---

## 🚀 Despliegue de Open WebUI

1. **Iniciar Docker Desktop** en tu computadora local.
2. **Ejecutar el contenedor:**
   ```bash
   docker compose up -d
   ```
3. **Acceder a la Plataforma:**
   - Abre tu navegador en `http://localhost:3000`.
   - Crea tu cuenta de **Administrador**.
   - En la parte superior de la interfaz, selecciona `llama3.5:3b` para comenzar a chatear.
