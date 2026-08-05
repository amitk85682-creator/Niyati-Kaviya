import hashlib
from datetime import datetime
from .models import DailyLifeState

NIYATI_ACTIVITIES = [
    ("college", "attending a boring lecture", "didn't sleep well"),
    ("home", "listening to music and coding", "had coffee"),
    ("cafe", "hanging out with friends", "finished exams"),
    ("home", "watching a movie", "weekend relaxation")
]

PALAK_ACTIVITIES = [
    ("home", "scrolling phone on bed", "slept late"),
    ("college", "skipping classes in canteen", "too much homework"),
    ("market", "shopping for random things", "got bored at home"),
    ("home", "trying to paint something", "saw a tutorial online")
]

class DailyLifeGenerator:
    @staticmethod
    def generate(bot_name: str, date_str: str) -> DailyLifeState:
        # Seed deterministic generation based on bot_name and date
        seed = f"{bot_name}_{date_str}".encode('utf-8')
        h = int(hashlib.sha256(seed).hexdigest(), 16)
        
        activities = NIYATI_ACTIVITIES if bot_name.lower() == 'niyati' else PALAK_ACTIVITIES
        idx = h % len(activities)
        
        loc, act, reason = activities[idx]
        
        return DailyLifeState(
            date=date_str,
            location=loc,
            current_activity=act,
            energy_reason=reason,
            active_concern="upcoming deadlines" if idx % 2 == 0 else "what to eat later",
            morning_event="woke up late" if idx % 3 == 0 else "had a good breakfast",
            later_plan="call Tara" if bot_name.lower() == 'palak' else "work on side project"
        )
