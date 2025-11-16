## ローカルで動かす超シンプル手順（Windows/初心者向け）

このプロジェクトは「LLMでレシピを作り、実行は決定論的に行う」Web API の最小構成です。まずはあなたのPCだけで無料で動かせます。

### 必要なもの
- Python 3.11 以上（3.12 でも可）
- PowerShell（標準で入っています）

### 初回セットアップ（10〜15分）
1. PowerShell を開く
2. プロジェクトのフォルダへ移動
   ```powershell
   Set-Location "C:\Users\<あなたのユーザー名>\Documents\Study\cursor\決定論サイト"
   ```
3. 仮想環境を作成して有効化（PCを汚さず安全）
   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```
4. 依存パッケージをインストール
   ```powershell
   python -m pip install --upgrade pip
   pip install -r requirements.txt
   ```
5. 環境変数を設定（.envに保存：安全・簡単）
   - プロジェクト直下に `.env` を作成して、以下を記入してください。
     ```env
     # OpenAI API（AI機能を使用する場合）
     OPENAI_API_KEY=sk-................................
     
     # JWT認証用秘密鍵（本番環境では必ず変更）
     # 以下のコマンドで生成できます:
     # python -c "import secrets; print(secrets.token_urlsafe(32))"
     SECRET_KEY=your-secret-key-change-this-in-production
     ```
   - `.env` は `.gitignore` 済みなので、公開されません。
6. API サーバーを起動
   ```powershell
   uvicorn app.main:app --reload
   ```
7. ブラウザで画面を開く
   - `http://127.0.0.1:8000/`（初心者向けGUI。入力とレシピを入れて実行できます）
   - `http://127.0.0.1:8000/docs`（開発者向けAPIドキュメント）

停止するときは PowerShell で Ctrl + C。仮想環境を抜けるには `deactivate` を実行します。

### よくあるつまずき
- セキュリティエラーで `.venv` 有効化が失敗した場合は、PowerShell を管理者で起動し、次を一度だけ実行してください。
  ```powershell
  Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  ```

### ディレクトリ構成（要点）
```
app/
  main.py            # FastAPI 本体
  config.py          # 設定（保存容量など）
  db.py              # SQLite（ファイル1つでOK）
  models.py          # データモデル
  routers/           # API 入口（recipes/datasets/runs）
  services/          # DSL実行や入出力処理
data/                # 入出力データが保存されます（自動作成）
requirements.txt
README.md
```

### ユーザー認証機能
このツールには**メールアドレス認証**機能が実装されています：

#### 主な機能
- **ユーザー登録**: メールアドレス + パスワード（8文字以上）で登録
- **ログイン/ログアウト**: JWT + HttpOnly Cookieによる安全なセッション管理
- **レシピの個人管理**: ログイン後、保存したレシピは自分のみ閲覧・編集可能

#### 使い方
1. 画面右上の「新規登録」ボタンからアカウント作成
2. ログイン後、レシピを保存すると自動的にユーザーに紐付けられます
3. レシピ一覧には自分のレシピのみ表示されます

#### セキュリティ
- パスワードは bcrypt でハッシュ化して保存
- セッションは JWT トークンで管理（7日間有効）
- 本番環境では必ず環境変数 `SECRET_KEY` を強力なものに変更してください

### 次にやること
- `http://127.0.0.1:8000/` でGUIから「実行して結果を見る」を試してください。
- うまくいけば、末尾の数字がJSONテーブルで表示されます。
- レシピを保存するには、まず「新規登録」でアカウントを作成してください。

### お金はかかる？
- ここまでは無料です。あなたのPCだけで動きます。
- LLM（OpenAI GPT API）を使う段階になったら、使った分だけ少額課金が発生しますが、送るのはサンプル（自動マスキング付）だけです。



