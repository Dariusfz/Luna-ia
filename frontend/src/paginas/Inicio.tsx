import {
  CalendarOutlined,
  CheckCircleOutlined,
  ClockCircleOutlined,
  DollarOutlined,
  HourglassOutlined,
  MedicineBoxOutlined,
  RiseOutlined,
  TeamOutlined,
  WalletOutlined,
} from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Col, Row, Space, Statistic, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { listarAtenciones, type Atencion } from '../api/atenciones'
import { obtenerUsuarioActual } from '../api/auth'
import { listarListaEspera } from '../api/listaEspera'
import { obtenerResumenCaja } from '../api/pagos'
import { listarPacientes, listarSedes } from '../api/recursos'
import { COLOR_ESTADO, ETIQUETA_ESTADO, type EstadoAtencion } from '../constantes/atenciones'

const etiquetaRol: Record<string, string> = {
  admin: 'Administrador',
  doctor: 'Doctor',
  recepcionista: 'Recepcionista',
  asistente: 'Asistente',
}

function fechaLocal(fecha: Date): string {
  const mes = String(fecha.getMonth() + 1).padStart(2, '0')
  const dia = String(fecha.getDate()).padStart(2, '0')
  return `${fecha.getFullYear()}-${mes}-${dia}`
}

function sumarDias(fecha: string, dias: number): string {
  const base = new Date(`${fecha}T12:00:00`)
  base.setDate(base.getDate() + dias)
  return fechaLocal(base)
}

const formatoHora = (hora: string) => hora.slice(0, 5)

const formatoLempiras = (valor: string) =>
  `L ${Number(valor).toLocaleString('es-HN', { minimumFractionDigits: 2 })}`

