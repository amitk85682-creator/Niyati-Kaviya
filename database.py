"""
╔══════════════════════════════════════════════════════╗
║           DATABASE MANAGER                            ║
║   Supabase REST API + Local Fallback (Bot-Aware)      ║
╚══════════════════════════════════════════════════════╝
"""

import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, List
from collections import defaultdict, deque

import httpx

from config import Config, logger


# ============================================================================
# SUPABASE CLIENT
# ============================================================================

class SupabaseClient:
    """Custom Supabase REST API Client with connection pooling"""

    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key
        self.headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        }
        self.rest_url = f"{self.url}/rest/v1"
        self._client = None
        self._verified = False
        self._lock = asyncio.Lock()
        logger.info("✅ SupabaseClient initialized")

    def _get_client(self) -> httpx.AsyncClient:
        """Get or create async client with connection pooling"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                headers=self.headers,
                timeout=30.0,
                limits=httpx.Limits(max_keepalive_connections=10, max_connections=20)
            )
        return self._client

    async def close(self):
        """Close the client"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            logger.info("✅ Supabase client closed")

    async def verify_connection(self) -> bool:
        """Verify database connection and tables exist"""
        if self._verified:
            return True

        async with self._lock:
            if self._verified:
                return True

            try:
                client = self._get_client()
                response = await client.get(f"{self.rest_url}/users?select=user_id&limit=1")

                if response.status_code == 200:
                    self._verified = True
                    logger.info("✅ Supabase tables verified")
                    return True
                elif response.status_code == 404:
                    logger.error("❌ Supabase table 'users' not found!")
                    return False
                else:
                    logger.error(f"❌ Supabase verification failed: {response.status_code}")
                    return False
            except Exception as e:
                logger.error(f"❌ Supabase connection error: {e}")
                return False

    async def select(self, table: str, columns: str = '*',
                     filters: Dict = None, limit: int = None) -> List[Dict]:
        """SELECT from table"""
        try:
            client = self._get_client()
            url = f"{self.rest_url}/{table}?select={columns}"

            if filters:
                for key, value in filters.items():
                    url += f"&{key}=eq.{value}"

            if limit:
                url += f"&limit={limit}"

            response = await client.get(url)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 404:
                return []
            else:
                logger.error(f"Supabase SELECT error {response.status_code}: {response.text}")
                return []

        except Exception as e:
            logger.error(f"Supabase SELECT exception: {e}")
            return []

    async def insert(self, table: str, data: Dict) -> Optional[Dict]:
        """INSERT into table"""
        try:
            client = self._get_client()
            url = f"{self.rest_url}/{table}"

            response = await client.post(url, json=data)

            if response.status_code in [200, 201]:
                result = response.json()
                return result[0] if isinstance(result, list) and result else data
            elif response.status_code == 409:
                return data
            else:
                logger.error(f"Supabase INSERT error {response.status_code}: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Supabase INSERT exception: {e}")
            return None

    async def update(self, table: str, data: Dict, filters: Dict) -> Optional[Dict]:
        """UPDATE table"""
        try:
            client = self._get_client()
            filter_parts = [f"{key}=eq.{value}" for key, value in filters.items()]
            url = f"{self.rest_url}/{table}?" + "&".join(filter_parts)

            response = await client.patch(url, json=data)

            if response.status_code == 200:
                result = response.json()
                return result[0] if isinstance(result, list) and result else data
            else:
                logger.error(f"Supabase UPDATE error {response.status_code}: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Supabase UPDATE exception: {e}")
            return None

    async def upsert(self, table: str, data: Dict) -> Optional[Dict]:
        """UPSERT (insert or update) into table"""
        try:
            client = self._get_client()
            url = f"{self.rest_url}/{table}"

            headers = self.headers.copy()
            headers['Prefer'] = 'resolution=merge-duplicates,return=representation'

            response = await client.post(url, json=data, headers=headers)

            if response.status_code in [200, 201]:
                result = response.json()
                return result[0] if isinstance(result, list) and result else data
            else:
                logger.error(f"Supabase UPSERT error {response.status_code}: {response.text}")
                return None

        except Exception as e:
            logger.error(f"Supabase UPSERT exception: {e}")
            return None

    async def delete(self, table: str, filters: Dict) -> bool:
        """DELETE from table"""
        try:
            client = self._get_client()
            filter_parts = [f"{key}=eq.{value}" for key, value in filters.items()]
            url = f"{self.rest_url}/{table}?" + "&".join(filter_parts)

            response = await client.delete(url)
            return response.status_code in [200, 204]

        except Exception as e:
            logger.error(f"Supabase DELETE exception: {e}")
            return False


