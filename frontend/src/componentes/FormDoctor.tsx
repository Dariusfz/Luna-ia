import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Form, Input, Modal, Select, Switch, message } from 'antd'
import { useEffect } from 'react'

import { ApiError } from '../api/cliente'
import {
  actualizarDoctor,
  crearDoctor,
  listarEspecialidades,
  type DatosDoctor,
  type Doctor,
} from '../api/catalogos'
import { listarSedes } from '../api/recursos'
import CampoTelefono from './CampoTelefono'

type Props = {
  abierto: boolean
  doctor: Doctor | null
  onCerrar: () => void
}

/** Alta y edición de doctores. Los contratados por sesión no tienen cuenta de acceso. */
export default function FormDoctor({ abierto, doctor, onCerrar }: Props) {
  const [form] = Form.useForm<DatosDoctor>()
  const cliente = useQueryClient()
  const editando = doctor !== null

  const { data: sedes } = useQuery({ queryKey: ['sedes', 'true'], queryFn: () => listarSedes('true') })
  const { data: especialidades } = useQuery({
    queryKey: ['especialidades', 'true'],
    queryFn: () => listarEspecialidades('true'),
  })

  useEffect(() => {
    if (!abierto) return
    if (doctor) {
      form.setFieldsValue({
        tipo: doctor.tipo,
        nombres: doctor.nombres,
        apellidos: doctor.apellidos,
        especialidad: doctor.especialidad,
        numero_colegiado: doctor.numero_colegiado,
        telefono: doctor.telefono,
        activo: doctor.activo,
        sedes: doctor.sedes,
        observaciones: doctor.observaciones ?? '',
      })
    } else {
      form.resetFields()
      form.setFieldsValue({ tipo: 'contratado', sedes: [], activo: true })
    }
  }, [abierto, doctor, form])

  const guardar = useMutation({
    mutationFn: (datos: DatosDoctor) => (editando ? actualizarDoctor(doctor.id, datos) : crearDoctor(datos)),
    onSuccess: () => {
      message.success(editando ? 'Doctor actualizado' : 'Doctor registrado')
      cliente.invalidateQueries({ queryKey: ['doctores'] })
      onCerrar()
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.campos).length > 0) {
        form.setFields(
          Object.entries(e.campos).map(([nombre, error]) => ({ name: nombre as keyof DatosDoctor, errors: [error] })),
        )
      }
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar el doctor.')
    },
  })

  return (
    <Modal
      title={editando ? 'Editar doctor' : 'Nuevo doctor'}
      open={abierto}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Guardar"
      cancelText="Cancelar"
      confirmLoading={guardar.isPending}
      destroyOnHidden
      width={640}
    >
      <Form<DatosDoctor> form={form} layout="vertical" requiredMark={false} onFinish={(v) => guardar.mutate(v)}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
          <Form.Item name="nombres" label="Nombres" rules={[{ required: true, message: 'Escribe los nombres' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="apellidos" label="Apellidos" rules={[{ required: true, message: 'Escribe los apellidos' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="tipo" label="Tipo de doctor" rules={[{ required: true, message: 'Elige el tipo' }]}>
            <Select
              options={[
                { value: 'propio', label: 'Interno (personal de la clínica)' },
                { value: 'contratado', label: 'Contratado por sesión' },
              ]}
            />
          </Form.Item>
          <Form.Item name="especialidad" label="Especialidad">
            <Select
              allowClear
              placeholder={especialidades?.results.length ? 'Elige una especialidad' : 'No hay especialidades activas'}
              options={especialidades?.results.map((e) => ({ value: e.id, label: e.nombre }))}
            />
          </Form.Item>
          <Form.Item name="numero_colegiado" label="Número de colegiado">
            <Input />
          </Form.Item>
          <Form.Item name="telefono" label="Teléfono">
            <CampoTelefono />
          </Form.Item>
        </div>
        <Form.Item
          name="sedes"
          label="Sedes donde atiende"
          rules={[{ required: true, message: 'Asigna al menos una sede' }]}
        >
          <Select
            mode="multiple"
            placeholder="Elige sedes"
            options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
          />
        </Form.Item>
        <Form.Item name="observaciones" label="Observaciones (solo administración)">
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
