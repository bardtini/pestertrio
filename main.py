import os
import json
import time
import random
import discord
from discord.ext import commands, tasks
from datetime import time as dt_time, timezone
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

# Task Data & State
tasks_list = []          
completed = []           
past_uncompleted = []    
archived_completed = []  
snooze_until = 0.0
DATA_FILE = "data.json"

def load_data():
    """Loads saved task data from JSON file on boot."""
    global tasks_list, completed, past_uncompleted, archived_completed, snooze_until
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                data = json.load(f)
                tasks_list = data.get("tasks_list", [])
                completed = data.get("completed", [])
                past_uncompleted = data.get("past_uncompleted", [])
                archived_completed = data.get("archived_completed", [])
                snooze_until = data.get("snooze_until", 0.0)
            except json.JSONDecodeError:
                pass

def save_data():
    """Saves current task data to JSON file."""
    with open(DATA_FILE, "w") as f:
        json.dump({
            "tasks_list": tasks_list,
            "completed": completed,
            "past_uncompleted": past_uncompleted,
            "archived_completed": archived_completed,
            "snooze_until": snooze_until
        }, f)

async def update_presence():
    """Updates bot presence to show completed task count for today."""
    done_count = sum(completed)
    await bot.change_presence(activity=discord.Game(name=f"TASKS {done_count}/3"))

def get_panel_embed():
    """Generates a dynamic, aesthetic embed for the main control panel."""
    if not tasks_list:
        return discord.Embed(
            title="🌅 Good Morning",
            description="Your infrastructure is up and running. What are we building today?",
            color=0x2B2D31 # Sleek Discord Dark Theme
        )
        
    if all(completed):
        return discord.Embed(
            title="✨ All Tasks Completed!",
            description="Incredible work today. Take some time to recharge or hyperfocus on your hobbies.",
            color=0x57F287 # Discord Green
        )

    # Unique, encouraging messages for pending tasks
    motivational_quotes = [
        "Every line of code and every small step adds up. Let's knock out another one!",
        "Momentum is a feature, not a bug. Keep the ball rolling!",
        "Focus mode activated. Let's crush this next objective.",
        "You have the vision. Now let's execute.",
        "System resources optimized. Let's direct that energy into your tasks.",
        "Laser focus. Zero distractions. You've got this."
    ]
    
    # Consolidates tasks into a clean, format-rich description block instead of bulky fields
    desc_lines = [f"*{random.choice(motivational_quotes)}*\n"]
    
    for i, t in enumerate(tasks_list):
        if completed[i]:
            desc_lines.append(f"✅ ~~{t}~~") # Strikethrough for completed
        else:
            desc_lines.append(f"⏳ **{t}**") # Bold for pending
            
    embed = discord.Embed(
        title="🎯 Current Objectives",
        description="\n".join(desc_lines),
        color=0x5865F2 # Discord Blurple
    )
        
    if past_uncompleted:
        embed.set_footer(text=f"📌 Note: You have {len(past_uncompleted)} past uncompleted tasks pending.")
        
    return embed

class TaskModal(discord.ui.Modal, title="Set Your Daily 3"):
    def __init__(self):
        super().__init__()
        self.t1 = discord.ui.TextInput(label="Task 1", placeholder="e.g. First task")
        self.t2 = discord.ui.TextInput(label="Task 2", placeholder="e.g. Second task")
        self.t3 = discord.ui.TextInput(label="Task 3", placeholder="e.g. Third task")
        self.add_item(self.t1)
        self.add_item(self.t2)
        self.add_item(self.t3)

    async def on_submit(self, interaction: discord.Interaction):
        global tasks_list, completed
        tasks_list = [self.t1.value, self.t2.value, self.t3.value]
        completed = [False, False, False]
        
        save_data()
        await update_presence()
        
        await interaction.response.edit_message(embed=get_panel_embed(), view=MainPanel())

