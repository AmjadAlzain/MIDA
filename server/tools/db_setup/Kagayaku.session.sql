-- =============================================
-- MIDA Database Schema Queries
-- Connection: postgresql://postgres:MIDA@localhost:5432/mida
-- =============================================

-- View all MIDA tables
SELECT table_name 
FROM information_schema.tables 
WHERE table_schema = 'public' 
ORDER BY table_name;

-- mida_certificates table structure
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'mida_certificates'
ORDER BY ordinal_position;

-- mida_certificate_items table structure
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'mida_certificate_items'
ORDER BY ordinal_position;

-- mida_import_records table structure
SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'mida_import_records'
ORDER BY ordinal_position;

-- Sample queries
-- List all certificates
SELECT id, certificate_number, company_name, status, created_at 
FROM mida_certificates 
ORDER BY created_at DESC;

-- List certificate items with remaining quantity
SELECT ci.id, ci.line_number, ci.description, ci.quantity_approved, ci.remaining_quantity, c.certificate_number
FROM mida_certificate_items ci
JOIN mida_certificates c ON ci.certificate_id = c.id
ORDER BY c.certificate_number, ci.line_number;

-- List import records
SELECT ir.id, ir.import_date, ir.declaration_form_reg_no, ir.invoice_number, ir.quantity_imported, ir.port
FROM mida_import_records ir
ORDER BY ir.import_date DESC;
