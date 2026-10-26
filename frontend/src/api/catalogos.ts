import { api } from './cliente'
import type { FiltroActivo, Paginado } from './recursos'

// ---------- Especialidades ----------

export type Especialidad = {
  id: number
  nombre: string
  activo: boolean
}

export const listarEspecialidades = (activo: FiltroActivo = 'todos') =>
  api<Paginado<Especialidad>>(`/especialidades/${query({ activo })}`)

export type DatosEspecialidad = {
  nombre: string
  activo?: boolean
}

export const crearEspecialidad = (datos: DatosEspecialidad) =>
  api<Especialidad>('/especialidades/', { method: 'POST', json: datos })

export const actualizarEspecialidad = (id: number, datos: Partial<DatosEspecialidad>) =>
  api<Especialidad>(`/especialidades/${id}/`, { method: 'PATCH', json: datos })

// ---------- Doctores ----------

export type TipoDoctor = 'propio' | 'contratado'

export type Doctor = {
  id: number
  tipo: TipoDoctor
  nombres: string
  apellidos: string
  especialidad: number | null
  especialidad_nombre: string | null
  numero_colegiado: string
  telefono: string
  activo: boolean
  sedes: number[]
  /** Solo lo ve el administrador. */
  observaciones?: string
  usuario?: number | null
}

export type FiltrosDoctores = {
  q?: string
  tipo?: TipoDoctor | null
  activo?: FiltroActivo
  sede?: number | null
}

function query(params: Record<string, string | number | null | undefined>): string {
  const partes = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  return partes.length ? `?${partes.join('&')}` : ''
}

export const listarDoctores = (pagina: number, f: FiltrosDoctores) =>
  api<Paginado<Doctor>>(
    `/doctores/${query({ page: pagina, q: f.q, tipo: f.tipo, activo: f.activo ?? 'todos', sede: f.sede })}`,
  )

export type DatosDoctor = {
  tipo: TipoDoctor
  nombres: string
  apellidos: string
  especialidad?: number | null
  numero_colegiado?: string
  telefono?: string
  activo?: boolean
  sedes: number[]
  observaciones?: string
}

export const crearDoctor = (datos: DatosDoctor) =>
  api<Doctor>('/doctores/', { method: 'POST', json: datos })

export const actualizarDoctor = (id: number, datos: Partial<DatosDoctor>) =>
  api<Doctor>(`/doctores/${id}/`, { method: 'PATCH', json: datos })

// ---------- Tipos de trabajo ----------

export type TipoTrabajo = {
  id: number
  nombre: string
  descripcion: string
  /** Llega como texto decimal desde la API, por ejemplo "850.50". */
  precio: string
  activo: boolean
}

export const listarTiposTrabajo = (activo: FiltroActivo = 'todos') =>
  api<Paginado<TipoTrabajo>>(`/tipos-trabajo/${query({ activo })}`)

export type DatosTipoTrabajo = {
  nombre: string
  descripcion?: string
  precio?: number
  activo?: boolean
}

export const crearTipoTrabajo = (datos: DatosTipoTrabajo) =>
  api<TipoTrabajo>('/tipos-trabajo/', { method: 'POST', json: datos })

export const actualizarTipoTrabajo = (id: number, datos: Partial<DatosTipoTrabajo>) =>
  api<TipoTrabajo>(`/tipos-trabajo/${id}/`, { method: 'PATCH', json: datos })
