# Plan del Proyecto — ERP para Clínica Odontológica (LUNA-IA)

> Fuente de verdad del proyecto. Cualquier modelo/agente que trabaje en este repositorio debe leer este archivo antes de tomar decisiones.

## 1. Objetivo y contexto

- **Proyecto académico** (Sistemas Abiertos II) con **intención comercial**: dejar el sistema bien estructurado para venderlo a un cliente potencial de clínica odontológica.
- **Fecha de entrega:** 05 de diciembre.
- **Equipo:** 3 personas; el trabajo principal lo realiza una sola persona.
- **Entregables académicos:** informe final, diagramas (arquitectura, ER, casos de uso, secuencia), manual técnico y manual de usuario.
- **Requisitos obligatorios del alcance:** agente de IA en WhatsApp y asistente de IA dentro del ERP.

## 2. Resumen funcional

Sistema ERP para una clínica odontológica con **3 sedes** que permite:

- Gestión de agenda/citas (crear, reprogramar, cancelar), pacientes, doctores, servicios/tratamientos, inventario y demás módulos (ver §7).
- **Agente de WhatsApp** que agenda, modifica y cancela citas conversando con el paciente (incluye entender **notas de voz**).
- **Asistente de IA interno** que responde preguntas ("¿cuántas citas hay hoy?", "¿cuántos pacientes se atendieron este mes?") y genera **gráficas** con endpoints analíticos predefinidos.
- Login restringido al personal de la clínica (sin registro público), con roles y 2FA.

## 3. Arquitectura

```
Paciente ─► WhatsApp ─► Evolution/Cloud API ─webhook─► Django (api_agente)
                                                        ├─► Celery (cola audio) ─► Whisper (audio → texto)
                                                        ├─► LLM (Ollama dev / API prod) ─tools─► API Django (mismo proceso)
                                                        └─► Evolution API (respuesta al paciente)
n8n ─► solo recordatorios (pacientes, doctores, asistentes) ─► Evolution/Cloud API
Personal ─► (cloudflared opcional) ─► reverse proxy ─► [React + /api] ─► Django
                                                                        ├─► PostgreSQL
                                                                        ├─► Redis
                                                                        └─► MinIO
```

> **Decisión de integración (03/11/2026):** el flujo del agente es **Evolution → Django → LLM**. n8n no interviene en la ruta de mensajes entrantes; solo ejecuta recordatorios programados. Los audios se descargan y transcriben en Django/Celery (no en n8n) para evitar saltos y copias de los archivos.

- **Dev/local:** todo en una máquina (16 GB) + Ollama en GPU + Whisper local.
- **Producción (venta):** VPS con reverse proxy (Caddy/TLS). El LLM va por **API en la nube**; Ollama no se usa en producción.
- **Ollama y Whisper** se ejecutan en el host (fuera de Docker), con la GPU. En producción se reemplazan por APIs.

## 4. Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Django 5 + Django REST Framework + `drf-spectacular` (OpenAPI) |
| Base de datos | PostgreSQL 16 (imagen `postgres:16`; `pgvector` **no** instalado todavía, reservado para futuro RAG) |
| Caché / colas | Redis + Celery (recordatorios, llamadas al LLM) |
| Archivos | MinIO (radiografías, fotos, documentos) vía `django-storages` |
| Frontend | React + Vite + TypeScript + **Ant Design 5** (`@ant-design/icons`, `@ant-design/charts`) |
| Estado/datos front | TanStack Query + React Router |
| LLM | Cliente **agnóstico** compatible-OpenAI (`httpx`): Ollama en dev, API en prod |
| Audio (STT) | **faster-whisper** local (`small`/`base`, `language=es`) |
| Automatización | n8n (solo recordatorios; el agente no pasa por n8n) |
| WhatsApp | Evolution API (Baileys) en dev/demo → Meta Cloud API en producción |
| Proxy/TLS | Caddy (producción); cloudflared opcional para demo local |
| Contenedores | Docker + docker-compose (perfiles `dev` y `prod`) |
| Servidor | Rocky Linux 9 |

## 5. IA

### 5.1 LLM agnóstico al proveedor (regla clave)
Se configura **solo por variables de entorno** — cambiar de proveedor no requiere tocar código:

