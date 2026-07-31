import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def init():
    DATABASE_URL = os.getenv("DATABASE_URL")
    if not DATABASE_URL:
        print("DATABASE_URL not found in environment.")
        return

    conn = await asyncpg.connect(DATABASE_URL)
    
    # Users table might already exist, but let's ensure all columns are there
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            wallet BIGINT DEFAULT 0,
            bank BIGINT DEFAULT 0,
            bank_limit BIGINT DEFAULT 5000,
            is_frozen BOOLEAN DEFAULT FALSE,
            is_blacklisted BOOLEAN DEFAULT FALSE,
            last_daily TIMESTAMP,
            last_work TIMESTAMP
        );
    """)

    # Jackpot system tables
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS jackpot (
            id SERIAL PRIMARY KEY,
            end_time TIMESTAMP NOT NULL,
            total_prize BIGINT DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE
        );
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS jackpot_tickets (
            id SERIAL PRIMARY KEY,
            jackpot_id INTEGER REFERENCES jackpot(id),
            user_id TEXT REFERENCES users(user_id),
            ticket_count INTEGER DEFAULT 0,
            UNIQUE(jackpot_id, user_id)
        );
    """)

    # Items and Inventory
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE,
            description TEXT,
            price BIGINT,
            type TEXT -- 'usable', 'collectible', 'boost'
        );
    """)

    await conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory (
            user_id TEXT REFERENCES users(user_id),
            item_id INTEGER REFERENCES items(id),
            quantity INTEGER DEFAULT 1,
            PRIMARY KEY (user_id, item_id)
        );
    """)

    # Audit Log for Staff
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS eco_logs (
            id SERIAL PRIMARY KEY,
            staff_id TEXT,
            target_id TEXT,
            action TEXT,
            amount BIGINT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Investments Market
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS investments (
            user_id TEXT,
            ticker TEXT,
            shares BIGINT DEFAULT 0,
            PRIMARY KEY (user_id, ticker)
        );
    """)

    # Server settings for announcements
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS server_settings (
            guild_id TEXT PRIMARY KEY,
            announcement_channel_id TEXT
        );
    """)

    # Global settings (multiplier, etc.)
    await conn.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)

    print("Database initialized successfully.")
    await conn.close()

if __name__ == "__main__":
    asyncio.run(init())
