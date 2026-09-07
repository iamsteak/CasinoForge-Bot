"""Profile and Top.gg voting commands for CasinoForge."""

import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("CasinoForge")
TOPGG_VOTE_URL = "https://top.gg/bot/1524862325927182536/vote"


class Profile(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="profile", description="View your CasinoForge economy profile.")
    @app_commands.describe(user="Optionally view another member's profile")
    async def profile(self, interaction: discord.Interaction, user: discord.User | None = None):
        target = user or interaction.user
        user_id = str(target.id)

        try:
            async with self.bot.db_pool.acquire() as conn:
                row = await conn.fetchrow(
                    """
                    SELECT wallet, bank, bank_limit, last_daily, last_work,
                           is_frozen, is_blacklisted
                    FROM users WHERE user_id = $1
                    """,
                    user_id,
                )
                if row is None:
                    await conn.execute(
                        "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                        user_id,
                    )
                    row = await conn.fetchrow(
                        """
                        SELECT wallet, bank, bank_limit, last_daily, last_work,
                               is_frozen, is_blacklisted
                        FROM users WHERE user_id = $1
                        """,
                        user_id,
                    )

                investment_count = await conn.fetchval(
                    "SELECT COUNT(*) FROM investments WHERE user_id = $1 AND shares > 0",
                    user_id,
                )
                games_played = await conn.fetchval(
                    "SELECT COUNT(*) FROM transaction_log WHERE user_id = $1",
                    user_id,
                )
                wins = await conn.fetchval(
                    """
                    SELECT COUNT(*) FROM transaction_log
                    WHERE user_id = $1 AND LOWER(COALESCE(result, '')) LIKE '%win%'
                    """,
                    user_id,
                )
                votes = await conn.fetchval(
                    "SELECT COUNT(*) FROM vote_claims WHERE user_id = $1",
                    user_id,
                )
        except Exception:
            logger.exception("Profile lookup failed for user %s", user_id)
            await interaction.response.send_message(
                "⚠️ I couldn't load that profile right now. Please try again shortly.",
                ephemeral=True,
            )
            return

        wallet = int(row["wallet"] or 0)
        bank = int(row["bank"] or 0)
        total = wallet + bank
        embed = discord.Embed(
            title=f"📊 {target.display_name}'s Profile",
            color=discord.Color.gold(),
            timestamp=datetime.now(timezone.utc),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        embed.add_field(name="💰 Wallet", value=f"**{wallet:,}** coins", inline=True)
        embed.add_field(name="🏦 Bank", value=f"**{bank:,}** / **{int(row['bank_limit'] or 0):,}**", inline=True)
        embed.add_field(name="💎 Total Wealth", value=f"**{total:,}** coins", inline=True)
        embed.add_field(name="🎮 Games Played", value=f"**{int(games_played or 0):,}**", inline=True)
        embed.add_field(name="🏆 Recorded Wins", value=f"**{int(wins or 0):,}**", inline=True)
        embed.add_field(name="📈 Investments", value=f"**{int(investment_count or 0):,}** position(s)", inline=True)
        embed.add_field(name="🗳️ Top.gg Votes", value=f"**{int(votes or 0):,}** claimed", inline=True)

        status = []
        if row["is_frozen"]:
            status.append("Frozen")
        if row["is_blacklisted"]:
            status.append("Blacklisted")
        embed.add_field(name="Status", value=", ".join(status) if status else "Active", inline=True)
        embed.set_footer(text="CasinoForge uses virtual currency only.")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="vote", description="Vote for CasinoForge on Top.gg and receive bonus coins.")
    async def vote(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🗳️ Vote for CasinoForge",
            description=(
                f"Support CasinoForge on Top.gg and receive **5,000 coins** when your vote is confirmed.\n\n"
                f"[Vote on Top.gg]({TOPGG_VOTE_URL})"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="Rewards are delivered automatically after Top.gg confirms the vote.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Profile(bot))
    logger.info("Profile cog loaded successfully")
