import { Input } from 'antd'

type Props = {
  value?: string
  onChange?: (valor: string) => void
}

/**
 * Teléfono hondureño: prefijo +504 fijo y exactamente 8 dígitos (XXXX-XXXX).
 * No deja escribir letras ni más dígitos de los necesarios.
 */
export default function CampoTelefono({ value = '', onChange }: Props) {
  // Solo los 8 dígitos locales, sin el prefijo ni el guion.
  const digitos = value.replace(/^\+504\s*/, '').replace(/\D/g, '').slice(0, 8)
  const mostrar = digitos.length > 4 ? `${digitos.slice(0, 4)}-${digitos.slice(4)}` : digitos

  function cambiar(e: React.ChangeEvent<HTMLInputElement>) {
    const nuevos = e.target.value.replace(/\D/g, '').slice(0, 8)
    if (!onChange) return
    if (nuevos === '') {
      onChange('')
      return
    }
    const formato = nuevos.length > 4 ? `${nuevos.slice(0, 4)}-${nuevos.slice(4)}` : nuevos
    onChange(`+504 ${formato}`)
  }

  return (
    <Input
      addonBefore="+504"
      value={mostrar}
      onChange={cambiar}
      placeholder="9999-9999"
      inputMode="numeric"
      maxLength={9}
    />
  )
}
