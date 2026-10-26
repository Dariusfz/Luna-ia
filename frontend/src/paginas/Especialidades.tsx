import { EditOutlined, PlusOutlined } from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Popconfirm, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { TableProps } from 'antd'
import { useState } from 'react'

import { obtenerUsuarioActual } from '../api/auth'
import { actualizarEspecialidad, listarEspecialidades, type Especialidad } from '../api/catalogos'
import { ApiError } from '../api/cliente'
import type { FiltroActivo } from '../api/recursos'
import FormEspecialidad from '../componentes/FormEspecialidad'

/** Catálogo de especialidades que se eligen al registrar un doctor. */
export default function Especialidades() {
  const cliente = useQueryClient()
  const [activo, setActivo] = useState<FiltroActivo>('todos')
  const [formAbierto, setFormAbierto] = useState(false)
  const [editando, setEditando] = useState<Especialidad | null>(null)

  const { data, isPending } = useQuery({
    queryKey: ['especialidades', activo],
    queryFn: () => listarEspecialidades(activo),
    placeholderData: keepPreviousData,
  })

  const { data: me } = useQuery({ queryKey: ['me'], queryFn: obtenerUsuarioActual })
  const esAdmin = me?.es_admin ?? false

  const cambiarEstado = useMutation({
    mutationFn: ({ id, activo: nuevo }: { id: number; activo: boolean }) =>
      actualizarEspecialidad(id, { activo: nuevo }),
    onSuccess: (_, { activo: nuevo }) => {
      message.success(nuevo ? 'Especialidad activada' : 'Especialidad desactivada')
      cliente.invalidateQueries({ queryKey: ['especialidades'] })
    },
    onError: (e) => message.error(e instanceof ApiError ? e.message : 'No se pudo cambiar el estado.'),
  })

  const columnas: TableProps<Especialidad>['columns'] = [
    { title: 'Nombre', dataIndex: 'nombre', key: 'nombre' },
    {
      title: 'Estado',
      dataIndex: 'activo',
      key: 'estado',
      render: (v: boolean) => (v ? <Tag color="success">Activa</Tag> : <Tag>Inactiva</Tag>),
    },
    ...(esAdmin
      ? [
          {
            title: 'Acciones',
            key: 'acciones',
            render: (_: unknown, e: Especialidad) => (
              <Space>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => {
                    setEditando(e)
                    setFormAbierto(true)
                  }}
                >
                  Editar
                </Button>
                {e.activo ? (
                  <Popconfirm
                    title="¿Desactivar especialidad?"
                    description="Ya no se podrá asignar a doctores nuevos. Los doctores actuales la conservan."
                    okText="Desactivar"
                    okButtonProps={{ danger: true }}
                    cancelText="Cancelar"
                    onConfirm={() => cambiarEstado.mutate({ id: e.id, activo: false })}
                  >
                    <Button size="small" danger>
                      Desactivar
                    </Button>
                  </Popconfirm>
                ) : (
                  <Button size="small" onClick={() => cambiarEstado.mutate({ id: e.id, activo: true })}>
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
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            Especialidades
          </Typography.Title>
          <Typography.Text type="secondary">
            Se eligen al registrar cada doctor.
          </Typography.Text>
        </div>
        <Space>
          <Select<FiltroActivo>
            style={{ width: 150 }}
            value={activo}
            onChange={setActivo}
            options={[
              { value: 'todos', label: 'Todas' },
              { value: 'true', label: 'Activas' },
              { value: 'false', label: 'Inactivas' },
            ]}
          />
          {esAdmin && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditando(null)
                setFormAbierto(true)
              }}
            >
              Nueva especialidad
            </Button>
          )}
        </Space>
      </Space>

      {esAdmin && (
        <FormEspecialidad abierto={formAbierto} especialidad={editando} onCerrar={() => setFormAbierto(false)} />
      )}
      <Table<Especialidad>
        rowKey="id"
        columns={columnas}
        dataSource={data?.results}
        loading={isPending}
        pagination={false}
        locale={{ emptyText: 'Aún no hay especialidades. Crea la primera con "Nueva especialidad".' }}
      />
    </Card>
  )
}
