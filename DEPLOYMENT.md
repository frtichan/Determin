# 本番環境デプロイガイド

このガイドでは、Render.comを使用して本番環境にデプロイする手順を説明します。

## 📋 事前準備

### 1. GitHubアカウント作成（まだの場合）
1. [GitHub](https://github.com/)にアクセス
2. 「Sign up」をクリックしてアカウントを作成

### 2. Render.comアカウント作成
1. [Render.com](https://render.com/)にアクセス
2. 「Get Started」をクリック
3. GitHubアカウントで連携してログイン（推奨）

---

## 🚀 デプロイ手順

### ステップ1: GitHubリポジトリの作成

#### 1-1. GitHubで新規リポジトリを作成
1. GitHubにログインして右上の「+」→「New repository」をクリック
2. 以下を入力：
   - **Repository name**: `dontlet-app`（任意の名前）
   - **Description**: `LLMでレシピを作成する決定論的実行サービス`
   - **Public / Private**: どちらでもOK（Publicの場合は無料）
   - **Initialize this repository with**: チェックを入れない
3. 「Create repository」をクリック

#### 1-2. ローカルからGitHubへpush

PowerShellでプロジェクトフォルダに移動して以下を実行：

```powershell
# Gitリポジトリの初期化（まだの場合）
git init

# すべてのファイルをステージング
git add .

# コミット
git commit -m "Initial commit: 本番デプロイ準備完了"

# GitHubリポジトリと接続（URLは作成したリポジトリのもの）
git remote add origin https://github.com/あなたのユーザー名/dontlet-app.git

# Pushする前にブランチ名を設定
git branch -M main

# GitHubにpush
git push -u origin main
```

**注意**: 初回pushの際、GitHubのユーザー名とパスワード（またはトークン）を求められます。

---

### ステップ2: Render.comでデプロイ

#### 2-1. Blueprintからデプロイ（自動設定）

1. Render.comダッシュボードで「Blueprints」→「New Blueprint Instance」をクリック
2. 「Connect a repository」から先ほど作成したGitHubリポジトリを選択
3. `render.yaml`が自動的に検出されます
4. プランを選択：
   - **無料で試す場合**: Web Service と Database を両方 "free" に変更
   - **本番運用の場合**: 両方 "starter" のまま（月$7×2=$14）
5. 「Apply」をクリック

#### 2-2. 環境変数の設定

デプロイが開始されますが、`OPENAI_API_KEY`は手動で設定する必要があります：

1. Render.comダッシュボードで作成された「dontlet-app」をクリック
2. 左サイドバーの「Environment」をクリック
3. 「Add Environment Variable」をクリック
4. 以下を追加：
   - **Key**: `OPENAI_API_KEY`
   - **Value**: あなたのOpenAI APIキー（`sk-...`）
5. 「Save Changes」をクリック

環境変数が保存されると、自動的に再デプロイが開始されます。

---

### ステップ3: デプロイ完了の確認

1. Render.comダッシュボードの「Logs」タブで進行状況を確認
2. "Your service is live 🎉" というメッセージが表示されたら成功！
3. 画面上部に表示されているURLをクリック（例: `https://dontlet-app.onrender.com`）

---

## 🔒 セキュリティ設定

### SECRET_KEYの確認

Render.comが自動生成した`SECRET_KEY`を確認：
1. 「Environment」タブを開く
2. `SECRET_KEY`が自動生成されていることを確認
3. 絶対に公開しないこと

### データベースバックアップ

1. Render.comダッシュボードで「dontlet-db」（データベース）をクリック
2. 「Backups」タブから手動バックアップを作成可能
3. 有料プラン（Starter）では自動バックアップが有効

---

## 🌐 カスタムドメイン設定（オプション）

後から`dontlet.ai`などのカスタムドメインを設定する場合：

1. ドメイン取得サービス（例：Cloudflare、Google Domainsなど）でドメインを取得
2. Render.comで「Settings」→「Custom Domain」をクリック
3. 取得したドメインを入力
4. 表示されるCNAMEレコードをドメイン管理画面で設定
5. SSL証明書は自動的に設定されます（Let's Encrypt）

---

## 📊 監視とメンテナンス

### ログの確認
- Render.comダッシュボードの「Logs」タブでリアルタイムログを確認

### パフォーマンス監視
- 「Metrics」タブでCPU使用率、メモリ、リクエスト数を確認

### アップデート
- GitHubにpushするだけで自動的に再デプロイされます：
  ```powershell
  git add .
  git commit -m "機能追加: ○○機能"
  git push
  ```

---

## 💰 料金プラン

### 無料プラン
- Web Service: 無料（15分間無操作でスリープ）
- Database: 無料（90日後に削除される）
- **合計**: $0/月

### 推奨プラン（本番運用）
- Web Service (Starter): $7/月
- Database (Starter): $7/月
- **合計**: $14/月（約2,000円）

---

## 🆘 トラブルシューティング

### デプロイが失敗する
1. Render.comの「Logs」でエラーメッセージを確認
2. `requirements.txt`の依存関係を確認
3. 環境変数が正しく設定されているか確認

### データベース接続エラー
1. `DATABASE_URL`環境変数が正しく設定されているか確認
2. データベースサービスが起動しているか確認

### アプリが起動しない
1. `SECRET_KEY`が設定されているか確認
2. `OPENAI_API_KEY`が正しいか確認

---

## 📝 次のステップ

1. ✅ デプロイ完了
2. 🧪 本番環境でテスト
3. 👥 ユーザーを招待
4. 📈 Google Analyticsなどの追加（収益化の準備）
5. 🌐 カスタムドメインの設定（必要に応じて）

---

**おめでとうございます！これであなたのWebサービスが世界中からアクセス可能になりました！** 🎉

