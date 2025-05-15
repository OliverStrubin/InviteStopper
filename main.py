import discord
from discord.ext import commands, tasks
from discord import app_commands
import datetime
import json
import os

PAUSE_FILE = "data/invite_pause_guilds.json"
os.makedirs("data", exist_ok=True)

def load_paused_guilds():
    if os.path.exists(PAUSE_FILE):
        try:
            with open(PAUSE_FILE, "r") as f:
                data = f.read().strip()
                if not data:
                    return set()
                return set(json.loads(data))
        except json.JSONDecodeError:
            print("⚠️ Warning: invite_pause_guilds.json is corrupted. Resetting.")
            return set()
    return set()

def save_paused_guilds(guild_ids):
    with open(PAUSE_FILE, "w") as f:
        json.dump(list(guild_ids), f)

def utcnow():
    return datetime.datetime.now(datetime.timezone.utc)

class Client(commands.Bot):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.invite_pause_guilds = load_paused_guilds()
        self.auto_extend = self.create_auto_extend_loop()

    def create_auto_extend_loop(self):
        @tasks.loop(hours=23)
        async def auto_extend():
            for guild_id in list(self.invite_pause_guilds):
                guild = self.get_guild(guild_id)
                if guild:
                    try:
                        await guild.edit(invites_disabled_until=None)
                        await guild.edit(invites_disabled_until=utcnow() + datetime.timedelta(hours=24))
                        print(f"🔁 Auto-extended invite pause for {guild.name}")
                    except Exception as e:
                        print(f"⚠️ Failed to extend invite pause for {guild.name}: {e}")
        return auto_extend

    async def on_ready(self):

        activity = discord.Activity(
            type=discord.ActivityType.watching,
            name=f"{len(self.guilds)} servers"
        )
        await self.change_presence(activity=activity, status=discord.Status.do_not_disturb)

        print(f'✅ Logged in as {self.user} (ID: {self.user.id})')
        try:
            synced = await self.tree.sync()
            print(f'✅ Synced {len(synced)} global command(s).')
        except Exception as e:
            print(f'❌ Failed to sync commands: {e}')

        if not self.auto_extend.is_running():
            self.auto_extend.start()

intents = discord.Intents.default()
intents.message_content = True
client = Client(command_prefix="!", intents=intents)

@client.tree.command(name="toggleinvites", description="Toggle invite pause on or off for this server.")
@app_commands.checks.has_permissions(administrator=True)
async def toggle_invites(interaction: discord.Interaction):
    guild = interaction.guild
    guild_id = guild.id
    is_paused = guild_id in client.invite_pause_guilds

    try:
        if is_paused:
            await guild.edit(invites_disabled_until=None)
            client.invite_pause_guilds.remove(guild_id)
            save_paused_guilds(client.invite_pause_guilds)
            await interaction.response.send_message(
                "✅ Invites have been resumed and auto-pause has been disabled.",
                ephemeral=True
            )
        else:
            await guild.edit(invites_disabled_until=utcnow() + datetime.timedelta(hours=24))
            client.invite_pause_guilds.add(guild_id)
            save_paused_guilds(client.invite_pause_guilds)
            await interaction.response.send_message(
                "🔒 Invites have been paused for 24h and will auto-renew until resumed.",
                ephemeral=True
            )
    except discord.Forbidden:
        await interaction.response.send_message(
            "❌ I need the 'Manage Server' permission to change invite settings.",
            ephemeral=True
        )
    except discord.HTTPException as e:
        await interaction.response.send_message(
            f"❌ Failed to update invite settings: {e}",
            ephemeral=True
        )

# Handle permission errors gracefully
@client.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
            "❌ You must have the **Administrator** permission to use this command.",
            ephemeral=True
        )
    else:
        await interaction.response.send_message(
            "⚠️ An unexpected error occurred.",
            ephemeral=True
        )
        raise error

client.run("BOT_TOKEN")
