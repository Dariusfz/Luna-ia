import { DeleteOutlined, EditOutlined, HistoryOutlined, PlusOutlined } from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Col,
  Collapse,
  Descriptions,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Row,
  Select,
  Space,
  Tag,
  Typography,
  message,
} from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { ApiError } from '../api/cliente'
import { listarDoctores } from '../api/catalogos'
import {
  actualizarHistoria,
  actualizarOdontograma,
  crearHistoria,
  crearOdontograma,
  historialHistoria,
  historialOdontograma,
  listarHistorias,
  listarOdontogramas,
  type DatosHallazgo,
  type HistoriaClinica as Historia,
  type Odontograma,
  type RegistroHistorial,
} from '../api/historiaClinica'
import { listarPacientes, listarSedes, obtenerPaciente } from '../api/recursos'
import OdontogramaDental from '../componentes/OdontogramaDental'
import {
  CARAS_DENTALES,
  COLOR_POR_ESTADO,
  ESTADOS_DENTALES,
} from '../componentes/odontogramaConstantes'

const hoy = () => new Date().toISOString().slice(0, 10)

export default function HistoriaClinica() {
  const cliente = useQueryClient()
  const [parametros, setParametros] = useSearchParams()
  const pacienteId = Number(parametros.get('paciente')) || null

  const [textoPaciente, setTextoPaciente] = useState('')
  const [qPaciente, setQPaciente] = useState('')
  const [historiaAbierta, setHistoriaAbierta] = useState(false)
  const [historiaEditando, setHistoriaEditando] = useState<Historia | null>(null)
  const [odontogramaAbierto, setOdontogramaAbierto] = useState(false)
  const [odontogramaEditando, setOdontogramaEditando] = useState<Odontograma | null>(null)

  const [hallazgosBorrador, setHallazgosBorrador] = useState<DatosHallazgo[]>([])
  const [dienteSeleccionado, setDienteSeleccionado] = useState<number | null>(null)
  const [nuevoHallazgo, setNuevoHallazgo] = useState<{
    cara?: string
    estado: string
    observacion: string
  }>({ estado: 'caries', observacion: '' })

  const [auditoria, setAuditoria] = useState<{ titulo: string; registros: RegistroHistorial[] } | null>(
    null,
  )
  const [cargandoAuditoria, setCargandoAuditoria] = useState(false)

  const [formHistoria] = Form.useForm()
  const [formOdontograma] = Form.useForm()

  useEffect(() => {
    const espera = setTimeout(() => setQPaciente(textoPaciente.trim()), 300)
    return () => clearTimeout(espera)
  }, [textoPaciente])

  const { data: pacientes, isFetching: buscandoPacientes } = useQuery({
    queryKey: ['pacientes', 'historia-busqueda', qPaciente],
    queryFn: () => listarPacientes(1, { q: qPaciente, activo: 'true' }),
    placeholderData: keepPreviousData,
  })

  const { data: paciente } = useQuery({
    queryKey: ['paciente', pacienteId],
    queryFn: () => obtenerPaciente(pacienteId!),
    enabled: !!pacienteId,
  })

  const { data: sedes } = useQuery({ queryKey: ['sedes', 'todas'], queryFn: () => listarSedes('todas') })
  const { data: doctores } = useQuery({
    queryKey: ['doctores', 'activos-historia'],
    queryFn: () => listarDoctores(1, { activo: 'true' }),
  })

  const { data: historias, isPending: cargandoHistorias } = useQuery({
    queryKey: ['historias', pacienteId],
    queryFn: () => listarHistorias(pacienteId!),
    enabled: !!pacienteId,
  })

  const { data: odontogramas, isPending: cargandoOdontogramas } = useQuery({
    queryKey: ['odontogramas', pacienteId],
    queryFn: () => listarOdontogramas(pacienteId!),
    enabled: !!pacienteId,
  })

  const opcionesSede = useMemo(
    () => sedes?.results.map((s) => ({ value: s.id, label: s.nombre })) ?? [],
    [sedes],
  )
  const opcionesDoctor = useMemo(
    () =>
      doctores?.results.map((d) => ({
        value: d.id,
        label: `${d.nombres} ${d.apellidos}`,
      })) ?? [],
    [doctores],
  )

  const hallazgosPieza = useMemo(
    () => hallazgosBorrador.filter((h) => h.diente === dienteSeleccionado),
    [hallazgosBorrador, dienteSeleccionado],
  )

  function elegirPaciente(id: number) {
    setParametros({ paciente: String(id) })
  }

  const guardarHistoria = useMutation({
    mutationFn: crearHistoria,
    onSuccess: () => {
      message.success('Entrada de historia clínica guardada')
      cerrarHistoria()
      cliente.invalidateQueries({ queryKey: ['historias', pacienteId] })
    },
    onError: (e) =>
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar la historia.'),
  })

  const editarHistoria = useMutation({
    mutationFn: ({ id, datos }: { id: number; datos: Parameters<typeof crearHistoria>[0] }) =>
      actualizarHistoria(id, datos),
    onSuccess: () => {
      message.success('Entrada de historia clínica actualizada')
      cerrarHistoria()
      cliente.invalidateQueries({ queryKey: ['historias', pacienteId] })
    },
    onError: (e) =>
      message.error(e instanceof ApiError ? e.message : 'No se pudo actualizar la historia.'),
  })

  const guardarOdontograma = useMutation({
    mutationFn: crearOdontograma,
    onSuccess: () => {
      message.success('Odontograma guardado')
      cerrarOdontograma()
      cliente.invalidateQueries({ queryKey: ['odontogramas', pacienteId] })
    },
    onError: (e) =>
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar el odontograma.'),
  })

  const editarOdontograma = useMutation({
    mutationFn: ({
      id,
      datos,
    }: {
      id: number
      datos: Parameters<typeof crearOdontograma>[0]
    }) => actualizarOdontograma(id, datos),
    onSuccess: () => {
      message.success('Odontograma actualizado')
      cerrarOdontograma()
      cliente.invalidateQueries({ queryKey: ['odontogramas', pacienteId] })
    },
    onError: (e) =>
      message.error(e instanceof ApiError ? e.message : 'No se pudo actualizar el odontograma.'),
  })

  const quitarHallazgoGuardado = useMutation({
    mutationFn: ({
      odontograma,
      hallazgoId,
    }: {
      odontograma: Odontograma
      hallazgoId: number
    }) =>
      actualizarOdontograma(odontograma.id, {
        paciente: odontograma.paciente,
        sede: odontograma.sede,
        doctor: odontograma.doctor,
        fecha: odontograma.fecha,
        notas: odontograma.notas,
        hallazgos: odontograma.hallazgos
          .filter((h) => h.id !== hallazgoId)
          .map((h) => ({
            diente: h.diente,
            cara: h.cara,
            estado: h.estado,
            observacion: h.observacion,
          })),
      }),
    onSuccess: () => {
      message.success('Hallazgo eliminado')
      cliente.invalidateQueries({ queryKey: ['odontogramas', pacienteId] })
    },
    onError: (e) =>
      message.error(e instanceof ApiError ? e.message : 'No se pudo eliminar el hallazgo.'),
  })

  function abrirHistoria() {
    setHistoriaEditando(null)
    formHistoria.setFieldsValue({
      fecha: hoy(),
      sede: paciente?.sede_origen ?? undefined,
    })
    setHistoriaAbierta(true)
  }

  function abrirEditarHistoria(h: Historia) {
    setHistoriaEditando(h)
    formHistoria.setFieldsValue({
      fecha: h.fecha,
      sede: h.sede,
      doctor: h.doctor,
      motivo_consulta: h.motivo_consulta,
      enfermedad_actual: h.enfermedad_actual,
      examen_clinico: h.examen_clinico,
      diagnostico: h.diagnostico,
      plan_tratamiento: h.plan_tratamiento,
      notas: h.notas,
    })
    setHistoriaAbierta(true)
  }

  function cerrarHistoria() {
    setHistoriaAbierta(false)
    setHistoriaEditando(null)
    formHistoria.resetFields()
  }

  function abrirOdontograma() {
    setOdontogramaEditando(null)
    formOdontograma.setFieldsValue({
      fecha: hoy(),
      sede: paciente?.sede_origen ?? undefined,
    })
    setNuevoHallazgo({ estado: 'caries', observacion: '' })
    setHallazgosBorrador([])
    setDienteSeleccionado(null)
    setOdontogramaAbierto(true)
  }

  function abrirEditarOdontograma(o: Odontograma) {
    setOdontogramaEditando(o)
    formOdontograma.setFieldsValue({
      fecha: o.fecha,
      sede: o.sede,
      doctor: o.doctor ?? undefined,
      notas: o.notas,
    })
    setHallazgosBorrador(
      o.hallazgos.map((h) => ({
        diente: h.diente,
        cara: h.cara,
        estado: h.estado,
        observacion: h.observacion,
      })),
    )
    setNuevoHallazgo({ estado: 'caries', observacion: '' })
    setDienteSeleccionado(null)
    setOdontogramaAbierto(true)
  }

  function cerrarOdontograma() {
    setOdontogramaAbierto(false)
    setOdontogramaEditando(null)
    formOdontograma.resetFields()
    setNuevoHallazgo({ estado: 'caries', observacion: '' })
    setHallazgosBorrador([])
    setDienteSeleccionado(null)
  }

  async function enviarHistoria() {
    let valores
    try {
      valores = await formHistoria.validateFields()
    } catch {
      return
    }
    const datos = {
      paciente: pacienteId!,
      sede: valores.sede,
      doctor: valores.doctor,
      fecha: valores.fecha,
      motivo_consulta: valores.motivo_consulta ?? '',
      enfermedad_actual: valores.enfermedad_actual ?? '',
      examen_clinico: valores.examen_clinico ?? '',
      diagnostico: valores.diagnostico ?? '',
      plan_tratamiento: valores.plan_tratamiento ?? '',
      notas: valores.notas ?? '',
    }
    if (historiaEditando) {
      editarHistoria.mutate({ id: historiaEditando.id, datos })
    } else {
      guardarHistoria.mutate(datos)
    }
  }

  async function enviarOdontograma() {
    let valores
    try {
      valores = await formOdontograma.validateFields()
    } catch {
      return
    }
    const datos = {
      paciente: pacienteId!,
      sede: valores.sede,
      doctor: valores.doctor ?? null,
      fecha: valores.fecha,
      notas: valores.notas ?? '',
      hallazgos: hallazgosBorrador,
    }
    if (odontogramaEditando) {
      editarOdontograma.mutate({ id: odontogramaEditando.id, datos })
    } else {
      guardarOdontograma.mutate(datos)
    }
  }

  function agregarHallazgo() {
    if (!dienteSeleccionado) {
      message.warning('Primero haz clic en un diente.')
      return
    }
    if (!nuevoHallazgo.estado) {
      message.warning('Elige el estado de la pieza.')
      return
    }
    const cara = nuevoHallazgo.cara ?? ''
    const repetido = hallazgosBorrador.some(
      (h) => h.diente === dienteSeleccionado && (h.cara ?? '') === cara,
    )
    if (repetido) {
      message.warning('Ya hay un hallazgo para esa pieza y cara. Elimínalo si quieres cambiarlo.')
      return
    }
    setHallazgosBorrador((previos) => [
      ...previos,
      {
        diente: dienteSeleccionado,
        cara: cara as DatosHallazgo['cara'],
        estado: nuevoHallazgo.estado as DatosHallazgo['estado'],
        observacion: nuevoHallazgo.observacion,
      },
    ])
    setNuevoHallazgo({ estado: nuevoHallazgo.estado, observacion: '' })
  }

  function quitarHallazgo(diente: number, cara: string) {
    setHallazgosBorrador((previos) =>
      previos.filter((h) => !(h.diente === diente && (h.cara ?? '') === cara)),
    )
  }

  function copiarUltimoOdontograma() {
    const ultimo = odontogramas?.results[0]
    if (!ultimo) {
      message.info('Todavía no hay un odontograma para copiar.')
      return
    }
    setHallazgosBorrador(
      ultimo.hallazgos.map((h) => ({
        diente: h.diente,
        cara: h.cara,
        estado: h.estado,
        observacion: h.observacion,
      })),
    )
    message.success(`Se copiaron ${ultimo.hallazgos.length} hallazgo(s) del ${ultimo.fecha}.`)
  }

  async function verAuditoria(tipo: 'historia' | 'odontograma', id: number, etiqueta: string) {
    setCargandoAuditoria(true)
    setAuditoria({ titulo: etiqueta, registros: [] })
    try {
      const registros =
        tipo === 'historia' ? await historialHistoria(id) : await historialOdontograma(id)
      setAuditoria({ titulo: etiqueta, registros })
    } catch (e) {
      message.error(e instanceof ApiError ? e.message : 'No se pudo cargar la auditoría.')
      setAuditoria(null)
    } finally {
      setCargandoAuditoria(false)
    }
  }

  function valorTexto(valor: unknown) {
    if (valor === null || valor === undefined || valor === '') return '-'
    if (typeof valor === 'string' || typeof valor === 'number' || typeof valor === 'boolean') {
      return String(valor)
    }
    return JSON.stringify(valor)
  }

  return (
    <Card>
      <Space style={{ width: '100%', justifyContent: 'space-between', marginBottom: 16 }} wrap>
        <Typography.Title level={4} style={{ margin: 0 }}>
          Historia clínica
        </Typography.Title>
        <Select
          showSearch
          allowClear
          placeholder="Buscar paciente por nombre"
          style={{ width: 360 }}
          value={pacienteId ?? undefined}
          onSearch={setTextoPaciente}
          onChange={(v) => (v ? elegirPaciente(v) : setParametros({}))}
          filterOption={false}
          loading={buscandoPacientes}
          options={(pacientes?.results ?? []).map((p) => ({
            value: p.id,
            label: `${p.nombres} ${p.apellidos}`,
          }))}
        />
      </Space>

      {!pacienteId ? (
        <Empty description="Selecciona un paciente para ver su historia clínica." />
      ) : (
        <>
          {paciente && (
            <Descriptions bordered size="small" column={{ xs: 1, md: 2 }} style={{ marginBottom: 16 }}>
              <Descriptions.Item label="Paciente">
                {paciente.nombres} {paciente.apellidos}
              </Descriptions.Item>
              <Descriptions.Item label="Identidad">{paciente.identidad || '-'}</Descriptions.Item>
              <Descriptions.Item label="Alergias">{paciente.alergias || 'Ninguna registrada'}</Descriptions.Item>
              <Descriptions.Item label="Antecedentes">
                {paciente.antecedentes_medicos || 'Sin antecedentes registrados'}
              </Descriptions.Item>
              <Descriptions.Item label="Medicamentos" span={2}>
                {paciente.medicamentos_actuales || 'Ninguno registrado'}
              </Descriptions.Item>
            </Descriptions>
          )}

          <Row gutter={[16, 16]}>
            <Col xs={24} xl={12}>
              <Card
                size="small"
                title="Entradas de historia clínica"
                extra={
                  <Button type="primary" size="small" icon={<PlusOutlined />} onClick={abrirHistoria}>
                    Nueva entrada
                  </Button>
                }
                loading={cargandoHistorias}
              >
                {(historias?.results.length ?? 0) === 0 ? (
                  <Empty description="Sin entradas registradas." />
                ) : (
                  <Collapse
                    size="small"
                    defaultActiveKey={[String(historias?.results[0]?.id)]}
                    items={(historias?.results ?? []).map((h: Historia) => ({
                      key: String(h.id),
                      label: (
                        <Space wrap size={8}>
                          <Typography.Text strong>{h.fecha}</Typography.Text>
                          <Tag>{h.sede_nombre}</Tag>
                          <Typography.Text type="secondary">{h.doctor_nombre}</Typography.Text>
                        </Space>
                      ),
                      children: (
                        <>
                          <Descriptions size="small" column={1} bordered>
                            <Descriptions.Item label="Motivo de consulta">
                              {h.motivo_consulta || '-'}
                            </Descriptions.Item>
                            <Descriptions.Item label="Enfermedad actual">
                              {h.enfermedad_actual || '-'}
                            </Descriptions.Item>
                            <Descriptions.Item label="Examen clínico">
                              {h.examen_clinico || '-'}
                            </Descriptions.Item>
                            <Descriptions.Item label="Diagnóstico">{h.diagnostico || '-'}</Descriptions.Item>
                            <Descriptions.Item label="Plan de tratamiento">
                              {h.plan_tratamiento || '-'}
                            </Descriptions.Item>
                            <Descriptions.Item label="Notas">{h.notas || '-'}</Descriptions.Item>
                          </Descriptions>
                          <Space size={0}>
                            <Button
                              size="small"
                              type="link"
                              icon={<EditOutlined />}
                              style={{ paddingLeft: 0 }}
                              onClick={() => abrirEditarHistoria(h)}
                            >
                              Editar
                            </Button>
                            <Button
                              size="small"
                              type="link"
                              icon={<HistoryOutlined />}
                              onClick={() =>
                                verAuditoria('historia', h.id, `Auditoría de la historia del ${h.fecha}`)
                              }
                            >
                              Ver auditoría
                            </Button>
                          </Space>
                        </>
                      ),
                    }))}
                  />
                )}
              </Card>
            </Col>

            <Col xs={24} xl={12}>
              <Card
                size="small"
                title="Odontogramas"
                extra={
                  <Button type="primary" size="small" icon={<PlusOutlined />} onClick={abrirOdontograma}>
                    Nuevo odontograma
                  </Button>
                }
                loading={cargandoOdontogramas}
              >
                {(odontogramas?.results.length ?? 0) === 0 ? (
                  <Empty description="Sin odontogramas registrados." />
                ) : (
                  <Collapse
                    size="small"
                    defaultActiveKey={[String(odontogramas?.results[0]?.id)]}
                    items={(odontogramas?.results ?? []).map((o: Odontograma) => ({
                      key: String(o.id),
                      label: (
                        <Space wrap size={8}>
                          <Typography.Text strong>{o.fecha}</Typography.Text>
                          <Tag>{o.sede_nombre}</Tag>
                          <Typography.Text type="secondary">
                            {o.hallazgos.length} hallazgo(s)
                          </Typography.Text>
                          {o.doctor_nombre && (
                            <Typography.Text type="secondary">{o.doctor_nombre}</Typography.Text>
                          )}
                        </Space>
                      ),
                      children: (
                        <>
                          <OdontogramaDental hallazgos={o.hallazgos} mostrarDetalle />
                          {o.hallazgos.length > 0 && (
                            <Space wrap size={6} style={{ marginTop: 8 }}>
                              {o.hallazgos.map((h) => (
                                <Space key={h.id} size={2}>
                                  <Tag color={COLOR_POR_ESTADO[h.estado]}>
                                    {h.diente} ·{' '}
                                    {ESTADOS_DENTALES.find((e) => e.value === h.estado)?.label ?? h.estado}
                                  </Tag>
                                  <Popconfirm
                                    title={`¿Quitar el hallazgo de la pieza ${h.diente}?`}
                                    okText="Quitar"
                                    cancelText="Cancelar"
                                    onConfirm={() => quitarHallazgoGuardado.mutate({ odontograma: o, hallazgoId: h.id })}
                                  >
                                    <Button
                                      size="small"
                                      type="text"
                                      danger
                                      disabled={quitarHallazgoGuardado.isPending}
                                      icon={<DeleteOutlined />}
                                      aria-label={`Quitar hallazgo de la pieza ${h.diente}`}
                                    />
                                  </Popconfirm>
                                </Space>
                              ))}
                            </Space>
                          )}
                          {o.notas && (
                            <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                              {o.notas}
                            </Typography.Paragraph>
                          )}
                          <Space size={0}>
                            <Button
                              size="small"
                              type="link"
                              icon={<EditOutlined />}
                              style={{ paddingLeft: 0 }}
                              onClick={() => abrirEditarOdontograma(o)}
                            >
                              Editar
                            </Button>
                            <Button
                              size="small"
                              type="link"
                              icon={<HistoryOutlined />}
                              onClick={() =>
                                verAuditoria('odontograma', o.id, `Auditoría del odontograma del ${o.fecha}`)
                              }
                            >
                              Ver auditoría
                            </Button>
                          </Space>
                        </>
                      ),
                    }))}
                  />
                )}
              </Card>
            </Col>
          </Row>
        </>
      )}

      <Modal
        title={historiaEditando ? 'Editar entrada de historia clínica' : 'Nueva entrada de historia clínica'}
        open={historiaAbierta}
        onCancel={cerrarHistoria}
        onOk={() => {
          void enviarHistoria()
        }}
        okText="Guardar"
        cancelText="Cancelar"
        confirmLoading={guardarHistoria.isPending || editarHistoria.isPending}
        forceRender
        width={680}
      >
        <Form form={formHistoria} layout="vertical">
          <Row gutter={12}>
            <Col xs={24} md={12}>
              <Form.Item name="fecha" label="Fecha" rules={[{ required: true, message: 'Elige la fecha' }]}>
                <Input type="date" />
              </Form.Item>
            </Col>
            <Col xs={24} md={12}>
              <Form.Item name="sede" label="Sede" rules={[{ required: true, message: 'Elige la sede' }]}>
                <Select options={opcionesSede} placeholder="Sede" />
              </Form.Item>
            </Col>
          </Row>
          <Form.Item name="doctor" label="Doctor" rules={[{ required: true, message: 'Elige el doctor' }]}>
            <Select options={opcionesDoctor} placeholder="Doctor" showSearch optionFilterProp="label" />
          </Form.Item>
          <Form.Item name="motivo_consulta" label="Motivo de consulta">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="enfermedad_actual" label="Enfermedad actual">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="examen_clinico" label="Examen clínico">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="diagnostico" label="Diagnóstico">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="plan_tratamiento" label="Plan de tratamiento">
            <Input.TextArea rows={2} />
          </Form.Item>
          <Form.Item name="notas" label="Notas">
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={odontogramaEditando ? 'Editar odontograma' : 'Nuevo odontograma'}
        open={odontogramaAbierto}
        onCancel={cerrarOdontograma}
        onOk={() => {
          void enviarOdontograma()
        }}
        okText="Guardar"
        cancelText="Cancelar"
        confirmLoading={guardarOdontograma.isPending || editarOdontograma.isPending}
        forceRender
        width={900}
      >
        <Form form={formOdontograma} layout="vertical">
          <Row gutter={12}>
            <Col xs={24} md={8}>
              <Form.Item name="fecha" label="Fecha" rules={[{ required: true, message: 'Elige la fecha' }]}>
                <Input type="date" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="sede" label="Sede" rules={[{ required: true, message: 'Elige la sede' }]}>
                <Select options={opcionesSede} placeholder="Sede" />
              </Form.Item>
            </Col>
            <Col xs={24} md={8}>
              <Form.Item name="doctor" label="Doctor">
                <Select allowClear options={opcionesDoctor} placeholder="Opcional" showSearch optionFilterProp="label" />
              </Form.Item>
            </Col>
          </Row>

          <Alert
            type="info"
            showIcon
            style={{ marginBottom: 12 }}
            message="Haz clic en un diente para registrar hallazgos. Las piezas con información se pintan según el estado."
            action={
              (odontogramas?.results.length ?? 0) > 0 ? (
                <Button size="small" onClick={copiarUltimoOdontograma}>
                  Copiar último
                </Button>
              ) : undefined
            }
          />

          <OdontogramaDental
            hallazgos={hallazgosBorrador}
            seleccionado={dienteSeleccionado}
            onSeleccionar={setDienteSeleccionado}
          />

          <Card
            size="small"
            style={{ marginTop: 16 }}
            title={dienteSeleccionado ? `Pieza ${dienteSeleccionado}` : 'Selecciona una pieza'}
            extra={
              hallazgosBorrador.length > 0 ? (
                <Button size="small" danger type="text" onClick={() => setHallazgosBorrador([])}>
                  Quitar todos ({hallazgosBorrador.length})
                </Button>
              ) : undefined
            }
          >
            {!dienteSeleccionado ? (
              <Typography.Text type="secondary">
                Haz clic en un diente del odontograma para ver o registrar su información.
              </Typography.Text>
            ) : (
              <>
                {hallazgosPieza.length === 0 ? (
                  <Typography.Text type="secondary">
                    Esta pieza todavía no tiene información registrada.
                  </Typography.Text>
                ) : (
                  <List
                    size="small"
                    dataSource={hallazgosPieza}
                    renderItem={(h) => (
                      <List.Item
                        actions={[
                          <Button
                            key="quitar"
                            danger
                            type="text"
                            size="small"
                            icon={<DeleteOutlined />}
                            aria-label="Quitar hallazgo"
                            onClick={() => quitarHallazgo(h.diente, h.cara ?? '')}
                          />,
                        ]}
                      >
                        <Space wrap size={8}>
                          <Tag color={COLOR_POR_ESTADO[h.estado]}>
                            {ESTADOS_DENTALES.find((e) => e.value === h.estado)?.label ?? h.estado}
                          </Tag>
                          <Typography.Text type="secondary">
                            {h.cara
                              ? CARAS_DENTALES.find((c) => c.value === h.cara)?.label ?? h.cara
                              : 'Toda la pieza'}
                          </Typography.Text>
                          {h.observacion && <Typography.Text>{h.observacion}</Typography.Text>}
                        </Space>
                      </List.Item>
                    )}
                  />
                )}

                <Space wrap style={{ marginTop: 8 }}>
                  <Select
                    allowClear
                    value={nuevoHallazgo.cara}
                    onChange={(v) => setNuevoHallazgo((p) => ({ ...p, cara: v }))}
                    options={CARAS_DENTALES}
                    placeholder="Cara (opcional)"
                    style={{ width: 150 }}
                  />
                  <Select
                    value={nuevoHallazgo.estado}
                    onChange={(v) => setNuevoHallazgo((p) => ({ ...p, estado: v }))}
                    options={ESTADOS_DENTALES}
                    placeholder="Estado"
                    style={{ width: 160 }}
                  />
                  <Input
                    value={nuevoHallazgo.observacion}
                    onChange={(e) => setNuevoHallazgo((p) => ({ ...p, observacion: e.target.value }))}
                    placeholder="Observación"
                    style={{ width: 220 }}
                  />
                  <Button icon={<PlusOutlined />} onClick={agregarHallazgo}>
                    Agregar hallazgo
                  </Button>
                </Space>
              </>
            )}
          </Card>

          <Form.Item name="notas" label="Notas" style={{ marginTop: 12 }}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={auditoria?.titulo ?? 'Auditoría'}
        open={auditoria !== null}
        onCancel={() => setAuditoria(null)}
        footer={null}
        width={640}
        loading={cargandoAuditoria}
      >
        {auditoria && auditoria.registros.length === 0 && !cargandoAuditoria ? (
          <Empty description="Sin registros de auditoría." />
        ) : (
          <List
            size="small"
            dataSource={auditoria?.registros ?? []}
            renderItem={(r) => (
              <List.Item>
                <Space direction="vertical" size={2} style={{ width: '100%' }}>
                  <Space wrap size={8}>
                    <Tag>{r.tipo_nombre}</Tag>
                    <Typography.Text strong>{valorTexto(r.fecha)}</Typography.Text>
                    <Typography.Text type="secondary">{r.usuario_nombre}</Typography.Text>
                  </Space>
                  {r.cambios.length === 0 ? (
                    <Typography.Text type="secondary">Sin cambios de campos.</Typography.Text>
                  ) : (
                    r.cambios.map((c) => (
                      <Typography.Text key={c.campo} style={{ fontSize: 12 }}>
                        <strong>{c.campo}:</strong> {valorTexto(c.antes)} → {valorTexto(c.despues)}
                      </Typography.Text>
                    ))
                  )}
                </Space>
              </List.Item>
            )}
          />
        )}
      </Modal>
    </Card>
  )
}
