import logging

import discord
from discord.ext import commands

logger = logging.getLogger("CasinoForge.role_nicknames")
MAX_NICKNAME_LENGTH = 32
OFFICIAL_GUILD_ID = 1525859383127441620


def get_role_emoji(member: discord.Member) -> str | None:
    """Return the emoji from the highest-ranked role that has one."""
    for role in reversed(member.roles):
        emoji = getattr(role, "unicode_emoji", None)
        if emoji:
            return emoji
        emoji = getattr(role, "emoji", None)
        if emoji:
            return str(emoji)
    return None


def build_nickname(member: discord.Member) -> str | None:
    """Build '<display name> [emoji]' without accumulating old suffixes."""
    base_name = member.display_name
    had_suffix = False
    if base_name.endswith("]"):
        marker = base_name.rfind(" [")
        if marker >= 0:
            base_name = base_name[:marker].rstrip()
            had_suffix = True

    emoji = get_role_emoji(member)
    if not emoji:
        return base_name[:MAX_NICKNAME_LENGTH] if had_suffix else member.nick

    suffix = f" [{emoji}]"
    available = MAX_NICKNAME_LENGTH - len(suffix)
    return suffix[-MAX_NICKNAME_LENGTH:] if available <= 0 else f"{base_name[:available].rstrip()}{suffix}"


class RoleNicknames(commands.Cog):
    """Keep member nicknames synchronized in the official server only."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self._synced_guilds: set[int] = set()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        for guild in self.bot.guilds:
            if guild.id != OFFICIAL_GUILD_ID or guild.id in self._synced_guilds:
                continue
            self._synced_guilds.add(guild.id)
            for member in guild.members:
                await self.update_member_nickname(member)

    async def update_member_nickname(self, member: discord.Member) -> None:
        if member.guild.id != OFFICIAL_GUILD_ID or member.bot:
            return
        if not member.guild.me or not member.guild.me.guild_permissions.manage_nicknames:
            return
        if member.top_role >= member.guild.me.top_role:
            logger.warning("Cannot update nickname for %s in %s: role hierarchy prevents it.", member.id, member.guild.id)
            return

        new_nickname = build_nickname(member)
        if member.nick == new_nickname:
            return

        try:
            await member.edit(nick=new_nickname, reason="Synchronize highest emoji role nickname")
        except (discord.Forbidden, discord.HTTPException) as exc:
            logger.warning("Failed to update nickname for %s in %s: %s", member.id, member.guild.id, exc)

    @discord.app_commands.command(name="name-sync", description="Update role-emoji names for everyone in this server.")
    async def name_sync(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != OFFICIAL_GUILD_ID:
            await interaction.response.send_message(
                "❌ This command only works in the official server.",
                ephemeral=True,
            )
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ This command must be used in a server.", ephemeral=True)
            return

        updated = 0
        skipped = 0
        for member in guild.members:
            before = member.nick
            await self.update_member_nickname(member)
            if member.nick != before:
                updated += 1
            else:
                skipped += 1

        await interaction.followup.send(
            f"✅ Name sync complete. Updated **{updated}** member(s); skipped **{skipped}**.",
            ephemeral=True,
        )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self.update_member_nickname(member)

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        if before.roles != after.roles or before.nick != after.nick:
            await self.update_member_nickname(after)


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(RoleNicknames(bot))
