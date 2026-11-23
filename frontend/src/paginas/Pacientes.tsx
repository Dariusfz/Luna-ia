import { EditOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Input, Popconfirm, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { TableProps } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import FormPaciente from '../componentes/FormPaciente'
import { ApiError } from '../api/cliente'
import {
  actualizarPaciente,
  listarPacientes,
  listarSedes,
  type FiltroActivo,
  type Paciente,
} from '../api/recursos'

const TAMANO_PAGINA = 25

export default function Pacientes() {
  const cliente = useQueryClient()
  const navegar = useNavigate()
  const [pagina, setPagina] = useState(1)
  const [texto, setTexto] = useState('')
  const [q, setQ] = useState('')
  const [sede, setSede] = useState<number | null>(null)
  const [activo, setActivo] = useState<FiltroActivo>('true')
  const [formAbierto, setFormAbierto] = useState(false)
  const [editando, setEditando] = useState<Paciente | null>(null)

  // Espera 300 ms tras escribir antes de consultar la API.
  useEffect(() => {
    const espera = setTimeout(() => setQ(texto.trim()), 300)
    return () => clearTimeout(espera)
  }, [texto])

  // Cualquier cambio de filtro vuelve a la primera página.
  useEffect(() => setPagina(1), [q, sede, activo])

  const filtros = useMemo(() => ({ q, sede, activo }), [q, sede, activo])

  const { data, isPending, isFetching } = useQuery({
    queryKey: ['pacientes', pagina, filtros],
    queryFn: () => listarPacientes(pagina, filtros),
    placeholderData: keepPreviousData,
  })

  const { data: sedes } = useQuery({ queryKey: ['sedes', 'todas'], queryFn: () => listarSedes('todas') })

  const nombreSede = useMemo(() => {
    const mapa = new Map<number, string>()
    sedes?.results.forEach((s) => mapa.set(s.id, s.nombre))
    return (id: number | null) => (id ? (mapa.get(id) ?? '-') : '-')
  }, [sedes])

  // Activar o desactivar: los pacientes no se borran.
  const cambiarEstado = useMutation({
    mutationFn: ({ id, activo: nuevo }: { id: number; activo: boolean }) =>
      actualizarPaciente(id, { activo: nuevo }),
    onSuccess: (_, { activo: nuevo }) => {
      message.success(nuevo ? 'Paciente activado' : 'Paciente desactivado')
      cliente.invalidateQueries({ queryKey: ['pacientes'] })
    },
    onError: (e) => message.error(e instanceof ApiError ? e.message : 'No se pudo cambiar el estado.'),
  })

  function nuevo() {
    setEditando(null)
    setFormAbierto(true)
  }

  function editar(paciente: Paciente) {
    setEditando(paciente)
    setFormAbierto(true)
  }

  const columnas: TableProps<Paciente>['columns'] = [
    {
      title: 'Nombre',
      key: 'nombre',
      render: (_, p) => `${p.nombres} ${p.apellidos}`,
    },
    { title: 'Identidad', dataIndex: 'identidad', key: 'identidad', render: (v: string) => v || '-' },
    { title: 'Teléfono', dataIndex: 'telefono', key: 'telefono', render: (v: string) => v || '-' },
    {
      title: 'Sede de origen',
      dataIndex: 'sede_origen',
      key: 'sede',
      render: (id: number | null) => nombreSede(id),
    },
    {
      title: 'Estado',
      dataIndex: 'activo',
      key: 'estado',
      render: (v: boolean) => (v ? <Tag color="success">Activo</Tag> : <Tag>Inactivo</Tag>),
    },
    {
      title: 'Acciones',
      key: 'acciones',
      render: (_, p) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => editar(p)}>
            Editar
          </Button>
          <Button size="small" onClick={() => navegar(`/historia-clinica?paciente=${p.id}`)}>
            Historia
          </Button>
          {p.activo ? (
            <Popconfirm
              title="¿Desactivar paciente?"
              description="No se borra su historial. Dejará de aparecer en el listado de activos."
              okText="Desactivar"
              okButtonProps={{ danger: true }}
              cancelText="Cancelar"
              onConfirm={() => cambiarEstado.mutate({ id: p.id, activo: false })}
            >
              <Button size="small" danger>
                Desactivar
              </Button>
            </Popconfirm>
          ) : (
            <Button size="small" onClick={() => cambiarEstado.mutate({ id: p.id, activo: true })}>
              Activar
            </Button>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Card>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Pacientes
        </Typography.Title>
        <Button type="primary" icon={<PlusOutlined />} onClick={nuevo}>
          Nuevo paciente
        </Button>
      </Space>

      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="Buscar por nombre, identidad o teléfono"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          style={{ width: 320 }}
        />
        <Select
          allowClear
          placeholder="Todas las sedes"
          style={{ width: 200 }}
          value={sede}
          onChange={(v) => setSede(v ?? null)}
          options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
        />
        <Select<FiltroActivo>
          style={{ width: 160 }}
          value={activo}
          onChange={setActivo}
          options={[
            { value: 'true', label: 'Activos' },
            { value: 'false', label: 'Inactivos' },
            { value: 'todos', label: 'Todos' },
          ]}
        />
      </Space>

      <FormPaciente abierto={formAbierto} paciente={editando} onCerrar={() => setFormAbierto(false)} />
      <Table<Paciente>
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
        locale={{ emptyText: 'No hay pacientes con estos filtros.' }}
      />
    </Card>
  )
}
