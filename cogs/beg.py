# -*- coding: utf-8 -*-
"""
CasinoForge - Beg Command Module
"""
import discord
from discord.ext import commands
from discord import app_commands
import random
import logging

logger = logging.getLogger('CasinoForge.Beg')

class Beg(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @app_commands.command(name="beg", description="Beg for some spare change from the high rollers.")
    # chill out for 45 seconds between asking for free money
    @app_commands.checks.cooldown(1, 45.0, key=lambda i: i.user.id)
    async def beg(self, interaction: discord.Interaction):
        # 33 percent chance they get rejected to keep it slightly grindy
        if random.random() < 0.33:
            rejections = [
                "Get a job, bum!",
                "I only give to charity, and you look like trouble.",
                "Look somewhere else, I'm fresh out of cash.",
                "The high rollers laugh and walk past you."
            ]
            await interaction.response.send_message(f"❌ {random.choice(rejections)}", ephemeral=True)
            return

        earnings = random.randint(75, 350)
        user_id_str = str(interaction.user.id)

        try:
            # throw this inside a safe transaction block so asyncpg doesn't freak out
            async with self.bot.db_pool.acquire() as conn:
                async with conn.transaction():
                    # check if they have an active wallet profile setup
                    user = await conn.fetchrow("SELECT wallet FROM users WHERE user_id = $1", user_id_str)
                    
                    if user:
                        # stack the new cash directly into their wallet
                        await conn.execute(
                            "UPDATE users SET wallet = wallet + $1 WHERE user_id = $2", 
                            earnings, user_id_str
                        )
                    else:
                        # profile missing, build a new user row and deposit the change
                        await conn.execute(
                            "INSERT INTO users (user_id, wallet, bank) VALUES ($1, $2, 0)", 
                            user_id_str, earnings
                        )

            success_messages = [
                f"A generous high roller tossed you **{earnings:,}** coins!",
                f"You found **{earnings:,}** coins left behind on a blackjack table!",
                f"Someone felt bad for you and handed you **{earnings:,}** coins."
            ]
            await interaction.response.send_message(f"🪙 {random.choice(success_messages)}")

        except Exception as e:
            logger.error(f"Database error in beg command: {e}")
            await interaction.response.send_message("⚠️ An error occurred processing your transaction.", ephemeral=True)

    # capture the cooldown error so it doesn't leave an ugly track trace in console
    @beg.error
    async def beg_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        if isinstance(error, app_commands.errors.CommandOnCooldown):
            seconds_left = round(error.retry_after)
            await interaction.response.send_message(
                f"🛑 chill out, you can beg again in **{seconds_left}s**.", 
                ephemeral=True
            )
        else:
            # pass everything else up to the main handler if something actually broke
            raise error

async def setup(bot: commands.Bot):
    await bot.add_cog(Beg(bot))
    logger.info("Beg cog loaded successfully")
