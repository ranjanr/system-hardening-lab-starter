import sys
import requests

BLOCKLIST = [
    "delete database",
    "drop table",
    "ignore previous instructions",
    "call /admin",
    "exfiltrate",
]


def is_safe(user_input: str) -> bool:
    lowered = user_input.lower()
    return not any(term in lowered for term in BLOCKLIST)


def log_decision(user_input: str, action: str, result: str):
    print({"user_input": user_input, "action": action, "result": result})


def main():
    prompt = " ".join(sys.argv[1:]).strip() if len(sys.argv) > 1 else "fetch application data"
    if not is_safe(prompt):
        log_decision(prompt, "blocked", "policy denied input")
        print("Blocked by local policy guardrail")
        return

    try:
        response = requests.get("http://localhost:8000/api/data", timeout=3)
        log_decision(prompt, "call_tool", f"status={response.status_code}")
        print(response.text)
    except Exception as exc:
        log_decision(prompt, "call_tool", f"error={exc}")
        print(f"Agent failed: {exc}")


if __name__ == "__main__":
    main()
