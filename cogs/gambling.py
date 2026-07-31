# -*- coding: utf-8 -*-
"""
CasinoForge - Gambling Cog
Contains all casino game commands
"""

import discord
from discord import app_commands
from discord.ext import commands
import random
import asyncio
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('CasinoForge.Gambling')

class BlackjackView(discord.ui.View):
    def __init__(self, cog, interaction, bet):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.interaction = interaction
        self.bet = bet
        self.deck = [2, 3, 4, 5, 6, 7, 8, 9, 10, 10, 10, 10, 11] * 4
        random.shuffle(self.deck)
        self.player_hand = [self.draw_card(), self.draw_card()]
        self.dealer_hand = [self.draw_card(), self.draw_card()]
        self.game_over = False

    def draw_card(self):
        return self.deck.pop()

    def get_score(self, hand):
        score = sum(hand)
        aces = hand.count(11)
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    def create_embed(self, finished=False):
        player_score = self.get_score(self.player_hand)
        dealer_score = self.get_score(self.dealer_hand)
        
        embed = discord.Embed(
            title="🃏 Blackjack",
            color=discord.Color.blue() if not finished else (discord.Color.green() if player_score <= 21 and (player_score > dealer_score or dealer_score > 21) else discord.Color.red())
        )
        
        dealer_display = f"{self.dealer_hand[0]} + ?" if not finished else f"{', '.join(map(str, self.dealer_hand))} ({dealer_score})"
        embed.add_field(name="Dealer's Hand", value=dealer_display, inline=False)
        embed.add_field(name="Your Hand", value=f"{', '.join(map(str, self.player_hand))} ({player_score})", inline=False)
        embed.set_footer(text=f"Bet: {self.bet:,} coins")
        
        return embed

    @discord.ui.button(label="Hit", style=discord.ButtonStyle.grey)
    async def hit(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message("This is not your game!", ephemeral=True)
        
        self.player_hand.append(self.draw_card())
        if self.get_score(self.player_hand) > 21:
            await self.end_game(interaction, "bust")
        else:
            await interaction.response.edit_message(embed=self.create_embed(), view=self)

    @discord.ui.button(label="Stand", style=discord.ButtonStyle.grey)
    async def stand(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.interaction.user.id:
            return await interaction.response.send_message("This is not your game!", ephemeral=True)
        
        while self.get_score(self.dealer_hand) < 17:
            self.dealer_hand.append(self.draw_card())
        
        player_score = self.get_score(self.player_hand)
        dealer_score = self.get_score(self.dealer_hand)
        
        if dealer_score > 21:
            await self.end_game(interaction, "dealer_bust")
        elif player_score > dealer_score:
            await self.end_game(interaction, "win")
        elif player_score < dealer_score:
            await self.end_game(interaction, "loss")
        else:
            await self.end_game(interaction, "push")

    async def end_game(self, interaction, result):
        self.game_over = True
        self.clear_items()
        
        player_score = self.get_score(self.player_hand)
        dealer_score = self.get_score(self.dealer_hand)
        
        if result == "bust":
            msg = f"💥 **BUST!** You went over 21. Lost **{self.bet:,}** coins."
        elif result == "dealer_bust":
            winnings = self.bet * 2
            await self.cog.payout(self.interaction.user.id, winnings)
            msg = f"🃏 Dealer busted at {dealer_score}! You win **{winnings:,}** coins!"
        elif result == "win":
            winnings = self.bet * 2
            await self.cog.payout(self.interaction.user.id, winnings)
            msg = f"🎉 You win! **{winnings:,}** coins!"
        elif result == "loss":
            msg = f"❌ Dealer wins. Lost **{self.bet:,}** coins."
        else:
            await self.cog.payout(self.interaction.user.id, self.bet)
            msg = f"🤝 Push! Your bet of **{self.bet:,}** was returned."

        await interaction.response.edit_message(content=msg, embed=self.create_embed(finished=True), view=None)
        self.stop()

class Gambling(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def ensure_user(self, user_id: int):
        """Ensure user exists in database with default values."""
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "INSERT INTO users (user_id) VALUES ($1) ON CONFLICT DO NOTHING;",
                str(user_id)
            )

    async def process_bet(self, interaction: discord.Interaction, bet: int) -> bool:
        """Deducts the bet and checks for restrictions. Returns True if successful."""
        # Maintenance Check
        if self.bot.maintenance_mode and interaction.user.id not in self.bot.creator_ids:
            await interaction.response.send_message(
                "🛠️ **Bot is under maintenance.**\nRegular users cannot play casino games at this time. Please try again later!",
                ephemeral=True
            )
            return False

        if bet <= 0:
            await interaction.response.send_message("❌ Bet amount must be positive.", ephemeral=True)
            return False

        await self.ensure_user(interaction.user.id)
        
        async with self.bot.db_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT wallet, is_frozen, is_blacklisted FROM users WHERE user_id = $1",
                str(interaction.user.id)
            )
            
            if row is None:
                await interaction.response.send_message("❌ Account not found.", ephemeral=True)
                return False
            
            if row['is_frozen'] or row['is_blacklisted']:
                await interaction.response.send_message("❌ Your account is restricted.", ephemeral=True)
                return False
            
            if row['wallet'] < bet:
                await interaction.response.send_message(f"❌ You don't have enough coins. Your wallet: **{row['wallet']:,}**", ephemeral=True)
                return False
            
            # Deduct the bet
            await conn.execute(
                "UPDATE users SET wallet = wallet - $1 WHERE user_id = $2",
                bet,
                str(interaction.user.id)
            )
        
        return True

    async def payout(self, user_id: int, amount: int):
        """Adds winnings to the user's wallet (with global multiplier)."""
        multiplied = int(amount * self.bot.global_multiplier)
        async with self.bot.db_pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET wallet = wallet + $1 WHERE user_id = $2",
                multiplied,
                str(user_id)
            )

    @app_commands.command(name="coinflip", description="Flip a coin for a 2x payout.")
    @app_commands.describe(bet="Amount to bet", side="Heads or Tails")
    @app_commands.choices(side=[
        app_commands.Choice(name="Heads", value="heads"),
        app_commands.Choice(name="Tails", value="tails")
    ])
    async def coinflip(self, interaction: discord.Interaction, bet: int, side: app_commands.Choice[str]):
        """Classic coin flip game."""
        if not await self.process_bet(interaction, bet):
            return
        
        result = random.choice(["heads", "tails"])
        
        await interaction.response.defer()
        await asyncio.sleep(1)
        
        if side.value == result:
            winnings = bet * 2
            await self.payout(interaction.user.id, winnings)
            await interaction.followup.send(
                f"🪙 **Coin landed on {result.upper()}!** Payout: **{winnings:,}** coins (2x your bet). 🎉"
            )
        else:
            await interaction.followup.send(
                f"🪙 **Coin landed on {result.upper()}!** You picked {side.value.upper()}. You lost **{bet:,}** coins. ❌"
            )

    @app_commands.command(name="slots", description="Spin the slots for a chance to win big.")
    @app_commands.describe(bet="Amount to bet")
    async def slots(self, interaction: discord.Interaction, bet: int):
        """Slots machine game."""
        if not await self.process_bet(interaction, bet):
            return
        
        symbols = ["🍎", "🍊", "🍋", "🍌", "🍇", "⭐"]
        
        await interaction.response.defer()
        await asyncio.sleep(1)
        
        spin1 = random.choice(symbols)
        spin2 = random.choice(symbols)
        spin3 = random.choice(symbols)
        
        result = f"🎰 **{spin1} | {spin2} | {spin3}**"
        
        if spin1 == spin2 == spin3:
            if spin1 == "⭐":
                winnings = bet * 10
                msg = f"{result}\n🎊 **JACKPOT!!!** Three stars! You win **{winnings:,}** coins!"
            else:
                winnings = bet * 5
                msg = f"{result}\n🎉 **WIN!** Three matches! You win **{winnings:,}** coins!"
            await self.payout(interaction.user.id, winnings)
        elif spin1 == spin2 or spin2 == spin3:
            winnings = int(bet * 1.5)
            msg = f"{result}\n✨ **Two matches!** You win **{winnings:,}** coins! (1.5x payout)"
            await self.payout(interaction.user.id, winnings)
        else:
            msg = f"{result}\n❌ No matches. You lost **{bet:,}** coins."
        
        await interaction.followup.send(msg)

    @app_commands.command(name="blackjack", description="Play blackjack against the dealer (OwO style).")
    @app_commands.describe(bet="Amount to bet")
    async def blackjack(self, interaction: discord.Interaction, bet: int):
        """Interactive blackjack game."""
        if not await self.process_bet(interaction, bet):
            return
        
        view = BlackjackView(self, interaction, bet)
        await interaction.response.send_message(embed=view.create_embed(), view=view)

    @app_commands.command(name="roulette", description="Spin the roulette wheel.")
    @app_commands.describe(bet="Amount to bet", color="Red or Black")
    @app_commands.choices(color=[
        app_commands.Choice(name="Red", value="red"),
        app_commands.Choice(name="Black", value="black")
    ])
    async def roulette(self, interaction: discord.Interaction, bet: int, color: app_commands.Choice[str]):
        """Roulette wheel game."""
        if not await self.process_bet(interaction, bet):
            return
        
        result = random.choice(["red"] * 18 + ["black"] * 18 + ["green"])  # 37 slots
        
        await interaction.response.defer()
        await asyncio.sleep(1)
        
        if result == "green":
            msg = f"🎡 **Landed on GREEN (0)!** House always wins. Lost **{bet:,}** coins. 😱"
        elif color.value == result:
            winnings = bet * 2
            msg = f"🎡 **Landed on {result.upper()}!** You win **{winnings:,}** coins! 🎉"
            await self.payout(interaction.user.id, winnings)
        else:
            msg = f"🎡 **Landed on {result.upper()}!** You picked {color.value.upper()}. Lost **{bet:,}** coins. ❌"
        
        await interaction.followup.send(msg)

    @app_commands.command(name="crash", description="Multiplier rises dynamically. Cash out before it crashes!")
    @app_commands.describe(bet="Amount to wager", target="Target multiplier (e.g., 2.5 for 2.5x)")
    async def crash(self, interaction: discord.Interaction, bet: int, target: float):
        """Crash game with dynamic multiplier."""
        if target <= 1.0:
            await interaction.response.send_message("❌ Target multiplier must be higher than 1.0x.", ephemeral=True)
            return
        
        if not await self.process_bet(interaction, bet):
            return
        
        await interaction.response.defer()
        
        # Calculate when it crashes (weighted random)
        crash_point = round(random.choices(
            [random.uniform(1.0, 1.5), random.uniform(1.5, 5.0), random.uniform(5.0, 20.0)],
            weights=[60, 35, 5], k=1
        )[0], 2)
        
        if target <= crash_point:
            winnings = int(bet * target)
            msg = f"📈 **Cashout Successful!** Chart rose to **{crash_point:.2f}x**. You cashed out at **{target:.2f}x**, winning **{winnings:,}** coins! 🎉"
            await self.payout(interaction.user.id, winnings)
        else:
            msg = f"💥 **CRASHED!** Chart crashed at **{crash_point:.2f}x** before your target of **{target:.2f}x**. You lost **{bet:,}** coins. 😭"
        
        await interaction.followup.send(msg)

    @app_commands.command(name="horserace", description="Bet on horses in an epic race.")
    @app_commands.describe(bet="Amount to bet", horse="Which horse to bet on")
    @app_commands.choices(horse=[
        app_commands.Choice(name="Thunderbolt", value="Thunderbolt"),
        app_commands.Choice(name="Star Blazer", value="Star Blazer"),
        app_commands.Choice(name="Midnight Rush", value="Midnight Rush"),
        app_commands.Choice(name="Platinum Hoof", value="Platinum Hoof")
    ])
    async def horserace(self, interaction: discord.Interaction, bet: int, horse: app_commands.Choice[str]):
        """Horse racing game."""
        if not await self.process_bet(interaction, bet):
            return
        
        await interaction.response.defer()
        
        msg_obj = await interaction.followup.send("🏁 **THE RACE BEGINS!**")
        
        updates = [
            "🏇 *Thunderbolt takes the early lead! Star Blazer is close behind!*",
            "🏇 *Midnight Rush makes a fast move on the final stretch!*",
            "🏇 *Platinum Hoof is charging hard!*",
        ]
        
        for update in updates:
            await asyncio.sleep(1.5)
            await msg_obj.edit(content=update)
        
        winners = ["Thunderbolt", "Star Blazer", "Midnight Rush", "Platinum Hoof"]
        winning_horse = random.choice(winners)
        
        if horse.value == winning_horse:
            winnings = bet * 4
            await self.payout(interaction.user.id, winnings)
            res = f"🏆 **{winning_horse} Won the Race!** Your champion took first place! You won **{winnings:,}** coins! 🎉"
        else:
            res = f"❌ **{winning_horse} Won the Race!** Your horse, {horse.value}, fell behind. You lost **{bet:,}** coins."
        
        await msg_obj.edit(content=res)

    @app_commands.command(name="dice", description="Roll the dice (1-6 or 1-100).")
    @app_commands.describe(bet="Amount to bet", sides="How many sides (6 or 100)")
    async def dice(self, interaction: discord.Interaction, bet: int, sides: int):
        """Dice rolling game."""
        if sides not in [6, 100]:
            await interaction.response.send_message("❌ Sides must be 6 or 100.", ephemeral=True)
            return
        
        if not await self.process_bet(interaction, bet):
            return
        
        await interaction.response.defer()
        await asyncio.sleep(1)
        
        roll = random.randint(1, sides)
        threshold = sides // 2
        
        if roll > threshold:
            winnings = bet * 2
            msg = f"🎲 **You rolled {roll}!** Over {threshold}. You win **{winnings:,}** coins! 🎉"
            await self.payout(interaction.user.id, winnings)
        else:
            msg = f"🎲 **You rolled {roll}!** {threshold} or under. You lost **{bet:,}** coins. ❌"
        
        await interaction.followup.send(msg)

    @app_commands.command(name="lottery", description="Buy a lottery ticket for a massive jackpot.")
    @app_commands.describe(ticket_cost="Cost per ticket")
    async def lottery(self, interaction: discord.Interaction, ticket_cost: int):
        """Lottery game with minimal odds but huge payout."""
        if not await self.process_bet(interaction, ticket_cost):
            return
        
        await interaction.response.defer()
        await asyncio.sleep(1)
        
        # 0.1% chance to win (1 in 1000)
        if random.random() < 0.001:
            jackpot = ticket_cost * 10000
            msg = f"🎰 **LOTTERY WINNER!!!** 🎉\nYou won the jackpot: **{jackpot:,}** coins! 🤑"
            await self.payout(interaction.user.id, jackpot)
        else:
            msg = f"❌ Better luck next time! Your ticket didn't win. Lost **{ticket_cost:,}** coins."
        
        await interaction.followup.send(msg)

    @app_commands.command(name="gamble", description="All-in high-stakes gamble.")
    @app_commands.describe(bet="Amount to go all-in with")
    async def gamble(self, interaction: discord.Interaction, bet: int):
        """50/50 all-in gamble."""
        if not await self.process_bet(interaction, bet):
            return
        
        await interaction.response.defer()
        await asyncio.sleep(1)
        
        if random.random() < 0.5:
            winnings = bet * 2
            msg = f"💰 **ALL-IN GAMBLE WIN!** You doubled your bet! **+{winnings:,}** coins! 🎉"
            await self.payout(interaction.user.id, winnings)
        else:
            msg = f"💀 **ALL-IN GAMBLE LOSS!** You lost your **{bet:,}** coins betting it all! 😭"
        
        await interaction.followup.send(msg)

    
    @app_commands.command(name="jackpot", description="Buy jackpot tickets (500 coins each).")
    @app_commands.describe(amount="Number of tickets to buy")
    async def jackpot(self, interaction: discord.Interaction, amount: int):
        """Buy jackpot tickets."""
        ticket_cost = 500
        total_cost = amount * ticket_cost
        
        if amount <= 0:
            return await interaction.response.send_message("❌ You must buy at least 1 ticket.", ephemeral=True)
            
        if not await self.process_bet(interaction, total_cost):
            return
        
        # Defer immediately to stop the 3-second timeout
        await interaction.response.defer()
        
        try:
            async with self.bot.db_pool.acquire() as conn:
                # Get or create active jackpot
                jackpot = await conn.fetchrow("SELECT id, end_time FROM jackpot WHERE is_active = TRUE")
                if not jackpot:
                    from datetime import timezone, timedelta
                    end_time = datetime.now(timezone(timedelta(hours=8))) + timedelta(days=3)
                    jackpot_id = await conn.fetchval(
                        "INSERT INTO jackpot (end_time, total_prize) VALUES ($1, $2) RETURNING id",
                        end_time, total_cost
                    )
                    end_time_str = end_time.strftime("%Y-%m-%d %H:%M:%S UTC")
                else:
                    jackpot_id = jackpot['id']
                    await conn.execute("UPDATE jackpot SET total_prize = total_prize + $1 WHERE id = $2", total_cost, jackpot_id)
                    end_time_str = jackpot['end_time'].strftime("%Y-%m-%d %H:%M:%S UTC")
                
                # Add tickets
                await conn.execute(
                    """
                    INSERT INTO jackpot_tickets (jackpot_id, user_id, ticket_count)
                    VALUES ($1, $2, $3)
                    ON CONFLICT (jackpot_id, user_id) 
                    DO UPDATE SET ticket_count = jackpot_tickets.ticket_count + $3
                    """,
                    jackpot_id, str(interaction.user.id), amount
                )
                
            # If we made it here, the DB stuff worked!
            await interaction.followup.send(
                f"🎰 **Jackpot Tickets Purchased!**\n"
                f"You bought **{amount}** tickets for **{total_cost:,}** coins.\n"
                f"The jackpot ends on: **{end_time_str}**.\n"
                f"Good luck! You'll be notified via DM when the winner is picked."
            )

        except Exception as e:
            # Print the exact error to your console so you can see why it froze
            print(f"[JACKPOT ERROR]: {e}")
            # Tell the user something went wrong instead of leaving them hanging
            await interaction.followup.send("❌ An error occurred while processing your database request. Please try again.")


    @app_commands.command(name="scratchcard", description="Buy a virtual scratchcard.")
    @app_commands.describe(bet="Cost of scratchcard (100, 500, 1000)")
    @app_commands.choices(bet=[
        app_commands.Choice(name="100", value=100),
        app_commands.Choice(name="500", value=500),
        app_commands.Choice(name="1000", value=1000)
    ])
    async def scratchcard(self, interaction: discord.Interaction, bet: app_commands.Choice[int]):
        """Scratchcard game."""
        if not await self.process_bet(interaction, bet.value):
            return
        
        await interaction.response.defer()
        await asyncio.sleep(1)
        
        res = random.random()
        if res < 0.05: # 5% chance for 10x
            winnings = bet.value * 10
            msg = f"🎫 **SCRATCH!** You found a **MEGA WIN!** You won **{winnings:,}** coins! 🤑"
            await self.payout(interaction.user.id, winnings)
        elif res < 0.15: # 10% chance for 3x
            winnings = bet.value * 3
            msg = f"🎫 **SCRATCH!** You found a **WIN!** You won **{winnings:,}** coins! 🎉"
            await self.payout(interaction.user.id, winnings)
        elif res < 0.40: # 25% chance for 1.5x
            winnings = int(bet.value * 1.5)
            msg = f"🎫 **SCRATCH!** Small win! You won **{winnings:,}** coins! ✨"
            await self.payout(interaction.user.id, winnings)
        else:
            msg = "🎫 **SCRATCH!** Nothing found. Better luck next time! ❌"
        
        await interaction.followup.send(msg)

    @app_commands.command(name="highlow", description="Guess if the next card is higher or lower.")
    @app_commands.describe(bet="Amount to bet")
    async def highlow(self, interaction: discord.Interaction, bet: int):
        """High-Low card game."""
        if not await self.process_bet(interaction, bet):
            return
        
        card1 = random.randint(1, 13)
        
        class HighLowView(discord.ui.View):
            def __init__(self, cog, interaction, bet, card1):
                super().__init__(timeout=30.0)
                self.cog = cog
                self.interaction = interaction
                self.bet = bet
                self.card1 = card1

            @discord.ui.button(label="Higher", style=discord.ButtonStyle.green)
            async def higher(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self.process_choice(interaction, "higher")

            @discord.ui.button(label="Lower", style=discord.ButtonStyle.red)
            async def lower(self, interaction: discord.Interaction, button: discord.ui.Button):
                await self.process_choice(interaction, "lower")

            async def process_choice(self, interaction, choice):
                if interaction.user.id != self.interaction.user.id:
                    return await interaction.response.send_message("Not your game!", ephemeral=True)
                
                card2 = random.randint(1, 13)
                win = False
                if choice == "higher" and card2 > self.card1: win = True
                elif choice == "lower" and card2 < self.card1: win = True
                
                if win:
                    winnings = int(self.bet * 1.8)
                    await self.cog.payout(self.interaction.user.id, winnings)
                    msg = f"🃏 Card was **{card2}**. You were right! Won **{winnings:,}** coins! 🎉"
                else:
                    msg = f"🃏 Card was **{card2}**. You were wrong. Lost **{self.bet:,}** coins. ❌"
                
                await interaction.response.edit_message(content=msg, view=None)
                self.stop()

        await interaction.response.send_message(f"🃏 Current card is **{card1}**. Will the next card be higher or lower?", view=HighLowView(self, interaction, bet, card1))

    @app_commands.command(name="mines", description="Gambling Minesweeper.")
    @app_commands.describe(bet="Amount to bet", mines="Number of mines (1-20)")
    async def mines(self, interaction: discord.Interaction, bet: int, mines: int):
        """Mines gambling game."""
        if mines < 1 or mines > 20:
            return await interaction.response.send_message("Mines must be between 1 and 20.", ephemeral=True)
        
        if not await self.process_bet(interaction, bet):
            return

        class MinesView(discord.ui.View):
            def __init__(self, cog, interaction, bet, mine_count):
                super().__init__(timeout=60.0)
                self.cog = cog
                self.interaction = interaction
                self.bet = bet
                self.mine_count = mine_count
                self.grid = ["💎"] * 25
                mine_indices = random.sample(range(25), mine_count)
                for idx in mine_indices: self.grid[idx] = "💣"
                self.revealed = [False] * 25
                self.current_winnings = bet
                self.safe_picks = 0
                
                for i in range(25):
                    self.add_item(MinesButton(i))

            async def pick(self, interaction, index):
                if interaction.user.id != self.interaction.user.id:
                    return await interaction.response.send_message("Not your game!", ephemeral=True)
                
                if self.grid[index] == "💣":
                    self.clear_items()
                    await interaction.response.edit_message(content=f"💥 **BOOM!** You hit a mine. Lost **{self.bet:,}** coins.", view=self)
                    self.stop()
                else:
                    self.revealed[index] = True
                    self.safe_picks += 1
                    multiplier = 1 + (self.mine_count / (25 - self.safe_picks))
                    self.current_winnings = int(self.current_winnings * multiplier)
                    
                    # Update buttons
                    for item in self.children:
                        if isinstance(item, MinesButton) and item.index == index:
                            item.label = "💎"
                            item.style = discord.ButtonStyle.green
                            item.disabled = True
                    
                    if not any(isinstance(i, CashoutButton) for i in self.children):
                        self.add_item(CashoutButton())
                    
                    await interaction.response.edit_message(content=f"💎 Safe! Current payout: **{self.current_winnings:,}**", view=self)

            async def cashout(self, interaction):
                await self.cog.payout(self.interaction.user.id, self.current_winnings)
                self.clear_items()
                await interaction.response.edit_message(content=f"💰 Cashed out! You won **{self.current_winnings:,}** coins!", view=self)
                self.stop()

        class MinesButton(discord.ui.Button):
            def __init__(self, index):
                super().__init__(label="?", style=discord.ButtonStyle.grey, row=index // 5)
                self.index = index
            async def callback(self, interaction):
                await self.view.pick(interaction, self.index)

        class CashoutButton(discord.ui.Button):
            def __init__(self):
                super().__init__(label="Cashout", style=discord.ButtonStyle.blurple, row=4)
            async def callback(self, interaction):
                await self.view.cashout(interaction)

        await interaction.response.send_message(f"💣 **Mines Game Started!** Pick a tile. Mines: {mines}", view=MinesView(self, interaction, bet, mines))

    @app_commands.command(name="plinko", description="Drop a ball and hope for a high multiplier.")
    @app_commands.describe(bet="Amount to bet")
    async def plinko(self, interaction: discord.Interaction, bet: int):
        """Plinko game."""
        if not await self.process_bet(interaction, bet):
            return
        
        # Simple plinko logic: 9 slots with different multipliers
        multipliers = [0.2, 0.5, 1.2, 2.0, 5.0, 2.0, 1.2, 0.5, 0.2]
        result_idx = random.randint(0, len(multipliers) - 1)
        mult = multipliers[result_idx]
        winnings = int(bet * mult)
        
        path = ""
        curr = 4
        for _ in range(4):
            move = random.choice([-0.5, 0.5])
            curr += move
            path += "↙️" if move < 0 else "↘️"
            
        await interaction.response.defer()
        await asyncio.sleep(1.5)
        
        if mult > 1:
            await self.payout(interaction.user.id, winnings)
            msg = f"🔵 **PLINKO!** Ball path: {path}\nLanded on **{mult}x**! You won **{winnings:,}** coins! 🎉"
        else:
            msg = f"🔵 **PLINKO!** Ball path: {path}\nLanded on **{mult}x**. You lost **{bet - winnings:,}** coins. 📉"
            
        await interaction.followup.send(msg)

    @app_commands.command(name="tower", description="Climb the tower for massive multipliers.")
    @app_commands.describe(bet="Amount to bet")
    async def tower(self, interaction: discord.Interaction, bet: int):
        """Tower climbing game."""
        if not await self.process_bet(interaction, bet):
            return

        class TowerView(discord.ui.View):
            def __init__(self, cog, interaction, bet):
                super().__init__(timeout=60.0)
                self.cog = cog
                self.interaction = interaction
                self.bet = bet
                self.level = 0
                self.multipliers = [1.2, 1.5, 2.0, 3.0, 5.0, 10.0, 25.0, 100.0]
                self.game_over = False

            def get_embed(self):
                embed = discord.Embed(title="🏰 The Tower", color=discord.Color.gold())
                embed.add_field(name="Current Level", value=f"Level {self.level}", inline=True)
                embed.add_field(name="Next Multiplier", value=f"{self.multipliers[self.level]}x" if self.level < len(self.multipliers) else "MAX", inline=True)
                embed.add_field(name="Potential Win", value=f"{int(self.bet * self.multipliers[self.level]):,}" if self.level < len(self.multipliers) else "N/A", inline=True)
                return embed

            @discord.ui.button(label="Climb (1/2 chance)", style=discord.ButtonStyle.green)
            async def climb(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.interaction.user.id: return
                
                if random.random() < 0.5: # 50% chance to fail
                    self.game_over = True
                    self.clear_items()
                    await interaction.response.edit_message(content=f"💀 **FALLEN!** You fell from level {self.level}. Lost **{self.bet:,}** coins.", embed=self.get_embed(), view=None)
                    self.stop()
                else:
                    self.level += 1
                    if self.level == len(self.multipliers):
                        winnings = int(self.bet * self.multipliers[-1])
                        await self.cog.payout(self.interaction.user.id, winnings)
                        self.clear_items()
                        await interaction.response.edit_message(content=f"🏆 **MAX LEVEL!** You reached the top! Won **{winnings:,}** coins!", embed=self.get_embed(), view=None)
                        self.stop()
                    else:
                        await interaction.response.edit_message(embed=self.get_embed(), view=self)

            @discord.ui.button(label="Cashout", style=discord.ButtonStyle.blurple)
            async def cashout(self, interaction: discord.Interaction, button: discord.ui.Button):
                if interaction.user.id != self.interaction.user.id: return
                if self.level == 0: return await interaction.response.send_message("Climb at least one level first!", ephemeral=True)
                
                winnings = int(self.bet * self.multipliers[self.level-1])
                await self.cog.payout(self.interaction.user.id, winnings)
                self.clear_items()
                await interaction.response.edit_message(content=f"💰 **CASHOUT!** You left at level {self.level}. Won **{winnings:,}** coins!", embed=self.get_embed(), view=None)
                self.stop()

        await interaction.response.send_message("🏰 **Tower Game Started!** How high can you go?", embed=discord.Embed(title="🏰 The Tower", description="Climb for higher multipliers, but one fall and you lose it all!"), view=TowerView(self, interaction, bet))

    @app_commands.command(name="lucky-wheel", description="Spin the lucky wheel for a chance at massive prizes.")
    @app_commands.describe(bet="Amount to bet")
    async def lucky_wheel(self, interaction: discord.Interaction, bet: int):
        """Lucky wheel spinning game with tiered prizes."""
        if not await self.process_bet(interaction, bet):
            return
        
        await interaction.response.defer()
        
        # Wheel segments: [label, multiplier, weight]
        wheel_segments = [
            ("JACKPOT", 10, 3),
            ("MEGA WIN", 5, 8),
            ("BIG WIN", 3, 15),
            ("NICE!", 2, 20),
            ("SMALL WIN", 1.5, 25),
            ("BANKRUPT", 0, 19),
            ("HALF BACK", 0.5, 10),
        ]
        
        # Weighted random selection
        total_weight = sum(w for _, _, w in wheel_segments)
        roll = random.random() * total_weight
        cumulative = 0
        selected_label, selected_mult, _ = wheel_segments[0]
        
        for label, mult, weight in wheel_segments:
            cumulative += weight
            if roll <= cumulative:
                selected_label, selected_mult, _ = label, mult, weight
                break
        
        # Build the wheel display
        wheel_lines = []
        for label, mult, _ in wheel_segments:
            if label == selected_label:
                wheel_lines.append(f"➤ **{label}** ({mult}x)")
            else:
                wheel_lines.append(f"  {label} ({mult}x)")
        
        wheel_text = "\n".join(wheel_lines)
        
        await asyncio.sleep(1.5)
        
        if selected_mult == 0:
            # Bankrupt
            msg = f"🎡 **Lucky Wheel Result:**\n```\n{wheel_text}\n```\n💀 **BANKRUPT!** You landed on bankruptcy. Lost **{bet:,}** coins."
        elif selected_mult < 1:
            # Half back
            winnings = int(bet * selected_mult)
            await self.payout(interaction.user.id, winnings)
            msg = f"🎡 **Lucky Wheel Result:**\n```\n{wheel_text}\n```\n📉 Landed on **{selected_label}** ({selected_mult}x). You got back **{winnings:,}** coins. Net loss: **{bet - winnings:,}** coins."
        elif selected_mult == 1.5:
            winnings = int(bet * selected_mult)
            await self.payout(interaction.user.id, winnings)
            msg = f"🎡 **Lucky Wheel Result:**\n```\n{wheel_text}\n```\n✨ Landed on **{selected_label}** ({selected_mult}x)! You won **{winnings:,}** coins!"
        else:
            winnings = int(bet * selected_mult)
            await self.payout(interaction.user.id, winnings)
            msg = f"🎡 **Lucky Wheel Result:**\n```\n{wheel_text}\n```\n🎉 Landed on **{selected_label}** ({selected_mult}x)! You won **{winnings:,}** coins!"
        
        await interaction.followup.send(msg)

    @commands.Cog.listener()
    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError):
        """Handle command errors globally."""
        if isinstance(error, app_commands.CommandOnCooldown):
            remaining = int(error.retry_after)
            await interaction.response.send_message(
                f"⏳ **Cooldown:** Try again in {remaining} seconds.",
                ephemeral=True
            )
        else:
            logger.error(f"Command error: {error}")
            if not interaction.response.is_done():
                try:
                    await interaction.response.send_message(
                        f"❌ An error occurred: {str(error)[:100]}",
                        ephemeral=True
                    )
                except:
                    pass

async def setup(bot: commands.Bot):
    await bot.add_cog(Gambling(bot))
    logger.info("Gambling cog loaded")
