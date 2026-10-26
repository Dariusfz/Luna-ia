# AGENTS.md — LUNA-IA (ERP Clínico)

> La **fuente de verdad** del proyecto es [`docs/PLAN.md`](docs/PLAN.md). Léelo antes de hacer cambios.

## Proyecto

ERP para una clínica odontológica (3 sedes) con agente de IA en WhatsApp y asistente de IA interno. Proyecto académico (entrega 05/12) con intención comercial.

- **Backend:** Django 5 + Django REST Framework + PostgreSQL 16 (+ Redis, Celery, MinIO).
- **Frontend:** React + Vite + TypeScript + **Ant Design 5**.
- **LLM:** agnóstico al proveedor, compatible-OpenAI (`httpx`): Ollama en dev, API en prod.
- **Audio:** faster-whisper local (`language=es`).
- **WhatsApp:** Evolution API (dev) → Meta Cloud API (prod). Un número para las 3 sedes.
- **Infra:** Docker Compose (perfiles `dev`/`prod`), Rocky Linux 9, Caddy en prod.
- **Idioma:** español. Localización: `America/Tegucigalpa`, HNL, +504.

## Estructura del repositorio

```
ProyectoFinal/
├─ backend/   config/ + apps por dominio (users, sedes, pacientes, agenda,
│             servicios, tratamientos, inventario, pagos, documentos,
│             analitica, auditoria, api_agente)
├─ frontend/  React + Vite + Ant Design
├─ infra/     docker-compose.dev.yml, docker-compose.prod.yml, nginx/caddy, cloudflared, backups
└─ docs/      PLAN.md, informes, diagramas, manuales
```

## Reglas de trabajo (obligatorias)

1. **Seguir `docs/PLAN.md`** como fuente de verdad. Si algo contradice el plan, avisar antes de cambiarlo.
2. **LLM siempre por variables de entorno.** Nunca hardcodear proveedor, URL ni API key.
   (`LLM_PROVIDER`, `LLM_BASE_URL`, `LLM_API_KEY`, `LLM_MODEL`)
3. **Reglas de negocio y permisos viven en Django**, nunca en el prompt del LLM.
4. El agente **no toca la BD directamente**: llama endpoints del backend. Nunca SQL libre para el asistente (solo endpoints analíticos).
5. **Sin registro público.** Alta de usuarios solo por invitación de un admin. **2FA TOTP obligatorio para `admin` y `doctor`.**
6. **Multi-sede:** filtrar querysets por las sedes del usuario. El admin ve consolidado.
7. **Auditoría:** usar `django-simple-history` en modelos clínicos.
8. **Ant Design:** usar tokens de tema (`ConfigProvider`) para colores/tipografía; no estilos sueltos. Iconos: `@ant-design/icons`. Gráficas: `@ant-design/charts`.
9. **No incluir facturación** (fuera de alcance).
10. **Idioma:** código y UI en español; nombres de tablas/modelos en inglés solo si el plan lo define.

## Convenciones

- Backend: apps Django por dominio; DRF + `drf-spectacular`; migraciones versionadas.
- Frontend: componentes en Ant Design, estado de servidor con TanStack Query, rutas con React Router.
- Commits: mensajes claros en español (ej. `feat(agenda): crear cita con validación de sede`).

## Comandos (actualizar cuando existan)

```bash
# Levantar entorno de desarrollo
docker compose -f infra/docker-compose.dev.yml up -d

# Backend: migraciones y servidor
docker compose -f infra/docker-compose.dev.yml exec backend python manage.py migrate
docker compose -f infra/docker-compose.dev.yml exec backend python manage.py runserver

# Frontend
cd frontend && npm install && npm run dev

# LLM local (host, con GPU)
ollama pull qwen3:8b
```

## Pendientes / recordatorios

- Crear estructura base de la Semana 1 (repo, compose, esqueleto Django/React).
- Decidir proveedor de correo transaccional al momento de vender.
- Añadir confirmación de dispositivo nuevo por correo (solo si sobra tiempo).
