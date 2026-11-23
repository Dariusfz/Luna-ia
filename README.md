# LUNA-IA — ERP Clínico con IA

ERP para una clínica odontológica con 3 sedes, agente de IA en WhatsApp y asistente interno.
Proyecto académico (Sistemas Abiertos II) con intención comercial.

La fuente de verdad del proyecto es [`docs/PLAN.md`](docs/PLAN.md).

## Stack

- **Backend:** Django 5 + Django REST Framework + PostgreSQL 16 + Redis + Celery.
- **Frontend:** React + Vite + TypeScript + Ant Design 5.
- **IA:** LLM agnóstico compatible-OpenAI (Ollama en desarrollo, API en producción).
- **Infra local:** Docker Compose (PostgreSQL, Redis, MinIO y Mailpit).
- **WhatsApp:** Evolution API (dev) → Meta Cloud API (producción).

## Requisitos

- Git
- Docker Desktop (o Docker Engine + Compose)
- Python 3.12+
- Node.js 20.19+ / 22.12+ y npm
- Opcional: [Ollama](https://ollama.com/) con un modelo compatible (`qwen3:8b` por defecto)

## Puesta en marcha

### 1. Clonar el repositorio

```bash
git clone <URL_DEL_REPOSITORIO>
cd LUNA_IA
```

### 2. Levantar los servicios de infraestructura

Crear el archivo de credenciales a partir del ejemplo:

```powershell
# Windows
Copy-Item infra\.env.example infra\.env
```

```bash
# Linux / macOS
cp infra/.env.example infra/.env
```

Editar `infra/.env` y definir contraseñas propias (no se versiona; el compose no
arranca si falta alguna). Compose lo lee automáticamente por estar junto al
`docker-compose.dev.yml`.

```bash
docker compose -f infra/docker-compose.dev.yml up -d
```

Servicios disponibles:

| Servicio | URL |
|---|---|
| PostgreSQL | `127.0.0.1:5432` (BD `luna_ia`, usuario `luna`, contraseña en `infra/.env`) |
| Redis | `127.0.0.1:6379` |
| MinIO (API / consola) | `127.0.0.1:9000` / `http://127.0.0.1:9001` (credenciales en `infra/.env`) |
| Mailpit (correo de desarrollo) | `http://127.0.0.1:8025` |

### 3. Configurar y ejecutar el backend

```bash
cd backend
```

Crear el entorno virtual e instalar dependencias:

```powershell
# Windows (PowerShell)
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

```bash
# Linux / macOS
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Crear el archivo de entorno a partir del ejemplo:

```powershell
# Windows
Copy-Item .env.example .env
```

```bash
# Linux / macOS
cp .env.example .env
```

Generar los secretos y pegarlos en `backend/.env`:

```bash
python -c "import secrets; print(secrets.token_urlsafe(64))"
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Luego aplicar migraciones y crear el usuario administrador:

```bash
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

> Al iniciar sesión con un superusuario o con rol `admin`/`doctor`, el sistema pedirá
> configurar la autenticación de dos pasos (TOTP) con una app como Google Authenticator.

### 4. Ejecutar el frontend

En otra terminal:

```bash
cd frontend
npm install
npm run dev
```

Vite reenvía `/api` a `http://127.0.0.1:8000`, por lo que no hace falta configurar una URL de API.

## URLs de desarrollo

| Recurso | URL |
|---|---|
| Frontend | `http://localhost:5173` |
| API / Swagger | `http://127.0.0.1:8000/api/docs/` |
| Admin de Django | `http://127.0.0.1:8000/admin/` |
| Correo de desarrollo (Mailpit) | `http://127.0.0.1:8025` |

## Variables de entorno

Todas las variables viven en `backend/.env` (no se versiona). Referencia completa:
[`backend/.env.example`](backend/.env.example).

Las credenciales de los contenedores viven en `infra/.env` (tampoco se versiona);
referencia: [`infra/.env.example`](infra/.env.example). `DATABASE_URL` en
`backend/.env` debe coincidir con `POSTGRES_USER`, `POSTGRES_PASSWORD` y
`POSTGRES_DB` de `infra/.env`.

| Variable | Descripción | Valor por defecto en desarrollo |
|---|---|---|
| `DJANGO_SECRET_KEY` | Clave secreta de Django | — (obligatoria) |
| `DJANGO_DEBUG` | Modo depuración | `True` |
| `DJANGO_ALLOWED_HOSTS` | Hosts permitidos (separados por coma) | `localhost,127.0.0.1` |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Orígenes de confianza para CSRF | `http://localhost:5173,...` |
| `DATABASE_URL` | Conexión PostgreSQL | — (obligatoria; debe coincidir con `infra/.env`) |
| `REDIS_URL` | Redis para caché y Celery | `redis://127.0.0.1:6379/0` |
| `FRONTEND_URL` | Enlaces de invitación/recuperación | `http://localhost:5173` |
| `EMAIL_HOST` / `EMAIL_PORT` | SMTP saliente | Mailpit en `127.0.0.1:1025` |
| `EMAIL_USE_TLS` | STARTTLS del SMTP (puerto 587) | `False` |
| `EMAIL_USE_SSL` | SSL directo del SMTP (puerto 465) | `False` |
| `EMAIL_TIMEOUT` | Segundos de espera del SMTP | `15` |
| `EMAIL_HOST_USER` / `EMAIL_HOST_PASSWORD` | Credenciales SMTP | vacío |
| `DEFAULT_FROM_EMAIL` | Remitente de correos | `LUNA-IA <no-reply@luna-ia.local>` |
| `TOTP_ENCRYPTION_KEY` | Clave Fernet para cifrar secretos TOTP | derivada de `DJANGO_SECRET_KEY` en dev |
| `LLM_PROVIDER` | Proveedor del LLM | `ollama` |
| `LLM_BASE_URL` | Endpoint compatible-OpenAI | `http://127.0.0.1:11434/v1` |
| `LLM_API_KEY` | Clave del proveedor LLM | vacío en dev |
| `LLM_MODEL` | Modelo a usar | `qwen3:8b` |

### Correo real (Gmail u otro SMTP)

Mailpit solo **captura** correos en `http://127.0.0.1:8025`; no los entrega a Gmail ni a
ninguna bandeja. Para que las invitaciones y la recuperación de contraseña lleguen de
verdad, configura un SMTP en `backend/.env`. Ejemplo con Gmail (requiere verificación en
dos pasos y una [contraseña de aplicación](https://myaccount.google.com/apppasswords)):

```env
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_USE_SSL=False
EMAIL_HOST_USER=tu.cuenta@gmail.com
EMAIL_HOST_PASSWORD=abcd efgh ijkl mnop   # sin espacios
DEFAULT_FROM_EMAIL="LUNA-IA <tu.cuenta@gmail.com>"
FRONTEND_URL=http://localhost:5173
```

Comprobar el envío sin crear usuarios:

```bash
cd backend
python manage.py probar_correo destino@gmail.com
```

`FRONTEND_URL` debe ser una dirección que el destinatario pueda abrir: `localhost`
solo sirve si el correo se abre en la misma máquina. Para probar desde un teléfono usa
la URL de ngrok/cloudflared del frontend. En producción, usa el SMTP del dominio de la
clínica (o un proveedor transaccional como Resend/Brevo/SendGrid), no un Gmail personal;
Gmail limita los envíos diarios.

### Seguridad de sesión

Con `DJANGO_DEBUG=False` se activan automáticamente cookies `Secure`, redirección a HTTPS
y HSTS. La sesión expira por inactividad a las 8 horas. Si necesitas ajustarlo (demo sin
TLS o un dominio distinto), usa en `backend/.env`:

```env
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True
SESSION_COOKIE_AGE_SEGUNDOS=28800
SESSION_SAVE_EVERY_REQUEST=True
SECURE_SSL_REDIRECT=True
SECURE_HSTS_SECONDS=31536000
```

Detrás de Caddy/nginx el backend confía en `X-Forwarded-Proto`; asegúrate de que el proxy
lo envíe (Caddy lo hace por defecto).

El login usa `django-axes`: tras 5 intentos fallidos para el mismo usuario desde la misma
IP, la cuenta queda bloqueada 15 minutos y la API responde `429` con `Retry-After`. Un login
correcto reinicia el contador y el bloqueo no afecta a los demás usuarios de la red.

Para usar Ollama en local:

```bash
ollama pull qwen3:8b
```

## Estructura del repositorio

```
LUNA_IA/
├─ backend/   Django + DRF, apps por dominio y migraciones
├─ frontend/  React + Vite + TypeScript + Ant Design
├─ infra/     Docker Compose para desarrollo
├─ docs/      Plan del proyecto y documentación
└─ img/       Recursos gráficos
```

## Pruebas y verificación

```bash
# Backend (requiere PostgreSQL y Redis levantados)
cd backend
python manage.py test

# Frontend
cd frontend
npm run lint
npm run build
```

Exportar en la máquina de origen:

```powershell
New-Item -ItemType Directory -Force backups
docker exec luna-ia-dev-postgres-1 pg_dump -U luna -d luna_ia -Fc --no-owner --no-privileges -f /tmp/luna_ia.dump
docker cp luna-ia-dev-postgres-1:/tmp/luna_ia.dump .\backups\luna_ia.dump
```

Importar en la máquina de destino (con los servicios levantados):

```powershell
docker cp .\backups\luna_ia.dump luna-ia-dev-postgres-1:/tmp/luna_ia.dump
docker exec -it luna-ia-dev-postgres-1 pg_restore -U luna -d luna_ia --clean --if-exists --no-owner --no-privileges /tmp/luna_ia.dump
```

> Detén `python manage.py runserver` antes de importar para evitar conexiones abiertas.

Las contraseñas de los usuarios están hasheadas y no se pueden leer. Después de importar:

```powershell
# Permite que cada usuario configure su propio 2FA al entrar
docker exec -it luna-ia-dev-postgres-1 psql -U luna -d luna_ia -c "DELETE FROM users_dispositivotp; DELETE FROM users_codigorecuperacion;"

# Cambiar la contraseña de un usuario
cd backend
python manage.py changepassword <usuario>
```

Si prefieres conservar el 2FA existente, comparte también `TOTP_ENCRYPTION_KEY` de
`backend/.env` por el mismo canal privado.


## Publicar en GitHub

```bash
git init
git add .
git commit -m "chore: preparar repositorio para GitHub"
git branch -M main
git remote add origin <URL_DEL_REPOSITORIO>
git push -u origin main
```

Con GitHub CLI:

```bash
gh repo create LUNA_IA --private --source=. --remote=origin --push
```

