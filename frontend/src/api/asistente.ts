import { api } from './cliente'

export interface PuntoGrafica {
  etiqueta: string
  valor: number
}

/** Formato común de las consultas de /api/analitica/ (ver backend/analitica/views.py). */
export type TipoGrafica = 'barras' | 'linea' | 'pastel' | 'puntos'

export interface GraficaAnalitica {
  titulo: string
  tipo_grafica: TipoGrafica
  ejes: { x: string; y: string }
  datos: PuntoGrafica[]
  total: number
  filtros: { desde?: string; hasta?: string; sede?: number | null }
}

export interface RespuestaAsistente {
  conversacion: number
  respuesta: string
  grafica: GraficaAnalitica | null
}

export interface ConversacionResumen {
  id: number
  titulo: string
  creada: string
  actualizada: string
}

export interface MensajeGuardado {
  id: number
  rol: 'usuario' | 'asistente'
  texto: string
  grafica: GraficaAnalitica | null
  creado: string
}

export interface ConversacionDetalle extends ConversacionResumen {
  mensajes: MensajeGuardado[]
}

export interface Paginado<T> {
  count: number
  results: T[]
}

export function preguntarAsistente(
  pregunta: string,
  conversacion: number | null,
): Promise<RespuestaAsistente> {
  return api<RespuestaAsistente>('/analitica/asistente/', {
    method: 'POST',
    json: conversacion ? { pregunta, conversacion } : { pregunta },
  })
}

export function listarConversaciones(): Promise<Paginado<ConversacionResumen>> {
  return api<Paginado<ConversacionResumen>>('/analitica/asistente/conversaciones/')
}

export function obtenerConversacion(id: number): Promise<ConversacionDetalle> {
  return api<ConversacionDetalle>(`/analitica/asistente/conversaciones/${id}/`)
}

export function eliminarConversacion(id: number): Promise<void> {
  return api<void>(`/analitica/asistente/conversaciones/${id}/`, { method: 'DELETE' })
}
