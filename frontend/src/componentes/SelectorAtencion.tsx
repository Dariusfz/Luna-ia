import { useQuery } from '@tanstack/react-query'
import { Select, Tag } from 'antd'
import { useState } from 'react'

import { listarAtenciones, type Atencion } from '../api/atenciones'

type Props = {
  value?: number
  onChange?: (id: number) => void
  onElegir: (atencion: Atencion | null) => void
  abierto: boolean
  paraDoctor?: boolean
}

const dinero = (valor: string) =>
  `L ${Number(valor).toLocaleString('es-HN', { minimumFractionDigits: 2 })}`

/** Busca citas con saldo pendiente para registrar un cobro o pago a doctor. */
export default function SelectorAtencion({
  value,
  onChange,
  onElegir,
  abierto,
  paraDoctor = false,
}: Props) {
  const [busqueda, setBusqueda] = useState('')

  const { data, isFetching } = useQuery({
    queryKey: ['atenciones', 'caja', busqueda],
    queryFn: () =>
      listarAtenciones(1, {
        q: busqueda,
        estado: ['pendiente', 'confirmada', 'completada'],
      }),
    enabled: abierto,
  })

  const opciones = (data?.results ?? [])
    .filter((atencion) =>
      paraDoctor
        ? Number(atencion.saldo_doctor) > 0
        : Number(atencion.saldo_pendiente) > 0,
    )
    .map((atencion) => ({
      value: atencion.id,
      label: `${atencion.fecha} ${atencion.hora_inicio.slice(0, 5)} · ${
        atencion.paciente_nombre
      } · ${atencion.tipo_trabajo_nombre} · ${
        paraDoctor
          ? `honorario ${dinero(atencion.honorario_doctor)}`
          : `saldo ${dinero(atencion.saldo_pendiente)}`
      }`,
    }))

  return (
    <Select
      showSearch
      filterOption={false}
      loading={isFetching}
      value={value}
      placeholder="Busca por paciente o tipo de trabajo"
      onSearch={setBusqueda}
      onChange={(id: number) => {
        onChange?.(id)
        onElegir(data?.results.find((a) => a.id === id) ?? null)
      }}
      options={opciones}
      notFoundContent={
        <Tag color="default">
          {paraDoctor
            ? 'No hay citas con honorario pendiente.'
            : 'No hay citas con saldo pendiente.'}
        </Tag>
      }
    />
  )
}
