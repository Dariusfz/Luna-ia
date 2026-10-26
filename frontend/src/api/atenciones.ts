import type { EstadoAtencion } from '../constantes/atenciones'
import type { TipoDoctor } from './catalogos'
import { api } from './cliente'
import type { Paginado } from './recursos'

export type Atencion = {
  id: number
  sede: number
  sede_nombre: string
  doctor: number
  doctor_nombre: string
  doctor_tipo: TipoDoctor
  paciente: number
  paciente_nombre: string
  tipo_trabajo: number
  tipo_trabajo_nombre: string
  estado: EstadoAtencion
  fecha: string
  hora_inicio: string
  hora_fin: string
  procedimiento: string
  /** Llega como texto decimal, por ejemplo "300.00". */
  honorario_doctor: string
  observaciones: string
}

export type FiltrosAtenciones = {
  sede?: number | null
  doctor?: number | null
  estado?: EstadoAtencion | EstadoAtencion[] | null
  desde?: string
  hasta?: string
}

export const listarAtenciones = (pagina: number, f: FiltrosAtenciones) => {
  const params = new URLSearchParams({ page: String(pagina) })
  if (f.sede) params.set('sede', String(f.sede))
  if (f.doctor) params.set('doctor', String(f.doctor))
  if (f.estado) {
    const estados = Array.isArray(f.estado) ? f.estado.join(',') : f.estado
    params.set('estado', estados)
  }
  if (f.desde) params.set('desde', f.desde)
  if (f.hasta) params.set('hasta', f.hasta)
  return api<Paginado<Atencion>>(`/atenciones/?${params.toString()}`)
}

export type DatosAtencion = {
  sede: number
  doctor: number
  paciente: number
  tipo_trabajo: number
  estado?: EstadoAtencion
  fecha: string
  hora_inicio: string
  hora_fin: string
  procedimiento?: string
  honorario_doctor: number
  observaciones?: string
}

export const crearAtencion = (datos: DatosAtencion) =>
  api<Atencion>('/atenciones/', { method: 'POST', json: datos })

export const actualizarAtencion = (id: number, datos: Partial<DatosAtencion>) =>
  api<Atencion>(`/atenciones/${id}/`, { method: 'PATCH', json: datos })
