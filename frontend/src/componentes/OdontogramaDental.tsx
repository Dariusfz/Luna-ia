import { Popover, Segmented, Space, Tag, Typography, theme } from 'antd'
import { useMemo, useState } from 'react'

import {
  CARAS_DENTALES,
  COLOR_POR_ESTADO,
  ESTADOS_DENTALES,
} from './odontogramaConstantes'

export type HallazgoVista = {
  diente: number
  cara?: string | null
  estado: string
  observacion?: string | null
}

const NOMBRE_ESTADO = new Map(ESTADOS_DENTALES.map((e) => [e.value, e.label]))
const NOMBRE_CARA = new Map(CARAS_DENTALES.map((c) => [c.value, c.label]))

const PRIORIDAD = [
  'caries',
  'fractura',
  'extraccion_indicada',
  'ausente',
  'endodoncia',
  'protesis',
  'corona',
  'implante',
  'obturado',
  'sellante',
  'sano',
]

const RUTA_DIENTE =
  'M12 3c-4.4 0-8 2.6-8 6.2 0 2.3 1 4.2 1.7 6.3.6 1.9.7 4.3 1 6.4.2 1.6 1 2.9 2 2.9 1.2 0 1.5-1.4 1.8-3 .2-1.2.6-2.4 1.5-2.4s1.3 1.2 1.5 2.4c.3 1.6.6 3 1.8 3 1 0 1.8-1.3 2-2.9.3-2.1.4-4.5 1-6.4C19 13.4 20 11.5 20 9.2 20 5.6 16.4 3 12 3Z'

function rango(desde: number, hasta: number): number[] {
  const salida: number[] = []
  const paso = desde <= hasta ? 1 : -1
  for (let n = desde; ; n += paso) {
    salida.push(n)
    if (n === hasta) break
  }
  return salida
}

type Denticion = 'permanente' | 'temporal'

const DENTICIONES: Record<
  Denticion,
  { superior: number[][]; inferior: number[][] }
> = {
  permanente: {
    superior: [rango(18, 11), rango(21, 28)],
    inferior: [rango(48, 41), rango(31, 38)],
  },
  temporal: {
    superior: [rango(55, 51), rango(61, 65)],
    inferior: [rango(85, 81), rango(71, 75)],
  },
}

/** Estado que pinta la pieza cuando tiene varios hallazgos. */
function estadoPrincipal(hallazgos: HallazgoVista[]): string | null {
  const estados = new Set(hallazgos.map((h) => h.estado))
  return PRIORIDAD.find((e) => estados.has(e)) ?? hallazgos[0]?.estado ?? null
}

function ResumenPieza({ diente, hallazgos }: { diente: number; hallazgos: HallazgoVista[] }) {
  if (hallazgos.length === 0) {
    return (
      <Typography.Text type="secondary">
        Sin información registrada para la pieza {diente}.
      </Typography.Text>
    )
  }
  return (
    <Space direction="vertical" size={4} style={{ maxWidth: 260 }}>
      {hallazgos.map((h, i) => (
        <div key={`${h.estado}-${h.cara ?? 'pieza'}-${i}`}>
          <Space size={6} wrap>
            <Tag color={COLOR_POR_ESTADO[h.estado]}>{NOMBRE_ESTADO.get(h.estado) ?? h.estado}</Tag>
            <Typography.Text type="secondary">
              {h.cara ? NOMBRE_CARA.get(h.cara) ?? h.cara : 'Toda la pieza'}
            </Typography.Text>
          </Space>
          {h.observacion && (
            <div>
              <Typography.Text>{h.observacion}</Typography.Text>
            </div>
          )}
        </div>
      ))}
    </Space>
  )
}

type Props = {
  hallazgos: HallazgoVista[]
  seleccionado?: number | null
  onSeleccionar?: (diente: number) => void
  /** Muestra el detalle al hacer clic (odontogramas guardados). */
  mostrarDetalle?: boolean
  /** Permite alternar entre dentición permanente y temporal. */
  cambiarDenticion?: boolean
}

