import { EditOutlined, PlusOutlined } from '@ant-design/icons'
import { useQuery } from '@tanstack/react-query'
import { Button, Card, Select, Space, Table, Tag, Typography } from 'antd'
import type { TableProps } from 'antd'
import { useState } from 'react'

import FormSede from '../componentes/FormSede'
import { listarSedes, type FiltroSedeActiva, type Sede } from '../api/recursos'

/** Solo el administrador ve esta página en el menú (la API también lo restringe). */
export default function Sedes() {
  const [abierto, setAbierto] = useState(false)
  const [editando, setEditando] = useState<Sede | null>(null)
  const [estado, setEstado] = useState<FiltroSedeActiva>('todas')

  const { data, isPending } = useQuery({
    queryKey: ['sedes', estado],
    queryFn: () => listarSedes(estado),
  })

  function nueva() {
    setEditando(null)
    setAbierto(true)
  }

  function editar(sede: Sede) {
    setEditando(sede)
    setAbierto(true)
  }

  const columnas: TableProps<Sede>['columns'] = [
    { title: 'Nombre', dataIndex: 'nombre', key: 'nombre' },
    { title: 'Dirección', dataIndex: 'direccion', key: 'direccion', render: (v: string) => v || '-' },
    { title: 'Teléfono', dataIndex: 'telefono', key: 'telefono', render: (v: string) => v || '-' },
    {
      title: 'Estado',
      dataIndex: 'activa',
      key: 'activa',
      render: (activa: boolean) => (activa ? <Tag color="success">Activa</Tag> : <Tag>Inactiva</Tag>),
    },
    {
      title: '',
      key: 'acciones',
      render: (_, sede) => (
        <Button size="small" icon={<EditOutlined />} onClick={() => editar(sede)}>
          Editar
        </Button>
      ),
    },
  ]

  return (
    <Card>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} align="start" wrap>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            Sedes
          </Typography.Title>
          <Typography.Text type="secondary">
            Las sedes son necesarias para registrar pacientes y atenciones. Se desactivan, no se borran.
          </Typography.Text>
        </div>
        <Space>
          <Select<FiltroSedeActiva>
            style={{ width: 160 }}
            value={estado}
            onChange={setEstado}
            options={[
              { value: 'todas', label: 'Todas' },
              { value: 'true', label: 'Activas' },
              { value: 'false', label: 'Inactivas' },
            ]}
          />
          <Button type="primary" icon={<PlusOutlined />} onClick={nueva}>
            Nueva sede
          </Button>
        </Space>
      </Space>
      <FormSede abierto={abierto} sede={editando} onCerrar={() => setAbierto(false)} />
      <Table<Sede>
        rowKey="id"
        columns={columnas}
        dataSource={data?.results}
        loading={isPending}
        pagination={false}
        locale={{ emptyText: 'No hay sedes con este filtro.' }}
      />
    </Card>
  )
}
