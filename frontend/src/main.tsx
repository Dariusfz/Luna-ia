import '@fontsource/inter/latin-400.css'
import '@fontsource/inter/latin-500.css'
import '@fontsource/inter/latin-600.css'
import '@fontsource/inter/latin-700.css'
import './index.css'

import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { App as AppAntd, ConfigProvider } from 'antd'
import esES from 'antd/locale/es_ES'
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router-dom'

import App from './App'
import { tema } from './tema'

const cliente = new QueryClient({
  defaultOptions: {
    queries: { retry: false, refetchOnWindowFocus: false },
  },
})

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <QueryClientProvider client={cliente}>
      <ConfigProvider theme={tema} locale={esES}>
        <AppAntd>
          <BrowserRouter>
            <App />
          </BrowserRouter>
        </AppAntd>
      </ConfigProvider>
    </QueryClientProvider>
  </StrictMode>,
)
