import re
from typing import Optional
from .models import AppraisalResult, RelationshipState, EmotionalInputContext

class AppraisalEngine:
    @staticmethod
    def appraise(context: EmotionalInputContext, relationship: Optional[RelationshipState] = None) -> AppraisalResult:
        text = context.text.lower()
        res = AppraisalResult()
        
        # 1. Target bot (from semantic target computed in orchestrator)
        res.target_bot = context.semantic_target_bot
        
        # Determine if directed to character
        if context.bot_name in text or f"@{context.bot_name}" in text or context.replied_to_bot_name == context.bot_name:
            res.directed_to_character = True
            res.target_bot = context.bot_name
        
        # "Arjun kon hai" logic -> Niyati
        if "arjun" in text:
            res.target_bot = "niyati"

        # Use director's resolved intent if provided (e.g. coreference)
        if context.turn_plan and context.turn_plan.resolved_intent != "unknown":
            res.intent = context.turn_plan.resolved_intent
            res.emotional_weight = 0.2
            res.requires_answer = True
            return res

        # 2. Intent & Rules
        is_correction_text = "maine niyati se" in text or "tujhse nahi pucha" in text or "maine palak se" in text
        if is_correction_text:
            # Only genuinely a correction if the character actually interrupted recently 
            # or the user replied directly to them
            if context.replied_to_bot_name == context.bot_name or context.previous_character_action is not None:
                res.intent = "correction"
                res.is_correction = True
                res.emotional_weight = 0.5
            else:
                res.intent = "statement"
                res.emotional_weight = 0.1
                
        elif any(w in text for w in ["i love you", "love you", "meri jaan", "pyaar karta", "pyar karta",
                                       "dil de diya", "tujhse pyaar", "love karta", "i luv u", "luv u",
                                       "tere bina", "jaanu", "meri jaanu"]):
            res.intent = "love_confession"
            res.emotional_weight = 0.7
            res.is_romantic_advance = True
            res.requires_answer = True
            
        elif any(w in text for w in ["sad", "dukhi", "rona", "toot", "depress", "akela", "rota"]):
            res.intent = "emotional_disclosure"
            res.is_emotional_disclosure = True
            res.is_user_sad = True
            res.emotional_weight = 0.8
            
        elif any(w in text for w in ["boring", "stupid", "pagal", "chup", "hate", "bakwas", "dumb"]):
            # Teasing vs Insult based on relationship
            if relationship and relationship.familiarity > 0.4:
                res.intent = "teasing"
                res.is_playful_teasing = True
                res.emotional_weight = 0.3
            else:
                res.intent = "insult"
                res.is_serious_insult = True
                res.emotional_weight = 0.6
                res.social_threat = 0.4
                
        elif any(w in text for w in ["jao so jao", "good night", "so jao", "go sleep"]):
            if context.turn_plan and context.turn_plan.active_topic == "current_feeling:sleepy":
                res.intent = "SUGGEST_SLEEP"
                res.emotional_weight = 0.3
            else:
                res.intent = "SUGGEST_SLEEP"
                res.emotional_weight = 0.2
                
        elif re.search(r'\b(hello|hey|hii|heyy)\b', text):
            # removed 'hi' from greeting to avoid 'bachhe aese hi hote hain' mismatch
            res.intent = "greeting"
            res.emotional_weight = 0.1
            
        elif any(w in text for w in ["chali jao", "chale jao", "nikalo", "yaha se jao", "leave me alone", "akela chhodo"]):
            res.intent = "REQUEST_CHAT_LEAVE"
            res.emotional_weight = 0.8
            res.is_serious_insult = True
            
        elif text.strip() in ["acha", "hmm", "ok", "okay", "accha"]:
            res.intent = "acknowledgement"
            res.emotional_weight = 0.1
            res.requires_answer = False
            
        elif "kaha se ho" in text:
            res.intent = "ASK_ORIGIN"
            res.is_question = True
            res.requires_answer = True
            
        elif "kahan ho" in text or "kaha ho" in text:
            res.intent = "ASK_CURRENT_LOCATION"
            res.is_question = True
            res.requires_answer = True
            
        elif "kya kar rahi ho" in text or "kya kr rhi" in text:
            res.intent = "ASK_CURRENT_ACTIVITY"
            res.is_question = True
            res.requires_answer = True
            
        elif "?" in text or any(w in text.split() for w in ["kya", "kaise", "kyu", "kon", "kab", "kahan", "kaha"]):
            res.intent = "question"
            res.is_question = True
            res.emotional_weight = 0.2
            res.requires_answer = True
            
        elif "hi hote hai" in text or "hi hote hain" in text:
            res.intent = "TOPIC_COMMENT"
            res.emotional_weight = 0.1
            
        else:
            res.intent = "casual_update"
            res.emotional_weight = 0.2
            
        return res
