import {
  CalendarOutlined,
  CheckCircleOutlined,
  DollarOutlined,
  LineChartOutlined,
} from '@ant-design/icons'
import { Column, Line } from '@ant-design/plots'
import { useQuery } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Col,
  DatePicker,
  Empty,
  Row,
  Select,
  Space,
  Spin,
  Statistic,
  Tag,
  Typography,
} from 'antd'
import dayjs from 'dayjs'
import type { Dayjs } from 'dayjs'
import { useMemo, useState } from 'react'

import {
  obtenerAtendidosMes,
  obtenerCitasHoy,
  obtenerIngresos,
  obtenerPorHora,
  obtenerPorSede,
  obtenerPorServicio,
  type GraficaAnalitica,
} from '../api/analitica'
import { obtenerUsuarioActual } from '../api/auth'
import { ApiError } from '../api/cliente'
import { listarSedes } from '../api/recursos'

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

// Espejo de `analitica/politicas.py`: decide qué tarjetas mostrar. El backend vuelve
// a validar el rol y las sedes en cada endpoint.
const CONSULTAS_POR_ROL: Record<string, string[]> = {
  recepcionista: ['citas_hoy', 'atendidos_mes', 'por_servicio', 'por_hora', 'por_sede'],
  asistente: ['citas_hoy', 'atendidos_mes', 'por_hora'],
  doctor: ['citas_hoy', 'atendidos_mes', 'por_servicio', 'por_hora'],
}
const CONSULTAS_ADMIN = [
  'citas_hoy',
  'atendidos_mes',
  'por_servicio',
  'por_hora',
  'por_sede',
  'ingresos',
]

const formatoLempiras = (valor: number) =>
  `L ${valor.toLocaleString('es-HN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`

/** Rango por defecto: del primero del mes actual hasta hoy. */
function rangoMesActual(): [Dayjs, Dayjs] {
  const ahora = dayjs()
  return [ahora.startOf('month'), ahora]
}

function Contenido({ grafica }: { grafica: GraficaAnalitica }) {
  if (grafica.total === 0) {
    return <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="No hay datos en este rango." />
  }
  const base = {
    data: grafica.datos,
    xField: 'etiqueta',
    yField: 'valor',
    height: 250,
    legend: false,
    axis: {
      x: {
        title: grafica.ejes.x,
        label: { autoHide: true, autoRotate: true },
      },
      y: { title: grafica.ejes.y },
    },
  }
  const grafico =
    grafica.tipo_grafica === 'linea' ? (
      <Line
        {...base}
        style={{ stroke: PALETA[0], lineWidth: 2 }}
        point={{ style: { fill: PALETA[0], stroke: PALETA[0] } }}
      />
    ) : (
      <Column {...base} colorField="etiqueta" scale={{ color: { range: PALETA } }} />
    )
  // Muchas fechas/categorías necesitan ancho extra: la gráfica se desplaza en horizontal.
  const porPunto = grafica.tipo_grafica === 'linea' ? 36 : 56
  const ancho = Math.max(grafica.datos.length * porPunto, 320)
  return (
    <div style={{ overflowX: 'auto' }}>
      <div style={{ width: ancho, minWidth: '100%' }}>{grafico}</div>
    </div>
  )
}

function TarjetaGrafica({
  titulo,
  grafica,
  cargando,
  error,
}: {
  titulo: string
  grafica: GraficaAnalitica | undefined
  cargando: boolean
  error: unknown
}) {
  return (
    <Card
      title={titulo}
      extra={grafica && <Tag>{grafica.total.toLocaleString('es-HN')}</Tag>}
      style={{ height: '100%' }}
      styles={{ body: { minHeight: 290 } }}
    >
      {cargando ? (
        <div style={{ display: 'flex', justifyContent: 'center', paddingTop: 80 }}>
          <Spin />
        </div>
      ) : error ? (
        <Alert
          type={error instanceof ApiError && error.status === 403 ? 'warning' : 'error'}
          showIcon
          message={
            error instanceof ApiError
              ? error.message
              : 'No se pudo cargar esta gráfica.'
          }
        />
      ) : grafica ? (
        <Contenido grafica={grafica} />
      ) : null}
    </Card>
  )
}

