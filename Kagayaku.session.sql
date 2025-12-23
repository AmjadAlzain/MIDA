SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'table1'
ORDER BY ordinal_position;

SELECT column_name, data_type, is_nullable, column_default
FROM information_schema.columns
WHERE table_name = 'table2'
ORDER BY ordinal_position;