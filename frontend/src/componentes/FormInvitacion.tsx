import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Form, Input, Modal, Select, Typography, message } from 'antd'

import { listarSedes } from '../api/recursos'
import { ApiError } from '../api/cliente'
import { invitarPersonal, type DatosInvitacion } from '../api/usuarios'

type Props = {
  abierto: boolean
  onCerrar: () => void
}

const roles = [
  { value: 'recepcionista', label: 'Recepcionista' },
  { value: 'asistente', label: 'Asistente' },
  { value: 'doctor', label: 'Doctor' },
  { value: 'admin', label: 'Administrador' },
]

/** Invita a una persona por correo. Ella crea su contraseña y configura el 2FA. */
export default function FormInvitacion({ abierto, onCerrar }: Props) {
  const [form] = Form.useForm<DatosInvitacion>()
  const cliente = useQueryClient()
  const rol = Form.useWatch('rol', form)

  const { data: sedes } = useQuery({ queryKey: ['sedes', 'true'], queryFn: () => listarSedes('true') })

  const invitar = useMutation({
    mutationFn: invitarPersonal,
    onSuccess: (respuesta) => {
      message.success(`Invitación enviada a ${respuesta.email}`)
      cliente.invalidateQueries({ queryKey: ['usuarios'] })
      form.resetFields()
      onCerrar()
    },
    onError: (e) => {
      message.error(e instanceof ApiError ? e.message : 'No se pudo enviar la invitación.')
    },
  })

  return (
    <Modal
      title="Invitar personal"
      open={abierto}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Enviar invitación"
      cancelText="Cancelar"
      confirmLoading={invitar.isPending}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        La persona recibirá un enlace por correo para crear su cuenta. El enlace vence en 72 horas.
      </Typography.Paragraph>
      <Form<DatosInvitacion>
        form={form}
        layout="vertical"
        requiredMark={false}
        initialValues={{ sedes: [] }}
        onFinish={(valores) => invitar.mutate(valores)}
      >
        <Form.Item
          name="email"
          label="Correo"
          rules={[
            { required: true, message: 'Escribe el correo' },
            { type: 'email', message: 'Correo no válido' },
          ]}
        >
          <Input />
        </Form.Item>
        <Form.Item name="rol" label="Rol" rules={[{ required: true, message: 'Elige un rol' }]}>
          <Select options={roles} placeholder="Elige un rol" />
        </Form.Item>
        <Form.Item
          name="sedes"
          label="Sedes"
          extra={rol === 'admin' ? 'El administrador ve todas las sedes.' : 'Elige al menos una sede.'}
          rules={[
            {
              validator: (_, valor: number[]) =>
                rol === 'admin' || (valor && valor.length > 0)
                  ? Promise.resolve()
                  : Promise.reject(new Error('Elige al menos una sede')),
            },
          ]}
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
