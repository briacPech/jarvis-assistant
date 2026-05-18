# memory.py
# ========================================
# Gestion de la mémoire et historique
# ========================================

import console_utf8  # noqa: F401

import sqlite3
import json
import re
import threading
from datetime import datetime
from typing import List, Dict, Callable, Optional
import os

# Faits de ton / identite — injectes en priorite dans le prompt
_PROFILE_FACT_MARKERS = (
    "tutoie",
    "m'appelle",
    "appelle-moi",
    "mon nom",
    "pote",
    "pas froid",
    "blagueur",
    "chaleureux",
    "briac",
)

try:
    from config import DB_PATH as _CFG_DB
    from config import MEMORY_SUMMARY_INTERVAL, MEMORY_SUMMARY_WINDOW
except ImportError:
    _CFG_DB = "jarvis_memory.db"
    MEMORY_SUMMARY_INTERVAL = 15
    MEMORY_SUMMARY_WINDOW = 15

# ========================================
# Configuration
# ========================================

DB_PATH = os.getenv("JARVIS_DB", _CFG_DB)

# ========================================
# Classe Memory
# ========================================

class Memory:
    """Gère la mémoire de Jarvis"""
    
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self.init_db()
    
    def init_db(self):
        """Crée la base de données si elle n'existe pas"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Créé la table des conversations
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_message TEXT NOT NULL,
                jarvis_response TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_id TEXT DEFAULT 'default'
            )
        """)
        
        # Créé la table des faits (mémoire long terme)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS facts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fact TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_id TEXT DEFAULT 'default'
            )
        """)
        
        # Créé la table des rappels
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS reminders (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                reminder TEXT NOT NULL,
                due_date DATETIME,
                completed BOOLEAN DEFAULT 0,
                user_id TEXT DEFAULT 'default'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS session_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                summary TEXT NOT NULL,
                from_conv_id INTEGER,
                to_conv_id INTEGER,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                user_id TEXT DEFAULT 'default'
            )
        """)

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_meta (
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT NOT NULL,
                PRIMARY KEY (user_id, key)
            )
        """)
        
        conn.commit()
        conn.close()
        try:
            from fts_prefetch import ensure_fts_schema

            ensure_fts_schema(self.db_path)
        except ImportError:
            pass
        print(f"[OK] Base de donnees initialisee : {self.db_path}")
    
    # ========================================
    # Conversations
    # ========================================
    
    def add_conversation(
        self,
        user_msg: str,
        jarvis_msg: str,
        user_id: str = "default",
        *,
        auto_summarize: bool = True,
        summarize_fn: Optional[Callable[[str], str]] = None,
    ) -> int:
        """Ajoute une conversation ; declenche un resume tous les N messages."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO conversations (user_message, jarvis_response, user_id)
            VALUES (?, ?, ?)
        """, (user_msg, jarvis_msg, user_id))
        conv_id = cursor.lastrowid or 0

        conn.commit()
        conn.close()
        print("[OK] Conversation sauvegardee")

        if conv_id:
            try:
                from fts_prefetch import index_conversation

                index_conversation(conv_id, user_msg, jarvis_msg, user_id)
            except ImportError:
                pass

        if auto_summarize and conv_id:
            threading.Thread(
                target=self.maybe_rollup_summary,
                kwargs={"user_id": user_id, "summarize_fn": summarize_fn},
                daemon=True,
                name="jarvis-summary",
            ).start()
        return conv_id
    
    def get_conversation_history(self, user_id: str = "default", limit: int = 10) -> List[Dict]:
        """Récupère l'historique de conversation"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT user_message, jarvis_response, timestamp
            FROM conversations
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        """, (user_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [
            {
                "user": row[0],
                "jarvis": row[1],
                "timestamp": row[2]
            }
            for row in rows
        ]
    
    def _get_meta(self, user_id: str, key: str, default: str = "0") -> str:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT value FROM user_meta WHERE user_id = ? AND key = ?",
            (user_id, key),
        )
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else default

    def _set_meta(self, user_id: str, key: str, value: str) -> None:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO user_meta (user_id, key, value) VALUES (?, ?, ?)
            ON CONFLICT(user_id, key) DO UPDATE SET value = excluded.value
            """,
            (user_id, key, value),
        )
        conn.commit()
        conn.close()

    def count_conversations(self, user_id: str = "default") -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM conversations WHERE user_id = ?",
            (user_id,),
        )
        n = cursor.fetchone()[0]
        conn.close()
        return n

    def get_conversations_for_summary(
        self, user_id: str, limit: int, after_id: int = 0
    ) -> List[Dict]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id, user_message, jarvis_response, timestamp
            FROM conversations
            WHERE user_id = ? AND id > ?
            ORDER BY id ASC
            LIMIT ?
            """,
            (user_id, after_id, limit),
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "id": row[0],
                "user": row[1],
                "jarvis": row[2],
                "timestamp": row[3],
            }
            for row in rows
        ]

    def add_session_summary(
        self,
        summary: str,
        user_id: str,
        from_conv_id: int,
        to_conv_id: int,
    ) -> int:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO session_summaries
            (summary, from_conv_id, to_conv_id, user_id)
            VALUES (?, ?, ?, ?)
            """,
            (summary, from_conv_id, to_conv_id, user_id),
        )
        sid = cursor.lastrowid or 0
        conn.commit()
        conn.close()
        return sid

    def get_session_summaries(
        self, user_id: str = "default", limit: int = 3
    ) -> List[str]:
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT summary FROM session_summaries
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        )
        rows = [r[0] for r in cursor.fetchall()]
        conn.close()
        return list(reversed(rows))

    def maybe_rollup_summary(
        self,
        user_id: str = "default",
        *,
        summarize_fn: Optional[Callable[[str], str]] = None,
        interval: Optional[int] = None,
        window: Optional[int] = None,
    ) -> bool:
        """Tous les N messages : resume -> SQLite (+ Chroma si dispo)."""
        every = interval if interval is not None else MEMORY_SUMMARY_INTERVAL
        win = window if window is not None else MEMORY_SUMMARY_WINDOW
        pending = int(self._get_meta(user_id, "msgs_since_summary", "0")) + 1
        self._set_meta(user_id, "msgs_since_summary", str(pending))
        if pending < every:
            return False

        last_id = int(self._get_meta(user_id, "last_summary_conv_id", "0"))
        batch = self.get_conversations_for_summary(user_id, win, after_id=last_id)
        if not batch:
            self._set_meta(user_id, "msgs_since_summary", "0")
            return False

        lines = []
        for row in batch:
            lines.append(f"Utilisateur: {row['user']}")
            lines.append(f"Jarvis: {(row['jarvis'] or '')[:800]}")
        transcript = "\n".join(lines)

        summary = ""
        if summarize_fn:
            summary = (summarize_fn(transcript) or "").strip()
        if not summary:
            self._set_meta(user_id, "msgs_since_summary", "0")
            return False

        from_id = batch[0]["id"]
        to_id = batch[-1]["id"]
        sid = self.add_session_summary(summary, user_id, from_id, to_id)
        self._set_meta(user_id, "last_summary_conv_id", str(to_id))
        self._set_meta(user_id, "msgs_since_summary", "0")

        for line in summary.split("\n"):
            line = line.strip().lstrip("-•* ").strip()
            if len(line) >= 8:
                self.add_fact(line[:300], user_id)

        try:
            from memory_summary import store_summary_vector

            store_summary_vector(summary, user_id, sid)
        except ImportError:
            pass

        print(f"[Memoire] Resume session #{sid} (conv {from_id}-{to_id})")
        return True

    def get_context(self, user_id: str = "default", limit: int = 5) -> str:
        """Récupère le contexte pour le prompt système"""
        history = self.get_conversation_history(user_id, limit)
        facts = self.get_facts(user_id)
        summaries = self.get_session_summaries(user_id, limit=2)
        parts = []
        if summaries:
            parts.append(
                "Resumes de sessions precedentes :\n"
                + "\n---\n".join(summaries)
            )
        if facts:
            parts.append("Faits memorises :\n" + "\n".join(f"- {f}" for f in facts[:25]))
        if history:
            lines = ["Historique recent :"]
            for entry in reversed(history):
                lines.append(f"Utilisateur: {entry['user']}")
                lines.append(f"Jarvis: {entry['jarvis'][:600]}")
            parts.append("\n".join(lines))
        return "\n\n".join(parts)

    def try_extract_fact(self, user_msg: str, user_id: str = "default") -> bool:
        """Detecte et enregistre un fait important dans le message."""
        import re
        msg = (user_msg or "").strip()
        if len(msg) < 4:
            return False
        patterns = [
            r"(?:je m'appelle|mon nom est|appelle[- ]moi)\s+(.+)",
            r"(?:retiens|n'oublie pas|note que|souviens[- ]toi que)\s+(.+)",
            r"(?:j'ai)\s+(\d+)\s+ans",
            r"(?:je suis|je travaille comme)\s+(.+)",
        ]
        for pattern in patterns:
            m = re.search(pattern, msg, re.IGNORECASE)
            if m:
                fact = m.group(1).strip().rstrip(".!?")[:300]
                if len(fact) >= 2:
                    self.add_fact(fact, user_id)
                    return True
        if re.search(r"\bretiens\b|\bmémoire\b|\bsouviens\b", msg, re.IGNORECASE):
            self.add_fact(msg[:300], user_id)
            return True
        return False
    
    # ========================================
    # Faits / Mémoire long terme
    # ========================================
    
    @staticmethod
    def _normalize_fact(fact: str) -> str:
        return re.sub(r"\s+", " ", (fact or "").strip().lower())

    def _is_duplicate_fact(self, fact: str, user_id: str = "default") -> bool:
        norm = self._normalize_fact(fact)
        if len(norm) < 2:
            return True
        for existing in self.get_facts(user_id):
            ex = self._normalize_fact(existing)
            if ex == norm:
                return True
            if len(norm) >= 12 and (norm in ex or ex in norm):
                return True
        return False

    def add_fact(self, fact: str, user_id: str = "default"):
        """Ajoute un fait à retenir (sans doublon proche)."""
        text = (fact or "").strip()[:300]
        if len(text) < 2:
            return
        if self._is_duplicate_fact(text, user_id):
            return
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO facts (fact, user_id)
            VALUES (?, ?)
        """, (text, user_id))

        conn.commit()
        conn.close()
        print(f"[Memoire] Fait ajoute : {text}")
    
    def get_facts(self, user_id: str = "default") -> List[str]:
        """Récupère tous les faits"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT fact FROM facts
            WHERE user_id = ?
            ORDER BY timestamp DESC
        """, (user_id,))
        
        facts = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        return facts

    def get_facts_for_prompt(
        self, user_id: str = "default", limit: int = 15
    ) -> List[str]:
        """Profil / ton en tete, puis autres faits, sans doublons."""
        all_facts = self.get_facts(user_id)
        profile: List[str] = []
        other: List[str] = []
        for f in all_facts:
            low = (f or "").lower()
            if any(m in low for m in _PROFILE_FACT_MARKERS):
                profile.append(f)
            else:
                other.append(f)
        seen: set[str] = set()
        out: List[str] = []
        for f in profile + other:
            key = self._normalize_fact(f)
            if key in seen:
                continue
            seen.add(key)
            out.append(f)
            if len(out) >= limit:
                break
        return out

    def has_fact_containing(
        self, needle: str, user_id: str = "default"
    ) -> bool:
        """True si un fait existant contient needle (insensible a la casse)."""
        n = (needle or "").strip().lower()
        if not n:
            return False
        return any(n in (f or "").lower() for f in self.get_facts(user_id))

    def ensure_personal_fact(
        self,
        fact: str,
        user_id: str = "default",
        *,
        marker: Optional[str] = None,
    ) -> bool:
        """
        Ajoute un fait de profil s'il n'existe pas deja (meme marker dans les faits).
        Retourne True si un nouveau fait a ete ajoute.
        """
        text = (fact or "").strip()[:300]
        if not text:
            return False
        check = (marker or text[:40]).strip().lower()
        if self.has_fact_containing(check, user_id):
            return False
        self.add_fact(text, user_id)
        return True
    
    # ========================================
    # Rappels
    # ========================================
    
    def add_reminder(self, reminder: str, user_id: str = "default", due_date: str = None):
        """Ajoute un rappel"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT INTO reminders (reminder, due_date, user_id)
            VALUES (?, ?, ?)
        """, (reminder, due_date, user_id))
        
        conn.commit()
        conn.close()
        print(f"[Memoire] Rappel ajoute : {reminder}")
    
    def get_reminders(self, user_id: str = "default") -> List[Dict]:
        """Récupère tous les rappels non complétés"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT id, reminder, due_date
            FROM reminders
            WHERE user_id = ? AND completed = 0
            ORDER BY due_date ASC
        """, (user_id,))
        
        reminders = [
            {"id": row[0], "reminder": row[1], "due_date": row[2]}
            for row in cursor.fetchall()
        ]
        conn.close()
        
        return reminders
    
    def mark_reminder_done(self, reminder_id: int):
        """Marque un rappel comme terminé"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            UPDATE reminders
            SET completed = 1
            WHERE id = ?
        """, (reminder_id,))
        
        conn.commit()
        conn.close()
        print(f"[OK] Rappel {reminder_id} marque comme termine")

    def pop_due_reminders(self, user_id: Optional[str] = None) -> List[Dict]:
        """Rappels dont l'échéance est passée (marqués terminés par l'appelant)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if user_id:
            cursor.execute(
                """
                SELECT id, reminder, due_date, user_id
                FROM reminders
                WHERE completed = 0 AND due_date IS NOT NULL AND due_date <= ?
                  AND user_id = ?
                ORDER BY due_date ASC
                """,
                (now, user_id),
            )
        else:
            cursor.execute(
                """
                SELECT id, reminder, due_date, user_id
                FROM reminders
                WHERE completed = 0 AND due_date IS NOT NULL AND due_date <= ?
                ORDER BY due_date ASC
                """,
                (now,),
            )
        rows = cursor.fetchall()
        conn.close()
        return [
            {"id": r[0], "reminder": r[1], "due_date": r[2], "user_id": r[3]}
            for r in rows
        ]
    
    # ========================================
    # Utilités
    # ========================================
    
    def clear_all(self, user_id: str = "default"):
        """Efface la mémoire (⚠️ attention !)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM facts WHERE user_id = ?", (user_id,))
        cursor.execute("DELETE FROM reminders WHERE user_id = ?", (user_id,))
        
        conn.commit()
        conn.close()
        print(f"[Memoire] Memoire effacee pour {user_id}")
    
    def get_stats(self, user_id: str = "default") -> Dict:
        """Retourne des statistiques"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM conversations WHERE user_id = ?", (user_id,))
        conv_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM facts WHERE user_id = ?", (user_id,))
        facts_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM reminders WHERE user_id = ? AND completed = 0", (user_id,))
        reminders_count = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "conversations": conv_count,
            "facts": facts_count,
            "reminders_pending": reminders_count
        }


# ========================================
# Test
# ========================================

if __name__ == "__main__":
    memory = Memory()
    
    # Test
    memory.add_conversation("Salut", "Bonjour !", "alice")
    memory.add_fact("Alice aime le café", "alice")
    memory.add_reminder("Acheter du café", "alice")
    
    print("\n[Historique]")
    print(memory.get_conversation_history("alice"))
    
    print("\n[Faits]")
    print(memory.get_facts("alice"))
    
    print("\n[Rappels]")
    print(memory.get_reminders("alice"))
    
    print("\n[Stats]")
    print(memory.get_stats("alice"))