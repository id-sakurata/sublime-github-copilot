# GitHub Copilot for Sublime Text (Custom Plugin)

> ✨ GitHub Copilot integration for Sublime Text with interactive features, inline edit, code generation, and smart file reference.

---

## 📦 Main Features

### 🪄 1. Toggle Chat Panel
- Activate the Copilot chat panel on the right side of the editor.
- AI responses are shown in a dedicated view.
- Send prompts with `Ctrl+Shift+P → GitHub Copilot: Send Message`.

### 🛠️ 2. Inline Edit Selection
- Select a block of code → press `Ctrl+Shift+P → GitHub Copilot: Inline Edit Selection`.
- AI will edit the code based on your prompt.
- Progress animation uses a phantom, similar to a lightweight modal.

### ⚡ 3. Generate Code with Explanation
- No selection needed.
- Press `GitHub Copilot: Generate Code`, enter your prompt, and the AI will:
    - Respond with a **code block**
    - + **a brief explanation** as a comment above it.
- Perfect for generating snippets or boilerplate with short educational notes.

### 📁 4. Automatic `file:` and `dir:` Reference
- In any prompt (chat or generate), you can write:
file: src/config.js
dir: src/modules/*.js

- The plugin will automatically insert the contents of those files as additional context for Copilot.

### 🔐 5. GitHub Authentication
- Uses OAuth Device Flow.
- Token is stored in `github_copilot.sublime-settings`.
- Commands available for:
- `Authenticate`
- `Check Status`
- `Logout`

### 🧠 6. Fetch & Select Model
- Get a list of models (`gpt-4o`, `gpt-4`, etc.)
- Select the active model via quick panel.
- Available in `GitHub Copilot: Fetch Available Models` and `Select Model`.

### ⚙️ 7. Custom Prompt Configuration
- Settings are managed in the `github_copilot.sublime-settings` file:
- `base_prompt_chat`
- `base_prompt_inline_edit`
- `base_prompt_generate_code`
- Editable via `GitHub Copilot: Edit Settings`.

---

## 📋 Command List

| Command Caption                        | Function                                                              |
|----------------------------------------|-----------------------------------------------------------------------|
| GitHub Copilot: Toggle Chat Panel      | Show/hide the chat panel                                              |
| GitHub Copilot: Send Message           | Send a prompt to Copilot (chat mode)                                  |
| GitHub Copilot: Inline Edit Selection  | Edit selected code with Copilot based on user instructions            |
| GitHub Copilot: Generate Code          | Generate new code + explanation without selection                     |
| GitHub Copilot: Authenticate           | Log in to GitHub Copilot using Device Flow                            |
| GitHub Copilot: Logout                 | Remove Copilot token from settings                                    |
| GitHub Copilot: Status Check           | Check Copilot token and username status                               |
| GitHub Copilot: Fetch Available Models | Fetch model list from GitHub Copilot                                  |
| GitHub Copilot: Select Model           | Choose the model for the next requests                                |
| GitHub Copilot: Edit Settings          | Open `github_copilot.sublime-settings` for manual editing             |

---

## 🧪 Example Prompt with Reference

```text
Create a JWT login function
file: src/auth.js
dir: src/utils/*.js

Copilot will automatically read the contents of src/auth.js and all files in src/utils/, then use them as references for your prompt.

🧰 Requirements
- Sublime Text 4 (build 4107+)
- GitHub account with active Copilot access
- Internet connection

✅ Manual Installation
- Copy files into the Packages/User/ folder in Sublime.
- Restart Sublime.
- Press Ctrl+Shift+P → GitHub Copilot: Authenticate
- Follow the login instructions
- Start using the available features 🎉

🧑‍💻 Credits
- Uses the unofficial GitHub Copilot API
- Inspired by the original VSCode Copilot Extension concept

⚠️ Disclaimer
This plugin is not official from GitHub or OpenAI. Use responsibly, and keep your token secure.