```
LLM_PROVIDER=ollama|openai|groq|... 
LLM_BASE_URL=http://<host>:11434/v1     # dev: Ollama; prod: API en la nube
LLM_API_KEY=                            # vacío en dev local
LLM_MODEL=llama3.1:8b                   # dev; en prod el modelo de la API
```

- **Dev:** Ollama + `llama3.1:8b` (respaldos: `qwen3:4b`, `qwen3:8b`).
- **Prod/cliente:** modelo en la nube vía API (VPS pagado por membresía).
- **Decisión 06/11/2026 — modelo de dev:** se usa `llama3.1:8b`. Los modelos `qwen3` "razonan" y gastan cientos o miles de tokens internos aunque se les envíe `/no_think`; medido en la GTX 1060 (6 GB): `qwen3:4b` tarda 35–43 s por respuesta y sufre timeouts, `llama3.1:8b` responde en 2–3 s y no inventa acciones. `qwen3` quedó como alternativa si se dispone de más VRAM.

### 5.2 Agente de WhatsApp (Django)
- Orquestación en `api_agente`: el webhook de Evolution llama a Django, que encola el procesamiento en Celery, ejecuta el LLM con tools y responde por Evolution API.
- **Decisión 05/11/2026 — el agente corre en el mismo proceso Django.** Las tools usan serializers y modelos directamente (nunca SQL libre ni escritura sin validar); no hacen llamadas HTTP. El modelo `TokenServicio` queda solo para consumidores externos de `/api/agente/`, no para el flujo interno.
- **Tools implementadas (06/11/2026):** `listar_sedes`, `consultar_disponibilidad`, `consultar_mis_pacientes`, `listar_mis_citas`, `seleccionar_paciente`, `preparar_paciente`, `preparar_cita`, `confirmar_accion`, `cancelar_accion`.
- **Tools pendientes:** `modificar_cita` y `cancelar_cita` sobre citas ya creadas. Mientras no existan, el agente dice que no puede cancelar ni cambiar y pide llamar a la clínica.
- **Crear o agendar es en dos pasos:** `preparar_*` guarda un borrador en `ConversacionWhatsApp.borrador`; `confirmar_accion` solo actúa si el último mensaje del paciente es afirmativo (se valida en código con una expresión regular, no en el prompt).
- **Todas las sedes:** el token de servicio puede consultar y agendar en cualquiera de las 3 sedes. La sede es argumento obligatorio; si el paciente no la menciona, el agente la pregunta antes de agendar.
- **Un solo número de WhatsApp** para las 3 sedes. El paciente se identifica por el teléfono del remitente; el LLM **nunca** elige el `paciente_id`: lo toma la capa de tools desde la conversación.
- **Confirmación explícita** antes de crear, modificar o cancelar citas y pacientes. El estado se guarda en Django, no en el prompt.
- **Reglas de negocio y permisos viven en Django**, no en el prompt.
- **Creación de pacientes por WhatsApp (06/11/2026):**
  - Obligatorios: nombres, apellidos, fecha de nacimiento y sede. El teléfono lo aporta la conversación.
  - **DNI (identidad):** obligatorio para mayores de 18 años; opcional para menores, que se registran a nombre de un tutor. Se normaliza a 13 dígitos y es único cuando existe.
  - La **edad no se guarda**: se calcula desde la fecha de nacimiento y se muestra en el resumen de confirmación.
  - La dirección es opcional: si falta, se usa la de la sede donde quiere ser atendido.
  - Los datos pueden llegar en **uno o varios mensajes**. `preparar_paciente` mezcla lo nuevo con lo ya guardado y devuelve `faltan` con lo que queda por pedir; el agente solo pregunta eso.
  - Recomendados (se preguntan, no bloquean): sexo, correo.
  - Antes de crear, buscar por teléfono e identidad. Si el teléfono ya existe, no se duplica: se pregunta para quién es la cita o se deriva a recepción.
  - El agente informa el tratamiento de datos y registra la aceptación.
