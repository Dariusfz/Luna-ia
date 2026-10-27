import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Form, Input, Modal, Select, message } from 'antd'
import { useEffect, useState } from 'react'

import { consultarDisponibilidad } from '../api/atenciones'
import { ApiError } from '../api/cliente'
import { listarDoctores, listarTiposTrabajo } from '../api/catalogos'
import { agendarEspera, type DatosAgendarEspera, type ListaEspera } from '../api/listaEspera'

type Props = {
  abierto: boolean
  espera: ListaEspera | null
  onCerrar: () => void
}

type Valores = Omit<DatosAgendarEspera, 'doctor' | 'tipo_trabajo'> & {
  doctor?: number
  tipo_trabajo?: number
}

function fechaLocal(fecha: Date): string {
  const mes = String(fecha.getMonth() + 1).padStart(2, '0')
  const dia = String(fecha.getDate()).padStart(2, '0')
  return `${fecha.getFullYear()}-${mes}-${dia}`
}

/** Convierte una espera en cita, validando horario y solapamientos en el backend. */
export default function FormAgendarEspera({ abierto, espera, onCerrar }: Props) {
  const [form] = Form.useForm<Valores>()
  const cliente = useQueryClient()
  const [fechaMinima] = useState(() => fechaLocal(new Date()))

  const doctorElegido = Form.useWatch('doctor', form)
  const fechaElegida = Form.useWatch('fecha', form)
  const horaInicio = Form.useWatch('hora_inicio', form)
  const horaFin = Form.useWatch('hora_fin', form)
  const rangoValido = !!horaInicio && !!horaFin && horaFin > horaInicio

  const { data: doctores } = useQuery({
    queryKey: ['doctores-sede-agendar', espera?.sede],
    queryFn: () => listarDoctores(1, { sede: espera!.sede, activo: 'true' }),
    enabled: abierto && !!espera,
  })
  const { data: tipos } = useQuery({
    queryKey: ['tipos-trabajo', 'true'],
    queryFn: () => listarTiposTrabajo('true'),
  })
  const { data: disponibilidad } = useQuery({
    queryKey: [
      'disponibilidad-espera',
      espera?.id,
      doctorElegido,
      fechaElegida,
      horaInicio,
      horaFin,
    ],
    queryFn: () =>
      consultarDisponibilidad({
        sede: espera!.sede,
        doctor: doctorElegido!,
        fecha: fechaElegida!,
        ...(rangoValido ? { hora_inicio: horaInicio!, hora_fin: horaFin! } : {}),
      }),
    enabled: abierto && !!espera && !!doctorElegido && !!fechaElegida,
  })

  useEffect(() => {
    if (!abierto || !espera) return
    form.resetFields()
    form.setFieldsValue({
      doctor: espera.doctor ?? undefined,
      tipo_trabajo: espera.tipo_trabajo ?? undefined,
      fecha:
        espera.fecha_deseada && espera.fecha_deseada >= fechaMinima
          ? espera.fecha_deseada
          : fechaMinima,
      hora_inicio: '09:00',
      hora_fin: '09:20',
    })
  }, [abierto, espera, form, fechaMinima])

  const ocupados = disponibilidad?.doctores[0]?.ocupados ?? []
  const horarioOcupado =
    rangoValido &&
    ocupados.some(
      (intervalo) => horaInicio! < intervalo.hora_fin && horaFin! > intervalo.hora_inicio,
    )
  const huecos = disponibilidad?.doctores[0]?.huecos ?? []
  const cerrada = disponibilidad?.abierta === false
  const sinHorario = disponibilidad?.horario_configurado === false
  const fueraDeHorario =
    rangoValido &&
    disponibilidad?.doctores[0]?.disponible === false &&
    !horarioOcupado &&
    !cerrada
  const tipoAviso: 'error' | 'warning' | 'info' =
    cerrada || horarioOcupado || fueraDeHorario ? 'error' : sinHorario ? 'warning' : 'info'
  const mensajeAviso = cerrada
    ? (disponibilidad?.motivo ?? 'La sede no abre ese día')
    : horarioOcupado
      ? 'Ese horario ya está ocupado'
      : fueraDeHorario
        ? 'El horario está fuera de la atención de la sede'
        : sinHorario
          ? 'La sede no tiene horario configurado'
          : 'Disponibilidad del doctor'
  const franjas = (disponibilidad?.abiertos ?? [])
    .map((intervalo) => `${intervalo.hora_inicio}–${intervalo.hora_fin}`)
    .join(' · ')
  const descripcionAviso = sinHorario
    ? 'Puedes agendar a cualquier hora; configura los horarios en Configuración.'
    : [
        franjas ? `Horario: ${franjas}` : null,
        ocupados.length > 0
          ? `Ocupados: ${ocupados
              .map((intervalo) => `${intervalo.hora_inicio}–${intervalo.hora_fin}`)
              .join(', ')}`
          : null,
        huecos.length > 0
          ? `Libres: ${huecos.slice(0, 12).join(', ')}${huecos.length > 12 ? '…' : ''}`
          : null,
      ]
        .filter(Boolean)
        .join(' · ') || undefined

  const agendar = useMutation({
    mutationFn: (datos: DatosAgendarEspera) => agendarEspera(espera!.id, datos),
    onSuccess: () => {
      message.success('Espera convertida en cita')
      cliente.invalidateQueries({ queryKey: ['lista-espera'] })
      cliente.invalidateQueries({ queryKey: ['atenciones'] })
      cliente.invalidateQueries({ queryKey: ['disponibilidad'] })
      cliente.invalidateQueries({ queryKey: ['disponibilidad-espera'] })
      cliente.invalidateQueries({ queryKey: ['dashboard'] })
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
      message.error(e instanceof ApiError ? e.message : 'No se pudo agendar la espera.')
    },
  })

  function enviar(valores: Valores) {
    agendar.mutate({
      fecha: valores.fecha,
      hora_inicio: valores.hora_inicio,
      hora_fin: valores.hora_fin,
      doctor: valores.doctor!,
      tipo_trabajo: valores.tipo_trabajo!,
      procedimiento: valores.procedimiento ?? '',
      observaciones: valores.observaciones ?? '',
      honorario_doctor: valores.honorario_doctor ?? 0,
    })
  }

  return (
    <Modal
      title="Agendar paciente en espera"
      open={abierto}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Crear cita"
      cancelText="Cancelar"
      confirmLoading={agendar.isPending}
      destroyOnHidden
      width={640}
    >
      {espera && (
        <Alert
          style={{ marginBottom: 16 }}
          type="info"
          showIcon
          message={`${espera.paciente_nombre} · ${espera.sede_nombre}`}
          description={[
            espera.tipo_trabajo_nombre ? `Trabajo: ${espera.tipo_trabajo_nombre}` : null,
            espera.motivo ? `Motivo: ${espera.motivo}` : null,
          ]
            .filter(Boolean)
            .join(' · ')}
        />
      )}
      <Form<Valores> form={form} layout="vertical" requiredMark={false} onFinish={enviar}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
          <Form.Item name="doctor" label="Doctor" rules={[{ required: true, message: 'Elige el doctor' }]}>
            <Select
              placeholder="Elige un doctor de la sede"
              options={doctores?.results.map((d) => ({
                value: d.id,
                label: `${d.nombres} ${d.apellidos}`,
              }))}
            />
          </Form.Item>
          <Form.Item
            name="tipo_trabajo"
            label="Tipo de trabajo"
            rules={[{ required: true, message: 'Elige el tipo de trabajo' }]}
          >
            <Select
              placeholder="Elige el tipo de trabajo"
              options={tipos?.results.map((t) => ({ value: t.id, label: t.nombre }))}
            />
          </Form.Item>
          <Form.Item name="fecha" label="Fecha" rules={[{ required: true, message: 'Elige la fecha' }]}>
            <Input type="date" min={fechaMinima} />
          </Form.Item>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 12 }}>
            <Form.Item name="hora_inicio" label="Hora inicio" rules={[{ required: true, message: 'Requerida' }]}>
              <Input type="time" />
            </Form.Item>
            <Form.Item name="hora_fin" label="Hora fin" rules={[{ required: true, message: 'Requerida' }]}>
              <Input type="time" />
            </Form.Item>
          </div>
          {disponibilidad && (
            <Alert
              style={{ gridColumn: '1 / -1' }}
              type={tipoAviso}
              showIcon
              message={mensajeAviso}
              description={descripcionAviso}
            />
          )}
        </div>
      </Form>
    </Modal>
  )
}
