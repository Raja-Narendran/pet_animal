-- Pet Animal V2.1: Simplify memory categories and scopes.
UPDATE memory_categories SET name='Password' WHERE name='Passwords and Credit and debit card details';
INSERT OR IGNORE INTO memory_categories(id, name, sensitive)
  SELECT lower(hex(randomblob(16))), 'Credit and Debit card details', 1
  WHERE NOT EXISTS (SELECT 1 FROM memory_categories WHERE name='Credit and Debit card details');

-- Move any records in 'Custom' to 'Important Notes'
UPDATE memories SET category_id=(SELECT id FROM memory_categories WHERE name='Important Notes')
  WHERE category_id IN (SELECT id FROM memory_categories WHERE name='Custom');
DELETE FROM memory_categories WHERE name='Custom';

PRAGMA user_version = 4;
