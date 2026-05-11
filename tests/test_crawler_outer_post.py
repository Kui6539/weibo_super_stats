import unittest

from crawler import parse_posts_from_html


class CrawlerOuterPostTests(unittest.TestCase):
    def test_parse_uses_outer_repost_card_only(self):
        html = """
        <div action-type="feed_list_item" mid="outer123" tbinfo="ouid=10001">
          <div class="WB_detail">
            <a node-type="feed_list_item_name" usercard="id=10001">外层作者</a>
            <a node-type="feed_list_item_date" href="//weibo.com/10001/outer123" title="2026-05-10 12:00">5月10日</a>
            <div node-type="feed_list_content">外层转发正文 #warma超话#</div>
            <div class="WB_media_wrap" action-data="clear_picSrc=https://wx1.sinaimg.cn/orj360/outerpic.jpg"></div>
            <div class="WB_feed_expand">
              <div action-type="feed_list_item" mid="inner999" tbinfo="ouid=99999">
                <a node-type="feed_list_item_name" usercard="id=99999">被转发作者</a>
                <a node-type="feed_list_item_date" href="//weibo.com/99999/inner999" title="2026-05-09 08:00">5月9日</a>
                <div node-type="feed_list_content">被转发的别人原帖正文，这里更长，不能覆盖外层转发正文。</div>
                <div class="WB_media_wrap" action-data="clear_picSrc=https://wx1.sinaimg.cn/orj360/innerpic.jpg"></div>
                <div class="WB_video"></div>
                <a action-type="feed_list_forward">转发 99</a>
                <a action-type="feed_list_comment">评论 88</a>
                <a action-type="feed_list_like">赞 77</a>
              </div>
            </div>
            <div class="WB_feed_handle">
              <a action-type="feed_list_forward">转发 1</a>
              <a action-type="feed_list_comment">评论 2</a>
              <a action-type="feed_list_like">赞 3</a>
            </div>
          </div>
        </div>
        """

        posts = parse_posts_from_html(html)

        self.assertEqual(len(posts), 1)
        post = posts[0]
        self.assertEqual(post["post_id"], "outer123")
        self.assertEqual(post["author_id"], "10001")
        self.assertEqual(post["user_name"], "外层作者")
        self.assertIn("外层转发正文", post["content"])
        self.assertNotIn("被转发的别人原帖正文", post["content"])
        self.assertEqual(post["reposts"], 1)
        self.assertEqual(post["comments"], 2)
        self.assertEqual(post["likes"], 3)
        self.assertEqual(post["engagement_total"], 6)
        self.assertIn("outerpic", post["original_image_urls"])
        self.assertNotIn("innerpic", post["original_image_urls"])
        self.assertFalse(post["has_video"])
        self.assertEqual(post["post_url"], "https://weibo.com/10001/outer123")


if __name__ == "__main__":
    unittest.main()