export default function Metricas() {
  const [rango, setRango] = useState<[Dayjs, Dayjs]>(rangoMesActual)
  const desde = rango[0].format('YYYY-MM-DD')
  const hasta = rango[1].format('YYYY-MM-DD')
  const [sede, setSede] = useState<number | null>(null)

  const { data: usuario } = useQuery({ queryKey: ['me'], queryFn: obtenerUsuarioActual })

  const { data: sedes } = useQuery({
    queryKey: ['sedes', 'todas'],
    queryFn: () => listarSedes('todas'),
    enabled: usuario?.es_admin === true,
  })

  const opcionesSede = useMemo(() => {
    if (usuario?.es_admin) {
      return sedes?.results.map((s) => ({ value: s.id, label: s.nombre })) ?? []
    }
    return usuario?.sedes.map((s) => ({ value: s.id, label: s.nombre })) ?? []
  }, [usuario, sedes])

  const permitidas = useMemo(() => {
    if (!usuario) return new Set<string>()
    if (usuario.es_admin) return new Set(CONSULTAS_ADMIN)
    return new Set(CONSULTAS_POR_ROL[usuario.rol] ?? [])
  }, [usuario])

  const puede = (consulta: string) => !!usuario && permitidas.has(consulta)

  const { data: citasHoy, isPending: cargandoCitasHoy, error: errorCitasHoy } = useQuery({
    queryKey: ['metricas', 'citas-hoy', sede],
    queryFn: () => obtenerCitasHoy(sede),
    enabled: puede('citas_hoy'),
  })

  const { data: atendidosMes, isPending: cargandoAtendidos, error: errorAtendidos } = useQuery({
    queryKey: ['metricas', 'atendidos-mes', desde, hasta, sede],
    queryFn: () => obtenerAtendidosMes(desde, hasta, sede),
    enabled: puede('atendidos_mes'),
  })

  const { data: porServicio, isPending: cargandoServicio, error: errorServicio } = useQuery({
    queryKey: ['metricas', 'por-servicio', desde, hasta, sede],
    queryFn: () => obtenerPorServicio(desde, hasta, sede),
    enabled: puede('por_servicio'),
  })

  const { data: porHora, isPending: cargandoHora, error: errorHora } = useQuery({
    queryKey: ['metricas', 'por-hora', desde, hasta, sede],
    queryFn: () => obtenerPorHora(desde, hasta, sede),
    enabled: puede('por_hora'),
  })

  const { data: porSede, isPending: cargandoSede, error: errorSede } = useQuery({
    queryKey: ['metricas', 'por-sede', desde, hasta],
    queryFn: () => obtenerPorSede(desde, hasta),
    enabled: puede('por_sede'),
  })

  const { data: ingresos, isPending: cargandoIngresos, error: errorIngresos } = useQuery({
    queryKey: ['metricas', 'ingresos', desde, hasta, sede],
    queryFn: () => obtenerIngresos(desde, hasta, sede),
    enabled: puede('ingresos'),
  })

  const citasEnRango =
    porHora?.total ?? porSede?.total ?? porServicio?.total ?? atendidosMes?.total ?? 0

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Métricas
        </Typography.Title>
        <Typography.Text type="secondary">
          Indicadores de citas, atención y dinero. Solo se muestran los módulos que tu rol
          puede consultar y las sedes que tienes asignadas.
        </Typography.Text>
      </div>

      <Card>
        <Space wrap size="middle" align="center">
          <Space direction="vertical" size={0}>
            <Typography.Text type="secondary">Rango de fechas</Typography.Text>
            <DatePicker.RangePicker
              allowClear
              value={rango}
              format="DD/MM/YYYY"
              placeholder={['Desde', 'Hasta']}
              onChange={(valores) => {
                // Al limpiar, se vuelve al rango por defecto: primero del mes actual hasta hoy.
                if (valores?.[0] && valores?.[1]) {
                  setRango([valores[0], valores[1]])
                } else {
                  setRango(rangoMesActual())
                }
              }}
            />
          </Space>
          <Button style={{ alignSelf: 'flex-end' }} onClick={() => setRango(rangoMesActual())}>
            Mes actual
          </Button>
          {opcionesSede.length > 0 && (
            <Space direction="vertical" size={0}>
              <Typography.Text type="secondary">Sede</Typography.Text>
              <Select<number | null>
                allowClear
                placeholder={usuario?.es_admin ? 'Todas las sedes' : 'Tus sedes'}
                style={{ width: 200 }}
                value={sede}
                onChange={(v) => setSede(v ?? null)}
                options={opcionesSede}
              />
            </Space>
          )}
          <Tag color="processing" style={{ alignSelf: 'flex-end' }}>
            {desde} a {hasta}
          </Tag>
        </Space>
      </Card>

      <Row gutter={[16, 16]}>
        <Col xs={12} xl={6}>
          <Card>
            <Statistic
              title="Citas en el rango"
              value={citasEnRango}
              prefix={<CalendarOutlined />}
              loading={!usuario}
            />
          </Card>
        </Col>
        {puede('atendidos_mes') && (
          <Col xs={12} xl={6}>
            <Card>
              <Statistic
                title="Pacientes atendidos"
                value={atendidosMes?.total ?? 0}
                prefix={<CheckCircleOutlined />}
                loading={cargandoAtendidos}
              />
            </Card>
          </Col>
        )}
        {puede('ingresos') && (
          <Col xs={12} xl={6}>
            <Card>
              <Statistic
                title="Cobrado en el rango"
                value={ingresos?.total ?? 0}
                prefix={<DollarOutlined />}
                formatter={(valor) => formatoLempiras(Number(valor))}
                loading={cargandoIngresos}
              />
            </Card>
          </Col>
        )}
        <Col xs={12} xl={6}>
          <Card>
            <Statistic
              title="Citas de hoy"
              value={citasHoy?.total ?? 0}
              prefix={<LineChartOutlined />}
              loading={cargandoCitasHoy}
            />
          </Card>
        </Col>
      </Row>

      <Row gutter={[16, 16]}>
        {puede('atendidos_mes') && (
          <Col xs={24} xl={12}>
            <TarjetaGrafica
              titulo="Pacientes atendidos por día"
              grafica={atendidosMes}
              cargando={cargandoAtendidos}
              error={errorAtendidos}
            />
          </Col>
        )}
        {puede('por_hora') && (
          <Col xs={24} xl={12}>
            <TarjetaGrafica
              titulo="Citas por hora de inicio"
              grafica={porHora}
              cargando={cargandoHora}
              error={errorHora}
            />
          </Col>
        )}
        {puede('por_servicio') && (
          <Col xs={24} xl={12}>
            <TarjetaGrafica
              titulo="Citas por tipo de trabajo"
              grafica={porServicio}
              cargando={cargandoServicio}
              error={errorServicio}
            />
          </Col>
        )}
        {puede('por_sede') && (
          <Col xs={24} xl={12}>
            <TarjetaGrafica
              titulo="Citas por sede"
              grafica={porSede}
              cargando={cargandoSede}
              error={errorSede}
            />
          </Col>
        )}
        {puede('citas_hoy') && (
          <Col xs={24} xl={12}>
            <TarjetaGrafica
              titulo="Citas de hoy por estado"
              grafica={citasHoy}
              cargando={cargandoCitasHoy}
              error={errorCitasHoy}
            />
          </Col>
        )}
        {puede('ingresos') && (
          <Col xs={24} xl={12}>
            <TarjetaGrafica
              titulo="Ingresos del rango (HNL)"
              grafica={ingresos}
              cargando={cargandoIngresos}
              error={errorIngresos}
            />
          </Col>
        )}
      </Row>
    </Space>
  )
}
