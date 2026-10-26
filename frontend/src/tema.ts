import type { ThemeConfig } from 'antd'

// Paleta y tipografía acordadas (basadas en la referencia visual de la plantilla).
// Todos los colores y radios del proyecto salen de aquí (AGENTS.md regla 8).
export const tema: ThemeConfig = {
  token: {
    colorPrimary: '#238781',
    colorSuccess: '#04a17f',
    colorWarning: '#eebb30',
    colorError: '#df2e3f',
    colorInfo: '#039ce0',
    colorTextBase: '#272727',
    colorTextSecondary: '#5f6b73',
    colorBgLayout: '#f4f8f8',
    colorBorder: '#dde2ee',
    borderRadius: 8,
    fontFamily: "'Inter', system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif",
  },
  components: {
    Layout: {
      siderBg: '#ffffff',
      headerBg: '#ffffff',
      bodyBg: '#f4f8f8',
    },
    Menu: {
      itemSelectedBg: '#e3eeef',
      itemSelectedColor: '#238781',
      itemBorderRadius: 8,
    },
  },
}
