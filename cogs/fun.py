# -*- coding: utf-8 -*-
"""
CasinoForge - Fun Cog
Non-economy entertainment and utility commands
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import logging

logger = logging.getLogger('CasinoForge.Fun')

class Fun(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    @app_commands.command(name="help", description="Get help with CasinoForge commands.")
    async def help(self, interaction: discord.Interaction):
        """Display help information."""
        embed = discord.Embed(
            title="🎰 CasinoForge - Command Help",
            description="A high-stakes Discord gambling economy bot",
            color=discord.Color.purple()
        )
        
        embed.add_field(
            name="🎲 **Gambling Games**",
            value="`/coinflip` `/slots` `/blackjack` `/roulette` `/crash` `/horserace` `/dice` `/lottery` `/gamble` `/scratchcard` `/highlow` `/mines` `/jackpot` `/plinko` `/tower` `/buy-jackpot`",
            inline=False
        )
        
        embed.add_field(
            name="💰 **Economy**",
            value="`/balance` `/deposit` `/withdraw` `/work` `/daily` `/payday` `/give` `/request` `/leaderboard` `/leaderboard-global` `/rob` `/shop` `/buy-item` `/beg` `/market` `/portfolio` `/invest` `/sell-stock`",
            inline=False
        )
        
        embed.add_field(
            name="🛡️ **Admin Commands**",
            value="`/eco-add` `/eco-remove` `/eco-set` `/eco-reset` `/eco-freeze` `/eco-unfreeze` `/eco-wipe` `/eco-search` `/bank-limit` `/blacklist` `/unblacklist` `/staff-stats` `/eco-audit` `/eco-top-spenders`",
            inline=False
        )
        
        embed.add_field(
            name="👨‍💻 **Developer Commands**",
            value="`/maintenance` `/dev-reload` `/dev-status` `/dev-eval` `/dev-sql` `/dev-guilds` `/dev-sync` `/global-say` `/dev-logs` `/dev-leave` `/dev-shutdown` `/dev-shell` `/dev-reboot` `/dev-inst-jp` `/dev-gift`",
            inline=False
        )
        
        embed.add_field(
            name="🎉 **Fun**",
            value="`/quote` `/roll` `/flip` `/8ball` `/choose` `/rps` `/slots-free` `/coinflip-free` `/meme` `/joke`",
            inline=False
        )
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="rps", description="Play Rock-Paper-Scissors.")
    @app_commands.describe(choice="Rock, Paper, or Scissors")
    @app_commands.choices(choice=[
        app_commands.Choice(name="Rock", value="rock"),
        app_commands.Choice(name="Paper", value="paper"),
        app_commands.Choice(name="Scissors", value="scissors")
    ])
    async def rps(self, interaction: discord.Interaction, choice: app_commands.Choice[str]):
        """Play RPS."""
        bot_choice = random.choice(["rock", "paper", "scissors"])
        
        if choice.value == bot_choice:
            res = "It's a tie!"
        elif (choice.value == "rock" and bot_choice == "scissors") or \
             (choice.value == "paper" and bot_choice == "rock") or \
             (choice.value == "scissors" and bot_choice == "paper"):
            res = "You win! 🎉"
        else:
            res = "You lose! ❌"
            
        await interaction.response.send_message(f"🤜 You chose **{choice.name}**, I chose **{bot_choice.capitalize()}**. {res}")

    @app_commands.command(name="slots-free", description="Play slots for free (no stakes).")
    async def slots_free(self, interaction: discord.Interaction):
        """Free slots."""
        symbols = ["🍎", "🍊", "🍋", "🍌", "🍇", "⭐"]
        s1, s2, s3 = random.choices(symbols, k=3)
        await interaction.response.send_message(f"🎰 **{s1} | {s2} | {s3}**\n(Free play - no coins awarded)")

    @app_commands.command(name="coinflip-free", description="Flip a coin for free.")
    async def coinflip_free(self, interaction: discord.Interaction):
        """Free coinflip."""
        res = random.choice(["Heads", "Tails"])
        await interaction.response.send_message(f"🪙 The coin landed on **{res}**!")

    @app_commands.command(name="quote", description="Get an inspiring quote.")
    async def quote(self, interaction: discord.Interaction):
        """Display a random quote."""
        quotes = [
            "\"I have come here to chew bubblegum and write code... and I'm all out of bubblegum.\" - Unknown Developer",
            "\"It's not a bug, it's an undocumented feature.\" - Anonymous",
            "\"Talk is cheap. Show me the code.\" - Linus Torvalds",
            "\"You miss 100% of the shots you don't take.\" - Wayne Gretzky - Michael Scott",
            "\"99% of gamblers quit right before they hit the jackpot.\" - CasinoForge",
            "\"The house always wins.\" - Every Casino",
            "\"I'm not superstitious, but I'm a little stitious.\" - Michael Scott",
            "\"May the odds be ever in your favor.\" - Hunger Games"
        ]
        await interaction.response.send_message(f"📜 {random.choice(quotes)}")

    @app_commands.command(name="roll", description="Roll a dice.")
    @app_commands.describe(sides="Number of sides (default: 6)")
    async def roll(self, interaction: discord.Interaction, sides: int = 6):
        """Roll a dice."""
        if sides < 2:
            await interaction.response.send_message("❌ Dice must have at least 2 sides.", ephemeral=True)
            return
        
        result = random.randint(1, sides)
        await interaction.response.send_message(
            f"🎲 You rolled a **{result}** out of **{sides}**!"
        )

    @app_commands.command(name="flip", description="Flip a coin.")
    async def flip(self, interaction: discord.Interaction):
        """Flip a coin."""
        result = random.choice(["Heads", "Tails"])
        await interaction.response.send_message(
            f"🪙 The coin landed on **{result}**!"
        )

    @app_commands.command(name="8ball", description="Ask the magic 8-ball a yes/no question.")
    @app_commands.describe(question="Your question")
    async def eightball(self, interaction: discord.Interaction, question: str):
        """Magic 8-ball response."""
        responses = [
            "Yes, definitely.", "No way.", "Maybe...", "Ask again later.", "It is certain.",
            "Don't count on it.", "Very doubtful.", "Outlook good.", "Signs point to yes.", "Without a doubt."
        ]
        
        response = random.choice(responses)
        embed = discord.Embed(
            title="🎱 Magic 8-Ball",
            description=f"**Q:** {question}\n\n**A:** {response}",
            color=discord.Color.random()
        )
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="choose", description="Let the bot choose for you.")
    @app_commands.describe(options="Options separated by commas")
    async def choose(self, interaction: discord.Interaction, options: str):
        """Choose randomly from options."""
        choices = [opt.strip() for opt in options.split(",")]
        
        if len(choices) < 2:
            await interaction.response.send_message(
                "❌ Please provide at least 2 options separated by commas.",
                ephemeral=True
            )
            return
        
        choice = random.choice(choices)
        await interaction.response.send_message(
            f"🤔 I choose: **{choice}**"
        )

    @app_commands.command(name="meme", description="Get a random gambling meme.")
    async def meme(self, interaction: discord.Interaction):
        """Gambling memes."""
        memes = [
            "https://i.imgflip.com/4/30y1.jpg",
            "https://i.redd.it/9n5q1q4q4q4q.jpg", # Placeholder URLs
            "99% of gamblers quit right before they hit the jackpot!",
            "Me after losing my entire wallet in /blackjack: 🤡"
        ]
        await interaction.response.send_message(random.choice(memes))

    @app_commands.command(name="joke", description="Get a random joke.")
    async def joke(self, interaction: discord.Interaction):
        """Random jokes."""
        jokes = [
            "Why did the gambler bring a ladder to the casino? Because they heard the stakes were high!",
            "What's a gambler's favorite type of music? Rock and 'Roll'!",
            "I used to be a professional gambler, but I lost interest... and my house."
        ]
        await interaction.response.send_message(f"😂 {random.choice(jokes)}")

async def setup(bot: commands.Bot):
    await bot.add_cog(Fun(bot))
    logger.info("Fun cog loaded")
