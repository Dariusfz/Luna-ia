import {
  CalendarOutlined,
  EditOutlined,
  PlusOutlined,
  StopOutlined,
} from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Button,
  Card,
  Input,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import { useEffect, useMemo, useState } from 'react'

import { ApiError } from '../api/cliente'
import { listarDoctores } from '../api/catalogos'
import {
  actualizarEspera,
  listarListaEspera,
  type FiltrosListaEspera,
  type ListaEspera as Espera,
} from '../api/listaEspera'
import { listarSedes } from '../api/recursos'
import FormAgendarEspera from '../componentes/FormAgendarEspera'
import FormEspera from '../componentes/FormEspera'
import {
  COLOR_ESPERA,
  COLOR_PRIORIDAD,
  ESTADOS_ESPERA,
  ETIQUETA_ESPERA,
  ETIQUETA_PRIORIDAD,
  PRIORIDADES_ESPERA,
  type EstadoEspera,
  type PrioridadEspera,
} from '../constantes/listaEspera'

const fecha = (valor: string | null) =>
  valor ? new Date(`${valor}T00:00:00`).toLocaleDateString('es-HN') : '—'

const hora = (valor: string | null) => (valor ? valor.slice(0, 5) : '')

export default function ListaEspera() {
  const cliente = useQueryClient()
  const [pagina, setPagina] = useState(1)
  const [sede, setSede] = useState<number | null>(null)
  const [doctor, setDoctor] = useState<number | null>(null)
  const [estados, setEstados] = useState<EstadoEspera[]>(['esperando', 'contactado'])
  const [prioridad, setPrioridad] = useState<PrioridadEspera | null>(null)
  const [q, setQ] = useState('')
  const [formAbierto, setFormAbierto] = useState(false)
  const [editando, setEditando] = useState<Espera | null>(null)
  const [agendando, setAgendando] = useState<Espera | null>(null)

  useEffect(() => setPagina(1), [sede, doctor, estados, prioridad, q])

  const filtros: FiltrosListaEspera = useMemo(
    () => ({ sede, doctor, estado: estados, prioridad, q: q.trim() || undefined }),
    [sede, doctor, estados, prioridad, q],
  )

  const { data, isPending, isFetching } = useQuery({
    queryKey: ['lista-espera', pagina, filtros],
    queryFn: () => listarListaEspera(pagina, filtros),
    placeholderData: keepPreviousData,
  })

  const { data: sedes } = useQuery({
    queryKey: ['sedes', 'todas'],
    queryFn: () => listarSedes('todas'),
  })
  const { data: doctores } = useQuery({
    queryKey: ['doctores', 'filtro-espera'],
    queryFn: () => listarDoctores(1, { activo: 'todos' }),
  })

  const cancelar = useMutation({
    mutationFn: (id: number) => actualizarEspera(id, { estado: 'cancelado' }),
    onSuccess: () => {
      message.success('Espera cancelada')
      cliente.invalidateQueries({ queryKey: ['lista-espera'] })
      cliente.invalidateQueries({ queryKey: ['dashboard'] })
    },
    onError: (e) => {
      message.error(e instanceof ApiError ? e.message : 'No se pudo cancelar la espera.')
    },
  })

  const columnas: TableProps<Espera>['columns'] = [
    {
      title: 'Prioridad',
      dataIndex: 'prioridad',
      key: 'prioridad',
      width: 100,
      render: (valor: PrioridadEspera) => (
        <Tag color={COLOR_PRIORIDAD[valor]}>{ETIQUETA_PRIORIDAD[valor]}</Tag>
      ),
    },
    {
      title: 'Estado',
      dataIndex: 'estado',
      key: 'estado',
      width: 120,
      render: (valor: EstadoEspera) => (
        <Tag color={COLOR_ESPERA[valor]}>{ETIQUETA_ESPERA[valor]}</Tag>
      ),
    },
    { title: 'Paciente', dataIndex: 'paciente_nombre', key: 'paciente' },
    { title: 'Sede', dataIndex: 'sede_nombre', key: 'sede' },
    {
      title: 'Doctor preferido',
      key: 'doctor',
      render: (_, espera) => espera.doctor_nombre ?? '—',
    },
    {
      title: 'Tipo de trabajo',
      key: 'tipo',
      render: (_, espera) => espera.tipo_trabajo_nombre ?? '—',
    },
    {
      title: 'Fecha deseada',
      dataIndex: 'fecha_deseada',
      key: 'fecha_deseada',
      render: (valor: string | null) => fecha(valor),
    },
    {
      title: 'Cita',
      key: 'cita',
      render: (_, espera) =>
        espera.atencion_fecha
          ? `${fecha(espera.atencion_fecha)} ${hora(espera.atencion_hora_inicio)}`
          : '—',
    },
    { title: 'Motivo', dataIndex: 'motivo', key: 'motivo' },
    {
      title: '',
      key: 'acciones',
      render: (_, espera) => (
        <Space size={4}>
          {espera.estado !== 'agendado' && espera.estado !== 'cancelado' && (
            <Button
              size="small"
              type="primary"
              icon={<CalendarOutlined />}
              onClick={() => setAgendando(espera)}
            >
              Agendar
            </Button>
          )}
          <Button
            size="small"
            icon={<EditOutlined />}
            onClick={() => {
              setEditando(espera)
              setFormAbierto(true)
            }}
          >
            Editar
          </Button>
          {espera.estado !== 'agendado' && espera.estado !== 'cancelado' && (
            <Popconfirm
              title="¿Cancelar esta espera?"
              okText="Cancelar espera"
              cancelText="Volver"
              onConfirm={() => cancelar.mutate(espera.id)}
            >
              <Button size="small" danger icon={<StopOutlined />}>
                Cancelar
              </Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} wrap>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            Lista de espera
          </Typography.Title>
          <Typography.Text type="secondary">
            Pacientes que esperan un cupo. Al agendar se crea la cita con las mismas validaciones de
            la agenda.
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
          Nuevo en espera
        </Button>
      </Space>

      <Space wrap style={{ marginBottom: 16 }}>
        <Select
          allowClear
          placeholder="Todas las sedes"
          style={{ width: 190 }}
          value={sede}
          onChange={(v) => setSede(v ?? null)}
          options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
        />
        <Select
          allowClear
          showSearch
          optionFilterProp="label"
          placeholder="Todos los doctores"
          style={{ width: 210 }}
          value={doctor}
          onChange={(v) => setDoctor(v ?? null)}
          options={doctores?.results.map((d) => ({
            value: d.id,
            label: `${d.nombres} ${d.apellidos}`,
          }))}
        />
        <Select<EstadoEspera[]>
          mode="multiple"
          allowClear
          placeholder="Estados"
          style={{ minWidth: 230 }}
          value={estados}
          onChange={setEstados}
          options={ESTADOS_ESPERA.map((estado) => ({
            value: estado,
            label: ETIQUETA_ESPERA[estado],
          }))}
        />
        <Select
          allowClear
          placeholder="Todas las prioridades"
          style={{ width: 180 }}
          value={prioridad}
          onChange={(v) => setPrioridad(v ?? null)}
          options={PRIORIDADES_ESPERA.map((p) => ({
            value: p,
            label: ETIQUETA_PRIORIDAD[p],
          }))}
        />
        <Input.Search
          allowClear
          placeholder="Buscar paciente o motivo"
          style={{ width: 240 }}
          onSearch={(valor) => setQ(valor)}
        />
      </Space>

      <FormEspera
        abierto={formAbierto}
        espera={editando}
        onCerrar={() => setFormAbierto(false)}
      />
      <FormAgendarEspera
        abierto={agendando !== null}
        espera={agendando}
        onCerrar={() => setAgendando(null)}
      />
      <Table<Espera>
        rowKey="id"
        columns={columnas}
        dataSource={data?.results}
        loading={isPending || isFetching}
        scroll={{ x: 1100 }}
        pagination={{
          current: pagina,
          pageSize: 25,
          total: data?.count ?? 0,
          showSizeChanger: false,
          onChange: setPagina,
        }}
        locale={{ emptyText: 'No hay pacientes en lista de espera con estos filtros.' }}
      />
    </Card>
  )
}
