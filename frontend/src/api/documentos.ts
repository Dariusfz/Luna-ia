import { api } from './cliente'
import type { Paginado } from './recursos'

export type TipoDocumento = 'radiografia' | 'foto' | 'consentimiento' | 'estudio' | 'otro'

export interface Documento {
  id: number
  paciente: number
  paciente_nombre: string
  sede: number
  sede_nombre: string
  tipo: TipoDocumento
  tipo_nombre: string
  titulo: string
  descripcion: string
  atencion: number | null
  atencion_resumen: string | null
  historia: number | null
  historia_resumen: string | null
  archivo_url: string
  nombre_archivo: string
  tamano_bytes: number | null
  es_imagen: boolean
  subido_por_nombre: string
  creado: string
}

export interface FiltrosDocumentos {
  q?: string
  paciente?: number | null
  atencion?: number | null
  historia?: number | null
  tipo?: TipoDocumento | null
  sede?: number | null
}

export type DatosDocumento = {
  paciente: number
  sede: number
  atencion?: number | null
  historia?: number | null
  tipo: TipoDocumento
  titulo: string
  descripcion?: string
  archivo: File
}

export const listarDocumentos = (pagina: number, filtros: FiltrosDocumentos) => {
  const params = new URLSearchParams()
  params.set('page', String(pagina))
  if (filtros.q) params.set('q', filtros.q)
  if (filtros.paciente) params.set('paciente', String(filtros.paciente))
  if (filtros.atencion) params.set('atencion', String(filtros.atencion))
  if (filtros.historia) params.set('historia', String(filtros.historia))
  if (filtros.tipo) params.set('tipo', filtros.tipo)
  if (filtros.sede) params.set('sede', String(filtros.sede))
  return api<Paginado<Documento>>(`/documentos/?${params.toString()}`)
}

export const subirDocumento = (datos: DatosDocumento) => {
  const formulario = new FormData()
  formulario.append('paciente', String(datos.paciente))
  formulario.append('sede', String(datos.sede))
  formulario.append('tipo', datos.tipo)
  formulario.append('titulo', datos.titulo)
  if (datos.descripcion) formulario.append('descripcion', datos.descripcion)
  if (datos.atencion) formulario.append('atencion', String(datos.atencion))
  if (datos.historia) formulario.append('historia', String(datos.historia))
  formulario.append('archivo', datos.archivo)
  return api<Documento>('/documentos/', { method: 'POST', form: formulario })
}

export const eliminarDocumento = (id: number) =>
  api<void>(`/documentos/${id}/`, { method: 'DELETE' })

/** URL del archivo servido por la API (requiere sesión). `descargar` fuerza la descarga. */
export const urlDocumento = (documento: Documento, descargar = false) =>
  `${documento.archivo_url}${descargar ? '?descargar=1' : ''}`

export const TIPOS_DOCUMENTO: { value: TipoDocumento; label: string; color: string }[] = [
  { value: 'radiografia', label: 'Radiografía', color: 'geekblue' },
  { value: 'foto', label: 'Foto clínica', color: 'magenta' },
  { value: 'consentimiento', label: 'Consentimiento', color: 'gold' },
  { value: 'estudio', label: 'Estudio', color: 'cyan' },
  { value: 'otro', label: 'Otro', color: 'default' },
]
