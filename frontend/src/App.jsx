import { useCallback, useState } from 'react'
import { Navigate, Route, Routes } from 'react-router-dom'

import AppShell from './components/AppShell'
import WakeScreen from './components/WakeScreen'
import { useAuth } from './auth/AuthContext'
import { LedgerProvider } from './data/LedgerContext'
import AccountPage from './pages/AccountPage'
import BatchEntry from './pages/BatchEntry'
import Entries from './pages/Entries'
import EntryEdit from './pages/EntryEdit'
import EntryNew from './pages/EntryNew'
import LedgerNew from './pages/LedgerNew'
import LedgerSettings from './pages/LedgerSettings'
import Login from './pages/Login'
import MembersPage from './pages/MembersPage'
import MorePage from './pages/MorePage'
import SummaryPage from './pages/SummaryPage'

export default function App() {
  const { user } = useAuth()
  const [awake, setAwake] = useState(false)
  const handleReady = useCallback(() => setAwake(true), [])

  // Nothing renders until the backend answers. Every screen behind this needs
  // it, so failing here once beats failing on each page separately.
  if (!awake) return <WakeScreen onReady={handleReady} />
  if (!user) return <Login />

  return (
    <LedgerProvider>
      <Routes>
        <Route element={<AppShell />}>
          <Route index element={<Entries />} />
          <Route path="new" element={<EntryNew />} />
          <Route path="batch" element={<BatchEntry />} />
          <Route path="entry/:id" element={<EntryEdit />} />
          <Route path="summary" element={<SummaryPage />} />
          <Route path="members" element={<MembersPage />} />
          <Route path="settings" element={<LedgerSettings />} />
          <Route path="account" element={<AccountPage />} />
          <Route path="more" element={<MorePage />} />
          <Route path="ledgers/new" element={<LedgerNew />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </LedgerProvider>
  )
}
