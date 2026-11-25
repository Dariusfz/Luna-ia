import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Form, Input, Modal, Select, message } from 'antd'
import { useEffect, useRef } from 'react'

import { ApiError } from '../api/cliente'
import {
  actualizarPaciente,
  crearPaciente,
  listarSedes,
  type DatosPaciente,
  type Paciente,
} from '../api/recursos'
import CampoTelefono from './CampoTelefono'

type Props = {
  abierto: boolean
  /** Si viene, el formulario edita ese paciente; si no, crea uno nuevo. */
  paciente?: Paciente | null
  onCerrar: () => void
}

const hoyISO = () => new Date().toISOString().slice(0, 10)

/** Alta y edición de paciente. Los errores de la API se muestran junto a cada campo. */
export default function FormPaciente({ abierto, paciente = null, onCerrar }: Props) {
  const [form] = Form.useForm<DatosPaciente>()
  const cliente = useQueryClient()
  const editando = paciente !== null
  const [modal, contextoModal] = Modal.useModal()
  const enviados = useRef<DatosPaciente | null>(null)

  const { data: sedes } = useQuery({ queryKey: ['sedes', 'true'], queryFn: () => listarSedes('true') })

  useEffect(() => {
    if (!abierto) return
    if (paciente) {
      form.setFieldsValue({
        nombres: paciente.nombres,
        apellidos: paciente.apellidos,
        identidad: paciente.identidad,
        fecha_nacimiento: paciente.fecha_nacimiento,
        sexo: paciente.sexo || null,
        sede_origen: paciente.sede_origen,
        telefono: paciente.telefono,
        email: paciente.email,
        direccion: paciente.direccion,
        alergias: paciente.alergias,
        antecedentes_medicos: paciente.antecedentes_medicos,
        medicamentos_actuales: paciente.medicamentos_actuales,
        observaciones: paciente.observaciones,
      })
    } else {
      form.resetFields()
    }
  }, [abierto, paciente, form])

  const guardar = useMutation({
    mutationFn: (datos: DatosPaciente) =>
      editando ? actualizarPaciente(paciente.id, datos) : crearPaciente(datos),
    onSuccess: () => {
      message.success(editando ? 'Paciente actualizado' : 'Paciente registrado')
      cliente.invalidateQueries({ queryKey: ['pacientes'] })
      onCerrar()
    },
    onError: (e) => {
      if (e instanceof ApiError) {
        // El backend detectó un homónimo: se pide confirmación explícita antes de duplicar.
        if (e.campos.duplicado) {
          modal.confirm({
            title: 'Posible paciente duplicado',
            content: e.campos.duplicado,
            okText: editando ? 'Es otra persona, guardar' : 'Es otra persona, registrar',
            cancelText: 'Cancelar',
            onOk: () => {
              if (enviados.current) {
                guardar.mutate({ ...enviados.current, confirmar_duplicado: true })
              }
            },
          })
          return
        }
        const campos = Object.entries(e.campos).filter(([nombre]) => nombre !== 'duplicado')
        if (campos.length > 0) {
          // Marca cada campo con su error en lugar de mostrar un aviso genérico.
          form.setFields(
            campos.map(([nombre, error]) => ({ name: nombre as keyof DatosPaciente, errors: [error] })),
          )
        }
      }
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar el paciente.')
    },
  })

  return (
    <>
      {contextoModal}
      <Modal
        title={editando ? 'Editar paciente' : 'Nuevo paciente'}
        open={abierto}
        onCancel={onCerrar}
        onOk={() => form.submit()}
        okText="Guardar"
        cancelText="Cancelar"
        confirmLoading={guardar.isPending}
        destroyOnHidden
        width={640}
      >
      {sedes && sedes.results.length === 0 && (
        <Alert
          type="warning"
          showIcon
          style={{ marginBottom: 16 }}
          message="No hay sedes activas"
          description="Crea o activa una sede en la sección Sedes antes de registrar pacientes."
        />
      )}
      <Form<DatosPaciente>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(valores) => {
          const datos = {
            ...valores,
            fecha_nacimiento: valores.fecha_nacimiento || null,
            sexo: valores.sexo || null,
          }
          enviados.current = datos
          guardar.mutate(datos)
        }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
          <Form.Item name="nombres" label="Nombres" rules={[{ required: true, message: 'Escribe los nombres' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="apellidos" label="Apellidos" rules={[{ required: true, message: 'Escribe los apellidos' }]}>
            <Input />
          </Form.Item>
          <Form.Item name="identidad" label="Identidad">
            <Input maxLength={13} placeholder="0801-1990-12345" />
          </Form.Item>
          <Form.Item
            name="fecha_nacimiento"
            label="Fecha de nacimiento"
            rules={[
              {
                validator: (_, valor: string | null) => {
                  if (!valor) return Promise.resolve()
                  const [anio] = valor.split('-')
                  if (anio.length !== 4) return Promise.reject(new Error('El año debe tener 4 dígitos'))
                  if (valor < '1900-01-01' || valor > hoyISO())
                    return Promise.reject(new Error('La fecha debe estar entre 1900 y hoy'))
                  return Promise.resolve()
                },
              },
            ]}
          >
            <Input type="date" min="1900-01-01" max={hoyISO()} />
          </Form.Item>
          <Form.Item name="sexo" label="Sexo">
            <Select
              allowClear
              options={[
                { value: 'F', label: 'Femenino' },
                { value: 'M', label: 'Masculino' },
                { value: 'O', label: 'Otro' },
              ]}
            />
          </Form.Item>
          <Form.Item
            name="sede_origen"
            label="Sede de origen"
            rules={[{ required: true, message: 'Elige la sede' }]}
          >
            <Select
              placeholder={sedes?.results.length ? 'Elige una sede' : 'No hay sedes activas'}
              disabled={!sedes?.results.length}
              options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
            />
          </Form.Item>
          <Form.Item name="telefono" label="Teléfono">
            <CampoTelefono />
          </Form.Item>
          <Form.Item name="email" label="Correo (opcional)" rules={[{ type: 'email', message: 'Correo no válido' }]}>
            <Input />
          </Form.Item>
        </div>
        <Form.Item
          name="direccion"
          label="Dirección o lugar de residencia"
          rules={[{ required: true, whitespace: true, message: 'Escribe la dirección o lugar de residencia' }]}
        >
          <Input placeholder="Colonia, barrio, municipio o departamento" />
        </Form.Item>
        <Form.Item name="alergias" label="Alergias">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Form.Item name="antecedentes_medicos" label="Antecedentes médicos">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Form.Item name="medicamentos_actuales" label="Medicamentos actuales">
          <Input.TextArea rows={2} />
        </Form.Item>
        <Form.Item name="observaciones" label="Observaciones">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
      </Modal>
    </>
  )
}
