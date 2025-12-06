PR #2: requirment add
URL: https://github.com/shkond/autouploader/pull/2

内容:
- 永続化キュー（DBベースの QueueJobModel）を導入
- OAuthトークンの暗号化（Fernet）と DB 保存
- ワーカープロセス分離（Procfile、worker）
- PostgreSQL 対応・設定の更新
- テストを多数追加（キュー、暗号化、永続化など）

指摘:
- Procfile がポート `8080` をハードコードしている（$PORT を使うべき）。
- `app/static/js/dashboard.js` で `activeJobs.forEach` が空で、進捗表示が未実装。
- `app/crypto.py` の `decrypt_token` docstring: 例外は `cryptography.fernet.InvalidToken` を指すべき。
- `app/models.py` の `QueueJobModel.id` 型注釈 (`Mapped[UUID]`) が `String(36)` と不一致 → `Mapped[str]` にするか注釈で理由を明記。
- `tests/conftest.py` の `sample_queue_job_data` で `metadata_json` に `str(dict)` を用いている → `json.dumps()` を使用するべき。
- `tests/test_database_persistence.py` で作成テーブルの検証が `upload_history` のみ。`queue_jobs` と `oauth_tokens` も検証すべき。
- テストで `pytest.raises(Exception)` を使っている箇所があり、より特定の例外（`cryptography.fernet.InvalidToken` など）を期待すべき。
- いくつかのフィクスチャ/テストで未使用のインポートや未使用のフィクスチャ（`env_override`, `sample_queue_job_data` 等）がある。
- `app/crypto.py` の `clear_fernet_cache()` をテストで検証していない。
- 一部のテストに空の `pass` が残っており、実装または削除が必要。
- `.env.example` のコメントフォーマットが一貫していない（Dev/Prod の説明整理を推奨）。

---

PR #3: Pr3
URL: https://github.com/shkond/autouploader/pull/3

内容:
- DBへ OAuth トークンとアップロードキューを移行し、永続化を実装
- ワーカープロセス追加／分離
- トークン暗号化によるセキュリティ改善
- マルチユーザー対応（トークンとジョブをユーザー単位で管理）

指摘:
- Procfile がポート `8080` をハードコードしている（$PORT を使うべき）。
- トークンリフレッシュ失敗時に DB 上の無効トークンが残る：リフレッシュ失敗時はキャッシュと DB をクリアして再認証を強制する実装を推奨。
- `app/auth/dependencies.py` の `get_current_user` は非同期 `async` だが await を使っていない / optional 引数の取り扱いが不明瞭。不要なら同期関数に、あるいは引数を必須に。
- `get_current_user_from_session` が `"anonymous"` を返す実装は、認証期待時にバグを隠す可能性があるため `None` か例外の方が安全。
- 例外ハンドリングで broad な `Exception` をキャッチしている箇所があり、`SQLAlchemyError` や `InvalidToken` など特定例外で扱うべき箇所がある。
- テストに `pass` のプレースホルダが残っている。実装または削除を推奨。
- `app/models.py` の `id` 型注釈と実際の `String(36)` の不一致。UUID で扱うなら DB 型/実装検討が必要。
- `app/static/js/dashboard.js` での `activeJobs.forEach` が空なので進捗 UI を実装すべき。
- `app/queue/worker.py` の `signal_handler` の引数 `frame` が未使用 → `_frame` にすると明示的。
- `app/queue/worker.py` の `run_standalone_worker` で `types` の import（フレーム型）や `logging` の設定・不要 import 問題の指摘。
- 多数のテストで未使用インポートの指摘（`asyncio`, `pytest_asyncio`, `MagicMock` 等）。

---

PR #4: pr4
URL: https://github.com/shkond/autouploader/pull/4

内容:
- アップロードジョブ管理をインメモリから DB バックエンドへ移行(`QueueManagerDB`)
- ジョブをユーザー所有にし、API はユーザー単位での操作に変更
- 認証をルートに統合し、UI/ワーカーを永続化されたキューと連携
- ワーカーの DB ベース処理へのリファクタ（QueueManagerDB を用いたジョブ取得/更新）

指摘:
- `manager_db.add_job` 等で `datetime.now()` を timezone-naive で使っており、モデルは timezone-aware（DateTime(timezone=True)）の想定。UTC 等の timezone-aware を使うべき（例: datetime.now(UTC)）。
- `get_status` で DB から全ジョブを読み込み Python 側でカウントしている→ DB の集計で効率化すべき（条件付き集計）。
- `list_jobs` が `jobs` を取得したあと、再度 `get_status` で DB クエリを投げているが、`jobs` から status を算出して返す方が無駄なクエリを減らせる。
- `add_bulk_jobs` が `add_job` をループで呼んでおり、そのたびにコミットするため非効率。バルク挿入かトランザクション内で一括コミットすべき。
- `get_status` が `is_processing=False` にハードコードされておりワーカー稼働状態が失われている。ワーカー側のフラグを経由して状態を返すべき。
- `worker._process_job` の `progress_callback` を `async def` にしているが、`youtube_service.upload_from_drive()` へは同期コールバックを渡している可能性があるため、同期/非同期の扱い不整合に注意（コールバックは同期にするか upload を async にする等）。
- `_save_upload_history` を別 DB コンテキストで開いており、呼び出し元のトランザクションと分離されている。可能なら同一セッション/トランザクションを使うべき。
- `get_job` で取得したモデルからジョブ状態を更新するまでにレースが発生する可能性がある → 行ロック（for update skip_locked）や楽観ロックを用いるべき。
- `get_next_pending_job` にロックやユーザーフィルタがなく、マルチワーカー環境で同一ジョブが複数回処理される競合の危険がある（skip_locked 等で安全にロック取得する対応を推奨）。
- `manager_db` で大量のジョブを持つユーザーに対して非効率な全件ロードがある箇所（`get_status` 等）→ DB 側で集計を行うべき。
- `worker` の `is_processing` 状態を復元して UI に反映できるように修正すべき。
- `app/queue/routes.py` と `app/drive/routes.py` での認証ロジックが重複している（`require_app_auth` と既存 `get_current_user` 依存を利用して重複削減を推奨）。