# ============================================================================
# DATABASE MANAGER
# ============================================================================

class Database:
    """
    Database manager with Supabase REST API + Local fallback.
    Bot-aware: uses bot_name to isolate data between Niyati & Kavya.
    """

    def __init__(self):
        self.client: Optional[SupabaseClient] = None
        self.connected = False
        self._initialized = False
        self._lock = asyncio.Lock()

        # Local cache (fallback)
        self.local_users: Dict[str, Dict] = {}       # key: "{bot_name}_{user_id}"
        self.local_groups: Dict[str, Dict] = {}       # key: "{bot_name}_{chat_id}"
        self.local_group_messages: Dict[int, deque] = defaultdict(lambda: deque(maxlen=Config.MAX_GROUP_MESSAGES))
        self.local_activities: deque = deque(maxlen=1000)

        # Cache access tracking
        self._user_access_times: Dict[str, datetime] = {}
        self._group_access_times: Dict[str, datetime] = {}

        logger.info("✅ Database manager initialized")

    def _user_key(self, bot_name: str, user_id: int) -> str:
        """Composite key for per-bot user isolation"""
        return f"{bot_name}_{user_id}"

    def _group_key(self, bot_name: str, chat_id: int) -> str:
        """Composite key for per-bot group isolation"""
        return f"{bot_name}_{chat_id}"

    async def initialize(self):
        """Initialize database connection"""
        async with self._lock:
            if self._initialized:
                return

            if Config.SUPABASE_URL and Config.SUPABASE_KEY:
                try:
                    self.client = SupabaseClient(
                        Config.SUPABASE_URL.strip(),
                        Config.SUPABASE_KEY.strip()
                    )

                    self.connected = await self.client.verify_connection()

                    if self.connected:
                        logger.info("✅ Supabase connected and verified")
                    else:
                        logger.warning("⚠️ Supabase verification failed - using local storage")

                except Exception as e:
                    logger.error(f"❌ Supabase init failed: {e}")
                    self.connected = False
            else:
                logger.warning("⚠️ Supabase not configured - using local storage")
                self.connected = False

            self._initialized = True

    async def cleanup_local_cache(self):
        """Cleanup old entries from local cache"""
        now = datetime.now(timezone.utc)
        cutoff_time = now - timedelta(hours=24)

        # Cleanup users
        if len(self.local_users) > Config.MAX_LOCAL_USERS_CACHE:
            to_remove = [k for k, t in self._user_access_times.items() if t < cutoff_time]
            for k in to_remove[:len(self.local_users) - Config.MAX_LOCAL_USERS_CACHE]:
                self.local_users.pop(k, None)
                self._user_access_times.pop(k, None)
            if to_remove:
                logger.info(f"🧹 Cleaned {len(to_remove)} users from cache")

        # Cleanup groups
        if len(self.local_groups) > Config.MAX_LOCAL_GROUPS_CACHE:
            to_remove = [k for k, t in self._group_access_times.items() if t < cutoff_time]
            for k in to_remove[:len(self.local_groups) - Config.MAX_LOCAL_GROUPS_CACHE]:
                self.local_groups.pop(k, None)
                self._group_access_times.pop(k, None)
            if to_remove:
                logger.info(f"🧹 Cleaned {len(to_remove)} groups from cache")

    # ========== USER OPERATIONS ==========

    async def get_or_create_user(self, bot_name: str, user_id: int,
                                  first_name: str = None, username: str = None) -> Dict:
        """Get or create user (bot-aware)"""
        key = self._user_key(bot_name, user_id)
        self._user_access_times[key] = datetime.now(timezone.utc)

        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', '*', {'user_id': user_id})

                if users_list and len(users_list) > 0:
                    user = users_list[0]

                    if first_name and user.get('first_name') != first_name:
                        await self.client.update('users', {
                            'first_name': first_name,
                            'username': username,
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }, {'user_id': user_id})
                    return user
                else:
                    new_user = {
                        'user_id': user_id,
                        'first_name': first_name or 'User',
                        'username': username,
                        'messages': json.dumps([]),
                        'preferences': json.dumps({
                            'meme_enabled': True,
                            'shayari_enabled': True,
                            'geeta_enabled': True
                        }),
                        'total_messages': 0,
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    result = await self.client.insert('users', new_user)
                    logger.info(f"✅ New user created: {user_id} ({first_name})")
                    return result or new_user

            except Exception as e:
                logger.error(f"❌ Database user error: {e}")

        # Fallback to local cache
        if key not in self.local_users:
            self.local_users[key] = {
                'user_id': user_id,
                'first_name': first_name or 'User',
                'username': username,
                'messages': [],
                'preferences': {
                    'meme_enabled': True,
                    'shayari_enabled': True,
                    'geeta_enabled': True
                },
                'total_messages': 0,
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            logger.info(f"✅ New user (local): {user_id} ({first_name}) for {bot_name}")

        return self.local_users[key]

    async def get_user_context(self, bot_name: str, user_id: int) -> List[Dict]:
        """Get user conversation context (bot-aware)"""
        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'messages', {'user_id': user_id})
                if users_list and len(users_list) > 0:
                    messages = users_list[0].get('messages', '[]')
                    if isinstance(messages, str):
                        try:
                            messages = json.loads(messages)
                        except:
                            messages = []
                    if not isinstance(messages, list):
                        messages = []
                    return messages[-Config.MAX_PRIVATE_MESSAGES:]
            except Exception as e:
                logger.debug(f"Get context error: {e}")

        key = self._user_key(bot_name, user_id)
        if key in self.local_users:
            return self.local_users[key].get('messages', [])[-Config.MAX_PRIVATE_MESSAGES:]

        return []

    async def save_message(self, bot_name: str, user_id: int, role: str, content: str):
        """Save message to user history (bot-aware)"""
        new_msg = {
            'role': role,
            'content': content,
            'bot': bot_name,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'messages,total_messages', {'user_id': user_id})

                if users_list and len(users_list) > 0:
                    user_data = users_list[0]
                    messages = user_data.get('messages', '[]')
                    if isinstance(messages, str):
                        try:
                            messages = json.loads(messages)
                        except:
                            messages = []
                    if not isinstance(messages, list):
                        messages = []

                    messages.append(new_msg)
                    messages = messages[-Config.MAX_PRIVATE_MESSAGES:]
                    total = user_data.get('total_messages', 0) + 1

                    await self.client.update('users', {
                        'messages': json.dumps(messages),
                        'total_messages': total,
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }, {'user_id': user_id})
                return
            except Exception as e:
                logger.debug(f"Save message error: {e}")

        # Local fallback
        key = self._user_key(bot_name, user_id)
        if key in self.local_users:
            if 'messages' not in self.local_users[key]:
                self.local_users[key]['messages'] = []
            self.local_users[key]['messages'].append(new_msg)
            self.local_users[key]['messages'] = \
                self.local_users[key]['messages'][-Config.MAX_PRIVATE_MESSAGES:]
            self.local_users[key]['total_messages'] = \
                self.local_users[key].get('total_messages', 0) + 1

    async def clear_user_memory(self, bot_name: str, user_id: int):
        """Clear user conversation memory"""
        if self.connected and self.client:
            try:
                await self.client.update('users', {
                    'messages': json.dumps([]),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }, {'user_id': user_id})
                logger.info(f"Memory cleared for user: {user_id} ({bot_name})")
                return
            except Exception as e:
                logger.debug(f"Clear memory error: {e}")

        key = self._user_key(bot_name, user_id)
        if key in self.local_users:
            self.local_users[key]['messages'] = []

    async def update_preference(self, bot_name: str, user_id: int, key_name: str, value: bool):
        """Update user preference"""
        pref_key = f"{key_name}_enabled"

        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'preferences', {'user_id': user_id})

                if users_list and len(users_list) > 0:
                    prefs = users_list[0].get('preferences', '{}')
                    if isinstance(prefs, str):
                        try:
                            prefs = json.loads(prefs)
                        except:
                            prefs = {}

                    prefs[pref_key] = value

                    await self.client.update('users', {
                        'preferences': json.dumps(prefs),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }, {'user_id': user_id})
                return
            except Exception as e:
                logger.debug(f"Update preference error: {e}")

        key = self._user_key(bot_name, user_id)
        if key in self.local_users:
            if 'preferences' not in self.local_users[key]:
                self.local_users[key]['preferences'] = {}
            self.local_users[key]['preferences'][pref_key] = value

    async def get_user_preferences(self, bot_name: str, user_id: int) -> Dict:
        """Get user preferences"""
        if self.connected and self.client:
            try:
                users_list = await self.client.select('users', 'preferences', {'user_id': user_id})

                if users_list and len(users_list) > 0:
                    prefs = users_list[0].get('preferences', '{}')
                    if isinstance(prefs, str):
                        try:
                            prefs = json.loads(prefs)
                        except:
                            prefs = {}
                    return prefs
            except Exception as e:
                logger.debug(f"Get preferences error: {e}")

        key = self._user_key(bot_name, user_id)
        if key in self.local_users:
            return self.local_users[key].get('preferences', {})

        return {'meme_enabled': True, 'shayari_enabled': True, 'geeta_enabled': True}

    async def get_all_users(self) -> List[Dict]:
        """Get ALL users with Pagination"""
        if self.connected and self.client:
            try:
                all_data = []
                offset = 0
                limit = 1000

                while True:
                    url = f"{self.client.rest_url}/users?select=user_id,first_name,username&offset={offset}&limit={limit}"
                    client = self.client._get_client()
                    response = await client.get(url)

                    data = response.json()
                    if not data:
                        break

                    all_data.extend(data)
                    if len(data) < limit:
                        break

                    offset += limit

                return all_data
            except Exception as e:
                logger.error(f"Get all users error: {e}")
                return []

        # Local: return unique users across all bots
        seen = {}
        for k, v in self.local_users.items():
            uid = v.get('user_id')
            if uid and uid not in seen:
                seen[uid] = v
        return list(seen.values())

    async def get_user_count(self) -> int:
        """Get total user count"""
        if self.connected and self.client:
            try:
                users = await self.client.select('users', 'user_id')
                return len(users)
            except Exception as e:
                logger.debug(f"User count error: {e}")
        # Count unique user IDs from local cache
        unique_ids = set()
        for v in self.local_users.values():
            uid = v.get('user_id')
            if uid:
                unique_ids.add(uid)
        return len(unique_ids)

    # ========== GROUP OPERATIONS ==========

    async def get_or_create_group(self, bot_name: str, chat_id: int, title: str = None) -> Dict:
        """Get or create group (bot-aware)"""
        key = self._group_key(bot_name, chat_id)
        self._group_access_times[key] = datetime.now(timezone.utc)

        if self.connected and self.client:
            try:
                groups_list = await self.client.select('groups', '*', {'chat_id': chat_id})

                if groups_list and len(groups_list) > 0:
                    group = groups_list[0]
                    if title and group.get('title') != title:
                        await self.client.update('groups', {
                            'title': title,
                            'updated_at': datetime.now(timezone.utc).isoformat()
                        }, {'chat_id': chat_id})
                    return group
                else:
                    new_group = {
                        'chat_id': chat_id,
                        'title': title or 'Unknown Group',
                        'settings': json.dumps({
                            'geeta_enabled': True,
                            'welcome_enabled': True
                        }),
                        'created_at': datetime.now(timezone.utc).isoformat(),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }
                    result = await self.client.insert('groups', new_group)
                    logger.info(f"✅ New group: {chat_id} ({title})")
                    return result or new_group

            except Exception as e:
                logger.debug(f"Group error: {e}")

        # Fallback to local cache
        if key not in self.local_groups:
            self.local_groups[key] = {
                'chat_id': chat_id,
                'title': title or 'Unknown Group',
                'settings': {'geeta_enabled': True, 'welcome_enabled': True},
                'created_at': datetime.now(timezone.utc).isoformat()
            }
            logger.info(f"✅ New group (local): {chat_id} ({title}) for {bot_name}")

        return self.local_groups[key]

    async def update_group_settings(self, bot_name: str, chat_id: int, key_name: str, value: bool):
        """Update group settings"""
        if self.connected and self.client:
            try:
                groups_list = await self.client.select('groups', 'settings', {'chat_id': chat_id})

                if groups_list and len(groups_list) > 0:
                    settings = groups_list[0].get('settings', '{}')
                    if isinstance(settings, str):
                        try:
                            settings = json.loads(settings)
                        except:
                            settings = {}

                    settings[key_name] = value

                    await self.client.update('groups', {
                        'settings': json.dumps(settings),
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }, {'chat_id': chat_id})
                return
            except Exception as e:
                logger.debug(f"Update group settings error: {e}")

        key = self._group_key(bot_name, chat_id)
        if key in self.local_groups:
            if 'settings' not in self.local_groups[key]:
                self.local_groups[key]['settings'] = {}
            self.local_groups[key]['settings'][key_name] = value

    async def get_group_settings(self, bot_name: str, chat_id: int) -> Dict:
        """Get group settings"""
        if self.connected and self.client:
            try:
                groups_list = await self.client.select('groups', 'settings', {'chat_id': chat_id})

                if groups_list and len(groups_list) > 0:
                    settings = groups_list[0].get('settings', '{}')
                    if isinstance(settings, str):
                        try:
                            settings = json.loads(settings)
                        except:
                            settings = {}
                    return settings
            except Exception as e:
                logger.debug(f"Get group settings error: {e}")

        key = self._group_key(bot_name, chat_id)
        if key in self.local_groups:
            return self.local_groups[key].get('settings', {})

        return {'geeta_enabled': True, 'welcome_enabled': True}

    async def get_group_fsub_targets(self, main_chat_id: int) -> List[Dict]:
        """Get required channels for a group"""
        if self.connected and self.client:
            try:
                result = await self.client.select(
                    'group_fsub_map',
                    'target_chat_id,target_link',
                    {'main_chat_id': main_chat_id}
                )
                return result if result else []
            except Exception as e:
                logger.error(f"FSub fetch error: {e}")
                return []
        return []

    async def get_all_groups(self) -> List[Dict]:
        """Get all groups"""
        if self.connected and self.client:
            try:
                return await self.client.select('groups', '*')
            except Exception as e:
                logger.debug(f"Get all groups error: {e}")

        # Deduplicate local groups by chat_id
        seen = {}
        for v in self.local_groups.values():
            cid = v.get('chat_id')
            if cid and cid not in seen:
                seen[cid] = v
        return list(seen.values())

    async def get_group_count(self) -> int:
        """Get total group count"""
        if self.connected and self.client:
            try:
                groups = await self.client.select('groups', 'chat_id')
                return len(groups)
            except Exception as e:
                logger.debug(f"Group count error: {e}")
        unique_ids = set()
        for v in self.local_groups.values():
            cid = v.get('chat_id')
            if cid:
                unique_ids.add(cid)
        return len(unique_ids)

    # ========== GROUP MESSAGE CACHE ==========

    def add_group_message(self, chat_id: int, user_name: str, user_id: int, content: str):
        """Add message to group cache with user identity"""
        self.local_group_messages[chat_id].append({
            'user_name': user_name,
            'user_id': user_id,
            'content': content,
            'timestamp': datetime.now(timezone.utc).isoformat()
        })

    def get_group_context(self, chat_id: int) -> List[Dict]:
        """Get group message context"""
        return list(self.local_group_messages.get(chat_id, []))

    # ========== ACTIVITY LOGGING ==========

    async def log_user_activity(self, user_id: int, activity_type: str):
        """Log user activity"""
        activity = {
            'user_id': user_id,
            'activity_type': activity_type,
            'timestamp': datetime.now(timezone.utc).isoformat()
        }

        if self.connected and self.client:
            try:
                await self.client.insert('activities', activity)
                return
            except Exception as e:
                logger.debug(f"Activity log error: {e}")

        self.local_activities.append(activity)

    # ========== CLEANUP ==========

    async def close(self):
        """Close database connections"""
        if self.client:
            await self.client.close()

        self.local_users.clear()
        self.local_groups.clear()
        self.local_group_messages.clear()
        self.local_activities.clear()
        self._user_access_times.clear()
        self._group_access_times.clear()

        logger.info("✅ Database connection closed")


# ============================================================================
# SINGLETON INSTANCE
# ============================================================================

db = Database()