- **Alcance de la conversación:** el agente solo responde sobre citas, sedes, horarios y los datos de la cita de quien escribe. Rechaza temas ajenos (usuarios, contraseñas, administración, otras personas) y nunca revela ids internos, totales ni listados de la base de datos.
- **Contexto y ejemplos (few-shot):** `api_agente/contexto.py` contiene pares mensaje del paciente / respuesta esperada que se añaden al prompt en cada llamada. Se editan sin tocar la lógica y no se guardan en la BD.
- **Tabla de conversaciones:** `ConversacionWhatsApp` y `MensajeWhatsApp` en PostgreSQL, con contenido cifrado y retención configurable (por defecto 90 días).
- **Atención humana por hilo (06/11/2026):** `ConversacionWhatsApp.agente_activo`. Si una persona escribe desde el WhatsApp de la clínica, el hilo se pausa solo; las respuestas del propio agente se reconocen por `wa_message_id` y no lo pausan. Desde el admin se puede pausar/reactivar. Con el hilo pausado, los mensajes del paciente se guardan pero el agente no responde.

### 5.3 Audio (notas de voz)
Flujo: webhook de Evolution → tarea Celery en cola `audio` → descarga del audio (base64, en memoria) → **faster-whisper** (`language="es"`, `vad_filter=True`) → texto → entra al agente como mensaje normal.
- El modelo se carga una vez por proceso worker. Concurrencia 1 en la cola `audio`.
- Dedupe por `messageId` de WhatsApp.
- El audio no se guarda en disco ni en BD; solo el texto transcrito.
- Fallback: si la transcripción falla, pedir al paciente que escriba.

### 5.4 Asistente interno del ERP
- Endpoints analíticos predefinidos (`/api/analitica/...`: citas-hoy, atendidos-mes, por-servicio, por-hora, por-sede).
- El LLM **elige la tool** e interpreta la pregunta; el backend devuelve `{tipo_grafica, ejes, datos}`.
- El frontend renderiza con Ant Design Charts. **No se usa SQL libre.**

## 6. Autenticación, roles y seguridad

- **Sin registro público.** El admin **invita por correo**; el receptor **acepta**, verifica su email y **crea su contraseña**.
- **2FA: TOTP + códigos de recuperación** (Google/Microsoft Authenticator). Obligatorio para roles `admin` y `doctor`. Sin passkeys por ahora. Sin confirmación de dispositivo nuevo por ahora (si hay tiempo, se añade).
- **RBAC** por rol (`admin`, `doctor`, `recepcionista`, `asistente`) **y por sede** (querysets filtrados por las sedes del usuario; el admin ve consolidado).
- Librerías: `django-allauth[mfa]` + `django-axes` (bloqueo por intentos) + modelo `Invitacion` propio.
- **Auditoría:** `django-simple-history` en modelos clínicos + registro de accesos/cambios.
- **Agente n8n:** no usa sesión de usuario; se autentica con **token de servicio** con permisos acotados.
- **Correo:** Mailpit en dev; en producción proveedor transaccional (se decide al vender).
- Infra: Postgres/Redis/Ollama sin puertos públicos; TLS por proxy; backups `pg_dump` + WAL a MinIO.
- Datos clínicos = sensibles → mínimo privilegio, cifrado, auditoría y backups.

## 7. Módulos (alcance completo)

1. Dashboard por rol
2. Agenda / Citas (+ lista de espera)
3. Pacientes / Historia clínica
4. Odontograma
5. Doctores (+ comisiones)
6. Servicios / Tratamientos / Planes de tratamiento
7. Inventario (por sede) + Proveedores + Órdenes de compra
8. Laboratorio (trabajos externos)
9. Caja / Pagos (**sin facturación**)
10. Documentos (MinIO: radiografías, fotos, consentimientos)
11. Recordatorios automáticos (WhatsApp)
12. Asistente IA
13. Usuarios / Roles / Sedes
14. Auditoría
15. Configuración (horarios, feriados por sede)

> **No se incluye facturación.**

## 8. Modelo de datos (núcleo, multi-sede)

