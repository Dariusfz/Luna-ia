import { api } from './cliente'
import type { Paginado } from './recursos'

export const METODOS_PAGO = ['efectivo', 'transferencia', 'tarjeta', 'otro'] as const

export type MetodoPago = (typeof METODOS_PAGO)[number]

export const ETIQUETA_METODO: Record<MetodoPago, string> = {
  efectivo: 'Efectivo',
  transferencia: 'Transferencia',
  tarjeta: 'Tarjeta',
  otro: 'Otro',
}

function query(params: Record<string, string | number | null | undefined>): string {
  const partes = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  return partes.length ? `?${partes.join('&')}` : ''
}

export type Pago = {
  id: number
  atencion: number
  atencion_etiqueta: string
  paciente_nombre: string
  sede_nombre: string
  tipo_trabajo_nombre: string
  doctor_nombre: string
  fecha_atencion: string
  hora_inicio: string
  monto: string
  metodo: MetodoPago
  metodo_nombre: string
  fecha: string
  nota: string
  registrado_por: number | null
  registrado_por_nombre: string | null
  precio_paciente: string
  total_pagado: string
  saldo_pendiente: string
  creado: string
}

export type FiltrosPagos = {
  atencion?: number | null
  sede?: number | null
  desde?: string
  hasta?: string
  metodo?: MetodoPago | null
}

export type DatosPago = {
  atencion: number
  monto: number
  metodo: MetodoPago
  fecha: string
  nota?: string
}

export const listarPagos = (pagina: number, f: FiltrosPagos) =>
  api<Paginado<Pago>>(
    `/pagos/${query({
      page: pagina,
      atencion: f.atencion,
      sede: f.sede,
      desde: f.desde,
      hasta: f.hasta,
      metodo: f.metodo,
    })}`,
  )

export const crearPago = (datos: DatosPago) =>
  api<Pago>('/pagos/', { method: 'POST', json: datos })

export type PagoDoctor = {
  id: number
  atencion: number
  atencion_etiqueta: string
  paciente_nombre: string
  sede_nombre: string
  tipo_trabajo_nombre: string
  doctor: number
  doctor_nombre: string
  doctor_tipo: 'propio' | 'contratado'
  fecha_atencion: string
  hora_inicio: string
  monto: string
  metodo: MetodoPago
  metodo_nombre: string
  fecha: string
  nota: string
  registrado_por: number | null
  registrado_por_nombre: string | null
  honorario_doctor: string
  total_pagado: string
  saldo_pendiente: string
  creado: string
}

export type FiltrosPagosDoctor = FiltrosPagos & {
  doctor?: number | null
}

export type DatosPagoDoctor = {
  atencion: number
  monto: number
  metodo: MetodoPago
  fecha: string
  nota?: string
}

export const listarPagosDoctores = (pagina: number, f: FiltrosPagosDoctor) =>
  api<Paginado<PagoDoctor>>(
    `/pagos-doctores/${query({
      page: pagina,
      atencion: f.atencion,
      doctor: f.doctor,
      sede: f.sede,
      desde: f.desde,
      hasta: f.hasta,
      metodo: f.metodo,
    })}`,
  )

export const crearPagoDoctor = (datos: DatosPagoDoctor) =>
  api<PagoDoctor>('/pagos-doctores/', { method: 'POST', json: datos })

export type DiaCaja = {
  fecha: string
  cobrado: string
  por_cobrar: string
  comision_doctores: string
  ganancia: string
}

export type ResumenCaja = {
  desde: string
  hasta: string
  sede: number | null
  cobrado: string
  por_cobrar: string
  comision_doctores: string
  ganancia: string
  abonos_caja: string
  pagado_doctores: string
  cantidad_cobros: number
  cantidad_abonos: number
  cantidad_pagos_doctores: number
  por_dia: DiaCaja[]
}

export type FiltrosCaja = {
  desde: string
  hasta: string
  sede?: number | null
}

export const obtenerResumenCaja = (f: FiltrosCaja) =>
  api<ResumenCaja>(
    `/caja/resumen/${query({ desde: f.desde, hasta: f.hasta, sede: f.sede })}`,
  )
