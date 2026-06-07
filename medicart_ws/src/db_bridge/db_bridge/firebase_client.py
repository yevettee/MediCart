"""firebase_client — db_bridge 의 Firebase RTDB 경계(읽기/쓰기/리스너).

로봇측 PC에서 firebase-admin(서비스계정=admin)으로 RTDB 에 접근한다. db_node 가
mission_pool 처리에 쓰지만, read/write/update/delete/push/listen 범용 메서드라
다른 읽기·쓰기 요청 처리에도 재사용한다.

cred_path: serviceAccountKey.json(FB_CRED), db_url: FB_DB_URL. ward_bridge 와 동일 자격.
"""


class FirebaseClient:
    """firebase-admin RTDB 래퍼. import/초기화 실패는 명확히 예외로 드러낸다(은닉 금지)."""

    def __init__(self, cred_path, db_url, logger=None):
        self._log = logger
        if not cred_path or not db_url:
            raise ValueError("FB_CRED / FB_DB_URL 필요(.env·robot.env 확인)")
        import firebase_admin
        from firebase_admin import credentials, db
        self._db = db
        if not firebase_admin._apps:
            firebase_admin.initialize_app(
                credentials.Certificate(cred_path), {"databaseURL": db_url})
        if logger:
            logger.info(f"[firebase_client] RTDB 연결: {db_url}")

    # ── 범용 read/write ──────────────────────────────────────────────────
    def read(self, path):
        return self._db.reference(path).get()

    def write(self, path, value):
        self._db.reference(path).set(value)

    def update(self, path, value):
        self._db.reference(path).update(value)

    def delete(self, path):
        self._db.reference(path).delete()

    def push(self, path, value):
        return self._db.reference(path).push(value).key

    def listen(self, path, callback):
        """path 하위 변경 스트림. callback(event) — event.data/event.path."""
        return self._db.reference(path).listen(callback)