- `Organizacion` (capa superior, preparada para multi-tenant futuro; hoy una sola)
- `Sede` (nombre, dirección, horarios, feriados)
- `Usuario` (rol + M2M sedes)
- `Doctor` (especialidades, M2M sedes, horario por sede)
- `Paciente` (global, sede de origen, dirección obligatoria: si no se conoce, la de la sede donde se atiende), `HistoriaClinica`, `Odontograma`
- `Servicio` → `Tratamiento` → `PlanTratamiento`
- `Atencion` (sede, doctor, paciente, tipo de trabajo, estado: pendiente/confirmada/completada/cancelada), `ListaEspera`
- `Insumo`, `Stock` (por sede), `MovimientoStock`, `Proveedor`, `OrdenCompra`
- `Pago`/`Abono`, `Comision`
- `Documento`, `Consentimiento`
- `ConversacionWhatsApp`, `AuditLog`

> **Decisión de agenda (24/10/2026):** `Atencion` unifica cita y visita. Una cita futura nace `pendiente`, puede pasar a `confirmada`, y al realizarse pasa a `completada`; `cancelada` queda para citas anuladas.
>
> - No se puede marcar como `completada` una cita con fecha futura.
> - El honorario del doctor se registra al completar la atención; puede ser 0 si el doctor es interno o no genera comisión. En citas pendientes o confirmadas también puede quedar en 0.
> - Los montos de honorarios y precios de tipos de trabajo tienen un tope de **L 500,000.00**, validado en frontend y backend.
> - El dashboard cuenta “Citas pendientes (7 días)” desde mañana y solo incluye estados `pendiente` y `confirmada`.
> - La tabla “Citas y atenciones de hoy” muestra todos los estados del día para dar contexto operativo.

## 9. Localización

- País: **Honduras** · Idioma: **español**
- Zona horaria: `America/Tegucigalpa`
- Moneda: **Lempira (HNL)**
- Teléfono: prefijo **+504**

## 10. Infraestructura y despliegue

- **Compose con perfiles:** `docker-compose.dev.yml` y `docker-compose.prod.yml`.
- Servicios: `postgres`, `redis`, `backend`, `frontend`, `n8n`, `evolution-api`, `minio` (+ `caddy` en prod; `cloudflared` opcional; `portainer`/`uptime-kuma` en prod).
- **Ollama y Whisper fuera de Docker** (host con GPU) en dev.
- **Producción:** VPS con dominio + Caddy (TLS). LLM por API. Cloudflared solo para demo local o Cloudflare Access.
- Backups automáticos de PostgreSQL; monitoreo con Uptime Kuma.

## 11. Cronograma (7 semanas: 15 oct → 5 dic)

| Semana | Trabajo | Documentación en paralelo |
|---|---|---|
| S1 (15–21 oct) | Infra: compose dev/prod, Rocky, Ollama, esqueleto Django/React, login Ant Design | Arquitectura C4 + ER inicial |
| S2 (22–28 oct) | Auth + roles + sedes + CRUD Pacientes/Doctores/Servicios | Casos de uso + modelo de datos |
| S3 (29 oct–4 nov) | Agenda/Citas + disponibilidad + dashboard por rol | ER final + manual técnico (instalación) |
| S4 (5–11 nov) | Endpoints analítica + Asistente IA (tool LLM + gráficas) | Secuencia del asistente |
| S5 (12–18 nov) | Agente WhatsApp (n8n + Evolution + tools) + audio (Whisper) | Secuencia del agente |
| S6 (19–25 nov) | Historia clínica + Odontograma + inventario + endurecimiento de seguridad | Manual de usuario + informe (borrador) |
| S7 (26 nov–5 dic) | Pruebas, correcciones, demo, ensayo | Informe final + revisión + capturas |

**Hitos:** fin S3 = ERP navegable · fin S5 = agente + asistente funcionando (crítico) · S7 = todo entregado.
**Red de seguridad:** si el tiempo aprieta, se posponen módulos "deseables" (inventario, caja, laboratorio), **nunca** el agente ni el asistente.

## 12. Supuestos

- Despliegue **single-tenant** (un VPS por cliente), con el **esquema preparado** para multi-tenant.
- Documentación en **español** (ajustar a formato/APA de la universidad si se exige).
- Máquina de desarrollo a **16 GB de RAM** con GPU GTX 1060 (6 GB VRAM) para Ollama/Whisper.

## 13. Notas de riesgo

