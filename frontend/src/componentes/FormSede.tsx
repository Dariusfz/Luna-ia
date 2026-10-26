import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Form, Input, Modal, Switch, message } from 'antd'
import { useEffect } from 'react'

import { ApiError } from '../api/cliente'
import { crearSede, editarSede, type DatosSede, type Sede } from '../api/recursos'
import CampoTelefono from './CampoTelefono'

type Props = {
  abierto: boolean
  sede: Sede | null
  onCerrar: () => void
}

/** Crear o editar una sede (solo admin). Si `sede` viene, se edita. */
export default function FormSede({ abierto, sede, onCerrar }: Props) {
  const [form] = Form.useForm<DatosSede>()
  const cliente = useQueryClient()
  const editando = sede !== null

  useEffect(() => {
    if (abierto) {
      form.setFieldsValue({
        nombre: sede?.nombre ?? '',
        direccion: sede?.direccion ?? '',
        telefono: sede?.telefono ?? '',
        activa: sede?.activa ?? true,
      })
    }
  }, [abierto, sede, form])

  const guardar = useMutation({
    mutationFn: (datos: DatosSede) => (editando ? editarSede(sede.id, datos) : crearSede(datos)),
    onSuccess: () => {
      message.success(editando ? 'Sede actualizada' : 'Sede creada')
      cliente.invalidateQueries({ queryKey: ['sedes'] })
      onCerrar()
    },
    onError: (e) => {
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar la sede.')
    },
  })

  return (
    <Modal
      title={editando ? 'Editar sede' : 'Nueva sede'}
      open={abierto}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Guardar"
      cancelText="Cancelar"
      confirmLoading={guardar.isPending}
      destroyOnHidden
    >
      <Form<DatosSede> form={form} layout="vertical" requiredMark={false} onFinish={(v) => guardar.mutate(v)}>
        <Form.Item name="nombre" label="Nombre de la sede" rules={[{ required: true, message: 'Escribe el nombre' }]}>
          <Input />
        </Form.Item>
        <Form.Item name="direccion" label="Dirección">
          <Input />
        </Form.Item>
        <Form.Item name="telefono" label="Teléfono">
          <CampoTelefono />
        </Form.Item>
        {editando && (
          <Form.Item name="activa" label="Activa" valuePropName="checked">
            <Switch />
          </Form.Item>
        )}
      </Form>
    </Modal>
  )
}
