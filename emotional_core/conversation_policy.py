from .models import CharacterRuntimeState, AppraisalResult, ConversationDecision, ConversationAction, EmotionalInputContext

class ConversationPolicy:
    @staticmethod
    def decide_action(state: CharacterRuntimeState, appraisal: AppraisalResult, is_group: bool, context: EmotionalInputContext = None) -> ConversationDecision:
        decision = ConversationDecision(action=ConversationAction.ANSWER, should_respond=True)
        
        if appraisal.is_correction and context:
            repair_event = next((e for e in state.unresolved_events if e.type == "repair_interruption" and not e.resolved), None)
            
            is_direct_reply = (context.replied_to_bot_name == state.bot_name)
            
            recent_resp = state.recent_responses[-1] if state.recent_responses else None
            is_recent_interrupter = False
            if recent_resp and recent_resp.responding_bot == state.bot_name and recent_resp.source_target_bot and recent_resp.source_target_bot != state.bot_name:
                is_recent_interrupter = True
                
            if is_direct_reply or is_recent_interrupter or repair_event:
                decision.action = ConversationAction.REPAIR_MISTAKE
                decision.content_goal = "briefly admit interruption, do not defend or blame the user"
                decision.reason = "repairing_interruption"
                if repair_event:
                    repair_event.resolved = True
                return decision
            
        # B. Message directed to another bot
        if appraisal.target_bot and appraisal.target_bot != state.bot_name:
            decision.action = ConversationAction.STAY_SILENT
            decision.should_respond = False
            decision.reason = f"message_targeted_to_{appraisal.target_bot}"
            return decision
            
        # C. Familiar user says "tum boring ho yrr"
        if appraisal.is_playful_teasing:
            decision.action = ConversationAction.TEASE
            decision.content_goal = "tease back briefly without becoming defensive"
            decision.reason = "playful_teasing"
            return decision
            
        # D. Repeated serious insult (or single based on high irritation)
        if appraisal.is_serious_insult or state.mood.irritation > 0.7:
            decision.action = ConversationAction.SET_BOUNDARY
            decision.content_goal = "set boundary calmly but firmly"
            decision.reason = "serious_insult_or_high_irritation"
            return decision
            
        # E. User says "main sad hu"
        if appraisal.is_user_sad:
            decision.action = ConversationAction.ACKNOWLEDGE
            decision.content_goal = "acknowledge sadness empathetically, no teasing"
            decision.reason = "user_sadness"
            decision.allow_emoji = False
            return decision
            
        # F. Simple "acha"
        if appraisal.intent == "acknowledgement":
            if is_group:
                # G. If nothing distinct to add in group
                decision.action = ConversationAction.STAY_SILENT
                decision.should_respond = False
                decision.reason = "group_acknowledgement_silence"
            else:
                decision.action = ConversationAction.ACKNOWLEDGE
                decision.content_goal = "brief acknowledgement, do not force a question"
                decision.reason = "simple_acknowledgement"
            return decision

        # Default fallback
        if not appraisal.requires_answer and is_group and state.mood.energy < 0.3:
            decision.action = ConversationAction.STAY_SILENT
            decision.should_respond = False
            decision.reason = "low_energy_group_silence"
            
        return decision
