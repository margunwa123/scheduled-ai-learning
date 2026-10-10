# test_gemini.py
from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client()  # picks up GEMINI_API_KEY from the environment

interaction = client.interactions.create(
    model="gemini-3.8-flash",
    input="In one sentence, confirm you're working.",
)
print(interaction.output_text)