- **Hardware:** la GPU está en la máquina de desarrollo (no siempre encendida). Para la demo basta con que esté encendida; para el cliente, usar host 24/7 o API.
- **Alcance vs. tiempo:** son muchos módulos para una persona en 7 semanas → congelar alcance al MVP y usar la red de seguridad.
- **Integración LLM/WhatsApp:** reservar S4–S5 con margen; mantener fallback a texto si el audio falla.
- **Documentación:** redactarla cada semana, no al final.

## 14. Estado operativo del entorno de desarrollo

> Actualizado: 24/10/2026. Esta sección conserva decisiones operativas que no deben perderse.
> Los valores reales de secretos viven solo en `backend/.env` (ignorado por Git).

### 14.1 Variables de entorno y secretos

- `backend/.env` es local y **nunca** se sube al repositorio. La plantilla versionada es `backend/.env.example`.
- Generar `DJANGO_SECRET_KEY`:
  `python -c "import secrets; print(secrets.token_urlsafe(64))"`
- Generar `TOTP_ENCRYPTION_KEY`:
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`
- `TOTP_ENCRYPTION_KEY` debe ser la misma en todas las máquinas que compartan una BD con 2FA ya configurado. Si no coincide, hay que borrar los dispositivos TOTP y configurarlos de nuevo.
- **No cambiar `TOTP_ENCRYPTION_KEY` con dispositivos 2FA ya registrados.** Los secretos TOTP se guardan cifrados con esa clave; al cambiarla, Django lanza `InvalidToken` y el código de Microsoft/Google Authenticator se rechaza aunque sea correcto. Pasó el 24/10/2026 al crear `backend/.env` después de configurar 2FA. Solución: mantener la clave anterior, re-cifrar los secretos con la nueva, o borrar `users_dispositivototp` y volver a configurar el 2FA.
- Los dumps de la BD incluyen los secretos TOTP cifrados: quien los importe debe usar la misma `TOTP_ENCRYPTION_KEY` o resetear el 2FA.
- El LLM se configura solo por variables de entorno (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`); no se hardcodea.
- Los secretos se comparten por canal privado (Drive/OneDrive/WhatsApp), nunca por GitHub.

### 14.2 Base de datos de desarrollo

- Motor: **PostgreSQL 16 en Docker** (`infra/docker-compose.dev.yml`). No se usa SQLite.
- Contenedor: `luna-ia-dev-postgres-1`
- Host/puerto: `127.0.0.1:5432`
- Base de datos: `luna_ia`
- Usuario: `luna`
- Contraseña: `luna_dev_pass`
- Volumen: `luna-ia-dev_pg_data` (dentro de Docker Desktop/WSL2, en `/var/lib/docker/volumes/luna-ia-dev_pg_data/_data`).
- Conectar por consola:
  `docker exec -it luna-ia-dev-postgres-1 psql -U luna -d luna_ia`
- Servicios de apoyo:
  - Redis: `127.0.0.1:6379` (sin contraseña en dev).
  - MinIO: `127.0.0.1:9000` (API) y `http://127.0.0.1:9001` (consola), usuario `minioadmin`, contraseña `minioadmin_dev`.
  - Mailpit: `127.0.0.1:1025` (SMTP) y `http://127.0.0.1:8025` (bandeja de prueba).
- Datos existentes al 24/10/2026: 2 sedes, 2 pacientes, 3 doctores, 2 especialidades, 2 tipos de trabajo, 4 atenciones (3 completadas y 1 pendiente) y 2 usuarios (1 superusuario y 1 admin). Las contraseñas están hasheadas y no se pueden leer.

### 14.3 Compartir datos con el equipo

Método recomendado: **exportar un dump SQL**, no copiar el volumen.

Exportar en la máquina de origen:

```powershell
New-Item -ItemType Directory -Force backups
docker exec luna-ia-dev-postgres-1 pg_dump -U luna -d luna_ia -Fc --no-owner --no-privileges -f /tmp/luna_ia.dump
docker cp luna-ia-dev-postgres-1:/tmp/luna_ia.dump .\backups\luna_ia.dump
```

El archivo `backups/luna_ia.dump` está ignorado por Git y se comparte por canal privado.
Importar en la máquina de destino:

