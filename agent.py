import json
import os
import requests
import subprocess
import time

LLAMA_SERVER = os.environ.get("LLAMA_SERVER", "http://172.30.84.6:8000/v1")
MODEL = "qwen3-coder:30b"
PROJECT_DIR = os.environ.get("PARLIAMENT_DIR", os.getcwd())
MAX_TURNS = 15

# ---------------------------------------------------------------------------
# TOOLS
# ---------------------------------------------------------------------------

def list_files(path: str) -> str:
    # Constrain to project directory
    full_path = os.path.normpath(os.path.join(PROJECT_DIR, path))
    if not full_path.startswith(os.path.normpath(PROJECT_DIR)):
        return "Error: path outside project directory"
    return json.dumps(os.listdir(full_path))


def read_file(path: str) -> str:
    full_path = os.path.normpath(os.path.join(PROJECT_DIR, path))
    norm_project = os.path.normpath(PROJECT_DIR)
    if not full_path.startswith(norm_project):
        return "Error: path outside project directory"
    with open(full_path, 'r') as f:
        return f.read()

def write_file(path: str, content: str) -> str:
    full_path = os.path.normpath(os.path.join(PROJECT_DIR, path))
    if not full_path.startswith(os.path.normpath(PROJECT_DIR)):
        return "Error: path outside project directory"
    os.makedirs(os.path.dirname(full_path), exist_ok=True)
    with open(full_path, 'w') as f:
        f.write(content)
    return f"Written {len(content)} bytes to {path}"

def run_tests(module: str = None) -> str:
    # Run unittest — optionally targeting a specific module
    # The jail has no network access so pip etc won't work here
    cmd = ["python", "-m", "unittest"]
    if module:
        cmd.append(module)
    else:
        cmd.extend(["discover", "-s", ".", "-p", "test*.py"])

    result = subprocess.run(
        cmd,
        cwd=PROJECT_DIR,
        capture_output=True,
        text=True,
        timeout=120,
        # No shell=True — avoids shell injection
    )
    output = result.stdout + result.stderr
    return output if output else "No output from test runner"

TOOL_IMPLEMENTATIONS = {
    'list_files':  lambda args: list_files(args['path']),
    'read_file':   lambda args: read_file(args['path']),
    'write_file':  lambda args: write_file(args['path'], args['content']),
    'run_tests':   lambda args: run_tests(args.get('module')),
}

TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory within the project",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path within project"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file within the project",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path within project"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Write or overwrite a file within the project",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path within project"},
                    "content": {"type": "string", "description": "File content to write"}
                },
                "required": ["path", "content"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "run_tests",
            "description": "Run unittest tests. Optionally target a specific test module.",
            "parameters": {
                "type": "object",
                "properties": {
                    "module": {
                        "type": "string",
                        "description": "Optional specific test module e.g. tests.test_parser"
                    }
                },
                "required": []
            }
        }
    },
]

# ---------------------------------------------------------------------------
# LLM + AGENT LOOP
# (same pattern as ebi-agent — no changes needed here)
# ---------------------------------------------------------------------------

def chat(messages: list) -> dict:
    response = requests.post(
        f"{LLAMA_SERVER}/chat/completions",
        json={
            "model": MODEL,
            "messages": messages,
            "tools": TOOL_DEFINITIONS,
            "stream": False,
        },
        headers={"Authorization": "Bearer EMPTY"},
        timeout=1200,
    )
    response.raise_for_status()
    return response.json()

def dispatch_tool_call(tool_call: dict) -> str:
    name = tool_call['function']['name']
    args = tool_call['function']['arguments']
    if isinstance(args, str):
        args = json.loads(args)
    if name not in TOOL_IMPLEMENTATIONS:
        return f"Error: unknown tool {name}"
    try:
        return TOOL_IMPLEMENTATIONS[name](args)
    except Exception as e:
        return f"Error executing {name}: {e}"

def run_agent(user_message: str):
    messages = [
        {
            "role": "system",
            "content": (
                "You are a coding assistant working on the Parliament Python project. "
                "You can read and write files within the project directory and run unittest tests. "
                "You cannot files outside the project. "
                "Always run tests after making changes to verify correctness."
            )
        },
        {
            "role": "user",
            "content": user_message
        }
    ]

    for turn in range(MAX_TURNS):
        print(f"\n--- Turn {turn + 1} ---")
        total_chars = sum(len(str(m.get('content', ''))) for m in messages)
        print(f"Approximate context size: {total_chars} chars (~{total_chars//4} tokens)")
        last_content = str(messages[-1].get('content', ''))[:200]
        print(f"Last message: {last_content}")
        t0 = time.time()
        response = chat(messages)
        print(f"Model response time: {time.time() - t0:.1f}s")
        message = response['choices'][0]['message']
        finish_reason = response['choices'][0]['finish_reason']
        print(f"Finish reason: {finish_reason}")
        messages.append(message)

        if finish_reason == 'stop' or not message.get('tool_calls'):
            print(f"\nFinal response:\n{message.get('content', '')}")
            return message.get('content', '')

        for tool_call in message.get('tool_calls', []):
            tool_name = tool_call['function']['name']
            print(f"Calling tool: {tool_name}")
            result = dispatch_tool_call(tool_call)
            print(f"Result: {result[:200]}")
            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.get('id', f"call_{tool_name}"),
                "content": result
            })

    print("Max turns reached")
    return None

if __name__ == '__main__':
    import sys
    query = ' '.join(sys.argv[1:]) if len(sys.argv) > 1 else \
        "List the project files and run the test suite. Report what you find."
    run_agent(query)



