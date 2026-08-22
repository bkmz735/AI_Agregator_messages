import os
import re

files_to_update = [
    "C:/Users/BKMZ/.gemini/antigravity-ide/scratch/ai-message-aggregator/ai_engine.py",
    "C:/Users/BKMZ/.gemini/antigravity-ide/scratch/ai-message-aggregator/main.py",
    "C:/Users/BKMZ/.gemini/antigravity-ide/scratch/ai-message-aggregator/config.py",
    "C:/Users/BKMZ/.gemini/antigravity-ide/scratch/ai-message-aggregator/user_agent.py"
]

def replace_in_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Replacements
    content = content.replace("GEMINI_API_KEY", "AI_API_KEY")
    content = content.replace("Gemini API", "AI API")
    content = content.replace("Gemini model", "AI model")
    content = content.replace("Gemini Free Tier", "AI Free Tier")
    content = content.replace("Gemini domains", "AI domains")
    content = content.replace("Gemini client", "AI client")
    content = content.replace("Gemini multimodal", "AI multimodal")
    content = content.replace("Gemini accuracy", "AI accuracy")
    content = content.replace("Gemini spam", "AI spam")
    content = content.replace("via Gemini", "via AI API")
    content = content.replace("from Gemini", "from AI")
    content = content.replace("by Gemini", "by AI")
    content = content.replace("using Gemini", "using AI")
    content = content.replace("for Gemini", "for AI")
    content = content.replace("Gemini", "AI") # Catch all remaining capitalized
    # We must fix back the model names to not break the API calls
    content = content.replace("AI-3", "gemini-3") 
    content = content.replace("AI-2", "gemini-2")
    content = content.replace("AI-1", "gemini-1")
    content = content.replace("gemini-3.5", "gemini-3.5")
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(content)

for filepath in files_to_update:
    if os.path.exists(filepath):
        replace_in_file(filepath)
        print(f"Updated {filepath}")
    else:
        print(f"Missing {filepath}")
