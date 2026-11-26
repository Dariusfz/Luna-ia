import {
  DeleteOutlined,
  DownloadOutlined,
  EyeOutlined,
  PlusOutlined,
  SearchOutlined,
} from '@ant-design/icons'
import { keepPreviousData, useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Button,
  Card,
  Form,
  Image,
  Input,
  Modal,
  Popconfirm,
  Select,
  Space,
  Table,
  Tag,
  Typography,
  Upload,
  message,
} from 'antd'
import type { TableProps } from 'antd'
import { useEffect, useMemo, useState } from 'react'

import { obtenerUsuarioActual } from '../api/auth'
import { ApiError } from '../api/cliente'
import { listarAtenciones } from '../api/atenciones'
import {
  TIPOS_DOCUMENTO,
  eliminarDocumento,
  listarDocumentos,
  subirDocumento,
  urlDocumento,
  type Documento,
  type TipoDocumento,
} from '../api/documentos'
import { listarHistorias } from '../api/historiaClinica'
import { listarPacientes, listarSedes } from '../api/recursos'

type ArchivoSubida = { originFileObj?: File }

type ValoresSubida = {
  sede: number
  atencion?: number | null
  historia?: number | null
  tipo: TipoDocumento
  titulo: string
  descripcion?: string
  archivo: ArchivoSubida[]
}

function formatoFecha(iso: string): string {
  return new Date(iso).toLocaleString('es-HN', { dateStyle: 'short', timeStyle: 'short' })
}

