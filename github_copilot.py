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
COPILOT_API_URL = "https://api.githubcopilot.com/chat/completions"

class GithubCopilotCommand(sublime_plugin.WindowCommand):
    def __init__(self, window):
        super().__init__(window)
        self.access_token = None
        self.chat_view = None
        self.chat_history = []
        self.settings = sublime.load_settings("github_copilot.sublime-settings")
        self.chat_panel_visible = False
        self.original_layout = None
        self.load_token()
        
    @classmethod
    def get_instance(cls, window):
        """Get or create instance for window"""
        if not hasattr(cls, '_instances'):
            cls._instances = {}
        if window.id() not in cls._instances:
            cls._instances[window.id()] = cls(window)
        return cls._instances[window.id()]

    def run(self):
        if self.chat_panel_visible:
            self.hide_chat_panel()
        else:
            self.show_chat_panel()

    def load_token(self):
        """Load saved access token"""
        self.access_token = self.settings.get("access_token")

    def save_token(self, token):
        self.access_token = token
        self.settings.set("access_token", token)
        sublime.save_settings("github_copilot.sublime-settings")

    def clear_token(self):
        """Clear saved access token"""
        self.access_token = None
        self.settings.erase("access_token")
        sublime.save_settings("github_copilot.sublime-settings")

    def show_chat_panel(self):
        """Show chat panel in right column"""
        # Store original layout
        if not self.original_layout:
            self.original_layout = self.window.get_layout()
        
        # Set layout with right panel (70/30 split)
        self.window.run_command("set_layout", {
            "cols": [0.0, 0.6, 1.0],
            "rows": [0.0, 1.0],
            "cells": [[0, 0, 1, 1], [1, 0, 2, 1]]
        })

        # Create or show chat view
        if not self.chat_view or not self.chat_view.is_valid():
            self.chat_view = self.window.new_file()
            self.chat_view.set_name("GitHub Copilot Chat")
            self.chat_view.set_scratch(True)
            # Set word_wrap to False as requested
            self.chat_view.settings().set("word_wrap", True)
            self.chat_view.settings().set("line_numbers", False)
            self.chat_view.settings().set("gutter", False)
            self.chat_view.settings().set("scroll_past_end", True)
            self.chat_view.settings().set("font_size", 10)
            
        # Move chat view to right panel
        self.window.set_view_index(self.chat_view, 1, 0)
        
        # Focus on chat view initially
        self.window.focus_view(self.chat_view)
        
        self.chat_panel_visible = True
        
        # Initialize chat content
        if self.is_authenticated():
            self.update_chat_view("=== GitHub Copilot Chat ===\nStatus: Authenticated ✓\nPress Ctrl+Shift+P and type 'GitHub Copilot: Send Message' to chat\n\n")
        else:
            self.update_chat_view("=== GitHub Copilot Chat ===\nStatus: Not authenticated ❌\nRun 'GitHub Copilot: Authenticate' to login\n\n")
        
        # Automatically show input panel when chat panel is opened
        if self.is_authenticated():
            sublime.set_timeout(lambda: self.show_input_panel(), 100)

    def hide_chat_panel(self):
        """Hide chat panel and restore original layout"""
        if self.original_layout:
            self.window.run_command("set_layout", self.original_layout)
            self.original_layout = None
        
        # Close chat view
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
            # Scroll to bottom
            # self.chat_view.show(self.chat_view.size())

    def is_authenticated(self):
        """Check if user is authenticated"""
        return self.access_token is not None

    def show_input_panel(self):
        """Show input panel for message"""
        if not self.is_authenticated():
            sublime.error_message("Please authenticate first using 'GitHub Copilot: Authenticate'")
            return
        
        self.window.show_input_panel(
            "Message to Copilot:",
            "",
            lambda message: self.send_message(message),
            None,  # on_change
            None   # on_cancel
        )

    def send_message(self, message):
        """Process and send the message"""
        message = message.strip()
        if not message:
            return

        # --- Tambahan: Parsing file: dan dir: ---
        file_contents = ""
        # file: src/foo.txt
        file_pattern = re.compile(r'file:\s*([^\s]+)', re.IGNORECASE)
        for filename in file_pattern.findall(message):
            abs_path = os.path.join(self.window.folders()[0], filename)
            if os.path.exists(abs_path):
                try:
                    with open(abs_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    file_contents += f"\n\n# file: {filename}\n{content}\n"
                except Exception as e:
                    file_contents += f"\n\n# file: {filename} (gagal dibaca: {e})\n"
            else:
                file_contents += f"\n\n# file: {filename} (tidak ditemukan)\n"

        # dir: src/*
        dir_pattern = re.compile(r'dir:\s*([^\s]+)', re.IGNORECASE)
        for pattern in dir_pattern.findall(message):
            abs_pattern = os.path.join(self.window.folders()[0], pattern)
            for filepath in glob.glob(abs_pattern, recursive=True):
                if os.path.isfile(filepath):
                    rel_path = os.path.relpath(filepath, self.window.folders()[0])
                    try:
                        with open(filepath, "r", encoding="utf-8") as f:
                            content = f.read()
                        file_contents += f"\n\n# file: {rel_path}\n{content}\n"
                    except Exception as e:
                        file_contents += f"\n\n# file: {rel_path} (gagal dibaca: {e})\n"

        if file_contents:
            # Jangan tampilkan isi file di panel chat, hanya kirim ke Copilot
            message_for_copilot = message + "\n\n# Referensi file:\n" + file_contents
        else:
            message_for_copilot = message
        # --- Akhir tambahan ---

        # Add user message to chat (hanya pesan user, tanpa isi file)
        timestamp = datetime.now().strftime("%H:%M:%S")
        user_msg = (
            "\n─────────────────────────────\n"
            f"[{timestamp}] 👤 You:\n"
            f"{message}\n"
        )
        self.update_chat_view(user_msg, append=True)
        print(f"Sending message: {message_for_copilot}")
        print(f"Authenticated: {self.is_authenticated()}")
        threading.Thread(target=self.send_to_copilot, args=(message_for_copilot,)).start()

    def send_to_copilot(self, message):
        """Send message to GitHub Copilot API"""
        try:
            # Add message to history
            self.chat_history.append({"role": "user", "content": message})
            
            # Keep only last 10 messages to avoid token limits
            if len(self.chat_history) > 10:
                self.chat_history = self.chat_history[-10:]
            
            # Start typing effect
            self.start_typing_effect()
            
            # Try different API endpoints and models
            api_endpoints = [
                ("https://api.githubcopilot.com/chat/completions", "gpt-4o"),
                ("https://api.githubcopilot.com/chat/completions", "gpt-4"),
                ("https://api.githubcopilot.com/chat/completions", "gpt-3.5-turbo"),
                ("https://copilot-proxy.githubusercontent.com/v1/chat/completions", "gpt-4o"),
            ]
            
            last_error = None
            
            for api_url, model in api_endpoints:
                try:
                    # Prepare API request
                    payload = {
                        "model": model,
                        "messages": self.chat_history,
                        "temperature": 0.7,
                        "max_tokens": 1000,
                        "stream": False
                    }
                    
                    data = json.dumps(payload).encode()
                    req = urllib.request.Request(api_url, data=data)
                    req.add_header('Authorization', f'Bearer {self.access_token}')
                    req.add_header('Content-Type', 'application/json')
                    req.add_header('Accept', 'application/json')
                    req.add_header('User-Agent', 'GitHub Copilot')
                    
                    print(f"Trying API: {api_url} with model: {model}")
                    
                    with urllib.request.urlopen(req, timeout=30) as response:
                        response_text = response.read().decode()
                        print(f"Response: {response_text}")
                        
                        result = json.loads(response_text)
                        
                        if 'choices' in result and result['choices']:
                            assistant_message = result['choices'][0]['message']['content']
                            self.chat_history.append({"role": "assistant", "content": assistant_message})

                            # Stop typing effect and add response
                            self.stop_typing_effect()
                            timestamp = datetime.now().strftime("%H:%M:%S")

                            # Format response with separator for code blocks
                            formatted_response = self.format_response(assistant_message)
                            response_msg = (
                                "\n─────────────────────────────\n"
                                f"[{timestamp}] 🤖 Copilot:\n"
                                f"{formatted_response}\n"
                            )

                            sublime.set_timeout(lambda: self.update_chat_with_response(response_msg), 0)
                            return
                        else:
                            last_error = f"Invalid response format: {result}"
                            continue
                            
                except urllib.error.HTTPError as e:
                    error_body = e.read().decode() if hasattr(e, 'read') else str(e)
                    last_error = f"HTTP {e.code}: {error_body}"
                    print(f"HTTP Error {e.code}: {error_body}")
                    continue
                except Exception as e:
                    last_error = str(e)
                    print(f"Request error: {e}")
                    continue
            
            # If all endpoints failed, try a simple echo response for testing
            if "test" in message.lower():
                self.stop_typing_effect()
                test_response = f"Echo: {message} (This is a test response)"
                timestamp = datetime.now().strftime("%H:%M:%S")
                response_msg = f"[{timestamp}] Copilot: {test_response}\n"
                sublime.set_timeout(lambda: self.update_chat_with_response(response_msg), 0)
                return
            
            # If all endpoints failed
            self.stop_typing_effect()
            error_msg = f"All API endpoints failed. Last error: {last_error}\n"
            sublime.set_timeout(lambda: self.update_chat_with_response(error_msg), 0)
                    
        except Exception as e:
            self.stop_typing_effect()
            error_msg = f"Unexpected error: {str(e)}\n"
            print(f"Unexpected error: {e}")
            sublime.set_timeout(lambda: self.update_chat_with_response(error_msg), 0)

    def format_response(self, response):
        """Format response with separators for code blocks"""
        if '```' in response:
            # Replace code block markers with separators
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
        if not self.typing_active:
            return

        dots = "." * (self.typing_dots % 4)
        typing_text = f"Copilot is typing{dots}   "

        if self.chat_view and self.chat_view.is_valid():
            current_content = self.chat_view.substr(sublime.Region(0, self.chat_view.size()))
            lines = current_content.split('\n')

            # Cari baris terakhir yang mengandung 'typing'
            found = False
            for i in range(len(lines) - 1, -1, -1):
                if 'typing' in lines[i]:
                    lines[i] = typing_text
                    found = True
                    break
            if not found:
                # Jika tidak ada, tambahkan di baris baru dan scroll ke bawah
                lines.append(typing_text)
                new_content = '\n'.join(lines)
                self.update_chat_view(new_content)
                sublime.set_timeout(lambda: self.chat_view.show(self.chat_view.size()), 0)
            else:
                # Jika sudah ada, hanya replace tanpa scroll
                new_content = '\n'.join(lines)
                self.update_chat_view(new_content)

        self.typing_dots += 1

        # Continue animation
        if self.typing_active:
            sublime.set_timeout(lambda: self.update_typing_indicator(), 500)
    
    def update_chat_with_response(self, response_text):
        """Update chat view removing typing indicator and adding response"""
        if self.chat_view and self.chat_view.is_valid():
            # Get current content and remove typing indicator
            current_content = self.chat_view.substr(sublime.Region(0, self.chat_view.size()))
            lines = current_content.split('\n')
            if lines and 'typing' in lines[-1]:
                lines = lines[:-1]

            # Add response
            new_content = '\n'.join(lines) + '\n' + response_text
            self.chat_view.set_read_only(False)
            # Replace seluruh isi file tanpa mengubah selection ke atas
            self.chat_view.run_command("replace_content_and_scroll", {"content": new_content})
            self.chat_view.set_read_only(True)

            # Show input panel again after response
            sublime.set_timeout(lambda: self.show_input_panel(), 500)

# Tambahkan command baru di bawah:
class ReplaceContentAndScrollCommand(sublime_plugin.TextCommand):
    def run(self, edit, content):
        region = sublime.Region(0, self.view.size())
        self.view.replace(edit, region, content)
        # Set selection ke awal baris terakhir
        last_line = self.view.rowcol(self.view.size())[0]
        pt = self.view.text_point(last_line, 0)
        self.view.sel().clear()
        self.view.sel().add(sublime.Region(pt, pt))
        # Scroll ke bawah (baris terakhir)
        self.view.show(pt)

class GithubCopilotToggleCommand(sublime_plugin.WindowCommand):
    """Command specifically for toggling chat panel"""
    def run(self):
        copilot_cmd = GithubCopilotCommand.get_instance(self.window)
        copilot_cmd.toggle_chat_panel()

class GithubCopilotAuthenticateCommand(sublime_plugin.WindowCommand):
    def run(self):
        copilot_cmd = GithubCopilotCommand.get_instance(self.window)
        if copilot_cmd.is_authenticated():
            sublime.message_dialog("Already authenticated with GitHub Copilot!")
            return
        
        threading.Thread(target=self.authenticate_async, args=(copilot_cmd,)).start()

    def authenticate_async(self, copilot_cmd):
        try:
            # Step 1: Get device code
            device_data = self.get_device_code()
            if not device_data:
                sublime.error_message("Failed to get device code")
                return

            device_code = device_data['device_code']
            user_code = device_data['user_code']
            verification_uri = device_data['verification_uri']
            interval = device_data.get('interval', 5)

            # Salin user_code ke clipboard
            sublime.set_clipboard(user_code)

            # Step 2: Open browser for user authentication
            sublime.message_dialog(
                f"Opening browser for authentication...\n"
                f"User code: {user_code} (sudah disalin ke clipboard)\n"
                f"Enter this code if prompted."
            )
            webbrowser.open(verification_uri)

            # Step 3: Poll for access token
            max_attempts = 60  # 5 minutes max
            for attempt in range(max_attempts):
                time.sleep(interval)
                token_data = self.poll_for_token(device_code)
                
                if token_data and 'access_token' in token_data:
                    access_token = token_data['access_token']
                    copilot_cmd.save_token(access_token)
                    copilot_cmd.load_token()  # Tambahkan baris ini agar token langsung aktif
                    sublime.message_dialog("Successfully authenticated with GitHub Copilot!")
                    # Update chat view if open
                    if copilot_cmd.chat_view and copilot_cmd.chat_view.is_valid():
                        copilot_cmd.update_chat_view("=== GitHub Copilot Chat ===\nStatus: Authenticated ✓\nPress Ctrl+Shift+P and type 'GitHub Copilot: Send Message' to chat\n\n")
                    return
                    
                elif token_data and token_data.get('error') == 'authorization_pending':
                    continue  # Keep polling
                elif token_data and token_data.get('error') == 'slow_down':
                    interval += 5  # Increase interval
                    continue
                else:
                    break

            sublime.error_message("Authentication timed out or failed")

        except Exception as e:
            sublime.error_message(f"Authentication error: {str(e)}")

    def get_device_code(self):
        """Get device code from GitHub"""
        try:
            data = urllib.parse.urlencode({
                'client_id': CLIENT_ID,
                'scope': 'copilot'
            }).encode()
            
            req = urllib.request.Request(GITHUB_DEVICE_CODE_URL, data=data)
            req.add_header('Accept', 'application/json')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            print(f"Error getting device code: {e}")
            return None

    def poll_for_token(self, device_code):
        """Poll GitHub for access token"""
        try:
            data = urllib.parse.urlencode({
                'client_id': CLIENT_ID,
                'device_code': device_code,
                'grant_type': 'urn:ietf:params:oauth:grant-type:device_code'
            }).encode()
            
            req = urllib.request.Request(GITHUB_TOKEN_URL, data=data)
            req.add_header('Accept', 'application/json')
            req.add_header('Content-Type', 'application/x-www-form-urlencoded')
            
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            return {'error': str(e)}

class GithubCopilotLogoutCommand(sublime_plugin.WindowCommand):
    def run(self):
        copilot_cmd = GithubCopilotCommand.get_instance(self.window)
        copilot_cmd.clear_token()
        
        # Update chat view if open
        if copilot_cmd.chat_view and copilot_cmd.chat_view.is_valid():
            copilot_cmd.update_chat_view("=== GitHub Copilot Chat ===\nStatus: Logged out ❌\nRun 'GitHub Copilot: Authenticate' to login\n\n")
        
        sublime.message_dialog("Logged out from GitHub Copilot")

class GithubCopilotStatusCommand(sublime_plugin.WindowCommand):
    def run(self):
        copilot_cmd = GithubCopilotCommand.get_instance(self.window)
        if copilot_cmd.is_authenticated():
            sublime.message_dialog("GitHub Copilot: Authenticated ✓")
        else:
            sublime.message_dialog("GitHub Copilot: Not authenticated ❌")

class GithubCopilotSendMessageCommand(sublime_plugin.WindowCommand):
    """Send message using input panel instead of separate view"""
    def run(self):
        copilot_cmd = GithubCopilotCommand.get_instance(self.window)
        
        if not copilot_cmd.is_authenticated():
            sublime.error_message("Please authenticate first using 'GitHub Copilot: Authenticate'")
            return
        
        # Show chat panel if not visible
        if not copilot_cmd.chat_panel_visible:
            copilot_cmd.show_chat_panel()
        else:
            # Just show input panel if chat panel is already visible
            copilot_cmd.show_input_panel()

class GithubCopilotInlineEditCommand(sublime_plugin.TextCommand):
    """Send selection to Copilot and replace with response"""
    def run(self, edit):
        window = self.view.window()
        copilot_cmd = GithubCopilotCommand.get_instance(window)
        if not copilot_cmd.is_authenticated():
            sublime.error_message("Please authenticate first using 'GitHub Copilot: Authenticate'")
            return

        sels = self.view.sel()
        if not sels or all(r.empty() for r in sels):
            sublime.error_message("Please select some text to edit with Copilot.")
            return

        selected_text = "\n".join([self.view.substr(r) for r in sels if not r.empty()])

        self.phantom_set = sublime.PhantomSet(self.view, "copilot_inline_progress")
        self.progress_active = False
        self.progress_dots = 0

        def on_done(prompt):
            full_prompt = f"{prompt}\n\nKode:\n{selected_text}"
            self.progress_active = True
            self.progress_dots = 0
            self.show_progress_phantom()
            self.animate_progress_phantom()
            threading.Thread(target=self.ask_copilot_and_replace, args=(full_prompt, [ (r.a, r.b) for r in sels ])).start()

        window.show_input_panel("Prompt for Copilot (inline edit):", "", on_done, None, None)

    def show_progress_phantom(self):
        region = self.view.sel()[0]
        dots = "." * (self.progress_dots % 4)
        phantom = sublime.Phantom(
            region,
            f'<span style="color: var(--bluish);">Copilot is thinking{dots}</span>',
            sublime.LAYOUT_BELOW
        )
        self.phantom_set.update([phantom])

    def animate_progress_phantom(self):
        if not getattr(self, "progress_active", False):
            return
        self.progress_dots += 1
        self.show_progress_phantom()
        sublime.set_timeout(self.animate_progress_phantom, 500)

    def clear_progress_phantom(self):
        self.progress_active = False
        if hasattr(self, "phantom_set"):
            self.phantom_set.update([])

    def ask_copilot_and_replace(self, prompt, sel_ranges):
        window = self.view.window()
        copilot_cmd = GithubCopilotCommand.get_instance(window)
        try:
            copilot_cmd.chat_history.append({"role": "user", "content": prompt})
            if len(copilot_cmd.chat_history) > 10:
                copilot_cmd.chat_history = copilot_cmd.chat_history[-10:]

            api_url, model = "https://api.githubcopilot.com/chat/completions", "gpt-4o"
            payload = {
                "model": model,
                "messages": copilot_cmd.chat_history,
                "temperature": 0.7,
                "max_tokens": 1000,
                "stream": False
            }
            data = json.dumps(payload).encode()
            req = urllib.request.Request(api_url, data=data)
            req.add_header('Authorization', f'Bearer {copilot_cmd.access_token}')
            req.add_header('Content-Type', 'application/json')
            req.add_header('Accept', 'application/json')
            req.add_header('User-Agent', 'GitHub Copilot')

            with urllib.request.urlopen(req, timeout=30) as response:
                response_text = response.read().decode()
                result = json.loads(response_text)
                if 'choices' in result and result['choices']:
                    assistant_message = result['choices'][0]['message']['content']
                    code = self.extract_code(assistant_message)
                    # Panggil command baru untuk replace selection
                    sublime.set_timeout(lambda: [
                        self.clear_progress_phantom(),
                        self.view.run_command(
                            "replace_selection_with_code", 
                            {"code": code, "regions": sel_ranges}
                        )
                    ], 0)
        except Exception as e:
            def handle_error(e=e):
                self.clear_progress_phantom()
                sublime.error_message(f"Copilot error: {e}")
            sublime.set_timeout(handle_error, 0)

    def extract_code(self, text):
        # Ambil isi blok kode pertama, tanpa label bahasa
        if "```" in text:
            parts = text.split("```")
            if len(parts) >= 2:
                code_block = parts[1]
                # Hilangkan label bahasa di baris pertama jika ada
                lines = code_block.splitlines()
                if lines and lines[0].strip() in ["python", "js", "javascript", "css", "html", "json", "c", "cpp", "c++", "java", "go", "ts", "typescript", "sh", "bash"]:
                    lines = lines[1:]
                return "\n".join(lines).strip()
        return text.strip()

class ReplaceSelectionWithCodeCommand(sublime_plugin.TextCommand):
    def run(self, edit, code, regions):
        # Ambil indentasi dari selection pertama
        if regions:
            a, b = regions[0]
            region = sublime.Region(a, b)
            line = self.view.substr(self.view.line(region.begin()))
            indent = ""
            for char in line:
                if char in " \t":
                    indent += char
                else:
                    break
            # Baris pertama tetap, baris kedua dst ditambah indentasi
            code_lines = code.splitlines()
            if len(code_lines) > 1:
                code = code_lines[0] + "\n" + "\n".join(
                    [(indent + l if l.strip() else l) for l in code_lines[1:]]
                )
            else:
                code = code_lines[0]
        # Replace all regions dengan kode yang sudah diindentasi
        for a, b in regions:
            region = sublime.Region(a, b)
            self.view.replace(edit, region, code)