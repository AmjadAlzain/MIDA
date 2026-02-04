import { Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import { 
  InvoiceConverter, 
  CertificateParser, 
  DatabaseView, 
  CertificateDetails, 
  ItemImports,
  BalanceMigration,
} from './pages';

function App() {
  return (
    <Routes>
      <Route path="/" element={<Layout />}>
        <Route index element={<Navigate to="/converter" replace />} />
        <Route path="converter" element={<InvoiceConverter />} />
        <Route path="parser" element={<CertificateParser />} />
        <Route path="database" element={<DatabaseView />} />
        <Route path="database/certificates/:id" element={<CertificateDetails />} />
        <Route path="database/certificates/:certId/items/:itemId/imports" element={<ItemImports />} />
        <Route path="migration" element={<BalanceMigration />} />
      </Route>
    </Routes>
  );
}

export default App;
