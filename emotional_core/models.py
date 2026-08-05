from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, FrozenSet
from datetime import datetime, timezone
from enum import Enum


# ════════════════════════════════════════════════════════════════════
# SHARED WORLD STATE  –  Immutable relationship facts shared by both bots
# ════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class SharedWorldState:
    """Stable public facts that both bots must never contradict."""
    # Palak and Niyati are close friends
    friends: FrozenSet[str] = frozenset({"niyati", "palak"})

    def are_friends(self, bot_a: str, bot_b: str) -> bool:
        return bot_a in self.friends and bot_b in self.friends

    def is_friend_of_bot(self, person_name: str, bot_name: str) -> bool:
        """Return True if person_name is the other bot and they are friends."""
        return person_name in self.friends and bot_name in self.friends and person_name != bot_name

# Singleton – import this everywhere
SHARED_WORLD = SharedWorldState()


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


class ResponseOutcome(Enum):
    SUCCESS = "SUCCESS"
    FAILED_GENERATION = "FAILED_GENERATION"
    FAILED_SEND = "FAILED_SEND"
    PARTIAL_SEND = "PARTIAL_SEND"
    SUPPRESSED = "SUPPRESSED"


@dataclass
class RecentResponse:
    responding_bot: str
    user_id: int
    source_human_message_id: int
    source_target_bot: Optional[str]
    sent_bot_message_id: int
    action: ConversationAction
    created_at: datetime


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
class DialogueState:
    stance: str = "NEUTRAL"
    consecutive_hostility_count: int = 0
    active_topic: str = ""
    active_topic_owner: str = ""
    last_user_intent: str = ""
    last_character_action: str = ""
    unresolved_boundary: bool = False
    withdrawn_until: Optional[datetime] = None
    support_mode_active: bool = False
    last_civil_message_at: Optional[datetime] = None
    recent_phrase_fingerprints: List[str] = field(default_factory=list)


@dataclass
class CharacterRuntimeState:
    bot_name: str
    chat_id: int
    user_id: int
    mood: MoodState = field(default_factory=MoodState)
    needs: NeedState = field(default_factory=NeedState)
    relationship: RelationshipState = field(default_factory=RelationshipState)
    daily_life: DailyLifeState = field(default_factory=DailyLifeState)
    dialogue: DialogueState = field(default_factory=DialogueState)
    unresolved_events: List[UnresolvedEvent] = field(default_factory=list)
    recent_responses: List[RecentResponse] = field(default_factory=list)
    successful_response_count: int = 0
    processed_events: List[str] = field(default_factory=list)
    claims: Dict[str, 'CharacterClaim'] = field(default_factory=dict)
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
    turn_plan: Optional['TurnPlan'] = None


@dataclass
class AppraisalResult:
    target_bot: Optional[str] = None
    intent: str = "unknown"
    tone: str = "neutral"
    is_question: bool = False
    is_correction: bool = False
    is_emotional_disclosure: bool = False
    is_serious_insult: bool = False
    is_playful_teasing: bool = False
    is_user_sad: bool = False
    directed_to_character: bool = False
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

@dataclass(frozen=True, slots=True)
class TurnPlan:
    chat_id: int
    human_user_id: int
    human_message_id: int
    selected_bots: tuple[str, ...]
    primary_bot: Optional[str] = None
    explicit_target: Optional[str] = None
    active_bot: Optional[str] = None
    referenced_bot: Optional[str] = None
    referenced_message_id: Optional[int] = None
    active_topic: Optional[str] = None
    resolved_intent: str = "unknown"
    reference_type: Optional[str] = None
    normalized_question: Optional[str] = None
    reason: str = ""
    conversation_session_id: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    is_both_turn: bool = False
    # Per-bot prompt override for both-turns: tuple of (bot_name, prompt) pairs
    bot_prompts: tuple = ()  # tuple[tuple[str, str], ...]

    def get_bot_prompt(self, bot_name: str) -> Optional[str]:
        for b, p in self.bot_prompts:
            if b == bot_name:
                return p
        return None

@dataclass
class ConversationSession:
    chat_id: int
    user_id: int
    active_bot: Optional[str] = None
    active_since: Optional[datetime] = None
    last_human_message_id: Optional[int] = None
    last_bot_message_id: Optional[int] = None
    last_bot_name: Optional[str] = None
    last_topic: Optional[str] = None
    last_explicit_target: Optional[str] = None
    pending_question: Optional[str] = None
    recent_turns: int = 0
    expires_at: Optional[datetime] = None
    processed_outcomes: set[tuple[int, str]] = field(default_factory=set)
    # Discourse referent tracking
    last_person_entity: Optional[str] = None          # e.g. "niyati" after referent resolved
    pending_ambiguous_question: Optional[str] = None   # original ambiguous question text
    clarification_expected: bool = False               # True when we sent an ambiguous question
    clarification_target_bot: Optional[str] = None     # which bot should answer after clarification
    last_relation_reference: Optional[str] = None      # e.g. "friend", "dost"

@dataclass
class CharacterClaim:
    bot_name: str
    claim_type: str
    value: str
    reason: str
    source_human_message_id: int
    source_bot_message_id: int
    created_at: datetime
    valid_until: Optional[datetime] = None
    superseded: bool = False
    confidence: float = 1.0
