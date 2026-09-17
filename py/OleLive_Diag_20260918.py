# -*- coding: utf-8 -*-
"""
欧乐影院：影视仓 6.2.0 分类筛选适配版

功能：
- 主分类独立分页
- 地区、年份、子类型、首字母、免费/会员、排序筛选
- 独立 searchContentPage，适配本项目分析的影视仓 6.2.0 Python 桥
- 只输出公开 urls 播放线路；不读取 vip_urls，不绕过会员鉴权

排查版 20260918：默认分类路径沿用原 OleLive；未核实的新增筛选暂不发送。
失败显示诊断卡片；不把网络错误伪装为空列表。未完成电视运行验证。
"""

import base64
import hashlib
import json
import time
import urllib.parse
from datetime import datetime

import requests
from base.spider import Spider

try:
    from Crypto.Cipher import AES
except ImportError:
    AES = None


class Spider(Spider):
    ACCESS_VALUES = {
        "all": "3",
        "free": "1",
        "vip": "2",
    }

    SORT_VALUES = {
        "update": "update",
        "add": "addtime",
        "hot": "hits",
        "score": "score",
    }

    DEFAULT_AREAS = [
        "大陆", "香港", "台湾", "美国", "韩国", "日本", "印度", "英国",
        "法国", "加拿大", "西班牙", "德国", "俄罗斯", "意大利", "泰国",
        "新加坡", "马来西亚", "其它",
    ]

    def __init__(self):
        self.name = "欧乐排查版 0918"
        self.last_error = ""
        self.host = "https://olelive.com"
        self.api = "https://api.olelive.com"
        self.image_base = "https://static.olelive.com"
        self.header = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/136.0.0.0 Safari/537.36"
            ),
            "Referer": "https://olelive.com/",
            "Origin": "https://olelive.com",
        }
        self.timeout = 20
        self.page_size = 24
        self._types = []

    def getName(self):
        return self.name

    def init(self, extend=""):
        # ext 可选传 JSON，以便站点换域名时临时覆盖。
        if not extend:
            return
        try:
            cfg = json.loads(extend) if isinstance(extend, str) else extend
            if isinstance(cfg, dict):
                self.host = str(cfg.get("host") or self.host).rstrip("/")
                self.api = str(cfg.get("api") or self.api).rstrip("/")
                self.image_base = str(cfg.get("image") or self.image_base).rstrip("/")
                self.header["Referer"] = self.host + "/"
                self.header["Origin"] = self.host
        except Exception:
            pass

    def destroy(self):
        pass

    def isVideoFormat(self, url):
        return False

    def manualVideoCheck(self):
        return False

    def _sign(self):
        ts = str(int(time.time()))
        parts = [[], [], [], []]
        for ch in ts:
            bits = bin(ord(ch))[2:]
            parts[0].append(bits[2:3])
            parts[1].append(bits[3:4])
            parts[2].append(bits[4:5])
            parts[3].append(bits[5:])
        encoded = []
        for part in parts:
            value = hex(int("".join(part) or "0", 2))[2:]
            encoded.append(value.rjust(3, "0"))
        digest = hashlib.md5(ts.encode("utf-8")).hexdigest()
        return (
            digest[:3] + encoded[0] + digest[6:11] + encoded[1]
            + digest[14:19] + encoded[2] + digest[22:27]
            + encoded[3] + digest[30:]
        )

    def _decrypt(self, data):
        if AES is None:
            return data
        date_text = datetime.now().strftime("%Y-%m-%d")
        key = hashlib.md5(date_text.encode("utf-8")).hexdigest()[8:24]
        cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, iv=key.encode("utf-8"))
        plain = cipher.decrypt(base64.b64decode(data))
        return plain.rstrip(b"\x00").decode("utf-8", "ignore")

    def _api_get(self, path, params=None):
        self.last_error = ""
        query = dict(params or {})
        query["_vv"] = self._sign()
        try:
            response = requests.get(
                self.api + path,
                headers=self.header,
                params=query,
                timeout=self.timeout,
            )
            if response.status_code != 200:
                self.last_error = "HTTP {}".format(response.status_code)
                return None
            payload = response.json()
            if not isinstance(payload, dict):
                self.last_error = "响应外层不是JSON对象"
                return None
            if payload.get("code") != 0:
                self.last_error = "接口业务码 {}".format(str(payload.get("code"))[:40])
                return None
            data = payload.get("data")
            if not isinstance(data, str):
                return data
            try:
                return json.loads(data)
            except Exception:
                try:
                    return json.loads(self._decrypt(data))
                except Exception:
                    self.last_error = "数据解析/解密失败，请检查电视日期、时区和Crypto依赖"
                    return None
        except Exception as exc:
            self.last_error = "请求失败：" + type(exc).__name__
            return None

    @staticmethod
    def _unique_text(items):
        result = []
        seen = set()
        for value in items or []:
            text = str(value or "").strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
        return result

    def _load_types(self):
        if self._types:
            return
        data = self._api_get("/v1/pub/vod/list/type")
        if not isinstance(data, list):
            return
        for item in data:
            type_name = str(item.get("typeName") or "")
            type_en = str(item.get("typeEn") or "")
            if type_en == "chengren" or "直播" in type_name or "live" in type_en.lower():
                continue
            children = []
            for child in item.get("children") or []:
                child_name = str(child.get("typeName") or "")
                child_en = str(child.get("typeEn") or "")
                if "直播" in child_name or "live" in child_en.lower():
                    continue
                child_id = child.get("typeId")
                if child_name and child_id is not None:
                    children.append({"n": child_name, "v": str(child_id)})
            self._types.append({
                "type_name": type_name,
                "type_id": str(item.get("typeId")),
                "children": children,
                "area": self._unique_text(item.get("area")),
                "year": self._unique_text(item.get("year")),
            })

    @staticmethod
    def _values(names, all_name="全部", all_value="0"):
        values = [{"n": all_name, "v": all_value}]
        values.extend({"n": str(name), "v": str(name)} for name in names)
        return values

    def _filter_for_type(self, item):
        areas = item.get("area") or self.DEFAULT_AREAS
        years = item.get("year") or [str(y) for y in range(datetime.now().year, 1999, -1)]
        letters = [chr(code) for code in range(ord("A"), ord("Z") + 1)]

        type_values = [{"n": "全部类型", "v": "0"}]
        type_values.extend(item.get("children") or [])

        return [
            {
                "key": "area",
                "name": "地区",
                "value": self._values(areas, "全部地区", "0"),
            },
            {
                "key": "year",
                "name": "年份",
                "value": self._values(years, "全部年份", "0"),
            },
            {
                "key": "class",
                "name": "类型",
                "value": type_values,
            },

        ]

    def _filters(self):
        return {
            item["type_id"]: self._filter_for_type(item)
            for item in self._types
        }

    def _pic(self, item):
        value = str(item.get("picThumb") or item.get("pic") or "")
        if not value:
            return ""
        if value.startswith("http"):
            return value
        return self.image_base + (value if value.startswith("/") else "/" + value)

    def _make_vod(self, item):
        remarks = str(item.get("remarks") or "")
        score = item.get("score")
        if score not in (None, "", 0, "0") and str(score) not in remarks:
            remarks = (remarks + "  " + str(score) + "分").strip()
        return {
            "vod_id": str(item.get("id") or ""),
            "vod_name": str(item.get("name") or ""),
            "vod_pic": self._pic(item),
            "vod_remarks": remarks,
        }

    def homeContent(self, filter):
        result = {"class": [], "list": []}
        self._load_types()
        result["class"] = [
            {"type_name": item["type_name"], "type_id": item["type_id"]}
            for item in self._types
        ]
        if filter:
            result["filters"] = self._filters()
        if not self._types:
            result["class"] = [{"type_id": "__diagnostic__", "type_name": "排查0918"}]
            result["list"] = self._diagnostic(self.last_error or "分类响应不是有效列表", 1)["list"]
            return result
        data = self._api_get("/v1/pub/index/vod/data/2")
        if isinstance(data, dict):
            result["list"] = [self._make_vod(item) for item in data.get("list") or []]
        return result

    def homeVideoContent(self):
        return {"list": []}

    def categoryContent(self, tid, pg, filter, extend):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        if tid == "__diagnostic__":
            self._types = []
            self._load_types()
            return self._diagnostic(self.last_error or "请重新加载站点分类", page)
        if isinstance(extend, str):
            try:
                extend = json.loads(extend)
            except ValueError:
                return self._diagnostic("筛选参数不是有效JSON", page)
        ext = extend if isinstance(extend, dict) else {}
        if (str(ext.get("letter") or "0") != "0"
                or str(ext.get("access") or "3") != "3"
                or str(ext.get("sort") or "update") != "update"):
            return self._diagnostic("新增筛选映射未核实，请重置筛选或使用新的站点key", page)
        area = str(ext.get("area") or "0")
        year = str(ext.get("year") or "0")
        child_type = str(ext.get("class") or "0")
        letter = str(ext.get("letter") or "0").upper()
        access = str(ext.get("access") or self.ACCESS_VALUES["all"])
        order = str(ext.get("sort") or self.SORT_VALUES["update"])

        if access not in self.ACCESS_VALUES.values():
            access = self.ACCESS_VALUES["all"]
        if order not in self.SORT_VALUES.values():
            order = self.SORT_VALUES["update"]
        if letter != "0" and (len(letter) != 1 or not letter.isalpha()):
            letter = "0"

        # 沿用原脚本的默认常量；不推定前三段的业务含义。
        path = (
            "/v1/pub/vod/list/1/{access}/{letter}/{area}/{tid}/{child}/{year}/"
            "{order}/{page}/{limit}"
        ).format(
            access=urllib.parse.quote(access, safe=""),
            letter=urllib.parse.quote(letter, safe=""),
            area=urllib.parse.quote(area, safe=""),
            tid=urllib.parse.quote(str(tid), safe=""),
            child=urllib.parse.quote(child_type, safe=""),
            year=urllib.parse.quote(year, safe=""),
            order=urllib.parse.quote(order, safe=""),
            page=page,
            limit=self.page_size,
        )
        data = self._api_get(path)
        result = {
            "list": [],
            "page": page,
            "pagecount": page,
            "limit": self.page_size,
            "total": 0,
        }
        if not isinstance(data, dict):
            return self._diagnostic(self.last_error or "分类data不是JSON对象", page)
        if not isinstance(data.get("list"), list):
            return self._diagnostic("分类响应缺少list数组", page)
        result["list"] = [self._make_vod(item) for item in data["list"] if isinstance(item, dict)]
        if not result["list"] and page == 1:
            return self._diagnostic("接口成功但列表为空，请重置筛选后比较原版", page)
        try:
            total = int(data.get("total") or 0)
        except Exception:
            total = 0
        result["total"] = total
        result["pagecount"] = max(1, (total + self.page_size - 1) // self.page_size) if total else (page + 1 if len(result["list"]) == self.page_size else page)
        return result

    def _diagnostic(self, message, page):
        # 诊断占位卡片，不是影片；ID携带提示避免并发覆盖错误信息。
        return {"list": [{"vod_id": "__ole_error__:" + message,
                         "vod_name": "排查0918：" + message,
                         "vod_pic": "", "vod_remarks": "诊断提示（非影片）"}],
                "page": page, "pagecount": page, "limit": self.page_size, "total": 0}

    def detailContent(self, ids):
        if ids and str(ids[0]).startswith("__ole_error__:"):
            return {"list": [{"vod_id": str(ids[0]), "vod_name": "欧乐诊断0918",
                             "vod_content": str(ids[0]).split(":", 1)[1],
                             "vod_play_from": "", "vod_play_url": ""}]}
        if not ids or not ids[0]:
            return {"list": []}
        vod_id = str(ids[0])
        data = self._api_get("/v1/pub/vod/detail/{}/1".format(urllib.parse.quote(vod_id, safe="")))
        if not isinstance(data, dict):
            return {"list": []}

        episodes = []
        for item in data.get("urls") or []:
            title = str(item.get("title") or "第{}集".format(item.get("index") or ""))
            url = str(item.get("url") or "")
            if url:
                episodes.append("{}${}".format(title.replace("$", " ").replace("#", " "), url))
        if not episodes:
            return {"list": []}

        return {"list": [{
            "vod_id": vod_id,
            "vod_name": str(data.get("name") or ""),
            "vod_pic": self._pic(data),
            "vod_remarks": str(data.get("remarks") or ""),
            "vod_year": str(data.get("year") or ""),
            "vod_area": str(data.get("area") or ""),
            "type_name": str(data.get("typeId1Name") or ""),
            "vod_actor": str(data.get("actor") or ""),
            "vod_director": str(data.get("director") or ""),
            "vod_content": str(data.get("content") or data.get("blurb") or ""),
            "vod_play_from": "欧乐公开线路",
            "vod_play_url": "#".join(episodes),
        }]}

    def searchContent(self, key, quick):
        return self.searchContentPage(key, quick, "1")

    def searchContentPage(self, key, quick, pg):
        try:
            page = max(1, int(pg))
        except Exception:
            page = 1
        keyword = urllib.parse.quote(str(key), safe="")
        data = self._api_get(
            "/v1/pub/index/search/{}/vod/0/{}/{}".format(keyword, page, self.page_size)
        )
        result = {"list": [], "page": page, "pagecount": page, "limit": self.page_size, "total": 0}
        if not isinstance(data, dict):
            return result
        for group in data.get("data") or []:
            if group.get("type") == "vod":
                result["list"].extend(self._make_vod(item) for item in group.get("list") or [])
        try:
            total = int(data.get("total") or 0)
        except Exception:
            total = 0
        if total:
            result["total"] = total
            result["pagecount"] = max(page, (total + self.page_size - 1) // self.page_size)
        elif len(result["list"]) == self.page_size:
            result["pagecount"] = page + 1
        return result

    def playerContent(self, flag, id, vipFlags):
        return {
            "parse": 0,
            "url": id,
            "header": {
                "User-Agent": self.header["User-Agent"],
                "Referer": self.host + "/",
            },
            "playUrl": "",
        }

    def localProxy(self, param):
        return None



