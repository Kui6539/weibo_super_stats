from __future__ import annotations

import unittest

from modules.weibo_emoticons import _api_payload_to_index, extract_weibo_emoticon_names


class WeiboEmoticonTests(unittest.TestCase):
    def test_extract_weibo_emoticon_names(self) -> None:
        self.assertEqual(extract_weibo_emoticon_names("你好[哈哈][doge]", "再见[泪]"), {"哈哈", "doge", "泪"})

    def test_api_payload_to_index_includes_newer_emoticons(self) -> None:
        index = _api_payload_to_index(
            [
                {
                    "phrase": "[捂嘴哭]",
                    "url": "https://face.t.sinajs.cn/t4/appstyle/expression/ext/normal/b4/2025_wuzuiku_mobile.png",
                    "type": "face",
                }
            ]
        )

        self.assertEqual(
            index["捂嘴哭"]["source"],
            "https://face.t.sinajs.cn/t4/appstyle/expression/ext/normal/b4/2025_wuzuiku_mobile.png",
        )


if __name__ == "__main__":
    unittest.main()
