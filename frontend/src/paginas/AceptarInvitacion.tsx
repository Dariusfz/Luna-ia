import { LockOutlined, UserOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'

import { ApiError } from '../api/cliente'
import { aceptarInvitacion, type DatosAceptarInvitacion } from '../api/invitacion'

/** Crear el perfil desde el enlace de invitación recibido por correo. */
export default function AceptarInvitacion() {
  const [params] = useSearchParams()
  const token = params.get('token') ?? ''

  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [creado, setCreado] = useState(false)

  async function crear(valores: Omit<DatosAceptarInvitacion, 'token'> & { confirmar: string }) {
    setCargando(true)
    setError(null)
    try {
      const { confirmar: _confirmar, ...resto } = valores
      await aceptarInvitacion({ ...resto, token })
      setCreado(true)
    } catch (e) {
      setError(e instanceof ApiError ? e.message : 'No se pudo conectar con el servidor.')
    } finally {
      setCargando(false)
    }
  }

  return (
    <div className="login-fondo">
      <Card className="login-tarjeta" variant="borderless">
        <div className="marca-login">
          <Typography.Title level={3} style={{ margin: 0, color: '#238781' }}>
            LUNA IA
          </Typography.Title>
          <Typography.Text type="secondary">Crear mi cuenta</Typography.Text>
        </div>

        {!token && (
          <Alert type="error" showIcon style={{ marginTop: 24 }} message="El enlace no es válido." />
        )}

        {token && creado && (
          <>
            <Alert
              type="success"
              showIcon
              style={{ marginTop: 24 }}
              message="Cuenta creada"
              description="Ahora inicia sesión. Después te pediremos configurar la verificación en dos pasos."
            />
            <Link to="/login">
              <Button type="primary" block style={{ marginTop: 24 }}>
                Ir al inicio de sesión
              </Button>
            </Link>
          </>
        )}

        {token && !creado && (
          <Form layout="vertical" onFinish={crear} requiredMark={false} style={{ marginTop: 24 }}>
            <Typography.Paragraph type="secondary">
              Completa tus datos. Tu correo ya quedó registrado con la invitación.
            </Typography.Paragraph>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
            <Form.Item name="nombres" label="Nombres" rules={[{ required: true, message: 'Escribe tus nombres' }]}>
              <Input autoFocus />
            </Form.Item>
            <Form.Item name="apellidos" label="Apellidos" rules={[{ required: true, message: 'Escribe tus apellidos' }]}>
              <Input />
            </Form.Item>
            <Form.Item
              name="username"
              label="Nombre de usuario"
              rules={[{ required: true, message: 'Elige un nombre de usuario' }]}
            >
              <Input prefix={<UserOutlined />} autoComplete="username" />
            </Form.Item>
            <Form.Item name="password" label="Contraseña" rules={[{ required: true, message: 'Crea una contraseña' }]}>
              <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
            </Form.Item>
            <Form.Item
              name="confirmar"
              label="Repite la contraseña"
              dependencies={['password']}
              rules={[
                { required: true, message: 'Repite la contraseña' },
                ({ getFieldValue }) => ({
                  validator(_, valor) {
                    if (!valor || getFieldValue('password') === valor) return Promise.resolve()
                    return Promise.reject(new Error('Las contraseñas no coinciden'))
                  },
                }),
              ]}
            >
              <Input.Password prefix={<LockOutlined />} autoComplete="new-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={cargando}>
              Crear cuenta
            </Button>
          </Form>
        )}
      </Card>
    </div>
  )
}
