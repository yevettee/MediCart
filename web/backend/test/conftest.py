"""공유 pytest 픽스처 — Flask test_client + 인메모리 RTDB monkeypatch.

실행: cd web/backend && env -i PATH=/usr/bin:/bin PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
      venv/bin/python -m pytest test/ -q
"""
import os

os.environ.setdefault("INTEL_PASSWORD", "spw")
os.environ.setdefault("INTEL_AUTH_TOKEN", "STAFFTOK")
os.environ.setdefault("INTEL_ADMIN_PASSWORD", "apw")
os.environ.setdefault("INTEL_ADMIN_TOKEN", "ADMINTOK")

import pytest
import fb_read
import app as flask_app


# ---------------------------------------------------------------------------
# 인메모리 RTDB 트리
# ---------------------------------------------------------------------------

class FakeRTDB:
    """fb_read 의 RTDB 접근을 대체하는 인메모리 트리."""

    def __init__(self):
        self.data = {}
        self._push_seq = 0

    def get(self, path):
        node = self.data
        for k in [p for p in str(path).strip("/").split("/") if p]:
            if not isinstance(node, dict) or k not in node:
                return None
            node = node[k]
        return node

    def set(self, path, value):
        parts = [p for p in str(path).strip("/").split("/") if p]
        if not parts:
            # root set
            if isinstance(value, dict):
                self.data = dict(value)
            return
        node = self.data
        for k in parts[:-1]:
            node = node.setdefault(k, {})
        node[parts[-1]] = value

    def delete(self, path):
        parts = [p for p in str(path).strip("/").split("/") if p]
        if not parts:
            self.data = {}
            return
        node = self.data
        for k in parts[:-1]:
            if not isinstance(node, dict) or k not in node:
                return
            node = node[k]
        node.pop(parts[-1], None)

    def update(self, path, patch):
        """path 아래를 patch 로 부분 갱신.
        Firebase 멀티패스 업데이트 의미(슬래시 포함 patch 키 = 중첩 경로 쓰기)도 지원."""
        base_path = str(path).strip("/")
        flat = {k: v for k, v in patch.items() if "/" not in str(k)}
        nested = {k: v for k, v in patch.items() if "/" in str(k)}
        if flat:
            existing = self.get(path)
            base = dict(existing) if isinstance(existing, dict) else {}
            base.update(flat)
            self.set(path, base)
        for k, v in nested.items():
            self.set(f"{base_path}/{k}" if base_path else str(k), v)

    def push(self, path, value):
        """Firebase push 흉내 — 단조증가 key 반환(결정적·충돌 없음)."""
        self._push_seq += 1
        key = f"push_{self._push_seq:08d}"
        parts = [p for p in str(path).strip("/").split("/") if p]
        node = self.data
        for k in parts:
            node = node.setdefault(k, {})
        node[key] = value
        return key


class _FakeRef:
    """db.reference(path) 가 반환하는 ref 의 인메모리 대체.

    fb_read 가 사용하는 메서드만 구현:
      get() / set(v) / update(v) / delete() / push(v) / child(k) / listen(cb)
    """

    def __init__(self, rtdb: FakeRTDB, path: str):
        self._rtdb = rtdb
        self._path = path.strip("/") if path else ""

    def _full(self, subpath=""):
        if subpath:
            return f"{self._path}/{subpath}".strip("/")
        return self._path

    def get(self):
        return self._rtdb.get(self._path)

    def set(self, value):
        self._rtdb.set(self._path, value)

    def update(self, patch):
        self._rtdb.update(self._path, patch)

    def delete(self):
        self._rtdb.delete(self._path)

    def push(self, value):
        key = self._rtdb.push(self._path, value)

        class _PushResult:
            pass

        r = _PushResult()
        r.key = key
        return r

    def child(self, key):
        return _FakeRef(self._rtdb, self._full(str(key)))

    def listen(self, callback):
        # SSE 스트림 테스트는 이 conftest 의 범위 밖.  no-op で OK.
        pass


class _FakeDB:
    """firebase_admin.db 모듈 대체 — reference() 만 필요."""

    def __init__(self, rtdb: FakeRTDB):
        self._rtdb = rtdb

    def reference(self, path=""):
        return _FakeRef(self._rtdb, str(path or ""))


# ---------------------------------------------------------------------------
# pytest 픽스처
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    flask_app.app.config["TESTING"] = True
    return flask_app.app.test_client()


@pytest.fixture
def staff(client):
    client.set_cookie("intel_auth", "STAFFTOK")
    return client


@pytest.fixture
def admin(client):
    client.set_cookie("intel_auth", "ADMINTOK")
    return client


@pytest.fixture
def fake_rtdb(monkeypatch):
    """fb_read._db を _FakeDB に差し替え、全 RTDB アクセスをインメモリ化する。

    monkeypatch 対象:
      fb_read._db  — _init() が返す firebase db モジュール本体。
                     全 fb_read 関数は _init().reference(path) 経由でアクセスするため、
                     ここを一点差し替えるだけで全読み書きを捕捉できる。

    patched target:
      fb_read._db — the firebase `db` module returned by _init().
                    All fb_read functions access RTDB via _init().reference(path),
                    so patching this single point intercepts every read and write.

    RTDB パス規約 (fb_read.py より):
      robot3/{topic}           AMR テレメトリ (amcl_pose / odom / battery_state …)
      robot6/{topic}           セカンダリ AMR
      {ns}/cmd                 モード制御コマンド
      {ns}/mission_pool/{key}  ミッションキュー (push)
      {ns}/nurse_cart/ocr_done OCR 完了フラグ
      {ns}/nurse_cart/phase    ロボット作業フェーズ
      {ns}/patrol              巡回ハンドシェイク
      {ns}/logs                ロボットログ
      {ns}/health              ヘルスチェック
      {ns}/camera              カメラフレーム
      {ns}/alerts              アラート
      patients/{pid}/…         患者データ
      intake_pending/{key}     非ログイン文診キュー
      ocr/latest               OCR 最新結果
      targets                  移動先プリセット
      rooms/{room}/patient     病床配置患者
      display/current_patient  病室ディスプレイ
    """
    rtdb = FakeRTDB()
    fake_db = _FakeDB(rtdb)
    # fb_read._db を直接差し替え — _init() の「_db is not None → 即リターン」を利用。
    # 既存の _db が None でなければ（他テストが _init() を呼んだ場合）も上書きする。
    monkeypatch.setattr(fb_read, "_db", fake_db)
    return rtdb
