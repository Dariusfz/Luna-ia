import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Form, Input, InputNumber, Modal, Select, message } from 'antd'
import { useEffect, useState } from 'react'

import type { Atencion } from '../api/atenciones'
import { ApiError } from '../api/cliente'
import {
  crearPagoDoctor,
  ETIQUETA_METODO,
  METODOS_PAGO,
  type DatosPagoDoctor,
} from '../api/pagos'
import { MONTO_MAXIMO, formatearMonto } from '../constantes/montos'
import SelectorAtencion from './SelectorAtencion'

type Props = {
  abierto: boolean
  atencionInicial?: Atencion | null
  onCerrar: () => void
}

type Valores = Omit<DatosPagoDoctor, 'monto'> & { monto: number | null }

const hoyLocal = () => {
  const hoy = new Date()
  const mes = String(hoy.getMonth() + 1).padStart(2, '0')
  const dia = String(hoy.getDate()).padStart(2, '0')
  return `${hoy.getFullYear()}-${mes}-${dia}`
}

const dinero = (valor: string | number) =>
  `L ${Number(valor).toLocaleString('es-HN', { minimumFractionDigits: 2 })}`

/** Registra el pago real de una cita a su doctor. */
export default function FormPagoDoctor({ abierto, atencionInicial, onCerrar }: Props) {
  const [form] = Form.useForm<Valores>()
  const cliente = useQueryClient()
  const [seleccionada, setSeleccionada] = useState<Atencion | null>(null)

  useEffect(() => {
    if (!abierto) return
    form.resetFields()
    if (atencionInicial) {
      setSeleccionada(atencionInicial)
      form.setFieldsValue({
        atencion: atencionInicial.id,
        monto: Number(atencionInicial.saldo_doctor),
        metodo: 'efectivo',
        fecha: hoyLocal(),
        nota: '',
      })
    } else {
      setSeleccionada(null)
      form.setFieldsValue({ metodo: 'efectivo', fecha: hoyLocal(), nota: '' })
    }
  }, [abierto, atencionInicial, form])

  const saldo = seleccionada ? Number(seleccionada.saldo_doctor) : 0
  const maximo = Math.min(saldo, MONTO_MAXIMO)

  const guardar = useMutation({
    mutationFn: (datos: DatosPagoDoctor) => crearPagoDoctor(datos),
    onSuccess: () => {
      message.success('Pago a doctor registrado')
      cliente.invalidateQueries({ queryKey: ['pagos-doctores'] })
      cliente.invalidateQueries({ queryKey: ['caja'] })
      cliente.invalidateQueries({ queryKey: ['atenciones'] })
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
      message.error(e instanceof ApiError ? e.message : 'No se pudo registrar el pago.')
    },
  })

  return (
    <Modal
      title="Registrar pago a doctor"
      open={abierto}
      onCancel={onCerrar}
      onOk={() => form.submit()}
      okText="Registrar"
      cancelText="Cancelar"
      confirmLoading={guardar.isPending}
      okButtonProps={{ disabled: !seleccionada || saldo <= 0 }}
      destroyOnHidden
      width={620}
    >
      <Form<Valores>
        form={form}
        layout="vertical"
        requiredMark={false}
        onFinish={(valores) =>
          guardar.mutate({
            atencion: valores.atencion,
            monto: valores.monto ?? 0,
            metodo: valores.metodo,
            fecha: valores.fecha,
            nota: valores.nota ?? '',
          })
        }
      >
        <Form.Item
          name="atencion"
          label="Cita"
          rules={[{ required: true, message: 'Elige la cita del doctor' }]}
        >
          <SelectorAtencion
            abierto={abierto}
            paraDoctor
            onElegir={(atencion) => {
              setSeleccionada(atencion)
              if (atencion) form.setFieldValue('monto', Number(atencion.saldo_doctor))
            }}
          />
        </Form.Item>

        {seleccionada && (
          <Alert
            style={{ marginBottom: 16 }}
            type="info"
            showIcon
            message={`Doctor: ${seleccionada.doctor_nombre} · Honorario: ${dinero(
              seleccionada.honorario_doctor,
            )} · Pagado: ${dinero(seleccionada.total_pagado_doctor)} · Saldo: ${dinero(
              seleccionada.saldo_doctor,
            )}`}
          />
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
          <Form.Item
            name="monto"
            label="Monto pagado (HNL)"
            rules={[
              { required: true, message: 'Escribe el monto' },
              {
                type: 'number',
                min: 0.01,
                max: maximo,
                message: `El pago debe estar entre L 0.01 y ${dinero(maximo)}.`,
              },
            ]}
          >
            <InputNumber
              min={0.01}
              max={maximo}
              precision={2}
              prefix="L"
              formatter={formatearMonto}
              style={{ width: '100%' }}
            />
          </Form.Item>
          <Form.Item name="metodo" label="Método de pago" rules={[{ required: true }]}>
            <Select
              options={METODOS_PAGO.map((metodo) => ({
                value: metodo,
                label: ETIQUETA_METODO[metodo],
              }))}
            />
          </Form.Item>
          <Form.Item name="fecha" label="Fecha del pago" rules={[{ required: true }]}>
            <Input type="date" max={hoyLocal()} />
          </Form.Item>
        </div>

        <Form.Item name="nota" label="Nota">
          <Input.TextArea rows={2} maxLength={200} placeholder="Ej.: pago de honorarios de la semana..." />
        </Form.Item>
      </Form>
    </Modal>
  )
}
