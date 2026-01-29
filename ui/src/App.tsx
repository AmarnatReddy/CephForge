import { Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Clusters from './pages/Clusters'
import Clients from './pages/Clients'
import Workloads from './pages/Workloads'
import Executions from './pages/Executions'
import ExecutionDetail from './pages/ExecutionDetail'

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Dashboard />} />
        <Route path="clusters" element={<Clusters />} />
        <Route path="clients" element={<Clients />} />
        <Route path="workloads" element={<Workloads />} />
        <Route path="executions" element={<Executions />} />
        <Route path="executions/:id" element={<ExecutionDetail />} />
      </Route>
    </Routes>
  )
}

export default App
