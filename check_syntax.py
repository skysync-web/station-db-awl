import ast, sys
try:
    with open(r"C:\Users\HP\Desktop\Claude Workspace\Station DB AWL Generation\Source\app.py", encoding="utf-8") as f:
        ast.parse(f.read())
    print("Syntax OK")
except SyntaxError as e:
    print(f"Syntax Error: {e}")
    sys.exit(1)
