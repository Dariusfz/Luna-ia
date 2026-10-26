import { api } from './cliente'
import type { Usuario } from './auth'

export type DatosAceptarInvitacion = {
  token: string
  username: string
  nombres: string
  apellidos: string
  password: string
}

/** Crea la cuenta a partir del enlace recibido por correo. Después se inicia sesión y se configura el 2FA. */
export const aceptarInvitacion = (datos: DatosAceptarInvitacion) =>
  api<Usuario>('/auth/aceptar-invitacion/', { method: 'POST', json: datos })
