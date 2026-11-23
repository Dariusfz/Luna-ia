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
- **Tools implementadas (09/11/2026):** `listar_sedes`, `consultar_disponibilidad`, `consultar_mis_pacientes`, `listar_mis_citas`, `seleccionar_paciente`, `preparar_paciente`, `preparar_cita`, `preparar_cancelacion_cita`, `preparar_modificacion_cita`, `confirmar_accion`, `cancelar_accion`, `consultar_tratamientos`, `solicitar_revision_administrador`.
- **Cancelar y modificar citas (09/11/2026):** el agente solo opera sobre citas futuras del paciente que escribe (`_cita_del_paciente`). Igual que al crear, `preparar_*` deja un borrador y `confirmar_accion` exige una afirmación explícita del paciente. La cancelación cambia el estado a `cancelada` y la modificación reutiliza `AtencionSerializer` (valida sede, doctor, horario y choques).
- **Flujo de tratamiento:** al pedir una cita, el agente pregunta primero qué tratamiento necesita, consulta el catálogo con `consultar_tratamientos` y da el precio de referencia. Si no existe, no agenda: informa que no está disponible y llama a `solicitar_revision_administrador`, que avisa al administrador. El tratamiento se recuerda durante toda la conversación: `preparar_cita` lo valida contra todos los mensajes del paciente, no solo los últimos 3, para que no se pierda mientras se elige sede, día y hora.
- **Consultar/confirmar una cita (09/11/2026):** si el paciente pide los datos de su cita o no recuerda la fecha, `listar_mis_citas` los devuelve. Si el número tiene **un solo paciente registrado**, la tool lo selecciona automáticamente (antes exigía `seleccionar_paciente` y el agente podía quedarse sin responder).
- **Números del administrador (09/11/2026):** los avisos enviados a `ADMIN_WHATSAPP` se guardan con rol `SISTEMA`, así su eco no pausa el hilo. Esos números son de uso humano: **si el administrador escribe, el agente se pausa** y solo se reactiva manualmente desde el admin. Se avisa al crear, modificar y cancelar una cita (y cuando falta un tratamiento). La fecha se envía con el día de la semana, por ejemplo `lunes 16/11/2026 a las 08:30`.
- **Confirmaciones simples (09/11/2026):** si el último mensaje del paciente es una afirmación corta (`si`, `sí`, `sip`, `claro`, `correcto`, `confirmo`, `ok`, `dale`, `de acuerdo`, `está bien`, `perfecto`, con o sin tilde), `agente.responder` ejecuta `confirmar_accion` en código, sin pasar por el modelo. Así un "si" sin acento no se interpreta como ambiguo ni el agente vuelve a preguntar.
- **Crear o agendar es en dos pasos:** `preparar_*` guarda un borrador en `ConversacionWhatsApp.borrador`; `confirmar_accion` solo actúa si el último mensaje del paciente es afirmativo (se valida en código con una expresión regular, no en el prompt).
- **Todas las sedes:** el token de servicio puede consultar y agendar en cualquiera de las 3 sedes. La sede es argumento obligatorio; si el paciente no la menciona, el agente la pregunta antes de agendar.
- **Un solo número de WhatsApp** para las 3 sedes. El paciente se identifica por el teléfono del remitente; el LLM **nunca** elige el `paciente_id`: lo toma la capa de tools desde la conversación.
- **Confirmación explícita** antes de crear, modificar o cancelar citas y pacientes. El estado se guarda en Django, no en el prompt.
- **Reglas de negocio y permisos viven en Django**, no en el prompt.
- **Creación de pacientes por WhatsApp (06/11/2026):**
  - Obligatorios: nombres, apellidos, fecha de nacimiento y sede. El teléfono lo aporta la conversación.
  - **Un mismo número puede tener varios pacientes (familiares).** `preparar_paciente` ya no bloquea el alta si el número ya tiene un paciente; se rechazan duplicados por DNI o por nombre+fecha. Para agendar a un familiar hay que confirmar primero su alta.
  - **DNI (identidad):** obligatorio para mayores de 18 años; opcional para menores, que se registran a nombre de un tutor. Se normaliza a 13 dígitos y es único cuando existe. Se valida un formato básico (departamento 01-18, no todo ceros). El año del DNI **no** se compara con la fecha de nacimiento: puede corresponder al trámite, por ejemplo un cambio de nombre hecho años después de nacer.
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
- **Mensajes viejos al reiniciar (23/11/2026):** Evolution entrega al reconectar los mensajes acumulados mientras el proyecto estaba apagado. `api_agente/vigencia.py` los descarta antes de guardarlos/encolarlos si superan `WHATSAPP_MENSAJE_MAX_ANTIGUEDAD_SEGUNDOS` (300 s por defecto) o si su marca de tiempo es anterior al arranque del proceso (`WHATSAPP_ARRANQUE_TOLERANCIA_SEGUNDOS`, 90 s). Las tareas de Celery que quedaron en el broker al apagar también se omiten al ejecutarse si el mensaje ya es viejo. Así el agente solo responde conversaciones activas, no hilos que quedaron pendientes de una sesión anterior.

