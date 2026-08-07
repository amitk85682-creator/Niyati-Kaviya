import random
from typing import Optional
from media_models import CharacterMedia
from media_vault import MediaVault
from config import Config

class MediaSelector:
    @staticmethod
    async def select_media(bot_name: str, 
                           request_type: str = "", 
                           scene: str = None, 
                           outfit: str = None,
                           mood: str = None) -> Optional[CharacterMedia]:
        """Score and select the most appropriate media based on context"""
        all_media = await MediaVault.get_all_media(bot_name)
        if not all_media:
            return None
            
        scored_media = []
        for media in all_media:
            score = 0.0
            
            # Penalize highly used media to encourage variety
            score -= (media.use_count * 0.1)
            
            # Request specific boosting
            if request_type == 'outfit':
                if 'outfit' in media.use_for or media.outfit:
                    score += 3.0
                elif media.pose == 'selfie':
                    score += 1.5
                    
            if request_type == 'location':
                if 'location' in media.use_for or media.scene:
                    score += 3.0
                    
            if request_type == 'selfie' or request_type == 'general':
                if media.pose == 'selfie':
                    score += 2.0
                
            # Context matching
            if scene and media.scene and scene.lower() in media.scene.lower():
                score += 3.0
            if outfit and media.outfit and outfit.lower() in media.outfit.lower():
                score += 3.0
            if mood and media.mood and mood.lower() == media.mood.lower():
                score += 1.0
                
            # Prefer random share if spontaneous
            if request_type == 'spontaneous' and 'random_share' in media.use_for:
                score += 2.0
                
            # Add to candidates
            scored_media.append((score, media))
            
        if not scored_media:
            return None
            
        # For spontaneous shares, if the best score is very bad (e.g. all heavily used), we might want to abort
        # But for direct requests, we ALWAYS return the best available.
        # Sort by score descending
        scored_media.sort(key=lambda x: x[0], reverse=True)
        
        if request_type == 'spontaneous' and scored_media[0][0] < -3.0:
            return None
        
        # Take top candidates and introduce slight variety
        top_score = scored_media[0][0]
        # Filter candidates that are close to the top score
        candidates = [m for s, m in scored_media if top_score - s <= 1.5]
        
        if not candidates:
            return None
            
        # Pick one randomly from top candidates
        return random.choice(candidates[:Config.MEDIA_MAX_RESULTS if hasattr(Config, 'MEDIA_MAX_RESULTS') else 3])
