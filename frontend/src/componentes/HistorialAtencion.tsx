import { useQuery } from '@tanstack/react-query'
import { Alert, Drawer, Empty, Space, Tag, Timeline, Typography } from 'antd'

import { listarHistorialAtencion, type Atencion, type RegistroHistorial } from '../api/atenciones'

type Props = {
  abierto: boolean
  atencion: Atencion | null
  onCerrar: () => void
}

const ETIQUETA_CAMPO: Record<string, string> = {
  sede: 'Sede',
  doctor: 'Doctor',
  paciente: 'Paciente',
  tipo_trabajo: 'Tipo de trabajo',
  estado: 'Estado',
  origen: 'Origen',
  creado_por: 'Creada por',
  fecha: 'Fecha',
  hora_inicio: 'Hora de inicio',
  hora_fin: 'Hora de fin',
  procedimiento: 'Procedimiento',
  honorario_doctor: 'Honorario',
  observaciones: 'Observaciones',
}

const COLOR_TIPO: Record<RegistroHistorial['tipo'], string> = {
  '+': 'green',
  '~': 'blue',
  '-': 'red',
}

const formatoFecha = (valor: string) =>
  new Date(valor).toLocaleString('es-HN', {
    dateStyle: 'medium',
    timeStyle: 'short',
  })

const valor = (dato: RegistroHistorial['cambios'][number]['antes']) =>
  dato === null || dato === undefined || dato === '' ? '—' : String(dato)

/** Historial de simple_history de una cita, con el usuario que hizo cada cambio. */
export default function HistorialAtencion({ abierto, atencion, onCerrar }: Props) {
  const { data, isPending, isError } = useQuery({
    queryKey: ['atenciones', atencion?.id, 'historial'],
    queryFn: () => listarHistorialAtencion(atencion!.id),
    enabled: abierto && !!atencion,
  })

  return (
    <Drawer
      title="Historial de la cita"
      open={abierto}
      onClose={onCerrar}
      width={620}
      destroyOnHidden
    >
      {atencion && (
        <Typography.Paragraph type="secondary">
          {atencion.paciente_nombre} · {atencion.fecha} · {atencion.hora_inicio.slice(0, 5)}–
          {atencion.hora_fin.slice(0, 5)}
        </Typography.Paragraph>
      )}
      {isError ? (
        <Alert type="error" showIcon message="No se pudo cargar el historial." />
      ) : !isPending && (data?.length ?? 0) === 0 ? (
        <Empty description="Esta cita no tiene cambios registrados." />
      ) : (
        <Timeline
          pending={isPending ? 'Cargando historial…' : undefined}
          items={(data ?? []).map((registro) => ({
            color: COLOR_TIPO[registro.tipo],
            children: (
              <div>
                <Space wrap size={8}>
                  <Tag color={COLOR_TIPO[registro.tipo]}>{registro.tipo_nombre}</Tag>
                  <Typography.Text strong>{registro.usuario_nombre}</Typography.Text>
                  <Typography.Text type="secondary">{formatoFecha(registro.fecha)}</Typography.Text>
                </Space>
                {registro.motivo && (
                  <div style={{ marginTop: 4 }}>
                    <Typography.Text type="secondary">Motivo: {registro.motivo}</Typography.Text>
                  </div>
                )}
                {registro.cambios.length > 0 && (
                  <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>
                    {registro.cambios.map((cambio) => (
                      <li key={`${registro.id}-${cambio.campo}`}>
                        <Typography.Text>
                          {ETIQUETA_CAMPO[cambio.campo] ?? cambio.campo}:
                        </Typography.Text>{' '}
                        <Typography.Text delete>{valor(cambio.antes)}</Typography.Text> →{' '}
                        <Typography.Text strong>{valor(cambio.despues)}</Typography.Text>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            ),
          }))}
        />
      )}
    </Drawer>
  )
}