```powershell
docker compose -f infra/docker-compose.dev.yml up -d
docker cp .\backups\luna_ia.dump luna-ia-dev-postgres-1:/tmp/luna_ia.dump
docker exec -it luna-ia-dev-postgres-1 pg_restore -U luna -d luna_ia --clean --if-exists --no-owner --no-privileges /tmp/luna_ia.dump
```

Después de importar, detener `runserver` y resetear credenciales de aplicación:

```powershell
docker exec -it luna-ia-dev-postgres-1 psql -U luna -d luna_ia -c "DELETE FROM users_dispositivotp; DELETE FROM users_codigorecuperacion;"
cd backend
python manage.py changepassword <usuario>
```

Alternativa (no recomendada): copiar el volumen completo `luna-ia-dev_pg_data` como `pg_data.tar.gz` con PostgreSQL detenido y la misma versión 16. Los comandos están en el `README.md`, sección “Compartir la base de datos de desarrollo”.

### 14.4 Repositorio y publicación

- Repositorio Git inicializado en la raíz del proyecto.
- `.gitignore` excluye `.env`, `.venv`, `node_modules`, `dist`, `backups/`, `media`, `staticfiles`, logs y archivos de editor/SO.
- `README.md` contiene requisitos, instalación paso a paso, variables de entorno, URLs y comandos para publicar en GitHub.
- Antes de cada `git add`, verificar que no se incluyan secretos ni datos de pacientes:

```powershell
git status --short
git check-ignore -v backend/.env backups/luna_ia.dump
git add --dry-run .
```

- Publicación inicial:

```powershell
git add .
git commit -m "chore: preparar repositorio para GitHub"
git branch -M main
git remote add origin <URL_DEL_REPOSITORIO>
git push -u origin main
```

## 15. Estado de implementación (avance real)

> Actualizado: 06/11/2026. Esta sección describe **qué existe ya en el código**, para que quien retome el proyecto no repita trabajo. Lo planificado está arriba; aquí va lo construido y lo que falta.

### 15.1 Puesta en marcha en desarrollo (Windows)

```powershell
# 1) Infra (PostgreSQL, Redis, Evolution API, MinIO, Mailpit)
docker compose -f infra/docker-compose.dev.yml up -d

# 2) Backend
cd backend
.\.venv\Scripts\python.exe manage.py migrate
.\.venv\Scripts\python.exe manage.py runserver

# 3) Worker de Celery (otra terminal)
cd backend
.\.venv\Scripts\celery.exe -A config worker -Q default,audio --pool=solo -l info

# 4) LLM local (host, fuera de Docker)
ollama pull llama3.1:8b
```

- Evolution API: `http://127.0.0.1:8080` (manager en `/manager`, apikey en `infra/.env`). Imagen `evoapicloud/evolution-api:v2.3.7`: las versiones `v2.1.x`/`v2.2.x` de `atendai/evolution-api` ya no existen en Docker Hub o tienen un bucle de reconexión que impide generar el QR.
- La instancia de WhatsApp se llama `luna-ia` y su webhook apunta a `http://host.docker.internal:8000/api/agente/webhook/evolution/<secreto>/`. El webhook se configura con body anidado en `POST /webhook/set/luna-ia` (`{"webhook": {...}}`); con el body plano devuelve 400.
- `backend/.env` añade, además de lo de la sección 14.1: `MENSAJES_ENCRYPTION_KEY` (si falta se deriva de `DJANGO_SECRET_KEY`), `EVOLUTION_BASE_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE`, `EVOLUTION_WEBHOOK_SECRET`, `LLM_TIMEOUT_SEGUNDOS=120`.

### 15.2 Qué está implementado

