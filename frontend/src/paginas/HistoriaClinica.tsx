import { DeleteOutlined, PlusOutlined } from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Col,
  Descriptions,
  Divider,
  Empty,
  Form,
  Input,
  InputNumber,
  Modal,
  Row,
  Select,
  Space,
  Table,
  Tag,
  Timeline,
  Typography,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { ApiError } from '../api/cliente'
import { listarDoctores } from '../api/catalogos'
import {
  crearHistoria,
  crearOdontograma,
  listarHistorias,
  listarOdontogramas,
  type DatosHallazgo,
  type HistoriaClinica as Historia,
  type HallazgoDental,
  type Odontograma,
} from '../api/historiaClinica'
import { listarPacientes, listarSedes, obtenerPaciente } from '../api/recursos'

const CARAS = [
  { value: 'oclusal', label: 'Oclusal' },
  { value: 'mesial', label: 'Mesial' },
  { value: 'distal', label: 'Distal' },
  { value: 'vestibular', label: 'Vestibular' },
  { value: 'lingual', label: 'Lingual/Palatino' },
]

const ESTADOS = [
  { value: 'sano', label: 'Sano' },
  { value: 'caries', label: 'Caries' },
  { value: 'obturado', label: 'Obturado' },
  { value: 'corona', label: 'Corona' },
  { value: 'endodoncia', label: 'Endodoncia' },
  { value: 'ausente', label: 'Ausente' },
  { value: 'extraccion_indicada', label: 'Extracción indicada' },
  { value: 'implante', label: 'Implante' },
  { value: 'sellante', label: 'Sellante' },
  { value: 'fractura', label: 'Fractura' },
  { value: 'protesis', label: 'Prótesis' },
]

const COLOR_ESTADO: Record<string, string> = {
  sano: 'green',
  caries: 'red',
  obturado: 'blue',
  corona: 'gold',
  endodoncia: 'purple',
  ausente: 'default',
  extraccion_indicada: 'volcano',
  implante: 'cyan',
  sellante: 'lime',
  fractura: 'magenta',
  protesis: 'geekblue',
}

const hoy = () => new Date().toISOString().slice(0, 10)

