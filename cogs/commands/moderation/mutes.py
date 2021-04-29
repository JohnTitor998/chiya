import logging
import time

import dataset
import discord
from discord.ext import commands
from discord.ext.commands import Cog, Bot, Context, Greedy

import config
from utils import database
from utils import embeds
from utils.record import record_usage

# Enabling logs
log = logging.getLogger(__name__)

class MuteCog(Cog):
    """ Mute Cog """

    def __init__(self, bot):
        self.bot = bot

    async def can_action_member(self, ctx: Context, member: discord.Member) -> bool:
        """ Stop mods from doing stupid things. """
        # Stop mods from actioning on the bot.
        if member.id == self.bot.user.id:
            await embeds.error_message(ctx=ctx, description="You cannot action that member due to hierarchy.")
            return False

        # Stop mods from actioning one another, people higher ranked than them or themselves.
        if member.top_role >= ctx.author.top_role:
            await embeds.error_message(ctx=ctx, description="You cannot action that member due to hierarchy.")
            return False

        # Checking if Bot is able to even perform the action
        if member.top_role >= member.guild.me.top_role:
            await embeds.error_message(ctx=ctx, description="I cannot action that member.")
            return False

        # Otherwise, the action is probably valid, return true.
        return True

    @commands.has_role(config.role_staff)
    @commands.bot_has_permissions(manage_roles=True, send_messages=True)
    @commands.before_invoke(record_usage)
    @commands.command(name="mute")
    async def mute(self, ctx: Context, member: discord.Member, *, reason: str = None):
        """ Mutes member in guild. """

        # TODO: Implement temp/timed mute functionality
        # NOTE: this is worthless if the member leaves and then rejoins. (resets roles)

        # Checks if invoker can action that member (self, bot, etc.)
        if not await self.can_action_member(ctx=ctx, member=member):
            return

        # Check if the user is muted already.
        if discord.utils.get(ctx.guild.roles, id=config.role_muted) in member.roles:
            await embeds.error_message(ctx=ctx, description=f"{member.mention} is already muted.")
            return

        # Handle cases where the reason is not provided.
        if not reason:
            reason = "No reason provided."
            
        if len(reason) > 512:
            await embeds.error_message(ctx=ctx, description="Reason must be less than 512 characters.")
            return

        embed = embeds.make_embed(ctx=ctx, title=f"Muting member: {member.name}",
            image_url=config.user_mute, color="soft_red")
        embed.description=f"{member.mention} was muted by {ctx.author.mention} for: {reason}"

        # Creates a channel for users to appeal/discuss their mute
        guild = ctx.message.guild
        category = discord.utils.get(guild.categories, id=config.ticket_category_id)

        # Create a channel in the tickets category specified in the config.     
        mute_channel = await guild.create_text_channel(f"mute-{member.id}", category=category)

        # Give both the staff and the user perms to access the channel. 
        await mute_channel.set_permissions(discord.utils.get(guild.roles, id=config.role_trial_mod), read_messages=True)
        await mute_channel.set_permissions(discord.utils.get(guild.roles, id=config.role_staff), read_messages=True)
        await mute_channel.set_permissions(member, read_messages=True)

        mute_channel_embed = embeds.make_embed(title="🤐 You were muted", description="If you have any questions or concerns about your mute, you may voice them here.")
        mute_channel_embed.add_field(name="Moderator:", value=ctx.author.mention, inline=True)
        mute_channel_embed.add_field(name="Length:", value="Indefinite.", inline=True) # TODO: Implement timed mutes
        mute_channel_embed.add_field(name="Reason:", value=reason, inline=False)
        
        await mute_channel.send(embed=mute_channel_embed)

        # Send member message telling them that they were muted and why.
        try: # Incase user has DM's Blocked.
            channel = await member.create_dm()
            mute_embed = embeds.make_embed(author=False, color=0x8083b0)
            mute_embed.title = f"Uh-oh, you've been muted!"
            mute_embed.description = "If you believe this was a mistake, contact staff."
            mute_embed.add_field(name="Server:", value=ctx.guild, inline=True)
            mute_embed.add_field(name="Moderator:", value=ctx.message.author.mention, inline=True)
            mute_embed.add_field(name="Length:", value="Indefinite", inline=True) # TODO: Implement timed mutes.
            mute_embed.add_field(name="Mute Channel:", value=mute_channel.mention, inline=True)
            mute_embed.add_field(name="Reason:", value=reason, inline=False)
            mute_embed.set_image(url="https://i.imgur.com/KE1jNl3.gif")
            await channel.send(embed=mute_embed)
        except:
            embed.add_field(name="Notice:", value=f"Unable to message {member.mention} about this action. This can be caused by the user not being in the server, having DMs disabled, or having the bot blocked.")

        # Send the mute embed DM to the user.
        await ctx.reply(embed=embed)

        # Adds "Muted" role to member.
        role = discord.utils.get(ctx.guild.roles, id=config.role_muted)
        await member.add_roles(role, reason=reason)

        # Add the mute to the mod_log database.
        with dataset.connect(database.get_db()) as db:
            db["mod_logs"].insert(dict(
                user_id=member.id, mod_id=ctx.author.id, timestamp=int(time.time()), reason=reason, type="mute"
            ))

    @commands.has_role(config.role_staff)
    @commands.bot_has_permissions(manage_roles=True, send_messages=True)
    @commands.before_invoke(record_usage)
    @commands.command(name="unmute")
    async def unmute(self, ctx: Context, member: discord.Member, *, reason: str = None):
        """ Unmutes member in guild. """

        # Checks if invoker can action that member (self, bot, etc.)
        if not await self.can_action_member(ctx=ctx, member=member):
            return

        # Check if the user is actually muted.
        if discord.utils.get(ctx.guild.roles, id=config.role_muted) not in member.roles:
            await ctx.reply("That user is not muted.")
            return

        # Handle cases where the reason is not provided.
        if not reason:
            reason = "No reason provided."
            
        if len(reason) > 512:
            await embeds.error_message(ctx=ctx, description="Reason must be less than 512 characters.")
            return

        embed = embeds.make_embed(ctx=ctx, title=f"Unmuting member: {member.name}",
            image_url=config.user_unmute, color=config.soft_green)
        embed.description=f"{member.mention} was unmuted by {ctx.author.mention} for: {reason}"
        
        # Send member message telling them that they were banned and why.
        try: # Incase user has DM's Blocked.
            channel = await member.create_dm()
            unmute_embed = embeds.make_embed(author=False, color=0x8a3ac5)
            unmute_embed.title = f"Yay, you've been unmuted!"
            unmute_embed.description = "Review our server rules to avoid being actioned again in the future."
            unmute_embed.add_field(name="Server:", value=ctx.guild, inline=True)
            unmute_embed.add_field(name="Moderator:", value=ctx.message.author.mention, inline=True)
            unmute_embed.add_field(name="Reason:", value=reason, inline=False)
            unmute_embed.set_image(url="https://i.imgur.com/U5Fvr2Y.gif")
            await channel.send(embed=unmute_embed)
        except:
            embed.add_field(name="Notice:", value=f"Unable to message {member.mention} about this action. User either has DMs disabled or the bot blocked.")

        # Send the unmute embed DM to the user.
        await ctx.reply(embed=embed)

        # Removes "Muted" role from member.
        role = discord.utils.get(ctx.guild.roles, id=config.role_muted)
        await member.remove_roles(role, reason=reason)

        # archives mute channel
        mute_category = discord.utils.get(ctx.guild.categories, id=config.ticket_category_id)
        channel = discord.utils.get(mute_category.channels, name=f"mute-{member.id}")
        archive = discord.utils.get(ctx.guild.categories, id=config.archive_category)
        await channel.edit(category=archive, sync_permissions=True)

        # Add the mute to the mod_log database.
        with dataset.connect(database.get_db()) as db:
            db["mod_logs"].insert(dict(
                user_id=member.id, mod_id=ctx.author.id, timestamp=int(time.time()), reason=reason, type="unmute"
            ))

def setup(bot: Bot) -> None:
    """ Load the Mute cog. """
    bot.add_cog(MuteCog(bot))
    log.info("Commands loaded: mutes")
