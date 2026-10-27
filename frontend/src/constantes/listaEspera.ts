export const ESTADOS_ESPERA = ['esperando', 'contactado', 'agendado', 'cancelado'] as const

export type EstadoEspera = (typeof ESTADOS_ESPERA)[number]

export const ETIQUETA_ESPERA: Record<EstadoEspera, string> = {
  esperando: 'En espera',
  contactado: 'Contactado',
  agendado: 'Agendado',
  cancelado: 'Cancelado',
}

export const COLOR_ESPERA: Record<EstadoEspera, string> = {
  esperando: 'gold',
  contactado: 'blue',
  agendado: 'green',
  cancelado: 'red',
}

export const PRIORIDADES_ESPERA = [1, 2, 3] as const

export type PrioridadEspera = (typeof PRIORIDADES_ESPERA)[number]

export const ETIQUETA_PRIORIDAD: Record<PrioridadEspera, string> = {
  1: 'Baja',
  2: 'Normal',
  3: 'Alta',
}

export const COLOR_PRIORIDAD: Record<PrioridadEspera, string> = {
  1: 'default',
  2: 'blue',
  3: 'red',
}
