# -*- coding: utf-8 -*-
# OLE欧乐 - FongMi / TVBox Python Spider
# 仅使用公开网页结构，不实现/绕过站点内部签名、登录、VIP 或 DRM。
#
# 配置示例：
# {
#   "key": "OLE",
#   "name": "🎬 欧乐｜网页",
#   "type": 3,
#   "api": "./py/olevod_public.py",
#   "searchable": 1,
#   "quickSearch": 0,
#   "filterable": 1,
#   "changeable": 1
# }

import sys
sys.path.append('..')

from base.spider import Spider
import re
from urllib.parse import quote, urljoin


class Spider(Spider):
    host = "https://www.olevod.com"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Linux; Android 10; Android TV) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        ),
        "Referer": "https://www.olevod.com/",
    }

    def getName(self):
        return "OLE欧乐公开网页"

    def init(self, extend=""):
        if isinstance(extend, str) and extend.strip().startswith("http"):
            self.host = extend.strip().rstrip("/")

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return bool(re.search(r"\.(m3u8|mp4|mkv|flv)(\?|$)", url or "", re.I))

    def manualVideoCheck(self):
        return False

    # ---------- helpers ----------

    def _get(self, url):
        if url.startswith("/"):
            url = self.host + url
        rsp = self.fetch(url, headers=self.headers)
        return rsp.text if rsp else ""

    def _root(self, html):
        return self.html(html)

    def _clean(self, s):
        if s is None:
            return ""
        s = re.sub(r"<[^>]+>", "", str(s))
        s = s.replace("&nbsp;", " ")
        return re.sub(r"\s+", " ", s).strip()

    def _first(self, arr, default=""):
        if not arr:
            return default
        x = arr[0]
        if hasattr(x, "xpath"):
            try:
                return self._clean(x.xpath("string(.)"))
            except Exception:
                return self._clean(x)
        return self._clean(x)

    def _abs(self, url):
        if not url:
            return ""
        return urljoin(self.host + "/", url)

    def _vod_id_from_href(self, href):
        m = re.search(r"/vod/detail/id/(\d+)", href or "")
        return m.group(1) if m else ""

    def _parse_cards(self, html):
        if not html:
            return []

        root = self._root(html)
        # OLE 页面是 MacCMS 风格；用宽松 XPath，减少换模板时失效概率。
        anchors = root.xpath(
            '//a[contains(@href,"/vod/detail/id/") '
            'or contains(@href,"?m=vod-detail-id-")]'
        )

        out = []
        seen = set()

        for a in anchors:
            href = self._first(a.xpath("./@href"))
            vid = self._vod_id_from_href(href)

            if not vid:
                m = re.search(r"vod-detail-id-(\d+)", href or "")
                vid = m.group(1) if m else ""

            if not vid or vid in seen:
                continue

            title = self._first(a.xpath("./@title"))
            if not title:
                title = self._first(a.xpath('.//img/@alt'))
            if not title:
                title = self._first(a.xpath("string(.)"))

            # 排除纯“查看详情”等无意义链接
            if not title or title in ("查看详情", "详情"):
                # 尝试从父容器标题取
                box = a.xpath(
                    'ancestor::*[contains(@class,"module-item") '
                    'or contains(@class,"search-list") '
                    'or self::li][1]'
                )
                if box:
                    title = self._first(
                        box[0].xpath(
                            './/a[contains(@href,"/vod/detail/id/")]/@title'
                            ' | .//h3//a/text() | .//h4//a/text()'
                        )
                    )

            if not title:
                continue

            box = a.xpath(
                'ancestor::*[contains(@class,"module-item") '
                'or contains(@class,"module-card") '
                'or contains(@class,"search-list") '
                'or self::li][1]'
            )
            box = box[0] if box else a

            pic = self._first(
                box.xpath(
                    './/img/@data-original | .//img/@data-src | .//img/@data-lazy-src | .//img/@src'
                )
            )
            pic = self._abs(pic)

            remarks = self._first(
                box.xpath(
                    './/*[contains(@class,"remarks")]/text()'
                    ' | .//*[contains(@class,"note")]/text()'
                    ' | .//*[contains(@class,"module-item-text")]/text()'
                    ' | .//*[contains(@class,"module-item-note")]/text()'
                )
            )

            out.append({
                "vod_id": vid,
                "vod_name": title,
                "vod_pic": pic,
                "vod_remarks": remarks,
            })
            seen.add(vid)

        return out

    def _page_count(self, html):
        m = re.search(r"共有\s*(\d+)\s*页", html or "")
        if not m:
            m = re.search(r"当前第\s*\d+\s*页\s*/\s*共有\s*(\d+)\s*页", html or "")
        return int(m.group(1)) if m else 1

    # ---------- FongMi Spider API ----------

    def homeContent(self, filter):
        classes = [
            {"type_name": "电影", "type_id": "1"},
            {"type_name": "连续剧", "type_id": "2"},
            {"type_name": "综艺", "type_id": "3"},
            {"type_name": "动漫", "type_id": "4"},
        ]

        result = {"class": classes}

        if filter:
            areas = ["", "大陆", "香港", "台湾", "美国", "韩国", "日本", "英国", "法国", "泰国", "马来西亚"]
            years = ["", "2026", "2025", "2024", "2023", "2022", "2021", "2020", "2019", "2018", "2017"]
            langs = ["", "国语", "英语", "粤语", "韩语", "日语"]
            sorts = [
                {"n": "最新", "v": "time"},
                {"n": "最热", "v": "hits"},
                {"n": "评分", "v": "score"},
            ]

            filters = {}
            for tid in ("1", "2", "3", "4"):
                filters[tid] = [
                    {
                        "key": "area",
                        "name": "地区",
                        "value": [{"n": "全部" if not v else v, "v": v} for v in areas],
                    },
                    {
                        "key": "year",
                        "name": "年份",
                        "value": [{"n": "全部" if not v else v, "v": v} for v in years],
                    },
                    {
                        "key": "lang",
                        "name": "语言",
                        "value": [{"n": "全部" if not v else v, "v": v} for v in langs],
                    },
                    {
                        "key": "by",
                        "name": "排序",
                        "value": sorts,
                    },
                ]
            result["filters"] = filters

        return result

    def homeVideoContent(self):
        html = self._get(self.host + "/")
        return {"list": self._parse_cards(html)[:40]}

    def categoryContent(self, tid, pg, filter, extend):
        pg = str(pg or "1")
        seg = []

        # MacCMS 风格路由，字段顺序不敏感
        if extend:
            for k in ("area", "by", "lang", "year"):
                v = extend.get(k, "")
                if v:
                    seg.extend([k, quote(str(v), safe="")])

        path = "/index.php/vod/show/"
        if seg:
            path += "/".join(seg) + "/"
        path += "id/{}/page/{}.html".format(tid, pg)

        html = self._get(path)
        return {
            "list": self._parse_cards(html),
            "page": int(pg) if pg.isdigit() else 1,
            "pagecount": self._page_count(html),
            "limit": 48,
            "total": 9999,
        }

    def detailContent(self, ids):
        vid = str(ids[0])
        url = self.host + "/index.php/vod/detail/id/{}.html".format(vid)
        html = self._get(url)
        root = self._root(html)

        name = self._first(
            root.xpath(
                '//meta[@property="og:title"]/@content'
                ' | //h1/text() | //h2/text()'
            )
        )
        name = re.sub(r"[_\-]?(在线观看|高清播放).*$", "", name).strip()

        pic = self._first(
            root.xpath(
                '//meta[@property="og:image"]/@content'
                ' | //img[contains(@class,"lazyload")]/@data-original'
                ' | //img[contains(@class,"lazyload")]/@data-src'
            )
        )
        pic = self._abs(pic)

        content = self._first(
            root.xpath(
                '//meta[@name="description"]/@content'
                ' | //div[contains(@class,"vod_content")]//text()'
                ' | //div[contains(@class,"module-info-introduction")]//text()'
                ' | //div[contains(@class,"module-info-introduction-content")]//text()'
            )
        )

        actor = ""
        director = ""
        year = ""
        area = ""

        all_text = self._clean(root.xpath("string(.)"))
        m = re.search(r"主演[:：]\s*([^导演简介]+)", all_text)
        if m:
            actor = self._clean(m.group(1))
        m = re.search(r"导演[:：]\s*([^主演简介]+)", all_text)
        if m:
            director = self._clean(m.group(1))
        m = re.search(r"\b(20\d{2}|19\d{2})\b", all_text)
        if m:
            year = m.group(1)

        for candidate in ("大陆", "香港", "台湾", "美国", "韩国", "日本", "英国", "法国", "泰国", "马来西亚"):
            if candidate in all_text:
                area = candidate
                break

        # 详情页公开播放链接：按 sid 分组
        links = root.xpath('//a[contains(@href,"/vod/play/id/")]')
        groups = {}
        for a in links:
            href = self._first(a.xpath("./@href"))
            m = re.search(r"/vod/play/id/(\d+)/sid/(\d+)/nid/(\d+)", href or "")
            if not m or m.group(1) != vid:
                continue
            sid, nid = m.group(2), m.group(3)
            ep = self._first(a.xpath("string(.)")) or ("第{}集".format(nid))
            ep = ep.replace("$", " ").replace("#", " ")
            play_page = self._abs(href)
            groups.setdefault(sid, [])
            # 同一 nid 去重
            if not any(x[0] == nid for x in groups[sid]):
                groups[sid].append((nid, ep, play_page))

        # 如果详情页模板没有直接输出播放链接，至少保留公开播放页入口
        if not groups:
            groups["1"] = [(
                "1",
                "播放",
                self.host + "/index.php/vod/play/id/{}/sid/1/nid/1.html".format(vid),
            )]

        play_from = []
        play_urls = []

        for sid in sorted(groups.keys(), key=lambda x: int(x) if x.isdigit() else 999):
            eps = sorted(
                groups[sid],
                key=lambda x: int(x[0]) if str(x[0]).isdigit() else 999999
            )
            play_from.append("欧乐线路{}".format(sid))
            play_urls.append("#".join(
                "{}${}".format(ep, purl) for _, ep, purl in eps
            ))

        vod = {
            "vod_id": vid,
            "vod_name": name or ("欧乐 " + vid),
            "vod_pic": pic,
            "vod_year": year,
            "vod_area": area,
            "vod_actor": actor,
            "vod_director": director,
            "vod_content": content,
            "vod_play_from": "$$$".join(play_from),
            "vod_play_url": "$$$".join(play_urls),
        }
        return {"list": [vod]}

    def searchContent(self, key, quick, pg="1"):
        pg = str(pg or "1")
        q = quote(str(key), safe="")
        # MacCMS 常用搜索路由
        url = self.host + "/index.php/vod/search/page/{}/wd/{}.html".format(pg, q)
        html = self._get(url)

        # 某些模板使用 wd 在前；若第一页没有结果，做一次兼容回退
        items = self._parse_cards(html)
        if not items and pg == "1":
            url2 = self.host + "/index.php/vod/search/wd/{}.html".format(q)
            html2 = self._get(url2)
            items = self._parse_cards(html2)
            if items:
                html = html2

        return {
            "list": items,
            "page": int(pg) if pg.isdigit() else 1,
            "pagecount": self._page_count(html),
            "limit": 20,
            "total": 9999,
        }

    def playerContent(self, flag, id, vipFlags):
        # id 是公开播放页面 URL。
        # 不解析站点内部签名/受保护接口，让 FongMi 自己走网页解析/嗅探流程。
        if self.isVideoFormat(id):
            return {
                "parse": 0,
                "url": id,
                "header": {
                    "User-Agent": self.headers["User-Agent"],
                    "Referer": self.host + "/",
                }
            }

        return {
            "parse": 1,
            "url": id,
            "header": {
                "User-Agent": self.headers["User-Agent"],
                "Referer": self.host + "/",
            }
        }
