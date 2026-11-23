import {
  MessageOutlined,
  PauseCircleOutlined,
  PlayCircleOutlined,
  ReloadOutlined,
  RobotOutlined,
  SearchOutlined,
  UserOutlined,
  WhatsAppOutlined,
} from '@ant-design/icons'
import { Line } from '@ant-design/plots'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Avatar,
  Badge,
  Button,
  Card,
  Col,
  Descriptions,
  Drawer,
  Empty,
  Input,
  Popconfirm,
  Row,
  Select,
  Space,
  Statistic,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import { useEffect, useMemo, useState } from 'react'

import {
  actualizarAgenteActivo,
  listarConversacionesAgente,
  obtenerConversacionAgente,
  obtenerResumenAgente,
  type ConversacionAgente,
  type EstadoConversacion,
  type FiltroAgenteActivo,
  type MensajeAgente,
  type ResumenAgente,
} from '../api/agente'
import { obtenerUsuarioActual } from '../api/auth'
import { ApiError } from '../api/cliente'
import { listarSedes } from '../api/recursos'

const TAMANO_PAGINA = 25

const ESTADOS: { value: EstadoConversacion; label: string; color: string }[] = [
  { value: 'inicio', label: 'Inicio', color: 'default' },
  { value: 'esperando_sede', label: 'Esperando sede', color: 'processing' },
  { value: 'esperando_datos', label: 'Esperando datos', color: 'gold' },
  { value: 'esperando_confirmacion', label: 'Esperando confirmación', color: 'orange' },
  { value: 'cerrada', label: 'Cerrada', color: 'green' },
]

const ETIQUETA_ESTADO = new Map(ESTADOS.map((e) => [e.value, e]))

const ROL_MENSAJE: Record<string, string> = {
  paciente: 'Paciente',
  agente: 'Agente',
  humano: 'Personal de la clínica',
  sistema: 'Sistema',
}

const PALETA = ['#238781', '#1677ff', '#fa8c16', '#722ed1', '#eb2f96']

const formatoFecha = (iso: string) =>
  new Date(iso).toLocaleString('es-HN', { dateStyle: 'short', timeStyle: 'short' })

const numero = (valor: number | undefined | null) =>
  valor === undefined || valor === null ? '—' : valor.toLocaleString('es-HN')

function EstadoTag({ estado }: { estado: EstadoConversacion }) {
  const config = ETIQUETA_ESTADO.get(estado)
  return <Tag color={config?.color}>{config?.label ?? estado}</Tag>
}

function GraficaMensajes({ resumen }: { resumen: ResumenAgente | undefined }) {
  const datos = useMemo(
    () =>
      resumen?.mensajes_por_dia.flatMap((dia) => [
        { fecha: dia.fecha.slice(5), serie: 'Paciente', valor: dia.paciente },
        { fecha: dia.fecha.slice(5), serie: 'Agente', valor: dia.agente },
        { fecha: dia.fecha.slice(5), serie: 'Personal', valor: dia.humano },
      ]) ?? [],
    [resumen],
  )

  if (!resumen || resumen.mensajes_por_dia.every((dia) => dia.total === 0)) {
    return (
      <Empty
        image={Empty.PRESENTED_IMAGE_SIMPLE}
        description="Aún no hay mensajes en los últimos 14 días."
      />
    )
  }

  return (
    <Line
      data={datos}
      xField="fecha"
      yField="valor"
      colorField="serie"
      height={220}
      scale={{ color: { range: PALETA } }}
      axis={{ x: { title: 'Día' }, y: { title: 'Mensajes' } }}
    />
  )
}

