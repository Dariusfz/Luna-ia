import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Form, Input, InputNumber, Modal, Switch, message } from 'antd'
import { useEffect } from 'react'

import { actualizarTipoTrabajo, crearTipoTrabajo, type DatosTipoTrabajo, type TipoTrabajo } from '../api/catalogos'
import { ApiError } from '../api/cliente'
import {
  MONTO_MAXIMO,
  MONTO_MAXIMO_LONGITUD,
  MONTO_MAXIMO_TEXTO,
  formatearMonto,
} from '../constantes/montos'

type Props = {
  abierto: boolean
  tipo: TipoTrabajo | null
  onCerrar: () => void
}

export default function FormTipoTrabajo({ abierto, tipo, onCerrar }: Props) {
  const [form] = Form.useForm<DatosTipoTrabajo>()
  const cliente = useQueryClient()
  const editando = tipo !== null

  useEffect(() => {
    if (!abierto) return
    if (tipo) {
      form.setFieldsValue({
        nombre: tipo.nombre,
        descripcion: tipo.descripcion,
        precio: Number(tipo.precio),
        activo: tipo.activo,
      })
    } else {
      form.resetFields()
      form.setFieldsValue({ activo: true, precio: 0 })
    }
  }, [abierto, tipo, form])

  const guardar = useMutation({
    mutationFn: (datos: DatosTipoTrabajo) =>
      editando ? actualizarTipoTrabajo(tipo.id, datos) : crearTipoTrabajo(datos),
    onSuccess: () => {
      message.success(editando ? 'Tipo actualizado' : 'Tipo creado')
      cliente.invalidateQueries({ queryKey: ['tipos-trabajo'] })
      onCerrar()
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.campos).length > 0) {
        form.setFields(
          Object.entries(e.campos).map(([nombre, error]) => ({ name: nombre as keyof DatosTipoTrabajo, errors: [error] })),
        )
      }
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar el tipo de trabajo.')
    },
  })

  return (
    <Modal
      title={editando ? 'Editar tipo de trabajo' : 'Nuevo tipo de trabajo'}
      open={abierto}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Guardar"
      cancelText="Cancelar"
      confirmLoading={guardar.isPending}
      destroyOnHidden
    >
      <Form<DatosTipoTrabajo> form={form} layout="vertical" requiredMark={false} onFinish={(v) => guardar.mutate(v)}>
        <Form.Item
          name="nombre"
          label="Nombre"
          rules={[{ required: true, whitespace: true, message: 'Escribe el nombre, por ejemplo "Extracción"' }]}
        >
          <Input />
        </Form.Item>
        <Form.Item
          name="precio"
          label="Precio (HNL)"
          rules={[
            { required: true, message: 'Escribe el precio del tratamiento' },
            {
              type: 'number',
              max: MONTO_MAXIMO,
              message: `El precio no puede superar ${MONTO_MAXIMO_TEXTO}.`,
            },
          ]}
        >
          <InputNumber
            min={0}
            max={MONTO_MAXIMO}
            maxLength={MONTO_MAXIMO_LONGITUD}
            precision={2}
            step={50}
            prefix="L"
            formatter={formatearMonto}
            onChange={(valor) => {
              if (typeof valor === 'number' && valor > MONTO_MAXIMO) {
                form.setFieldValue('precio', MONTO_MAXIMO)
              }
            }}
            style={{ width: '100%' }}
          />
        </Form.Item>
        <Form.Item name="descripcion" label="Descripción">
          <Input.TextArea rows={2} />
        </Form.Item>
        {editando && (
          <Form.Item name="activo" label="Activo" valuePropName="checked">
            <Switch />
          </Form.Item>
        )}
      </Form>
    </Modal>
  )
}