### 5.3 Audio (notas de voz)
Flujo: webhook de Evolution → tarea Celery en cola `audio` → descarga del audio (base64, en memoria) → **faster-whisper** (`language="es"`, `vad_filter=True`) → texto → entra al agente como mensaje normal.
- El modelo se carga una vez por proceso worker. Concurrencia 1 en la cola `audio`.
- Dedupe por `messageId` de WhatsApp.
- El audio no se guarda en disco ni en BD; solo el texto transcrito.
- Fallback: si la transcripción falla, pedir al paciente que escriba.

### 5.4 Asistente interno del ERP
- Endpoints analíticos predefinidos (`/api/analitica/...`: citas-hoy, atendidos-mes, por-servicio, por-hora, por-sede, ingresos).
- El LLM **elige la tool** e interpreta la pregunta; el backend devuelve `{tipo_grafica, ejes, datos}`.
- Herramienta de **análisis estratégico** (`analisis_estrategico`): tendencias por mes, proyección del próximo mes, tratamientos más solicitados, horas pico, carga de doctores, sedes, lista de espera e ingresos. Los cálculos los hace el backend; el modelo solo interpreta y propone el plan.
- El frontend renderiza con Ant Design Charts. **No se usa SQL libre.**

## 6. Autenticación, roles y seguridad

