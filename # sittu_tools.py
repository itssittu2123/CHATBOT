# sittu_tools.py
import os
import json
import urllib.request
import urllib.parse
from dotenv import load_dotenv

# 1. Environment variables load karna (.env file se)
load_dotenv()

api_key = os.getenv("OPENAI_API_KEY")
ollama_url = os.getenv("OLLAMA_URL", "http://localhost:11434")
ollama_model = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

def check_tools_status():
    print("--- Sittu AI Tools Status ---")
    if api_key:
        print(" OpenAI API Key: Successfully Loaded!")
    else:
        print(" OpenAI API Key: Not Found (Fallback mode)")
        
    print(f" Ollama URL: {ollama_url}")
    print(f" Ollama Model: {ollama_model}")

#2. Urllib aur Parsing ka basic setup template
def sample_search_tool(query):
    print(f"Searching for: {query} using urllib...")
    # Yahan urllib ya network request ka logic likh sakte hain
    encoded_query = urllib.parse.quote(query)
    print(f"Encoded query URL ready: {encoded_query}")

if __name__ == "__main__":
    check_tools_status()
    print("\nTools script successfully executed!")