class MarkProgressSelect(discord.ui.Select):
    def __init__(self, panel_message):
        self.panel_message = panel_message
        options = []
        for i, task in enumerate(tasks_list):
            if not completed[i]:
                options.append(discord.SelectOption(label=f"Today: Task {i+1}", description=task[:90], value=f"today_{i}"))
        for j, task in enumerate(past_uncompleted):
            options.append(discord.SelectOption(label=f"Past Task #{j+1}", description=task[:90], value=f"past_{j}"))
        
        super().__init__(placeholder="Select a task to complete...", min_values=1, max_values=1, options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val.startswith("today_"):
            idx = int(val.split("_")[1])
            completed[idx] = True
            archived_completed.append(tasks_list[idx])
            task_name = tasks_list[idx]
        else:
            idx = int(val.split("_")[1])
            task_name = past_uncompleted.pop(idx)
            archived_completed.append(task_name)
        
        save_data()
        await update_presence()
        
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=get_panel_embed(), view=MainPanel())
            except:
                pass
        
        await interaction.response.edit_message(content=f"✅ **{task_name}** successfully completed!", view=None)

class UndoSelect(discord.ui.Select):
    def __init__(self, panel_message):
        self.panel_message = panel_message
        options = []
        for i, task in enumerate(tasks_list):
            if completed[i]:
                options.append(discord.SelectOption(label=f"Today: Task {i+1}", description=task[:90], value=f"today_{i}"))
        for k, task in enumerate(archived_completed):
            if task not in [tasks_list[i] for i, c in enumerate(completed) if c]:
                options.append(discord.SelectOption(label=f"Archived Task #{k+1}", description=task[:90], value=f"archive_{k}"))

        super().__init__(placeholder="Select a task to undo...", min_values=1, max_values=1, options=options[:25])

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val.startswith("today_"):
            idx = int(val.split("_")[1])
            completed[idx] = False
            task_name = tasks_list[idx]
            if task_name in archived_completed:
                archived_completed.remove(task_name)
        else:
            idx = int(val.split("_")[1])
            task_name = archived_completed.pop(idx)
            past_uncompleted.append(task_name)

        save_data()
        await update_presence()
        
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=get_panel_embed(), view=MainPanel())
            except:
                pass

        await interaction.response.edit_message(content=f"↩️ Reverted **{task_name}** to pending status.", view=None)

