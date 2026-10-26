import { LockOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'

import { confirmarRecuperacion } from '../api/auth'
import { ApiError } from '../api/cliente'

export default function ConfirmarRecuperacion() {
  const [params] = useSearchParams()
  const navigate = useNavigate()
  const token = params.get('token') ?? ''

  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [listo, setListo] = useState(false)

  async function guardar(valores: { password: string; confirmar: string }) {
    setCargando(true)
    setError(null)
    try {
      await confirmarRecuperacion(token, valores.password)
      setListo(true)
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
          <Typography.Text type="secondary">Nueva contraseña</Typography.Text>
        </div>

        {!token && (
          <Alert type="error" showIcon style={{ marginTop: 24 }} message="El enlace no es válido." />
        )}

        {token && listo && (
          <>
            <Alert
              type="success"
              showIcon
              style={{ marginTop: 24 }}
              message="Contraseña actualizada"
              description="Inicia sesión con tu nueva contraseña. Después te pediremos el código de tu app."
            />
            <Button type="primary" block style={{ marginTop: 24 }} onClick={() => navigate('/login')}>
              Ir al inicio de sesión
            </Button>
          </>
        )}

        {token && !listo && (
          <Form layout="vertical" onFinish={guardar} requiredMark={false} style={{ marginTop: 24 }}>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
            <Form.Item name="password" label="Nueva contraseña" rules={[{ required: true, message: 'Escribe la nueva contraseña' }]}>
              <Input.Password prefix={<LockOutlined />} autoComplete="new-password" autoFocus />
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
              Guardar contraseña
            </Button>
            <Link to="/login">
              <Button type="link" block>
                Cancelar
              </Button>
            </Link>
          </Form>
        )}
      </Card>
    </div>
  )
}
