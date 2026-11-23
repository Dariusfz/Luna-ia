import { api } from './cliente'

export interface PuntoGrafica {
  etiqueta: string
  valor: number
}

/** Formato común de las consultas de /api/analitica/ (ver backend/analitica/views.py). */
export interface GraficaAnalitica {
  titulo: string
  tipo_grafica: 'barras' | 'linea'
  ejes: { x: string; y: string }
  datos: PuntoGrafica[]
  total: number
  filtros: { desde: string; hasta: string; sede: number | null }
}

function queryString(params: Record<string, string | number | null | undefined>): string {
  const partes = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  return partes.length ? `?${partes.join('&')}` : ''
}

export const obtenerCitasHoy = (sede: number | null) =>
  api<GraficaAnalitica>(
    `/analitica/citas-hoy/${queryString({ sede })}`,
  )

export const obtenerAtendidosMes = (desde: string, hasta: string, sede: number | null) =>
  api<GraficaAnalitica>(
    `/analitica/atendidos-mes/${queryString({ desde, hasta, sede })}`,
  )

export const obtenerPorServicio = (desde: string, hasta: string, sede: number | null) =>
  api<GraficaAnalitica>(
    `/analitica/por-servicio/${queryString({ desde, hasta, sede })}`,
  )

export const obtenerPorHora = (desde: string, hasta: string, sede: number | null) =>
  api<GraficaAnalitica>(
    `/analitica/por-hora/${queryString({ desde, hasta, sede })}`,
  )

export const obtenerPorSede = (desde: string, hasta: string) =>
  api<GraficaAnalitica>(`/analitica/por-sede/${queryString({ desde, hasta })}`)

export const obtenerIngresos = (desde: string, hasta: string, sede: number | null) =>
  api<GraficaAnalitica>(
    `/analitica/ingresos/${queryString({ desde, hasta, sede })}`,
  )
