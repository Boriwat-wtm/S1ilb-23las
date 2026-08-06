import { useCallback, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import Layout from './components/Layout'
import WakeScreen from './components/WakeScreen'
import { useAuth } from './auth/AuthContext'
import { RefDataProvider } from './data/RefDataContext'
import AddTransaction from './pages/AddTransaction'
import Dashboard from './pages/Dashboard'
import EditTransaction from './pages/EditTransaction'
import Login from './pages/Login'
import Summary from './pages/Summary'

export default function App() {
  const { user } = useAuth()
  const [awake, setAwake] = useState(false)
  const handleReady = useCallback(() => setAwake(true), [])

  // Nothing renders until the backend answers — every screen behind this needs
  // it, so failing here once beats failing on every page individually.
  if (!awake) return <WakeScreen onReady={handleReady} />
  if (!user) return <Login />

  return (
    <RefDataProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<Dashboard />} />
          <Route path="add" element={<AddTransaction />} />
          <Route path="edit/:id" element={<EditTransaction />} />
          <Route path="summary" element={<Summary />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </RefDataProvider>
  )
}
