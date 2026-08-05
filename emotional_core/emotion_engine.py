from datetime import datetime, timezone
from .models import CharacterRuntimeState, AppraisalResult, clamp, UnresolvedEvent
from .profiles import get_character_traits

class EmotionEngine:
    @staticmethod
    def apply_appraisal(state: CharacterRuntimeState, appraisal: AppraisalResult, message_id: int):
        traits = get_character_traits(state.bot_name)
        
        # 1. Update relationship based on general interaction
        state.relationship.interaction_count += 1
        
        # Slowly increase familiarity and trust with respectful repeated interaction
        if not appraisal.is_serious_insult and not appraisal.social_threat:
            inc = 0.01 * traits.get("warmth", 0.5)
            state.relationship.familiarity = clamp(state.relationship.familiarity + inc)
            if appraisal.is_emotional_disclosure:
                state.relationship.trust = clamp(state.relationship.trust + 0.02)
            else:
                state.relationship.trust = clamp(state.relationship.trust + 0.005)
                
        # 2. Specific Intent Rules
        if appraisal.is_playful_teasing:
            # increase playfulness, small irritation increase or none, do not reduce trust
            state.mood.playfulness = clamp(state.mood.playfulness + 0.1 * traits.get("playfulness", 0.5))
            state.mood.irritation = clamp(state.mood.irritation + 0.02 * (1.0 - traits.get("patience", 0.5)))
            
        elif appraisal.is_serious_insult:
            # increase irritation, guardedness, reduce warmth and respect
            state.mood.irritation = clamp(state.mood.irritation + 0.2 * traits.get("sensitivity", 0.5))
            state.relationship.guardedness = clamp(state.relationship.guardedness + 0.15)
            state.relationship.warmth = clamp(state.relationship.warmth - 0.05)
            state.relationship.respect = clamp(state.relationship.respect - 0.05)
            
        elif appraisal.is_correction:
            # increase embarrassment, reduce confidence, create unresolved event
            state.mood.embarrassment = clamp(state.mood.embarrassment + 0.3 * traits.get("sensitivity", 0.5))
            state.mood.confidence = clamp(state.mood.confidence - 0.1)
            
            # Check if event already exists
            exists = any(e.type == "repair_interruption" and not e.resolved for e in state.unresolved_events)
            if not exists:
                evt = UnresolvedEvent(
                    type="repair_interruption",
                    source_message_id=message_id,
                    target_bot=state.bot_name,
                    created_at=datetime.now(timezone.utc),
                    resolved=False,
                    intensity=0.5
                )
                state.unresolved_events.append(evt)
                
        elif appraisal.is_user_sad:
            # reduce playfulness, increase social openness, increase connection need
            state.mood.playfulness = clamp(state.mood.playfulness - 0.2)
            state.mood.social_openness = clamp(state.mood.social_openness + 0.1 * traits.get("warmth", 0.5))
            state.needs.connection = clamp(state.needs.connection + 0.15)
            
        # 3. Update stage
        if state.relationship.interaction_count > 10 and state.relationship.familiarity > 0.3:
            state.relationship.stage = "familiar"
            
        # Clamp all values at the end just to be sure
        state.clamp_all()
