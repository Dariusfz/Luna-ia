export const CARAS_DENTALES = [
  { value: 'oclusal', label: 'Oclusal' },
  { value: 'mesial', label: 'Mesial' },
  { value: 'distal', label: 'Distal' },
  { value: 'vestibular', label: 'Vestibular' },
  { value: 'lingual', label: 'Lingual/Palatino' },
]

export const ESTADOS_DENTALES = [
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

export const COLOR_POR_ESTADO: Record<string, string> = {
  sano: '#52c41a',
  caries: '#ff4d4f',
  obturado: '#1677ff',
  corona: '#faad14',
  endodoncia: '#722ed1',
  ausente: '#8c8c8c',
  extraccion_indicada: '#fa541c',
  implante: '#13c2c2',
  sellante: '#a0d911',
  fractura: '#eb2f96',
  protesis: '#2f54eb',
}
