#!/usr/bin/env python3
"""
Interactive Menu CLI for Bare Metal Agent
- Arrow key navigation and keyboard shortcuts
- Colors and formatted output
- Task history with timestamps
- Multiple models and providers
"""

import os
import sys
import subprocess
import json
import termios
import tty
from pathlib import Path
from datetime import datetime

SCRIPT_DIR = Path(__file__).parent.resolve()
HISTORY_FILE = SCRIPT_DIR / '.menu_history.json'

# ANSI Colors
class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    DIM = '\033[2m'
    CYAN = '\033[36m'
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    RED = '\033[31m'
    BLUE = '\033[34m'
    MAGENTA = '\033[35m'
    WHITE = '\033[37m'


class MenuSystem:
    def __init__(self):
        self.providers = {
            'ollama': {
                'label': 'Ollama (Local/Cloud)',
                'desc': 'Fast local & cloud models',
                'models': {
                    # ☁️  CLOUD MODELS (verified, production stable)
                    'glm-5.1-cloud': '☁️  GLM 5.1 • 1.5TB • Agentic flagship',
                    'glm-5-cloud': '☁️  GLM 5 • 756GB • Reasoning engine',
                    'glm-4.7-cloud': '☁️  GLM 4.7 • 696GB • Strong coder',
                    'kimi-k2.6-cloud': '☁️  Kimi K2.6 • 595GB • Multimodal',
                    'kimi-k2.5-cloud': '☁️  Kimi K2.5 • 1.1TB • Vision + thinking',
                    'minimax-m2.7-cloud': '☁️  MiniMax M2.7 • 481GB • Agentic',
                    'minimax-m2.5-cloud': '☁️  MiniMax M2.5 • 230GB • Coding',
                    'devstral-2-cloud': '☁️  Devstral-2 • 128GB • 123B eng',
                    'deepseek-v3.2-cloud': '☁️  DeepSeek V3.2 • 689GB • MoE',
                    'mistral-large-3-cloud': '☁️  Mistral Large • 682GB • Prod',
                    'gemma4-cloud': '☁️  Gemma 4 • 62GB • Vision + code',
                    'nemotron-3-super-cloud': '☁️  Nemotron 3 • 230GB • MoE agent',
                    
                    # 💻 LOCAL MODELS (run offline)
                    'llama3.2:latest': '💻 Llama 3.2 • 2GB • General ⭐',
                    'llama3.1:latest': '💻 Llama 3.1 • 4GB • Strong',
                    'gemma3:27b': '💻 Gemma 3 • 55GB • Efficient',
                    'mistral:latest': '💻 Mistral 7B • Fast',
                    'neural-chat:7b': '💻 Neural Chat • 4GB • Conv',
                    'ministral-3:8b': '💻 Ministral 3 • 10GB • Balanced',
                    'qwen3.5:0.8b': '💻 Qwen 3.5 0.8B • 1GB • Ultra-lite',
                    'functiongemma:latest': '💻 FunctionGemma • 300MB',
                    'tinyllama:1.1b': '💻 TinyLlama • 1.1B • Minimal',
                    'deepseek-r1:8b': '💻 DeepSeek-R1 • Reasoning',
                    'phi4-reasoning:14b': '💻 Phi-4 Reasoning • Math',
                    'llama3.2-vision:11b': '💻 Llama Vision • Image',
                    'moondream:1.8b': '💻 Moondream • Edge vision',
                    'codellama:34b': '💻 Code Llama • Code gen',
                    'devstral-small-2:24b': '💻 Devstral Small • 51GB',
                    'rnj-1:8b': '💻 RNJ-1 • Coding + STEM',
                }
            },
            'claude': {
                'label': 'Claude Code CLI',
                'desc': 'Claude via OAuth (Pro subscription)',
                'models': {
                    'sonnet': 'Claude Sonnet (default)',
                    'opus': 'Claude 3 Opus',
                }
            },
            'anthropic': {
                'label': 'Anthropic API',
                'desc': 'Direct API (needs ANTHROPIC_API_KEY)',
                'models': {
                    'claude-sonnet-4-20250514': 'Claude Sonnet 4',
                    'claude-opus-4-1-20250805': 'Claude 3 Opus',
                }
            }
        }
        self.history = self._load_history()

    def _load_history(self):
        """Load task history"""
        if HISTORY_FILE.exists():
            try:
                with open(HISTORY_FILE) as f:
                    return json.load(f)
            except:
                return []
        return []

    def _save_history(self, provider, model, task):
        """Save task to history"""
        self.history.append({
            'timestamp': datetime.now().isoformat(),
            'provider': provider,
            'model': model,
            'task': task
        })
        # Keep last 20 entries
        if len(self.history) > 20:
            self.history = self.history[-20:]
        try:
            with open(HISTORY_FILE, 'w') as f:
                json.dump(self.history, f, indent=2)
        except:
            pass

    def clear_screen(self):
        """Clear terminal"""
        os.system('clear' if os.name == 'posix' else 'cls')

    def display_header(self):
        """Show header with colors"""
        print(f'\n{Colors.BOLD}{Colors.CYAN}{"="*60}{Colors.RESET}')
        print(f'{Colors.BOLD}{Colors.CYAN}  🤖 BARE METAL AGENT{Colors.RESET}')
        print(f'{Colors.BOLD}{Colors.CYAN}{"="*60}{Colors.RESET}\n')

    def getch_unix(self):
        """Read single char from stdin (Unix/Linux)"""
        if os.name != 'posix':
            return sys.stdin.read(1)
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
        return ch

    def show_menu(self, title, options, descs=None):
        """Display interactive menu with arrow key navigation"""
        selected = 0
        
        while True:
            self.clear_screen()
            self.display_header()
            print(f"{Colors.BOLD}{Colors.YELLOW}📋 {title}{Colors.RESET}\n")
            
            for i, option in enumerate(options):
                if i == selected:
                    marker = f"{Colors.GREEN}▶{Colors.RESET}"
                    line = f"{Colors.BOLD}{Colors.GREEN}{option}{Colors.RESET}"
                else:
                    marker = f"{Colors.DIM} {Colors.RESET}"
                    line = f"{Colors.DIM}{option}{Colors.RESET}"
                
                desc = f" — {Colors.DIM}{descs[i]}{Colors.RESET}" if descs and i < len(descs) else ""
                print(f"{marker} [{i+1}] {line}{desc}")
            
            # Show recent history
            if self.history and 'Select' in title:
                print(f"\n{Colors.DIM}┌─ Recent ─{Colors.RESET}")
                for task in self.history[-2:]:
                    dt = datetime.fromisoformat(task['timestamp']).strftime('%H:%M')
                    print(f"{Colors.DIM}│ [{dt}] {task['task'][:36]}{Colors.RESET}")
                print(f"{Colors.DIM}└─{Colors.RESET}")
            
            print(f"\n{Colors.BLUE}▲ ▼ = Navigate • Enter = Select • H = History • Q = Quit{Colors.RESET}")
            
            # Get input
            try:
                ch = self.getch_unix()
                if ch == '\x1b':
                    self.getch_unix()  # [
                    ch = self.getch_unix()
                    if ch == 'A':
                        selected = (selected - 1) % len(options)
                    elif ch == 'B':
                        selected = (selected + 1) % len(options)
                elif ch == '\r' or ch == '\n':
                    return selected
                elif ch.lower() == 'q':
                    print(f"\n{Colors.RED}✗ Exit{Colors.RESET}")
                    sys.exit(0)
                elif ch.lower() == 'h':
                    self._show_history()
                elif ch.isdigit():
                    idx = int(ch) - 1
                    if 0 <= idx < len(options):
                        return idx
            except:
                return self._simple_menu(title, options, descs)

    def _show_history(self):
        """Show task history"""
        if not self.history:
            self.clear_screen()
            self.display_header()
            print(f"{Colors.YELLOW}No history.{Colors.RESET}")
            return
        
        self.clear_screen()
        self.display_header()
        print(f"{Colors.BOLD}{Colors.MAGENTA}📜 Task History{Colors.RESET}\n")
        
        for i, task in enumerate(reversed(self.history[-10:]), 1):
            dt = datetime.fromisoformat(task['timestamp']).strftime('%H:%M')
            print(f"{Colors.DIM}[{dt}]{Colors.RESET} {Colors.CYAN}{task['provider']:<8}{Colors.RESET} {task['task'][:50]}")
        
        print(f"\n{Colors.DIM}─────────────────────────────────────────────{Colors.RESET}")


    def _simple_menu(self, title, options, descs=None):
        """Fallback menu using simple input"""
        while True:
            self.clear_screen()
            self.display_header()
            print(f"{Colors.YELLOW}{title}{Colors.RESET}\n")
            
            for i, option in enumerate(options, 1):
                desc = f" — {descs[i-1]}" if descs else ""
                print(f"  [{i}] {option}{desc}")
            
            print(f"\n{Colors.BLUE}Enter # or [Q]uit:${Colors.RESET} ", end='')
            choice = input().strip()
            
            if choice.lower() == 'q':
                sys.exit(0)
            elif choice.isdigit():
                idx = int(choice) - 1
                if 0 <= idx < len(options):
                    return idx

    def _direct_run(self, provider, model, task):
        """Run agent directly without menu (for CLI args)"""
        try:
            # Validate provider exists
            if provider not in self.providers:
                print(f"{Colors.RED}✗ Unknown provider: {provider}{Colors.RESET}")
                sys.exit(1)
            
            # Validate model exists
            models_dict = self.providers[provider]['models']
            if model not in models_dict:
                print(f"{Colors.RED}✗ Unknown model for {provider}: {model}{Colors.RESET}")
                print(f"Available: {', '.join(list(models_dict.keys())[:5])}...")
                sys.exit(1)
            
            # Save history and run
            self._save_history(provider, model, task)
            self._execute_agent(provider, model, task)
        
        except Exception as e:
            print(f"{Colors.RED}✗ Error: {e}{Colors.RESET}")
            sys.exit(1)

    def _execute_agent(self, provider, model, task):
        """Execute the agent"""
        cmd = ['python3', 'agent.py', '--provider', provider, '--model', model, task]
        env = os.environ.copy()
        
        print(f"{Colors.GREEN}✓ Starting agent...{Colors.RESET}\n")
        print('='*60 + '\n')
        result = subprocess.run(cmd, cwd=SCRIPT_DIR, env=env)
        sys.exit(result.returncode)

    def run(self):
        """Run the menu system"""
        try:
            # Select Provider
            provider_names = list(self.providers.keys())
            provider_labels = [self.providers[p]['label'] for p in provider_names]
            provider_descs = [self.providers[p]['desc'] for p in provider_names]
            
            provider_idx = self.show_menu("🖥️  Select Provider", provider_labels, provider_descs)
            provider = provider_names[provider_idx]
            
            # Select Model
            models_dict = self.providers[provider]['models']
            model_names = list(models_dict.keys())
            model_descs = list(models_dict.values())
            
            model_idx = self.show_menu("🧠 Select Model", model_names, model_descs)
            model = model_names[model_idx]
            
            # Get Task
            self.clear_screen()
            self.display_header()
            print(f"{Colors.BOLD}{Colors.YELLOW}📝 Enter Your Task{Colors.RESET}\n")
            print("Examples:")
            print("  • scan wifi networks on wlan1")
            print("  • write security report for this machine")
            print("  • crack Fiber 4K-1100 network\n")
            print(f"{Colors.BLUE}Task:${Colors.RESET} ", end='')
            task = input().strip()
            
            if not task:
                print(f"{Colors.RED}✗ No task.{Colors.RESET}")
                return
            
            # Auto-start (no confirmation)
            self._save_history(provider, model, task)
            self._execute_agent(provider, model, task)
        
        except KeyboardInterrupt:
            print(f"\n{Colors.RED}✗ Interrupted.{Colors.RESET}")
            sys.exit(1)



if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Bare Metal Agent CLI')
    parser.add_argument('--provider', help='Provider: ollama, claude, anthropic')
    parser.add_argument('--model', help='Model name')
    parser.add_argument('--yes', '-y', action='store_true', help='Skip confirmations')
    parser.add_argument('task', nargs='?', help='Task to execute')
    
    args = parser.parse_args()
    
    menu = MenuSystem()
    
    # Direct mode: bypass menu if all args provided
    if args.provider and args.model and args.task:
        menu._direct_run(args.provider, args.model, args.task)
    else:
        menu.run()
