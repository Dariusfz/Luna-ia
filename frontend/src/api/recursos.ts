import { api } from './cliente'

export type Paginado<T> = {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

export type Paciente = {
  id: number
  nombres: string
  apellidos: string
  identidad: string
  fecha_nacimiento: string | null
  sexo: '' | 'F' | 'M' | 'O'
  telefono: string
  email: string
  direccion: string
  sede_origen: number | null
  alergias: string
  antecedentes_medicos: string
  medicamentos_actuales: string
  observaciones: string
  activo: boolean
  creado: string
}

export type Sede = {
  id: number
  nombre: string
  direccion: string
  telefono: string
  activa: boolean
}

export type FiltroActivo = 'true' | 'false' | 'todos'
export type FiltroSedeActiva = 'true' | 'false' | 'todas'

export type FiltrosPacientes = {
  q?: string
  sede?: number | null
  activo?: FiltroActivo
}

/** Convierte un objeto de filtros en query string, omitiendo los vacíos. */
function queryString(params: Record<string, string | number | null | undefined>): string {
  const partes = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  return partes.length ? `?${partes.join('&')}` : ''
}

export const listarPacientes = (pagina: number, filtros: FiltrosPacientes) =>
  api<Paginado<Paciente>>(
    `/pacientes/${queryString({
      page: pagina,
      q: filtros.q,
      sede: filtros.sede,
      activo: filtros.activo ?? 'true',
    })}`,
  )

export type DatosPaciente = {
  nombres: string
  apellidos: string
  identidad?: string
  fecha_nacimiento?: string | null
  sexo?: '' | 'F' | 'M' | 'O' | null
  telefono?: string
  email?: string
  direccion?: string
  sede_origen: number | null
  alergias?: string
  antecedentes_medicos?: string
  medicamentos_actuales?: string
  observaciones?: string
  activo?: boolean
}

export const crearPaciente = (datos: DatosPaciente) =>
  api<Paciente>('/pacientes/', { method: 'POST', json: datos })

export const obtenerPaciente = (id: number) => api<Paciente>(`/pacientes/${id}/`)

export const actualizarPaciente = (id: number, datos: Partial<DatosPaciente>) =>
  api<Paciente>(`/pacientes/${id}/`, { method: 'PATCH', json: datos })

export const listarSedes = (activa: FiltroSedeActiva = 'todas') =>
  api<Paginado<Sede>>(`/sedes/${queryString({ activa })}`)

export type DatosSede = {
  nombre: string
  direccion?: string
  telefono?: string
  activa?: boolean
}

export const crearSede = (datos: DatosSede) => api<Sede>('/sedes/', { method: 'POST', json: datos })

export const editarSede = (id: number, datos: DatosSede) =>
  api<Sede>(`/sedes/${id}/`, { method: 'PATCH', json: datos })
