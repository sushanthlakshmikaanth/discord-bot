import discord
import tiktoken
from discord.ext import commands
from conf import DISCORD_TOKEN
from cache import SimpleTTLCache
from misc import get_logger
from util_meta import get_gh_discuss, get_pep_text
from util_openai import tokens_to_chunks, send_partial_text, summarize
import random

logger = get_logger(__name__)
intents = discord.Intents.default()
intents.message_content = True
cache = SimpleTTLCache(100)
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
    logger.info(f"Logged in as {bot.user.name}({bot.user.id})")


@bot.command(name="ping")
async def ping(ctx):
    """Check if the bot is alive."""
    await ctx.send("pong")


@bot.command(name="tldr")
@commands.cooldown(1, 10, commands.BucketType.user)  # Cooldown: 1 request every 10 seconds per user
async def tldr(ctx, target: str, number: int):
    """Summarize PEP or GitHub issue."""
    requester = ctx.message.author
    logger.info(f"Request: {requester}, target: {target}, number: {number}")
    target = target.lower()
    if target not in ["pep", "gh"]:
        await ctx.send("Only supports PEP and GitHub right now.")
        return

    try:
        target_doc = f"{target}-{number:04d}"
        cached_result = cache.get(target_doc)
        author = ctx.message.author
        if cached_result:
            await ctx.send(f"{author.mention} Here you go:\n{cached_result}")
            return
        if target == "pep":
            text = await get_pep_text(target_doc)
            link = f"https://peps.python.org/{target_doc}"
        else:
            text = await get_gh_discuss(number)
            link = f"https://github.com/python/cpython/issues/{number}"

        encoding = tiktoken.encoding_for_model("gpt-3.5-turbo")
        tokens = encoding.encode(text)
        if len(tokens) > 3000:
            responses = []
            for chunk in tokens_to_chunks(tokens):
                decoded_text = encoding.decode(chunk)
                res = await send_partial_text(decoded_text, target_doc)
                responses.append(res)
            final_text = "\n".join(responses)
        else:
            final_text = text

        summary = await summarize(link, final_text)
        cache.put(target_doc, summary, 60 * 10)  # Cache for 10 minutes
        await ctx.send(f"{author.mention} Here you go:\n{summary}")
    except Exception as e:
        logger.error("An exception was thrown!", exc_info=True)
        await ctx.send(f"Error: {e}")


@bot.command(name="help")
async def help_command(ctx):
    """Display the available commands and their usage."""
    commands_info = (
        "**!ping** - Check if the bot is alive.\n"
        "**!tldr [pep/gh] [number]** - Summarize a PEP or GitHub issue.\n"
        "**!about** - Get information about this bot.\n"
        "**!random_pep** - Get a summary of a random PEP.\n"
        "**!clear [key]** - Clear a specific cached result (admin only).\n"
    )
    await ctx.send(f"**Available Commands:**\n{commands_info}")


@bot.command(name="about")
async def about(ctx):
    """Provide information about the bot."""
    await ctx.send(
        "I am a Python bot designed to summarize Python PEPs and GitHub discussions."
        " Use `!help` to see my commands."
    )


@bot.command(name="random_pep")
async def random_pep(ctx):
    """Fetch a summary of a random PEP."""
    pep_number = random.randint(1, 800)  # Assuming there are ~800 PEPs
    await tldr(ctx, "pep", pep_number)


@bot.command(name="clear")
@commands.has_permissions(administrator=True)
async def clear_cache(ctx, key: str):
    """Clear the cache for a specific key (admin-only)."""
    if cache.delete(key):
        await ctx.send(f"Cache for `{key}` cleared!")
    else:
        await ctx.send(f"No cache entry found for `{key}`.")


@tldr.error
async def tldr_error(ctx, error):
    """Handle errors for the tldr command."""
    if isinstance(error, commands.CommandOnCooldown):
        await ctx.send(f"You're doing that too often! Try again in {error.retry_after:.2f} seconds.")
    else:
        await ctx.send(f"An error occurred: {str(error)}")


if __name__ == "__main__":
    bot.run(DISCORD_TOKEN)
