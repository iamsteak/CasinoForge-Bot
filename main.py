# -*- coding: utf-8 -*-
"""
CasinoForge - Core Engine
"""

import discord
from discord import app_commands
from discord.ext import commands, tasks
import asyncpg
import os
import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta, timezone
from dotenv import load_dotenv

# Load environment variables from .env (harmless on Wispbyte; useful for local dev)
load_dotenv()

# In-memory log buffer for Wispbyte compatibility (no file logging)
log_buffer = deque(maxlen=100)

class MemoryLogHandler(logging.Handler):
    """Stores log entries in memory for retrieval via /dev-logs on Wispbyte."""
    def emit(self, record):
        log_entry = self.format(record)
        log_buffer.append(log_entry)

# 1. Advanced Logging Setup
memory_handler = MemoryLogHandler()
memory_handler.setLevel(logging.INFO)
memory_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))

root_logger = logging.getLogger()
root_logger.setLevel(logging.INFO)
root_logger.addHandler(console_handler)
root_logger.addHandler(memory_handler)

logger = logging.getLogger('CasinoForge')

class CasinoForge(commands.Bot):
    def __init__(self, db_pool: asyncpg.Pool, creator_ids: list[int]):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True # Needed for DMs and member list
        
        super().__init__(
            command_prefix="!", 
            intents=intents,
            help_command=None 
        )
        
        self.db_pool = db_pool
        self.creator_ids = creator_ids
        self.maintenance_mode = False
        self.global_multiplier = 1.0

    async def setup_hook(self):
        # Auto-initialize database tables if not exist
        try:
            async with self.db_pool.acquire() as conn:
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
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS items (
                        id SERIAL PRIMARY KEY,
                        name TEXT UNIQUE,
                        description TEXT,
                        price BIGINT,
                        type TEXT
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
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS investments (
                        user_id TEXT,
                        ticker TEXT,
                        shares BIGINT DEFAULT 0,
                        PRIMARY KEY (user_id, ticker)
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS server_settings (
                        guild_id TEXT PRIMARY KEY,
                        announcement_channel_id TEXT
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS transaction_log (
                        id SERIAL PRIMARY KEY,
                        user_id TEXT,
                        guild_id TEXT,
                        action TEXT,
                        amount BIGINT,
                        game TEXT,
                        result TEXT,
                        timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS settings (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                """)
                logger.info("Database tables verified/initialized successfully.")
        except Exception as e:
            logger.error(f"Failed to initialize database tables: {e}")

        # Load global multiplier from DB
        try:
            async with self.db_pool.acquire() as conn:
                result = await conn.fetchval("SELECT value FROM settings WHERE key = 'global_multiplier'")
                if result:
                    self.global_multiplier = float(result)
                    logger.info(f"Loaded global multiplier: {self.global_multiplier}x")
        except Exception as e:
            logger.warning(f"Could not load global multiplier from DB: {e}")
        
        # Attach the error handler directly to the tree inside the setup hook safely
        self.tree.on_error = self.on_app_command_error

        initial_cogs = ["cogs.gambling", "cogs.staff", "cogs.creator", "cogs.fun", "cogs.action", "cogs.beg", "cogs.invest", "cogs.stats", "cogs.role_nicknames"]
        
        for cog in initial_cogs:
            try:
                await self.load_extension(cog)
                logger.info(f"Successfully loaded module: {cog}")
            except Exception as e:
                logger.warning(f"Skipped loading {cog}: {e}")

        # Register persistent views so buttons keep working after bot restart
        try:
            from cogs.creator import DevGiftView
            # DevGiftView now accepts None placeholders for startup registration.
            # Persistent views are registered so button callbacks remain active.
            self.add_view(DevGiftView(self.db_pool, self, None, None, 0))
            logger.info("Registered persistent views (DevGiftView)")
        except Exception as e:
            logger.warning(f"Failed to register persistent views: {e}")
        
        logger.info("Syncing slash commands globally...")
        await self.tree.sync()
        logger.info("Global slash commands synced successfully!")
        
        # Start background tasks
        self.jackpot_checker.start()

    async def on_ready(self):
        logger.info(f"Bot Online! Logged in as {self.user.name} (ID: {self.user.id})")
        await self.change_presence(activity=discord.Activity(type=discord.ActivityType.playing, name="High Stakes | /help"))

    @tasks.loop(minutes=5)
    async def jackpot_checker(self):
        """Check for expired jackpots and pick a winner."""
        async with self.db_pool.acquire() as conn:
            # Find active jackpots that have ended
            ended_jackpots = await conn.fetch(
                "SELECT id, total_prize FROM jackpot WHERE is_active = TRUE AND end_time <= NOW()"
            )
            
            for jackpot in ended_jackpots:
                jackpot_id = jackpot['id']
                total_prize = jackpot['total_prize']
                
                # Get all participants and their tickets
                tickets = await conn.fetch(
                    "SELECT user_id, ticket_count FROM jackpot_tickets WHERE jackpot_id = $1",
                    jackpot_id
                )
                
                if not tickets:
                    await conn.execute("UPDATE jackpot SET is_active = FALSE WHERE id = $1", jackpot_id)
                    continue
                
                # Pick a winner
                import random
                weighted_users = []
                for t in tickets:
                    weighted_users.extend([t['user_id']] * t['ticket_count'])
                
                winner_id = random.choice(weighted_users)
                
                # Update database
                async with conn.transaction():
                    await conn.execute(
                        "UPDATE users SET wallet = wallet + $1 WHERE user_id = $2",
                        total_prize, winner_id
                    )
                    await conn.execute(
                        "UPDATE jackpot SET is_active = FALSE WHERE id = $1",
                        jackpot_id
                    )
                
                # Notify participants
                winner_user = await self.fetch_user(int(winner_id))
                winner_name = winner_user.display_name if winner_user else "Unknown"
                
                for t in tickets:
                    try:
                        user = await self.fetch_user(int(t['user_id']))
                        if user:
                            if t['user_id'] == winner_id:
                                await user.send(
                                    f"🎉 **JACKPOT WINNER!** 🎉\n"
                                    f"Congratulations! You won the jackpot prize of **{total_prize:,}** coins!"
                                )
                            else:
                                await user.send(
                                    f"🎰 **Jackpot Results** 🎰\n"
                                    f"The jackpot has ended. Unfortunately, you didn't win this time.\n"
                                    f"Winner: **{winner_name}**\n"
                                    f"Total Prize: **{total_prize:,}** coins.\n"
                                    f"Better luck next time!"
                                )
                    except Exception as e:
                        logger.warning(f"Could not send DM to user {t['user_id']}: {e}")

    @jackpot_checker.before_loop
    async def before_jackpot_checker(self):
        await self.wait_until_ready()

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.CommandOnCooldown):
            seconds = error.retry_after
            if seconds >= 60:
                time_left = f"{int(seconds // 60)}m {int(seconds % 60)}s"
            else:
                time_left = f"{seconds:.1f}s"
                
            try:
                await interaction.response.send_message(
                    f"⏳ **Slow down!** You can use this command again in **{time_left}**.",
                    ephemeral=True
                )
            except Exception:
                pass
            return

        logger.error(f"Unhandled slash command error: {error}")

async def main():
    TOKEN = os.getenv("BOT_TOKEN")
    DATABASE_URL = os.getenv("DATABASE_URL")
    CREATOR_IDS = [1075340640243691520, 1307955870713380884] # DONT REMOVE IDS 

    if not TOKEN or not DATABASE_URL:
        logger.error("FATAL BOOT ERROR: BOT_TOKEN or DATABASE_URL missing from environment variables!")
        return

    logger.info("Initializing database connection pool...")
    try:
        pool = await asyncpg.create_pool(
            DATABASE_URL, 
            command_timeout=30, 
            max_inactive_connection_lifetime=300,
            statement_cache_size=0
        )
        logger.info("Connected to PostgreSQL flawlessly.")
        
        # Ensure all tables exist immediately upon connection
        async with pool.acquire() as conn:
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
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS items (
                    id SERIAL PRIMARY KEY,
                    name TEXT UNIQUE,
                    description TEXT,
                    price BIGINT,
                    type TEXT
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
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS investments (
                    user_id TEXT,
                    ticker TEXT,
                    shares BIGINT DEFAULT 0,
                    PRIMARY KEY (user_id, ticker)
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS server_settings (
                    guild_id TEXT PRIMARY KEY,
                    announcement_channel_id TEXT
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS transaction_log (
                    id SERIAL PRIMARY KEY,
                    user_id TEXT,
                    guild_id TEXT,
                    action TEXT,
                    amount BIGINT,
                    game TEXT,
                    result TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
            """)
            logger.info("All database tables successfully verified/created at startup.")
    except Exception as e:
        logger.error(f"FATAL DATABASE ERROR: Could not connect or initialize database: {e}")
        return

    async with pool:
        bot = CasinoForge(db_pool=pool, creator_ids=CREATOR_IDS)
        await bot.start(TOKEN)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot manually shut down.")
