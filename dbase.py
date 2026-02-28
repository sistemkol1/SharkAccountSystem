import sqlite3
import logging
import json
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


class DataBase:
    def __init__(self, database):
        import os
        db_dir = os.path.dirname(database)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        self.__db = sqlite3.connect(database, check_same_thread=False)
        self.__db.row_factory = sqlite3.Row
        self.__db.execute("PRAGMA foreign_keys = ON")
        self.__db.commit()
        self._lock = threading.Lock()

    def _cur(self):
        return self.__db.cursor()

    def _commit(self):
        with self._lock:
            self.__db.commit()

    def create_tables(self):
        try:
            cur = self._cur()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS accounts(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    login TEXT UNIQUE,
                    password TEXT,
                    shared_secret TEXT,
                    identity_secret TEXT,
                    steamid32 INTEGER,
                    cookies TEXT,
                    avatar_url TEXT
                )
            """)
            cur.execute("""
                CREATE TABLE IF NOT EXISTS auth_history(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    login TEXT,
                    auth_time TEXT,
                    status TEXT,
                    note TEXT
                )
            """)
            self._commit()
        except Exception as e:
            logger.error(e)
            self.__db.rollback()

    def add_account(self, login, password, shared_secret, identity_secret, steamid32):
        try:
            cur = self._cur()
            cur.execute("SELECT * FROM accounts WHERE login = ? LIMIT 1", (login,))
            res = cur.fetchone()
            if not res:
                cur2 = self._cur()
                cur2.execute("""
                    INSERT INTO accounts (login, password, shared_secret, identity_secret, steamid32)
                    VALUES (?, ?, ?, ?, ?)
                """, (login, password, shared_secret, identity_secret, steamid32))
                self._commit()
                print(f"Аккаунт {login} успешно добавлен.")
            else:
                print(f"Аккаунт {login} уже есть.")
        except Exception as e:
            logger.error(f"Ошибка при добавлении аккаунта {login}: {e}")
            self.__db.rollback()

    def get_acc(self, login):
        try:
            cur = self._cur()
            cur.execute("SELECT * FROM accounts WHERE login = ? LIMIT 1", (login,))
            row = cur.fetchone()
            if row:
                cookies = json.loads(row["cookies"]) if row["cookies"] else None
                return dict(row), cookies
            return None, None
        except Exception as e:
            logger.error(e)
            return None, None

    def update_cookies(self, login, cookies_dict):
        try:
            cookies_json = json.dumps(cookies_dict)
            cur = self._cur()
            cur.execute("UPDATE accounts SET cookies = ? WHERE login = ?", (cookies_json, login))
            self._commit()
            # Записываем в историю
            self.add_auth_history(login, "success", "Авторизация выполнена")
            print(f"Куки для {login} обновлены.")
        except Exception as e:
            logger.error(f"Ошибка при обновлении куки для {login}: {e}")
            self.__db.rollback()

    def add_auth_history(self, login, status="success", note=""):
        try:
            cur = self._cur()
            now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            cur.execute("""
                INSERT INTO auth_history (login, auth_time, status, note)
                VALUES (?, ?, ?, ?)
            """, (login, now, status, note))
            self._commit()
        except Exception as e:
            logger.error(f"Ошибка записи истории для {login}: {e}")

    def get_auth_history(self, login=None, limit=100):
        try:
            cur = self._cur()
            if login:
                cur.execute("""
                    SELECT * FROM auth_history WHERE login = ?
                    ORDER BY id DESC LIMIT ?
                """, (login, limit))
            else:
                cur.execute("""
                    SELECT * FROM auth_history
                    ORDER BY id DESC LIMIT ?
                """, (limit,))
            return cur.fetchall()
        except Exception as e:
            logger.error(e)
            return []

    def migrate(self):
        try:
            cur = self._cur()
            cur.execute("ALTER TABLE accounts ADD COLUMN avatar_url TEXT")
            self._commit()
        except Exception:
            pass
        # Создаём таблицу истории если нет
        try:
            cur = self._cur()
            cur.execute("""
                CREATE TABLE IF NOT EXISTS auth_history(
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    login TEXT,
                    auth_time TEXT,
                    status TEXT,
                    note TEXT
                )
            """)
            self._commit()
        except Exception:
            pass

    def update_avatar(self, login, avatar_url):
        try:
            cur = self._cur()
            cur.execute("UPDATE accounts SET avatar_url = ? WHERE login = ?", (avatar_url, login))
            self._commit()
        except Exception as e:
            logger.error(f"Ошибка при обновлении аватарки для {login}: {e}")
            self.__db.rollback()

    def reset_remote_avatars(self):
        try:
            cur = self._cur()
            cur.execute("UPDATE accounts SET avatar_url = NULL WHERE avatar_url LIKE 'http%'")
            count = cur.rowcount
            self._commit()
            print(f"Сброшено {count} удалённых аватарок — будут перескачаны при следующей авторизации")
        except Exception as e:
            logger.error(e)

    def auth_count(self):
        try:
            cur = self._cur()
            cur.execute("SELECT COUNT(*) FROM accounts WHERE cookies IS NOT NULL AND cookies != ''")
            return cur.fetchone()[0]
        except Exception as e:
            logger.error(e)
            return 0

    def all_count(self):
        try:
            cur = self._cur()
            cur.execute("SELECT COUNT(*) FROM accounts")
            return cur.fetchone()[0]
        except Exception as e:
            logger.error(e)
            return 0

    def get_all(self):
        try:
            cur = self._cur()
            cur.execute("SELECT * FROM accounts")
            return cur.fetchall()
        except Exception as e:
            logger.error(e)
            return []

    def find_acc(self, filter_text):
        try:
            cur = self._cur()
            cur.execute("SELECT * FROM accounts WHERE login LIKE ?", (f"%{filter_text}%",))
            return cur.fetchall()
        except Exception as e:
            logger.error(e)
            return []

    def delete_account(self, login):
        try:
            cur = self._cur()
            cur.execute("DELETE FROM accounts WHERE login = ?", (login,))
            self._commit()
            print(f"Аккаунт {login} удалён.")
            return True
        except Exception as e:
            logger.error(f"Ошибка при удалении {login}: {e}")
            self.__db.rollback()
            return False