function Burbuja({ mensaje }: { mensaje: MensajeAgente }) {
  const esSistema = mensaje.rol === 'sistema'
  const esPersonal = mensaje.rol === 'humano'
  const esAgente = mensaje.rol === 'agente'
  const alineadoDerecha = esPersonal

  if (esSistema) {
    return (
      <div style={{ display: 'flex', justifyContent: 'center' }}>
        <Tag color="default" style={{ whiteSpace: 'pre-wrap', maxWidth: '90%' }}>
          {mensaje.texto}
        </Tag>
      </div>
    )
  }

  return (
    <div
      style={{
        display: 'flex',
        justifyContent: alineadoDerecha ? 'flex-end' : 'flex-start',
        gap: 8,
      }}
    >
      {!alineadoDerecha && (
        <Avatar
          style={{ backgroundColor: esAgente ? '#238781' : '#8c8c8c' }}
          icon={esAgente ? <RobotOutlined /> : <UserOutlined />}
        />
      )}
      <div
        style={{
          maxWidth: '78%',
          padding: '8px 12px',
          borderRadius: 12,
          background: esAgente ? '#e6f4f3' : '#fafafa',
          border: '1px solid #f0f0f0',
          whiteSpace: 'pre-wrap',
        }}
      >
        <Typography.Text style={{ fontSize: 11, display: 'block', color: '#8c8c8c' }}>
          {ROL_MENSAJE[mensaje.rol] ?? mensaje.rol}
          {mensaje.tipo === 'audio' ? ' · audio transcrito' : ''} · {formatoFecha(mensaje.creado)}
        </Typography.Text>
        <Typography.Text>{mensaje.texto}</Typography.Text>
      </div>
      {alineadoDerecha && <Avatar style={{ backgroundColor: '#1677ff' }} icon={<UserOutlined />} />}
    </div>
  )
}

