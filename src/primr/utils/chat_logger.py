"""
Chat logging utility for AI interactions.
"""

from datetime import datetime
import json
from pathlib import Path

from colorama import Fore, Style

# Get project root for log directory
from primr.config.config import PROJECT_ROOT

# Directory for storing chat logs
CHAT_LOG_DIR = Path(PROJECT_ROOT) / "logs" / "chat_history"
CHAT_LOG_DIR.mkdir(parents=True, exist_ok=True)


def get_log_file_path() -> Path:
    """Generates a log file path based on the current session timestamp."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    return CHAT_LOG_DIR / f"chat_log_{timestamp}.json"


def log_chat_interaction(prompt, response, session_id="general"):
    """
    Logs AI interactions (prompt and response) for debugging and explainability.

    - session_id: Identifies logs per company research session.
    - Stores conversations in JSON format for structured review.
    """
    log_file_path = CHAT_LOG_DIR / f"{session_id}.json"

    # Load existing logs if the file exists
    chat_history = []
    if log_file_path.exists():
        try:
            with open(log_file_path, encoding="utf-8") as f:
                chat_history = json.load(f)
        except json.JSONDecodeError:
            print(
                Fore.RED
                + "[ERROR] Corrupt log file detected. Starting fresh log."
                + Style.RESET_ALL
            )

    # Append new log entry
    chat_history.append(
        {"timestamp": datetime.now().isoformat(), "prompt": prompt, "response": response}
    )

    # Save the updated chat log
    try:
        with open(log_file_path, "w", encoding="utf-8") as f:
            json.dump(chat_history, f, indent=4)
    except Exception as e:
        print(Fore.RED + f"[ERROR] Failed to save chat log: {e}" + Style.RESET_ALL)


def read_chat_logs(session_id="general"):
    """Reads and returns chat logs for a given session."""
    log_file_path = CHAT_LOG_DIR / f"{session_id}.json"

    if not log_file_path.exists():
        print(Fore.YELLOW + f"[WARNING] No logs found for session: {session_id}" + Style.RESET_ALL)
        return []

    try:
        with open(log_file_path, encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        print(Fore.RED + f"[ERROR] Corrupt chat log file: {log_file_path}" + Style.RESET_ALL)
        return []


if __name__ == "__main__":
    # CLI Testing Mode
    while True:
        action = (
            input(
                Fore.BLUE
                + "\nEnter 'log' to save AI interaction, 'read' to view logs, or 'exit': "
                + Style.RESET_ALL
            )
            .strip()
            .lower()
        )

        if action == "log":
            prompt = input(Fore.CYAN + "Enter AI prompt: " + Style.RESET_ALL).strip()
            response = input(Fore.CYAN + "Enter AI response: " + Style.RESET_ALL).strip()
            session = (
                input(
                    Fore.CYAN + "Enter session ID (default: 'general'): " + Style.RESET_ALL
                ).strip()
                or "general"
            )
            log_chat_interaction(prompt, response, session)

        elif action == "read":
            session = (
                input(
                    Fore.CYAN
                    + "Enter session ID to read logs (default: 'general'): "
                    + Style.RESET_ALL
                ).strip()
                or "general"
            )
            logs = read_chat_logs(session)
            print(Fore.GREEN + f"\n[✔] Chat Logs for Session: {session}" + Style.RESET_ALL)
            for log in logs:
                print(
                    f"{log['timestamp']}: \n- **Prompt:** {log['prompt']}\n- **Response:** {log['response']}\n"
                )

        elif action == "exit":
            break

        else:
            print(
                Fore.RED
                + "[ERROR] Invalid input. Please enter 'log', 'read', or 'exit'."
                + Style.RESET_ALL
            )
