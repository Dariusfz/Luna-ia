export const ESTADOS_ATENCION = ['pendiente', 'confirmada', 'completada', 'cancelada'] as const

export type EstadoAtencion = (typeof ESTADOS_ATENCION)[number]

export const ETIQUETA_ESTADO: Record<EstadoAtencion, string> = {
  pendiente: 'Pendiente',
  confirmada: 'Confirmada',
  completada: 'Completada',
  cancelada: 'Cancelada',
}

export const COLOR_ESTADO: Record<EstadoAtencion, string> = {
  pendiente: 'gold',
  confirmada: 'blue',
  completada: 'green',
  cancelada: 'red',
}

export const ORIGENES_ATENCION = [
  'panel',
  'agente_whatsapp',
  'asistente_ia',
  'sistema',
] as const

export type OrigenAtencion = (typeof ORIGENES_ATENCION)[number]

export const ETIQUETA_ORIGEN: Record<OrigenAtencion, string> = {
  panel: 'Personal',
  agente_whatsapp: 'Agente WhatsApp',
  asistente_ia: 'Asistente IA',
  sistema: 'Sistema',
}

export const COLOR_ORIGEN: Record<OrigenAtencion, string> = {
  panel: 'default',
  agente_whatsapp: 'green',
  asistente_ia: 'purple',
  sistema: 'blue',
}
