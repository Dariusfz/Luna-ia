import { EditOutlined, PlusOutlined } from '@ant-design/icons'
import { keepPreviousData, useQuery } from '@tanstack/react-query'
import { Button, Card, DatePicker, Select, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useEffect, useMemo, useState } from 'react'

import { listarAtenciones, type Atencion, type FiltrosAtenciones } from '../api/atenciones'
import { listarDoctores } from '../api/catalogos'
import { listarSedes } from '../api/recursos'
import FormAtencion from '../componentes/FormAtencion'
import { COLOR_ESTADO, ETIQUETA_ESTADO, ESTADOS_ATENCION, type EstadoAtencion } from '../constantes/atenciones'

const formatoLempiras = (v: string) => `L ${Number(v).toLocaleString('es-HN', { minimumFractionDigits: 2 })}`

export default function Atenciones() {
  const [pagina, setPagina] = useState(1)
  const [sede, setSede] = useState<number | null>(null)
  const [doctor, setDoctor] = useState<number | null>(null)
  const [estado, setEstado] = useState<EstadoAtencion | null>(null)
  const [desde, setDesde] = useState<string>('')
  const [hasta, setHasta] = useState<string>('')
  const [formAbierto, setFormAbierto] = useState(false)
  const [editando, setEditando] = useState<Atencion | null>(null)

  useEffect(() => setPagina(1), [sede, doctor, estado, desde, hasta])

  const filtros: FiltrosAtenciones = useMemo(
    () => ({ sede, doctor, estado, desde, hasta }),
    [sede, doctor, estado, desde, hasta],
  )

  const { data, isPending, isFetching } = useQuery({
    queryKey: ['atenciones', pagina, filtros],
    queryFn: () => listarAtenciones(pagina, filtros),
    placeholderData: keepPreviousData,
  })

  const { data: sedes } = useQuery({ queryKey: ['sedes', 'todas'], queryFn: () => listarSedes('todas') })
  const { data: doctores } = useQuery({
    queryKey: ['doctores', 'filtro-atenciones'],
    queryFn: () => listarDoctores(1, { activo: 'todos' }),
  })

  const columnas: TableProps<Atencion>['columns'] = [
    { title: 'Fecha', dataIndex: 'fecha', key: 'fecha', render: (v: string) => new Date(`${v}T00:00:00`).toLocaleDateString('es-HN') },
    { title: 'Horario', key: 'horario', render: (_, a) => `${a.hora_inicio.slice(0, 5)} - ${a.hora_fin.slice(0, 5)}` },
    {
      title: 'Estado',
      dataIndex: 'estado',
      key: 'estado',
      render: (e: EstadoAtencion) => <Tag color={COLOR_ESTADO[e]}>{ETIQUETA_ESTADO[e]}</Tag>,
    },
    { title: 'Paciente', dataIndex: 'paciente_nombre', key: 'paciente' },
    {
      title: 'Doctor',
      key: 'doctor',
      render: (_, a) => (
        <Space size={4}>
          {a.doctor_nombre}
          <Tag>{a.doctor_tipo === 'propio' ? 'Interno' : 'Por sesión'}</Tag>
        </Space>
      ),
    },
    { title: 'Sede', dataIndex: 'sede_nombre', key: 'sede' },
    { title: 'Tipo de trabajo', dataIndex: 'tipo_trabajo_nombre', key: 'tipo' },
    {
      title: 'Honorario',
      dataIndex: 'honorario_doctor',
      key: 'honorario',
      align: 'right',
      render: formatoLempiras,
    },
    {
      title: '',
      key: 'acciones',
      render: (_, a) => (
        <Button
          size="small"
          icon={<EditOutlined />}
          onClick={() => {
            setEditando(a)
            setFormAbierto(true)
          }}
        >
          Editar
        </Button>
      ),
    },
  ]

  return (
    <Card>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} wrap>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            Atenciones y citas
          </Typography.Title>
          <Typography.Text type="secondary">
            Agenda de citas y registro de las atenciones realizadas.
          </Typography.Text>
        </div>
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={() => {
            setEditando(null)
            setFormAbierto(true)
          }}
        >
          Nueva cita
        </Button>
      </Space>

      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="Todas las sedes"
          style={{ width: 200 }}
          value={sede}
          onChange={(v) => setSede(v ?? null)}
          options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="Todos los doctores"
          style={{ width: 220 }}
          value={doctor}
          onChange={(v) => setDoctor(v ?? null)}
          options={doctores?.results.map((d) => ({ value: d.id, label: `${d.nombres} ${d.apellidos}` }))}
        />
        <Select
          allowClear
          placeholder="Todos los estados"
          style={{ width: 180 }}
          value={estado}
          onChange={(v) => setEstado(v ?? null)}
          options={ESTADOS_ATENCION.map((e) => ({ value: e, label: ETIQUETA_ESTADO[e] }))}
        />
        <DatePicker
          placeholder="Desde"
          onChange={(_, texto) => setDesde(typeof texto === 'string' ? texto : '')}
        />
        <DatePicker
          placeholder="Hasta"
          onChange={(_, texto) => setHasta(typeof texto === 'string' ? texto : '')}
        />
      </Space>

      <FormAtencion abierto={formAbierto} atencion={editando} onCerrar={() => setFormAbierto(false)} />
      <Table<Atencion>
        rowKey="id"
        columns={columnas}
        dataSource={data?.results}
        loading={isPending || isFetching}
        pagination={{
          current: pagina,
          pageSize: 25,
          total: data?.count ?? 0,
          showSizeChanger: false,
          onChange: setPagina,
        }}
        locale={{ emptyText: 'No hay citas ni atenciones con estos filtros.' }}
      />
    </Card>
  )
}
