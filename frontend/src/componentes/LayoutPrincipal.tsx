import {
  BankOutlined,
  CalendarOutlined,
  ExperimentOutlined,
  HomeOutlined,
  IdcardOutlined,
  LogoutOutlined,
  MedicineBoxOutlined,
  MenuOutlined,
  TagsOutlined,
  TeamOutlined,
  UserOutlined,
} from '@ant-design/icons'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Avatar, Button, Dropdown, Grid, Layout, Menu, Space, Typography } from 'antd'
import type { MenuProps } from 'antd'
import { useEffect, useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'

import { cerrarSesion, obtenerUsuarioActual } from '../api/auth'

const { Sider, Header, Content } = Layout

const ALTURA_ENCABEZADO = 64

const itemsBase: NonNullable<MenuProps['items']> = [
  { key: '/', icon: <HomeOutlined />, label: 'Inicio' },
  { key: '/pacientes', icon: <TeamOutlined />, label: 'Pacientes' },
  { key: '/atenciones', icon: <CalendarOutlined />, label: 'Atenciones' },
  { key: '/doctores', icon: <MedicineBoxOutlined />, label: 'Doctores' },
  { key: '/especialidades', icon: <ExperimentOutlined />, label: 'Especialidades' },
  { key: '/tipos-trabajo', icon: <TagsOutlined />, label: 'Tipos de trabajo' },
]

const itemsAdmin: NonNullable<MenuProps['items']> = [
  { key: '/sedes', icon: <BankOutlined />, label: 'Sedes' },
  { key: '/personal', icon: <IdcardOutlined />, label: 'Personal' },
]

export default function LayoutPrincipal() {
  const navigate = useNavigate()
  const ubicacion = useLocation()
  const cliente = useQueryClient()
  const { data: usuario } = useQuery({ queryKey: ['me'], queryFn: obtenerUsuarioActual })

  // Menor a 992 px: el menú empieza cerrado y se muestra encima del contenido.
  const { lg } = Grid.useBreakpoint()
  const movil = lg === false
  const [abierto, setAbierto] = useState(true)

  useEffect(() => {
    setAbierto(!movil)
  }, [movil])

  function elegir(ruta: string) {
    navigate(ruta)
    if (movil) setAbierto(false)
  }

  async function salir() {
    await cerrarSesion().catch(() => undefined)
    cliente.removeQueries({ queryKey: ['me'] })
    navigate('/login', { replace: true })
  }

  const menuUsuario: MenuProps['items'] = [
    { key: 'salir', icon: <LogoutOutlined />, label: 'Cerrar sesión', onClick: salir },
  ]

  const iniciales = usuario ? `${usuario.nombres.charAt(0)}${usuario.apellidos.charAt(0)}` : ''
  const itemsMenu = usuario?.es_admin ? [...itemsBase, ...itemsAdmin] : itemsBase

  const menuFlotante = movil && abierto

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Header className="encabezado">
        <div className="marca-encabezado">
          <Button
            type="text"
            icon={<MenuOutlined />}
            onClick={() => setAbierto((v) => !v)}
            aria-label={abierto ? 'Cerrar menú' : 'Abrir menú'}
            aria-expanded={abierto}
            className="boton-menu"
          />
          <img src="/img/logoLuna.jpeg" alt="Logo LUNA" className="logo-encabezado" />
          <Typography.Text strong className="nombre-marca">
            LUNA IA
          </Typography.Text>
        </div>
        <Dropdown menu={{ items: menuUsuario }} trigger={['click']}>
          <Space className="usuario-menu">
            <Avatar style={{ backgroundColor: '#238781' }} icon={<UserOutlined />}>
              {iniciales}
            </Avatar>
            {!movil && (
              <Typography.Text strong>{usuario ? `${usuario.nombres} ${usuario.apellidos}` : ''}</Typography.Text>
            )}
          </Space>
        </Dropdown>
      </Header>

      <Layout>
        <Sider
          trigger={null}
          width={240}
          collapsedWidth={0}
          collapsed={!abierto}
          className="sider-luna"
          style={
            menuFlotante
              ? { position: 'fixed', top: ALTURA_ENCABEZADO, bottom: 0, left: 0, zIndex: 900 }
              : undefined
          }
        >
          <Menu
            mode="inline"
            selectedKeys={[ubicacion.pathname]}
            items={itemsMenu}
            onClick={({ key }) => elegir(key)}
          />
        </Sider>
        <Content className="contenido">
          <Outlet />
        </Content>
      </Layout>
    </Layout>
  )
}
