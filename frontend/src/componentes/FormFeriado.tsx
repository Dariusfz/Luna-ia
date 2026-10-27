import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Form, Input, Modal, Select, Switch, message } from 'antd'
import { useEffect } from 'react'

import { ApiError } from '../api/cliente'
import {
  crearFeriado,
  editarFeriado,
  type DatosFeriado,
  type Feriado,
} from '../api/configuracion'
import type { Sede } from '../api/recursos'

type Props = {
  abierto: boolean
  feriado: Feriado | null
  sedes: Sede[]
  onCerrar: () => void
}

type Valores = Omit<DatosFeriado, 'sede'> & { sede?: number | null }

/** Alta o edición de un feriado completo o de medio día. */
export default function FormFeriado({ abierto, feriado, sedes, onCerrar }: Props) {
  const [form] = Form.useForm<Valores>()
  const cliente = useQueryClient()
  const editando = feriado !== null
  const todoElDia = Form.useWatch('todo_el_dia', form) ?? true

  useEffect(() => {
    if (!abierto) return
    form.setFieldsValue({
      sede: feriado?.sede ?? null,
      fecha: feriado?.fecha ?? '',
      nombre: feriado?.nombre ?? '',
      todo_el_dia: feriado?.todo_el_dia ?? true,
      hora_inicio: feriado?.hora_inicio?.slice(0, 5) ?? '09:00',
      hora_fin: feriado?.hora_fin?.slice(0, 5) ?? '12:00',
    })
  }, [abierto, feriado, form])

  const guardar = useMutation({
    mutationFn: (datos: DatosFeriado) =>
      editando ? editarFeriado(feriado.id, datos) : crearFeriado(datos),
    onSuccess: () => {
      message.success(editando ? 'Feriado actualizado' : 'Feriado creado')
      cliente.invalidateQueries({ queryKey: ['feriados'] })
      cliente.invalidateQueries({ queryKey: ['disponibilidad'] })
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
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar el feriado.')
    },
  })

  function enviar(valores: Valores) {
    guardar.mutate({
      sede: valores.sede ?? null,
      fecha: valores.fecha,
      nombre: valores.nombre,
      todo_el_dia: valores.todo_el_dia,
      hora_inicio: valores.todo_el_dia ? null : (valores.hora_inicio ?? null),
      hora_fin: valores.todo_el_dia ? null : (valores.hora_fin ?? null),
    })
  }

  return (
    <Modal
      title={editando ? 'Editar feriado' : 'Nuevo feriado'}
      open={abierto}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Guardar"
      cancelText="Cancelar"
      confirmLoading={guardar.isPending}
      destroyOnHidden
    >
      <Form<Valores> form={form} layout="vertical" requiredMark={false} onFinish={enviar}>
        <Form.Item
          name="sede"
          label="Sede"
          extra="Déjalo vacío para cerrar todas las sedes."
        >
          <Select
            allowClear
            placeholder="Todas las sedes"
            options={sedes.map((sede) => ({ value: sede.id, label: sede.nombre }))}
          />
        </Form.Item>
        <Form.Item name="fecha" label="Fecha" rules={[{ required: true, message: 'Elige la fecha' }]}>
          <Input type="date" />
        </Form.Item>
        <Form.Item
          name="nombre"
          label="Motivo"
          rules={[{ required: true, message: 'Escribe el motivo del feriado' }]}
        >
          <Input placeholder="Ej.: Día de la Independencia" />
        </Form.Item>
        <Form.Item name="todo_el_dia" label="Todo el día" valuePropName="checked">
          <Switch />
        </Form.Item>
        {!todoElDia && (
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
            <Form.Item
              name="hora_inicio"
              label="Desde"
              rules={[{ required: true, message: 'Requerida' }]}
            >
              <Input type="time" />
            </Form.Item>
            <Form.Item
              name="hora_fin"
              label="Hasta"
              rules={[{ required: true, message: 'Requerida' }]}
            >
              <Input type="time" />
            </Form.Item>
          </div>
        )}
      </Form>
    </Modal>
  )
}
