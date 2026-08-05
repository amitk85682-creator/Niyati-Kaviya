import asyncio
import copy
from typing import Dict, Tuple, Optional, Callable
from datetime import datetime, timezone
from .models import CharacterRuntimeState, clamp, ConversationAction, ResponseOutcome, RecentResponse
from .profiles import get_character_traits

class EmotionalStateManager:
    """Async-safe manager for isolated character emotional states."""
    
    def __init__(self):
        # Key: (bot_name, chat_id, user_id) -> CharacterRuntimeState
        self._states: Dict[Tuple[str, int, int], CharacterRuntimeState] = {}
        self._lock = asyncio.Lock()
        
    async def get_state(self, bot_name: str, chat_id: int, user_id: int) -> CharacterRuntimeState:
        key = (bot_name.lower(), chat_id, user_id)
        async with self._lock:
            if key not in self._states:
                self._states[key] = CharacterRuntimeState(
                    bot_name=bot_name.lower(),
                    chat_id=chat_id,
                    user_id=user_id
                )
            return copy.deepcopy(self._states[key])
            
    async def save_state(self, state: CharacterRuntimeState):
        key = (state.bot_name.lower(), state.chat_id, state.user_id)
        async with self._lock:
            state.clamp_all()
            state.last_updated_at = datetime.now(timezone.utc)
            self._states[key] = copy.deepcopy(state)

    async def mutate_state(self, bot_name: str, chat_id: int, user_id: int, mutator: Callable[[CharacterRuntimeState], None]) -> CharacterRuntimeState:
        key = (bot_name.lower(), chat_id, user_id)
        async with self._lock:
            if key not in self._states:
                self._states[key] = CharacterRuntimeState(
                    bot_name=bot_name.lower(),
                    chat_id=chat_id,
                    user_id=user_id
                )
            
            # Deepcopy to isolate changes
            state_copy = copy.deepcopy(self._states[key])
            
            # Apply mutations inside the lock
            mutator(state_copy)
            
            # Validate and clamp
            state_copy.clamp_all()
            state_copy.last_updated_at = datetime.now(timezone.utc)
            
            # Save and return a fresh deepcopy to the caller
            self._states[key] = copy.deepcopy(state_copy)
            return copy.deepcopy(state_copy)
            
    async def record_response_outcome(self, bot_name: str, chat_id: int, user_id: int, outcome: ResponseOutcome, response_meta: Optional[RecentResponse] = None):
        key = (bot_name.lower(), chat_id, user_id)
        async with self._lock:
            if key in self._states:
                state = self._states[key]
                if outcome == ResponseOutcome.SUCCESS:
                    state.successful_response_count += 1
                    if response_meta:
                        state.recent_responses.append(response_meta)
                        if len(state.recent_responses) > 10:
                            state.recent_responses = state.recent_responses[-10:]
            
    async def reset_state(self, bot_name: str, chat_id: int, user_id: int):
        key = (bot_name.lower(), chat_id, user_id)
        async with self._lock:
            if key in self._states:
                del self._states[key]
                
    def apply_decay(self, state: CharacterRuntimeState, now: datetime):
        """
        Deterministic time-based decay of emotions.
        """
        elapsed = (now - state.last_updated_at).total_seconds()
        if elapsed <= 0:
            return
            
        hours = elapsed / 3600.0
        
        # Embarrassment decays completely in ~1 hour (0.017 per minute, ~1.0 per hour)
        decay_embarrassment = hours * 1.0
        state.mood.embarrassment = clamp(state.mood.embarrassment - decay_embarrassment)
        
        # Irritation decays in ~3 hours (0.33 per hour)
        decay_irritation = hours * 0.33
        state.mood.irritation = clamp(state.mood.irritation - decay_irritation)
        
        # Playfulness returns toward baseline (0.5) in ~2 hours (0.5 per hour)
        decay_playful = hours * 0.5
        if state.mood.playfulness > 0.5:
            state.mood.playfulness = clamp(state.mood.playfulness - decay_playful, min_val=0.5)
        elif state.mood.playfulness < 0.5:
            state.mood.playfulness = clamp(state.mood.playfulness + decay_playful, max_val=0.5)
            
        # Sadness decays in ~12 hours (0.08 per hour)
        decay_sadness = hours * 0.08
        state.mood.sadness = clamp(state.mood.sadness - decay_sadness)
        
        # Update last updated at so we don't decay again
        state.last_updated_at = now

state_manager = EmotionalStateManager()
