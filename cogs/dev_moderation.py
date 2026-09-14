# -*- coding: utf-8 -*-
"""Creator-only development and moderation controls for CasinoForge."""
import logging
from datetime import datetime, timezone

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("CasinoForge.DevModeration")


def CreatorOnly():
    async def predicate(interaction: discord.Interaction) -> bool:
        if interaction.user.id not in interaction.client.creator_ids:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "❌ This command is restricted to the bot creator.",
                    ephemeral=True,
                )
            return False
        return True

    return app_commands.check(predicate)


class DevModeration(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def ensure_user(self, user_id: str) -> None:
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                user_id,
            )

    async def resolve_user(self, user_id: str) -> discord.User | None:
        try:
            return self.bot.get_user(int(user_id)) or await self.bot.fetch_user(int(user_id))
        except (ValueError, discord.NotFound, discord.HTTPException):
            return None

    @app_commands.command(name="dev-warn", description="[Creator] Warn a Discord user by ID.")
    @app_commands.describe(user_id="The user's Discord ID", reason="Reason for the warning")
    @CreatorOnly()
    async def dev_warn(self, interaction: discord.Interaction, user_id: str, reason: str):
        """Create a persistent warning and notify the target by DM."""
        user_id = user_id.strip()
        if not user_id.isdigit():
            return await interaction.response.send_message("❌ User ID must contain only numbers.", ephemeral=True)
        if not reason.strip():
            return await interaction.response.send_message("❌ A warning reason is required.", ephemeral=True)

        target = await self.resolve_user(user_id)
        if target is None:
            return await interaction.response.send_message("❌ I could not find that Discord user.", ephemeral=True)

        await self.ensure_user(user_id)
        async with self.bot.db_pool.acquire() as conn:
            warning = await conn.fetchrow(
                """
                INSERT INTO user_warnings (user_id, moderator_id, reason)
                VALUES ($1, $2, $3)
                RETURNING id, created_at
                """,
                user_id,
                str(interaction.user.id),
                reason.strip(),
            )
            warning_count = await conn.fetchval(
                "SELECT COUNT(*) FROM user_warnings WHERE user_id = $1",
                user_id,
            )

        dm_status = "DM sent"
        try:
            await target.send(
                f"⚠️ **You have received a warning in CasinoForge.**\n\n"
                f"**Warned by:** {interaction.user} (ID: `{interaction.user.id}`)\n"
                f"**Reason:** {reason.strip()}\n"
                f"**Warning count:** `{warning_count}`"
            )
        except (discord.Forbidden, discord.HTTPException):
            dm_status = "DM could not be sent (DMs may be disabled)"

        await interaction.response.send_message(
            f"✅ Warned **{target}** (`{user_id}`).\n"
            f"**Warning count:** `{warning_count}`\n**{dm_status}.**",
            ephemeral=True,
        )
        logger.info("Creator %s warned user %s: %s", interaction.user.id, user_id, reason.strip())

    @app_commands.command(name="dev-eco", description="[Creator] Add or remove wallet coins by user ID.")
    @app_commands.describe(value="Amount to add; use a negative value to remove coins", user_id="The user's Discord ID")
    @CreatorOnly()
    async def dev_eco(self, interaction: discord.Interaction, value: int, user_id: str):
        """Adjust a user's wallet, allowing positive or negative values."""
        user_id = user_id.strip()
        if not user_id.isdigit():
            return await interaction.response.send_message("❌ User ID must contain only numbers.", ephemeral=True)
        if value == 0:
            return await interaction.response.send_message("❌ Value cannot be zero.", ephemeral=True)

        await self.ensure_user(user_id)
        async with self.bot.db_pool.acquire() as conn:
            async with conn.transaction():
                old_balance = await conn.fetchval(
                    "SELECT wallet FROM users WHERE user_id = $1 FOR UPDATE",
                    user_id,
                )
                new_balance = max(0, old_balance + value)
                applied = new_balance - old_balance
                await conn.execute("UPDATE users SET wallet = $1 WHERE user_id = $2", new_balance, user_id)
                await conn.execute(
                    "INSERT INTO eco_logs (staff_id, target_id, action, amount) VALUES ($1, $2, $3, $4)",
                    str(interaction.user.id), user_id, "DEV_ADJUST", applied,
                )

        target = await self.resolve_user(user_id)
        label = str(target) if target else f"user `{user_id}`"
        await interaction.response.send_message(
            f"✅ Updated **{label}**'s wallet.\n"
            f"**Change:** `{applied:+,}` coins\n**New balance:** `{new_balance:,}` coins",
            ephemeral=True,
        )
        logger.info("Creator %s changed wallet for %s by %s", interaction.user.id, user_id, applied)

    @app_commands.command(name="dev-cogs", description="[Creator] Permanently enable or disable a cog.")
    @app_commands.describe(cog="Cog module name, such as gambling or fun", action="Enable or disable the cog")
    @app_commands.choices(action=[
        app_commands.Choice(name="Enable", value="enable"),
        app_commands.Choice(name="Disable", value="disable"),
    ])
    @CreatorOnly()
    async def dev_cogs(self, interaction: discord.Interaction, cog: str, action: app_commands.Choice[str]):
        """Persist a cog's enabled state and update the running bot immediately."""
        cog_name = cog.strip().lower().removeprefix("cogs.")
        allowed = {extension.rsplit(".", 1)[-1] for extension in getattr(self.bot, "initial_cogs", [])}
        if cog_name not in allowed:
            return await interaction.response.send_message(
                f"❌ Unknown cog `{cog_name}`. Available cogs: `{', '.join(sorted(allowed))}`.",
                ephemeral=True,
            )
        if cog_name in {"creator", "dev_moderation"} and action.value == "disable":
            return await interaction.response.send_message("❌ Core creator controls cannot be disabled.", ephemeral=True)

        enabled = action.value == "enable"
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO cog_settings (cog_name, enabled, updated_by)
                VALUES ($1, $2, $3)
                ON CONFLICT (cog_name) DO UPDATE SET enabled = EXCLUDED.enabled, updated_by = EXCLUDED.updated_by, updated_at = CURRENT_TIMESTAMP
                """,
                cog_name, enabled, str(interaction.user.id),
            )
        extension = f"cogs.{cog_name}"
        try:
            if enabled:
                self.bot.disabled_cogs.discard(cog_name)
            else:
                self.bot.disabled_cogs.add(cog_name)
            await interaction.response.send_message(
                f"✅ Cog `{cog_name}` is now **{'enabled' if enabled else 'disabled'}**.\n"
                f"This setting is saved in the database and survives restarts.",
                ephemeral=True,
            )
            if enabled and extension not in self.bot.extensions:
                await self.bot.load_extension(extension)
            elif not enabled and extension in self.bot.extensions:
                await self.bot.unload_extension(extension)
        except Exception as exc:
            logger.exception("Could not apply cog state for %s", cog_name)
            await interaction.followup.send(
                f"⚠️ The database setting was saved, but the live cog change failed: `{exc}`",
                ephemeral=True,
            )

    @app_commands.command(name="dev-warnings", description="[Creator] View a user's warning history.")
    @app_commands.describe(user_id="The user's Discord ID")
    @CreatorOnly()
    async def dev_warnings(self, interaction: discord.Interaction, user_id: str):
        """Display the latest warnings for a user."""
        user_id = user_id.strip()
        if not user_id.isdigit():
            return await interaction.response.send_message("❌ User ID must contain only numbers.", ephemeral=True)
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT moderator_id, reason, created_at FROM user_warnings WHERE user_id = $1 ORDER BY created_at DESC LIMIT 10",
                user_id,
            )
        if not rows:
            return await interaction.response.send_message(f"ℹ️ User `{user_id}` has no recorded warnings.", ephemeral=True)
        lines = [
            f"`{index}.` <@{row['moderator_id']}> — {row['reason']} ({row['created_at'].strftime('%Y-%m-%d %H:%M UTC')})"
            for index, row in enumerate(rows, 1)
        ]
        await interaction.response.send_message(
            f"⚠️ **Warnings for `{user_id}`** ({len(rows)} shown)\n" + "\n".join(lines),
            ephemeral=True,
        )

    @app_commands.command(name="dev-unwarn", description="[Creator] Remove a user's latest warning.")
    @app_commands.describe(user_id="The user's Discord ID")
    @CreatorOnly()
    async def dev_unwarn(self, interaction: discord.Interaction, user_id: str):
        """Remove the most recent warning for a user."""
        user_id = user_id.strip()
        if not user_id.isdigit():
            return await interaction.response.send_message("❌ User ID must contain only numbers.", ephemeral=True)
        async with self.bot.db_pool.acquire() as conn:
            removed = await conn.fetchrow(
                "DELETE FROM user_warnings WHERE id = (SELECT id FROM user_warnings WHERE user_id = $1 ORDER BY created_at DESC LIMIT 1) RETURNING reason",
                user_id,
            )
        if not removed:
            return await interaction.response.send_message("ℹ️ That user has no warnings to remove.", ephemeral=True)
        await interaction.response.send_message(f"✅ Removed the latest warning for `{user_id}`: {removed['reason']}", ephemeral=True)

    @app_commands.command(name="dev-userinfo", description="[Creator] Inspect a user's account by ID.")
    @app_commands.describe(user_id="The user's Discord ID")
    @CreatorOnly()
    async def dev_userinfo(self, interaction: discord.Interaction, user_id: str):
        """Show economy, warning, and account flags for any user ID."""
        user_id = user_id.strip()
        if not user_id.isdigit():
            return await interaction.response.send_message("❌ User ID must contain only numbers.", ephemeral=True)
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT wallet, bank, bank_limit, is_frozen, is_blacklisted FROM users WHERE user_id = $1",
                user_id,
            )
            warning_count = await conn.fetchval("SELECT COUNT(*) FROM user_warnings WHERE user_id = $1", user_id)
        if not row:
            return await interaction.response.send_message(f"ℹ️ No account exists for `{user_id}` yet.", ephemeral=True)
        embed = discord.Embed(title="Developer User Info", color=discord.Color.blurple(), timestamp=datetime.now(timezone.utc))
        embed.add_field(name="User ID", value=f"`{user_id}`", inline=False)
        embed.add_field(name="Wallet", value=f"`{row['wallet']:,}`", inline=True)
        embed.add_field(name="Bank", value=f"`{row['bank']:,}` / `{row['bank_limit']:,}`", inline=True)
        embed.add_field(name="Warnings", value=f"`{warning_count}`", inline=True)
        embed.add_field(name="Frozen", value="Yes" if row['is_frozen'] else "No", inline=True)
        embed.add_field(name="Blacklisted", value="Yes" if row['is_blacklisted'] else "No", inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(DevModeration(bot))


async def teardown(bot: commands.Bot):
    logger.info("Dev moderation cog unloaded")
