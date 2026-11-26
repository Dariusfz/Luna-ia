import type { EstadoAtencion, OrigenAtencion } from '../constantes/atenciones'
import type { TipoDoctor } from './catalogos'
import { api } from './cliente'
import type { Paginado } from './recursos'

export type AtencionTrabajo = {
  id: number
  tipo_trabajo: number
  tipo_trabajo_nombre: string
  /** Precio del tipo de trabajo al momento de la cita. */
  precio: string
}

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
  trabajos: AtencionTrabajo[]
  estado: EstadoAtencion
  origen: OrigenAtencion
  origen_nombre: string
  creado_por: number | null
  creado_por_nombre: string | null
  fecha: string
  hora_inicio: string
  hora_fin: string
  procedimiento: string
  /** Total calculado con los precios de los tipos de trabajo, como texto decimal. */
  precio_paciente: string
  /** Llega como texto decimal, por ejemplo "300.00". */
  honorario_doctor: string
  total_pagado: string
  saldo_pendiente: string
  total_pagado_doctor: string
  saldo_doctor: string
  observaciones: string
}

export type FiltrosAtenciones = {
  sede?: number | null
  doctor?: number | null
  paciente?: number | null
  estado?: EstadoAtencion | EstadoAtencion[] | null
  origen?: OrigenAtencion | null
  desde?: string
  hasta?: string
  q?: string
}

export const listarAtenciones = (pagina: number, f: FiltrosAtenciones) => {
  const params = new URLSearchParams({ page: String(pagina) })
  if (f.sede) params.set('sede', String(f.sede))
  if (f.doctor) params.set('doctor', String(f.doctor))
  if (f.paciente) params.set('paciente', String(f.paciente))
  if (f.estado) {
    const estados = Array.isArray(f.estado) ? f.estado.join(',') : f.estado
    params.set('estado', estados)
  }
  if (f.origen) params.set('origen', f.origen)
  if (f.desde) params.set('desde', f.desde)
  if (f.hasta) params.set('hasta', f.hasta)
  if (f.q) params.set('q', f.q)
  return api<Paginado<Atencion>>(`/atenciones/?${params.toString()}`)
}

export type DatosAtencion = {
  sede: number
  doctor: number
  paciente: number
  tipo_trabajo: number
  tipos_trabajo?: number[]
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

export type IntervaloOcupado = {
  atencion: number
  hora_inicio: string
  hora_fin: string
  paciente: string
  estado: EstadoAtencion
}

export type IntervaloHorario = {
  hora_inicio: string
  hora_fin: string
}

export type FeriadoDia = {
  nombre: string
  todo_el_dia: boolean
  hora_inicio: string | null
  hora_fin: string | null
}

export type DisponibilidadDoctor = {
  doctor: number
  doctor_nombre: string
  ocupados: IntervaloOcupado[]
  /** Horas de inicio libres según la duración consultada. */
  huecos?: string[]
  /** Solo llega cuando se consulta un rango hora_inicio/hora_fin. */
  disponible?: boolean
}

export type Disponibilidad = {
  sede: { id: number; nombre: string }
  fecha: string
  duracion: number
  horario_configurado: boolean
  abierta: boolean
  motivo: string | null
  horarios: IntervaloHorario[]
  abiertos: IntervaloHorario[]
  feriados: FeriadoDia[]
  doctores: DisponibilidadDoctor[]
  consulta?: { hora_inicio: string; hora_fin: string }
}

export type FiltrosDisponibilidad = {
  sede: number
  fecha: string
  doctor?: number | null
  hora_inicio?: string
  hora_fin?: string
  duracion?: number
}

export const consultarDisponibilidad = (f: FiltrosDisponibilidad) => {
  const params = new URLSearchParams({ sede: String(f.sede), fecha: f.fecha })
  if (f.doctor) params.set('doctor', String(f.doctor))
  if (f.hora_inicio) params.set('hora_inicio', f.hora_inicio)
  if (f.hora_fin) params.set('hora_fin', f.hora_fin)
  if (f.duracion) params.set('duracion', String(f.duracion))
  return api<Disponibilidad>(`/atenciones/disponibilidad/?${params.toString()}`)
}

export type CambioHistorial = {
  campo: string
  antes: string | number | null
  despues: string | number | null
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

export const listarHistorialAtencion = (id: number) =>
  api<RegistroHistorial[]>(`/atenciones/${id}/historial/`)
