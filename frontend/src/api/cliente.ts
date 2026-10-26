export class ApiError extends Error {
  status: number
  /** Errores por campo devueltos por la API, por ejemplo { telefono: "..." }. */
  campos: Record<string, string>

  constructor(status: number, mensaje: string, campos: Record<string, string> = {}) {
    super(mensaje)
    this.status = status
    this.campos = campos
  }
}

function camposDeError(datos: unknown): Record<string, string> {
  const salida: Record<string, string> = {}
  if (datos && typeof datos === 'object') {
    for (const [clave, valor] of Object.entries(datos as Record<string, unknown>)) {
      if (clave === 'detail' || clave === 'non_field_errors') continue
      if (Array.isArray(valor) && typeof valor[0] === 'string') salida[clave] = valor[0]
      if (typeof valor === 'string') salida[clave] = valor
    }
  }
  return salida
}

type Opciones = Omit<RequestInit, 'body'> & { json?: unknown }

function tokenCsrf(): string | undefined {
  const fila = document.cookie.split('; ').find((c) => c.startsWith('csrftoken='))
  return fila?.split('=')[1]
}

function mensajeDeError(datos: unknown): string {
  if (datos && typeof datos === 'object') {
    const d = datos as Record<string, unknown>
    if (typeof d.detail === 'string') return d.detail
    // Errores de validación: { campo: ["mensaje"] } o { non_field_errors: [...] }
    for (const valor of Object.values(d)) {
      if (Array.isArray(valor) && typeof valor[0] === 'string') return valor[0]
      if (typeof valor === 'string') return valor
    }
  }
  return 'No se pudo completar la operación.'
}

/**
 * Llama a la API bajo /api. Envía cookies de sesión y el token CSRF en métodos que modifican datos.
 * La ruta es relativa a /api, por ejemplo api('/auth/me/').
 */
export async function api<T>(ruta: string, opciones: Opciones = {}): Promise<T> {
  const { json, ...resto } = opciones
  const headers = new Headers(resto.headers)
  const metodo = (resto.method ?? 'GET').toUpperCase()

  let body: BodyInit | undefined
  if (json !== undefined) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(json)
  }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(metodo)) {
    const token = tokenCsrf()
    if (token) headers.set('X-CSRFToken', token)
  }

  const respuesta = await fetch(`/api${ruta}`, {
    ...resto,
    method: metodo,
    headers,
    body,
    credentials: 'same-origin',
  })

  if (respuesta.status === 204) return undefined as T

  const datos: unknown = await respuesta.json().catch(() => null)
  if (!respuesta.ok) {
    throw new ApiError(respuesta.status, mensajeDeError(datos), camposDeError(datos))
  }
  return datos as T
}