function formatoTamano(bytes: number | null): string {
  if (!bytes) return '-'
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

export default function Documentos() {
  const cliente = useQueryClient()
  const [pagina, setPagina] = useState(1)
  const [texto, setTexto] = useState('')
  const [q, setQ] = useState('')
  const [tipo, setTipo] = useState<TipoDocumento | null>(null)
  const [sede, setSede] = useState<number | null>(null)
  const [paciente, setPaciente] = useState<number | null>(null)
  const [etiquetaPaciente, setEtiquetaPaciente] = useState('')
  const [busquedaPaciente, setBusquedaPaciente] = useState('')
  const [qPaciente, setQPaciente] = useState('')
  const [subirAbierto, setSubirAbierto] = useState(false)
  const [ver, setVer] = useState<Documento | null>(null)

  const [form] = Form.useForm<ValoresSubida>()

  const { data: usuario } = useQuery({ queryKey: ['me'], queryFn: obtenerUsuarioActual })
  const { data: sedes } = useQuery({ queryKey: ['sedes', 'true'], queryFn: () => listarSedes('true') })

  useEffect(() => {
    const espera = setTimeout(() => setQ(texto.trim()), 300)
    return () => clearTimeout(espera)
  }, [texto])

  useEffect(() => {
    const espera = setTimeout(() => setQPaciente(busquedaPaciente.trim()), 300)
    return () => clearTimeout(espera)
  }, [busquedaPaciente])

  useEffect(() => setPagina(1), [q, tipo, sede, paciente])

  const { data: pacientesEncontrados, isFetching: buscandoPacientes } = useQuery({
    queryKey: ['documentos', 'pacientes', qPaciente],
    queryFn: () => listarPacientes(1, { q: qPaciente, activo: 'true' }),
    enabled: qPaciente.length >= 2,
  })

  const { data: atenciones } = useQuery({
    queryKey: ['documentos', 'atenciones', paciente],
    queryFn: () => listarAtenciones(1, { paciente }),
    enabled: paciente !== null,
  })

  const { data: historias } = useQuery({
    queryKey: ['documentos', 'historias', paciente],
    queryFn: () => listarHistorias(paciente as number),
    enabled: paciente !== null,
  })

  const opcionesPacientes = useMemo(() => {
    const base =
      pacientesEncontrados?.results.map((p) => ({
        value: p.id,
        label: `${p.nombres} ${p.apellidos}`.trim(),
      })) ?? []
    if (paciente && etiquetaPaciente && !base.some((opcion) => opcion.value === paciente)) {
      base.push({ value: paciente, label: etiquetaPaciente })
    }
    return base
  }, [pacientesEncontrados, paciente, etiquetaPaciente])

  const filtros = useMemo(
    () => ({ q, paciente, tipo, sede }),
    [q, paciente, tipo, sede],
  )

  const { data, isPending } = useQuery({
    queryKey: ['documentos', pagina, filtros],
    queryFn: () => listarDocumentos(pagina, filtros),
    placeholderData: keepPreviousData,
  })

  const subir = useMutation({
    mutationFn: subirDocumento,
    onSuccess: () => {
      message.success('Documento subido')
      cliente.invalidateQueries({ queryKey: ['documentos'] })
      form.resetFields()
      setSubirAbierto(false)
    },
    onError: (e) => {
      if (e instanceof ApiError && Object.keys(e.campos).length > 0) {
        form.setFields(
          Object.entries(e.campos).map(([campo, error]) => ({
            name: campo as keyof ValoresSubida,
            errors: [error],
          })),
        )
      }
      message.error(e instanceof ApiError ? e.message : 'No se pudo subir el documento.')
    },
  })

  const eliminar = useMutation({
    mutationFn: eliminarDocumento,
    onSuccess: () => {
      message.success('Documento eliminado')
      cliente.invalidateQueries({ queryKey: ['documentos'] })
    },
    onError: (e) =>
      message.error(e instanceof ApiError ? e.message : 'No se pudo eliminar el documento.'),
  })

  function abrirSubida() {
    form.resetFields()
    const unicaSede = sedes?.results.length === 1 ? sedes.results[0].id : undefined
    form.setFieldsValue({ sede: unicaSede, tipo: 'radiografia' })
    setSubirAbierto(true)
  }

  const columnas: TableProps<Documento>['columns'] = [
    {
      title: 'Fecha',
      dataIndex: 'creado',
      key: 'creado',
      render: (valor: string) => formatoFecha(valor),
    },
    {
      title: 'Paciente',
      dataIndex: 'paciente_nombre',
      key: 'paciente',
      render: (valor: string) => <Typography.Text strong>{valor}</Typography.Text>,
    },
    {
      title: 'Tipo',
      dataIndex: 'tipo',
      key: 'tipo',
      render: (valor: TipoDocumento, documento) => {
        const config = TIPOS_DOCUMENTO.find((t) => t.value === valor)
        return <Tag color={config?.color}>{documento.tipo_nombre}</Tag>
      },
    },
    {
      title: 'Título',
      dataIndex: 'titulo',
      key: 'titulo',
      render: (valor: string, documento) => (
        <div>
          <div>{valor}</div>
          {documento.descripcion && (
            <Typography.Text type="secondary" style={{ fontSize: 12 }}>
              {documento.descripcion}
            </Typography.Text>
          )}
        </div>
      ),
    },
    {
      title: 'Vinculado a',
      key: 'vinculo',
      render: (_, documento) =>
        documento.atencion_resumen ? (
          <Typography.Text>Atención: {documento.atencion_resumen}</Typography.Text>
        ) : documento.historia_resumen ? (
          <Typography.Text>Historia: {documento.historia_resumen}</Typography.Text>
        ) : (
          <Typography.Text type="secondary">Sin vincular</Typography.Text>
        ),
    },
    { title: 'Sede', dataIndex: 'sede_nombre', key: 'sede' },
    {
      title: 'Subido por',
      dataIndex: 'subido_por_nombre',
      key: 'subido_por',
      render: (valor: string) => valor || '-',
    },
    {
      title: 'Tamaño',
      dataIndex: 'tamano_bytes',
      key: 'tamano',
      render: (valor: number | null) => formatoTamano(valor),
    },
    {
      title: 'Acciones',
      key: 'acciones',
      render: (_, documento) => (
        <Space wrap>
          {documento.es_imagen && (
            <Button size="small" icon={<EyeOutlined />} onClick={() => setVer(documento)}>
              Ver
            </Button>
          )}
          <Button
            size="small"
            icon={<DownloadOutlined />}
            onClick={() => window.open(urlDocumento(documento, true), '_blank', 'noopener')}
          >
            Descargar
          </Button>
          {usuario?.es_admin && (
            <Popconfirm
              title="¿Eliminar este documento?"
              description="Se borra el archivo. No se puede recuperar."
              okText="Eliminar"
              cancelText="Cancelar"
              okButtonProps={{ danger: true }}
              onConfirm={() => eliminar.mutate(documento.id)}
            >
              <Button size="small" danger icon={<DeleteOutlined />} aria-label="Eliminar documento" />
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ]

  return (
    <Space direction="vertical" size="large" style={{ width: '100%' }}>
      <div>
        <Typography.Title level={3} style={{ margin: 0 }}>
          Documentos
        </Typography.Title>
        <Typography.Text type="secondary">
          Radiografías, fotos clínicas y consentimientos de cada paciente.
        </Typography.Text>
      </div>

      <Alert
        type="info"
        showIcon
        message="Archivos privados"
        description="Solo el personal con acceso a la sede puede verlos. Formatos: PDF, JPG, PNG o WEBP. Se descargan con tu sesión, no por enlaces públicos."
      />

      <Card>
        <Space wrap style={{ marginBottom: 16 }}>
          <Select
            allowClear
            showSearch
            filterOption={false}
            placeholder="Buscar paciente"
            style={{ width: 280 }}
            value={paciente}
            loading={buscandoPacientes}
            onSearch={setBusquedaPaciente}
            onChange={(valor, opcion) => {
              setPaciente(valor ?? null)
              setEtiquetaPaciente(
                (opcion as { label?: string } | undefined)?.label ?? '',
              )
            }}
            options={opcionesPacientes}
            notFoundContent={qPaciente.length < 2 ? 'Escribe al menos 2 letras' : 'Sin resultados'}
          />
          <Select
            allowClear
            placeholder="Todos los tipos"
            style={{ width: 180 }}
            value={tipo}
            onChange={(valor) => setTipo(valor ?? null)}
            options={TIPOS_DOCUMENTO.map(({ value, label }) => ({ value, label }))}
          />
          <Select
            allowClear
            placeholder="Todas las sedes"
            style={{ width: 180 }}
            value={sede}
            onChange={(valor) => setSede(valor ?? null)}
            options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre })) ?? []}
          />
          <Input
            allowClear
            prefix={<SearchOutlined />}
            placeholder="Buscar por título o paciente"
            style={{ width: 280 }}
            value={texto}
            onChange={(evento) => setTexto(evento.target.value)}
          />
          <Button
            type="primary"
            icon={<PlusOutlined />}
            disabled={!paciente}
            title={paciente ? undefined : 'Elige primero un paciente'}
            onClick={abrirSubida}
          >
            Subir documento
          </Button>
        </Space>

        <Table<Documento>
          rowKey="id"
          columns={columnas}
          dataSource={data?.results}
          loading={isPending}
          locale={{ emptyText: 'No hay documentos con estos filtros.' }}
          pagination={{
            current: pagina,
            pageSize: 25,
            total: data?.count ?? 0,
            showSizeChanger: false,
            onChange: setPagina,
          }}
        />
      </Card>

      <Modal
        title={`Subir documento${etiquetaPaciente ? ` — ${etiquetaPaciente}` : ''}`}
        open={subirAbierto}
        onCancel={() => setSubirAbierto(false)}
        onOk={() => form.submit()}
        okText="Subir"
        cancelText="Cancelar"
        confirmLoading={subir.isPending}
        destroyOnHidden
        width={620}
      >
        <Form<ValoresSubida>
          form={form}
          layout="vertical"
          requiredMark={false}
          onFinish={(valores) => {
            const archivo = valores.archivo?.[0]?.originFileObj
            if (!paciente || !archivo) {
              message.error('Elige el archivo que quieres subir.')
              return
            }
            subir.mutate({
              paciente,
              sede: valores.sede,
              atencion: valores.atencion ?? null,
              historia: valores.historia ?? null,
              tipo: valores.tipo,
              titulo: valores.titulo,
              descripcion: valores.descripcion,
              archivo,
            })
          }}
        >
          <Form.Item name="sede" label="Sede" rules={[{ required: true, message: 'Elige la sede' }]}>
            <Select
              placeholder="Elige la sede"
              options={sedes?.results.map((s) => ({ value: s.id, label: s.nombre })) ?? []}
            />
          </Form.Item>
          <Form.Item
            name="atencion"
            label="Atención (opcional)"
            extra="Enlaza el archivo a la cita o visita correspondiente."
          >
            <Select
              allowClear
              placeholder="Sin atención"
              options={
                atenciones?.results.map((a) => ({
                  value: a.id,
                  label: `${a.fecha} ${a.hora_inicio} · ${a.tipo_trabajo_nombre}`,
                })) ?? []
              }
              onChange={(valor) => {
                const atencion = atenciones?.results.find((a) => a.id === valor)
                if (atencion) form.setFieldValue('sede', atencion.sede)
              }}
            />
          </Form.Item>
          <Form.Item
            name="historia"
            label="Historia clínica (opcional)"
            extra="Si la historia viene de una cita, se enlaza también esa atención."
          >
            <Select
              allowClear
              placeholder="Sin historia clínica"
              options={
                historias?.results.map((h) => ({
                  value: h.id,
                  label: `${h.fecha} · ${h.motivo_consulta || 'Historia clínica'}`,
                })) ?? []
              }
              onChange={(valor) => {
                const historia = historias?.results.find((h) => h.id === valor)
                if (historia) {
                  form.setFieldValue('sede', historia.sede)
                  if (historia.atencion) form.setFieldValue('atencion', historia.atencion)
                }
              }}
            />
          </Form.Item>
          <Form.Item name="tipo" label="Tipo" rules={[{ required: true, message: 'Elige el tipo' }]}>
            <Select options={TIPOS_DOCUMENTO.map(({ value, label }) => ({ value, label }))} />
          </Form.Item>
          <Form.Item
            name="titulo"
            label="Título"
            rules={[{ required: true, whitespace: true, message: 'Escribe un título' }]}
          >
            <Input maxLength={150} placeholder="Ej. Radiografía panorámica inicial" />
          </Form.Item>
          <Form.Item name="descripcion" label="Descripción (opcional)">
            <Input.TextArea rows={2} maxLength={500} />
          </Form.Item>
          <Form.Item
            name="archivo"
            label="Archivo"
            valuePropName="fileList"
            getValueFromEvent={(evento) => (Array.isArray(evento) ? evento : evento?.fileList)}
            rules={[{ required: true, message: 'Selecciona el archivo' }]}
            extra="PDF o imagen JPG, PNG o WEBP. Máximo 20 MB."
          >
            <Upload.Dragger
              beforeUpload={() => false}
              maxCount={1}
              accept=".pdf,.jpg,.jpeg,.png,.webp"
            >
              <p className="ant-upload-text">Haz clic o arrastra el archivo aquí</p>
              <p className="ant-upload-hint">Se guarda de forma privada, ligado al paciente.</p>
            </Upload.Dragger>
          </Form.Item>
        </Form>
      </Modal>

      <Modal
        title={ver?.titulo}
        open={ver !== null}
        onCancel={() => setVer(null)}
        footer={null}
        width={800}
        destroyOnHidden
      >
        {ver?.es_imagen && (
          <Image
            src={urlDocumento(ver)}
            alt={ver.titulo}
            style={{ width: '100%' }}
            fallback="data:image/gif;base64,R0lGODlhAQABAAAAACw="
          />
        )}
      </Modal>
    </Space>
  )
}
