import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Form, Modal, Select, message } from 'antd'
import { useEffect } from 'react'

import { ApiError } from '../api/cliente'
import { listarSedes } from '../api/recursos'
import { editarUsuario, type DatosEditarUsuario, type Rol, type UsuarioAdmin } from '../api/usuarios'

type Props = {
  usuario: UsuarioAdmin | null
  onCerrar: () => void
}

const roles: { value: Rol; label: string }[] = [
  { value: 'recepcionista', label: 'Recepcionista' },
  { value: 'asistente', label: 'Asistente' },
  { value: 'doctor', label: 'Doctor' },
  { value: 'admin', label: 'Administrador' },
]

/** Cambiar rol y sedes de una cuenta. El estado activo se cambia desde la tabla. */
export default function FormUsuario({ usuario, onCerrar }: Props) {
  const [form] = Form.useForm<{ rol: Rol; sedes: number[] }>()
  const cliente = useQueryClient()
  const rol = Form.useWatch('rol', form)

  const { data: sedes } = useQuery({ queryKey: ['sedes', 'true'], queryFn: () => listarSedes('true') })

  useEffect(() => {
    if (usuario) {
      form.setFieldsValue({ rol: usuario.rol, sedes: (usuario.sedes ?? []).map((s) => s.id) })
    }
  }, [usuario, form])

  const guardar = useMutation({
    mutationFn: (datos: DatosEditarUsuario) => editarUsuario(usuario!.id, datos),
    onSuccess: () => {
      message.success('Personal actualizado')
      cliente.invalidateQueries({ queryKey: ['usuarios'] })
      onCerrar()
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.campos).length > 0) {
        form.setFields(
          Object.entries(e.campos).map(([nombre, error]) => ({ name: nombre as 'rol' | 'sedes', errors: [error] })),
        )
      }
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar.')
    },
  })

  return (
    <Modal
      title={usuario ? `Editar a ${usuario.nombres} ${usuario.apellidos}` : 'Editar'}
      open={usuario !== null}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Guardar"
      cancelText="Cancelar"
      confirmLoading={guardar.isPending}
      destroyOnHidden
    >
      <Form<{ rol: Rol; sedes: number[] }>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(valores) => guardar.mutate(valores)}
      >
        <Form.Item name="rol" label="Rol" rules={[{ required: true, message: 'Elige un rol' }]}>
          <Select options={roles} />
        </Form.Item>
        <Form.Item
          name="sedes"
          label="Sedes"
          extra={rol === 'admin' ? 'El administrador ve todas las sedes.' : 'Asigna al menos una sede.'}
        >
          <Select
            mode="multiple"
            placeholder="Elige sedes"
            disabled={rol === 'admin'}
            options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
          />
        </Form.Item>
      </Form>
    </Modal>
  )
}
