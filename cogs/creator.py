# -*- coding: utf-8 -*-
"""
CasinoForge - Creator Cog
Developer-only commands for bot management
"""

import discord
from discord import app_commands
from discord.ext import commands
import asyncio
import logging
import sys
import os
from datetime import datetime, timezone

logger = logging.getLogger('CasinoForge.Creator')

def CreatorOnly():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id not in interaction.client.creator_ids:
            await interaction.response.send_message(
                "❌ This command is restricted to the bot creator.",
                ephemeral=True
            )
            return False
        return True
    return app_commands.check(predicate)

class Creator(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="maintenance", description="[Creator] Toggles global maintenance mode.")
    @CreatorOnly()
    async def maintenance(self, interaction: discord.Interaction):
        """Toggle maintenance mode."""
        self.bot.maintenance_mode = not self.bot.maintenance_mode
        status = "ENABLED 🛠️" if self.bot.maintenance_mode else "DISABLED ✅"
        
        await interaction.response.send_message(
            f"🚧 **Maintenance Mode** is now **{status}**.\n"
            f"{'Regular users can no longer play casino games.' if self.bot.maintenance_mode else 'Regular users can now play games again.'}",
            ephemeral=True
        )
        logger.info(f"Maintenance mode toggled to: {self.bot.maintenance_mode}")

    @app_commands.command(name="dev-logs", description="[Creator] Fetch the latest bot logs.")
    @CreatorOnly()
    async def dev_logs(self, interaction: discord.Interaction):
        """Fetch logs from in-memory buffer (Wispbyte compatible)."""
        try:
            from main import log_buffer
            logs = list(log_buffer)[-25:]
            if not logs:
                await interaction.response.send_message("📜 **No logs available yet.**", ephemeral=True)
                return
            log_text = "\n".join(logs)
            await interaction.response.send_message(f"📜 **Latest Logs (last 25):**\n```\n{log_text}\n```", ephemeral=True)
        except ImportError:
            # Fallback if imported directly from cogs directory
            await interaction.response.send_message("📜 **Logs are available in the Wispbyte Console tab.**\nUse the panel to view full logs.", ephemeral=True)
        except Exception:
            await interaction.response.send_message("❌ Could not retrieve logs. Check the Wispbyte Console.", ephemeral=True)

    @app_commands.command(name="dev-leave", description="[Creator] Force the bot to leave a guild.")
    @CreatorOnly()
    @app_commands.describe(guild_id="ID of the guild to leave")
    async def dev_leave(self, interaction: discord.Interaction, guild_id: str):
        """Force leave guild."""
        guild = self.bot.get_guild(int(guild_id))
        if guild:
            await guild.leave()
            await interaction.response.send_message(f"👋 Left guild: **{guild.name}**", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Guild not found.", ephemeral=True)

    @app_commands.command(name="dev-reload", description="[Creator] Hot-reload a cog module.")
    @CreatorOnly()
    @app_commands.describe(module="Module name: gambling, action, staff, creator, or fun")
    async def dev_reload(self, interaction: discord.Interaction, module: str):
        """Developer: Reload a cog."""
        await interaction.response.defer(ephemeral=True)
        try:
            await self.bot.reload_extension(f"cogs.{module.lower()}")
            await interaction.followup.send(
                f"🔄 Module `cogs.{module.lower()}` successfully reloaded!"
            )
            logger.info(f"Reloaded cog: cogs.{module.lower()}")
        except Exception as e:
            await interaction.followup.send(
                f"❌ **Reload Failed:**\n```py\n{e}\n```"
            )
            logger.error(f"Failed to reload cog: {e}")

    @app_commands.command(name="dev-status", description="[Creator] Check bot status and stats.")
    @CreatorOnly()
    async def dev_status(self, interaction: discord.Interaction):
        """Developer: Check bot status."""
        embed = discord.Embed(
            title="🤖 Bot Status",
            color=discord.Color.green()
        )
        embed.add_field(name="Bot Name", value=self.bot.user.name, inline=True)
        embed.add_field(name="Bot ID", value=self.bot.user.id, inline=True)
        embed.add_field(name="Latency", value=f"{self.bot.latency * 1000:.2f}ms", inline=True)
        embed.add_field(name="Guilds", value=len(self.bot.guilds), inline=True)
        embed.add_field(name="Maintenance", value="ON 🛠️" if self.bot.maintenance_mode else "OFF ✅", inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="dev-shutdown", description="[Creator] Shutdown the bot.")
    @CreatorOnly()
    async def dev_shutdown(self, interaction: discord.Interaction):
        """Developer: Shutdown bot. Wispbyte will auto-restart unless stopped from panel."""
        await interaction.response.send_message(
            "🛑 **Bot shutting down...**\n\n"
            "⚠️ Note: On Wispbyte, the server may auto-restart the bot.\n"
            "To fully stop it, use the **Stop** button in your Wispbyte panel.",
        )
        logger.warning("Bot shutdown initiated by creator")
        await self.bot.close()

    @app_commands.command(name="dev-sync", description="[Creator] Sync slash commands globally.")
    @CreatorOnly()
    async def dev_sync(self, interaction: discord.Interaction):
        """Developer: Sync slash commands."""
        await interaction.response.defer(ephemeral=True)
        try:
            synced = await self.bot.tree.sync()
            await interaction.followup.send(
                f"✅ Synced **{len(synced)}** command(s) globally."
            )
            logger.info(f"Synced {len(synced)} commands")
        except Exception as e:
            await interaction.followup.send(
                f"❌ Sync failed: {e}"
            )
            logger.error(f"Failed to sync commands: {e}")

    @app_commands.command(name="dev-eval", description="[Creator] Evaluate Python code.")
    @CreatorOnly()
    @app_commands.describe(code="Python code to evaluate")
    async def dev_eval(self, interaction: discord.Interaction, code: str):
        """Developer: Eval code."""
        await interaction.response.defer(ephemeral=True)
        try:
            result = eval(code)
            await interaction.followup.send(f"✅ **Result:**\n```py\n{result}\n```")
        except Exception as e:
            await interaction.followup.send(f"❌ **Error:**\n```py\n{e}\n```")

    @app_commands.command(name="dev-sql", description="[Creator] Execute a raw SQL query.")
    @CreatorOnly()
    @app_commands.describe(query="SQL query to execute")
    async def dev_sql(self, interaction: discord.Interaction, query: str):
        """Developer: Run SQL."""
        await interaction.response.defer(ephemeral=True)
        try:
            async with self.bot.db_pool.acquire() as conn:
                if query.strip().lower().startswith("select"):
                    rows = await conn.fetch(query)
                    if not rows:
                        await interaction.followup.send("✅ Query executed successfully. No results returned.")
                        return
                    
                    header = " | ".join(rows[0].keys())
                    lines = [header, "-" * len(header)]
                    for row in rows[:10]:
                        lines.append(" | ".join(str(v) for v in row.values()))
                    
                    result_text = "\n".join(lines)
                    if len(rows) > 10:
                        result_text += f"\n... and {len(rows) - 10} more rows."
                        
                    await interaction.followup.send(f"📊 **Query Results:**\n```\n{result_text}\n```")
                else:
                    status = await conn.execute(query)
                    await interaction.followup.send(f"✅ Query executed successfully: `{status}`")
        except Exception as e:
            await interaction.followup.send(f"❌ **Database Error:**\n```py\n{e}\n```")

    @app_commands.command(name="dev-guilds", description="[Creator] List all guilds the bot is in.")
    @CreatorOnly()
    async def dev_guilds(self, interaction: discord.Interaction):
        """Developer: List guilds."""
        guilds = self.bot.guilds
        guild_list = "\n".join([f"• {g.name} ({g.id}) - {g.member_count} members" for g in guilds[:20]])
        
        embed = discord.Embed(
            title=f"🏰 Connected Guilds ({len(guilds)})",
            description=guild_list if guild_list else "No guilds found.",
            color=discord.Color.blue()
        )
        if len(guilds) > 20:
            embed.set_footer(text=f"Showing first 20 out of {len(guilds)} guilds.")
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(
        name="global-announcement-setup", 
        description="[Admin] Set the channel where global announcements will be received."
    )
    @app_commands.checks.has_permissions(manage_channels=True)
    @app_commands.describe(channel="The channel where announcements should go")
    async def global_announcement_setup(self, interaction: discord.Interaction, channel: discord.TextChannel):
        await interaction.response.defer(ephemeral=True)
        
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO server_settings (guild_id, announcement_channel_id)
                VALUES ($1, $2)
                ON CONFLICT (guild_id) 
                DO UPDATE SET announcement_channel_id = EXCLUDED.announcement_channel_id
                """,
                str(interaction.guild_id),
                str(channel.id)
            )
            
        await interaction.followup.send(
            f"✅ Successfully set {channel.mention} as this server's global announcement channel!",
            ephemeral=True
        )

    @app_commands.command(
        name="global-say", 
        description="[Creator] Broadcast an announcement to all configured server channels."
    )
    @CreatorOnly()
    @app_commands.describe(message="The message or announcement content to broadcast everywhere")
    async def global_say(self, interaction: discord.Interaction, message: str):
        await interaction.response.defer(ephemeral=True)
        
        rows = []
        try:
            conn = await asyncio.wait_for(self.bot.db_pool.acquire(), timeout=10.0)
            async with conn:
                rows = await conn.fetch("SELECT announcement_channel_id FROM server_settings")
        except Exception:
            await interaction.followup.send("❌ **Database connection timeout.** Could not fetch announcement channels. Check your DATABASE_URL.", ephemeral=True)
            return

        if not rows:
            await interaction.followup.send(
                "❌ No servers have configured a global announcement channel using `/global-announcement-setup` yet.",
                ephemeral=True
            )
            return

        success_count = 0
        fail_count = 0
        for row in rows:
            channel_id = int(row['announcement_channel_id'])
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                try:
                    channel = await self.bot.fetch_channel(channel_id)
                except Exception:
                    fail_count += 1
                    continue
            try:
                await channel.send(message)
                success_count += 1
            except Exception:
                fail_count += 1

        await interaction.followup.send(
            f"📢 **Global Announcement Dispatched!**\n"
            f"✅ Sent successfully to **{success_count}** channel(s).\n"
            f"❌ Failed/Skipped **{fail_count}** channel(s).",
            ephemeral=True
        )


    @app_commands.command(name="dev-shell", description="[Creator] Execute a shell command.")
    @CreatorOnly()
    @app_commands.describe(command="Shell command to run")
    async def dev_shell(self, interaction: discord.Interaction, command: str):
        """Developer: Run shell command. Not available on Wispbyte - use the Console tab instead."""
        await interaction.response.send_message(
            "⚠️ **Shell commands are not available on Wispbyte.**\n"
            "Wispbyte runs the bot in a container without shell access.\n"
            "To run commands, use the **Console** tab in your Wispbyte panel.\n"
            "You can type commands directly in the console.",
            ephemeral=True
        )

    @app_commands.command(name="dev-reboot", description="[Creator] Reboot the bot process.")
    @CreatorOnly()
    async def dev_reboot(self, interaction: discord.Interaction):
        """Developer: Reboot bot. Not available on Wispbyte - use panel restart."""
        await interaction.response.send_message(
            "⚠️ **Reboot is not available on Wispbyte.**\n"
            "The bot runs in a container and cannot self-restart.\n"
            "To reboot, go to your **Wispbyte panel → Console → Restart**.\n\n"
            "Alternatively, use `/dev-reload <module>` to reload a specific cog without restarting.",
            ephemeral=True
        )

    @app_commands.command(name="dev-inst-jp", description="[Creator] Forcefully end and announce the jackpot winner instantly.")
    @CreatorOnly()
    async def dev_inst_jp(self, interaction: discord.Interaction):
        """Forcefully end jackpot."""
        await interaction.response.defer(ephemeral=True)
        
        async with self.bot.db_pool.acquire() as conn:
            # Find active jackpot
            jackpot = await conn.fetchrow("SELECT id, total_prize FROM jackpot WHERE is_active = TRUE")
            
            if not jackpot:
                return await interaction.followup.send("❌ No active jackpot found to end.", ephemeral=True)
            
            jackpot_id = jackpot['id']
            total_prize = jackpot['total_prize']
            
            # Get all participants
            tickets = await conn.fetch("SELECT user_id, ticket_count FROM jackpot_tickets WHERE jackpot_id = $1", jackpot_id)
            
            if not tickets:
                await conn.execute("UPDATE jackpot SET is_active = FALSE WHERE id = $1", jackpot_id)
                return await interaction.followup.send("❌ No one bought tickets for this jackpot.", ephemeral=True)
            
            # Pick a winner
            import random
            weighted_users = []
            for t in tickets:
                weighted_users.extend([t['user_id']] * t['ticket_count'])
            
            winner_id = random.choice(weighted_users)
            
            # Update database
            async with conn.transaction():
                await conn.execute("UPDATE users SET wallet = wallet + $1 WHERE user_id = $2", total_prize, winner_id)
                await conn.execute("UPDATE jackpot SET is_active = FALSE WHERE id = $1", jackpot_id)
            
            # Notify winner and participants
            winner_user = await self.bot.fetch_user(int(winner_id))
            winner_name = winner_user.display_name if winner_user else "Unknown"
            
            for t in tickets:
                try:
                    user = await self.bot.fetch_user(int(t['user_id']))
                    if user:
                        if t['user_id'] == winner_id:
                            await user.send(
                                f"🎉 **JACKPOT WINNER!** 🎉\n"
                                f"Congratulations! You won the jackpot prize of **{total_prize:,}** coins!\n"
                                f"-# The Dev forcefully end the Jackpot waits"
                            )
                        else:
                            await user.send(
                                f"🎰 **Jackpot Results** 🎰\n"
                                f"The jackpot has been forcefully ended by a developer.\n"
                                f"Winner: **{winner_name}**\n"
                                f"Total Prize: **{total_prize:,}** coins.\n"
                                f"-# The Dev forcefully end the Jackpot waits"
                            )
                except Exception as e:
                    logger.warning(f"Could not send DM to user {t['user_id']}: {e}")
                    
        await interaction.followup.send(f"✅ Jackpot #{jackpot_id} forcefully ended. Winner: **{winner_name}**.", ephemeral=True)

    @app_commands.command(name="dev-gift", description="[Creator] Gift coins to a user via DM with a claim button.")
    @CreatorOnly()
    @app_commands.describe(user="User to gift coins to", amount="Amount of coins to gift")
    async def dev_gift(self, interaction: discord.Interaction, user: discord.User, amount: int):
        """Developer: Gift coins to a user via DM with a claim button."""
        if amount <= 0:
            return await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
        
        await interaction.response.defer(ephemeral=True)
        
        # Ensure the user exists in the database
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                str(user.id)
            )
        
        # Create the claim view
        view = DevGiftView(self.bot.db_pool, self.bot, interaction.user, user, amount)
        
        # Create the gift embed
        embed = discord.Embed(
            title="🎁 Dev Gift Received!",
            description=f"A developer has gifted you **{amount:,} Coins**!",
            color=discord.Color.gold()
        )
        embed.set_footer(text=f"Gifted by: {interaction.user.display_name} ({interaction.user.name})")
        
        # Try to send DM
        try:
            await user.send(embed=embed, view=view)
            await interaction.followup.send(
                f"✅ Sent a gift of **{amount:,}** coins to **{user.display_name}** via DM!",
                ephemeral=True
            )
        except discord.Forbidden:
            await interaction.followup.send(
                f"❌ Could not send DM to {user.mention}. They may have DMs disabled.",
                ephemeral=True
            )

    @app_commands.command(name="dev-multiplier", description="[Creator] Set a global multiplier for all income and gambling payouts.")
    @CreatorOnly()
    @app_commands.describe(multiplier="Multiplier amount (e.g. 1.5 for 1.5x)")
    async def dev_multiplier(self, interaction: discord.Interaction, multiplier: float):
        """Set the global income/gambling multiplier."""
        if multiplier < 0.1 or multiplier > 10.0:
            return await interaction.response.send_message("❌ Multiplier must be between 0.1 and 10.0.", ephemeral=True)
        
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO settings (key, value) VALUES ('global_multiplier', $1) ON CONFLICT (key) DO UPDATE SET value = $1",
                str(multiplier)
            )
        
        self.bot.global_multiplier = multiplier
        
        await interaction.response.send_message(
            f"✅ Global multiplier set to **{multiplier}x**. All income and gambling payouts will be multiplied by this amount. Set to **1.0** to reset to normal.",
            ephemeral=True
        )
        logger.info(f"Global multiplier set to {multiplier}x by {interaction.user.id}")


class DevGiftView(discord.ui.View):
    def __init__(self, db_pool, bot, dev_user, target_user, amount):
        super().__init__(timeout=None)  # Persistent view, no timeout
        self.db_pool = db_pool
        self.bot = bot
        self.dev_user = dev_user
        self.target_user = target_user
        self.amount = amount

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message(
                "❌ This gift is not for you!",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Claim Now", style=discord.ButtonStyle.green, custom_id="dev_gift_claim")
    async def claim(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        try:
            async with self.db_pool.acquire() as conn:
                await conn.execute(
                    "UPDATE users SET wallet = wallet + $1 WHERE user_id = $2",
                    self.amount,
                    str(self.target_user.id)
                )
            
            # Disable all buttons so it can't be claimed again
            for child in self.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            
            # Update the message to show it's been claimed
            embed = discord.Embed(
                title="✅ Gift Claimed!",
                description=f"You have successfully claimed **{self.amount:,} Coins** from **{self.dev_user.display_name}**!",
                color=discord.Color.green()
            )
            embed.set_footer(text=f"Gifted by: {self.dev_user.display_name} ({self.dev_user.name})")
            
            await interaction.edit_original_response(embed=embed, view=None)
            logger.info(f"Dev gift claimed: {self.target_user.id} received {self.amount} coins from {self.dev_user.id}")
        except Exception as e:
            logger.error(f"Failed to claim dev gift: {e}")
            await interaction.followup.send(f"❌ Failed to claim gift. Please try again or contact support.\nError: `{e}`", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(Creator(bot))
    logger.info("Creator cog loaded")
