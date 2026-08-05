from dataclasses import dataclass, field, asdict
from typing import List, Optional
from datetime import datetime, timezone
from enum import Enum


class ConversationAction(Enum):
    ANSWER = "ANSWER"
    ACKNOWLEDGE = "ACKNOWLEDGE"
    ASK_FOLLOWUP = "ASK_FOLLOWUP"
    TEASE = "TEASE"
    DISAGREE = "DISAGREE"
    SELF_DISCLOSE = "SELF_DISCLOSE"
    REPAIR_MISTAKE = "REPAIR_MISTAKE"
    SET_BOUNDARY = "SET_BOUNDARY"
    CHANGE_TOPIC = "CHANGE_TOPIC"
    STAY_SILENT = "STAY_SILENT"


def clamp(value: float, min_val: float = 0.0, max_val: float = 1.0) -> float:
    return max(min_val, min(max_val, value))


@dataclass
class MoodState:
    valence: float = 0.5
    energy: float = 0.5
    irritation: float = 0.0
    sadness: float = 0.0
    embarrassment: float = 0.0
    playfulness: float = 0.5
    confidence: float = 0.5
    social_openness: float = 0.5
    
    def clamp_all(self):
        for k, v in self.__dict__.items():
            if isinstance(v, float):
                setattr(self, k, clamp(v))


@dataclass
class NeedState:
    connection: float = 0.5
    autonomy: float = 0.5
    rest: float = 0.5
    validation: float = 0.5
    novelty: float = 0.5
    
    def clamp_all(self):
        for k, v in self.__dict__.items():
            if isinstance(v, float):
                setattr(self, k, clamp(v))


@dataclass
class RelationshipState:
    familiarity: float = 0.0
    trust: float = 0.5
    warmth: float = 0.5
    respect: float = 0.5
    playfulness: float = 0.2
    guardedness: float = 0.5
    irritation: float = 0.0
    recent_tension: float = 0.0
    stage: str = "new"
    interaction_count: int = 0
    last_interaction_at: Optional[datetime] = None
    
    def clamp_all(self):
        for k, v in self.__dict__.items():
            if isinstance(v, float):
                setattr(self, k, clamp(v))


@dataclass
class DailyLifeState:
    date: str = ""
    location: str = ""
    current_activity: str = ""
    energy_reason: str = ""
    active_concern: str = ""
    morning_event: str = ""
    later_plan: str = ""
    disclosed_facts: List[str] = field(default_factory=list)


@dataclass
class UnresolvedEvent:
    type: str
    source_message_id: int
    target_bot: str
    created_at: datetime
    resolved: bool = False
    intensity: float = 0.5


@dataclass
class CharacterRuntimeState:
    bot_name: str
    chat_id: int
    user_id: int
    mood: MoodState = field(default_factory=MoodState)
    needs: NeedState = field(default_factory=NeedState)
    relationship: RelationshipState = field(default_factory=RelationshipState)
    daily_life: DailyLifeState = field(default_factory=DailyLifeState)
    unresolved_events: List[UnresolvedEvent] = field(default_factory=list)
    recent_actions: List[str] = field(default_factory=list)
    last_updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    def clamp_all(self):
        self.mood.clamp_all()
        self.needs.clamp_all()
        self.relationship.clamp_all()

    def to_dict(self):
        return asdict(self)


@dataclass
class EmotionalInputContext:
    bot_name: str
    chat_id: int
    user_id: int
    message_id: int
    text: str
    is_group: bool
    mentioned_bot_names: List[str] = field(default_factory=list)
    replied_to_bot_name: Optional[str] = None
    semantic_target_bot: Optional[str] = None
    latest_human_sender_id: Optional[int] = None
    original_human_trigger_id: Optional[int] = None
    character_already_responded: bool = False
    recent_group_context: List[str] = field(default_factory=list)
    previous_character_action: Optional[str] = None


@dataclass
class AppraisalResult:
    directed_to_character: bool = True
    target_bot: Optional[str] = None
    intent: str = "unknown"
    tone: str = "neutral"
    is_question: bool = False
    is_correction: bool = False
    is_playful_teasing: bool = False
    is_serious_insult: bool = False
    is_emotional_disclosure: bool = False
    is_user_sad: bool = False
    social_threat: float = 0.0
    emotional_weight: float = 0.1
    novelty: float = 0.1
    requires_answer: bool = False
    confidence: float = 0.5


@dataclass
class ConversationDecision:
    action: ConversationAction
    target_bot: Optional[str] = None
    emotional_tone: str = "neutral"
    content_goal: str = ""
    should_respond: bool = True
    max_sentences: int = 1
    allow_emoji: bool = True
    reason: str = ""
