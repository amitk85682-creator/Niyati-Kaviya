import re
from typing import Optional
from .models import AppraisalResult, RelationshipState

class AppraisalEngine:
    @staticmethod
    def appraise(message_text: str, reply_to_bot: Optional[str] = None, relationship: Optional[RelationshipState] = None) -> AppraisalResult:
        text = message_text.lower()
        res = AppraisalResult()
        
        # 1. Target bot (from reply or explicit mention)
        res.target_bot = reply_to_bot
        if not res.target_bot:
            if "niyati" in text and "palak" not in text:
                res.target_bot = "niyati"
            elif "palak" in text and "niyati" not in text:
                res.target_bot = "palak"
                
        # "Arjun kon hai" logic -> Niyati
        if "arjun" in text:
            res.target_bot = "niyati"

        # 2. Intent & Rules
        if "maine niyati se" in text or "tujhse nahi pucha" in text or "maine palak se" in text:
            res.intent = "correction"
            res.is_correction = True
            res.emotional_weight = 0.5
            
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
                
        elif text.strip() in ["hi", "hello", "hey", "hii", "heyy"]:
            res.intent = "greeting"
            res.emotional_weight = 0.1
            
        elif text.strip() in ["acha", "hmm", "ok", "okay", "accha"]:
            res.intent = "acknowledgement"
            res.emotional_weight = 0.1
            res.requires_answer = False
            
        elif "?" in text or any(w in text.split() for w in ["kya", "kaise", "kyu", "kon", "kab", "kahan", "kaha"]):
            res.intent = "question"
            res.is_question = True
            res.emotional_weight = 0.2
            res.requires_answer = True
            
        else:
            res.intent = "casual_update"
            res.emotional_weight = 0.2
            
        return res
