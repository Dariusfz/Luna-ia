import { api } from './cliente'
import type { Paginado } from './recursos'
import type { EstadoEspera, PrioridadEspera } from '../constantes/listaEspera'

export type ListaEspera = {
  id: number
  sede: number
  sede_nombre: string
  paciente: number
  paciente_nombre: string
  doctor: number | null
  doctor_nombre: string | null
  tipo_trabajo: number | null
  tipo_trabajo_nombre: string | null
  prioridad: PrioridadEspera
  prioridad_nombre: string
  estado: EstadoEspera
  estado_nombre: string
  fecha_deseada: string | null
  motivo: string
  atencion: number | null
  atencion_fecha: string | null
  atencion_hora_inicio: string | null
  creada: string
  actualizada: string
}

export type FiltrosListaEspera = {
  sede?: number | null
  doctor?: number | null
  estado?: EstadoEspera | EstadoEspera[] | null
  prioridad?: PrioridadEspera | null
  q?: string
}

export const listarListaEspera = (pagina: number, f: FiltrosListaEspera) => {
  const params = new URLSearchParams({ page: String(pagina) })
  if (f.sede) params.set('sede', String(f.sede))
  if (f.doctor) params.set('doctor', String(f.doctor))
  if (f.estado) {
    const estados = Array.isArray(f.estado) ? f.estado.join(',') : f.estado
    params.set('estado', estados)
  }
  if (f.prioridad) params.set('prioridad', String(f.prioridad))
  if (f.q) params.set('q', f.q)
  return api<Paginado<ListaEspera>>(`/lista-espera/?${params.toString()}`)
}

export type DatosEspera = {
  sede: number
  paciente: number
  doctor?: number | null
  tipo_trabajo?: number | null
  prioridad?: PrioridadEspera
  estado?: EstadoEspera
  fecha_deseada?: string | null
  motivo?: string
}

export const crearEspera = (datos: DatosEspera) =>
  api<ListaEspera>('/lista-espera/', { method: 'POST', json: datos })

export const actualizarEspera = (id: number, datos: Partial<DatosEspera>) =>
  api<ListaEspera>(`/lista-espera/${id}/`, { method: 'PATCH', json: datos })

export type DatosAgendarEspera = {
  fecha: string
  hora_inicio: string
  hora_fin: string
  doctor: number
  tipo_trabajo: number
  procedimiento?: string
  observaciones?: string
  honorario_doctor?: number
}

export const agendarEspera = (id: number, datos: DatosAgendarEspera) =>
  api<ListaEspera>(`/lista-espera/${id}/agendar/`, { method: 'POST', json: datos })
