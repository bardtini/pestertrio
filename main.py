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
        
        status = "\n".join([f"❌ {t}" for t in tasks_list])
        await interaction.response.send_message(f"Tasks locked in! Clock is ticking.\n\n**Today's Tasks:**\n{status}", ephemeral=False)

class MarkProgressSelect(discord.ui.Select):
    def __init__(self):
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
        await interaction.response.send_message(f"✅ Marked completed: **{task_name}**", ephemeral=False)

class UndoSelect(discord.ui.Select):
    def __init__(self):
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
        await interaction.response.send_message(f"↩️ Undid completion for: **{task_name}**", ephemeral=False)

class SingleView(discord.ui.View):
    def __init__(self, item):
        super().__init__(timeout=None)
        self.add_item(item)

class TaskView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="📝 Set Tasks", style=discord.ButtonStyle.primary, row=0)
    async def set_tasks(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TaskModal())

    @discord.ui.button(label="✅ Mark Progress", style=discord.ButtonStyle.success, row=0)
    async def complete_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        has_today = any(not c for c in completed)
        has_past = len(past_uncompleted) > 0
        if not has_today and not has_past:
            await interaction.response.send_message("No uncompleted tasks available!", ephemeral=True)
            return
        await interaction.response.send_message("Which task did you complete?", view=SingleView(MarkProgressSelect()), ephemeral=True)

    @discord.ui.button(label="↩️ Undo", style=discord.ButtonStyle.danger, row=0)
    async def undo_task(self, interaction: discord.Interaction, button: discord.ui.Button):
        has_today_done = any(completed)
        has_archived = len(archived_completed) > 0
        if not has_today_done and not has_archived:
            await interaction.response.send_message("No completed tasks to undo!", ephemeral=True)
            return
        await interaction.response.send_message("Which task do you want to mark as incomplete?", view=SingleView(UndoSelect()), ephemeral=True)

    @discord.ui.button(label="📋 Today", style=discord.ButtonStyle.secondary, row=1)
    async def view_today(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not tasks_list:
            await interaction.response.send_message("No tasks set for today yet.", ephemeral=True)
            return
        status = [f"{'✅' if completed[i] else '❌'} {t}" for i, t in enumerate(tasks_list)]
        await interaction.response.send_message("**Today's Tasks:**\n" + "\n".join(status), ephemeral=True)

    @discord.ui.button(label="📜 Past Uncompleted", style=discord.ButtonStyle.secondary, row=1)
    async def view_past(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not past_uncompleted:
            await interaction.response.send_message("No past uncompleted tasks!", ephemeral=True)
            return
        status = [f"❌ {t}" for t in past_uncompleted]
        await interaction.response.send_message("**Past Uncompleted Tasks:**\n" + "\n".join(status), ephemeral=True)

    @discord.ui.button(label="📁 Archive", style=discord.ButtonStyle.secondary, row=1)
    async def view_archive(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not archived_completed:
            await interaction.response.send_message("Archive is empty.", ephemeral=True)
            return
        status = [f"✅ {t}" for t in archived_completed]
        await interaction.response.send_message("**Completed Tasks Archive:**\n" + "\n".join(status), ephemeral=True)

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
        await channel.purge(limit=100) # Deletes up to 100 messages prior to setting new tasks
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
        past_note = f"\n\n*(You also have {len(past_uncompleted)} past uncompleted tasks pending)*" if past_uncompleted else ""
        await channel.send(f"⚠️ <@{USER_ID}> GET BACK TO WORK! Pending tasks:\n{status_str}{past_note}", view=TaskView())

load_data()
bot.run(TOKEN)