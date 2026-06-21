import { BrowserRouter, Routes, Route } from 'react-router-dom'
import { Shell } from '@/components/layout/Shell'
import { DashboardPage } from '@/pages/DashboardPage'
import { BacktestPage } from '@/pages/BacktestPage'
import { ReplayPage } from '@/pages/ReplayPage'
import { LogsPage } from '@/pages/LogsPage'
import { DataPage } from '@/pages/DataPage'
import { ChartPage } from '@/pages/ChartPage'

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route element={<Shell />}>
          <Route index element={<DashboardPage />} />
          <Route path="/backtest" element={<BacktestPage />} />
          <Route path="/replay" element={<ReplayPage />} />
          <Route path="/data" element={<DataPage />} />
          <Route path="/chart" element={<ChartPage />} />
          <Route path="/logs" element={<LogsPage />} />
        </Route>
      </Routes>
    </BrowserRouter>
  )
}

export default App
