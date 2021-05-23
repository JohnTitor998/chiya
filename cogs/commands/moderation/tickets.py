import asyncio
import logging
import privatebinapi

import dataset
import discord
from discord.ext import commands
from discord.ext.commands import Cog, Bot

import config
from utils import database
from utils import embeds
from utils.record import record_usage

# Enabling logs
log = logging.getLogger(__name__)


class TicketCog(Cog):
    """ Ticket Cog """

    def __init__(self, bot):
        self.bot = bot

    @commands.has_role(config.role_staff)
    @commands.before_invoke(record_usage)
    @commands.group()
    async def ticket(self, ctx):
        if ctx.invoked_subcommand is None:
            # Send the help command for this group
            await ctx.send_help(ctx.command)

    @commands.has_role(config.role_staff)
    @commands.before_invoke(record_usage)
    @ticket.command(name="close")
    async def close(self, ctx):
        """ Closes the modmail ticket."""

        # Get the ticket topic in database for embeds.
        with dataset.connect(database.get_db()) as db:
            table = db["tickets"]
            ticket = table.find_one(user_id=int(ctx.channel.name.replace("ticket-", "")), status="in-progress")
            ticket_topic = ticket["ticket_topic"]

        # Fetch the ticket channel.
        channel = ctx.message.channel

        # Fetch the member name with discriminator.
        member = await ctx.guild.fetch_member(ctx.message.author.id)

        # Fetch the staff role.
        role_staff = discord.utils.get(ctx.guild.roles, id=config.role_staff)

        # Fetch the trial mod role.
        role_trial_mod = discord.utils.get(ctx.guild.roles, id=config.role_trial_mod)

        # Warns if the ticket close command is called outside of the current active ticket channel.
        if not channel.category_id == config.ticket_category_id or "ticket" not in channel.name:
            await embeds.error_message(ctx=ctx, description="You can only run this command in active ticket channels.")
            return

        # Send notice that the channel has been marked read only and will be archived.
        embed = embeds.make_embed(author=False, color=0xffffc3)
        embed.title = f"🔒 Your ticket has been closed."
        embed.description = f"The channel has been marked read-only and will be archived in one minute. If you have additional comments or concerns, feel free to open another ticket."
        embed.set_image(url="https://i.imgur.com/TodlFQq.gif")
        await ctx.send(embed=embed)

        # Set the channel into a read only state.
        for role in channel.overwrites:
            # default_role is @everyone role, so skip that.
            if role == ctx.guild.default_role:
                continue
            await channel.set_permissions(role, read_messages=True, send_messages=False, add_reactions=False,
                                          manage_messages=False)

        # Initialize the PrivateBin message log string.
        message_log = f"Ticket Creator: {member}\nUser ID: {member.id}\nTicket Topic: {ticket_topic}\n\n"

        # Initialize a list of moderator ids as a set for no duplicates.
        mod_list = set()

        # Loop through all messages in the ticket from old to new.
        async for message in ctx.channel.history(oldest_first=True):

            # Ignore the bot replies.
            if not message.author.bot:

                # Time format is unnecessarily lengthy so trimming it down and keep the log go easier on the eyes.
                formatted_time = str(message.created_at).split(".")[-2]

                # Append the new messages to the current log as we loop.
                message_log += f"[{formatted_time}] {message.author}: {message.content}\n"

                # If the messenger has either staff role or trial mod role, add their ID to the mod_list set.
                if role_staff or role_trial_mod in message.author.roles:
                    mod_list.add(message.author.id)

        # Convert the set of participated mod IDs (mod_list) into a string to be used in the embed.
        participating_mods = ""
        for mod in mod_list:
            participating_mods += f"<@{mod}>\n"

        # Dump message log to private bin. This returns a dictionary, but only the url is needed for the embed.
        token = privatebinapi.send("https://bin.piracy.moe", text=message_log, expiration="never")
        url = token["full_url"]

        # Create the embed in #ticket-log.
        embed_log = embeds.make_embed(ctx=ctx, author=False, image_url=config.pencil, color=0x00ffdf)
        embed_log.title = f"{ctx.channel.name} archived"
        embed_log.add_field(name="Ticket Creator:", value=member.mention, inline=False)
        embed_log.add_field(name="Ticket Topic:", value=ticket_topic, inline=False)
        embed_log.add_field(name="Participating Moderators:", value=participating_mods, inline=False)
        embed_log.add_field(name="Ticket Log: ", value=url, inline=False)

        # Send the embed to #ticket-log.
        ticket_log = discord.utils.get(ctx.guild.channels, id=config.ticket_log)
        await ticket_log.send(embed=embed_log)

        # Update the ticket status from "in-progress" to "completed" and the PrivateBin url field in the database.
        ticket["status"] = "completed"
        ticket["log_url"] = url
        table.update(ticket, ["id"])

        # Sleep for 60 seconds before deleting the channel.
        await asyncio.sleep(60)

        # Delete the channel.
        await ctx.channel.delete()


def setup(bot: Bot) -> None:
    """ Load the Ticket cog. """
    bot.add_cog(TicketCog(bot))
    log.info("Commands loaded: tickets")