class ManageSelect(discord.ui.Select):
    """The master dropdown that hides all the secondary clutter."""
    def __init__(self, panel_message):
        self.panel_message = panel_message
        options = []
        
        # Dynamic Snooze Options
        if time.time() < snooze_until:
            options.append(discord.SelectOption(label="Cancel Snooze", emoji="⏰", description="Resume notifications now", value="snooze_cancel"))
        else:
            options.append(discord.SelectOption(label="Snooze for 1 Hour", emoji="💤", description="Pause pings for 60 mins", value="snooze_1h"))
            options.append(discord.SelectOption(label="Snooze for 4 Hours", emoji="🛌", description="Pause pings for 4 hours", value="snooze_4h"))

        # Task Management
        options.append(discord.SelectOption(label="Undo Last Action", emoji="↩️", description="Mark a completed task as pending", value="undo"))
        
        # History Views
        options.append(discord.SelectOption(label="View Today's Tasks", emoji="📋", value="view_today"))
        options.append(discord.SelectOption(label="View Past Uncompleted", emoji="📜", value="view_past"))
        options.append(discord.SelectOption(label="View Archive", emoji="📁", value="view_archive"))

        super().__init__(placeholder="🛠️ Manage Tasks & Settings...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        global snooze_until
        val = self.values[0]

        if val.startswith("snooze_"):
            if val == "snooze_1h":
                snooze_until = time.time() + 3600
                msg = "💤 Notifications snoozed for 1 hour."
            elif val == "snooze_4h":
                snooze_until = time.time() + 14400
                msg = "🛌 Notifications snoozed for 4 hours."
            elif val == "snooze_cancel":
                snooze_until = 0.0
                msg = "⏰ Snooze canceled. Notifications resumed."
            
            save_data()
            await interaction.response.send_message(msg, ephemeral=True)
            if self.panel_message:
                await self.panel_message.edit(view=MainPanel())
                
        elif val == "undo":
            has_today_done = any(completed)
            has_archived = len(archived_completed) > 0
            if not has_today_done and not has_archived:
                await interaction.response.send_message("No completed tasks to undo!", ephemeral=True)
                return
            await interaction.response.send_message("Which task do you want to mark as incomplete?", view=SingleView(UndoSelect(self.panel_message)), ephemeral=True)

        elif val == "view_today":
            if not tasks_list:
                await interaction.response.send_message("No tasks set for today yet.", ephemeral=True)
                return
            status = [f"{'✅' if completed[i] else '❌'} {t}" for i, t in enumerate(tasks_list)]
            await interaction.response.send_message("**Today's Tasks:**\n" + "\n".join(status), ephemeral=True)

        elif val == "view_past":
            if not past_uncompleted:
                await interaction.response.send_message("No past uncompleted tasks!", ephemeral=True)
                return
            status = [f"❌ {t}" for t in past_uncompleted]
            await interaction.response.send_message("**Past Uncompleted Tasks:**\n" + "\n".join(status), ephemeral=True)

        elif val == "view_archive":
            if not archived_completed:
                await interaction.response.send_message("Archive is empty.", ephemeral=True)
                return
            status = [f"✅ {t}" for t in archived_completed]
            await interaction.response.send_message("**Completed Tasks Archive:**\n" + "\n".join(status), ephemeral=True)


class SingleView(discord.ui.View):
    def __init__(self, item):
        super().__init__(timeout=None)
        self.add_item(item)

class SetTasksBtn(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Set Tasks", emoji="📝", style=discord.ButtonStyle.primary, row=0)
    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(TaskModal())

class MarkProgressBtn(discord.ui.Button):
    def __init__(self):
        super().__init__(label="Mark Progress", emoji="✅", style=discord.ButtonStyle.success, row=0)
    async def callback(self, interaction: discord.Interaction):
        has_today = any(not c for c in completed)
        has_past = len(past_uncompleted) > 0
        if not has_today and not has_past:
            await interaction.response.send_message("No uncompleted tasks available!", ephemeral=True)
            return
        await interaction.response.send_message("Which task did you complete?", view=SingleView(MarkProgressSelect(interaction.message)), ephemeral=True)


class MainPanel(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        
        if not tasks_list:
            self.add_item(SetTasksBtn())
        elif not all(completed):
            self.add_item(MarkProgressBtn())
            
        self.add_item(ManageSelect(panel_message=None))

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await update_presence()
    harass_loop.start()
    daily_prompt.start()

# Prompts at 8:00 AM UTC
@tasks.loop(time=dt_time(hour=8, minute=0, tzinfo=timezone.utc))
async def daily_prompt():
    global tasks_list, completed, past_uncompleted, snooze_until
    for i, t in enumerate(tasks_list):
        if not completed[i]:
            past_uncompleted.append(t)

    tasks_list = []
    completed = []
    snooze_until = 0.0 # Reset snooze on a new day
    
    save_data()
    await update_presence()
    
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.purge(limit=100)
        view = MainPanel()
        msg = await channel.send(f"<@{USER_ID}>", embed=get_panel_embed(), view=view)
        view.children[-1].panel_message = msg

# Pings every 20 minutes
@tasks.loop(minutes=20)
async def harass_loop():
    if time.time() < snooze_until:
        return 
        
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return
        
    await channel.purge(limit=50, check=lambda m: m.author == bot.user)
    view = MainPanel()
    msg = await channel.send(f"<@{USER_ID}>", embed=get_panel_embed(), view=view)
    view.children[-1].panel_message = msg

load_data()
bot.run(TOKEN)