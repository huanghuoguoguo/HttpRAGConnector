# HttpRAGConnector

汎用 HTTP RAG コネクター。HTTP API を提供する任意のナレッジベースサービスを LangBot に接続します。

Dify、RAGFlow、FastGPT などの一般的なプラットフォームに接続する場合は、**まずそれぞれの専用プラグインをご利用ください**。専用プラグインがない場合、またはカスタム HTTP 検索エンドポイントに接続する場合にのみ、このプラグインを使用してください。

## クイックスタート

最低 **3 つのフィールド** を入力するだけで動作します：

| フィールド | 入力内容 | 例 |
|-----------|---------|-----|
| API Base URL | RAG サービスのベース URL | `https://your-rag.com/api/v1` |
| Retrieval Endpoint | 検索 API のパス | `/search` |
| API Key | 認証キー（不要な場合は空欄） | `sk-xxx` |

その他のフィールドにはすべて適切なデフォルト値が設定されています：

- **Request Body Template** を空欄 → 自動的に `{"query": "ユーザーの質問", "top_k": 5}` を送信
- **Results Array Path** のデフォルトは `results`
- **Content Field(s)** のデフォルトは `content`
- **Score Field** のデフォルトは `score`
- **ID Field** のデフォルトは `id`

API のレスポンス形式がこれらのデフォルト値と一致していれば、何も変更せずにそのまま使用できます。

## 仕組み

プラグインに伝えることは 2 つだけです：

1. **リクエスト**：どの HTTP エンドポイントを呼び出し、リクエストボディがどのような形式か
2. **レスポンス**：レスポンス内の結果配列、テキストコンテンツ、スコア、ID がそれぞれどのフィールドにあるか

プラグインはユーザーの質問と検索パラメータを自動的にリクエストに挿入し、レスポンスを LangBot で使用可能なナレッジセグメントに変換します。

## フィールドリファレンス

### 作成設定

#### API Base URL（必須）

対象サービスのベース URL。ドメインとパスプレフィックスのみ入力し、具体的なエンドポイントパスは含めないでください。

```
https://your-rag-service.com/api/v1
```

#### API Key

認証キー。デフォルトでは `Authorization: Bearer <key>` として送信されます。認証が不要な場合は空欄にしてください。

#### Dataset ID

データセット/ナレッジベース ID。エンドポイントパスやリクエストボディで `{{ dataset_id }}` を使用している場合、実行時にこの値に置き換えられます。不要な場合は空欄にしてください。

### 検索設定

#### Retrieval Endpoint（必須）

検索エンドポイントのパス。最終リクエスト URL = API Base URL + このパス。`{{ dataset_id }}` 変数をサポートしています。

```
/search
/datasets/{{ dataset_id }}/retrieve
/api/query
```

#### Request Body Template

検索リクエストの JSON テンプレート。以下の変数をサポートしています：

| 変数 | ソース |
|------|--------|
| `{{ query }}` | ユーザーの現在の質問 |
| `{{ top_k }}` | 検索設定の結果数 |
| `{{ similarity_threshold }}` | 検索設定の類似度閾値 |
| `{{ dataset_id }}` | 作成設定のデータセット ID |

**空欄の場合のデフォルト**：`{"query": "{{ query }}", "top_k": {{ top_k }}}`

カスタム例：

```json
{
  "query": "{{ query }}",
  "limit": {{ top_k }},
  "min_score": {{ similarity_threshold }},
  "collection": "{{ dataset_id }}"
}
```

注意：文字列変数には引用符が必要です（`"{{ query }}"`）、数値変数には不要です（`{{ top_k }}`）。

#### Results Array Path（必須）

レスポンス JSON 内の結果配列の位置。ドット区切りのパスを使用します。

| レスポンス構造 | 入力値 |
|---|---|
| `{"results": [...]}` | `results` |
| `{"data": {"records": [...]}}` | `data.records` |
| `{"hits": {"hits": [...]}}` | `hits.hits` |

#### Content Field(s)（必須）

各結果内のテキストコンテンツを含むフィールド。ドット区切りのパスをサポート。複数フィールドはカンマで区切ると自動的に連結されます。

| 結果構造 | 入力値 |
|---|---|
| `{"content": "..."}` | `content` |
| `{"segment": {"content": "..."}}` | `segment.content` |
| `{"question": "...", "answer": "..."}` | `question,answer` |

#### Score Field / ID Field

