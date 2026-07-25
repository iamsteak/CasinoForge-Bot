# -*- coding: utf-8 -*-
"""
CasinoForge - Action Cog
Handles wallet, bank, work, give, and request commands
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('CasinoForge.Action')

class GiveConfirmView(discord.ui.View):
    def __init__(self, db_pool, sender, target, amount):
        super().__init__()
        self.db_pool = db_pool
        self.sender = sender
        self.target = target
        self.amount = amount

    @discord.ui.button(label="Confirm Transfer", style=discord.ButtonStyle.green, custom_id="give_confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                sender_bal = await conn.fetchval(
                    "SELECT wallet FROM users WHERE user_id = $1 AND is_frozen = FALSE AND is_blacklisted = FALSE",
                    str(self.sender.id)
                )
                
                if sender_bal is None or sender_bal < self.amount:
                    await interaction.followup.send(
                        f"❌ Transaction failed. {self.sender.mention}, you no longer have enough funds.",
                        ephemeral=True
                    )
                    self.stop()
                    return

                await conn.execute(
                    "UPDATE users SET wallet = wallet - $1 WHERE user_id = $2",
                    self.amount,
                    str(self.sender.id)
                )
                
                await conn.execute(
                    "INSERT INTO users (user_id, wallet) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET wallet = users.wallet + $2",
                    str(self.target.id),
                    self.amount
                )
        
        await interaction.followup.send(
            f"✅ {self.sender.mention} sent **{self.amount:,}** coins to {self.target.mention}!"
        )
        self.stop()

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.red, custom_id="give_cancel")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send("❌ Transfer cancelled.")
        self.stop()

class RequestConfirmView(discord.ui.View):
    def __init__(self, db_pool, requester, target_user, amount):
        super().__init__(timeout=60.0) 
        self.db_pool = db_pool
        self.requester = requester
        self.target_user = target_user
        self.amount = amount

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target_user.id:
            await interaction.response.send_message(
                f"❌ This request isn't for you! Only {self.target_user.mention} can respond.", 
                ephemeral=True
            )
            return False 
        return True 

    @discord.ui.button(label="Accept Request", style=discord.ButtonStyle.green, custom_id="req_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        async with self.db_pool.acquire() as conn:
            async with conn.transaction():
                target_bal = await conn.fetchval(
                    "SELECT wallet FROM users WHERE user_id = $1 AND is_frozen = FALSE AND is_blacklisted = FALSE",
                    str(self.target_user.id)
                )
                
                if target_bal is None or target_bal < self.amount:
                    await interaction.followup.send(
                        f"❌ You don't have enough coins to accept this request.",
                        ephemeral=True
                    )
                    return

                await conn.execute(
                    "UPDATE users SET wallet = wallet - $1 WHERE user_id = $2",
                    self.amount,
                    str(self.target_user.id)
                )
                
                await conn.execute(
                    "INSERT INTO users (user_id, wallet) VALUES ($1, $2) ON CONFLICT (user_id) DO UPDATE SET wallet = users.wallet + $2",
                    str(self.requester.id),
                    self.amount
                )
        
        await interaction.followup.send(
            f"✅ {self.target_user.mention} sent **{self.amount:,}** coins to {self.requester.mention}!"
        )
        self.stop()

    @discord.ui.button(label="Decline Request", style=discord.ButtonStyle.red, custom_id="req_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.followup.send(
            f"❌ {self.target_user.mention} declined your request."
            )
        self.stop()

class Action(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def ensure_user(self, user_id: int):
        """Ensure user exists in database."""
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING",
                str(user_id)
            )

    @app_commands.command(name="balance", description="Check your or another user's balance.")
    @app_commands.describe(user="User to check balance for (optional)")
    async def balance(self, interaction: discord.Interaction, user: discord.User = None):
        """Display wallet and bank balance."""
        target_user = user or interaction.user
        await self.ensure_user(target_user.id)
        
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT wallet, bank, bank_limit FROM users WHERE user_id = $1",
                str(target_user.id)
            )
        
        if row is None:
            await interaction.response.send_message("❌ User not found.", ephemeral=True)
            return
        
        embed = discord.Embed(
            title=f"💰 {target_user.display_name}'s Balance",
            color=discord.Color.gold()
        )
        embed.add_field(name="Wallet", value=f"**{row['wallet']:,}** coins", inline=False)
        embed.add_field(name="Bank", value=f"**{row['bank']:,}** / **{row['bank_limit']:,}** coins", inline=False)
        embed.add_field(name="Total", value=f"**{row['wallet'] + row['bank']:,}** coins", inline=False)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="deposit", description="Deposit coins into your bank.")
    @app_commands.describe(amount="Amount to deposit (0 for all)")
    async def deposit(self, interaction: discord.Interaction, amount: int):
        """Deposit coins from wallet to bank."""
        if amount < 0:
            await interaction.response.send_message("❌ Amount cannot be negative.", ephemeral=True)
            return
        
        await self.ensure_user(interaction.user.id)
        
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT wallet, bank, bank_limit, is_frozen, is_blacklisted FROM users WHERE user_id = $1",
                str(interaction.user.id)
            )
            
            if row['is_blacklisted'] or row['is_frozen']:
                await interaction.response.send_message("❌ Your account is restricted.", ephemeral=True)
                return

            deposit_amount = row['wallet'] if amount == 0 else amount
            
            if deposit_amount == 0:
                await interaction.response.send_message("❌ You have no coins to deposit.", ephemeral=True)
                return
            
            if row['wallet'] < deposit_amount:
                await interaction.response.send_message(f"❌ You only have **{row['wallet']:,}** coins.", ephemeral=True)
                return
            
            available_space = row['bank_limit'] - row['bank']
            if available_space <= 0:
                await interaction.response.send_message("❌ Your bank is full!", ephemeral=True)
                return
            
            if deposit_amount > available_space:
                deposit_amount = available_space

            await conn.execute(
                "UPDATE users SET wallet = wallet - $1, bank = bank + $1 WHERE user_id = $2",
                deposit_amount,
                str(interaction.user.id)
            )
        
        await interaction.response.send_message(
            f"✅ Successfully deposited **{deposit_amount:,}** coins into your bank."
        )

    @app_commands.command(name="withdraw", description="Withdraw coins from your bank.")
    @app_commands.describe(amount="Amount to withdraw (0 for all)")
    async def withdraw(self, interaction: discord.Interaction, amount: int):
        """Withdraw coins from bank to wallet."""
        if amount < 0:
            await interaction.response.send_message("❌ Amount cannot be negative.", ephemeral=True)
            return
        
        await self.ensure_user(interaction.user.id)
        
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT wallet, bank, is_frozen, is_blacklisted FROM users WHERE user_id = $1",
                str(interaction.user.id)
            )
            
            if row['is_blacklisted'] or row['is_frozen']:
                await interaction.response.send_message("❌ Your account is restricted.", ephemeral=True)
                return

            withdraw_amount = row['bank'] if amount == 0 else amount
            
            if withdraw_amount == 0:
                await interaction.response.send_message("❌ Your bank is empty.", ephemeral=True)
                return
            
            if row['bank'] < withdraw_amount:
                await interaction.response.send_message(f"❌ You only have **{row['bank']:,}** in your bank.", ephemeral=True)
                return

            await conn.execute(
                "UPDATE users SET wallet = wallet + $1, bank = bank - $1 WHERE user_id = $2",
                withdraw_amount,
                str(interaction.user.id)
            )
        
        await interaction.response.send_message(
            f"✅ Successfully withdrew **{withdraw_amount:,}** coins from your bank."
        )

    @app_commands.command(name="work", description="Work to earn coins.")
    @app_commands.checks.cooldown(1, 3600, key=lambda i: i.user.id)  # 1 hour cooldown
    async def work(self, interaction: discord.Interaction):
        """Perform work to earn coins."""
   
await interaction.response.defer()
        await self.ensure_user(interaction.user.id)
        
        earnings = random.randint(100, 500)
        
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET wallet = wallet + $1, last_work = $2 WHERE user_id = $3",
                earnings, datetime.utcnow(), str(interaction.user.id)
            )
        
        await interaction.followup.send(
            f"💼 You worked hard and earned **{earnings:,}** coins!"
        )

    @app_commands.command(name="daily", description="Claim your daily reward.")
    @app_commands.checks.cooldown(1, 86400, key=lambda i: i.user.id)
    async def daily(self, interaction: discord.Interaction):
        """Claim daily coins."""
        await self.ensure_user(interaction.user.id)
        reward = 1000
        
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET wallet = wallet + $1, last_daily = $2 WHERE user_id = $3",
                reward, datetime.utcnow(), str(interaction.user.id)
            )
        
        await interaction.response.send_message(f"🎁 You claimed your daily reward of **{reward:,}** coins!")

    @app_commands.command(name="payday", description="Get a small payday reward.")
    @app_commands.checks.cooldown(1, 600, key=lambda i: i.user.id)
    async def payday(self, interaction: discord.Interaction):
        """Small passive income."""
        await self.ensure_user(interaction.user.id)
        reward = random.randint(50, 150)
        
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET wallet = wallet + $1 WHERE user_id = $2",
                reward, str(interaction.user.id)
            )
        
        await interaction.response.send_message(f"💸 It's payday! You got **{reward:,}** coins.")

    @app_commands.command(name="leaderboard", description="Show the top richest users in this server.")
    async def leaderboard(self, interaction: discord.Interaction):
        """Server leaderboard."""
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, (wallet + bank) as total FROM users ORDER BY total DESC LIMIT 10"
            )
        
        embed = discord.Embed(title="🏆 Server Leaderboard", color=discord.Color.gold())
        
        description = ""
        for i, row in enumerate(rows, 1):
            user = self.bot.get_user(int(row['user_id']))
            name = user.display_name if user else f"User {row['user_id']}"
            description += f"**{i}.** {name} — **{row['total']:,}** coins\n"
        
        embed.description = description if description else "No data found."
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard-global", description="Show the top richest users globally.")
    async def leaderboard_global(self, interaction: discord.Interaction):
        """Global leaderboard."""
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, (wallet + bank) as total FROM users ORDER BY total DESC LIMIT 10"
            )
        
        embed = discord.Embed(title="🌍 Global Leaderboard", color=discord.Color.purple())
        
        description = ""
        for i, row in enumerate(rows, 1):
            try:
                user = await self.bot.fetch_user(int(row['user_id']))
                name = user.display_name
            except:
                name = f"User {row['user_id']}"
            description += f"**{i}.** {name} — **{row['total']:,}** coins\n"
        
        embed.description = description if description else "No data found."
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rob", description="Attempt to rob another user's wallet.")
    @app_commands.describe(user="User to rob")
    @app_commands.checks.cooldown(1, 7200, key=lambda i: i.user.id) # 2 hour cooldown
    async def rob(self, interaction: discord.Interaction, user: discord.User):
        """Robbery command."""
        if user == interaction.user:
            return await interaction.response.send_message("❌ You can't rob yourself.", ephemeral=True)
        if user.bot:
            return await interaction.response.send_message("❌ You can't rob a bot.", ephemeral=True)
            
        await self.ensure_user(interaction.user.id)
        await self.ensure_user(user.id)
        
        async with self.bot.db_pool.acquire() as conn:
            target_bal = await conn.fetchval("SELECT wallet FROM users WHERE user_id = $1", str(user.id))
            if target_bal < 500:
                return await interaction.response.send_message(f"❌ {user.mention} is too poor to rob! They need at least 500 coins.", ephemeral=True)
            
            # 35% success chance
            if random.random() < 0.35:
                amount = random.randint(100, int(target_bal * 0.4))
                async with conn.transaction():
                    await conn.execute("UPDATE users SET wallet = wallet - $1 WHERE user_id = $2", amount, str(user.id))
                    await conn.execute("UPDATE users SET wallet = wallet + $1 WHERE user_id = $2", amount, str(interaction.user.id))
                await interaction.response.send_message(f"🥷 **SUCCESS!** You robbed **{amount:,}** coins from {user.mention}!")
            else:
                fine = random.randint(200, 500)
                await conn.execute("UPDATE users SET wallet = GREATEST(0, wallet - $1) WHERE user_id = $2", fine, str(interaction.user.id))
                await interaction.response.send_message(f"👮 **CAUGHT!** You were caught trying to rob {user.mention} and fined **{fine:,}** coins.")

    @app_commands.command(name="shop", description="View items available for purchase.")
    async def shop(self, interaction: discord.Interaction):
        """View shop items."""
        async with self.bot.db_pool.acquire() as conn:
            rows = await conn.fetch("SELECT name, description, price FROM items ORDER BY price ASC")
            
        if not rows:
            # Seed default items if shop is empty
            async with self.bot.db_pool.acquire() as conn:
                await conn.execute("""
                    INSERT INTO items (name, description, price, type) VALUES
                    ('Lucky Charm', 'Increases gambling luck slightly (Collectable)', 5000, 'collectible'),
                    ('Bank Card', 'Increases bank limit by 10,000', 15000, 'boost'),
                    ('Shield', 'Protects you from one robbery attempt', 2500, 'usable')
                    ON CONFLICT DO NOTHING
                """)
                rows = await conn.fetch("SELECT name, description, price FROM items ORDER BY price ASC")

        embed = discord.Embed(title="🛒 CasinoForge Shop", color=discord.Color.green())
        for row in rows:
            embed.add_field(name=f"{row['name']} — {row['price']:,} coins", value=row['description'], inline=False)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="buy-item", description="Buy an item from the shop.")
    @app_commands.describe(item_name="Name of the item to buy")
    async def buy_item(self, interaction: discord.Interaction, item_name: str):
        """Buy item command."""
        await self.ensure_user(interaction.user.id)
        
        async with self.bot.db_pool.acquire() as conn:
            item = await conn.fetchrow("SELECT id, name, price, type FROM items WHERE LOWER(name) = $1", item_name.lower())
            if not item:
                return await interaction.response.send_message("❌ Item not found.", ephemeral=True)
            
            user_wallet = await conn.fetchval("SELECT wallet FROM users WHERE user_id = $1", str(interaction.user.id))
            if user_wallet < item['price']:
                return await interaction.response.send_message(f"❌ You don't have enough coins. Price: **{item['price']:,}**", ephemeral=True)
            
            async with conn.transaction():
                await conn.execute("UPDATE users SET wallet = wallet - $1 WHERE user_id = $2", item['price'], str(interaction.user.id))
                await conn.execute(
                    "INSERT INTO inventory (user_id, item_id, quantity) VALUES ($1, $2, 1) ON CONFLICT (user_id, item_id) DO UPDATE SET quantity = inventory.quantity + 1",
                    str(interaction.user.id), item['id']
                )
                
                # Apply instant boosts
                if item['name'] == 'Bank Card':
                    await conn.execute("UPDATE users SET bank_limit = bank_limit + 10000 WHERE user_id = $1", str(interaction.user.id))
            
            await interaction.response.send_message(f"🛍️ You bought a **{item['name']}** for **{item['price']:,}** coins!")

    @app_commands.command(name="give", description="Give coins to another user.")
    @app_commands.describe(user="User to give coins to", amount="Amount to give")
    async def give(self, interaction: discord.Interaction, user: discord.User, amount: int):
        """Transfer coins to another user."""
        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
            return
        
        if user == interaction.user:
            await interaction.response.send_message("❌ You can't give coins to yourself.", ephemeral=True)
            return
        
        if user.bot:
            await interaction.response.send_message("❌ You can't give coins to a bot.", ephemeral=True)
            return
        
        await self.ensure_user(interaction.user.id)
        await self.ensure_user(user.id)
        
        view = GiveConfirmView(self.bot.db_pool, interaction.user, user, amount)
        
        embed = discord.Embed(
            title="💸 Confirm Transfer",
            description=f"**{interaction.user.mention}** wants to send **{amount:,}** coins to **{user.mention}**",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed, view=view)

    @app_commands.command(name="request", description="Request coins from another user.")
    @app_commands.describe(user="User to request coins from", amount="Amount to request")
    async def request(self, interaction: discord.Interaction, user: discord.User, amount: int):
        """Request coins from another user."""
        if amount <= 0:
            await interaction.response.send_message("❌ Amount must be positive.", ephemeral=True)
            return
        
        if user == interaction.user:
            await interaction.response.send_message("❌ You can't request coins from yourself.", ephemeral=True)
            return
        
        if user.bot:
            await interaction.response.send_message("❌ You can't request coins from a bot.", ephemeral=True)
            return
        
        await self.ensure_user(interaction.user.id)
        await self.ensure_user(user.id)
        
        view = RequestConfirmView(self.bot.db_pool, interaction.user, user, amount)
        
        embed = discord.Embed(
            title="📬 Money Request",
            description=f"**{interaction.user.mention}** is requesting **{amount:,}** coins from you",
            color=discord.Color.orange()
        )
        
        await interaction.response.send_message(f"Hey {user.mention}!", embed=embed, view=view)

async def setup(bot: commands.Bot):
    await bot.add_cog(Action(bot))
    logger.info("Action cog loaded")
