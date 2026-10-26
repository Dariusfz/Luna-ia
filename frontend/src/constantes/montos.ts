export const MONTO_MAXIMO = 500_000
export const MONTO_MAXIMO_FORMATEADO = MONTO_MAXIMO.toLocaleString('en-US', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})
export const MONTO_MAXIMO_TEXTO = `L ${MONTO_MAXIMO_FORMATEADO}`
export const MONTO_MAXIMO_LONGITUD = MONTO_MAXIMO_FORMATEADO.length

export function formatearMonto(valor: number | string | null | undefined): string {
  if (valor === null || valor === undefined || valor === '') return ''
  const [entero, decimal] = String(valor).split('.')
  const enteroConComas = entero.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return decimal === undefined ? enteroConComas : `${enteroConComas}.${decimal}`
}
