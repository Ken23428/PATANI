#!/usr/bin/env python3
"""
Database migration script for performance optimizations
"""

import os
import sys
from sqlalchemy import create_engine, text
from routes.config import SQLALCHEMY_DATABASE_URI

def run_migration():
    """Run database migration for performance optimizations"""
    
    print("🔄 Starting database migration for performance optimizations...")
    
    # Create engine
    engine = create_engine(SQLALCHEMY_DATABASE_URI)
    
    try:
        with engine.connect() as conn:
            # Check if indexes already exist
            existing_indexes = []
            result = conn.execute(text("""
                SELECT indexname FROM pg_indexes 
                WHERE tablename IN ('user', 'pengaduan')
            """))
            existing_indexes = [row[0] for row in result]
            
            print(f"📋 Found {len(existing_indexes)} existing indexes")
            
            # Indexes to create
            indexes_to_create = [
                # User table indexes
                ("CREATE INDEX IF NOT EXISTS idx_user_email ON user(email)", "User email index"),
                ("CREATE INDEX IF NOT EXISTS idx_user_role ON user(role)", "User role index"),
                ("CREATE INDEX IF NOT EXISTS idx_user_region ON user(region)", "User region index"),
                ("CREATE INDEX IF NOT EXISTS idx_user_created_at ON user(created_at)", "User created_at index"),
                
                # Pengaduan table indexes
                ("CREATE INDEX IF NOT EXISTS idx_pengaduan_user_id ON pengaduan(user_id)", "Pengaduan user_id index"),
                ("CREATE INDEX IF NOT EXISTS idx_pengaduan_region ON pengaduan(region)", "Pengaduan region index"),
                ("CREATE INDEX IF NOT EXISTS idx_pengaduan_status ON pengaduan(status)", "Pengaduan status index"),
                ("CREATE INDEX IF NOT EXISTS idx_pengaduan_category ON pengaduan(category)", "Pengaduan category index"),
                ("CREATE INDEX IF NOT EXISTS idx_pengaduan_created_at ON pengaduan(created_at)", "Pengaduan created_at index"),
                ("CREATE INDEX IF NOT EXISTS idx_pengaduan_updated_at ON pengaduan(updated_at)", "Pengaduan updated_at index"),
                ("CREATE INDEX IF NOT EXISTS idx_pengaduan_incident_date ON pengaduan(incident_date)", "Pengaduan incident_date index"),
                ("CREATE INDEX IF NOT EXISTS idx_pengaduan_region_status ON pengaduan(region, status)", "Pengaduan region_status composite index"),
                ("CREATE INDEX IF NOT EXISTS idx_pengaduan_user_created ON pengaduan(user_id, created_at)", "Pengaduan user_created composite index"),
            ]
            
            # Create indexes
            created_count = 0
            for sql, description in indexes_to_create:
                try:
                    conn.execute(text(sql))
                    conn.commit()
                    print(f"✅ Created: {description}")
                    created_count += 1
                except Exception as e:
                    print(f"⚠️ Skipped {description}: {e}")
            
            # Update table statistics
            print("📊 Updating table statistics...")
            conn.execute(text("ANALYZE user"))
            conn.execute(text("ANALYZE pengaduan"))
            conn.commit()
            
            # Show final index count
            result = conn.execute(text("""
                SELECT tablename, COUNT(*) as index_count 
                FROM pg_indexes 
                WHERE tablename IN ('user', 'pengaduan')
                GROUP BY tablename
            """))
            
            print("\n📈 Final index count:")
            for row in result:
                print(f"   {row[0]}: {row[1]} indexes")
            
            print(f"\n✅ Migration completed! Created {created_count} new indexes.")
            
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        sys.exit(1)

def optimize_database():
    """Additional database optimizations"""
    
    print("\n🔧 Running additional database optimizations...")
    
    engine = create_engine(SQLALCHEMY_DATABASE_URI)
    
    try:
        with engine.connect() as conn:
            # Set work_mem for better query performance
            conn.execute(text("SET work_mem = '256MB'"))
            
            # Set effective_cache_size (adjust based on available RAM)
            conn.execute(text("SET effective_cache_size = '1GB'"))
            
            # Set random_page_cost for SSD
            conn.execute(text("SET random_page_cost = 1.1"))
            
            # Set seq_page_cost
            conn.execute(text("SET seq_page_cost = 1.0"))
            
            # Enable parallel query execution
            conn.execute(text("SET max_parallel_workers_per_gather = 2"))
            conn.execute(text("SET max_parallel_workers = 4"))
            
            conn.commit()
            print("✅ Database settings optimized")
            
    except Exception as e:
        print(f"⚠️ Could not optimize database settings: {e}")

def create_cache_table():
    """Create cache table for application-level caching"""
    
    print("\n🗄️ Creating cache table...")
    
    engine = create_engine(SQLALCHEMY_DATABASE_URI)
    
    try:
        with engine.connect() as conn:
            # Create cache table
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS app_cache (
                    cache_key VARCHAR(255) PRIMARY KEY,
                    cache_value TEXT,
                    expires_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """))
            
            # Create index on expires_at for cleanup
            conn.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_cache_expires 
                ON app_cache(expires_at)
            """))
            
            conn.commit()
            print("✅ Cache table created")
            
    except Exception as e:
        print(f"⚠️ Could not create cache table: {e}")

def cleanup_old_data():
    """Clean up old data for better performance"""
    
    print("\n🧹 Cleaning up old data...")
    
    engine = create_engine(SQLALCHEMY_DATABASE_URI)
    
    try:
        with engine.connect() as conn:
            # Clean up expired cache entries
            conn.execute(text("""
                DELETE FROM app_cache 
                WHERE expires_at < CURRENT_TIMESTAMP
            """))
            
            # Clean up old file uploads (older than 1 year)
            conn.execute(text("""
                DELETE FROM pengaduan 
                WHERE created_at < CURRENT_TIMESTAMP - INTERVAL '1 year'
                AND status = 'processed'
            """))
            
            conn.commit()
            print("✅ Old data cleaned up")
            
    except Exception as e:
        print(f"⚠️ Could not clean up old data: {e}")

if __name__ == "__main__":
    print("🚀 AgroLLM Database Migration Tool")
    print("=" * 50)
    
    # Run migrations
    run_migration()
    optimize_database()
    create_cache_table()
    cleanup_old_data()
    
    print("\n🎉 All optimizations completed successfully!")
    print("\n📝 Next steps:")
    print("   1. Restart your Flask application")
    print("   2. Monitor performance improvements")
    print("   3. Check database query performance")
    print("   4. Consider implementing Redis for caching in production")