-- Test database initialization script
-- Creates additional test databases and users if needed

-- Ensure test database exists with proper encoding
CREATE DATABASE IF NOT EXISTS workshop_inventory_test 
    CHARACTER SET utf8mb4 
    COLLATE utf8mb4_unicode_ci;

-- Grant permissions to test user
GRANT ALL PRIVILEGES ON workshop_inventory_test.* TO 'inventory_test_user'@'%';
FLUSH PRIVILEGES;