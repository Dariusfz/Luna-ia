import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, App as AppAntd, Form, Input, Modal, Select, Typography } from 'antd'
import { useState } from 'react'

import { listarSedes } from '../api/recursos'
import { ApiError } from '../api/cliente'
import { invitarPersonal, type DatosInvitacion } from '../api/usuarios'

type Props = {
  abierto: boolean
  onCerrar: () => void
  /** Se llama al enviar la invitación, para mostrar el acuse en la página. */
  onEnviada: (email: string) => void
}

const roles = [
  { value: 'recepcionista', label: 'Recepcionista' },
  { value: 'asistente', label: 'Asistente' },
  { value: 'doctor', label: 'Doctor' },
  { value: 'admin', label: 'Administrador' },
]

/** Invita a una persona por correo. Ella crea su contraseña y configura el 2FA. */
export default function FormInvitacion({ abierto, onCerrar, onEnviada }: Props) {
  const [form] = Form.useForm<DatosInvitacion>()
  const cliente = useQueryClient()
  const rol = Form.useWatch('rol', form)
  const [error, setError] = useState<string | null>(null)
  const { message } = AppAntd.useApp()

  const { data: sedes } = useQuery({ queryKey: ['sedes', 'true'], queryFn: () => listarSedes('true') })

  const invitar = useMutation({
    mutationFn: invitarPersonal,
    onSuccess: (respuesta) => {
      setError(null)
      message.success(`Invitación enviada a ${respuesta.email}`)
      onEnviada(respuesta.email)
      cliente.invalidateQueries({ queryKey: ['usuarios'] })
      form.resetFields()
      onCerrar()
    },
    onError: (e) => {
      const texto = e instanceof ApiError ? e.message : 'No se pudo enviar la invitación.'
      // El motivo se muestra también bajo el campo que lo provocó (correo, rol o sedes).
      if (e instanceof ApiError) {
        form.setFields(
          Object.entries(e.campos).map(([campo, mensaje]) => ({
            name: campo as keyof DatosInvitacion,
            errors: [mensaje],
          })),
        )
      }
      setError(texto)
      message.error(texto)
    },
  })

  function cerrar() {
    setError(null)
    onCerrar()
  }

  return (
    <Modal
      title="Invitar personal"
      open={abierto}
      onCancel={cerrar}
      onOk={() => {
        setError(null)
        form.submit()
      }}
      okText="Enviar invitación"
      cancelText="Cancelar"
      confirmLoading={invitar.isPending}
      destroyOnHidden
    >
      <Typography.Paragraph type="secondary">
        La persona recibirá un enlace por correo para crear su cuenta. El enlace vence en 72 horas.
      </Typography.Paragraph>
      {error && <Alert type="error" showIcon message={error} style={{ marginBottom: 16 }} />}
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
