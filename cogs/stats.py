# -*- coding: utf-8 -*-
"""
CasinoForge - Stats Cog
Provides a /stats command and an HTTP API endpoint for live bot statistics.
"""

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
from datetime import datetime, timezone

logger = logging.getLogger('CasinoForge.Stats')

class StatsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.start_time = datetime.now(timezone.utc)

    async def get_live_stats(self):
        """Fetch live stats from the database."""
        stats = {
            "status": "online",
            "uptime": None,
            "guilds": len(self.bot.guilds),
            "users": 0,
            "total_wallet": 0,
            "total_bank": 0,
            "games_played": 0,
            "jackpot_active": False,
            "jackpot_prize": 0,
            "global_multiplier": self.bot.global_multiplier,
            "maintenance": self.bot.maintenance_mode,
            "version": "2.0.0",
            "updated_at": datetime.now(timezone.utc).isoformat()
        }

        # Calculate uptime
        delta = datetime.now(timezone.utc) - self.start_time
        hours = int(delta.total_seconds() // 3600)
        minutes = int((delta.total_seconds() % 3600) // 60)
        stats["uptime"] = f"{hours}h {minutes}m"

        try:
            async with self.bot.db_pool.acquire() as conn:
                # Total registered users
                user_count = await conn.fetchval("SELECT COUNT(*) FROM users")
                stats["users"] = int(user_count) if user_count else 0

                # Total coins in circulation
                total_wallet = await conn.fetchval("SELECT COALESCE(SUM(wallet), 0) FROM users")
                total_bank = await conn.fetchval("SELECT COALESCE(SUM(bank), 0) FROM users")
                stats["total_wallet"] = int(total_wallet) if total_wallet else 0
                stats["total_bank"] = int(total_bank) if total_bank else 0

                # Active jackpots
                active_jackpot = await conn.fetchrow(
                    "SELECT total_prize FROM jackpot WHERE is_active = TRUE ORDER BY id DESC LIMIT 1"
                )
                if active_jackpot:
                    stats["jackpot_active"] = True
                    stats["jackpot_prize"] = int(active_jackpot["total_prize"])

                # Games played (from transaction log)
                games_played = await conn.fetchval("SELECT COUNT(*) FROM transaction_log")
                stats["games_played"] = int(games_played) if games_played else 0

        except Exception as e:
            logger.warning(f"Could not fetch live stats from DB: {e}")

        return stats

    @app_commands.command(name="stats", description="View CasinoForge bot statistics")
    async def stats(self, interaction: discord.Interaction):
        stats = await self.get_live_stats()

        embed = discord.Embed(
            title="📊 CasinoForge Stats",
            color=discord.Color.blue()
        )
        embed.set_footer(text=f"Updated at {stats['updated_at'][:19]} UTC")

        embed.add_field(name="🟢 Status", value="Online" if not stats["maintenance"] else "Maintenance", inline=True)
        embed.add_field(name="⏱️ Uptime", value=stats["uptime"], inline=True)
        embed.add_field(name="🖥️ Version", value=stats["version"], inline=True)
        embed.add_field(name="🏠 Servers", value=f"{stats['guilds']:,}", inline=True)
        embed.add_field(name="👥 Users", value=f"{stats['users']:,}", inline=True)
        embed.add_field(name="🎰 Games Played", value=f"{stats['games_played']:,}", inline=True)
        embed.add_field(name="💰 Wallet Total", value=f"{stats['total_wallet']:,} coins", inline=True)
        embed.add_field(name="🏦 Bank Total", value=f"{stats['total_bank']:,} coins", inline=True)
        embed.add_field(name="⚙️ Multiplier", value=f"{stats['global_multiplier']}x", inline=True)

        if stats["jackpot_active"]:
            embed.add_field(
                name="🎡 Active Jackpot",
                value=f"{stats['jackpot_prize']:,} coins",
                inline=False
            )

        await interaction.response.send_message(embed=embed)


async def setup(bot):
    await bot.add_cog(StatsCog(bot))
