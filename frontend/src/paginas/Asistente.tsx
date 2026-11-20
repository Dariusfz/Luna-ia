import {
  DeleteOutlined,
  MessageOutlined,
  PlusOutlined,
  RobotOutlined,
  SendOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { Column, Line } from '@ant-design/plots'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Avatar, Button, Card, Col, Input, Popconfirm, Row, Space, Tag, Typography } from 'antd'
import { useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import {
  eliminarConversacion,
  listarConversaciones,
  obtenerConversacion,
  preguntarAsistente,
  type GraficaAnalitica,
  type MensajeGuardado,
} from '../api/asistente'
import { obtenerUsuarioActual } from '../api/auth'
import { ApiError } from '../api/cliente'

interface Sugerencia {
  texto: string
  /** Roles que ven la sugerencia. Sin valor: todos. El admin las ve todas. */
  roles?: string[]
}

// Las sugerencias solo orientan; el backend es quien decide qué puede consultar cada rol.
const SUGERENCIAS: Sugerencia[] = [
  { texto: '¿Cuántas citas hay hoy?' },
  { texto: '¿Cuántos pacientes se atendieron este mes?', roles: ['doctor', 'recepcionista', 'asistente'] },
  { texto: '¿Qué tratamientos se piden más este mes?', roles: ['doctor', 'recepcionista'] },
  { texto: '¿A qué horas hay más citas?' },
  { texto: '¿Qué sede tiene más citas este mes?', roles: ['recepcionista'] },
  { texto: '¿Cuánto dinero se ha cobrado este mes?', roles: ['admin'] },
]

const BIENVENIDA = {
  rol: 'asistente' as const,
  texto:
    'Hola, soy el asistente de LUNA-IA. Puedo responder preguntas sobre citas y atenciones ' +
    'y mostrarte una gráfica. Solo veo los datos de tus sedes.',
}

// Paleta de la marca y colores complementarios: cada barra tiene su propio color.
const PALETA = [
  '#238781',
  '#1677ff',
  '#fa8c16',
  '#722ed1',
  '#eb2f96',
  '#13c2c2',
  '#faad14',
  '#2f54eb',
  '#a0d911',
  '#f5222d',
]

function GraficaResultado({ grafica }: { grafica: GraficaAnalitica }) {
  if (grafica.total === 0) {
    return <Typography.Text type="secondary">No hay datos para esta consulta.</Typography.Text>
  }
  const base = {
    data: grafica.datos,
    xField: 'etiqueta',
    yField: 'valor',
    height: 260,
    legend: false,
    axis: {
      x: { title: grafica.ejes.x },
      y: { title: grafica.ejes.y },
    },
  }
  if (grafica.tipo_grafica === 'linea') {
    return (
      <Line
        {...base}
        style={{ stroke: PALETA[0], lineWidth: 2 }}
        point={{ style: { fill: PALETA[0], stroke: PALETA[0] } }}
      />
    )
  }
  return (
    <Column
      {...base}
      colorField="etiqueta"
      scale={{ color: { range: PALETA } }}
    />
  )
}

function Burbuja({
  rol,
  texto,
  grafica,
}: {
  rol: 'usuario' | 'asistente'
  texto: string
  grafica?: GraficaAnalitica | null
}) {
  const esUsuario = rol === 'usuario'
  return (
    <div style={{ display: 'flex', justifyContent: esUsuario ? 'flex-end' : 'flex-start', gap: 8 }}>
      {!esUsuario && <Avatar style={{ backgroundColor: '#238781' }} icon={<RobotOutlined />} />}
      <div
        style={{
          maxWidth: '80%',
          padding: '10px 14px',
          borderRadius: 12,
          background: esUsuario ? '#e6f4f3' : '#fafafa',
          border: '1px solid #f0f0f0',
          whiteSpace: 'pre-wrap',
        }}
      >
        <Typography.Text>{texto}</Typography.Text>
        {grafica && (
          <div style={{ marginTop: 12, minWidth: 320 }}>
            <Typography.Text strong>{grafica.titulo}</Typography.Text>
            <div style={{ marginTop: 8 }}>
              <GraficaResultado grafica={grafica} />
            </div>
            <Space size={4} wrap style={{ marginTop: 4 }}>
              <Tag>
                {grafica.filtros.desde} a {grafica.filtros.hasta}
              </Tag>
              {grafica.filtros.sede !== null && <Tag color="processing">Sede filtrada</Tag>}
            </Space>
          </div>
        )}
      </div>
      {esUsuario && <Avatar icon={<UserOutlined />} />}
    </div>
  )
}

function formatoFecha(iso: string): string {
  return new Date(iso).toLocaleString('es-HN', { dateStyle: 'short', timeStyle: 'short' })
}

export default function Asistente() {
  const cliente = useQueryClient()
  const [params, setParams] = useSearchParams()
  const conversacionId = Number(params.get('c')) || null

  const { data: usuario } = useQuery({ queryKey: ['me'], queryFn: obtenerUsuarioActual })
  const sugerencias = SUGERENCIAS.filter(
    (sugerencia) =>
      !sugerencia.roles || usuario?.es_admin || (usuario && sugerencia.roles.includes(usuario.rol)),
  )

  const { data: conversaciones, isPending: cargandoLista } = useQuery({
    queryKey: ['asistente', 'conversaciones'],
    queryFn: listarConversaciones,
  })

  const { data: detalle, isPending: cargandoDetalle, error: errorDetalle } = useQuery({
    queryKey: ['asistente', 'conversacion', conversacionId],
    queryFn: () => obtenerConversacion(conversacionId as number),
    enabled: conversacionId !== null,
  })

  const [pregunta, setPregunta] = useState('')
  const [preguntaPendiente, setPreguntaPendiente] = useState<string | null>(null)
  const [errorEnvio, setErrorEnvio] = useState<string | null>(null)
  const finRef = useRef<HTMLDivElement>(null)

  // Al entrar al módulo sin conversación en la URL se abre la más reciente. Solo una vez:
  // si después el usuario pulsa "Nueva", no debe reabrirse la anterior.
  const abreYaResuelta = useRef(false)
  useEffect(() => {
    if (abreYaResuelta.current) return
    if (conversacionId !== null) {
      abreYaResuelta.current = true
      return
    }
    if (conversaciones) {
      abreYaResuelta.current = true
      if (conversaciones.results.length > 0) {
        setParams({ c: String(conversaciones.results[0].id) }, { replace: true })
      }
    }
  }, [conversacionId, conversaciones, setParams])

  // Si la conversación ya no existe (borrada o de otro usuario), se quita de la URL.
  useEffect(() => {
    if (errorDetalle instanceof ApiError && errorDetalle.status === 404) {
      setParams({}, { replace: true })
    }
  }, [errorDetalle, setParams])

  const enviarPregunta = useMutation({
    mutationFn: (texto: string) => preguntarAsistente(texto, conversacionId),
    onMutate: (texto) => {
      setPreguntaPendiente(texto)
      setErrorEnvio(null)
    },
    onSuccess: (datos) => {
      setPreguntaPendiente(null)
      if (datos.conversacion !== conversacionId) {
        setParams({ c: String(datos.conversacion) }, { replace: true })
      }
      cliente.invalidateQueries({ queryKey: ['asistente', 'conversaciones'] })
      cliente.invalidateQueries({ queryKey: ['asistente', 'conversacion', datos.conversacion] })
    },
    onError: (error, texto) => {
      setPreguntaPendiente(null)
      setPregunta(texto) // se devuelve el texto para no tener que escribirlo otra vez
      setErrorEnvio(
        error instanceof ApiError ? error.message : 'No se pudo consultar al asistente.',
      )
    },
  })

  const eliminar = useMutation({
    mutationFn: eliminarConversacion,
    onSuccess: (_, id) => {
      cliente.removeQueries({ queryKey: ['asistente', 'conversacion', id] })
      if (id === conversacionId) setParams({}, { replace: true })
      cliente.invalidateQueries({ queryKey: ['asistente', 'conversaciones'] })
    },
  })

  const mensajes: MensajeGuardado[] = detalle?.mensajes ?? []

  useEffect(() => {
    finRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [mensajes.length, preguntaPendiente, enviarPregunta.isPending])

  function enviar(texto: string) {
    const limpio = texto.trim()
    if (!limpio || enviarPregunta.isPending) return
    setPregunta('')
    enviarPregunta.mutate(limpio)
  }

  function nuevaConversacion() {
    setErrorEnvio(null)
    setParams({}, { replace: true })
  }

  const enCurso = enviarPregunta.isPending

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Asistente IA
        </Typography.Title>
        <Typography.Text type="secondary">
          Pregunta sobre citas y atenciones. Las respuestas usan solo los datos de tus sedes.
        </Typography.Text>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} lg={7}>
          <Card
            title="Conversaciones"
            extra={
              <Button type="link" icon={<PlusOutlined />} onClick={nuevaConversacion}>
                Nueva
              </Button>
            }
            styles={{ body: { padding: 8, maxHeight: 560, overflowY: 'auto' } }}
          >
            {cargandoLista && <Typography.Text type="secondary">Cargando...</Typography.Text>}
            {conversaciones && conversaciones.results.length === 0 && (
              <Typography.Text type="secondary">
                Aún no tienes conversaciones. Escribe una pregunta para empezar.
              </Typography.Text>
            )}
            <Space direction="vertical" size={4} style={{ width: '100%' }}>
              {conversaciones?.results.map((conversacion) => {
                const activa = conversacion.id === conversacionId
                return (
                  <div
                    key={conversacion.id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 4,
                      padding: '6px 8px',
                      borderRadius: 8,
                      background: activa ? '#e6f4f3' : undefined,
                    }}
                  >
                    <Button
                      type="text"
                      icon={<MessageOutlined />}
                      onClick={() => setParams({ c: String(conversacion.id) }, { replace: true })}
                      style={{ flex: 1, minWidth: 0, textAlign: 'left', overflow: 'hidden' }}
                    >
                      <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {conversacion.titulo || 'Conversación'}
                      </span>
                    </Button>
                    <Popconfirm
                      title="¿Borrar esta conversación?"
                      description="No se puede recuperar."
                      okText="Borrar"
                      cancelText="Cancelar"
                      okButtonProps={{ danger: true }}
                      onConfirm={() => eliminar.mutate(conversacion.id)}
                    >
                      <Button
                        type="text"
                        size="small"
                        danger
                        icon={<DeleteOutlined />}
                        aria-label="Borrar conversación"
                      />
                    </Popconfirm>
                  </div>
                )
              })}
            </Space>
            {conversacionId && detalle && (
              <Typography.Text type="secondary" style={{ display: 'block', marginTop: 8, fontSize: 12 }}>
                Actualizada: {formatoFecha(detalle.actualizada)}
              </Typography.Text>
            )}
          </Card>
        </Col>

        <Col xs={24} lg={17}>
          <Card styles={{ body: { padding: 16 } }}>
            <div style={{ maxHeight: 520, overflowY: 'auto', paddingRight: 4 }}>
              <Space direction="vertical" size="middle" style={{ width: '100%' }}>
                {conversacionId === null && <Burbuja rol={BIENVENIDA.rol} texto={BIENVENIDA.texto} />}
                {cargandoDetalle && conversacionId !== null && (
                  <Typography.Text type="secondary">Cargando conversación...</Typography.Text>
                )}
                {mensajes.map((mensaje) => (
                  <Burbuja
                    key={mensaje.id}
                    rol={mensaje.rol}
                    texto={mensaje.texto}
                    grafica={mensaje.grafica}
                  />
                ))}
                {preguntaPendiente && <Burbuja rol="usuario" texto={preguntaPendiente} />}
                {enCurso && <Typography.Text type="secondary">Consultando...</Typography.Text>}
                {errorEnvio && <Typography.Text type="danger">{errorEnvio}</Typography.Text>}
                <div ref={finRef} />
              </Space>
            </div>
          </Card>

          <Space wrap style={{ marginTop: 16 }}>
            {sugerencias.map((sugerencia) => (
              <Button
                key={sugerencia.texto}
                size="small"
                onClick={() => enviar(sugerencia.texto)}
                disabled={enCurso}
              >
                {sugerencia.texto}
              </Button>
            ))}
          </Space>

          <Space.Compact style={{ width: '100%', marginTop: 12 }}>
            <Input
              value={pregunta}
              onChange={(evento) => setPregunta(evento.target.value)}
              onPressEnter={() => enviar(pregunta)}
              placeholder="Escribe tu pregunta"
              maxLength={500}
              disabled={enCurso}
              aria-label="Pregunta para el asistente"
            />
            <Button
              type="primary"
              icon={<SendOutlined />}
              onClick={() => enviar(pregunta)}
              loading={enCurso}
              disabled={!pregunta.trim()}
            >
              Enviar
            </Button>
          </Space.Compact>
        </Col>
      </Row>
    </Space>
  )
}
