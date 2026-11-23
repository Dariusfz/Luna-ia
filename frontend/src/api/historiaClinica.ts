import { api } from './cliente'
import type { Paginado } from './recursos'

export type CaraDental = '' | 'oclusal' | 'mesial' | 'distal' | 'vestibular' | 'lingual'

export type EstadoDental =
  | 'sano'
  | 'caries'
  | 'obturado'
  | 'corona'
  | 'endodoncia'
  | 'ausente'
  | 'extraccion_indicada'
  | 'implante'
  | 'sellante'
  | 'fractura'
  | 'protesis'

export type HallazgoDental = {
  id: number
  diente: number
  cara: CaraDental
  cara_nombre: string
  estado: EstadoDental
  estado_nombre: string
  observacion: string
}

export type Odontograma = {
  id: number
  paciente: number
  paciente_nombre: string
  historia: number | null
  sede: number
  sede_nombre: string
  doctor: number | null
  doctor_nombre: string | null
  fecha: string
  notas: string
  hallazgos: HallazgoDental[]
  creado: string
  actualizado: string
}

export type HistoriaClinica = {
  id: number
  paciente: number
  paciente_nombre: string
  atencion: number | null
  sede: number
  sede_nombre: string
  doctor: number
  doctor_nombre: string
  fecha: string
  motivo_consulta: string
  enfermedad_actual: string
  examen_clinico: string
  diagnostico: string
  plan_tratamiento: string
  notas: string
  odontograma: Odontograma | null
  creado: string
  actualizado: string
}

function query(params: Record<string, string | number | null | undefined>): string {
  const partes = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  return partes.length ? `?${partes.join('&')}` : ''
}

export const listarHistorias = (paciente: number) =>
  api<Paginado<HistoriaClinica>>(`/historias-clinicas/${query({ paciente })}`)

export type DatosHistoria = {
  paciente: number
  sede: number
  doctor: number
  fecha: string
  motivo_consulta?: string
  enfermedad_actual?: string
  examen_clinico?: string
  diagnostico?: string
  plan_tratamiento?: string
  notas?: string
}

export const crearHistoria = (datos: DatosHistoria) =>
  api<HistoriaClinica>('/historias-clinicas/', { method: 'POST', json: datos })

export const actualizarHistoria = (id: number, datos: Partial<DatosHistoria>) =>
  api<HistoriaClinica>(`/historias-clinicas/${id}/`, { method: 'PATCH', json: datos })

export const listarOdontogramas = (paciente: number) =>
  api<Paginado<Odontograma>>(`/odontogramas/${query({ paciente })}`)

export type DatosHallazgo = {
  diente: number
  cara?: CaraDental
  estado: EstadoDental
  observacion?: string
}

export type DatosOdontograma = {
  paciente: number
  sede: number
  doctor?: number | null
  fecha: string
  notas?: string
  hallazgos?: DatosHallazgo[]
}

export const crearOdontograma = (datos: DatosOdontograma) =>
  api<Odontograma>('/odontogramas/', { method: 'POST', json: datos })

export const actualizarOdontograma = (id: number, datos: Partial<DatosOdontograma>) =>
  api<Odontograma>(`/odontogramas/${id}/`, { method: 'PATCH', json: datos })

export type CambioHistorial = {
  campo: string
  antes: unknown
  despues: unknown
}

export type RegistroHistorial = {
  id: number
  fecha: string
  tipo: '+' | '~' | '-'
  tipo_nombre: string
  usuario: string | null
  usuario_nombre: string
  motivo: string
  cambios: CambioHistorial[]
}

export const historialHistoria = (id: number) =>
  api<RegistroHistorial[]>(`/historias-clinicas/${id}/historial/`)

export const historialOdontograma = (id: number) =>
  api<RegistroHistorial[]>(`/odontogramas/${id}/historial/`)
