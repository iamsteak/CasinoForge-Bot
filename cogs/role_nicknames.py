import logging
import unicodedata

import discord
from discord import app_commands
from discord.ext import commands

logger = logging.getLogger("CasinoForge.role_nicknames")
MAX_NICKNAME_LENGTH = 32
OFFICIAL_GUILD_ID = 1525859383127441620


def leading_emoji(text: str) -> str | None:
    """Extract a leading Unicode emoji/symbol from a role name."""
    text = text.lstrip()
    if not text:
        return None

    first = text[0]
    category = unicodedata.category(first)
    if not (category.startswith("So") or category.startswith("Sk")):
        return None

    result = [first]
    index = 1
    while index < len(text):
        char = text[index]
        codepoint = ord(char)
        category = unicodedata.category(char)
        if codepoint in (0xFE0E, 0xFE0F, 0x200D) or category in {"Mn", "Mc"} or 0x1F3FB <= codepoint <= 0x1F3FF:
            result.append(char)
            index += 1
            continue
        break
    return "".join(result)


def get_role_emoji(member: discord.Member) -> str | None:
    """Return the emoji from the highest-ranked emoji-bearing role."""
    for role in reversed(member.roles):
        role_emoji = getattr(role, "unicode_emoji", None)
        if role_emoji:
            return str(role_emoji)
        role_emoji = leading_emoji(role.name)
        if role_emoji:
            return role_emoji
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

    async def update_member_nickname(self, member: discord.Member) -> str:
        if member.guild.id != OFFICIAL_GUILD_ID:
            return "wrong_server"
        if member.bot:
            return "bot"
        if not member.guild.me or not member.guild.me.guild_permissions.manage_nicknames:
            return "missing_permission"
        if member.top_role >= member.guild.me.top_role:
            logger.warning("Cannot update nickname for %s: target role is not below the bot role.", member.id)
            return "role_hierarchy"

        new_nickname = build_nickname(member)
        if member.nick == new_nickname:
            return "unchanged"

        try:
            await member.edit(nick=new_nickname, reason="Synchronize highest emoji role nickname")
            return "updated"
        except discord.Forbidden:
            logger.warning("Discord denied nickname update for member %s.", member.id)
            return "forbidden"
        except discord.HTTPException as exc:
            logger.warning("Nickname update failed for member %s: %s", member.id, exc)
            return "api_error"

    @app_commands.command(name="name-sync", description="Update role-emoji names for everyone in this server.")
    async def name_sync(self, interaction: discord.Interaction) -> None:
        if interaction.guild_id != OFFICIAL_GUILD_ID:
            await interaction.response.send_message("❌ This command only works in the official server.", ephemeral=True)
            return

        await interaction.response.defer(ephemeral=True)
        guild = interaction.guild
        if guild is None:
            await interaction.followup.send("❌ This command must be used in a server.", ephemeral=True)
            return

        # Fetch the current member list instead of relying only on the local cache.
        members = [member async for member in guild.fetch_members(limit=None)]
        counts = {key: 0 for key in ("updated", "unchanged", "bot", "missing_permission", "role_hierarchy", "forbidden", "api_error")}
        for member in members:
            result = await self.update_member_nickname(member)
            counts[result] = counts.get(result, 0) + 1

        await interaction.followup.send(
            "✅ **Name sync complete.**\n"
            f"Updated: **{counts['updated']}** | Already correct: **{counts['unchanged']}**\n"
            f"No emoji role/bot: **{counts['bot']}** | Role hierarchy: **{counts['role_hierarchy']}**\n"
            f"Permission/API failures: **{counts['missing_permission'] + counts['forbidden'] + counts['api_error']}**",
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
