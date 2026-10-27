import { api } from './cliente'

export type DiaSemana = 0 | 1 | 2 | 3 | 4 | 5 | 6

export const DIAS_SEMANA: { value: DiaSemana; label: string }[] = [
  { value: 0, label: 'Lunes' },
  { value: 1, label: 'Martes' },
  { value: 2, label: 'Miércoles' },
  { value: 3, label: 'Jueves' },
  { value: 4, label: 'Viernes' },
  { value: 5, label: 'Sábado' },
  { value: 6, label: 'Domingo' },
]

export type HorarioSede = {
  id: number
  sede: number
  sede_nombre: string
  dia_semana: DiaSemana
  dia_nombre: string
  hora_apertura: string
  hora_cierre: string
}

export type DatosHorario = {
  sede: number
  dia_semana: DiaSemana
  hora_apertura: string
  hora_cierre: string
}

function queryString(params: Record<string, string | number | null | undefined>): string {
  const partes = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  return partes.length ? `?${partes.join('&')}` : ''
}

export const listarHorarios = (sede?: number | null) =>
  api<HorarioSede[]>(`/horarios-sede/${queryString({ sede })}`)

export const crearHorario = (datos: DatosHorario) =>
  api<HorarioSede>('/horarios-sede/', { method: 'POST', json: datos })

export const editarHorario = (id: number, datos: DatosHorario) =>
  api<HorarioSede>(`/horarios-sede/${id}/`, { method: 'PATCH', json: datos })

export const eliminarHorario = (id: number) =>
  api<void>(`/horarios-sede/${id}/`, { method: 'DELETE' })

export type Feriado = {
  id: number
  sede: number | null
  sede_nombre: string
  fecha: string
  nombre: string
  todo_el_dia: boolean
  hora_inicio: string | null
  hora_fin: string | null
}

export type DatosFeriado = {
  sede: number | null
  fecha: string
  nombre: string
  todo_el_dia: boolean
  hora_inicio?: string | null
  hora_fin?: string | null
}

export const listarFeriados = (sede?: number | null) =>
  api<Feriado[]>(`/feriados/${queryString({ sede })}`)

export const crearFeriado = (datos: DatosFeriado) =>
  api<Feriado>('/feriados/', { method: 'POST', json: datos })

export const editarFeriado = (id: number, datos: DatosFeriado) =>
  api<Feriado>(`/feriados/${id}/`, { method: 'PATCH', json: datos })

export const eliminarFeriado = (id: number) =>
  api<void>(`/feriados/${id}/`, { method: 'DELETE' })
