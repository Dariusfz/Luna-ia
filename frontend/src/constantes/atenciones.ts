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