export default function Inicio() {
  const navegar = useNavigate()
  const [hoy] = useState(() => fechaLocal(new Date()))
  const manana = sumarDias(hoy, 1)
  const enUnaSemana = sumarDias(hoy, 7)

  const { data: usuario } = useQuery({ queryKey: ['me'], queryFn: obtenerUsuarioActual })

  const { data: atencionesHoy, isPending: cargandoHoy } = useQuery({
    queryKey: ['atenciones', 'hoy', hoy],
    queryFn: () => listarAtenciones(1, { desde: hoy, hasta: hoy }),
  })

  const { data: completadasHoy, isPending: cargandoCompletadas } = useQuery({
    queryKey: ['atenciones', 'completadas-hoy', hoy],
    queryFn: () => listarAtenciones(1, { estado: 'completada', desde: hoy, hasta: hoy }),
  })

  const { data: proximas } = useQuery({
    queryKey: ['atenciones', 'proximas', manana, enUnaSemana],
    queryFn: () =>
      listarAtenciones(1, {
        estado: ['pendiente', 'confirmada'],
        desde: manana,
        hasta: enUnaSemana,
      }),
  })

  const { data: pacientes } = useQuery({
    queryKey: ['pacientes', 'resumen'],
    queryFn: () => listarPacientes(1, { activo: 'true' }),
  })

  const { data: enEspera, isPending: cargandoEspera } = useQuery({
    queryKey: ['lista-espera', 'resumen'],
    queryFn: () => listarListaEspera(1, { estado: ['esperando', 'contactado'] }),
  })

  const { data: sedes } = useQuery({
    queryKey: ['sedes', 'resumen'],
    queryFn: () => listarSedes('true'),
  })

  const { data: cajaHoy } = useQuery({
    queryKey: ['caja', 'resumen', hoy, hoy],
    queryFn: () => obtenerResumenCaja({ desde: hoy, hasta: hoy }),
    enabled: usuario?.es_admin === true,
  })

  const nombre = usuario ? `${usuario.nombres} ${usuario.apellidos}`.trim() || usuario.username : ''

  const columnas: TableProps<Atencion>['columns'] = [
    {
      title: 'Horario',
      key: 'horario',
      render: (_, atencion) => `${formatoHora(atencion.hora_inicio)} - ${formatoHora(atencion.hora_fin)}`,
    },
    {
      title: 'Estado',
      dataIndex: 'estado',
      key: 'estado',
      render: (estado: EstadoAtencion) => (
        <Tag color={COLOR_ESTADO[estado]}>{ETIQUETA_ESTADO[estado]}</Tag>
      ),
    },
    { title: 'Paciente', dataIndex: 'paciente_nombre', key: 'paciente' },
    {
      title: 'Doctor',
      key: 'doctor',
      render: (_, atencion) => (
        <Space size={4}>
          {atencion.doctor_nombre}
          <Tag>{atencion.doctor_tipo === 'propio' ? 'Interno' : 'Por sesión'}</Tag>
        </Space>
      ),
    },
    { title: 'Sede', dataIndex: 'sede_nombre', key: 'sede' },
    { title: 'Tipo de trabajo', dataIndex: 'tipo_trabajo_nombre', key: 'tipo' },
  ]

  if (usuario?.es_admin) {
    columnas.push({
      title: 'Honorario',
      dataIndex: 'honorario_doctor',
      key: 'honorario',
      align: 'right',
      render: formatoLempiras,
    })
  }

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Hola, {nombre}
        </Typography.Title>
        <Space wrap size="small" style={{ marginTop: 4 }}>
          <Typography.Text type="secondary">{usuario ? etiquetaRol[usuario.rol] : ''}</Typography.Text>
          <Tag color="teal">{usuario?.es_admin ? 'Todas las sedes' : 'Tus sedes'}</Tag>
        </Space>
      </div>

      <Row gutter={[16, 16]}>
        <Col xs={24} sm={12} xl={8}>
          <Card>
            <Statistic
              title="Citas y atenciones de hoy"
              value={atencionesHoy ? atencionesHoy.count : '—'}
              prefix={<CalendarOutlined />}
              loading={cargandoHoy}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={8}>
          <Card>
            <Statistic
              title="Completadas hoy"
              value={completadasHoy ? completadasHoy.count : '—'}
              prefix={<CheckCircleOutlined />}
              loading={cargandoCompletadas}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={8}>
          <Card>
            <Statistic
              title="Citas pendientes (7 días)"
              value={proximas ? proximas.count : '—'}
              prefix={<ClockCircleOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={8}>
          <Card>
            <Statistic
              title="Pacientes activos"
              value={pacientes ? pacientes.count : '—'}
              prefix={<TeamOutlined />}
            />
          </Card>
        </Col>
        <Col xs={24} sm={12} xl={8}>
          <Card>
            <Statistic
              title="En lista de espera"
              value={enEspera ? enEspera.count : '—'}
              prefix={<HourglassOutlined />}
              loading={cargandoEspera}
            />
          </Card>
        </Col>
      </Row>

      {usuario?.es_admin && (
        <Row gutter={[16, 16]}>
          <Col xs={24} sm={12} xl={8}>
            <Card
              title="Caja de hoy"
              extra={
                <Button type="link" onClick={() => navegar('/caja')}>
                  Ver caja
                </Button>
              }
            >
              <Statistic
                title="Cobrado"
                value={Number(cajaHoy?.cobrado ?? 0)}
                precision={2}
                prefix={<DollarOutlined />}
                suffix="L"
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={8}>
            <Card style={{ height: '100%' }}>
              <Statistic
                title="Comisión doctores"
                value={Number(cajaHoy?.comision_doctores ?? 0)}
                precision={2}
                prefix={<WalletOutlined />}
                suffix="L"
              />
            </Card>
          </Col>
          <Col xs={24} sm={12} xl={8}>
            <Card style={{ height: '100%' }}>
              <Statistic
                title="Ganancia neta"
                value={Number(cajaHoy?.ganancia ?? 0)}
                precision={2}
                prefix={<RiseOutlined />}
                suffix="L"
              />
            </Card>
          </Col>
        </Row>
      )}

      <Row gutter={[16, 16]}>
        <Col xs={24} xl={17}>
          <Card
            title="Citas y atenciones de hoy"
            extra={
              <Button type="link" onClick={() => navegar('/atenciones')}>
                Ver todas
              </Button>
            }
          >
            <Table<Atencion>
              rowKey="id"
              columns={columnas}
              dataSource={atencionesHoy?.results}
              loading={cargandoHoy}
              pagination={false}
              size="small"
              locale={{ emptyText: 'No hay citas ni atenciones registradas para hoy.' }}
            />
          </Card>
        </Col>
        <Col xs={24} xl={7}>
          <Card title="Accesos rápidos">
            <Space direction="vertical" style={{ width: '100%' }}>
              <Button block icon={<CalendarOutlined />} onClick={() => navegar('/atenciones')}>
                Nueva cita
              </Button>
              <Button block icon={<HourglassOutlined />} onClick={() => navegar('/lista-espera')}>
                Lista de espera
              </Button>
              <Button block icon={<TeamOutlined />} onClick={() => navegar('/pacientes')}>
                Pacientes
              </Button>
              {usuario?.es_admin && (
                <Button block icon={<MedicineBoxOutlined />} onClick={() => navegar('/doctores')}>
                  Doctores
                </Button>
              )}
            </Space>
          </Card>

          <Card title="Sedes activas" style={{ marginTop: 16 }}>
            <Space wrap>
              {usuario?.es_admin && <Tag color="teal">Consolidado</Tag>}
              {usuario?.sedes.map((sede) => (
                <Tag key={sede.id} color="processing">
                  {sede.nombre}
                </Tag>
              ))}
              {usuario && !usuario.es_admin && usuario.sedes.length === 0 && (
                <Typography.Text type="secondary">No tienes sedes asignadas.</Typography.Text>
              )}
              {usuario?.es_admin && (
                <Typography.Text type="secondary">
                  {sedes ? `${sedes.count} sede(s) activa(s)` : ''}
                </Typography.Text>
              )}
            </Space>
          </Card>
        </Col>
      </Row>
    </Space>
  )
}
