from .models import CharacterRuntimeState, AppraisalResult
from .profiles import get_character_traits

class EmotionEngine:
    @staticmethod
    def apply_appraisal(state: CharacterRuntimeState, appraisal: AppraisalResult):
        traits = get_character_traits(state.bot_name)
        
        # 1. Update relationship based on general interaction
        state.relationship.interaction_count += 1
        
        # Slowly increase familiarity and trust with respectful repeated interaction
        if not appraisal.is_serious_insult and not appraisal.social_threat:
            inc = 0.01 * traits.get("warmth", 0.5)
            state.relationship.familiarity += inc
            if appraisal.is_emotional_disclosure:
                state.relationship.trust += 0.02
            else:
                state.relationship.trust += 0.005
                
        # 2. Specific Intent Rules
        if appraisal.is_playful_teasing:
            # increase playfulness, small irritation increase or none, do not reduce trust
            state.mood.playfulness += 0.1 * traits.get("playfulness", 0.5)
            state.mood.irritation += 0.02 * (1.0 - traits.get("patience", 0.5))
            
        elif appraisal.is_serious_insult:
            # increase irritation, guardedness, reduce warmth and respect
            state.mood.irritation += 0.2 * traits.get("sensitivity", 0.5)
            state.relationship.guardedness += 0.15
            state.relationship.warmth -= 0.05
            state.relationship.respect -= 0.05
            
        elif appraisal.is_correction:
            # increase embarrassment, reduce confidence, create unresolved event
            state.mood.embarrassment += 0.3 * traits.get("sensitivity", 0.5)
            state.mood.confidence -= 0.1
            if "repair_interruption" not in state.unresolved_events:
                state.unresolved_events.append("repair_interruption")
                
        elif appraisal.is_user_sad:
            # reduce playfulness, increase social openness, increase connection need
            state.mood.playfulness -= 0.2
            state.mood.social_openness += 0.1 * traits.get("warmth", 0.5)
            state.needs.connection += 0.15
            
        # 3. Update stage
        if state.relationship.interaction_count > 10 and state.relationship.familiarity > 0.3:
            state.relationship.stage = "familiar"
            
        # Clamp all values at the end
        state.clamp_all()