- **Sin registro público.** El admin **invita por correo**; el receptor **acepta**, verifica su email y **crea su contraseña**.
- **2FA: TOTP + códigos de recuperación** (Google/Microsoft Authenticator). Obligatorio para roles `admin` y `doctor`. Sin passkeys por ahora. Sin confirmación de dispositivo nuevo por ahora (si hay tiempo, se añade).
- **RBAC** por rol (`admin`, `doctor`, `recepcionista`, `asistente`) **y por sede** (querysets filtrados por las sedes del usuario; el admin ve consolidado). Además, historia clínica y odontograma exigen que el doctor esté activo y tenga asignada la sede del registro; si no, la API responde 400 en el campo `doctor`.
- **Sesiones y cookies (23/11/2026):** cookie de sesión `HttpOnly` y `SameSite=Lax`; la de CSRF queda legible por el frontend (`CSRF_COOKIE_HTTPONLY=False`) porque `cliente.ts` la copia al encabezado `X-CSRFToken`. En producción (`DEBUG=False`) se activan solas `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_SSL_REDIRECT` y HSTS (1 año); todo se puede ajustar por entorno. La sesión expira por inactividad a las 8 h (`SESSION_SAVE_EVERY_REQUEST=True`, `SESSION_COOKIE_AGE_SEGUNDOS=28800`). Detrás de Caddy/nginx se respeta `X-Forwarded-Proto`. `X-Frame-Options=DENY`, `nosniff` y `Referrer-Policy=same-origin`.
- **Bloqueo por intentos (23/11/2026):** `django-axes` con 5 fallos, 15 min de espera y reinicio del contador al entrar bien. El bloqueo es por **combinación usuario+IP** (`AXES_LOCKOUT_PARAMETERS = [["ip_address", "username"]]`), así un empleado que se equivoca no bloquea a toda la clínica. El login responde `429` con `Retry-After` y no revela si la contraseña era correcta. Los tests limpian los intentos de la caché Redis entre casos.
- Librerías: `django-allauth[mfa]` + `django-axes` (bloqueo por intentos) + modelo `Invitacion` propio.
- **Auditoría:** `django-simple-history` en modelos clínicos + registro de accesos/cambios.
- **Agente n8n:** no usa sesión de usuario; se autentica con **token de servicio** con permisos acotados.
- **Correo:** Mailpit en dev (solo captura). El backend usa SMTP configurable por entorno (`EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_USE_TLS`/`EMAIL_USE_SSL`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_TIMEOUT`): sirve Gmail con contraseña de aplicación para probar con correos reales y cualquier proveedor transaccional en producción (se decide al vender). Si el envío falla, la invitación se borra y la API devuelve 400 (no se miente al admin). `manage.py probar_correo <destino>` verifica el SMTP. El enlace de invitación usa `FRONTEND_URL`, que debe ser accesible desde el dispositivo del destinatario (en demo, URL de ngrok/cloudflared).
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

> Actualizado: 23/11/2026. Esta sección describe **qué existe ya en el código**, para que quien retome el proyecto no repita trabajo. Lo planificado está arriba; aquí va lo construido y lo que falta.

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
- `backend/.env` añade, además de lo de la sección 14.1: `MENSAJES_ENCRYPTION_KEY` (si falta se deriva de `DJANGO_SECRET_KEY`), `EVOLUTION_BASE_URL`, `EVOLUTION_API_KEY`, `EVOLUTION_INSTANCE`, `EVOLUTION_WEBHOOK_SECRET`, `LLM_TIMEOUT_SEGUNDOS=120`, `WHATSAPP_MENSAJE_MAX_ANTIGUEDAD_SEGUNDOS`/`WHATSAPP_ARRANQUE_TOLERANCIA_SEGUNDOS` (por defecto `300` y `90`) y `WHISPER_MODEL`/`WHISPER_DEVICE`/`WHISPER_COMPUTE_TYPE`/`WHISPER_LANGUAGE`/`WHISPER_BEAM_SIZE` (por defecto `small`, `auto`, `int8`, `es`, `5`).

### 15.2 Qué está implementado

- **ERP previo:** usuarios con 2FA, sedes, pacientes, agenda, servicios, tratamientos, inventario, pagos, documentos, analítica de consulta y auditoría. Dirección del paciente obligatoria en modelo y en BD (`CheckConstraint`).
- **`api_agente` completo para texto y audio:**
  - `webhook.py`: valida el secreto de la ruta con `hmac.compare_digest`, ignora grupos y tipos no soportados, deduplica por `wa_message_id` y encola en Celery. Antes de guardar, `vigencia.motivo_para_ignorar` descarta los mensajes atrasados o anteriores al arranque (ver 5.2).
  - `vigencia.py`: filtros de mensajes viejos por marca de tiempo de Evolution y por hora de creación de la tarea en cola (`mensaje_vigente`).
  - `evolution.py`: `enviar_texto` (devuelve el id del mensaje para reconocer su eco) y `descargar_audio`.
  - `llm.py`: cliente compatible-OpenAI con `httpx`; todo por `LLM_*`.
  - `herramientas.py` y `agente.py`: bucle LLM + tools con máximo de 5 iteraciones y 12 mensajes de contexto.
  - `contexto.py`: ejemplos few-shot que se inyectan al prompt; es el lugar para enseñar respuestas nuevas.
  - `transcripcion.py`: `faster-whisper` con el modelo cargado una vez por proceso (caché en memoria, cerrojo para la primera carga). Todo por `WHISPER_*`; el audio llega y se procesa en memoria. Si la GPU configurada no puede cargar el modelo, se reintenta en CPU.
  - `tasks.py`: `procesar_texto` (agente) y `procesar_audio` (descarga la nota de voz, la transcribe, reemplaza el marcador `[audio]` por el texto y sigue el flujo normal; si no se entiende o falla, pide que escriba).
  - `cifrado.py`: Fernet para el contenido de los mensajes.
  - Panel de admin para conversaciones, mensajes y tokens de servicio.
- **Panel del agente de WhatsApp en el frontend (23/11/2026):** módulo "Agente WhatsApp" (`frontend/src/paginas/AgenteWhatsApp.tsx`, visible para `admin` y `recepcionista`). Lista las conversaciones del agente con búsqueda por teléfono o paciente, filtros por estado, sede y agente activo/pausado, y detalle en un panel lateral con los mensajes descifrados (incluye notas de voz transcritas). Permite **pausar o reactivar el agente** en cada hilo sin entrar al admin de Django. La recepcionista solo ve las conversaciones de sus sedes (o sin sede asignada). Incluye métricas de uso: conversaciones totales/activas/pausadas, mensajes de hoy por rol, citas agendadas por el agente en el mes, porcentaje de citas del canal y serie de mensajes de los últimos 14 días. Endpoints (sesión normal, no token de agente): `GET /api/agente/panel/conversaciones/`, `GET /api/agente/panel/conversaciones/<id>/`, `PATCH /api/agente/panel/conversaciones/<id>/actualizar/` y `GET /api/agente/panel/resumen/` (ver `api_agente/panel.py`; el contenido se descifra al leerlo y nunca se expone el ciphertext).
- **Página Métricas del ERP (23/11/2026):** módulo "Métricas" (`frontend/src/paginas/Metricas.tsx`, `frontend/src/api/analitica.ts`) que consume los endpoints de `/api/analitica/` y renderiza tarjetas y gráficas con Ant Design Charts. Filtra por rango de fechas y sede; por defecto usa **del primero del mes actual hasta hoy** y el rango se puede limpiar (vuelve a ese valor) o restablecer con el botón "Mes actual". Las fechas se envían en ISO `AAAA-MM-DD` y el mes como `AAAA-MM`. `atendidos-mes` acepta `mes=AAAA-MM` o `desde`/`hasta`, así la gráfica de pacientes atendidos cubre **todo el rango** (no solo un mes). Las gráficas con muchas fechas o categorías usan **scroll horizontal** para que se vean todos los puntos. Los KPIs y gráficas se muestran según el rol (mismo criterio que `analitica/politicas.py`: el admin ve todo, recepción no ve ingresos, el doctor solo su agenda y el asistente un subconjunto). Incluye citas del rango, pacientes atendidos del rango, cobrado en el rango, citas de hoy por estado, atendidos por día, citas por hora, por tipo de trabajo, por sede e ingresos (solo admin). El backend sigue validando rol y sedes en cada llamada.
- **Registro de pacientes:** datos acumulables entre mensajes, fecha en formato hondureño (`DD/MM/AAAA`) o ISO, edad calculada y DNI obligatorio para adultos. Django descarta la fecha o el DNI que el modelo proponga si el paciente no los escribió (guardas `_fecha_mencionada`/`_identidad_mencionada`) y los vuelve a pedir conservando el resto del borrador.
- **Argumentos del modelo:** las tools validan los ids (`_entero`) antes de consultar; un `sede_id` o `paciente_id` no numérico devuelve error al modelo en vez de romper el worker.
- **Comando de diagnóstico:** `manage.py probar_llm` prueba el modelo contra 13 frases (incluye fugas de datos y temas ajenos); con `--respuestas` muestra la respuesta final que vería el paciente usando herramientas simuladas (no escribe en la BD).
- **Asistente interno del ERP (sección 5.4) — implementado en `analitica`:**
  - `views.py`: endpoints `citas-hoy`, `atendidos-mes`, `por-servicio`, `por-hora`, `por-sede` e `ingresos` con formato común `{titulo, tipo_grafica, ejes, datos, total, filtros}`; rango máximo de 366 días. `atendidos-mes` acepta `mes=AAAA-MM` (mes completo) o `desde`/`hasta` (todos los días del rango).
  - `politicas.py`: matriz de consultas por rol. Admin ve todo (incluye ingresos); recepcionista no ve ingresos; asistente solo agenda del día, por hora y por servicio; doctor solo su propia agenda.
  - `registros.py`: herramienta `consultar_registros` (pacientes, doctores, especialidades, tipos de trabajo, sedes, atenciones, lista de espera, pagos, pagos a doctores, jornadas externas, personal) con filtros tipados, agrupación, `limite` ≤ 50 y `suma_total`. Excluye a propósito DNI, correo, dirección, datos clínicos e ids.
  - `estrategia.py`: herramienta `analisis_estrategico` (ver 5.4). Cada sección aparece solo si el rol tiene acceso; las citas respetan el alcance por sede y por doctor. Las proyecciones son una regresión lineal sobre los meses completos.
  - `asistente.py`: vista `POST /api/analitica/asistente/`, prompt por rol, persistencia de conversaciones (`ConversacionAsistente`/`MensajeAsistente`, últimos 10 mensajes), endpoints `asistente/conversaciones/` (listar, ver, borrar; privadas por usuario), 503 si el LLM falla y respaldo con los datos si la redacción sale vacía.
  - **Llamadas escritas como texto:** si el modelo devuelve la llamada con marcas DSML en el contenido, se parsea y se ejecuta (`api_agente/llamadas_textuales.py`, compartido con el agente de WhatsApp). Las marcas nunca llegan al usuario.
  - **Frontend:** `frontend/src/paginas/Asistente.tsx` (chat, gráficas con color por categoría, historial de conversaciones, sugerencias por rol) y entrada "Asistente IA" en el menú.
- **Seguridad de sesión y permisos (23/11/2026):** settings de cookies (HttpOnly, SameSite, Secure en producción), expiración por inactividad de 8 h, HSTS/SSL redirect y cabeceras (`X-Frame-Options`, `nosniff`, `Referrer-Policy`), configurables por entorno (ver §6 y `.env.example`). El test intermitente de 2FA se corrigió fijando el reloj TOTP también al confirmar el dispositivo: el código y su validación caen siempre en el mismo paso de 30 s (se ejecutó `users.test_2fa` 5 veces seguidas sin fallos). `django-axes` quedó probado: bloqueo por usuario+IP, `429` con `Retry-After`, no bloquea al resto de la red y se reinicia con un login correcto. Se añadió una auditoría automática de permisos por endpoint (anónimo rechazado, recepcionista sin módulos de admin, doctor sin escritura de catálogos) y la validación de que el doctor de una historia/odontograma tenga la sede asignada.
- **Correo e invitaciones (23/11/2026):** el envío usa SMTP real por variables de entorno (Gmail con contraseña de aplicación en demo; proveedor transaccional en producción). `send_mail` ya no falla en silencio: si el SMTP rechaza el envío, la invitación se elimina y la API responde 400 con un mensaje claro. El comando `manage.py probar_correo <destino>` envía una prueba y muestra el SMTP configurado; se añadieron `EMAIL_USE_SSL` y `EMAIL_TIMEOUT`. En la máquina de desarrollo quedó configurado Gmail (`smtp.gmail.com:587`, TLS) y el envío se verificó a `carlosdario13hent@gmail.com`. El `.env` debe guardarse en UTF-8 **sin BOM**: con BOM, django-environ imprime `Invalid line` al leer la primera línea.
- **Historia clínica y odontograma (23/11/2026):** modelos `HistoriaClinica`, `Odontograma` y `HallazgoDental` (numeración FDI 11-48 y 51-85, caras y estados) con `simple-history`, migración `pacientes.0006`; endpoints `/api/historias-clinicas/` y `/api/odontogramas/` con filtros por paciente/sede/fecha y acción `historial/` para auditoría. La pantalla `HistoriaClinica.tsx` permite buscar al paciente, registrar entradas con todos sus campos, editarlas sin borrarlas, ver la auditoría de cada registro y guardar odontogramas.
  - **Odontograma animado e interactivo (`componentes/OdontogramaDental.tsx`):** dibuja las piezas con SVG y una animación de entrada escalonada; alterna dentición permanente/temporal; las piezas con hallazgos se pintan con el color del estado registrado (leyenda incluida) y muestran un contador si tienen varios. En los odontogramas guardados, al hacer clic en una pieza se abre un Popover con su información; los hallazgos también se listan como etiquetas con botón para quitarlos. En el editor, el clic selecciona la pieza para agregar/quitar hallazgos por cara, estado y observación. Los odontogramas guardados se pueden editar (PATCH que reemplaza los hallazgos) o eliminar hallazgos sueltos sin abrir el editor. Incluye "Copiar último" para partir del odontograma anterior.
  - **Corrección del guardado (23/11/2026):** los formularios de historia y odontograma usan `forceRender` para que `setFieldsValue` se aplique con el formulario montado, y `validateFields` se captura para que un campo inválido muestre el error en vez de dejar el modal sin respuesta. El odontograma ya no usa un formulario anidado: los hallazgos viven en estado de React y se envían al guardar.
- **Tests:** 505 en total, todos en verde. `analitica` cubre formato de endpoints, permisos por rol y sede, registros, llamadas textuales, conversaciones, proyecciones y contenido del análisis estratégico; `api_agente` cubre webhook, deduplicación, cifrado, borradores, confirmación explícita, aislamiento de pacientes por teléfono, pausa del agente, limpieza de ` thinking`, argumentos inválidos, alta de pacientes, cancelación/modificación de citas, avisos al administrador, transcripción de audio (caché del modelo, idioma, VAD, fallos y respaldo), descarte de mensajes atrasados o anteriores al arranque y el panel del agente (permisos por rol y sede, descifrado, pausa/reactivación y métricas); `pacientes` cubre historia clínica, odontograma y coherencia doctor-sede; `users` cubre invitaciones, 2FA, recuperación, fallo de envío de correo, bloqueo de intentos con `django-axes` y auditoría de permisos por endpoint.

### 15.3 Cómo probar el agente

1. Levantar infra, `runserver` y el worker (reiniciarlo tras cada cambio en `tasks.py`, `agente.py` o `.env`).
2. Escribir por WhatsApp al número vinculado desde **otro** teléfono.
3. Frases útiles: `hola`, `¿qué sedes tienen?`, `quiero una cita mañana en San Pedro`, `quiero registrarme, me llamo ...`.
4. Para tomar el hilo como persona: escribir desde el WhatsApp de la clínica (pausa automática) o usar las acciones del admin. Luego "Reactivar el agente" en el admin.
5. Prueba sin WhatsApp ni BD: `manage.py probar_llm --respuestas`.
6. Para enseñar una respuesta nueva: agregar la tupla `(mensaje, respuesta)` en `api_agente/contexto.py`. No hace falta migración ni reiniciar el worker si solo se cambian ejemplos (el módulo se recarga con el proceso; reiniciar el worker si se editó mientras corría).
7. Para probar el audio: enviar una nota de voz con el worker escuchando también la cola `audio` (`-Q default,audio`). La primera vez descarga el modelo de Whisper y tarda más. Si la transcripción falla o no se entiende, el agente pide que se lo escriban.
8. Para probar el filtro de mensajes viejos: apagar Django y el worker, escribir por WhatsApp y volver a arrancar. Al reconectar, Evolution reenvía el evento con una marca de tiempo antigua: el webhook debe registrarlo en el log como ignorado y no debe aparecer respuesta. Con un mensaje nuevo (enviado con el sistema encendido) el agente responde normal.
9. Panel del agente: entrar al ERP con `admin` o `recepcionista` → menú **Agente WhatsApp**. Abrir un hilo para ver los mensajes descifrados, pulsar **Pausar** / **Reactivar** para cambiar quién responde y revisar las métricas arriba. La recepcionista solo ve las conversaciones de sus sedes.

### 15.4 Límites conocidos y pendientes

- **Audio:** implementado con `faster-whisper` (ver 15.2). La primera transcripción descarga el modelo a la caché de Hugging Face (decenas o cientos de MB según `WHISPER_MODEL`); si no está instalado `faster-whisper`, el agente pide al paciente que escriba en vez de romper el worker. El audio nunca se guarda en disco ni en BD: solo el texto transcrito. Verificado de punta a punta con un WAV en español (`tiny`, CPU). Se fija `av>=11,<17` porque PyAV 19 rechaza `metadata_errors`, que faster-whisper usa al decodificar. Si la GPU carga el modelo pero falla al transcribir (caso típico en Windows: `Library cublas64_12.dll is not found`), `transcripcion.py` recarga el modelo en CPU y reintenta una vez; el proceso queda en CPU. En máquinas sin cuBLAS conviene poner `WHISPER_DEVICE=cpu` para no perder el primer intento.
- **Mensajes al reiniciar:** el filtro de `vigencia.py` es por tiempo: se ignoran los mensajes con más de `WHATSAPP_MENSAJE_MAX_ANTIGUEDAD_SEGUNDOS` (300 s) y los enviados más de `WHATSAPP_ARRANQUE_TOLERANCIA_SEGUNDOS` (90 s) antes de arrancar. Subir o bajar esas variables ajusta el rigor; el filtro no borra la conversación existente, solo evita responder mensajes viejos.
- **Notificaciones internas:** `api_agente/notificaciones.py` avisa por WhatsApp al número de `ADMIN_WHATSAPP` cuando el agente crea, modifica o cancela una cita, o cuando el paciente pide un tratamiento fuera del catálogo. Es informativo: si el envío falla, la acción del paciente no se interrumpe. Los recordatorios programados seguirán en n8n.
- **Honorario de las citas creadas por el agente:** se guarda en 0 y el personal lo ajusta después.
- **Dirección del paciente:** si no la da, se guarda la de la sede (no la suya). Conviene que recepción la corrija.
- **Asistente interno:** implementado (ver 15.2). Límites: las proyecciones son lineales y con pocos meses de datos pueden desviarse; no hay retención automática de conversaciones (hoy se borran a mano); el asistente redacta con el LLM, así que la forma de la respuesta puede variar, pero las cifras salen del backend.
- **Panel de pausa:** disponible en el frontend (módulo "Agente WhatsApp", 23/11/2026) y en el admin de Django; ambos permiten pausar/reactivar cada hilo. El panel del ERP además muestra las conversaciones y sus métricas de uso.
- **Modelo:** `llama3.1:8b` a veces llama una herramienta innecesaria (por ejemplo `listar_sedes` al saludar o `cancelar_accion` ante un dolor). La respuesta final es correcta, pero gasta una llamada extra. Si molesta, filtrar por intención antes de darle tools. También tiende a rellenar huecos con datos inventados: por eso las guardas de Django son la defensa real, no el prompt.
- **Contexto:** los ejemplos son few-shot en `contexto.py`. No se usa `pgvector`: con decenas de casos no aporta y añade infraestructura. Si algún día hay cientos de políticas o preguntas frecuentes para recuperar, ahí sí conviene RAG con `pgvector`.
- **Git:** último commit `993fa06` (actualizando clínica). **Sin commitear:** cambios de seguridad/correo/tests listados antes, más el panel del agente (`api_agente/panel.py`, `api_agente/test_panel.py`, `api_agente/urls.py`, `frontend/src/api/agente.ts`, `frontend/src/paginas/AgenteWhatsApp.tsx`), la página de métricas (`frontend/src/api/analitica.ts`, `frontend/src/paginas/Metricas.tsx`), `App.tsx`, `LayoutPrincipal.tsx` y este plan. `backend/.env` (no versionado) ya tiene Gmail y `WHISPER_DEVICE=cpu` en esta máquina.

### 15.5 Cómo probar el asistente interno

1. Con `runserver` en marcha, entrar al ERP con un usuario `admin` y abrir **Asistente IA** en el menú.
2. Preguntas útiles: `¿cuántas citas hay hoy?`, `¿cuántos pacientes se atendieron este mes?`, `citas por servicio de los últimos 30 días`.
3. Plan estratégico: `haz un plan estratégico: cuántas personas se atienden, proyección y qué tratamientos conviene impulsar`. Debe traer diagnóstico con cifras, proyección, tratamientos en crecimiento y recomendaciones.
4. Comprobar el aislamiento: con un usuario `recepcionista` no debe aparecer información de ingresos; con un `doctor`, solo sus propias citas.
5. Sin LLM disponible, el endpoint responde 503; si el modelo no redacta, la respuesta se arma con los datos de la consulta.
6. Si se cambió `asistente.py`, `estrategia.py` o `registros.py`, reiniciar `runserver` antes de probar.

### 15.6 Punto de retorno (próxima sesión)

**Estado al cierre del 23/11/2026:** historia clínica y odontograma completos (odontograma animado con dentición permanente/temporal, colores por estado, detalle al clic, edición de odontogramas guardados y borrado de hallazgos, auditoría con `simple-history`); guardado corregido y migración `pacientes.0006` aplicada en la BD local. Agente: filtro de mensajes viejos al reiniciar (`vigencia.py`) y reintento de Whisper en CPU cuando la GPU falla por `cublas64_12.dll` (`WHISPER_DEVICE=cpu` en esta máquina). **Panel del agente en el frontend:** conversaciones, detalle descifrado, pausa/reactivación por hilo y métricas de uso (ver 15.2). **Página Métricas:** KPIs y gráficas de citas, atención e ingresos por rol y sede (ver 15.2). Correo real con Gmail configurado y verificado, con `probar_correo` y manejo de fallos de invitación. Seguridad: cookies/sesión endurecidas, `django-axes` probado (usuario+IP, `429` con `Retry-After`), test 2FA estable, auditoría de permisos por endpoint y validación doctor-sede en historia/odontograma. **505 tests en verde.**

**Primero, antes de seguir:**
1. Commitear los cambios pendientes del 23/11 (ver 15.4).
2. En cualquier máquina nueva, correr `manage.py migrate` (incluye `pacientes.0006`; sin ella, guardar historia/odontograma falla).
3. Reiniciar `runserver` (toma SMTP de Gmail, cookies/sesión y el nuevo login con `django-axes`) y el worker con `-Q default,audio`. `WHISPER_DEVICE=cpu` ya está en `backend/.env`.
4. Probar el flujo completo de invitación con un correo real: admin crea usuario → llega el enlace → el invitado define usuario/contraseña. Si el enlace se abre desde otro dispositivo, usar una `FRONTEND_URL` pública (ngrok/cloudflared) y añadirla a `DJANGO_CSRF_TRUSTED_ORIGINS`/`DJANGO_ALLOWED_HOSTS`.
5. Si el agente no recibe mensajes, revisar primero la sesión de WhatsApp de Evolution (instancia `open` pero sin eventos): reiniciar desde `/manager` o con `POST /instance/restart/luna-ia`, y confirmar que el hilo tenga `agente_activo` marcado.
6. Redis es obligatorio para el login: `django-axes` y la caché de Django lo usan. Si está apagado, levantar `docker compose -f infra/docker-compose.dev.yml up -d redis`.

**Incidencia 23/11/2026 (entorno, no código):** Evolution/Baileys dejó de entregar mensajes nuevos aunque la instancia figuraba `open`; su BD no registraba mensajes desde las 11:00. Se reinició la instancia y volvió a `open`. Los chats de prueba quedaron pausados (`agente_activo=False`), lo que también impide respuesta. El reinicio de la instancia no borra la sesión ni el webhook.

**LLM:** al 23/11 `backend/.env` apunta a OpenCode Go (`deepseek-v4.1-flash`). Si vuelve el 429 mensual, cambiar a Ollama local (`LLM_PROVIDER=ollama`, `LLM_BASE_URL=http://127.0.0.1:11434/v1`, `LLM_MODEL=llama3.1:8b`).

> **Nota 21/11/2026 — modelo gratuito:** `deepseek-v4.1-flash-free` **no** está incluido en el plan OpenCode Go; el endpoint `https://opencode.ai/inference/go/openai/v1` devuelve 400 (`isn't included in OpenCode Go`). Solo sirve `deepseek-v4.1-flash` (de pago). Además, el endpoint exige la cabecera `x-opencode-session` en cada petición.

**Siguiente según cronograma (S6, 19–25 nov):**
1. ~~Historia clínica + odontograma~~ — **hecho 23/11/2026** (ver 15.2). Falta probarlo manualmente en el navegador con datos reales y una nota de voz.
2. Endurecimiento de seguridad — **hecho 23/11/2026**: correo real, invitaciones con reversión, test 2FA estable, cookies/sesión seguras, HSTS/SSL, cabeceras, `django-axes` probado (usuario+IP, `429`/`Retry-After`) y auditoría de permisos por endpoint. Falta probar de punta a punta la recuperación de contraseña real y el reset de 2FA desde el admin.
3. Inventario (marcado como "deseable": posponer si aprieta el tiempo).
4. Menores: retención de conversaciones del asistente y revisión de `procesar_audio` en producción (el plan prevé cambiar Whisper por una API de STT). ~~Botón de pausa del agente en el frontend~~ — **hecho 23/11/2026** (módulo "Agente WhatsApp").

**Orden sugerido para la próxima sesión:**
1. `git add`/commit de todo lo pendiente y `manage.py test` (debe dar 505).
2. Abrir el ERP, verificar login con bloqueo de intentos, invitar un usuario a Gmail y aceptar la invitación.
3. Probar recuperación de contraseña real y reset de 2FA desde el admin.
4. Decidir si entra inventario o si se pasa directo a pruebas/demo de S7.

**Después (S7, 26 nov–5 dic):** pruebas integrales, corregir hallazgos, ensayo de demo y cierre documental (informe final, manual de usuario, capturas).
