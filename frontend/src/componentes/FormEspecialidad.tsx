import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Form, Input, Modal, Switch, message } from 'antd'
import { useEffect } from 'react'

import {
  actualizarEspecialidad,
  crearEspecialidad,
  type DatosEspecialidad,
  type Especialidad,
} from '../api/catalogos'
import { ApiError } from '../api/cliente'

type Props = {
  abierto: boolean
  especialidad: Especialidad | null
  onCerrar: () => void
}

export default function FormEspecialidad({ abierto, especialidad, onCerrar }: Props) {
  const [form] = Form.useForm<DatosEspecialidad>()
  const cliente = useQueryClient()
  const editando = especialidad !== null

  useEffect(() => {
    if (!abierto) return
    if (especialidad) {
      form.setFieldsValue({ nombre: especialidad.nombre, activo: especialidad.activo })
    } else {
      form.resetFields()
      form.setFieldsValue({ activo: true })
    }
  }, [abierto, especialidad, form])

  const guardar = useMutation({
    mutationFn: (datos: DatosEspecialidad) =>
      editando ? actualizarEspecialidad(especialidad.id, datos) : crearEspecialidad(datos),
    onSuccess: () => {
      message.success(editando ? 'Especialidad actualizada' : 'Especialidad creada')
      cliente.invalidateQueries({ queryKey: ['especialidades'] })
      onCerrar()
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.campos).length > 0) {
        form.setFields(
          Object.entries(e.campos).map(([nombre, error]) => ({ name: nombre as keyof DatosEspecialidad, errors: [error] })),
        )
      }
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar la especialidad.')
    },
  })

  return (
    <Modal
      title={editando ? 'Editar especialidad' : 'Nueva especialidad'}
      open={abierto}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Guardar"
      cancelText="Cancelar"
      confirmLoading={guardar.isPending}
      destroyOnHidden
    >
      <Form<DatosEspecialidad> form={form} layout="vertical" requiredMark={false} onFinish={(v) => guardar.mutate(v)}>
        <Form.Item
          name="nombre"
          label="Nombre"
          rules={[{ required: true, whitespace: true, message: 'Escribe el nombre, por ejemplo "Ortodoncia"' }]}
        >
          <Input />
        </Form.Item>
        {editando && (
          <Form.Item name="activo" label="Activa" valuePropName="checked">
            <Switch />
          </Form.Item>
        )}
      </Form>
    </Modal>
  )
}
