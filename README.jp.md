# arc-crawler

🌐 [English](https://github.com/Amachoma/arc-crawler/blob/master/README.md) | [日本語](https://github.com/Amachoma/arc-crawler/blob/master/README.jp.md)

![img](https://raw.githubusercontent.com/Amachoma/arc-crawler/master/docs/arc-crawler-logo.svg)

`arc-crawler` は、複雑なウェブスクレイピングタスクを簡素化するために設計された柔軟なPythonモジュールです。
効率的で再開可能なデータ収集、構造化された出力管理、カスタマイズ可能なデータ処理に焦点を当てています。


## ✨ 機能

* **柔軟なフェッチ戦略**: 高速な並行フェッチと、正確な逐次URLフェッチの両方をサポートし、
カスタマイズ可能な遅延設定が可能です。
* **進行状況の再開可能な追跡**: 進行状況を自動的に追跡するため、中断からのシームレスな再開や、
データへの増分的な追加が可能です。
* **効率的な出力管理**: フェッチされたデータと一緒にメタデータを書き込むため、
非常に大きな出力ファイルでも、組み込みの`IndexReader`を介して簡単にアクセスし、クエリできます。
* **カスタマイズ可能なデータ処理**: リクエスト前の処理、レスポンス後の処理、
カスタムメタデータインデックス作成のための柔軟なコールバック関数を提供します。


## 🚀 クイックスタート

### インストール

`arc-crawler` は`pip`を使って簡単にインストールできます。

```bash
pip install arc-crawler
```

### 基本的な使用法

この例では、いくつかのWikipediaページを迅速にクロールし、組み込みの `html_body_processor` を使用して、
`<body>` タグの内容のみを保存する方法を示します。

```python
from arc_crawler import Crawler, html_body_processor

def crawl_wikipedia():
    urls_to_fetch = [
        "https://en.wikipedia.org/wiki/JavaScript",
        "https://en.wikipedia.org/wiki/Go_(programming_language)",
        "https://en.wikipedia.org/wiki/Python_(programming_language)",
        "https://en.wikipedia.org/wiki/Node.js",
    ]

    # クローラーを初期化し、新しい './output' ディレクトリに出力します
    crawler = Crawler(out_file_path="./output")

    # URLをフェッチし、レスポンスを処理して<body>タグのみを保存し、'wiki-programming' ファイルに保存します
    reader = crawler.get( # await を追加
        urls_to_fetch,
        out_file_name="wiki-programming",
        response_processor=html_body_processor, # 組み込みのプロセッサを使用
    )

    print(f"Wikipediaのエントリを{len(reader)}件、正常に収集しました。")
    print(f"データセットファイルは次のフォルダーに保存されました: {reader.path}")

if __name__ == "__main__":
    crawl_wikipedia()
```

---

## 📚 その他の例と高度な使用法

カスタムレスポンス/リクエストプロセッサ、メタデータインデックス作成、JSONコンテンツの処理など、
高度な機能を示すより詳細な例については、リポジトリ内の [basic.py](https://github.com/Amachoma/arc-crawler/blob/master/examples/basic.py) 
および [advanced.py](https://github.com/Amachoma/arc-crawler/blob/master/examples/advanced.py) ファイルを参照してください。

さらに、すべての利用可能なパラメーター、戻り値の型、内部動作を含む包括的なAPIドキュメントについては、
`arc-crawler` モジュールのソースコード内の詳細なドキュメント文字列（例：Pythonインタープリターで
`help(Crawler)`や`help(Crawler.get)`を使用するか、IDEツールを介してドキュメントにアクセス）を参照してください。

---

## 💡 ベストプラクティス：スクレイピングとパースの分離

ウェブスクレイピングにおける最適な効率と保守性のために、`response_processor` コールバック内で生の、
**変更されていないレスポンスデータを最初に保存することを強く推奨します**。
フェッチ中に複雑なパースロジックを直接実装することは避けてください。

このアプローチには下記の利点があります：

* **反復的な改善**: ローカルデータに対してパースロジックを改良・改善することができ、
毎回すべてを再フェッチする必要がありません。
* **回復力と速度**: フェッチ段階は純粋にデータ取得に焦点を当てるため、ネットワークの問題に対する回復力が向上し、
ダウンロード速度を最大化できます。
* **リソース管理**: CPUとメモリを消費するパース処理を別のプロセスやスクリプトにオフロードすることで、 
I/Oバウンドなフェッチ操作の速度低下を防ぎます。

要するに、`arc-crawler` では、生のソースデータの保存に焦点を当ててください。パースは、
フェッチが完了した後に行われるべき、別の独立したステップです。