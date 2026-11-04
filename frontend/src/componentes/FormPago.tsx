import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Alert, Form, Input, InputNumber, Modal, Select, message } from 'antd'
import { useEffect, useState } from 'react'

import type { Atencion } from '../api/atenciones'
import { ApiError } from '../api/cliente'
import {
  crearPago,
  ETIQUETA_METODO,
  METODOS_PAGO,
  type DatosPago,
} from '../api/pagos'
import { MONTO_MAXIMO, formatearMonto } from '../constantes/montos'
import SelectorAtencion from './SelectorAtencion'

type Props = {
  abierto: boolean
  atencionInicial?: Atencion | null
  onCerrar: () => void
}

type Valores = Omit<DatosPago, 'monto'> & { monto: number | null }

const hoyLocal = () => {
  const hoy = new Date()
  const mes = String(hoy.getMonth() + 1).padStart(2, '0')
  const dia = String(hoy.getDate()).padStart(2, '0')
  return `${hoy.getFullYear()}-${mes}-${dia}`
}

const dinero = (valor: string | number) =>
  `L ${Number(valor).toLocaleString('es-HN', { minimumFractionDigits: 2 })}`

/** Registra un abono de paciente contra una cita. */
export default function FormPago({ abierto, atencionInicial, onCerrar }: Props) {
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
        monto: Number(atencionInicial.saldo_pendiente),
        metodo: 'efectivo',
        fecha: hoyLocal(),
        nota: '',
      })
    } else {
      setSeleccionada(null)
      form.setFieldsValue({ metodo: 'efectivo', fecha: hoyLocal(), nota: '' })
    }
  }, [abierto, atencionInicial, form])

  const saldo = seleccionada ? Number(seleccionada.saldo_pendiente) : 0
  const maximo = Math.min(saldo, MONTO_MAXIMO)

  const guardar = useMutation({
    mutationFn: (datos: DatosPago) => crearPago(datos),
    onSuccess: () => {
      message.success('Abono registrado')
      cliente.invalidateQueries({ queryKey: ['pagos'] })
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
      message.error(e instanceof ApiError ? e.message : 'No se pudo registrar el abono.')
    },
  })

  return (
    <Modal
      title="Registrar abono"
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
          rules={[{ required: true, message: 'Elige la cita que se está cobrando' }]}
        >
          <SelectorAtencion
            abierto={abierto}
            onElegir={(atencion) => {
              setSeleccionada(atencion)
              if (atencion) form.setFieldValue('monto', Number(atencion.saldo_pendiente))
            }}
          />
        </Form.Item>

        {seleccionada && (
          <Alert
            style={{ marginBottom: 16 }}
            type="info"
            showIcon
            message={`Precio: ${dinero(seleccionada.precio_paciente)} · Abonado: ${dinero(
              seleccionada.total_pagado,
            )} · Saldo: ${dinero(seleccionada.saldo_pendiente)}`}
          />
        )}

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', columnGap: 16 }}>
          <Form.Item
            name="monto"
            label="Monto del abono (HNL)"
            rules={[
              { required: true, message: 'Escribe el monto' },
              {
                type: 'number',
                min: 0.01,
                max: maximo,
                message: `El abono debe estar entre L 0.01 y ${dinero(maximo)}.`,
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
          <Form.Item name="fecha" label="Fecha del cobro" rules={[{ required: true }]}>
            <Input type="date" max={hoyLocal()} />
          </Form.Item>
        </div>

        <Form.Item name="nota" label="Nota">
          <Input.TextArea rows={2} maxLength={200} placeholder="Ej.: abono inicial, pago con transferencia..." />
        </Form.Item>
      </Form>
    </Modal>
  )
}