export default function HistoriaClinica() {
  const cliente = useQueryClient()
  const [parametros, setParametros] = useSearchParams()
  const pacienteId = Number(parametros.get('paciente')) || null

  const [textoPaciente, setTextoPaciente] = useState('')
  const [qPaciente, setQPaciente] = useState('')
  const [historiaAbierta, setHistoriaAbierta] = useState(false)
  const [odontogramaAbierto, setOdontogramaAbierto] = useState(false)

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

  function elegirPaciente(id: number) {
    setParametros({ paciente: String(id) })
  }

  const guardarHistoria = useMutation({
    mutationFn: crearHistoria,
    onSuccess: () => {
      message.success('Entrada de historia clínica guardada')
      setHistoriaAbierta(false)
      formHistoria.resetFields()
      cliente.invalidateQueries({ queryKey: ['historias', pacienteId] })
    },
    onError: (e) =>
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar la historia.'),
  })

  const guardarOdontograma = useMutation({
    mutationFn: crearOdontograma,
    onSuccess: () => {
      message.success('Odontograma guardado')
      setOdontogramaAbierto(false)
      formOdontograma.resetFields()
      cliente.invalidateQueries({ queryKey: ['odontogramas', pacienteId] })
    },
    onError: (e) =>
      message.error(e instanceof ApiError ? e.message : 'No se pudo guardar el odontograma.'),
  })

  function abrirHistoria() {
    formHistoria.setFieldsValue({
      fecha: hoy(),
      sede: paciente?.sede_origen ?? undefined,
    })
    setHistoriaAbierta(true)
  }

  function abrirOdontograma() {
    formOdontograma.setFieldsValue({
      fecha: hoy(),
      sede: paciente?.sede_origen ?? undefined,
      hallazgos: [{ estado: 'caries', diente: 11 }],
    })
    setOdontogramaAbierto(true)
  }

  async function enviarHistoria() {
    const valores = await formHistoria.validateFields()
    guardarHistoria.mutate({
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
    })
  }

  async function enviarOdontograma() {
    const valores = await formOdontograma.validateFields()
    const hallazgos: DatosHallazgo[] = (valores.hallazgos ?? []).map(
      (h: DatosHallazgo) => ({
        diente: h.diente,
        cara: h.cara ?? '',
        estado: h.estado,
        observacion: h.observacion ?? '',
      }),
    )
    guardarOdontograma.mutate({
      paciente: pacienteId!,
      sede: valores.sede,
      doctor: valores.doctor ?? null,
      fecha: valores.fecha,
      notas: valores.notas ?? '',
      hallazgos,
    })
  }

  const columnasHallazgos: TableProps<HallazgoDental>['columns'] = [
    { title: 'Pieza', dataIndex: 'diente', key: 'diente', width: 90 },
    {
      title: 'Cara',
      dataIndex: 'cara',
      key: 'cara',
      render: (v: string, h) => (v ? h.cara_nombre : 'Toda la pieza'),
    },
    {
      title: 'Estado',
      dataIndex: 'estado',
      key: 'estado',
      render: (v: string, h) => <Tag color={COLOR_ESTADO[v]}>{h.estado_nombre}</Tag>,
    },
    { title: 'Observación', dataIndex: 'observacion', key: 'observacion', render: (v: string) => v || '-' },
  ]

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

          <Row gutter={16}>
            <Col xs={24} lg={12}>
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
                  <Timeline
                    items={(historias?.results ?? []).map((h: Historia) => ({
                      children: (
                        <div>
                          <Space wrap size={8}>
                            <Typography.Text strong>{h.fecha}</Typography.Text>
                            <Tag>{h.sede_nombre}</Tag>
                            <Typography.Text type="secondary">{h.doctor_nombre}</Typography.Text>
                          </Space>
                          {h.motivo_consulta && (
                            <div style={{ marginTop: 4 }}>
                              <Typography.Text strong>Motivo: </Typography.Text>
                              {h.motivo_consulta}
                            </div>
                          )}
                          {h.diagnostico && (
                            <div>
                              <Typography.Text strong>Diagnóstico: </Typography.Text>
                              {h.diagnostico}
                            </div>
                          )}
                          {h.plan_tratamiento && (
                            <div>
                              <Typography.Text strong>Plan: </Typography.Text>
                              {h.plan_tratamiento}
                            </div>
                          )}
                          {h.notas && (
                            <div>
                              <Typography.Text type="secondary">{h.notas}</Typography.Text>
                            </div>
                          )}
                        </div>
                      ),
                    }))}
                  />
                )}
              </Card>
            </Col>

            <Col xs={24} lg={12}>
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
                  (odontogramas?.results ?? []).map((o: Odontograma, indice) => (
                    <div key={o.id}>
                      {indice > 0 && <Divider />}
                      <Space wrap size={8} style={{ marginBottom: 8 }}>
                        <Typography.Text strong>{o.fecha}</Typography.Text>
                        <Tag>{o.sede_nombre}</Tag>
                        {o.doctor_nombre && (
                          <Typography.Text type="secondary">{o.doctor_nombre}</Typography.Text>
                        )}
                      </Space>
                      <Table<HallazgoDental>
                        rowKey="id"
                        size="small"
                        columns={columnasHallazgos}
                        dataSource={o.hallazgos}
                        pagination={false}
                        locale={{ emptyText: 'Sin hallazgos.' }}
                      />
                      {o.notas && (
                        <Typography.Paragraph type="secondary" style={{ marginTop: 8, marginBottom: 0 }}>
                          {o.notas}
                        </Typography.Paragraph>
                      )}
                    </div>
                  ))
                )}
              </Card>
            </Col>
          </Row>
        </>
      )}

      <Modal
        title="Nueva entrada de historia clínica"
        open={historiaAbierta}
        onCancel={() => setHistoriaAbierta(false)}
        onOk={enviarHistoria}
        okText="Guardar"
        cancelText="Cancelar"
        confirmLoading={guardarHistoria.isPending}
        destroyOnHidden
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
        title="Nuevo odontograma"
        open={odontogramaAbierto}
        onCancel={() => setOdontogramaAbierto(false)}
        onOk={enviarOdontograma}
        okText="Guardar"
        cancelText="Cancelar"
        confirmLoading={guardarOdontograma.isPending}
        destroyOnHidden
        width={760}
      >
        <Alert
          type="info"
          showIcon
          style={{ marginBottom: 12 }}
          message="Usa la numeración FDI (11-48 para piezas permanentes, 51-85 para temporales)."
        />
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

          <Divider orientation="left">Hallazgos</Divider>
          <Form.List name="hallazgos">
            {(campos, { add, remove }) => (
              <>
                {campos.map((campo) => (
                  <Row gutter={8} key={campo.key} align="middle">
                    <Col xs={8} md={4}>
                      <Form.Item
                        name={[campo.name, 'diente']}
                        rules={[{ required: true, message: 'Pieza' }]}
                      >
                        <InputNumber min={11} max={85} placeholder="Pieza" style={{ width: '100%' }} />
                      </Form.Item>
                    </Col>
                    <Col xs={8} md={5}>
                      <Form.Item name={[campo.name, 'cara']}>
                        <Select allowClear options={CARAS} placeholder="Cara" />
                      </Form.Item>
                    </Col>
                    <Col xs={8} md={5}>
                      <Form.Item
                        name={[campo.name, 'estado']}
                        rules={[{ required: true, message: 'Estado' }]}
                      >
                        <Select options={ESTADOS} placeholder="Estado" />
                      </Form.Item>
                    </Col>
                    <Col xs={16} md={8}>
                      <Form.Item name={[campo.name, 'observacion']}>
                        <Input placeholder="Observación" />
                      </Form.Item>
                    </Col>
                    <Col xs={8} md={2}>
                      <Button
                        danger
                        type="text"
                        icon={<DeleteOutlined />}
                        onClick={() => remove(campo.name)}
                        aria-label="Quitar hallazgo"
                      />
                    </Col>
                  </Row>
                ))}
                <Button type="dashed" block icon={<PlusOutlined />} onClick={() => add({ estado: 'caries' })}>
                  Agregar hallazgo
                </Button>
              </>
            )}
          </Form.List>

          <Form.Item name="notas" label="Notas" style={{ marginTop: 12 }}>
            <Input.TextArea rows={2} />
          </Form.Item>
        </Form>
      </Modal>
    </Card>
  )
}
