import { EditOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Input, Popconfirm, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { TableProps } from 'antd'
import { useEffect, useMemo, useState } from 'react'

import { obtenerUsuarioActual } from '../api/auth'
import { actualizarDoctor, listarDoctores, type Doctor, type FiltrosDoctores, type TipoDoctor } from '../api/catalogos'
import { ApiError } from '../api/cliente'
import { listarSedes, type FiltroActivo } from '../api/recursos'
import FormDoctor from '../componentes/FormDoctor'

const etiquetaTipo: Record<TipoDoctor, string> = {
  propio: 'Interno',
  contratado: 'Por sesión',
}

export default function Doctores() {
  const cliente = useQueryClient()
  const [pagina, setPagina] = useState(1)
  const [texto, setTexto] = useState('')
  const [q, setQ] = useState('')
  const [tipo, setTipo] = useState<TipoDoctor | null>(null)
  const [sede, setSede] = useState<number | null>(null)
  const [activo, setActivo] = useState<FiltroActivo>('todos')
  const [formAbierto, setFormAbierto] = useState(false)
  const [editando, setEditando] = useState<Doctor | null>(null)

  useEffect(() => {
    const espera = setTimeout(() => setQ(texto.trim()), 300)
    return () => clearTimeout(espera)
  }, [texto])

  useEffect(() => setPagina(1), [q, tipo, sede, activo])

  const filtros: FiltrosDoctores = useMemo(() => ({ q, tipo, sede, activo }), [q, tipo, sede, activo])

  const { data, isPending, isFetching } = useQuery({
    queryKey: ['doctores', pagina, filtros],
    queryFn: () => listarDoctores(pagina, filtros),
    placeholderData: keepPreviousData,
  })

  const { data: sedes } = useQuery({ queryKey: ['sedes', 'todas'], queryFn: () => listarSedes('todas') })
  const { data: me } = useQuery({ queryKey: ['me'], queryFn: obtenerUsuarioActual })
  const esAdmin = me?.es_admin ?? false

  const nombreSede = useMemo(() => {
    const mapa = new Map<number, string>()
    sedes?.results.forEach((s) => mapa.set(s.id, s.nombre))
    return (id: number) => mapa.get(id) ?? `Sede ${id}`
  }, [sedes])

  const cambiarEstado = useMutation({
    mutationFn: ({ id, activo: nuevo }: { id: number; activo: boolean }) => actualizarDoctor(id, { activo: nuevo }),
    onSuccess: (_, { activo: nuevo }) => {
      message.success(nuevo ? 'Doctor activado' : 'Doctor desactivado')
      cliente.invalidateQueries({ queryKey: ['doctores'] })
    },
    onError: (e) => message.error(e instanceof ApiError ? e.message : 'No se pudo cambiar el estado.'),
  })

  const columnas: TableProps<Doctor>['columns'] = [
    { title: 'Nombre', key: 'nombre', render: (_, d) => `Dr(a). ${d.nombres} ${d.apellidos}` },
    { title: 'Tipo', dataIndex: 'tipo', key: 'tipo', render: (t: TipoDoctor) => <Tag>{etiquetaTipo[t]}</Tag> },
    {
      title: 'Especialidades',
      dataIndex: 'especialidades_nombres',
      key: 'esp',
      render: (nombres: string[]) =>
        nombres.length ? nombres.map((nombre) => <Tag key={nombre}>{nombre}</Tag>) : '-',
    },
    { title: 'Teléfono', dataIndex: 'telefono', key: 'tel', render: (v: string) => v || '-' },
    {
      title: 'Sedes',
      key: 'sedes',
      render: (_, d) => d.sedes.map((id) => <Tag key={id}>{nombreSede(id)}</Tag>),
    },
    {
      title: 'Estado',
      dataIndex: 'activo',
      key: 'estado',
      render: (v: boolean) => (v ? <Tag color="success">Activo</Tag> : <Tag>Inactivo</Tag>),
    },
    ...(esAdmin
      ? [
          {
            title: 'Acciones',
            key: 'acciones',
            render: (_: unknown, d: Doctor) => (
              <Space>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => {
                    setEditando(d)
                    setFormAbierto(true)
                  }}
                >
                  Editar
                </Button>
                {d.activo ? (
                  <Popconfirm
                    title="¿Desactivar doctor?"
                    description="No podrá registrar nuevas atenciones. Su historial se conserva."
                    okText="Desactivar"
                    okButtonProps={{ danger: true }}
                    cancelText="Cancelar"
                    onConfirm={() => cambiarEstado.mutate({ id: d.id, activo: false })}
                  >
                    <Button size="small" danger>
                      Desactivar
                    </Button>
                  </Popconfirm>
                ) : (
                  <Button size="small" onClick={() => cambiarEstado.mutate({ id: d.id, activo: true })}>
                    Activar
                  </Button>
                )}
              </Space>
            ),
          },
        ]
      : []),
  ]

  return (
    <Card>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Doctores
        </Typography.Title>
        {esAdmin && (
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={() => {
              setEditando(null)
              setFormAbierto(true)
            }}
          >
            Nuevo doctor
          </Button>
        )}
      </Space>

      <Space wrap style={{ marginBottom: 16 }}>
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="Buscar por nombre o especialidad"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          style={{ width: 300 }}
        />
        <Select
          allowClear
          placeholder="Todos los tipos"
          style={{ width: 180 }}
          value={tipo}
          onChange={(v) => setTipo(v ?? null)}
          options={[
            { value: 'propio', label: 'Interno' },
            { value: 'contratado', label: 'Por sesión' },
          ]}
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
          style={{ width: 150 }}
          value={activo}
          onChange={setActivo}
          options={[
            { value: 'todos', label: 'Todos' },
            { value: 'true', label: 'Activos' },
            { value: 'false', label: 'Inactivos' },
          ]}
        />
      </Space>

      {esAdmin && <FormDoctor abierto={formAbierto} doctor={editando} onCerrar={() => setFormAbierto(false)} />}
      <Table<Doctor>
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
        locale={{ emptyText: 'No hay doctores con estos filtros.' }}
      />
    </Card>
  )
}
