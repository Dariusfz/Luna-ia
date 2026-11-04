import { DollarOutlined, PlusOutlined, RiseOutlined, WalletOutlined } from '@ant-design/icons'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Input,
  Select,
  Space,
  Statistic,
  Table,
  Tabs,
  Tag,
  Typography,
} from 'antd'
import type { TableProps } from 'antd'
import { useState } from 'react'

import { listarAtenciones, type Atencion } from '../api/atenciones'
import { obtenerUsuarioActual } from '../api/auth'
import {
  ETIQUETA_METODO,
  listarPagos,
  listarPagosDoctores,
  obtenerResumenCaja,
  type DiaCaja,
  type MetodoPago,
  type Pago,
  type PagoDoctor,
} from '../api/pagos'
import { listarSedes } from '../api/recursos'
import FormPago from '../componentes/FormPago'
import FormPagoDoctor from '../componentes/FormPagoDoctor'
import { COLOR_ESTADO, ETIQUETA_ESTADO } from '../constantes/atenciones'

const hoyLocal = () => {
  const hoy = new Date()
  const mes = String(hoy.getMonth() + 1).padStart(2, '0')
  const dia = String(hoy.getDate()).padStart(2, '0')
  return `${hoy.getFullYear()}-${mes}-${dia}`
}

const dinero = (valor: string | number | null | undefined) =>
  valor === null || valor === undefined
    ? '—'
    : `L ${Number(valor).toLocaleString('es-HN', { minimumFractionDigits: 2 })}`

const COLOR_METODO: Record<string, string> = {
  efectivo: 'green',
  transferencia: 'blue',
  tarjeta: 'purple',
  otro: 'default',
}

