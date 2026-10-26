import { EditOutlined, PlusOutlined } from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Popconfirm, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { TableProps } from 'antd'
import { useState } from 'react'

import { obtenerUsuarioActual } from '../api/auth'
import { actualizarTipoTrabajo, listarTiposTrabajo, type TipoTrabajo } from '../api/catalogos'
import { ApiError } from '../api/cliente'
import type { FiltroActivo } from '../api/recursos'
import FormTipoTrabajo from '../componentes/FormTipoTrabajo'

export default function TiposTrabajo() {
  const cliente = useQueryClient()
  const [activo, setActivo] = useState<FiltroActivo>('todos')
  const [formAbierto, setFormAbierto] = useState(false)
  const [editando, setEditando] = useState<TipoTrabajo | null>(null)

  const { data, isPending } = useQuery({
    queryKey: ['tipos-trabajo', activo],
    queryFn: () => listarTiposTrabajo(activo),
    placeholderData: keepPreviousData,
  })

  const { data: me } = useQuery({ queryKey: ['me'], queryFn: obtenerUsuarioActual })
  const esAdmin = me?.es_admin ?? false

  const cambiarEstado = useMutation({
    mutationFn: ({ id, activo: nuevo }: { id: number; activo: boolean }) => actualizarTipoTrabajo(id, { activo: nuevo }),
    onSuccess: (_, { activo: nuevo }) => {
      message.success(nuevo ? 'Tipo activado' : 'Tipo desactivado')
      cliente.invalidateQueries({ queryKey: ['tipos-trabajo'] })
    },
    onError: (e) => message.error(e instanceof ApiError ? e.message : 'No se pudo cambiar el estado.'),
  })

  const columnas: TableProps<TipoTrabajo>['columns'] = [
    { title: 'Nombre', dataIndex: 'nombre', key: 'nombre' },
    { title: 'Descripción', dataIndex: 'descripcion', key: 'desc', render: (v: string) => v || '-' },
    {
      title: 'Precio',
      dataIndex: 'precio',
      key: 'precio',
      align: 'right',
      render: (v: string) => `L ${Number(v).toLocaleString('es-HN', { minimumFractionDigits: 2 })}`,
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
            render: (_: unknown, t: TipoTrabajo) => (
              <Space>
                <Button
                  size="small"
                  icon={<EditOutlined />}
                  onClick={() => {
                    setEditando(t)
                    setFormAbierto(true)
                  }}
                >
                  Editar
                </Button>
                {t.activo ? (
                  <Popconfirm
                    title="¿Desactivar este tipo?"
                    description="Ya no aparecerá al registrar nuevos trabajos. El historial se conserva."
                    okText="Desactivar"
                    okButtonProps={{ danger: true }}
                    cancelText="Cancelar"
                    onConfirm={() => cambiarEstado.mutate({ id: t.id, activo: false })}
                  >
                    <Button size="small" danger>
                      Desactivar
                    </Button>
                  </Popconfirm>
                ) : (
                  <Button size="small" onClick={() => cambiarEstado.mutate({ id: t.id, activo: true })}>
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
            Tipos de trabajo
          </Typography.Title>
          <Typography.Text type="secondary">
            Catálogo de procedimientos usado al registrar atenciones y jornadas externas.
          </Typography.Text>
        </div>
        <Space>
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
          {esAdmin && (
            <Button
              type="primary"
              icon={<PlusOutlined />}
              onClick={() => {
                setEditando(null)
                setFormAbierto(true)
              }}
            >
              Nuevo tipo
            </Button>
          )}
        </Space>
      </Space>

      {esAdmin && <FormTipoTrabajo abierto={formAbierto} tipo={editando} onCerrar={() => setFormAbierto(false)} />}
      <Table<TipoTrabajo>
        rowKey="id"
        columns={columnas}
        dataSource={data?.results}
        loading={isPending}
        pagination={false}
        locale={{ emptyText: 'Aún no hay tipos de trabajo.' }}
      />
    </Card>
  )
}
