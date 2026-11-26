import { api } from './cliente'
import type { Paginado } from './recursos'

export type EstadoConversacion =
  | 'inicio'
  | 'esperando_sede'
  | 'esperando_datos'
  | 'esperando_confirmacion'
  | 'cerrada'

export type RolMensajeAgente = 'paciente' | 'agente' | 'humano' | 'sistema'

export interface ConversacionAgente {
  id: number
  telefono: string
  paciente: number | null
  paciente_nombre: string
  sede: number | null
  sede_nombre: string | null
  estado: EstadoConversacion
  agente_activo: boolean
  creada: string
  ultima_actividad: string
  total_mensajes: number
  ultimo_mensaje: string
  ultimo_rol: RolMensajeAgente | ''
}

export interface MensajeAgente {
  id: number
  rol: RolMensajeAgente
  tipo: 'texto' | 'audio'
  texto: string
  creado: string
}

export interface DetalleConversacionAgente extends ConversacionAgente {
  mensajes: MensajeAgente[]
}

export interface DiaMensajes {
  fecha: string
  total: number
  paciente: number
  agente: number
  humano: number
}

export interface ResumenAgente {
  conversaciones: {
    total: number
    activas: number
    pausadas: number
    nuevas_hoy: number
  }
  mensajes: {
    hoy: number
    paciente_hoy: number
    agente_hoy: number
    humano_hoy: number
  }
  citas: {
    agente_hoy: number
    agente_mes: number
    total_mes: number
    porcentaje_agente: number
  }
  mensajes_por_dia: DiaMensajes[]
}

export type FiltroAgenteActivo = 'todas' | 'activas' | 'pausadas'

export interface FiltrosConversacionesAgente {
  q?: string
  agente_activo?: FiltroAgenteActivo
  estado?: EstadoConversacion | null
  sede?: number | null
}

function queryString(params: Record<string, string | number | null | undefined>): string {
  const partes = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(String(v))}`)
  return partes.length ? `?${partes.join('&')}` : ''
}

export function listarConversacionesAgente(
  pagina: number,
  filtros: FiltrosConversacionesAgente,
): Promise<Paginado<ConversacionAgente>> {
  return api<Paginado<ConversacionAgente>>(
    `/agente/panel/conversaciones/${queryString({
      page: pagina,
      q: filtros.q,
      agente_activo:
        filtros.agente_activo === 'activas'
          ? 'true'
          : filtros.agente_activo === 'pausadas'
            ? 'false'
            : undefined,
      estado: filtros.estado,
      sede: filtros.sede,
    })}`,
  )
}

export const obtenerConversacionAgente = (id: number) =>
  api<DetalleConversacionAgente>(`/agente/panel/conversaciones/${id}/`)

export const eliminarConversacionAgente = (id: number) =>
  api<void>(`/agente/panel/conversaciones/${id}/`, { method: 'DELETE' })

export const actualizarAgenteActivo = (id: number, agenteActivo: boolean) =>
  api<{ id: number; agente_activo: boolean }>(
    `/agente/panel/conversaciones/${id}/actualizar/`,
    { method: 'PATCH', json: { agente_activo: agenteActivo } },
  )

export const obtenerResumenAgente = () =>
  api<ResumenAgente>('/agente/panel/resumen/')