- **ERP previo:** usuarios con 2FA, sedes, pacientes, agenda, servicios, tratamientos, inventario, pagos, documentos, analítica de consulta y auditoría. Dirección del paciente obligatoria en modelo y en BD (`CheckConstraint`).
- **`api_agente` completo para texto:**
  - `webhook.py`: valida el secreto de la ruta con `hmac.compare_digest`, ignora grupos y tipos no soportados, deduplica por `wa_message_id` y encola en Celery.
  - `evolution.py`: `enviar_texto` (devuelve el id del mensaje para reconocer su eco) y `descargar_audio`.
  - `llm.py`: cliente compatible-OpenAI con `httpx`; todo por `LLM_*`.
  - `herramientas.py` y `agente.py`: bucle LLM + tools con máximo de 5 iteraciones y 12 mensajes de contexto.
  - `contexto.py`: ejemplos few-shot que se inyectan al prompt; es el lugar para enseñar respuestas nuevas.
  - `tasks.py`: `procesar_texto` (agente) y `procesar_audio` (responde que aún no procesa audios).
  - `cifrado.py`: Fernet para el contenido de los mensajes.
  - Panel de admin para conversaciones, mensajes y tokens de servicio.
- **Registro de pacientes:** datos acumulables entre mensajes, fecha en formato hondureño (`DD/MM/AAAA`) o ISO, edad calculada y DNI obligatorio para adultos. Django descarta la fecha o el DNI que el modelo proponga si el paciente no los escribió (guardas `_fecha_mencionada`/`_identidad_mencionada`) y los vuelve a pedir conservando el resto del borrador.
- **Argumentos del modelo:** las tools validan los ids (`_entero`) antes de consultar; un `sede_id` o `paciente_id` no numérico devuelve error al modelo en vez de romper el worker.
- **Comando de diagnóstico:** `manage.py probar_llm` prueba el modelo contra 13 frases (incluye fugas de datos y temas ajenos); con `--respuestas` muestra la respuesta final que vería el paciente usando herramientas simuladas (no escribe en la BD).
- **Tests:** 287 en total, todos en verde (69 de `api_agente`). Cubren webhook, deduplicación, cifrado, borradores, confirmación explícita, aislamiento de pacientes por teléfono, pausa del agente, limpieza de `</think>`, argumentos inválidos y validación del alta de pacientes.

### 15.3 Cómo probar el agente

1. Levantar infra, `runserver` y el worker (reiniciarlo tras cada cambio en `tasks.py`, `agente.py` o `.env`).
2. Escribir por WhatsApp al número vinculado desde **otro** teléfono.
3. Frases útiles: `hola`, `¿qué sedes tienen?`, `quiero una cita mañana en San Pedro`, `quiero registrarme, me llamo ...`.
4. Para tomar el hilo como persona: escribir desde el WhatsApp de la clínica (pausa automática) o usar las acciones del admin. Luego "Reactivar el agente" en el admin.
5. Prueba sin WhatsApp ni BD: `manage.py probar_llm --respuestas`.
6. Para enseñar una respuesta nueva: agregar la tupla `(mensaje, respuesta)` en `api_agente/contexto.py`. No hace falta migración ni reiniciar el worker si solo se cambian ejemplos (el módulo se recarga con el proceso; reiniciar el worker si se editó mientras corría).

### 15.4 Límites conocidos y pendientes

- **Audio:** falta integrar `faster-whisper` en `procesar_audio`; hoy responde con un texto de fallback.
- **Cancelar/modificar citas:** sin tools; el agente deriva a la clínica.
- **Honorario de las citas creadas por el agente:** se guarda en 0 y el personal lo ajusta después.
- **Dirección del paciente:** si no la da, se guarda la de la sede (no la suya). Conviene que recepción la corrija.
- **Asistente interno del ERP (sección 5.4):** no implementado todavía.
- **Panel de pausa:** solo existe en el admin de Django; falta el botón en el frontend.
- **Modelo:** `llama3.1:8b` a veces llama una herramienta innecesaria (por ejemplo `listar_sedes` al saludar o `cancelar_accion` ante un dolor). La respuesta final es correcta, pero gasta una llamada extra. Si molesta, filtrar por intención antes de darle tools. También tiende a rellenar huecos con datos inventados: por eso las guardas de Django son la defensa real, no el prompt.
- **Contexto:** los ejemplos son few-shot en `contexto.py`. No se usa `pgvector`: con decenas de casos no aporta y añade infraestructura. Si algún día hay cientos de políticas o preguntas frecuentes para recuperar, ahí sí conviene RAG con `pgvector`.
- **Git:** hay cambios sin commitear y el commit `52f36af` no se ha subido a `origin`.
