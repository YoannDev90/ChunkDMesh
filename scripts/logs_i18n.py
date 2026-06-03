import os

import json5
import requests


def lang_to_file(lang: str, path: str = "server/config/locales") -> str:
    return f"{path}/{lang}.json5"


def translate(
    en_file_path: str, target_langs: list, output_path: str = "server/config/locales"
):
    os.makedirs(output_path, exist_ok=True)

    with open(en_file_path) as f:
        en_config = json5.load(f)
        texts = en_config.get("en", {})

    print(f"📝 Found {len(texts)} messages to translate")
    print(f"🌍 Target languages: {', '.join(target_langs)}\n")

    for lang in target_langs:
        print(f"⏳ Translating to {lang.upper()}...")
        translations = {}

        for key, text in texts.items():
            url = "https://api.mymemory.translated.net/get"
            params = {"q": text, "langpair": f"en|{lang}"}

            try:
                resp = requests.get(url, params=params, timeout=5)
                resp.raise_for_status()

                translated = resp.json()["responseData"]["translatedText"]
                translations[key] = translated

            except Exception as e:
                translations[key] = text

        output_file = lang_to_file(lang, output_path)
        with open(output_file, "w") as f:
            json5.dump({lang: translations}, f, indent=2)

        print(f"✅ Saved to {output_file}\n")


if __name__ == "__main__":
    translate("server/config/locales/en.json5", ["fr", "es", "de"])