export default function Caja() {
  const [desde, setDesde] = useState(hoyLocal)
  const [hasta, setHasta] = useState(hoyLocal)
  const [sede, setSede] = useState<number | null>(null)
  const [paginaCitas, setPaginaCitas] = useState(1)
  const [paginaPagos, setPaginaPagos] = useState(1)
  const [paginaDoctores, setPaginaDoctores] = useState(1)
  const [formPago, setFormPago] = useState(false)
  const [formDoctor, setFormDoctor] = useState(false)

  const { data: me } = useQuery({ queryKey: ['me'], queryFn: obtenerUsuarioActual })
  const { data: sedes } = useQuery({
    queryKey: ['sedes', 'true'],
    queryFn: () => listarSedes('true'),
    enabled: me?.es_admin === true,
  })

  const { data: resumen, isPending: cargandoResumen } = useQuery({
    queryKey: ['caja', 'resumen', desde, hasta, sede],
    queryFn: () => obtenerResumenCaja({ desde, hasta, sede }),
    enabled: me?.es_admin === true,
  })

  const { data: pagos, isPending: cargandoPagos, isFetching: actualizandoPagos } = useQuery({
    queryKey: ['pagos', paginaPagos, desde, hasta, sede],
    queryFn: () => listarPagos(paginaPagos, { desde, hasta, sede }),
    placeholderData: keepPreviousData,
    enabled: me?.es_admin === true,
  })

  const { data: citas, isPending: cargandoCitas, isFetching: actualizandoCitas } = useQuery({
    queryKey: ['caja', 'atenciones', paginaCitas, desde, hasta, sede],
    queryFn: () =>
      listarAtenciones(paginaCitas, {
        desde,
        hasta,
        sede,
        estado: ['pendiente', 'confirmada', 'completada'],
      }),
    placeholderData: keepPreviousData,
    enabled: me?.es_admin === true,
  })

  const { data: pagosDoctor, isPending: cargandoDoctores, isFetching: actualizandoDoctores } =
    useQuery({
      queryKey: ['pagos-doctores', paginaDoctores, desde, hasta, sede],
      queryFn: () => listarPagosDoctores(paginaDoctores, { desde, hasta, sede }),
      placeholderData: keepPreviousData,
      enabled: me?.es_admin === true,
    })

  if (me && !me.es_admin) {
    return (
      <Alert
        type="error"
        showIcon
        message="Caja y ganancias"
        description="Solo el administrador puede ver o registrar movimientos de dinero."
      />
    )
  }

  const columnasCitas: TableProps<Atencion>['columns'] = [
    { title: 'Fecha', dataIndex: 'fecha', key: 'fecha', width: 110 },
    {
      title: 'Cita',
      key: 'cita',
      render: (_, atencion) => (
        <div>
          <Typography.Text strong>{atencion.paciente_nombre}</Typography.Text>
          <br />
          <Typography.Text type="secondary">
            {atencion.trabajos.length
              ? atencion.trabajos.map((trabajo) => trabajo.tipo_trabajo_nombre).join(' + ')
              : atencion.tipo_trabajo_nombre}
          </Typography.Text>
        </div>
      ),
    },
    { title: 'Sede', dataIndex: 'sede_nombre', key: 'sede', width: 120 },
    { title: 'Doctor', dataIndex: 'doctor_nombre', key: 'doctor', width: 150 },
    {
      title: 'Estado',
      dataIndex: 'estado',
      key: 'estado',
      width: 120,
      render: (estado: Atencion['estado']) => (
        <Tag color={COLOR_ESTADO[estado]}>{ETIQUETA_ESTADO[estado]}</Tag>
      ),
    },
    {
      title: 'Total cita',
      dataIndex: 'precio_paciente',
      key: 'total',
      align: 'right',
      width: 120,
      render: dinero,
    },
    {
      title: 'Abonos',
      dataIndex: 'total_pagado',
      key: 'abonos',
      align: 'right',
      width: 110,
      render: dinero,
    },
    {
      title: 'Pendiente',
      key: 'pendiente',
      align: 'right',
      width: 120,
      render: (_, atencion) =>
        dinero(atencion.estado === 'completada' ? 0 : atencion.saldo_pendiente),
    },
    {
      title: 'Comisión doctor',
      dataIndex: 'honorario_doctor',
      key: 'comision',
      align: 'right',
      width: 140,
      render: dinero,
    },
  ]

  const columnasPagos: TableProps<Pago>['columns'] = [
    { title: 'Fecha', dataIndex: 'fecha', key: 'fecha', width: 110 },
    { title: 'Cita', dataIndex: 'atencion_etiqueta', key: 'cita' },
    { title: 'Sede', dataIndex: 'sede_nombre', key: 'sede', width: 120 },
    {
      title: 'Monto',
      dataIndex: 'monto',
      key: 'monto',
      align: 'right',
      width: 120,
      render: dinero,
    },
    {
      title: 'Método',
      dataIndex: 'metodo',
      key: 'metodo',
      width: 130,
      render: (metodo: MetodoPago) => (
        <Tag color={COLOR_METODO[metodo]}>{ETIQUETA_METODO[metodo]}</Tag>
      ),
    },
    {
      title: 'Registrado por',
      dataIndex: 'registrado_por_nombre',
      key: 'registrado',
      width: 150,
      render: (v: string | null) => v ?? 'Sistema',
    },
    { title: 'Nota', dataIndex: 'nota', key: 'nota', render: (v: string) => v || '—' },
  ]

  const columnasDoctores: TableProps<PagoDoctor>['columns'] = [
    { title: 'Fecha', dataIndex: 'fecha', key: 'fecha', width: 110 },
    { title: 'Doctor', dataIndex: 'doctor_nombre', key: 'doctor', width: 160 },
    { title: 'Cita', dataIndex: 'atencion_etiqueta', key: 'cita' },
    { title: 'Sede', dataIndex: 'sede_nombre', key: 'sede', width: 120 },
    {
      title: 'Monto',
      dataIndex: 'monto',
      key: 'monto',
      align: 'right',
      width: 120,
      render: dinero,
    },
    {
      title: 'Método',
      dataIndex: 'metodo',
      key: 'metodo',
      width: 130,
      render: (metodo: MetodoPago) => (
        <Tag color={COLOR_METODO[metodo]}>{ETIQUETA_METODO[metodo]}</Tag>
      ),
    },
    {
      title: 'Registrado por',
      dataIndex: 'registrado_por_nombre',
      key: 'registrado',
      width: 150,
      render: (v: string | null) => v ?? 'Sistema',
    },
    { title: 'Nota', dataIndex: 'nota', key: 'nota', render: (v: string) => v || '—' },
  ]

  const columnasResumen: TableProps<DiaCaja>['columns'] = [
    { title: 'Fecha', dataIndex: 'fecha', key: 'fecha' },
    {
      title: 'Cobrado',
      dataIndex: 'cobrado',
      key: 'cobrado',
      align: 'right',
      render: dinero,
    },
    {
      title: 'Por cobrar',
      dataIndex: 'por_cobrar',
      key: 'por_cobrar',
      align: 'right',
      render: dinero,
    },
    {
      title: 'Comisión doctores',
      dataIndex: 'comision_doctores',
      key: 'comision',
      align: 'right',
      render: dinero,
    },
    {
      title: 'Ganancia',
      dataIndex: 'ganancia',
      key: 'ganancia',
      align: 'right',
      render: (v: string) => <Typography.Text strong>{dinero(v)}</Typography.Text>,
    },
  ]

  const contenidoCitas = (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={5} style={{ margin: 0 }}>
          Cobros por cita
        </Typography.Title>
        <Typography.Text type="secondary">
          Las citas completadas cuentan como cobradas; las pendientes y confirmadas
          muestran lo que falta por cobrar.
        </Typography.Text>
      </div>
      <Table<Atencion>
        rowKey="id"
        columns={columnasCitas}
        dataSource={citas?.results}
        loading={cargandoCitas || actualizandoCitas}
        scroll={{ x: 1200 }}
        pagination={{
          current: paginaCitas,
          pageSize: 25,
          total: citas?.count,
          onChange: setPaginaCitas,
          showSizeChanger: false,
        }}
        locale={{ emptyText: 'No hay citas en el rango seleccionado.' }}
      />
    </Space>
  )

  const contenidoAbonos = (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
        <div>
          <Typography.Title level={5} style={{ margin: 0 }}>
            Abonos de pacientes
          </Typography.Title>
          <Typography.Text type="secondary">
            {resumen ? `${resumen.cantidad_abonos} abono(s) en el rango` : 'Cargando…'}
          </Typography.Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setFormPago(true)}>
          Registrar abono
        </Button>
      </Space>
      <Table<Pago>
        rowKey="id"
        columns={columnasPagos}
        dataSource={pagos?.results}
        loading={cargandoPagos || actualizandoPagos}
        scroll={{ x: 1100 }}
        pagination={{
          current: paginaPagos,
          pageSize: 25,
          total: pagos?.count,
          onChange: setPaginaPagos,
          showSizeChanger: false,
        }}
        locale={{ emptyText: 'No hay abonos en el rango seleccionado.' }}
      />
    </Space>
  )

  const contenidoDoctores = (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
        <div>
          <Typography.Title level={5} style={{ margin: 0 }}>
            Pagos a doctores
          </Typography.Title>
          <Typography.Text type="secondary">
            {resumen
              ? `${resumen.cantidad_pagos_doctores} pago(s) en el rango`
              : 'Cargando…'}
          </Typography.Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setFormDoctor(true)}>
          Registrar pago
        </Button>
      </Space>
      <Table<PagoDoctor>
        rowKey="id"
        columns={columnasDoctores}
        dataSource={pagosDoctor?.results}
        loading={cargandoDoctores || actualizandoDoctores}
        scroll={{ x: 1200 }}
        pagination={{
          current: paginaDoctores,
          pageSize: 25,
          total: pagosDoctor?.count,
          onChange: setPaginaDoctores,
          showSizeChanger: false,
        }}
        locale={{ emptyText: 'No hay pagos a doctores en el rango seleccionado.' }}
      />
    </Space>
  )

  const contenidoResumen = (
    <Space direction="vertical" size="middle" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={5} style={{ margin: 0 }}>
          Resumen por día
        </Typography.Title>
        <Typography.Text type="secondary">
          Cobros por cita completada, pendientes y comisiones en el rango seleccionado.
        </Typography.Text>
      </div>
      <Table
        rowKey="fecha"
        columns={columnasResumen}
        dataSource={resumen?.por_dia}
        loading={cargandoResumen}
        pagination={false}
        locale={{ emptyText: 'No hay movimientos en el rango seleccionado.' }}
      />
    </Space>
  )

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Caja y ganancias
        </Typography.Title>
        <Typography.Text type="secondary">
          Cobros por cita completada, comisiones de doctores y abonos reales. Solo
          administrador.
        </Typography.Text>
      </div>

      <Card>
        <Space wrap size="middle">
          <Input
            type="date"
            value={desde}
            max={hasta || undefined}
            onChange={(e) => {
              setDesde(e.target.value)
              setPaginaCitas(1)
              setPaginaPagos(1)
              setPaginaDoctores(1)
            }}
            style={{ width: 160 }}
          />
          <Input
            type="date"
            value={hasta}
            min={desde || undefined}
            onChange={(e) => {
              setHasta(e.target.value)
              setPaginaCitas(1)
              setPaginaPagos(1)
              setPaginaDoctores(1)
            }}
            style={{ width: 160 }}
          />
          <Button
            onClick={() => {
              const hoy = hoyLocal()
              setDesde(hoy)
              setHasta(hoy)
              setPaginaCitas(1)
              setPaginaPagos(1)
              setPaginaDoctores(1)
            }}
          >
            Hoy
          </Button>
          <Select
            allowClear
            placeholder="Todas las sedes"
            style={{ width: 200 }}
            value={sede}
            onChange={(v) => {
              setSede(v ?? null)
              setPaginaCitas(1)
              setPaginaPagos(1)
              setPaginaDoctores(1)
            }}
            options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
          />
        </Space>
      </Card>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(190px, 1fr))',
          gap: 16,
        }}
      >
        <Card>
          <Statistic
            title="Cobrado"
            value={Number(resumen?.cobrado ?? 0)}
            precision={2}
            prefix={<DollarOutlined />}
            suffix="L"
            loading={cargandoResumen}
          />
        </Card>
        <Card>
          <Statistic
            title="Por cobrar"
            value={Number(resumen?.por_cobrar ?? 0)}
            precision={2}
            prefix={<DollarOutlined />}
            suffix="L"
            loading={cargandoResumen}
          />
        </Card>
        <Card>
          <Statistic
            title="Comisión doctores"
            value={Number(resumen?.comision_doctores ?? 0)}
            precision={2}
            prefix={<WalletOutlined />}
            suffix="L"
            loading={cargandoResumen}
          />
        </Card>
        <Card>
          <Statistic
            title="Ganancia neta"
            value={Number(resumen?.ganancia ?? 0)}
            precision={2}
            prefix={<RiseOutlined />}
            suffix="L"
            loading={cargandoResumen}
          />
        </Card>
      </div>
      <Typography.Text type="secondary">
        Abonos registrados en caja: {dinero(resumen?.abonos_caja)} · Pagado a doctores: {dinero(resumen?.pagado_doctores)}
      </Typography.Text>

      <Card>
        <Tabs
          items={[
            { key: 'citas', label: 'Cobros por cita', children: contenidoCitas },
            { key: 'abonos', label: 'Abonos', children: contenidoAbonos },
            { key: 'doctores', label: 'Pagos a doctores', children: contenidoDoctores },
            { key: 'resumen', label: 'Resumen', children: contenidoResumen },
          ]}
        />
      </Card>

      <FormPago abierto={formPago} onCerrar={() => setFormPago(false)} />
      <FormPagoDoctor abierto={formDoctor} onCerrar={() => setFormDoctor(false)} />
    </Space>
  )
}