export default function AgenteWhatsApp() {
  const cliente = useQueryClient()
  const [pagina, setPagina] = useState(1)
  const [texto, setTexto] = useState('')
  const [q, setQ] = useState('')
  const [filtroActivo, setFiltroActivo] = useState<FiltroAgenteActivo>('todas')
  const [estado, setEstado] = useState<EstadoConversacion | null>(null)
  const [sede, setSede] = useState<number | null>(null)
  const [seleccionada, setSeleccionada] = useState<number | null>(null)

  const { data: usuario } = useQuery({ queryKey: ['me'], queryFn: obtenerUsuarioActual })
  const puede =
    usuario?.es_admin === true || usuario?.rol === 'recepcionista'

  const { data: sedes } = useQuery({
    queryKey: ['sedes', 'todas'],
    queryFn: () => listarSedes('todas'),
    enabled: puede,
  })

  const opcionesSede = useMemo(() => {
    if (usuario?.es_admin) {
      return sedes?.results.map((s) => ({ value: s.id, label: s.nombre })) ?? []
    }
    return usuario?.sedes.map((s) => ({ value: s.id, label: s.nombre })) ?? []
  }, [usuario, sedes])

  useEffect(() => {
    const espera = setTimeout(() => setQ(texto.trim()), 300)
    return () => clearTimeout(espera)
  }, [texto])

  useEffect(() => setPagina(1), [q, filtroActivo, estado, sede])

  const filtros = useMemo(
    () => ({ q, agente_activo: filtroActivo, estado, sede }),
    [q, filtroActivo, estado, sede],
  )

  const { data, isPending, isFetching, error } = useQuery({
    queryKey: ['agente', 'conversaciones', pagina, filtros],
    queryFn: () => listarConversacionesAgente(pagina, filtros),
    placeholderData: keepPreviousData,
    enabled: puede,
    refetchInterval: 60_000,
  })

  const { data: resumen } = useQuery({
    queryKey: ['agente', 'resumen'],
    queryFn: obtenerResumenAgente,
    enabled: puede,
    refetchInterval: 60_000,
  })

  const { data: detalle, isPending: cargandoDetalle } = useQuery({
    queryKey: ['agente', 'conversacion', seleccionada],
    queryFn: () => obtenerConversacionAgente(seleccionada as number),
    enabled: seleccionada !== null,
  })

  const cambiar = useMutation({
    mutationFn: ({ id, activo }: { id: number; activo: boolean }) =>
      actualizarAgenteActivo(id, activo),
    onSuccess: (resultado) => {
      message.success(resultado.agente_activo ? 'Agente reactivado' : 'Agente pausado')
      cliente.invalidateQueries({ queryKey: ['agente'] })
    },
    onError: (e) =>
      message.error(e instanceof ApiError ? e.message : 'No se pudo cambiar el estado.'),
  })

  const columnas: TableProps<ConversacionAgente>['columns'] = [
    {
      title: 'Teléfono',
      dataIndex: 'telefono',
      key: 'telefono',
      render: (valor: string) => <Typography.Text strong>{valor}</Typography.Text>,
    },
    {
      title: 'Paciente',
      dataIndex: 'paciente_nombre',
      key: 'paciente',
      render: (valor: string) => valor || <Typography.Text type="secondary">Sin registrar</Typography.Text>,
    },
    {
      title: 'Sede',
      dataIndex: 'sede_nombre',
      key: 'sede',
      render: (valor: string | null) => valor || '-',
    },
    {
      title: 'Estado',
      dataIndex: 'estado',
      key: 'estado',
      render: (valor: EstadoConversacion) => <EstadoTag estado={valor} />,
    },
    {
      title: 'Agente',
      dataIndex: 'agente_activo',
      key: 'agente',
      render: (activo: boolean) => (
        <Tag color={activo ? 'success' : 'warning'}>{activo ? 'Activo' : 'Pausado'}</Tag>
      ),
    },
    {
      title: 'Mensajes',
      dataIndex: 'total_mensajes',
      key: 'mensajes',
      align: 'right',
      render: (valor: number) => numero(valor),
    },
    {
      title: 'Última actividad',
      dataIndex: 'ultima_actividad',
      key: 'actividad',
      render: (valor: string) => formatoFecha(valor),
    },
    {
      title: 'Acciones',
      key: 'acciones',
      render: (_, conversacion) => (
        <Space>
          <Button size="small" icon={<MessageOutlined />} onClick={() => setSeleccionada(conversacion.id)}>
            Ver
          </Button>
          {conversacion.agente_activo ? (
            <Popconfirm
              title="¿Pausar el agente en este hilo?"
              description="Una persona deberá responder. Puedes reactivarlo cuando quieras."
              okText="Pausar"
              cancelText="Cancelar"
              onConfirm={() => cambiar.mutate({ id: conversacion.id, activo: false })}
            >
              <Button size="small" icon={<PauseCircleOutlined />}>
                Pausar
              </Button>
            </Popconfirm>
          ) : (
            <Button
              size="small"
              type="primary"
              icon={<PlayCircleOutlined />}
              loading={cambiar.isPending}
              onClick={() => cambiar.mutate({ id: conversacion.id, activo: true })}
            >
              Reactivar
            </Button>
          )}
        </Space>
      ),
    },
  ]

  if (usuario && !puede) {
    return (
      <Alert
        type="warning"
        showIcon
        message="Sin acceso al panel del agente"
        description="Solo el administrador y recepción pueden ver las conversaciones de WhatsApp."
      />
    )
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Agente WhatsApp
        </Typography.Title>
        <Typography.Text type="secondary">
          Conversaciones del agente, estado de cada hilo y métricas de uso.
          {usuario && !usuario.es_admin ? ' Solo ves las conversaciones de tus sedes.' : ''}
        </Typography.Text>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={12} sm={8} xl={4}>
          <Card>
            <Statistic
              title="Conversaciones"
              value={numero(resumen?.conversaciones.total)}
              prefix={<WhatsAppOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <Card>
            <Statistic
              title="Agente activo"
              value={numero(resumen?.conversaciones.activas)}
              prefix={<PlayCircleOutlined />}
              valueStyle={{ color: '#238781' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <Card>
            <Statistic
              title="Pausadas"
              value={numero(resumen?.conversaciones.pausadas)}
              prefix={<PauseCircleOutlined />}
              valueStyle={{ color: '#fa8c16' }}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <Card>
            <Statistic
              title="Mensajes hoy"
              value={numero(resumen?.mensajes.hoy)}
              prefix={<MessageOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <Card>
            <Statistic
              title="Citas del agente (mes)"
              value={numero(resumen?.citas.agente_mes)}
              prefix={<RobotOutlined />}
            />
          </Card>
        </Col>
        <Col xs={12} sm={8} xl={4}>
          <Card>
            <Statistic
              title="% citas del mes"
              value={resumen?.citas.porcentaje_agente ?? 0}
              suffix="%"
              prefix={<RobotOutlined />}
            />
          </Card>
        </Col>
      </Row>

      <Card title="Mensajes de los últimos 14 días">
        <GraficaMensajes resumen={resumen} />
      </Card>

      <Card
        title="Conversaciones"
        extra={
          <Button
            icon={<ReloadOutlined />}
            onClick={() => cliente.invalidateQueries({ queryKey: ['agente'] })}
          >
            Actualizar
          </Button>
        }
      >
        <Space wrap style={{ marginBottom: 16 }}>
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="Buscar por teléfono o paciente"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            style={{ width: 280 }}
          />
          <Select<FiltroAgenteActivo>
            style={{ width: 170 }}
            value={filtroActivo}
            onChange={setFiltroActivo}
            options={[
              { value: 'todas', label: 'Todas' },
              { value: 'activas', label: 'Agente activo' },
              { value: 'pausadas', label: 'Pausadas' },
            ]}
          />
          <Select<EstadoConversacion | null>
            allowClear
            placeholder="Todos los estados"
            style={{ width: 210 }}
            value={estado}
            onChange={(v) => setEstado(v ?? null)}
            options={ESTADOS.map((e) => ({ value: e.value, label: e.label }))}
          />
          {opcionesSede.length > 1 && (
            <Select<number | null>
              allowClear
              placeholder={usuario?.es_admin ? 'Todas las sedes' : 'Tus sedes'}
              style={{ width: 180 }}
              value={sede}
              onChange={(v) => setSede(v ?? null)}
              options={opcionesSede}
            />
          )}
        </Space>

        {error instanceof ApiError && error.status === 403 && (
          <Alert
            type="error"
            showIcon
            style={{ marginBottom: 16 }}
            message="No tienes permiso para ver estas conversaciones."
          />
        )}

        <Table<ConversacionAgente>
          rowKey="id"
          columns={columnas}
          dataSource={data?.results}
          loading={isPending || isFetching}
          pagination={{
            current: pagina,
            pageSize: TAMANO_PAGINA,
            total: data?.count ?? 0,
            showSizeChanger: false,
            onChange: setPagina,
          }}
          locale={{ emptyText: 'No hay conversaciones con estos filtros.' }}
          scroll={{ x: 900 }}
        />
      </Card>

      <Drawer
        title={
          detalle ? (
            <Space>
              <Badge status={detalle.agente_activo ? 'success' : 'warning'} />
              {detalle.telefono}
            </Space>
          ) : (
            'Conversación'
          )
        }
        open={seleccionada !== null}
        onClose={() => setSeleccionada(null)}
        width={620}
        destroyOnHidden
        extra={
          detalle && (
            <Button
              type={detalle.agente_activo ? 'default' : 'primary'}
              icon={detalle.agente_activo ? <PauseCircleOutlined /> : <PlayCircleOutlined />}
              loading={cambiar.isPending}
              onClick={() =>
                cambiar.mutate({ id: detalle.id, activo: !detalle.agente_activo })
              }
            >
              {detalle.agente_activo ? 'Pausar agente' : 'Reactivar agente'}
            </Button>
          )
        }
      >
        {cargandoDetalle && <Typography.Text type="secondary">Cargando conversación...</Typography.Text>}
        {detalle && (
          <Space direction="vertical" size="middle" style={{ width: '100%' }}>
            <Descriptions bordered size="small" column={1}>
              <Descriptions.Item label="Paciente">
                {detalle.paciente_nombre || 'Sin registrar'}
              </Descriptions.Item>
              <Descriptions.Item label="Sede">{detalle.sede_nombre || '-'}</Descriptions.Item>
              <Descriptions.Item label="Estado">
                <EstadoTag estado={detalle.estado} />
              </Descriptions.Item>
              <Descriptions.Item label="Agente">
                <Tag color={detalle.agente_activo ? 'success' : 'warning'}>
                  {detalle.agente_activo ? 'Activo' : 'Pausado (atención humana)'}
                </Tag>
              </Descriptions.Item>
              <Descriptions.Item label="Creada">{formatoFecha(detalle.creada)}</Descriptions.Item>
              <Descriptions.Item label="Última actividad">
                {formatoFecha(detalle.ultima_actividad)}
              </Descriptions.Item>
            </Descriptions>

            <Typography.Text type="secondary">
              {detalle.total_mensajes} mensaje(s). Se muestran los más recientes.
            </Typography.Text>

            <div style={{ maxHeight: '52vh', overflowY: 'auto', paddingRight: 4 }}>
              <Space direction="vertical" size="small" style={{ width: '100%' }}>
                {detalle.mensajes.map((mensaje) => (
                  <Burbuja key={mensaje.id} mensaje={mensaje} />
                ))}
              </Space>
            </div>
          </Space>
        )}
      </Drawer>
    </Space>
  )
}
