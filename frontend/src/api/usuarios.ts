import { api } from './cliente'
import type { Paginado, FiltroActivo } from './recursos'

export type Rol = 'admin' | 'doctor' | 'recepcionista' | 'asistente'

export type UsuarioAdmin = {
  id: number
  username: string
  email: string
  nombres: string
  apellidos: string
  rol: Rol
  is_active: boolean
  tiene_2fa: boolean
  sedes: { id: number; nombre: string }[]
}

export type FiltrosPersonal = {
  q?: string
  rol?: Rol | null
  activo?: FiltroActivo
}

export const listarUsuarios = (filtros: FiltrosPersonal) => {
  const params = new URLSearchParams()
  if (filtros.q) params.set('q', filtros.q)
  if (filtros.rol) params.set('rol', filtros.rol)
  params.set('activo', filtros.activo ?? 'todos')
  return api<Paginado<UsuarioAdmin>>(`/usuarios/?${params.toString()}`)
}

export type DatosEditarUsuario = {
  rol?: Rol
  sedes?: number[]
  is_active?: boolean
}

export const editarUsuario = (id: number, datos: DatosEditarUsuario) =>
  api<UsuarioAdmin>(`/usuarios/${id}/`, { method: 'PATCH', json: datos })

export type DatosInvitacion = {
  email: string
  rol: Rol
  sedes: number[]
}

/** El personal se da de alta por invitación: el enlace llega por correo. */
export const invitarPersonal = (datos: DatosInvitacion) =>
  api<{ id: number; email: string }>('/invitaciones/', { method: 'POST', json: datos })

export const restablecer2FA = (id: number) =>
  api<{ detail: string }>(`/usuarios/${id}/restablecer-2fa/`, { method: 'POST' })
