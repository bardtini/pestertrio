import os
import discord
from discord.ext import commands, tasks
from datetime import time, timezone
from dotenv import load_dotenv

from flask import Flask
from threading import Thread

app = Flask('')

@app.route('/')
def home():
    return "Bot is online!"

def keep_alive():
    Thread(target=lambda: app.run(host='0.0.0.0', port=8080)).start()

keep_alive()

# Load credentials
load_dotenv()
TOKEN = os.getenv("DISCORD_TOKEN")
USER_ID = int(os.getenv("USER_ID"))
CHANNEL_ID = int(os.getenv("CHANNEL_ID"))

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

tasks_list = []
completed = []

async def update_presence():
    """Updates bot presence to show completed task count."""
    done_count = sum(completed)
    await bot.change_presence(activity=discord.Game(name=f"TASKS {done_count}/3"))

class TaskModal(discord.ui.Modal, title="Set Your Daily 3"):
    t1 = discord.ui.TextInput(label="Task 1", placeholder="e.g. First")
    t2 = discord.ui.TextInput(label="Task 2", placeholder="e.g. Second")
    t3 = discord.ui.TextInput(label="Task 3", placeholder="e.g. Third")

    async def on_submit(self, interaction: discord.Interaction):
        global tasks_list, completed
        tasks_list = [self.t1.value, self.t2.value, self.t3.value]
        completed = [False, False, False]
        await update_presence()
        await interaction.response.send_message("Tasks locked in. Clock is ticking!", ephemeral=True)

class TaskView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 Set Tasks", style=discord.ButtonStyle.primary)
    async def set_tasks(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TaskModal())

    @discord.ui.button(label="✅ Mark Progress", style=discord.ButtonStyle.success)
    async def complete_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        global completed
        for i in range(len(completed)):
            if not completed[i]:
                completed[i] = True
                await update_presence()
                await interaction.response.send_message(f"Marked completed: **{tasks_list[i]}**", ephemeral=False)
                return
        await interaction.response.send_message("All tasks are already completed!", ephemeral=True)

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await update_presence()
    harass_loop.start()
    daily_prompt.start()

# Prompts at 8:00 AM UTC
@tasks.loop(time=time(hour=8, minute=0, tzinfo=timezone.utc))
async def daily_prompt():
    global tasks_list, completed
    tasks_list = []
    completed = []
    await update_presence()
    channel = bot.get_channel(CHANNEL_ID)
    await channel.send(f"<@{USER_ID}> Good morning! Set your 3 tasks for today.", view=TaskView())

# Pings every 20 minutes
@tasks.loop(minutes=20)
async def harass_loop():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return

    if not tasks_list:
        await channel.send(f"🚨 <@{USER_ID}> You HAVEN'T SET YOUR 3 TASKS YET!", view=TaskView())
    elif not all(completed):
        pending = [f"❌ {t}" for i, t in enumerate(tasks_list) if not completed[i]]
        status_str = "\n".join(pending)
        await channel.send(f"⚠️ <@{USER_ID}> GET BACK TO WORK! Pending tasks:\n{status_str}", view=TaskView())

bot.run(TOKEN)