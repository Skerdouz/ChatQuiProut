import os
import discord
import asyncio
import requests
import random
from typing import Union
from src import log, responses
from dotenv import load_dotenv
from discord import app_commands
from Bard import Chatbot as BardChatbot
from revChatGPT.V3 import Chatbot
from revChatGPT.V1 import AsyncChatbot
from EdgeGPT import Chatbot as EdgeChatbot
from datetime import datetime
from .sql import *


logger = log.setup_logger(__name__)
load_dotenv()

conn = create_connection()
create_table(conn)

config_dir = os.path.abspath(f"{__file__}/../../")
prompt_name = 'system_prompt.txt'
prompt_path = os.path.join(config_dir, prompt_name)
with open(prompt_path, "r", encoding="utf-8") as f:
    prompt = f.read()

class aclient(discord.Client):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        self.activity = discord.Activity(type=discord.ActivityType.listening, name="/help | /chat")
        self.isPrivate = False
        self.is_replying_all = os.getenv("REPLYING_ALL")
        self.replying_all_discord_channel_id = os.getenv("REPLYING_ALL_DISCORD_CHANNEL_ID")
        self.openAI_email = os.getenv("OPENAI_EMAIL")
        self.openAI_password = os.getenv("OPENAI_PASSWORD")
        self.openAI_API_key = os.getenv("OPENAI_API_KEY")
        self.openAI_gpt_engine = os.getenv("GPT_ENGINE")
        self.chatgpt_session_token = os.getenv("SESSION_TOKEN")
        self.chatgpt_access_token = os.getenv("ACCESS_TOKEN")
        self.chatgpt_paid = os.getenv("UNOFFICIAL_PAID")
        self.bard_session_id = os.getenv("BARD_SESSION_ID")
        self.chat_model = os.getenv("CHAT_MODEL")
        self.chatbot = self.get_chatbot_model()
        self.message_queue = asyncio.Queue()
        self.unsplash_access_key = os.getenv("UNSPLASH_ACCESS_KEY")
        self.unsplash_api_url = f'https://api.unsplash.com/photos/random?query=woman-face&client_id={self.unsplash_access_key}'
        self.conn = create_connection()
        self.pexels_access_key = os.getenv("PEXELS_ACCESS_KEY")
        self.pexels_api_url = f'https://api.pexels.com/v1/search?query=woman%20face%20photoshoot'
        self.img_api_model = os.getenv("IMAGE_API_MODEL")


    def get_chatbot_model(self, prompt=prompt) -> Union[AsyncChatbot, Chatbot]:
        if self.chat_model == "UNOFFICIAL":
            return AsyncChatbot(config={"email": self.openAI_email, "password": self.openAI_password, "access_token": self.chatgpt_access_token, "model": self.openAI_gpt_engine, "paid": self.chatgpt_paid})
        elif self.chat_model == "OFFICIAL":
                return Chatbot(api_key=self.openAI_API_key, engine=self.openAI_gpt_engine, system_prompt=prompt)
        elif self.chat_model == "Bard":
            return BardChatbot(session_id=self.bard_session_id)
        elif self.chat_model == "Bing":
            return EdgeChatbot(cookie_path='./cookies.json')

    async def process_messages(self):
        while True:
            message, user_message = await self.message_queue.get()
            try:
                await self.send_message(message, user_message)
            except Exception as e:
                logger.exception(f"Error while processing message: {e}")
            finally:
                self.message_queue.task_done()

    async def enqueue_message(self, message, user_message):
        await message.response.defer(ephemeral=self.isPrivate)
        await self.message_queue.put((message, user_message))

    async def send_message(self, message, user_message):
        if self.is_replying_all == "False":
            author = message.user.id
        else:
            author = message.author.id
        try:
            chat_model_status = self.chat_model
            if self.chat_model == "UNOFFICIAL":
                chat_model_status = f'ChatGPT {self.openAI_gpt_engine}'
            elif self.chat_model == "OFFICIAL":
                chat_model_status = f'OpenAI {self.openAI_gpt_engine}'
            response = (f'> **{user_message}** - <@{str(author)}> ({chat_model_status}) \n\n')
            if self.chat_model == "OFFICIAL":
                response = f"{response}{await responses.official_handle_response(user_message, self)}"
            elif self.chat_model == "UNOFFICIAL":
                response = f"{response}{await responses.unofficial_handle_response(user_message, self)}"
            elif self.chat_model == "Bard":
                response = f"{response}{await responses.bard_handle_response(user_message, self)}"
            elif self.chat_model == "Bing":
                response = f"{response}{await responses.bing_handle_response(user_message, self)}"
            char_limit = 1900
            if len(response) > char_limit:
                # Split the response into smaller chunks of no more than 1900 characters each(Discord limit is 2000 per chunk)
                if "```" in response:
                    # Split the response if the code block exists
                    parts = response.split("```")

                    for i in range(len(parts)):
                        if i%2 == 0: # indices that are even are not code blocks
                            if self.is_replying_all == "True":
                                await message.channel.send(parts[i])
                            else:
                                await message.followup.send(parts[i])
                        else: # Odd-numbered parts are code blocks
                            code_block = parts[i].split("\n")
                            formatted_code_block = ""
                            for line in code_block:
                                while len(line) > char_limit:
                                    # Split the line at the 50th character
                                    formatted_code_block += line[:char_limit] + "\n"
                                    line = line[char_limit:]
                                formatted_code_block += line + "\n"  # Add the line and seperate with new line

                            # Send the code block in a separate message
                            if (len(formatted_code_block) > char_limit+100):
                                code_block_chunks = [formatted_code_block[i:i+char_limit]
                                                    for i in range(0, len(formatted_code_block), char_limit)]
                                for chunk in code_block_chunks:
                                    if self.is_replying_all == "True":
                                        await message.channel.send(f"```{chunk}```")
                                    else:
                                        await message.followup.send(f"```{chunk}```")
                            elif self.is_replying_all == "True":
                                await message.channel.send(f"```{formatted_code_block}```")
                            else:
                                await message.followup.send(f"```{formatted_code_block}```")
                else:
                    response_chunks = [response[i:i+char_limit]
                                    for i in range(0, len(response), char_limit)]
                    for chunk in response_chunks:
                        if self.is_replying_all == "True":
                            await message.channel.send(chunk)
                        else:
                            await message.followup.send(chunk)
            elif self.is_replying_all == "True":
                await message.channel.send(response)
            else:
                await message.followup.send(f"{response}")
        except Exception as e:
            if self.is_replying_all == "True":
                await message.channel.send(f"> **ERROR: Something went wrong, please try again later!** \n ```ERROR MESSAGE: {e}```")
            else:
                await message.followup.send(f"> **ERROR: Something went wrong, please try again later!** \n ```ERROR MESSAGE: {e}```")
            logger.exception(f"Error while sending message: {e}")

    async def send_start_prompt(self):
        import os.path

        config_dir = os.path.abspath(f"{__file__}/../../")
        prompt_name = 'system_prompt.txt'
        prompt_path = os.path.join(config_dir, prompt_name)
        discord_channel_id = os.getenv("DISCORD_CHANNEL_ID")
        try:
            if os.path.isfile(prompt_path) and os.path.getsize(prompt_path) > 0:
                with open(prompt_path, "r", encoding="utf-8") as f:
                    prompt = f.read()
                    if (discord_channel_id):
                        logger.info(f"Send system prompt with size {len(prompt)}")
                        response = ""
                        if self.chat_model == "OFFICIAL":
                            response = f"{response}{await responses.official_handle_response(prompt, self)}"
                        elif self.chat_model == "UNOFFICIAL":
                            embed=discord.Embed(description="Status: Operational ✅", color=0xee2bde)
                            embed.add_field(name="`/help` ", value="for the commands list :pencil:", inline=False)
                            embed.add_field(name="`/chat`", value="to start a prompt :incoming_envelope:", inline=True)
                            embed.add_field(name="`/reset`", value="to clear my memory :wastebasket:", inline=True)
                            
                            # Add the footer to the embed
                            current_time = datetime.now().strftime("%m-%d-%Y %H:%M")
                            embed.set_footer(text=f"{current_time}")  

                            channel = self.get_channel(int(discord_channel_id))
                            await channel.send(embed=embed)  # Send the embed message

                            #response = f"{response}{await responses.unofficial_handle_response(prompt, self)}"
                        elif self.chat_model == "Bard":
                            response = f"{response}{await responses.bard_handle_response(prompt, self)}"
                        elif self.chat_model == "Bing":
                            response = f"{response}{await responses.bing_handle_response(prompt, self)}"
                        if response:  # Check if the response is not empty
                            channel = self.get_channel(int(discord_channel_id))
                            await channel.send(response)
                            logger.info(f"System prompt response:{response}")
                    else:
                        logger.info("No Channel selected. Skip sending system prompt.")
            else:
                logger.info(f"No {prompt_name}. Skip sending system prompt.")
        except Exception as e:
            logger.exception(f"Error while sending system prompt: {e}")

    async def get_woman(self):
        if self.img_api_model == "UNSPLASH":
            response = requests.get(self.unsplash_api_url)
            if response.status_code == 200:
                data = response.json()
                return data['urls']['regular']
            else:
                return None
        elif self.img_api_model == "PEXELS":
            headers = {
                'Authorization': f'{self.pexels_access_key}'
            }
            response = requests.get(f'{self.pexels_api_url}&page={random.randint(1, 100)}&per_page=10', headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data['photos'][random.randint(0, 9)]['src']['original']
            else:
                logger.info('Error response status code')
                return None
        else:
            logger.info('Error img model')
            return None

    async def get_leaderboard(self):
        return get_leaderboard(self.conn)

    async def get_rank(self, rep):
        return get_rank(rep)

    async def get_user_count(self, user_id):
        return get_user_count(self.conn, user_id)

client = aclient()
