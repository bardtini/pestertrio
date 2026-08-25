import os
import json
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

# Task Data
tasks_list = []          
completed = []           
past_uncompleted = []    
archived_completed = []  
DATA_FILE = "data.json"

def load_data():
    """Loads saved task data from JSON file on boot."""
    global tasks_list, completed, past_uncompleted, archived_completed
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r") as f:
            try:
                data = json.load(f)
                tasks_list = data.get("tasks_list", [])
                completed = data.get("completed", [])
                past_uncompleted = data.get("past_uncompleted", [])
                archived_completed = data.get("archived_completed", [])
            except json.JSONDecodeError:
                pass

def save_data():
    """Saves current task data to JSON file."""
    with open(DATA_FILE, "w") as f:
        json.dump({
            "tasks_list": tasks_list,
            "completed": completed,
            "past_uncompleted": past_uncompleted,
            "archived_completed": archived_completed
        }, f)

async def update_presence():
    """Updates bot presence to show completed task count for today."""
    done_count = sum(completed)
    await bot.change_presence(activity=discord.Game(name=f"TASKS {done_count}/3"))

def get_panel_embed():
    """Generates the dynamic embed for the main control panel."""
    if not tasks_list:
        return discord.Embed(
            title="🚨 TASK ALERT",
            description="You HAVEN'T SET YOUR 3 TASKS YET!",
            color=discord.Color.red()
        )
        
    if all(completed):
        return discord.Embed(
            title="🎯 All Tasks Completed!",
            description="Great job! You've finished your 3 tasks for today.",
            color=discord.Color.green()
        )
        
    pending = [f"{'✅' if completed[i] else '❌'} {t}" for i, t in enumerate(tasks_list)]
    status_str = "\n".join(pending)
    past_note = f"\n\n*(You also have {len(past_uncompleted)} past uncompleted tasks pending)*" if past_uncompleted else ""
    
    return discord.Embed(
        title="⚠️ GET BACK TO WORK!",
        description=f"**Today's Tasks:**\n{status_str}{past_note}",
        color=discord.Color.orange()
    )

class TaskModal(discord.ui.Modal, title="Set Your Daily 3"):
    t1 = discord.ui.TextInput(label="Task 1", placeholder="e.g. First task")
    t2 = discord.ui.TextInput(label="Task 2", placeholder="e.g. Second task")
    t3 = discord.ui.TextInput(label="Task 3", placeholder="e.g. Third task")

    async def on_submit(self, interaction: discord.Interaction):
        global tasks_list, completed
        tasks_list = [self.t1.value, self.t2.value, self.t3.value]
        completed = [False, False, False]
        
        save_data()
        await update_presence()
        
        # Dynamically edits the main panel message that triggered this modal
        await interaction.response.edit_message(embed=get_panel_embed(), view=TaskView())

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
        
        # Updates the original main panel visually
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=get_panel_embed(), view=TaskView())
            except:
                pass
        
        # Replaces the ephemeral dropdown menu entirely with the success text
        await interaction.response.edit_message(content=f"✅ Marked completed: **{task_name}**", view=None)

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
        
        # Updates the original main panel visually
        if self.panel_message:
            try:
                await self.panel_message.edit(embed=get_panel_embed(), view=TaskView())
            except:
                pass

        # Replaces the ephemeral dropdown menu entirely with the undo text
        await interaction.response.edit_message(content=f"↩️ Undid completion for: **{task_name}**", view=None)

class SingleView(discord.ui.View):
    def __init__(self, item):
        super().__init__(timeout=None)
        self.add_item(item)

class DataSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Today's Tasks", emoji="📋", description="View your current daily tasks", value="today"),
            discord.SelectOption(label="Past Uncompleted", emoji="📜", description="View unfinished tasks from previous days", value="past"),
            discord.SelectOption(label="Archive", emoji="📁", description="View all completed tasks", value="archive")
        ]
        super().__init__(placeholder="📊 View task history...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        val = self.values[0]
        if val == "today":
            if not tasks_list:
                await interaction.response.send_message("No tasks set for today yet.", ephemeral=True)
                return
            status = [f"{'✅' if completed[i] else '❌'} {t}" for i, t in enumerate(tasks_list)]
            await interaction.response.send_message("**Today's Tasks:**\n" + "\n".join(status), ephemeral=True)
        elif val == "past":
            if not past_uncompleted:
                await interaction.response.send_message("No past uncompleted tasks!", ephemeral=True)
                return
            status = [f"❌ {t}" for t in past_uncompleted]
            await interaction.response.send_message("**Past Uncompleted Tasks:**\n" + "\n".join(status), ephemeral=True)
        elif val == "archive":
            if not archived_completed:
                await interaction.response.send_message("Archive is empty.", ephemeral=True)
                return
            status = [f"✅ {t}" for t in archived_completed]
            await interaction.response.send_message("**Completed Tasks Archive:**\n" + "\n".join(status), ephemeral=True)

class TaskView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(DataSelect())

    @discord.ui.button(label="Set Tasks", emoji="📝", style=discord.ButtonStyle.primary, row=0)
    async def set_tasks(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TaskModal())

    @discord.ui.button(label="Mark Progress", emoji="✅", style=discord.ButtonStyle.success, row=0)
    async def complete_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        has_today = any(not c for c in completed)
        has_past = len(past_uncompleted) > 0
        if not has_today and not has_past:
            await interaction.response.send_message("No uncompleted tasks available!", ephemeral=True)
            return
        # Pass interaction.message so the dropdown knows which panel to edit
        await interaction.response.send_message("Which task did you complete?", view=SingleView(MarkProgressSelect(interaction.message)), ephemeral=True)

    @discord.ui.button(label="Undo", emoji="↩️", style=discord.ButtonStyle.danger, row=0)
    async def undo_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        has_today_done = any(completed)
        has_archived = len(archived_completed) > 0
        if not has_today_done and not has_archived:
            await interaction.response.send_message("No completed tasks to undo!", ephemeral=True)
            return
        # Pass interaction.message so the dropdown knows which panel to edit
        await interaction.response.send_message("Which task do you want to mark as incomplete?", view=SingleView(UndoSelect(interaction.message)), ephemeral=True)

    @discord.ui.button(label="Clear Chat", emoji="🧹", style=discord.ButtonStyle.secondary, row=2)
    async def clear_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await interaction.channel.purge(limit=100)
        # Rebuild the main panel fresh
        await interaction.channel.send(f"<@{USER_ID}>", embed=get_panel_embed(), view=TaskView())

@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")
    await update_presence()
    harass_loop.start()
    daily_prompt.start()

# Prompts at 8:00 AM UTC
@tasks.loop(time=time(hour=8, minute=0, tzinfo=timezone.utc))
async def daily_prompt():
    global tasks_list, completed, past_uncompleted
    for i, t in enumerate(tasks_list):
        if not completed[i]:
            past_uncompleted.append(t)

    tasks_list = []
    completed = []
    
    save_data()
    await update_presence()
    
    channel = bot.get_channel(CHANNEL_ID)
    if channel:
        await channel.purge(limit=100) 
        await channel.send(f"<@{USER_ID}>", embed=get_panel_embed(), view=TaskView())

# Pings every 20 minutes
@tasks.loop(minutes=20)
async def harass_loop():
    channel = bot.get_channel(CHANNEL_ID)
    if not channel:
        return
        
    await channel.purge(limit=50, check=lambda m: m.author == bot.user)
    await channel.send(f"<@{USER_ID}>", embed=get_panel_embed(), view=TaskView())

load_data()
bot.run(TOKEN)