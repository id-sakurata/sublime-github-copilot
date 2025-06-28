import sublime
import sublime_plugin
import threading
import json
import urllib.request
import urllib.parse
import webbrowser
import time
import html
import glob
import re
import os
from datetime import datetime

# Constants
CLIENT_ID = "01ab8ac9400c4e429b23"
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_API_URL = "https://api.github.com/user"
COPILOT_API_URL = "https://api.githubcopilot.com/chat/completions"
COPILOT_MODELS_URL = "https://api.githubcopilot.com/v1/models"

class GithubCopilotCommand(sublime_plugin.WindowCommand):
    def __init__(self, window):
        super().__init__(window)
        self.access_token = None
        self.username = None
        self.chat_view = None
        self.chat_history = []
        self.settings = sublime.load_settings("github_copilot.sublime-settings")
        self.chat_panel_visible = False
        self.original_layout = None
        self.load_settings()

    # <--- PERBAIKAN: Method yang hilang dikembalikan ---
    @classmethod
    def get_instance(cls, window):
        """Get or create instance for window"""
        if not hasattr(cls, '_instances'):
            cls._instances = {}
        if window.id() not in cls._instances:
            cls._instances[window.id()] = cls(window)
        return cls._instances[window.id()]
    # --- Akhir Perbaikan ---

    def load_settings(self):
        """Load saved access token and other settings"""
        self.access_token = self.settings.get("access_token")
        self.username = self.settings.get("username")

    def save_setting(self, key, value):
        self.settings.set(key, value)
        sublime.save_settings("github_copilot.sublime-settings")

    def clear_token(self):
        """Clear saved access token and username"""
        self.access_token = None
        self.username = None
        self.settings.erase("access_token")
        self.settings.erase("username")
        sublime.save_settings("github_copilot.sublime-settings")

    def prepare_chat_view(self):
        if not self.chat_view or not self.chat_view.is_valid():
            self.chat_view = self.window.new_file()
            self.chat_view.set_name("GitHub Copilot Chat")
            self.chat_view.set_scratch(True)
            self.chat_view.settings().set("word_wrap", True)
            self.chat_view.settings().set("line_numbers", False)
            self.chat_view.settings().set("gutter", False)
            self.chat_view.settings().set("scroll_past_end", True)
            self.chat_view.settings().set("font_size", 10)
            
        self.window.set_view_index(self.chat_view, 1, 0)
        self.window.focus_view(self.chat_view)
        self.chat_panel_visible = True
        
        if self.is_authenticated() and self.username:
            self.update_chat_view(f"=== GitHub Copilot Chat ===\nStatus: Authenticated as {self.username} ✓\nPress Ctrl+Shift+P and type 'GitHub Copilot: Send Message' to chat\n\n")
        elif self.is_authenticated():
             self.update_chat_view("=== GitHub Copilot Chat ===\nStatus: Authenticated ✓ (Run status check to see username)\nPress Ctrl+Shift+P and type 'GitHub Copilot: Send Message' to chat\n\n")
        else:
            self.update_chat_view("=== GitHub Copilot Chat ===\nStatus: Not authenticated ❌\nRun 'GitHub Copilot: Authenticate' to login\n\n")
        
        if self.is_authenticated():
            sublime.set_timeout(lambda: self.show_input_panel(), 100)

    def show_chat_panel(self):
        """Show chat panel in right column"""
        if not self.original_layout:
            self.original_layout = self.window.get_layout()
        
        self.window.run_command("set_layout", {
            "cols": [0.0, 0.6, 1.0],
            "rows": [0.0, 1.0],
            "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]
        })

        # Delay untuk memastikan layout siap
        sublime.set_timeout(lambda: self.prepare_chat_view(), 100)

    def hide_chat_panel(self):
        """Hide chat panel and restore original layout"""
        if self.original_layout:
            self.window.run_command("set_layout", self.original_layout)
            self.original_layout = None
        if self.chat_view and self.chat_view.is_valid():
            self.chat_view.close()
            self.chat_view = None
        self.chat_panel_visible = False

    def toggle_chat_panel(self):
        """Toggle chat panel visibility"""
        if self.chat_panel_visible:
            self.hide_chat_panel()
        else:
            self.show_chat_panel()

    def update_chat_view(self, text, append=False):
        """Update chat view with text"""
        if self.chat_view and self.chat_view.is_valid():
            self.chat_view.set_read_only(False)
            if append:
                self.chat_view.run_command("append", {"characters": text})
            else:
                self.chat_view.run_command("select_all")
                self.chat_view.run_command("right_delete")
                self.chat_view.run_command("append", {"characters": text})
            self.chat_view.set_read_only(True)

    def is_authenticated(self):
        """Check if user has a token"""
        return self.access_token is not None

    def show_input_panel(self):
        """Show input panel for message"""
        if not self.is_authenticated():
            sublime.error_message("Please authenticate first using 'GitHub Copilot: Authenticate'")
            return
        
        self.window.show_input_panel(
            "Message to Copilot:", "",
            lambda message: self.send_message(message), None, None
        )

    def send_message(self, message):
        """Process and send the message"""
        message = message.strip()
        if not message:
            return

        file_contents = ""
        file_pattern = re.compile(r'file:\s*([^\s]+)', re.IGNORECASE)
        for filename in file_pattern.findall(message):
            abs_path = os.path.join(self.window.folders()[0], filename)
            if os.path.exists(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8") as f: content = f.read()
                    file_contents += f"\n\n# file: {filename}\n{content}\n"
                except Exception as e: file_contents += f"\n\n# file: {filename} (gagal dibaca: {e})\n"
            else: file_contents += f"\n\n# file: {filename} (tidak ditemukan)\n"

        dir_pattern = re.compile(r'dir:\s*([^\s]+)', re.IGNORECASE)
        for pattern in dir_pattern.findall(message):
            abs_pattern = os.path.join(self.window.folders()[0], pattern)
            for filepath in glob.glob(abs_pattern, recursive=True):
                if os.path.isfile(filepath):
                    rel_path = os.path.relpath(filepath, self.window.folders()[0])
                    try:
                        with open(filepath, "r", encoding="utf-8") as f: content = f.read()
                        file_contents += f"\n\n# file: {rel_path}\n{content}\n"
                    except Exception as e: file_contents += f"\n\n# file: {rel_path} (gagal dibaca: {e})\n"

        message_for_copilot = message + ("\n\n# Referensi file:\n" + file_contents if file_contents else "")
        
        timestamp = datetime.now().strftime("%H:%M:%S")
        user_msg = f"\n─────────────────────────────\n[{timestamp}] 👤 You:\n{message}\n"
        self.update_chat_view(user_msg, append=True)
        
        threading.Thread(target=self.send_to_copilot, args=(message_for_copilot,)).start()

    def send_to_copilot(self, message):
        """Send message to GitHub Copilot API"""
        try:
            base_prompt = self.settings.get("base_prompt_chat", "")
            messages = []
            if base_prompt:
                messages.append({"role": "system", "content": base_prompt})
            
            if len(self.chat_history) > 10:
                self.chat_history = self.chat_history[-10:]
            
            messages.extend(self.chat_history)
            messages.append({"role": "user", "content": message})
            
            self.start_typing_effect()
            
            selected_model = self.settings.get("selected_model", "gpt-4o")
            
            payload = {
                "model": selected_model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 1500,
                "stream": False
            }
            
            data = json.dumps(payload).encode()
            req = urllib.request.Request(COPILOT_API_URL, data=data)
            req.add_header('Authorization', f'Bearer {self.access_token}')
            req.add_header('Content-Type', 'application/json')
            req.add_header('Accept', 'application/json')
            req.add_header('User-Agent', 'GitHubCopilot/1.200.0.0 (sublime; 4169; x64)')

            with urllib.request.urlopen(req, timeout=45) as response:
                result = json.loads(response.read().decode())
                
                if 'choices' in result and result['choices']:
                    assistant_message = result['choices'][0]['message']['content']
                    self.chat_history.append({"role": "user", "content": message})
                    self.chat_history.append({"role": "assistant", "content": assistant_message})

                    self.stop_typing_effect()
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    formatted_response = self.format_response(assistant_message)
                    response_msg = f"\n─────────────────────────────\n[{timestamp}] 🤖 Copilot ({selected_model}):\n{formatted_response}\n"
                    sublime.set_timeout(lambda: self.update_chat_with_response(response_msg), 0)
                else:
                    raise Exception(f"Invalid response format: {result}")
                    
        except urllib.error.HTTPError as e:
            error_body = e.read().decode(errors='ignore') if hasattr(e, 'read') else str(e)
            error_msg = f"API Error: HTTP {e.code} - {error_body}\n"
            self.stop_typing_effect()
            sublime.set_timeout(lambda: self.update_chat_with_response(error_msg), 0)
        except Exception as e:
            self.stop_typing_effect()
            error_msg = f"Unexpected error: {str(e)}\n"
            sublime.set_timeout(lambda: self.update_chat_with_response(error_msg), 0)

    def format_response(self, response):
        """Format response with separators for code blocks"""
        if '```' in response:
            response = response.replace('```', '\n+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+\n')
        return response

    def start_typing_effect(self):
        """Start typing effect animation"""
        self.typing_active = True
        self.typing_dots = 0
        sublime.set_timeout(lambda: self.update_typing_indicator(), 0)

    def stop_typing_effect(self):
        """Stop typing effect animation"""
        self.typing_active = False

    def update_typing_indicator(self):
        """Update typing indicator with animation"""
        if not self.typing_active: return
        dots = "." * (self.typing_dots % 4)
        typing_text = f"Copilot is typing{dots}   "
        if self.chat_view and self.chat_view.is_valid():
            current_content = self.chat_view.substr(sublime.Region(0, self.chat_view.size()))
            lines = current_content.split('\n')
            found = False
            for i in range(len(lines) - 1, -1, -1):
                if 'typing' in lines[i]:
                    lines[i] = typing_text; found = True; break
            if not found:
                lines.append(typing_text)
                self.update_chat_view('\n'.join(lines))
                sublime.set_timeout(lambda: self.chat_view.show(self.chat_view.size()), 0)
            else:
                self.update_chat_view('\n'.join(lines))
        self.typing_dots += 1
        if self.typing_active:
            sublime.set_timeout(lambda: self.update_typing_indicator(), 500)
    
    def update_chat_with_response(self, response_text):
        """Update chat view removing typing indicator and adding response"""
        if self.chat_view and self.chat_view.is_valid():
            current_content = self.chat_view.substr(sublime.Region(0, self.chat_view.size()))
            lines = current_content.split('\n')
            if lines and 'typing' in lines[-1]: lines = lines[:-1]
            new_content = '\n'.join(lines) + '\n' + response_text
            self.chat_view.set_read_only(False)
            self.chat_view.run_command("replace_content_and_scroll", {"content": new_content})
            self.chat_view.set_read_only(True)
            sublime.set_timeout(lambda: self.show_input_panel(), 500)

class ReplaceContentAndScrollCommand(sublime_plugin.TextCommand):
    def run(self, edit, content):
        self.view.replace(edit, sublime.Region(0, self.view.size()), content)
        last_line = self.view.rowcol(self.view.size())[0]
        pt = self.view.text_point(last_line, 0)
        self.view.sel().clear(); self.view.sel().add(sublime.Region(pt, pt))
        self.view.show(pt)

class GithubCopilotAuthenticateCommand(sublime_plugin.WindowCommand):
    def run(self):
        copilot_cmd = GithubCopilotCommand.get_instance(self.window)
        if copilot_cmd.is_authenticated():
            sublime.message_dialog("Already authenticated. Run 'GitHub Copilot: Status Check' to verify.")
            return
        threading.Thread(target=self.authenticate_async, args=(copilot_cmd,)).start()

    def authenticate_async(self, copilot_cmd):
        try:
            device_data = self.get_device_code()
            if not device_data: sublime.error_message("Failed to get device code"); return

            device_code, user_code, verification_uri, interval = device_data['device_code'], device_data['user_code'], device_data['verification_uri'], device_data.get('interval', 5)
            sublime.set_clipboard(user_code)
            sublime.message_dialog(f"Opening browser...\nUser code: {user_code} (copied to clipboard)")
            webbrowser.open(verification_uri)

            for _ in range(60):
                time.sleep(interval)
                token_data = self.poll_for_token(device_code)
                if token_data and 'access_token' in token_data:
                    access_token = token_data['access_token']
                    copilot_cmd.save_setting("access_token", access_token)
                    copilot_cmd.load_settings()
                    sublime.message_dialog("Authentication successful! Verifying account...")
                    self.window.run_command("github_copilot_status_check") 
                    if copilot_cmd.chat_view and copilot_cmd.chat_view.is_valid():
                       copilot_cmd.show_chat_panel()
                    return
            sublime.error_message("Authentication timed out or failed.")
        except Exception as e:
            sublime.error_message(f"Authentication error: {str(e)}")

    def get_device_code(self):
        try:
            data = urllib.parse.urlencode({'client_id': CLIENT_ID, 'scope': 'copilot'}).encode()
            req = urllib.request.Request(GITHUB_DEVICE_CODE_URL, data=data)
            req.add_header('Accept', 'application/json')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            with urllib.request.urlopen(req) as response: return json.loads(response.read().decode())
        except Exception as e: print(f"Error getting device code: {e}"); return None

    def poll_for_token(self, device_code):
        try:
            data = urllib.parse.urlencode({'client_id': CLIENT_ID, 'device_code': device_code, 'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'}).encode()
            req = urllib.request.Request(GITHUB_TOKEN_URL, data=data)
            req.add_header('Accept', 'application/json')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            with urllib.request.urlopen(req) as response: return json.loads(response.read().decode())
        except Exception as e: return {'error': str(e)}

class GithubCopilotLogoutCommand(sublime_plugin.WindowCommand):
    def run(self):
        copilot_cmd = GithubCopilotCommand.get_instance(self.window)
        copilot_cmd.clear_token()
        if copilot_cmd.chat_view and copilot_cmd.chat_view.is_valid():
            copilot_cmd.update_chat_view("=== GitHub Copilot Chat ===\nStatus: Logged out ❌\nRun 'GitHub Copilot: Authenticate' to login\n\n")
        sublime.message_dialog("Logged out from GitHub Copilot.")

class GithubCopilotStatusCheckCommand(sublime_plugin.WindowCommand):
    def run(self):
        copilot_cmd = GithubCopilotCommand.get_instance(self.window)
        if not copilot_cmd.is_authenticated():
            sublime.message_dialog("GitHub Copilot: Not authenticated ❌")
            return
        sublime.status_message("Checking GitHub Copilot authentication status...")
        threading.Thread(target=self.check_status_async, args=(copilot_cmd,)).start()

    def check_status_async(self, copilot_cmd):
        try:
            req = urllib.request.Request(GITHUB_USER_API_URL)
            req.add_header('Authorization', f'Bearer {copilot_cmd.access_token}')
            req.add_header('Accept', 'application/vnd.github.v3+json')
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    user_data = json.loads(response.read().decode())
                    username = user_data.get('login')
                    copilot_cmd.save_setting("username", username)
                    copilot_cmd.username = username
                    sublime.message_dialog(f"GitHub Copilot: Authenticated as '{username}' ✓")
                    if copilot_cmd.chat_view and copilot_cmd.chat_view.is_valid():
                        sublime.set_timeout(lambda: copilot_cmd.show_chat_panel(), 0)
                else:
                    sublime.error_message(f"GitHub API Error: Status {response.status}")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                sublime.error_message("GitHub Copilot: Authentication failed (Invalid Token) ❌. Please re-authenticate.")
                copilot_cmd.clear_token()
            else:
                sublime.error_message(f"GitHub Copilot: HTTP Error {e.code}")
        except Exception as e:
            sublime.error_message(f"Status Check Error: {e}")

class GithubCopilotFetchModelsCommand(sublime_plugin.WindowCommand):
    def run(self):
        copilot_cmd = GithubCopilotCommand.get_instance(self.window)
        if not copilot_cmd.is_authenticated():
            sublime.error_message("Please authenticate first.")
            return
        sublime.status_message("Fetching available models from GitHub Copilot...")
        threading.Thread(target=self.fetch_models_async, args=(copilot_cmd,)).start()

    def fetch_models_async(self, copilot_cmd):
        try:
            req = urllib.request.Request(COPILOT_MODELS_URL)
            req.add_header('Authorization', f'Bearer {copilot_cmd.access_token}')
            with urllib.request.urlopen(req) as response:
                if response.status == 200:
                    models_data = json.loads(response.read().decode())
                    model_ids = [m['id'] for m in models_data.get('data', []) if "gpt" in m['id']]
                    if model_ids:
                        copilot_cmd.save_setting('available_models', model_ids)
                        sublime.message_dialog(f"Successfully fetched {len(model_ids)} models.\nYou can now select one using 'GitHub Copilot: Select Model'.")
                    else:
                        sublime.error_message("No compatible models found in the response.")
                else:
                    sublime.error_message(f"Failed to fetch models: Status {response.status}")
        except Exception as e:
            sublime.error_message(f"Error fetching models: {e}")

class GithubCopilotSelectModelCommand(sublime_plugin.WindowCommand):
    def run(self):
        copilot_cmd = GithubCopilotCommand.get_instance(self.window)
        available_models = copilot_cmd.settings.get('available_models', [])
        if not available_models:
            sublime.error_message("No available models found. Please run 'GitHub Copilot: Fetch Available Models' first.")
            return

        def on_done(index):
            if index == -1: return
            selected = available_models[index]
            copilot_cmd.save_setting('selected_model', selected)
            sublime.message_dialog(f"Model set to: {selected}")

        self.window.show_quick_panel(available_models, on_done)


class GithubCopilotSendMessageCommand(sublime_plugin.WindowCommand):
    def run(self):
        copilot_cmd = GithubCopilotCommand.get_instance(self.window)
        if not copilot_cmd.is_authenticated():
            sublime.error_message("Please authenticate first.")
            return
        
        copilot_cmd.show_chat_panel()
        copilot_cmd.show_input_panel()

class GithubCopilotInlineEditCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        window = self.view.window()
        copilot_cmd = GithubCopilotCommand.get_instance(window)
        if not copilot_cmd.is_authenticated():
            sublime.error_message("Please authenticate first.")
            return

        sels = self.view.sel()
        if not sels or all(r.empty() for r in sels):
            sublime.error_message("Please select some text to edit.")
            return

        selected_text = "\n".join([self.view.substr(r) for r in sels if not r.empty()])
        self.phantom_set = sublime.PhantomSet(self.view, "copilot_inline_progress")

        def on_done(prompt):
            base_prompt = copilot_cmd.settings.get("base_prompt_inline_edit", "")
            full_prompt_content = f"{prompt}\n\n```\n{selected_text}\n```"
            
            messages = []
            if base_prompt:
                messages.append({"role": "system", "content": base_prompt})
            messages.append({"role": "user", "content": full_prompt_content})
            
            self.progress_active = True
            self.progress_dots = 0
            self.show_progress_phantom()
            self.animate_progress_phantom()

            threading.Thread(target=self.ask_copilot_and_replace, args=(messages, [ (r.a, r.b) for r in sels ])).start()

        window.show_input_panel("Prompt for Copilot (inline edit):", "", on_done, None, None)

    def show_progress_phantom(self):
        region = self.view.sel()[0]
        dots = "." * (self.progress_dots % 4)
        html = f'''
            <body id="copilot-inline-progress">
                <style>
                    #copilot-inline-progress .modal {{
                        background-color: color(var(--background) blend(#000 85%));
                        padding: 18px;
                        border-radius: 10px;
                        border: 1px solid var(--bluish);
                        text-align: center;
                        font-size: 1.1rem;
                        max-width: 400px;
                        margin: 8px auto;
                    }}
                </style>
                <div class="modal">
                    <small>Performing inline edit.</small><br>
                    <b>💡 Copilot is thinking{dots}</b>
                </div>
            </body>
        '''
        phantom = sublime.Phantom(region, html, sublime.LAYOUT_BLOCK)
        self.phantom_set.update([phantom])


    def animate_progress_phantom(self):
        if not getattr(self, "progress_active", False):
            return
        self.progress_dots += 1
        self.show_progress_phantom()
        sublime.set_timeout(self.animate_progress_phantom, 500)

    def clear_progress_phantom(self):
        self.progress_active = False
        if hasattr(self, "phantom_set"): self.phantom_set.update([])
    
    def ask_copilot_and_replace(self, messages, sel_ranges):
        window = self.view.window()
        copilot_cmd = GithubCopilotCommand.get_instance(window)
        try:
            selected_model = copilot_cmd.settings.get("selected_model", "gpt-4o")
            payload = {
                "model": selected_model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 2000,
                "stream": False
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(COPILOT_API_URL, data=data)
            req.add_header('Authorization', f'Bearer {copilot_cmd.access_token}')
            req.add_header('Content-Type', 'application/json')
            req.add_header('Accept', 'application/json')
            req.add_header('User-Agent', 'GitHubCopilot/1.200.0.0 (sublime; 4169; x64)')

            with urllib.request.urlopen(req, timeout=45) as response:
                result = json.loads(response.read().decode())
                if 'choices' in result and result['choices']:
                    assistant_message = result['choices'][0]['message']['content']
                    code = self.extract_code(assistant_message)
                    sublime.set_timeout(lambda: [
                        self.clear_progress_phantom(),
                        self.view.run_command("replace_selection_with_code", {"code": code, "regions": sel_ranges})
                    ], 0)
        except Exception as e:
            sublime.set_timeout(lambda e=e: [self.clear_progress_phantom(), sublime.error_message(f"Copilot error: {e}")], 0)

    def extract_code(self, text):
        if "```" in text:
            match = re.search(r'```(?:[a-zA-Z0-9\+]+)?\n(.*?)\n```', text, re.DOTALL)
            if match: return match.group(1).strip()
        return text.strip()

def _build_message_with_file_refs(prompt, window):
    import re, os, glob
    file_contents = ""
    file_pattern = re.compile(r'file:\s*([^\s]+)', re.IGNORECASE)
    for filename in file_pattern.findall(prompt):
        abs_path = os.path.join(window.folders()[0], filename)
        if os.path.exists(abs_path):
            try:
                with open(abs_path, "r", encoding="utf-8") as f:
                    content = f.read()
                file_contents += f"\n\n# file: {filename}\n{content}\n"
            except Exception as e:
                file_contents += f"\n\n# file: {filename} (gagal dibaca: {e})\n"
        else:
            file_contents += f"\n\n# file: {filename} (tidak ditemukan)\n"

    dir_pattern = re.compile(r'dir:\s*([^\s]+)', re.IGNORECASE)
    for pattern in dir_pattern.findall(prompt):
        abs_pattern = os.path.join(window.folders()[0], pattern)
        for filepath in glob.glob(abs_pattern, recursive=True):
            if os.path.isfile(filepath):
                rel_path = os.path.relpath(filepath, window.folders()[0])
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read()
                    file_contents += f"\n\n# file: {rel_path}\n{content}\n"
                except Exception as e:
                    file_contents += f"\n\n# file: {rel_path} (gagal dibaca: {e})\n"

    return prompt + ("\n\n# Referensi file:\n" + file_contents if file_contents else "")

class GithubCopilotGenerateCodeCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        window = self.view.window()
        copilot_cmd = GithubCopilotCommand.get_instance(window)
        if not copilot_cmd.is_authenticated():
            sublime.error_message("Please authenticate first.")
            return

        def on_done(prompt):
            base_prompt = copilot_cmd.settings.get("base_prompt_generate_code", "")
            full_user_prompt = _build_message_with_file_refs(prompt, window)

            messages = []
            if base_prompt:
                messages.append({"role": "system", "content": base_prompt})
            messages.append({"role": "user", "content": full_user_prompt})

            self.progress_active = True
            self.progress_dots = 0
            self.phantom_set = sublime.PhantomSet(self.view, "copilot_gen_progress")
            self._animate_progress()

            threading.Thread(
                target=self._ask_copilot_and_insert,
                args=(messages, self.view.sel()[0].begin())
            ).start()

        window.show_input_panel("Prompt (generate code):", "", on_done, None, None)

    def _animate_progress(self):
        if not getattr(self, "progress_active", False):
            return

        dots = "." * (self.progress_dots % 4)

        content = f'''
            <body id="copilot-progress">
                <style>
                    #copilot-progress .modal-box {{
                        background-color: color(var(--background) blend(#000 80%));
                        border: 1px solid var(--bluish);
                        border-radius: 8px;
                        padding: 16px 20px;
                        margin: 8px auto;
                        color: var(--foreground);
                        max-width: 400px;
                        text-align: center;
                        font-size: 1.1rem;
                    }}
                </style>
                <div class="modal-box">
                    Mohon tunggu sebentar.<br>
                    <b>GitHub Copilot sedang berpikir{dots}</b>
                </div>
            </body>
        '''

        region = self.view.sel()[0]
        phantom = sublime.Phantom(region, content, sublime.LAYOUT_BLOCK)
        self.phantom_set.update([phantom])

        self.progress_dots += 1
        sublime.set_timeout(self._animate_progress, 500)


    def _stop_progress(self):
        self.progress_active = False
        if hasattr(self, "phantom_set"):
            self.phantom_set.update([])

    def _ask_copilot_and_insert(self, messages, insert_pt):
        window = self.view.window()
        copilot_cmd = GithubCopilotCommand.get_instance(window)
        try:
            selected_model = copilot_cmd.settings.get("selected_model", "gpt-4o")
            payload = {
                "model": selected_model,
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 2000,
                "stream": False
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(COPILOT_API_URL, data=data)
            req.add_header('Authorization', f'Bearer {copilot_cmd.access_token}')
            req.add_header('Content-Type', 'application/json')
            req.add_header('Accept', 'application/json')
            req.add_header('User-Agent', 'GitHubCopilot/1.200.0.0 (sublime; 4169; x64)')

            with urllib.request.urlopen(req, timeout=45) as response:
                result = json.loads(response.read().decode())
                if 'choices' in result and result['choices']:
                    assistant_message = result['choices'][0]['message']['content']
                    code, explanation = self._split_code_and_explanation(assistant_message)
                    sublime.set_timeout(lambda: [
                        self._stop_progress(),
                        self.view.run_command(
                            "insert_generated_code",
                            {
                                "code": code,
                                "explanation": explanation,
                                "pt": insert_pt
                            }
                        )
                    ], 0)
        except Exception as e:
            sublime.set_timeout(lambda e=e: [
                self._stop_progress(),
                sublime.error_message(f"Copilot error: {e}")
            ], 0)

    def _split_code_and_explanation(self, text):
        code = ""
        explanation = text.strip()
        if "```" in text:
            m = re.search(r'```(?:[a-zA-Z0-9\+]+)?\n(.*?)\n```', text, re.DOTALL)
            if m:
                code = m.group(1).rstrip()
                explanation = text.replace(m.group(0), "").strip()
        return code, explanation


class InsertGeneratedCodeCommand(sublime_plugin.TextCommand):
    def run(self, edit, code, explanation, pt):
        to_insert = ""
        if explanation:
            comment = self.view.meta_info("shellVariables", pt)
            if comment:
                starters = [sv["value"] for sv in comment if sv.get("name") == "TM_COMMENT_START"]
                c = starters[0] if starters else "#"
            else:
                c = "#"
            exp_lines = [f"{c} {l}" for l in explanation.splitlines()]
            to_insert += "\n".join(exp_lines) + "\n\n"
        to_insert += code if code else explanation

        self.view.insert(edit, pt, to_insert)
        end_pt = pt + len(to_insert)
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(end_pt, end_pt))
        self.view.show(end_pt)


class ReplaceSelectionWithCodeCommand(sublime_plugin.TextCommand):
    def run(self, edit, code, regions):
        for a, b in reversed(regions):
            region = sublime.Region(a, b)
            self.view.replace(edit, region, code)
        # Indentasi ulang dengan fitur bawaan Sublime
        self.view.run_command("reindent", {"force_indent": False})
        # Hilangkan seleksi, letakkan kursor di awal seleksi pertama
        if regions:
            a, _ = regions[0]
            self.view.sel().clear()
            self.view.sel().add(sublime.Region(a, a))

class GithubCopilotEditSettingsCommand(sublime_plugin.ApplicationCommand):
    def run(self):
        sublime.active_window().open_file(
            "${packages}/User/github_copilot.sublime-settings".replace("${packages}", sublime.packages_path())
        )
