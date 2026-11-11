import { Route, Routes, Navigate } from 'react-router-dom';
import { AppLayout, RequireAnalysis } from './components/Layout';
import SessionSelect from './pages/SessionSelect';
import Overview from './pages/Overview';
import Telemetry from './pages/Telemetry';
import Tires from './pages/Tires';
import StrategyLab from './pages/StrategyLab';
import Insights from './pages/Insights';

export default function App() {
  return (
    <Routes>
      <Route element={<AppLayout />}>
        <Route index element={<SessionSelect />} />
        <Route path="overview" element={<RequireAnalysis><Overview /></RequireAnalysis>} />
        <Route path="telemetry" element={<RequireAnalysis><Telemetry /></RequireAnalysis>} />
        <Route path="tires" element={<RequireAnalysis><Tires /></RequireAnalysis>} />
        <Route path="strategy" element={<RequireAnalysis><StrategyLab /></RequireAnalysis>} />
        <Route path="insights" element={<RequireAnalysis><Insights /></RequireAnalysis>} />
        <Route path="*" element={<Navigate to="/" replace />} />
      </Route>
    </Routes>
  );
}
