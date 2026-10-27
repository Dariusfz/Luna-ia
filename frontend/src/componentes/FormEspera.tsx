import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Form, Input, Modal, Select, message } from 'antd'
import { useEffect, useState } from 'react'

import { ApiError } from '../api/cliente'
import {
  actualizarEspera,
  crearEspera,
  type DatosEspera,
  type ListaEspera,
} from '../api/listaEspera'
import { listarDoctores, listarTiposTrabajo } from '../api/catalogos'
import { listarPacientes, listarSedes } from '../api/recursos'
import {
  ESTADOS_ESPERA,
  ETIQUETA_ESPERA,
  ETIQUETA_PRIORIDAD,
  PRIORIDADES_ESPERA,
  type EstadoEspera,
  type PrioridadEspera,
} from '../constantes/listaEspera'

type Props = {
  abierto: boolean
  espera: ListaEspera | null
  onCerrar: () => void
}

type Valores = {
  sede: number
  paciente: number
  doctor?: number | null
  tipo_trabajo?: number | null
  prioridad: PrioridadEspera
  estado?: EstadoEspera
  fecha_deseada?: string
  motivo?: string
}

const ESTADOS_EDITABLES = ESTADOS_ESPERA.filter((estado) => estado !== 'agendado')

/** Alta y edición de una persona en lista de espera. */
export default function FormEspera({ abierto, espera, onCerrar }: Props) {
  const [form] = Form.useForm<Valores>()
  const cliente = useQueryClient()
  const editando = espera !== null
  const [busqueda, setBusqueda] = useState('')
  const [nombres, setNombres] = useState<Record<number, string>>({})

  const sedeElegida = Form.useWatch('sede', form)

  const { data: sedes } = useQuery({
    queryKey: ['sedes', 'true'],
    queryFn: () => listarSedes('true'),
  })
  const { data: doctores } = useQuery({
    queryKey: ['doctores-sede-espera', sedeElegida],
    queryFn: () => listarDoctores(1, { sede: sedeElegida, activo: 'true' }),
    enabled: !!sedeElegida,
  })
  const { data: tipos } = useQuery({
    queryKey: ['tipos-trabajo', 'true'],
    queryFn: () => listarTiposTrabajo('true'),
  })
  const { data: pacientes } = useQuery({
    queryKey: ['pacientes-buscar-espera', busqueda],
    queryFn: () => listarPacientes(1, { q: busqueda, activo: 'true' }),
    enabled: abierto,
  })

  useEffect(() => {
    if (!abierto) return
    setBusqueda('')
    if (espera) {
      setNombres({ [espera.paciente]: espera.paciente_nombre })
      form.setFieldsValue({
        sede: espera.sede,
        paciente: espera.paciente,
        doctor: espera.doctor,
        tipo_trabajo: espera.tipo_trabajo,
        prioridad: espera.prioridad,
        estado: espera.estado === 'agendado' ? undefined : espera.estado,
        fecha_deseada: espera.fecha_deseada ?? '',
        motivo: espera.motivo,
      })
    } else {
      setNombres({})
      form.resetFields()
      form.setFieldsValue({ prioridad: 2 })
    }
  }, [abierto, espera, form])

  useEffect(() => {
    if (!pacientes) return
    setNombres((previo) => {
      const nuevo = { ...previo }
      pacientes.results.forEach((p) => {
        nuevo[p.id] = `${p.nombres} ${p.apellidos}`
      })
      return nuevo
    })
  }, [pacientes])

  // Al cambiar de sede, el doctor preferido de otra sede deja de aplicar.
  useEffect(() => {
    if (!sedeElegida) return
    if (!editando || sedeElegida !== espera?.sede) form.setFieldValue('doctor', undefined)
  }, [sedeElegida]) // eslint-disable-line react-hooks/exhaustive-deps

  const guardar = useMutation({
    mutationFn: (datos: DatosEspera) =>
      editando ? actualizarEspera(espera.id, datos) : crearEspera(datos),
    onSuccess: () => {
      message.success(editando ? 'Espera actualizada' : 'Paciente agregado a la lista de espera')
      cliente.invalidateQueries({ queryKey: ['lista-espera'] })
      cliente.invalidateQueries({ queryKey: ['dashboard'] })
      onCerrar()
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.campos).length > 0) {
        form.setFields(
          Object.entries(e.campos).map(([nombre, error]) => ({
            name: nombre as keyof Valores,
            errors: [error],
          })),
        )
      }
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar la espera.')
    },
  })

  function enviar(valores: Valores) {
    const datos: DatosEspera = {
      sede: valores.sede,
      paciente: valores.paciente,
      doctor: valores.doctor ?? null,
      tipo_trabajo: valores.tipo_trabajo ?? null,
      prioridad: valores.prioridad,
      fecha_deseada: valores.fecha_deseada || null,
      motivo: valores.motivo ?? '',
    }
    if (editando && espera.estado !== 'agendado') datos.estado = valores.estado ?? 'esperando'
    guardar.mutate(datos)
  }

  return (
    <Modal
      title={editando ? 'Editar lista de espera' : 'Nuevo en lista de espera'}
      open={abierto}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Guardar"
      cancelText="Cancelar"
      confirmLoading={guardar.isPending}
      destroyOnHidden
      width={640}
    >
      <Form<Valores> form={form} layout="vertical" requiredMark={false} onFinish={enviar}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
          <Form.Item name="sede" label="Sede" rules={[{ required: true, message: 'Elige la sede' }]}>
            <Select
              placeholder="Elige una sede"
              options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
            />
          </Form.Item>
          <Form.Item
            name="paciente"
            label="Paciente"
            rules={[{ required: true, message: 'Elige el paciente' }]}
          >
            <Select
              showSearch
              filterOption={false}
              onSearch={setBusqueda}
              placeholder="Escribe nombre, identidad o teléfono"
              options={Object.entries(nombres).map(([id, nombre]) => ({
                value: Number(id),
                label: nombre,
              }))}
            />
          </Form.Item>
          <Form.Item name="doctor" label="Doctor preferido">
            <Select
              allowClear
              placeholder={sedeElegida ? 'Sin preferencia' : 'Primero elige la sede'}
              disabled={!sedeElegida}
              options={doctores?.results.map((d) => ({
                value: d.id,
                label: `${d.nombres} ${d.apellidos}`,
              }))}
            />
          </Form.Item>
          <Form.Item name="tipo_trabajo" label="Tipo de trabajo">
            <Select
              allowClear
              placeholder="Sin especificar"
              options={tipos?.results.map((t) => ({ value: t.id, label: t.nombre }))}
            />
          </Form.Item>
          <Form.Item
            name="prioridad"
            label="Prioridad"
            rules={[{ required: true, message: 'Elige la prioridad' }]}
          >
            <Select
              options={PRIORIDADES_ESPERA.map((p) => ({
                value: p,
                label: ETIQUETA_PRIORIDAD[p],
              }))}
            />
          </Form.Item>
          {editando && espera.estado !== 'agendado' && (
            <Form.Item name="estado" label="Estado">
              <Select
                options={ESTADOS_EDITABLES.map((estado) => ({
                  value: estado,
                  label: ETIQUETA_ESPERA[estado],
                }))}
              />
            </Form.Item>
          )}
          <Form.Item name="fecha_deseada" label="Fecha deseada">
            <Input type="date" />
          </Form.Item>
        </div>
        <Form.Item name="motivo" label="Motivo o preferencia">
          <Input.TextArea
            rows={2}
            placeholder="Ej.: solo puede por la mañana, viene de otra ciudad…"
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
