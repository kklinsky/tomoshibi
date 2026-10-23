"""Understanding short replies without the AI, so they work offline (docs/DESIGN.md §5).

For now: answers to a reminder ("OK", "thanks, I took them", "remind me in ten minutes").
"""

import re

NUMBERS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
           "eight": 8, "nine": 9, "ten": 10, "fifteen": 15, "twenty": 20, "thirty": 30,
           "forty five": 45, "forty-five": 45, "sixty": 60, "a few": 5, "a couple of": 2,
           "a couple": 2}
_ACK = re.compile(r"^\W*(ok(ay)?|alright|all right|thanks?( you)?|thank you|got it|will do|"
                  r"sure|yes|yeah|yep|i did|i took (it|them)|done|on it|i know|i'?m on it|"
                  r"i'?ll do (it|that)|very good|good|great|right)\b", re.IGNORECASE)
_SNOOZE = re.compile(r"\b(remind me|tell me|ask me)\b.*?\b(?:again\s+)?in\s+"
                     r"(\d+|a few|a couple(?: of)?|half an|forty[- ]five|\w+)\s+(minutes?|mins?|hours?|hour)\b",
                     re.IGNORECASE)
_LATER = re.compile(r"\b(later|not now|in a (minute|bit|while)|give me a (minute|moment|bit))\b",
                    re.IGNORECASE)


def reminder_reply(text: str) -> tuple[str, int]:
    """("ack", 0), ("snooze", minutes) or ("other", 0) for what was said after a reminder."""
    text = text.strip()
    if m := _SNOOZE.search(text):
        amount, unit = m.group(2).lower(), m.group(3).lower()
        hours = unit.startswith("hour")
        if amount == "half an":
            return "snooze", 30 if hours else 1
        n = int(amount) if amount.isdigit() else NUMBERS.get(amount, 10)
        return "snooze", n * 60 if hours else n
    if _LATER.search(text):
        return "snooze", 10
    if _ACK.search(text):
        return "ack", 0
    return "other", 0
