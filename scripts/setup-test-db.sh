#!/bin/bash
set -e

# Workshop Inventory Test Database Setup Script
# 
# This script helps set up MariaDB test environment for local development and testing.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🗄️  Setting up Workshop Inventory Test Database"
echo "================================================"

# Check if Docker is available
if ! command -v docker &> /dev/null; then
    echo "❌ Docker is required but not installed."
    echo "Please install Docker and try again."
    exit 1
fi

# Check if Docker Compose is available
if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo "❌ Docker Compose is required but not installed."
    echo "Please install Docker Compose and try again."
    exit 1
fi

# Use docker compose or docker-compose depending on what's available
COMPOSE_CMD="docker compose"
if ! docker compose version &> /dev/null; then
    COMPOSE_CMD="docker-compose"
fi

cd "$PROJECT_DIR"

# Function to wait for MariaDB to be ready
wait_for_db() {
    echo "⏳ Waiting for MariaDB to be ready..."
    
    for i in {1..30}; do
        if docker exec workshop-inventory-test-db mysqladmin ping -h localhost -u root -ptest_root_password --silent 2>/dev/null; then
            echo "✅ MariaDB is ready!"
            return 0
        fi
        echo "   Waiting for MariaDB... ($i/30)"
        sleep 2
    done
    
    echo "❌ MariaDB failed to start within 60 seconds"
    return 1
}

# Function to run database migrations
run_migrations() {
    echo "🔄 Running database migrations..."
    
    export USE_TEST_MARIADB=1
    export TEST_DB_HOST=localhost
    export TEST_DB_PORT=3307
    export TEST_DB_USER=inventory_test_user
    export TEST_DB_PASSWORD=test_password
    export TEST_DB_NAME=workshop_inventory_test
    
    # Create a temporary .env file for testing
    cat > .env.test << EOF
# Test database configuration
SQLALCHEMY_DATABASE_URI=mysql+pymysql://inventory_test_user:test_password@localhost:3307/workshop_inventory_test
TEST_DB_HOST=localhost
TEST_DB_PORT=3307
TEST_DB_USER=inventory_test_user
TEST_DB_PASSWORD=test_password
TEST_DB_NAME=workshop_inventory_test
EOF
    
    # Load test environment and run migrations
    if [ -f .env.test ]; then
        export $(grep -v '^#' .env.test | xargs)
    fi
    
    python manage.py db upgrade
    
    # Clean up temporary env file
    rm -f .env.test
    
    echo "✅ Database migrations completed!"
}

# Function to verify database setup
verify_setup() {
    echo "🔍 Verifying database setup..."
    
    # Check tables exist
    TABLES=$(docker exec workshop-inventory-test-db mysql -h localhost -u inventory_test_user -ptest_password workshop_inventory_test -e "SHOW TABLES;" -s)
    
    if echo "$TABLES" | grep -q "inventory_items"; then
        echo "✅ inventory_items table exists"
    else
        echo "❌ inventory_items table missing"
        return 1
    fi
    
    if echo "$TABLES" | grep -q "material_taxonomy"; then
        echo "✅ material_taxonomy table exists"
    else
        echo "❌ material_taxonomy table missing"
        return 1
    fi
    
    echo "✅ Database verification completed!"
}

# Main setup process
echo "🚀 Starting MariaDB test container..."
$COMPOSE_CMD -f docker-compose.test.yml up -d mariadb-test

if wait_for_db; then
    run_migrations
    verify_setup
    
    echo ""
    echo "🎉 Test database setup completed successfully!"
    echo ""
    echo "📋 Connection Details:"
    echo "   Host: localhost"
    echo "   Port: 3307"
    echo "   Database: workshop_inventory_test"
    echo "   Username: inventory_test_user"
    echo "   Password: test_password"
    echo ""
    echo "🧪 To run tests with MariaDB:"
    echo "   export USE_TEST_MARIADB=1"
    echo "   nox -s tests -- -m integration"
    echo ""
    echo "🛑 To stop the test database:"
    echo "   $COMPOSE_CMD -f docker-compose.test.yml down"
    echo ""
    echo "🗑️  To reset the test database:"
    echo "   $COMPOSE_CMD -f docker-compose.test.yml down -v"
    echo "   $0"
    
else
    echo "❌ Failed to set up test database"
    echo "🔍 Check logs with: $COMPOSE_CMD -f docker-compose.test.yml logs mariadb-test"
    exit 1
fi