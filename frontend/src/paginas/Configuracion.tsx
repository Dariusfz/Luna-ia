import { DeleteOutlined, EditOutlined, PlusOutlined } from '@ant-design/icons'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Button, Card, Popconfirm, Select, Space, Table, Tabs, Tag, Typography, message } from 'antd'
import type { TableProps } from 'antd'
import { useEffect, useState } from 'react'

import { ApiError } from '../api/cliente'
import {
  eliminarFeriado,
  eliminarHorario,
  listarFeriados,
  listarHorarios,
  type Feriado,
  type HorarioSede,
} from '../api/configuracion'
import { listarSedes } from '../api/recursos'
import FormFeriado from '../componentes/FormFeriado'
import FormHorarioSede from '../componentes/FormHorarioSede'

const hora = (valor: string | null) => (valor ? valor.slice(0, 5) : '--:--')

/** Horarios semanales y feriados por sede. Solo el administrador puede modificarlos. */
export default function Configuracion() {
  const cliente = useQueryClient()
  const [sedeId, setSedeId] = useState<number | null>(null)

  const { data: sedes } = useQuery({ queryKey: ['sedes', 'true'], queryFn: () => listarSedes('true') })

  useEffect(() => {
    if (sedeId === null && sedes?.results.length) setSedeId(sedes.results[0].id)
  }, [sedes, sedeId])

  const { data: horarios, isPending: cargandoHorarios } = useQuery({
    queryKey: ['horarios', sedeId],
    queryFn: () => listarHorarios(sedeId),
    enabled: sedeId !== null,
  })

  const { data: feriados, isPending: cargandoFeriados } = useQuery({
    queryKey: ['feriados'],
    queryFn: () => listarFeriados(),
  })

  const [horarioAbierto, setHorarioAbierto] = useState(false)
  const [horarioEditando, setHorarioEditando] = useState<HorarioSede | null>(null)
  const [feriadoAbierto, setFeriadoAbierto] = useState(false)
  const [feriadoEditando, setFeriadoEditando] = useState<Feriado | null>(null)

  function avisoError(e: unknown) {
    message.error(e instanceof ApiError ? e.message : 'No se pudo completar la operación.')
  }

  const borrarHorario = useMutation({
    mutationFn: eliminarHorario,
    onSuccess: () => {
      message.success('Turno eliminado')
      cliente.invalidateQueries({ queryKey: ['horarios'] })
      cliente.invalidateQueries({ queryKey: ['disponibilidad'] })
    },
    onError: avisoError,
  })

  const borrarFeriado = useMutation({
    mutationFn: eliminarFeriado,
    onSuccess: () => {
      message.success('Feriado eliminado')
      cliente.invalidateQueries({ queryKey: ['feriados'] })
      cliente.invalidateQueries({ queryKey: ['disponibilidad'] })
    },
    onError: avisoError,
  })

  function nuevoHorario() {
    setHorarioEditando(null)
    setHorarioAbierto(true)
  }

  function editarTurno(turno: HorarioSede) {
    setHorarioEditando(turno)
    setHorarioAbierto(true)
  }

  function nuevoFeriado() {
    setFeriadoEditando(null)
    setFeriadoAbierto(true)
  }

  function editarDiaFeriado(dia: Feriado) {
    setFeriadoEditando(dia)
    setFeriadoAbierto(true)
  }

  const columnasHorario: TableProps<HorarioSede>['columns'] = [
    { title: 'Día', dataIndex: 'dia_nombre', key: 'dia_nombre', width: 160 },
    {
      title: 'Apertura',
      dataIndex: 'hora_apertura',
      key: 'hora_apertura',
      render: (valor: string) => hora(valor),
    },
    {
      title: 'Cierre',
      dataIndex: 'hora_cierre',
      key: 'hora_cierre',
      render: (valor: string) => hora(valor),
    },
    {
      title: '',
      key: 'acciones',
      render: (_, turno) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => editarTurno(turno)}>
            Editar
          </Button>
          <Popconfirm
            title="¿Eliminar este turno?"
            okText="Eliminar"
            cancelText="Cancelar"
            onConfirm={() => borrarHorario.mutate(turno.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              Eliminar
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const columnasFeriado: TableProps<Feriado>['columns'] = [
    { title: 'Fecha', dataIndex: 'fecha', key: 'fecha', width: 130 },
    { title: 'Sede', dataIndex: 'sede_nombre', key: 'sede_nombre', width: 170 },
    { title: 'Motivo', dataIndex: 'nombre', key: 'nombre' },
    {
      title: 'Cierre',
      key: 'cierre',
      width: 190,
      render: (_, feriado) =>
        feriado.todo_el_dia ? (
          <Tag color="red">Todo el día</Tag>
        ) : (
          <Tag color="orange">
            {hora(feriado.hora_inicio)}–{hora(feriado.hora_fin)}
          </Tag>
        ),
    },
    {
      title: '',
      key: 'acciones',
      render: (_, feriado) => (
        <Space>
          <Button size="small" icon={<EditOutlined />} onClick={() => editarDiaFeriado(feriado)}>
            Editar
          </Button>
          <Popconfirm
            title="¿Eliminar este feriado?"
            okText="Eliminar"
            cancelText="Cancelar"
            onConfirm={() => borrarFeriado.mutate(feriado.id)}
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              Eliminar
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ]

  const pestanaHorarios = (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space wrap>
        <Typography.Text strong>Sede</Typography.Text>
        <Select<number>
          style={{ width: 240 }}
          value={sedeId ?? undefined}
          onChange={setSedeId}
          placeholder="Elige la sede"
          options={sedes?.results.map((sede) => ({ value: sede.id, label: sede.nombre }))}
        />
        <Button
          type="primary"
          icon={<PlusOutlined />}
          onClick={nuevoHorario}
          disabled={sedeId === null}
        >
          Nuevo turno
        </Button>
      </Space>
      <Typography.Text type="secondary">
        Cada fila es un bloque continuo de atención. Para el almuerzo, crea un turno de mañana y
        otro de tarde. Si la sede no tiene turnos, las citas no se validan contra horario.
      </Typography.Text>
      <Table<HorarioSede>
        rowKey="id"
        columns={columnasHorario}
        dataSource={horarios}
        loading={cargandoHorarios}
        pagination={false}
        locale={{ emptyText: 'Esta sede no tiene turnos configurados.' }}
      />
    </Space>
  )

  const pestanaFeriados = (
    <Space direction="vertical" size={16} style={{ width: '100%' }}>
      <Space style={{ width: '100%', justifyContent: 'space-between' }} wrap>
        <Typography.Text type="secondary">
          Un feriado sin sede aplica a todas las sedes. Los de medio día bloquean solo su rango.
        </Typography.Text>
        <Button type="primary" icon={<PlusOutlined />} onClick={nuevoFeriado}>
          Nuevo feriado
        </Button>
      </Space>
      <Table<Feriado>
        rowKey="id"
        columns={columnasFeriado}
        dataSource={feriados}
        loading={cargandoFeriados}
        pagination={false}
        locale={{ emptyText: 'No hay feriados registrados.' }}
      />
    </Space>
  )

  return (
    <Card>
      <Typography.Title level={4} style={{ marginTop: 0 }}>
        Configuración
      </Typography.Title>
      <Typography.Paragraph type="secondary">
        Define los horarios de atención de cada sede y los feriados que cierran la agenda.
      </Typography.Paragraph>
      <Tabs
        items={[
          { key: 'horarios', label: 'Horarios', children: pestanaHorarios },
          { key: 'feriados', label: 'Feriados', children: pestanaFeriados },
        ]}
      />
      {sedeId !== null && (
        <FormHorarioSede
          abierto={horarioAbierto}
          sede={sedeId}
          horario={horarioEditando}
          onCerrar={() => setHorarioAbierto(false)}
        />
      )}
      <FormFeriado
        abierto={feriadoAbierto}
        feriado={feriadoEditando}
        sedes={sedes?.results ?? []}
        onCerrar={() => setFeriadoAbierto(false)}
      />
    </Card>
  )
}
