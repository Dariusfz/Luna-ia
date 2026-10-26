import { useQuery } from '@tanstack/react-query'
import { Spin } from 'antd'
import { Navigate, Outlet } from 'react-router-dom'

import { obtenerUsuarioActual } from '../api/auth'

/** Deja pasar solo a usuarios con sesión activa (ya verificada con 2FA si aplica). */
export default function RequiereSesion() {
  const { data, isPending, isError } = useQuery({
    queryKey: ['me'],
    queryFn: obtenerUsuarioActual,
  })

  if (isPending) {
    return <Spin fullscreen />
  }
  if (isError || !data) {
    return <Navigate to="/login" replace />
  }
  return <Outlet />
}
