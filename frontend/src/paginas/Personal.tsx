import { EditOutlined, PlusOutlined, SearchOutlined } from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Input, Popconfirm, Select, Space, Table, Tag, Typography, message } from 'antd'
import type { TableProps } from 'antd'
import { useEffect, useMemo, useState } from 'react'

import { obtenerUsuarioActual } from '../api/auth'
import FormInvitacion from '../componentes/FormInvitacion'
import FormUsuario from '../componentes/FormUsuario'
import { ApiError } from '../api/cliente'
import {
  editarUsuario,
  listarUsuarios,
  restablecer2FA,
  type Rol,
  type UsuarioAdmin,
} from '../api/usuarios'
import type { FiltroActivo } from '../api/recursos'

const etiquetaRol: Record<string, string> = {
  admin: 'Administrador',
  doctor: 'Doctor',
  recepcionista: 'Recepcionista',
  asistente: 'Asistente',
}

/** Solo visible para el administrador (la API también lo restringe). */
export default function Personal() {
  const cliente = useQueryClient()
  const [invitarAbierto, setInvitarAbierto] = useState(false)
  const [editando, setEditando] = useState<UsuarioAdmin | null>(null)

  const [texto, setTexto] = useState('')
  const [q, setQ] = useState('')
  const [rol, setRol] = useState<Rol | null>(null)
  const [activo, setActivo] = useState<FiltroActivo>('todos')

  useEffect(() => {
    const espera = setTimeout(() => setQ(texto.trim()), 300)
    return () => clearTimeout(espera)
  }, [texto])

  const filtros = useMemo(() => ({ q, rol, activo }), [q, rol, activo])

  const { data, isPending } = useQuery({
    queryKey: ['usuarios', filtros],
    queryFn: () => listarUsuarios(filtros),
    placeholderData: keepPreviousData,
  })

  const { data: me } = useQuery({ queryKey: ['me'], queryFn: obtenerUsuarioActual })

  const cambiarEstado = useMutation({
    mutationFn: ({ id, activo: nuevo }: { id: number; activo: boolean }) => editarUsuario(id, { is_active: nuevo }),
    onSuccess: (_, { activo: nuevo }) => {
      message.success(nuevo ? 'Cuenta activada' : 'Cuenta desactivada')
      cliente.invalidateQueries({ queryKey: ['usuarios'] })
    },
    onError: (e) => message.error(e instanceof ApiError ? e.message : 'No se pudo cambiar el estado.'),
  })

  const restablecer = useMutation({
    mutationFn: (id: number) => restablecer2FA(id),
    onSuccess: (respuesta) => {
      message.success(respuesta.detail)
      cliente.invalidateQueries({ queryKey: ['usuarios'] })
    },
    onError: (e) => message.error(e instanceof ApiError ? e.message : 'No se pudo restablecer el 2FA.'),
  })

  const columnas: TableProps<UsuarioAdmin>['columns'] = [
    {
      title: 'Nombre',
      key: 'nombre',
      render: (_, u) => `${u.nombres} ${u.apellidos}`.trim() || u.username,
    },
    { title: 'Usuario', dataIndex: 'username', key: 'username' },
    { title: 'Correo', dataIndex: 'email', key: 'email' },
    {
      title: 'Rol',
      dataIndex: 'rol',
      key: 'rol',
      render: (r: string) => etiquetaRol[r] ?? r,
    },
    {
      title: 'Sedes',
      key: 'sedes',
      render: (_, u) =>
        u.rol === 'admin' ? (
          <Tag color="teal">Todas</Tag>
        ) : (
          (u.sedes ?? []).map((s) => <Tag key={s.id}>{s.nombre}</Tag>)
        ),
    },
    {
      title: '2FA',
      dataIndex: 'tiene_2fa',
      key: '2fa',
      render: (ok: boolean) => (ok ? <Tag color="success">Configurada</Tag> : <Tag>Pendiente</Tag>),
    },
    {
      title: 'Estado',
      dataIndex: 'is_active',
      key: 'estado',
      render: (ok: boolean) => (ok ? <Tag color="success">Activa</Tag> : <Tag>Inactiva</Tag>),
    },
    {
      title: 'Acciones',
      key: 'acciones',
      render: (_, u) => {
        const esYo = me?.id === u.id
        return (
          <Space wrap>
            <Button size="small" icon={<EditOutlined />} onClick={() => setEditando(u)}>
              Editar
            </Button>
            {u.is_active ? (
              <Popconfirm
                title="¿Desactivar esta cuenta?"
                description="No podrá entrar al sistema. Sus sesiones abiertas se cerrarán."
                okText="Desactivar"
                okButtonProps={{ danger: true }}
                cancelText="Cancelar"
                onConfirm={() => cambiarEstado.mutate({ id: u.id, activo: false })}
                disabled={esYo}
              >
                <Button size="small" danger disabled={esYo} title={esYo ? 'No puedes desactivar tu cuenta' : undefined}>
                  Desactivar
                </Button>
              </Popconfirm>
            ) : (
              <Button size="small" onClick={() => cambiarEstado.mutate({ id: u.id, activo: true })}>
                Activar
              </Button>
            )}
            {u.tiene_2fa && (
              <Popconfirm
                title="¿Restablecer el 2FA?"
                description="Se borrará su autenticador y sus códigos. Deberá configurarlo de nuevo al entrar."
                okText="Restablecer"
                okButtonProps={{ danger: true }}
                cancelText="Cancelar"
                onConfirm={() => restablecer.mutate(u.id)}
              >
                <Button size="small" danger>
                  Restablecer 2FA
                </Button>
              </Popconfirm>
            )}
          </Space>
        )
      },
    },
  ]

  return (
    <Card>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 8 }} align="start" wrap>
        <div>
          <Typography.Title level={4} style={{ margin: 0 }}>
            Personal
          </Typography.Title>
          <Typography.Text type="secondary">
            "Restablecer 2FA" solo si la persona perdió su teléfono y sus códigos de recuperación.
          </Typography.Text>
        </div>
        <Button type="primary" icon={<PlusOutlined />} onClick={() => setInvitarAbierto(true)}>
          Invitar personal
        </Button>
      </Space>

      <Space wrap style={{ margin: '16px 0' }}>
        <Input
          allowClear
          prefix={<SearchOutlined />}
          placeholder="Buscar por nombre o usuario"
          value={texto}
          onChange={(e) => setTexto(e.target.value)}
          style={{ width: 280 }}
        />
        <Select
          allowClear
          placeholder="Todos los roles"
          style={{ width: 200 }}
          value={rol}
          onChange={(v) => setRol(v ?? null)}
          options={Object.entries(etiquetaRol).map(([value, label]) => ({ value, label }))}
        />
        <Select<FiltroActivo>
          style={{ width: 160 }}
          value={activo}
          onChange={setActivo}
          options={[
            { value: 'todos', label: 'Todos' },
            { value: 'true', label: 'Activos' },
            { value: 'false', label: 'Inactivos' },
          ]}
        />
      </Space>

      <FormInvitacion abierto={invitarAbierto} onCerrar={() => setInvitarAbierto(false)} />
      <FormUsuario usuario={editando} onCerrar={() => setEditando(null)} />
      <Table<UsuarioAdmin>
        rowKey="id"
        columns={columnas}
        dataSource={data?.results}
        loading={isPending}
        pagination={false}
        locale={{ emptyText: 'No hay personal con estos filtros.' }}
      />
    </Card>
  )
}
