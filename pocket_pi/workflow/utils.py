import os
import json
from dotenv import load_dotenv
from rich.console import Console

# Load environment keys
load_dotenv()

console = Console()

def call_llm(
    provider: str,
    model: str,
    messages: list,
    system_prompt: str,
    tools: list,
    thinking_level: str = "medium",
    thinking_budget: int = 10240
) -> dict:
    """
    Unified caller for Anthropic & OpenAI supporting tool call bindings.
    """
    if provider == "anthropic":
        res = _call_anthropic(model, messages, system_prompt, tools, thinking_level, thinking_budget)
    elif provider in ("openai", "openrouter"):
        res = _call_openai(provider, model, messages, system_prompt, tools)
    else:
        # Fallback
        raise ValueError(f"Unknown model provider: {provider}")

    # Standardize <think> tag extractions (extremely common on OpenRouter/DeepSeek reasoning models)
    import re
    text_val = res.get("text", "")
    if "<think>" in text_val and "</think>" in text_val:
        pattern = re.compile(r'<think>(.*?)</think>', re.DOTALL)
        match = pattern.search(text_val)
        if match:
            extracted_thinking = match.group(1).strip()
            stripped_text = pattern.sub('', text_val).strip()
            res["text"] = stripped_text
            res["thinking"] = (res.get("thinking") or "") + "\n" + extracted_thinking
            res["thinking"] = res["thinking"].strip()

    return res

def _call_anthropic(
    model: str,
    messages: list,
    system_prompt: str,
    tools: list,
    thinking_level: str,
    thinking_budget: int
) -> dict:
    import anthropic
    
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError("Missing ANTHROPIC_API_KEY environment variable. Run /login or set it in your environment.")
        
    client = anthropic.Anthropic(api_key=api_key)
    
    # Map messages safely to Anthropic API formats
    # Note: Anthropic system prompt is passed as a top-level parameter
    anthropic_messages = []
    for msg in messages:
        role = msg["role"]
        if role == "system":
            # Anthropic doesn't allow 'system' messages in the message list
            continue
        anthropic_messages.append({
            "role": role,
            "content": msg["content"]
        })
        
    formatted_tools = []
    for t in tools:
        formatted_tools.append({
            "name": t["name"],
            "description": t["description"],
            "input_schema": t["input_schema"]
        })
        
    # Standard parameters
    params = {
        "model": model,
        "max_tokens": 40000 if "claude-3-7" in model else 4096,
        "system": system_prompt,
        "messages": anthropic_messages,
        "tools": formatted_tools
    }
    
    # Gracefyl max token bounding correction
    if "claude-3-7" in model:
        params["max_tokens"] = 64000
    else:
        params["max_tokens"] = 4096
        
    # Inject Thinking limits if using Claude 3.7+ and thinking is not turned off
    # Anthropic requires max_tokens to be greater than thinking.budget_tokens
    if "claude-3-7" in model and thinking_level != "off":
        params["thinking"] = {
            "type": "enabled",
            "budget_tokens": thinking_budget
        }
        # Buffer max_tokens appropriately
        params["max_tokens"] = max(params["max_tokens"], thinking_budget + 4096)
        
    try:
        response = client.messages.create(**params)
        
        # Parse return content
        text_content = ""
        thinking_content = ""
        tool_calls = []
        
        for block in response.content:
            if block.type == "text":
                text_content += block.text
            elif block.type == "thinking":
                thinking_content += block.thinking
            elif block.type == "tool_use":
                tool_calls.append({
                    "id": block.id,
                    "name": block.name,
                    "arguments": block.input
                })
                
        # Parse usage details
        usage = {
            "input": 0,
            "output": 0,
            "totalTokens": 0
        }
        if hasattr(response, "usage") and response.usage is not None:
            inp = getattr(response.usage, "input_tokens", 0) or 0
            out = getattr(response.usage, "output_tokens", 0) or 0
            usage = {
                "input": inp,
                "output": out,
                "totalTokens": inp + out
            }
        
        return {
            "text": text_content,
            "thinking": thinking_content,
            "tool_calls": tool_calls,
            "usage": usage
        }
    except Exception as e:
        console.print(f"[red]Anthropic LLM call failed: {e}[/red]")
        raise e

def _call_openai(
    provider: str,
    model: str,
    messages: list,
    system_prompt: str,
    tools: list
) -> dict:
    import openai
    
    if provider == "openrouter":
        api_key = os.environ.get("OPENROUTER_API_KEY") or os.environ.get("OPENAI_API_KEY")
        base_url = "https://openrouter.ai/api/v1"
    else:
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = None
        
    if not api_key:
        raise ValueError(f"Missing API key for provider '{provider}'. Please run /login or set OPENAI_API_KEY/OPENROUTER_API_KEY in your environment.")
        
    client = openai.OpenAI(api_key=api_key, base_url=base_url)
    
    # Format messages
    openai_messages = [{"role": "system", "content": system_prompt}]
    for msg in messages:
        openai_messages.append(msg)
        
    # Format tools to openai schemes format
    formatted_tools = []
    for t in tools:
        formatted_tools.append({
            "type": "function",
            "function": {
                "name": t["name"],
                "description": t["description"],
                "parameters": t["input_schema"]
            }
        })
        
    params = {
        "model": model,
        "messages": openai_messages,
    }
    if formatted_tools:
        params["tools"] = formatted_tools
        
    # Adjust parameters for reasoning models (o1/o3-mini)
    # Note: Reasoning models sometimes do not support system messages or have limited tool support on standard completions
    is_reasoning_model = "o1" in model or "o3" in model
    if is_reasoning_model:
        # Standard system prompts are sometimes injected differently or reasoning efforts are used.
        # Ensure compatible formats:
        pass
        
    try:
        response = client.chat.completions.create(**params)
        choice = response.choices[0]
        msg = choice.message
        
        text_content = msg.content or ""
        tool_calls = []
        
        if msg.tool_calls:
            for tc in msg.tool_calls:
                # Resolve args safely
                args_dict = {}
                try:
                    args_dict = json.loads(tc.function.arguments)
                except Exception:
                    pass
                tool_calls.append({
                    "id": tc.id,
                    "name": tc.function.name,
                    "arguments": args_dict
                })
                
        usage = {
            "input": 0,
            "output": 0,
            "totalTokens": 0
        }
        if hasattr(response, "usage") and response.usage is not None:
            usage = {
                "input": getattr(response.usage, "prompt_tokens", 0) or 0,
                "output": getattr(response.usage, "completion_tokens", 0) or 0,
                "totalTokens": getattr(response.usage, "total_tokens", 0) or 0
            }
        
        reasoning = getattr(msg, "reasoning_content", None)
        if not reasoning and hasattr(msg, "model_extra") and isinstance(msg.model_extra, dict):
            reasoning = msg.model_extra.get("reasoning_content")
            
        return {
            "text": text_content,
            "thinking": reasoning or "",
            "tool_calls": tool_calls,
            "usage": usage
        }
    except Exception as e:
        console.print(f"[red]OpenAI LLM call failed: {e}[/red]")
        raise e
