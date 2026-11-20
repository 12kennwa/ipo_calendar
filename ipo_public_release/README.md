# 楽天証券 IPOカレンダー（公開版）

楽天証券で取り扱われるIPOの日程と、確認済みの過去実績を表示するStreamlitアプリです。

## Streamlit Community Cloudへの公開

1. このフォルダ内のファイルをGitHubリポジトリへアップロードします。
2. Streamlit Community Cloudでリポジトリを選択します。
3. Main file pathに `app.py` を指定してDeployします。

## ローカルでの起動

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 秘密情報

APIキーはリポジトリへ保存しないでください。必要な場合はStreamlit Community CloudのSecretsに設定します。

この公開版には `.streamlit/secrets.toml`、`.env`、キャッシュ、バックアップ、J-Quantsの自動取得画面を含めていません。

## 注意

- 価格を取得・確認できない場合は「未取得」と表示します。
- 表示される過去実績は保存済みの楽天証券取扱銘柄を対象としています。
- 投資判断を示すものではありません。
