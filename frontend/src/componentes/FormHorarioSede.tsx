import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Form, Input, Modal, Select, Typography, message } from 'antd'
import { useEffect } from 'react'

import { ApiError } from '../api/cliente'
import {
  DIAS_SEMANA,
  crearHorario,
  editarHorario,
  type DatosHorario,
  type HorarioSede,
} from '../api/configuracion'

type Props = {
  abierto: boolean
  sede: number
  horario: HorarioSede | null
  onCerrar: () => void
}

/** Alta o edición de un turno semanal de la sede. */
export default function FormHorarioSede({ abierto, sede, horario, onCerrar }: Props) {
  const [form] = Form.useForm<DatosHorario>()
  const cliente = useQueryClient()
  const editando = horario !== null

  useEffect(() => {
    if (!abierto) return
    form.setFieldsValue({
      sede,
      dia_semana: horario?.dia_semana ?? 0,
      hora_apertura: horario?.hora_apertura.slice(0, 5) ?? '09:00',
      hora_cierre: horario?.hora_cierre.slice(0, 5) ?? '12:00',
    })
  }, [abierto, sede, horario, form])

  const guardar = useMutation({
    mutationFn: (datos: DatosHorario) =>
      editando ? editarHorario(horario.id, datos) : crearHorario(datos),
    onSuccess: () => {
      message.success(editando ? 'Turno actualizado' : 'Turno creado')
      cliente.invalidateQueries({ queryKey: ['horarios'] })
      cliente.invalidateQueries({ queryKey: ['disponibilidad'] })
      onCerrar()
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.campos).length > 0) {
        form.setFields(
          Object.entries(e.campos).map(([nombre, error]) => ({
            name: nombre as keyof DatosHorario,
            errors: [error],
          })),
        )
      }
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar el turno.')
    },
  })

  return (
    <Modal
      title={editando ? 'Editar turno' : 'Nuevo turno'}
      open={abierto}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Guardar"
      cancelText="Cancelar"
      confirmLoading={guardar.isPending}
      destroyOnHidden
    >
      <Form<DatosHorario>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(valores) => guardar.mutate({ ...valores, sede })}
      >
        <Form.Item name="dia_semana" label="Día" rules={[{ required: true, message: 'Elige el día' }]}>
          <Select options={DIAS_SEMANA.map((dia) => ({ value: dia.value, label: dia.label }))} />
        </Form.Item>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
          <Form.Item
            name="hora_apertura"
            label="Hora de apertura"
            rules={[{ required: true, message: 'Requerida' }]}
          >
            <Input type="time" />
          </Form.Item>
          <Form.Item
            name="hora_cierre"
            label="Hora de cierre"
            rules={[{ required: true, message: 'Requerida' }]}
          >
            <Input type="time" />
          </Form.Item>
        </div>
        <Typography.Text type="secondary">
          Cada turno es un bloque continuo. Para el almuerzo, crea un turno de mañana y otro de
          tarde.
        </Typography.Text>
      </Form>
    </Modal>
  )
}
