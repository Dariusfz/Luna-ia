import { MailOutlined } from '@ant-design/icons'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { solicitarRecuperacion } from '../api/auth'
import { ApiError } from '../api/cliente'

/** Siempre muestra el mismo mensaje, exista o no la cuenta (no revela usuarios). */
export default function RecuperarContrasena() {
  const [cargando, setCargando] = useState(false)
  const [enviado, setEnviado] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function enviar(valores: { email: string }) {
    setCargando(true)
    setError(null)
    try {
      await solicitarRecuperacion(valores.email.trim())
      setEnviado(true)
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
          <Typography.Text type="secondary">Recuperar contraseña</Typography.Text>
        </div>

        {enviado ? (
          <>
            <Alert
              type="success"
              showIcon
              style={{ marginTop: 24 }}
              message="Revisa tu correo"
              description="Si el correo está registrado, recibirás un enlace válido por 30 minutos."
            />
            <Link to="/login">
              <Button type="primary" block style={{ marginTop: 24 }}>
                Volver al inicio de sesión
              </Button>
            </Link>
          </>
        ) : (
          <Form layout="vertical" onFinish={enviar} requiredMark={false} style={{ marginTop: 24 }}>
            <Typography.Paragraph type="secondary">
              Escribe el correo de tu cuenta y te enviaremos un enlace para crear una nueva contraseña.
            </Typography.Paragraph>
            {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
            <Form.Item
              name="email"
              label="Correo"
              rules={[{ required: true, message: 'Escribe tu correo' }, { type: 'email', message: 'Correo no válido' }]}
            >
              <Input prefix={<MailOutlined />} autoComplete="email" autoFocus />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={cargando}>
              Enviar enlace
            </Button>
            <Link to="/login">
              <Button type="link" block>
                Volver
              </Button>
            </Link>
          </Form>
        )}
      </Card>
    </div>
  )
}
