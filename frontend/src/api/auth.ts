import { api } from './cliente'

export type Usuario = {
  id: number
  username: string
  email: string
  nombres: string
  apellidos: string
  rol: 'admin' | 'doctor' | 'recepcionista' | 'asistente'
  sedes: { id: number; nombre: string }[]
  es_admin: boolean
}

export type PasoLogin = 'completo' | 'verificar_2fa' | 'configurar_2fa'

export type RespuestaLogin = {
  paso: PasoLogin
  usuario?: Usuario
}

export type RespuestaConfigurar = {
  secreto: string
  uri: string
}

export type RespuestaConfirmar = {
  paso: 'completo'
  usuario: Usuario
  codigos_recuperacion: string[]
}

export const cargarCsrf = () => api<{ detail: string }>('/auth/csrf/')

export const iniciarSesion = (username: string, password: string) =>
  api<RespuestaLogin>('/auth/login/', { method: 'POST', json: { username, password } })

export const verificarSegundoFactor = (codigo: string) =>
  api<RespuestaLogin>('/auth/2fa/verificar/', { method: 'POST', json: { codigo } })

export const configurar2FA = () =>
  api<RespuestaConfigurar>('/auth/2fa/configurar/', { method: 'POST' })

export const confirmar2FA = (codigo: string) =>
  api<RespuestaConfirmar>('/auth/2fa/confirmar/', { method: 'POST', json: { codigo } })

export const cerrarSesion = () => api<void>('/auth/logout/', { method: 'POST' })

export const obtenerUsuarioActual = () => api<Usuario>('/auth/me/')

export const solicitarRecuperacion = (email: string) =>
  api<{ detail: string }>('/auth/recuperar/', { method: 'POST', json: { email } })

export const confirmarRecuperacion = (token: string, password: string) =>
  api<{ detail: string }>('/auth/recuperar/confirmar/', { method: 'POST', json: { token, password } })
