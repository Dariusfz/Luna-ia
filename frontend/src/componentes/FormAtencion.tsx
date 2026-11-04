import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Alert, Form, Input, InputNumber, Modal, Select, message } from 'antd'
import { useEffect, useState } from 'react'

import {
  actualizarAtencion,
  consultarDisponibilidad,
  crearAtencion,
  type Atencion,
  type DatosAtencion,
} from '../api/atenciones'
import { ApiError } from '../api/cliente'
import { listarDoctores } from '../api/catalogos'
import { listarPacientes, listarSedes } from '../api/recursos'
import { listarTiposTrabajo } from '../api/catalogos'
import { ETIQUETA_ESTADO, ESTADOS_ATENCION } from '../constantes/atenciones'
import {
  MONTO_MAXIMO,
  MONTO_MAXIMO_LONGITUD,
  MONTO_MAXIMO_TEXTO,
  formatearMonto,
} from '../constantes/montos'

type Props = {
  abierto: boolean
  atencion: Atencion | null
  onCerrar: () => void
}

type Valores = Omit<
  DatosAtencion,
  'tipo_trabajo' | 'tipos_trabajo' | 'honorario_doctor'
> & {
  tipos_trabajo: number[]
  honorario_doctor: number | null
}

/** Registro y edición de una visita. El doctor se elige entre los asignados a la sede. */
export default function FormAtencion({ abierto, atencion, onCerrar }: Props) {
  const [form] = Form.useForm<Valores>()
  const cliente = useQueryClient()
  const editando = atencion !== null

  const [fechaMinima] = useState(() => {
    const hoy = new Date()
    const mes = String(hoy.getMonth() + 1).padStart(2, '0')
    const dia = String(hoy.getDate()).padStart(2, '0')
    return `${hoy.getFullYear()}-${mes}-${dia}`
  })

  const sedeElegida = Form.useWatch('sede', form)
  const doctorElegido = Form.useWatch('doctor', form)
  const fechaElegida = Form.useWatch('fecha', form)
  const horaInicio = Form.useWatch('hora_inicio', form)
  const horaFin = Form.useWatch('hora_fin', form)
  const estadoActual = Form.useWatch('estado', form)
  const tiposElegidos = Form.useWatch('tipos_trabajo', form) ?? []
  const rangoValido = !!horaInicio && !!horaFin && horaFin > horaInicio
  const [busqueda, setBusqueda] = useState('')
  const [nombres, setNombres] = useState<Record<number, string>>({})

  const { data: sedes } = useQuery({ queryKey: ['sedes', 'true'], queryFn: () => listarSedes('true') })
  const { data: doctores } = useQuery({
    queryKey: ['doctores-sede', sedeElegida],
    queryFn: () => listarDoctores(1, { sede: sedeElegida, activo: 'true' }),
    enabled: !!sedeElegida,
  })
  const { data: pacientes } = useQuery({
    queryKey: ['pacientes-buscar', busqueda],
    queryFn: () => listarPacientes(1, { q: busqueda, activo: 'true' }),
    enabled: abierto,
  })
  const { data: tipos } = useQuery({ queryKey: ['tipos-trabajo', 'true'], queryFn: () => listarTiposTrabajo('true') })
  const { data: disponibilidad } = useQuery({
    queryKey: [
      'disponibilidad',
      sedeElegida,
      doctorElegido,
      fechaElegida,
      horaInicio,
      horaFin,
    ],
    queryFn: () =>
      consultarDisponibilidad({
        sede: sedeElegida!,
        doctor: doctorElegido!,
        fecha: fechaElegida!,
        ...(rangoValido
          ? { hora_inicio: horaInicio!, hora_fin: horaFin! }
          : {}),
      }),
    enabled: abierto && !!sedeElegida && !!doctorElegido && !!fechaElegida,
  })

  // La cita que se está editando no debe contarse como ocupada.
  const ocupados = (disponibilidad?.doctores[0]?.ocupados ?? []).filter(
    (intervalo) => intervalo.atencion !== atencion?.id,
  )
  const horarioOcupado =
    !!horaInicio &&
    !!horaFin &&
    horaFin > horaInicio &&
    ocupados.some(
      (intervalo) => horaInicio < intervalo.hora_fin && horaFin > intervalo.hora_inicio,
    )

  const huecos = disponibilidad?.doctores[0]?.huecos ?? []
  const precioTotal = tiposElegidos.reduce((total, id) => {
    const tipo = tipos?.results.find((item) => item.id === id)
    return total + (tipo ? Number(tipo.precio) : 0)
  }, 0)
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
  const franjasConfiguradas = (disponibilidad?.horarios ?? [])
    .map((intervalo) => `${intervalo.hora_inicio}–${intervalo.hora_fin}`)
    .join(' · ')
  const descripcionAviso = sinHorario
    ? 'Puedes agendar a cualquier hora; configura los horarios en Configuración.'
    : cerrada
      ? franjasConfiguradas
        ? `Horario habitual: ${franjasConfiguradas}`
        : undefined
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

  useEffect(() => {
    if (!abierto) return
    setBusqueda('')
    if (atencion) {
      setNombres({ [atencion.paciente]: atencion.paciente_nombre })
      form.setFieldsValue({
        sede: atencion.sede,
        doctor: atencion.doctor,
        paciente: atencion.paciente,
        tipos_trabajo: atencion.trabajos.length
          ? atencion.trabajos.map((trabajo) => trabajo.tipo_trabajo)
          : [atencion.tipo_trabajo],
        estado: atencion.estado,
        fecha: atencion.fecha,
        hora_inicio: atencion.hora_inicio.slice(0, 5),
        hora_fin: atencion.hora_fin.slice(0, 5),
        procedimiento: atencion.procedimiento,
        honorario_doctor: Number(atencion.honorario_doctor),
        observaciones: atencion.observaciones,
      })
    } else {
      setNombres({})
      form.resetFields()
      form.setFieldsValue({ estado: 'pendiente' })
    }
  }, [abierto, atencion, form])

  // Al cambiar de sede, el doctor elegido ya no aplica.
  useEffect(() => {
    if (!editando || sedeElegida !== atencion?.sede) form.setFieldValue('doctor', undefined)
  }, [sedeElegida]) // eslint-disable-line react-hooks/exhaustive-deps

  // Guarda el nombre de cada paciente visto, para mostrarlo aunque deje de salir en la búsqueda.
  useEffect(() => {
    if (!pacientes) return
    setNombres((previo) => {
      const nuevo = { ...previo }
      pacientes.results.forEach((p) => {
        nuevo[p.id] = `${p.nombres} ${p.apellidos}`
      })
      return nuevo
    })
  }, [pacientes])

  const guardar = useMutation({
    mutationFn: (datos: DatosAtencion) =>
      editando ? actualizarAtencion(atencion.id, datos) : crearAtencion(datos),
    onSuccess: () => {
      message.success(editando ? 'Cita actualizada' : 'Cita creada')
      cliente.invalidateQueries({ queryKey: ['atenciones'] })
      cliente.invalidateQueries({ queryKey: ['disponibilidad'] })
      cliente.invalidateQueries({ queryKey: ['caja'] })
      onCerrar()
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.campos).length > 0) {
        form.setFields(
          Object.entries(e.campos).map(([nombre, error]) => ({ name: nombre as keyof Valores, errors: [error] })),
        )
      }
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar la atención.')
    },
  })

  function enviar(valores: Valores) {
    const tipos = valores.tipos_trabajo ?? []
    guardar.mutate({
      ...valores,
      tipo_trabajo: tipos[0],
      tipos_trabajo: tipos,
      estado: editando ? (valores.estado ?? 'pendiente') : 'pendiente',
      procedimiento: valores.procedimiento ?? '',
      observaciones: valores.observaciones ?? '',
      honorario_doctor: valores.honorario_doctor ?? 0,
    })
  }

  return (
    <Modal
      title={editando ? 'Editar cita' : 'Nueva cita'}
      open={abierto}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Guardar"
      cancelText="Cancelar"
      confirmLoading={guardar.isPending}
      destroyOnHidden
      width={680}
    >
      <Form<Valores> form={form} layout="vertical" requiredMark={false} onFinish={enviar}>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
          <Form.Item name="sede" label="Sede" rules={[{ required: true, message: 'Elige la sede' }]}>
            <Select
              placeholder="Elige una sede"
              options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre }))}
            />
          </Form.Item>
          <Form.Item name="doctor" label="Doctor" rules={[{ required: true, message: 'Elige el doctor' }]}>
            <Select
              placeholder={sedeElegida ? 'Elige un doctor de esta sede' : 'Primero elige la sede'}
              disabled={!sedeElegida}
              options={doctores?.results.map((d) => ({ value: d.id, label: `${d.nombres} ${d.apellidos}` }))}
            />
          </Form.Item>
          <Form.Item name="paciente" label="Paciente" rules={[{ required: true, message: 'Elige el paciente' }]}>
            <Select
              showSearch
              filterOption={false}
              onSearch={setBusqueda}
              placeholder="Escribe nombre, identidad o teléfono"
              options={Object.entries(nombres).map(([id, nombre]) => ({ value: Number(id), label: nombre }))}
            />
          </Form.Item>
          <Form.Item
            name="tipos_trabajo"
            label="Tipos de trabajo"
            rules={[{ required: true, message: 'Elige al menos un tipo de trabajo' }]}
          >
            <Select
              mode="multiple"
              placeholder="Elige uno o varios tipos de trabajo"
              options={tipos?.results.map((t) => ({ value: t.id, label: t.nombre }))}
            />
          </Form.Item>
          {editando ? (
            <Form.Item name="estado" label="Estado" rules={[{ required: true, message: 'Elige el estado' }]}>
              <Select options={ESTADOS_ATENCION.map((e) => ({ value: e, label: ETIQUETA_ESTADO[e] }))} />
            </Form.Item>
          ) : (
            <Form.Item label="Estado">
              <Select
                value="pendiente"
                disabled
                options={[{ value: 'pendiente', label: ETIQUETA_ESTADO.pendiente }]}
              />
            </Form.Item>
          )}
          <Form.Item name="fecha" label="Fecha" rules={[{ required: true, message: 'Elige la fecha' }]}>
            <Input type="date" min={editando ? undefined : fechaMinima} />
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
          <Form.Item
            label="Precio total al paciente (HNL)"
            extra="Se calcula automáticamente con los precios de los tipos de trabajo."
          >
            <Input
              value={`L ${precioTotal.toLocaleString('es-HN', { minimumFractionDigits: 2 })}`}
              disabled
            />
          </Form.Item>
          <Form.Item
            name="honorario_doctor"
            label="Comisión / honorario del doctor (HNL)"
            extra={estadoActual === 'completada' ? 'Obligatorio al completar la cita.' : 'Puedes dejarlo en 0 mientras la cita está pendiente.'}
            rules={[
              {
                required: estadoActual === 'completada',
                message: 'Registra el honorario al completar la cita',
              },
              {
                type: 'number',
                max: MONTO_MAXIMO,
                message: `El honorario no puede superar ${MONTO_MAXIMO_TEXTO}.`,
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
                  form.setFieldValue('honorario_doctor', MONTO_MAXIMO)
                }
              }}
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item name="procedimiento" label="Detalle del procedimiento">
            <Input placeholder="Ej.: extracción pieza 36 con anestesia" />
          </Form.Item>
        </div>
        <Form.Item name="observaciones" label="Observaciones">
          <Input.TextArea rows={2} />
        </Form.Item>
      </Form>
    </Modal>
  )
}