export default function OdontogramaDental({
  hallazgos,
  seleccionado,
  onSeleccionar,
  mostrarDetalle = false,
  cambiarDenticion = true,
}: Props) {
  const { token } = theme.useToken()
  const [denticion, setDenticion] = useState<Denticion>('permanente')
  const [interna, setInterna] = useState<number | null>(null)
  const piezaActiva = seleccionado !== undefined ? seleccionado : interna

  const porDiente = useMemo(() => {
    const mapa = new Map<number, HallazgoVista[]>()
    for (const h of hallazgos) {
      const lista = mapa.get(h.diente) ?? []
      lista.push(h)
      mapa.set(h.diente, lista)
    }
    return mapa
  }, [hallazgos])

  const retenidas = hallazgos.filter((h) => h.diente >= 51 && h.diente <= 85)
  const enOtraDenticion = denticion === 'permanente' ? retenidas.length : 0

  function elegir(diente: number) {
    if (seleccionado === undefined) setInterna(diente)
    onSeleccionar?.(diente)
  }

  function dibujarFila(numeros: number[], inferior: boolean, desplazamiento: number) {
    return (
      <div className="luna-odontograma__fila">
        {numeros.map((numero, indice) => {
          const lista = porDiente.get(numero) ?? []
          const estado = estadoPrincipal(lista)
          const color = estado ? COLOR_POR_ESTADO[estado] ?? token.colorPrimary : null
          const activo = piezaActiva === numero
          const boton = (
            <button
              key={numero}
              type="button"
              className={`luna-diente${activo ? ' luna-diente--activo' : ''}`}
              style={{
                animationDelay: `${(desplazamiento + indice) * 18}ms`,
                color: color ?? token.colorTextSecondary,
              }}
              aria-label={`Pieza ${numero}`}
              aria-pressed={onSeleccionar ? activo : undefined}
              onClick={() => elegir(numero)}
            >
              <svg viewBox="0 0 24 30" width={30} height={34} aria-hidden="true">
                <path
                  d={RUTA_DIENTE}
                  transform={inferior ? 'rotate(180 12 15)' : undefined}
                  fill={color ? `${color}26` : 'transparent'}
                  stroke={color ?? token.colorBorder}
                  strokeWidth={1.6}
                  strokeLinejoin="round"
                />
                {estado === 'ausente' && (
                  <line
                    x1="5"
                    y1="6"
                    x2="19"
                    y2="24"
                    stroke={token.colorTextSecondary}
                    strokeWidth="2"
                  />
                )}
              </svg>
              <span className="luna-diente__numero">{numero}</span>
              {lista.length > 1 && <span className="luna-diente__contador">{lista.length}</span>}
            </button>
          )
          if (!mostrarDetalle) return boton
          return (
            <Popover
              key={numero}
              trigger="click"
              placement={inferior ? 'bottom' : 'top'}
              title={`Pieza ${numero}`}
              content={<ResumenPieza diente={numero} hallazgos={lista} />}
            >
              {boton}
            </Popover>
          )
        })}
      </div>
    )
  }

  const arcos = DENTICIONES[denticion]

  return (
    <div className="luna-odontograma">
      <style>{`
        @keyframes luna-diente-entra {
          from { opacity: 0; transform: translateY(8px) scale(.55); }
          to { opacity: 1; transform: translateY(0) scale(1); }
        }
        .luna-odontograma { font-family: inherit; }
        .luna-odontograma__arco { display: flex; flex-direction: column; gap: 6px; align-items: center; min-width: max-content; }
        .luna-odontograma__filas { display: flex; flex-direction: column; gap: 14px; padding: 8px 4px; align-items: center; }
        .luna-odontograma__fila { display: flex; align-items: flex-end; gap: 2px; }
        .luna-odontograma__eje { align-self: stretch; display: flex; align-items: center; justify-content: center; }
        .luna-odontograma__separacion { width: 14px; flex: 0 0 14px; }
        .luna-diente {
          position: relative;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 1px;
          width: 34px;
          padding: 2px 1px 1px;
          border: 1px solid transparent;
          border-radius: 8px;
          background: transparent;
          cursor: pointer;
          animation: luna-diente-entra .45s cubic-bezier(.2, .8, .3, 1.25) both;
          transition: transform .15s ease, border-color .15s ease, box-shadow .15s ease;
        }
        .luna-diente:hover { transform: translateY(-3px) scale(1.06); }
        .luna-diente:focus-visible { outline: 2px solid ${token.colorPrimary}; outline-offset: 1px; }
        .luna-diente--activo {
          border-color: currentColor;
          box-shadow: 0 0 0 3px ${token.colorPrimaryBg};
        }
        .luna-diente__numero { font-size: 11px; line-height: 1.1; color: ${token.colorTextSecondary}; }
        .luna-diente__contador {
          position: absolute;
          top: 0;
          right: 0;
          min-width: 14px;
          height: 14px;
          padding: 0 3px;
          border-radius: 7px;
          background: ${token.colorPrimary};
          color: #fff;
          font-size: 9px;
          line-height: 14px;
          text-align: center;
        }
        .luna-odontograma__leyenda { display: flex; flex-wrap: wrap; gap: 10px 16px; margin-top: 4px; }
        .luna-odontograma__leyenda span { display: inline-flex; align-items: center; gap: 5px; font-size: 12px; color: ${token.colorTextSecondary}; }
        .luna-odontograma__leyenda i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; }
        @media (prefers-reduced-motion: reduce) {
          .luna-diente { animation: none; transition: none; }
          .luna-diente:hover { transform: none; }
        }
      `}</style>

      {cambiarDenticion && (
        <Space style={{ marginBottom: 8 }} wrap>
          <Segmented
            size="small"
            value={denticion}
            onChange={(valor) => setDenticion(valor as Denticion)}
            options={[
              { value: 'permanente', label: 'Permanente' },
              { value: 'temporal', label: `Temporal${retenidas.length ? ` (${retenidas.length})` : ''}` },
            ]}
          />
          {enOtraDenticion > 0 && (
            <Typography.Text type="secondary">
              Hay {enOtraDenticion} hallazgo(s) en dentición temporal.
            </Typography.Text>
          )}
        </Space>
      )}

      <div style={{ overflowX: 'auto', paddingBottom: 4 }}>
        <div key={denticion} className="luna-odontograma__arco">
          <Typography.Text strong style={{ fontSize: 12 }}>
            Superior
          </Typography.Text>
          <div className="luna-odontograma__filas">
            <div className="luna-odontograma__fila">
              {dibujarFila(arcos.superior[0], false, 0)}
              <div className="luna-odontograma__separacion" />
              {dibujarFila(arcos.superior[1], false, arcos.superior[0].length)}
            </div>
            <div className="luna-odontograma__fila">
              {dibujarFila(arcos.inferior[0], true, 0)}
              <div className="luna-odontograma__separacion" />
              {dibujarFila(arcos.inferior[1], true, arcos.inferior[0].length)}
            </div>
          </div>
          <Typography.Text strong style={{ fontSize: 12 }}>
            Inferior
          </Typography.Text>
        </div>
      </div>

      <div className="luna-odontograma__leyenda">
        {ESTADOS_DENTALES.map((e) => (
          <span key={e.value}>
            <i style={{ background: COLOR_POR_ESTADO[e.value] }} />
            {e.label}
          </span>
        ))}
      </div>
    </div>
  )
}
