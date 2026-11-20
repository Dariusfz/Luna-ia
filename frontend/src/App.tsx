import { Navigate, Route, Routes } from 'react-router-dom'

import LayoutPrincipal from './componentes/LayoutPrincipal'
import RequiereSesion from './componentes/RequiereSesion'
import AceptarInvitacion from './paginas/AceptarInvitacion'
import Asistente from './paginas/Asistente'
import Atenciones from './paginas/Atenciones'
import Caja from './paginas/Caja'
import Configuracion from './paginas/Configuracion'
import ConfirmarRecuperacion from './paginas/ConfirmarRecuperacion'
import Doctores from './paginas/Doctores'
import Especialidades from './paginas/Especialidades'
import Inicio from './paginas/Inicio'
import ListaEspera from './paginas/ListaEspera'
import Login from './paginas/Login'
import Pacientes from './paginas/Pacientes'
import Personal from './paginas/Personal'
import RecuperarContrasena from './paginas/RecuperarContrasena'
import Sedes from './paginas/Sedes'
import TiposTrabajo from './paginas/TiposTrabajo'

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />
      <Route path="/recuperar" element={<RecuperarContrasena />} />
      <Route path="/recuperar/confirmar" element={<ConfirmarRecuperacion />} />
      <Route path="/aceptar-invitacion" element={<AceptarInvitacion />} />
      <Route element={<RequiereSesion />}>
        <Route element={<LayoutPrincipal />}>
          <Route index element={<Inicio />} />
          <Route path="pacientes" element={<Pacientes />} />
          <Route path="atenciones" element={<Atenciones />} />
          <Route path="lista-espera" element={<ListaEspera />} />
          <Route path="asistente" element={<Asistente />} />
          <Route path="caja" element={<Caja />} />
          <Route path="personal" element={<Personal />} />
          <Route path="doctores" element={<Doctores />} />
          <Route path="especialidades" element={<Especialidades />} />
          <Route path="tipos-trabajo" element={<TiposTrabajo />} />
          <Route path="sedes" element={<Sedes />} />
          <Route path="configuracion" element={<Configuracion />} />
        </Route>
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  )
}
