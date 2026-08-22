import ast

with open('C:/Users/BKMZ/.gemini/antigravity-ide/scratch/ai-message-aggregator/master_bot.py', 'r', encoding='utf-8') as f:
    tree = ast.parse(f.read())
    
print("Classes and Functions:")
for node in tree.body:
    if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
        print(f"{type(node).__name__}: {node.name}")
        if isinstance(node, ast.ClassDef):
            for subnode in node.body:
                if isinstance(subnode, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    print(f"  - {subnode.name}")