スコアと ID のフィールド。該当しない場合は空欄にしてください。

#### Top K / Similarity Threshold

結果数と類似度閾値。テンプレート内の `{{ top_k }}` と `{{ similarity_threshold }}` を置き換えます。

### 高度な接続設定

「高度な接続設定を表示」をクリックして展開します。ほとんどの場合、変更は不要です。

| フィールド | 用途 | 変更が必要な場合 |
|-----------|------|----------------|
| Auth Header Name | 認証ヘッダー名（デフォルト：`Authorization`） | サービスが `X-API-Key` などのカスタムヘッダーを要求する場合 |
| Auth Header Prefix | 認証ヘッダーのプレフィックス（デフォルト：`Bearer`） | サービスが生トークン（空欄）や他のプレフィックスを要求する場合 |
| Extra Headers (JSON) | 追加リクエストヘッダー | マルチテナンシー、バージョンヘッダー、カスタムトレースヘッダー |
| Verify SSL | SSL 証明書の検証（デフォルト：オン） | 内部ネットワークの自己署名証明書 |
| Request Timeout | リクエストタイムアウト（デフォルト：30 秒） | レスポンスが遅いサービス |
| Debug Mode | デバッグログ（デフォルト：オフ） | 初回接続時やトラブルシューティング |

### 高度な検索設定

「高度な検索設定を表示」をクリックして展開します。ほとんどの場合、変更は不要です。

| フィールド | 用途 | 変更が必要な場合 |
|-----------|------|----------------|
| HTTP Method | 検索リクエストメソッド（デフォルト：`POST`） | API が `GET` などの他のメソッドを要求する場合 |
| Payload Mode | リクエスト送信方式（デフォルト：JSON body） | API がフォーム送信やクエリパラメータを要求する場合 |
| Metadata Field Mapping | 追加の返却フィールド | ソース、ページ番号、URL などの情報が必要な場合 |
| Skip Empty Content | 空コンテンツのスキップ（デフォルト：オン） | すべてのシナリオで有効のままにすることを推奨 |

### ファイルアップロード / ドキュメント削除

対応するトグルを有効にしてから、プロンプトに従って API 情報を入力してください。

## 設定例

### 最もシンプルな API

API が `POST {"query": "...", "top_k": N}` を受け取り、`{"results": [{"content": "...", "score": 0.9, "id": "1"}]}` を返す場合。

入力するだけ：
- **API Base URL**: `https://my-rag.com`
- **Retrieval Endpoint**: `/search`
- その他はすべて空欄/デフォルト

### Dify

- **API Base URL**: `https://api.dify.ai/v1`
- **API Key**: Dify Dataset API キー
- **Dataset ID**: Dify コンソールのデータセット ID
- **Retrieval Endpoint**: `/datasets/{{ dataset_id }}/retrieve`
- **Request Body Template**:

```json
{
  "query": "{{ query }}",
  "retrieval_model": {
    "search_method": "semantic_search",
    "reranking_enable": false,
    "reranking_mode": null,
    "reranking_model": {
      "reranking_provider_name": "",
      "reranking_model_name": ""
    },
    "weights": null,
    "top_k": {{ top_k }},
    "score_threshold_enabled": true,
    "score_threshold": {{ similarity_threshold }}
  }
}
```

- **Results Array Path**: `records`
- **Content Field(s)**: `segment.content`
- **Score Field**: `score`
- **ID Field**: `segment.id`

### GET リクエストの検索 API

API が `GET /search?q=xxx&limit=5` を使用し、`{"data": [{"text": "...", "relevance": 0.8}]}` を返す場合。

- **API Base URL**: `https://my-search.com`
- **Retrieval Endpoint**: `/search`
- **Request Body Template**: `{"q": "{{ query }}", "limit": {{ top_k }}}`
- **Results Array Path**: `data`
- **Content Field(s)**: `text`
- **Score Field**: `relevance`
- 「高度な検索設定」を開く → **HTTP Method**: `GET`、**Payload Mode**: `Query Params`

## トラブルシューティング

1. 「高度な接続設定」を開く → **Debug Mode** を有効にする
2. ログ内の最終 URL、メソッド、ペイロードが期待通りか確認する
3. レスポンス内の results_path が配列を指しているか確認する
4. content_fields、score_field、id_field が実際のフィールド名と一致しているか確認する
5. 内部ネットワークの HTTPS サービスの場合、Verify SSL を無効にする必要があるか確認する
