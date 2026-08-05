# Independent Bots Specification

This document outlines the identity configuration, backward compatibility rules, and the strict separation of concerns for the independent bots running in this project.

## Bot Identities

### Bot 1: Niyati
- **Internal ID:** `niyati`
- **Display Name:** Niyati
- **Username:** Configured through environment variable
- **Token:** `NIYATI_BOT_TOKEN`

### Bot 2: Palak
- **Internal ID:** `palak`
- **Display Name:** Palak Deva
- **Username:** `palakdevabot`
- **Token:** `PALAK_BOT_TOKEN`

## Architecture: Independent vs Shared State

### Separate (Independent) Resources
The following components and states must remain completely independent per bot instance:
- **AIEngine instance:** Each bot maintains its own AI engine.
- **AI provider/client state:** Independent connections and fallback states.
- **API-key rotation index:** Even though both bots may use the same API keys, their rotation indexes are independent.
- **Personality prompt:** Unique system prompts and backstories.
- **Mood:** Independent random mood generation.
- **Private-chat memory:** Fully isolated 1-on-1 conversations.
- **Private-chat user preferences:** Isolated settings per bot (e.g., meme toggles).
- **Rate-limit state:** Independent cooldowns and request tracking.
- **Last private conversation:** Independent tracking of the last interaction.
- **Response generation:** Completely isolated text generation pipelines.

### Shared Resources
Only group-level data is shared to enable cross-bot awareness and natural multi-participant conversations. The following are shared globally:
- **Group membership:** Bots share knowledge of group participants.
- **Group transcript:** The unified chat history of the group (users + both bots).
- **Active human conversation session:** Shared tracking of ongoing human interaction.
- **Telegram message deduplication:** Ensuring a group message is processed exactly once in the shared memory, even if received by both bots.
- **Turn coordination:** Deciding which bot responds or if they both respond in sequence.
- **Conversation depth:** Shared tracking of how deep the group thread has gone.
- **Last responder:** Tracking which bot spoke last to prevent talking over each other.
- **Partner-bot presence:** Awareness of the other bot's presence in the chat.

## Backward Compatibility Rules

- **Legacy Name Migration:** "Kavya" has been completely replaced by "Palak" (`kavya` -> `palak`). 
- Internal configurations, prompts, and memory mechanisms previously referencing Kavya should now point to Palak.
- Any legacy data or database records storing the internal ID as `kavya` must be migrated to `palak`.
