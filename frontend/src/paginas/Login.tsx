import { LockOutlined, MailOutlined, SafetyOutlined } from '@ant-design/icons'
import { useQueryClient } from '@tanstack/react-query'
import { Alert, Button, Card, Form, Input, Typography } from 'antd'
import { QRCodeSVG } from 'qrcode.react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import {
  cargarCsrf,
  confirmar2FA,
  configurar2FA,
  iniciarSesion,
  verificarSegundoFactor,
  type RespuestaConfigurar,
  type Usuario,
} from '../api/auth'
import { ApiError } from '../api/cliente'

type Paso = 'credenciales' | 'verificar' | 'configurar' | 'codigos'

function mensaje(error: unknown): string {
  return error instanceof ApiError ? error.message : 'No se pudo conectar con el servidor.'
}

export default function Login() {
  const navigate = useNavigate()
  const cliente = useQueryClient()

  const [paso, setPaso] = useState<Paso>('credenciales')
  const [cargando, setCargando] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [configuracion, setConfiguracion] = useState<RespuestaConfigurar | null>(null)
  const [codigos, setCodigos] = useState<string[]>([])

  // Obtiene la cookie CSRF antes del primer POST.
  useEffect(() => {
    cargarCsrf().catch(() => undefined)
  }, [])

  function entrar(usuario: Usuario) {
    cliente.setQueryData(['me'], usuario)
    navigate('/', { replace: true })
  }

  async function ejecutar(accion: () => Promise<void>) {
    setCargando(true)
    setError(null)
    try {
      await accion()
    } catch (e) {
      setError(mensaje(e))
      if (e instanceof ApiError && e.message.includes('No hay un inicio de sesión pendiente')) {
        setPaso('credenciales')
      }
    } finally {
      setCargando(false)
    }
  }

  const onCredenciales = (valores: { username: string; password: string }) =>
    ejecutar(async () => {
      const respuesta = await iniciarSesion(valores.username, valores.password)
      if (respuesta.paso === 'completo' && respuesta.usuario) {
        entrar(respuesta.usuario)
      } else if (respuesta.paso === 'verificar_2fa') {
        setPaso('verificar')
      } else {
        setConfiguracion(await configurar2FA())
        setPaso('configurar')
      }
    })

  const onVerificar = (valores: { codigo: string }) =>
    ejecutar(async () => {
      const respuesta = await verificarSegundoFactor(valores.codigo.trim())
      if (respuesta.usuario) entrar(respuesta.usuario)
    })

  const onConfirmar = (valores: { codigo: string }) =>
    ejecutar(async () => {
      const respuesta = await confirmar2FA(valores.codigo.trim())
      cliente.setQueryData(['me'], respuesta.usuario)
      setCodigos(respuesta.codigos_recuperacion)
      setPaso('codigos')
    })

  const titulo = {
    credenciales: 'Iniciar sesión',
    verificar: 'Verificación en dos pasos',
    configurar: 'Configura la verificación en dos pasos',
    codigos: 'Guarda tus códigos de recuperación',
  }[paso]

  return (
    <div className="login-fondo">
      <Card className="login-tarjeta" variant="borderless">
        <div className="marca-login">
          <Typography.Title level={3} style={{ margin: 0, color: '#238781' }}>
            LUNA IA
          </Typography.Title>
          <Typography.Text type="secondary">Acceso del personal autorizado</Typography.Text>
        </div>

        <Typography.Title level={4} style={{ marginTop: 24 }}>
          {titulo}
        </Typography.Title>

        {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}

        {paso === 'credenciales' && (
          <Form layout="vertical" onFinish={onCredenciales} requiredMark={false}>
            <Form.Item name="username" label="Usuario" rules={[{ required: true, message: 'Escribe tu usuario' }]}>
              <Input prefix={<MailOutlined />} autoComplete="username" autoFocus />
            </Form.Item>
            <Form.Item name="password" label="Contraseña" rules={[{ required: true, message: 'Escribe tu contraseña' }]}>
              <Input.Password prefix={<LockOutlined />} autoComplete="current-password" />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={cargando}>
              Continuar
            </Button>
            <Button type="link" block onClick={() => navigate('/recuperar')}>
              Olvidé mi contraseña
            </Button>
          </Form>
        )}

        {paso === 'verificar' && (
          <Form layout="vertical" onFinish={onVerificar} requiredMark={false}>
            <Typography.Paragraph type="secondary">
              Escribe el código de 6 dígitos de tu app de autenticación. También puedes usar un código de recuperación.
            </Typography.Paragraph>
            <Form.Item name="codigo" rules={[{ required: true, message: 'Escribe el código' }]}>
              <Input prefix={<SafetyOutlined />} placeholder="123456" autoComplete="one-time-code" autoFocus />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={cargando}>
              Verificar
            </Button>
            <Button type="link" block onClick={() => setPaso('credenciales')}>
              Volver
            </Button>
          </Form>
        )}

        {paso === 'configurar' && configuracion && (
          <Form layout="vertical" onFinish={onConfirmar} requiredMark={false}>
            <Typography.Paragraph type="secondary">
              Escanea este código con Microsoft Authenticator o Google Authenticator. Si no puedes escanearlo, ingresa la clave manualmente.
            </Typography.Paragraph>
            <div className="qr-caja">
              <QRCodeSVG value={configuracion.uri} size={180} />
            </div>
            <Typography.Paragraph copyable={{ text: configuracion.secreto }} className="clave-manual">
              {configuracion.secreto}
            </Typography.Paragraph>
            <Form.Item name="codigo" label="Código de 6 dígitos de la app" rules={[{ required: true, message: 'Escribe el código' }]}>
              <Input placeholder="123456" autoComplete="one-time-code" maxLength={6} />
            </Form.Item>
            <Button type="primary" htmlType="submit" block loading={cargando}>
              Confirmar
            </Button>
          </Form>
        )}

        {paso === 'codigos' && (
          <>
            <Typography.Paragraph type="secondary">
              Son tu respaldo si pierdes el teléfono. Cada código sirve una sola vez y no se volverán a mostrar.
            </Typography.Paragraph>
            <div className="codigos">
              {codigos.map((c) => (
                <Typography.Text key={c} code>
                  {c}
                </Typography.Text>
              ))}
            </div>
            <Button type="primary" block style={{ marginTop: 24 }} onClick={() => navigate('/', { replace: true })}>
              Ya los guardé, continuar
            </Button>
          </>
        )}
      </Card>
    </div>
  )
}
