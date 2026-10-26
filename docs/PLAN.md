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
Paciente ─► WhatsApp ─► Evolution/Cloud API ─webhook─► n8n ─► LLM (Ollama dev / API prod)
                                                          ├─► Backend Django (API)
                                                          └─► Whisper (audio → texto)
Personal ─► (cloudflared opcional) ─► reverse proxy ─► [React + /api] ─► Django
                                                                        ├─► PostgreSQL
                                                                        ├─► Redis
                                                                        └─► MinIO
```

- **Dev/local:** todo en una máquina (16 GB) + Ollama en GPU + Whisper local.
- **Producción (venta):** VPS con reverse proxy (Caddy/TLS). El LLM va por **API en la nube**; Ollama no se usa en producción.
- **Ollama y Whisper** se ejecutan en el host (fuera de Docker), con la GPU. En producción se reemplazan por APIs.

## 4. Stack tecnológico

| Capa | Tecnología |
|---|---|
| Backend | Django 5 + Django REST Framework + `drf-spectacular` (OpenAPI) |
| Base de datos | PostgreSQL 16 (+ extensión `pgvector` reservada para futuro RAG) |
| Caché / colas | Redis + Celery (recordatorios, llamadas al LLM) |
| Archivos | MinIO (radiografías, fotos, documentos) vía `django-storages` |
| Frontend | React + Vite + TypeScript + **Ant Design 5** (`@ant-design/icons`, `@ant-design/charts`) |
| Estado/datos front | TanStack Query + React Router |
| LLM | Cliente **agnóstico** compatible-OpenAI (`httpx`): Ollama en dev, API en prod |
| Audio (STT) | **faster-whisper** local (`small`/`base`, `language=es`) |
| Automatización | n8n |
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
LLM_MODEL=qwen3:8b                      # dev; en prod el modelo de la API
```

- **Dev:** Ollama + `qwen3:8b` (respaldos: `llama3.1:8b`, `qwen3:4b`).
- **Prod/cliente:** modelo en la nube vía API (VPS pagado por membresía).

### 5.2 Agente de WhatsApp (n8n)
- Tools que llaman al backend (nunca SQL ni tocar la BD directamente):
  `crear_cita`, `modificar_cita`, `cancelar_cita`, `consultar_disponibilidad`.
- **Un solo número de WhatsApp** para las 3 sedes: n8n **debe resolver la sede** (si el paciente no la menciona, la pregunta antes de agendar). La sede es argumento obligatorio y se valida en Django.
- **Reglas de negocio y permisos viven en Django**, no en el prompt.

### 5.3 Audio (notas de voz)
Flujo: audio (OGG/Opus) → descargar → **Whisper** → texto en español → entra al agente como mensaje normal.
- Servicio de transcripción local con endpoint HTTP; n8n lo invoca.
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
- `Paciente` (global, sede de origen), `HistoriaClinica`, `Odontograma`
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
