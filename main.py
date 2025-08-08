from turtle import up
from pkg.plugin.context import register, handler, llm_func, BasePlugin, APIHost, EventContext
from pkg.plugin.events import *  # 导入事件类
from mirai import MessageChain,At,Image
import asyncio
import os
import json
import requests

"""查询频率，单位为秒，推荐为60"""
CHECK_DELAY = 60
"""发生问题时，是否通知管理员(通知则把ID修改为机器人管理员的QQ)"""
NOTIFY_ADMIN = False
ADMIN_ID = None   # int

@register(name="BilibiliReminder", description="订阅B站UP主的开播状态信息", version="0.5", author="Amateur")
class BilibiliReminder(BasePlugin):
    # 插件加载时触发
    def __init__(self, host: APIHost):
        # 检测是否存在subscription.json
        if not os.path.exists("subscription.json"):
            with open("subscription.json", "w", encoding="utf-8") as f:
                data = {
                    "group_ids":[]
                }
                '''
                样例示范：
                {
                 "group_ids":[],        # 群号列表
                 "group_id": {          # 群号
                     "room_ids": [
                         "room_id1",
                         "room_id2"
                     ],
                     "person_ids": [
                         "person_id1",
                         "person_id2"
                     ],
                     "person_id1": {
                         "up_name1" : "room_id1",
                         "up_name2" : "room_id2"
                     },
                     "room_id": [
                         "0",           # 房间状态码
                         "member_id1",
                         "member_id2"
                     ]
                 }
                 '''
                json.dump(data, f, indent=4)
        try:
            with open("subscription.json", "r", encoding="utf-8") as f:
                self.subscription = json.load(f)
        except json.JSONDecodeError:
            self.ap.logger.error("subscription.json decoding failed")
            print("subscription.json decoding failed")

    # 异步初始化
    async def initialize(self):
        pass
    # 写入json
    def write_json(self):
        with open("subscription.json", "w", encoding="utf-8") as f:
            json.dump(self.subscription, f, indent=4)

    # 执行任务
    async def run(self, ctx:EventContext):
        while True:
            for group_id in self.subscription["group_ids"]:
                for room_id in self.subscription[group_id]["room_ids"]:
                    if int(self.subscription[group_id][room_id][0]) == 0:  # 上一时段状态为未开播时
                        live_status = self.check_room_live(room_id)
                        if live_status == 1:
                            self.subscription[group_id][room_id][0] = 1 # 修改开播状态
                            await self.notify_person(group_id,room_id,ctx) # 通知群友
                    elif int(self.subscription[group_id][room_id][0]) == 1:  # 上一时段为开播时
                        live_status = self.check_room_live(room_id)
                        if live_status == 0:
                            self.subscription[group_id][room_id][0] = 0  # 修改未开播状态
                        elif live_status == 2: # 增加轮播状态
                            self.subscription[group_id][room_id][0] = 0  # 修改未开播状态
                    else:
                        if NOTIFY_ADMIN:
                            await ctx.send_message("person",ADMIN_ID,[f"直播间通知插件出了点问题，去看看后台,房间号{room_id},群号：{group_id}，状态码：{self.subscription[group_id][room_id][0]}"])
                    self.write_json()
            await asyncio.sleep(CHECK_DELAY)

    # 通知群友
    async def notify_person(self,group_id,room_id,ctx:EventContext):  # 一直在重复请求，不知道会不会被ban，出问题再说
        API = f'https://api.live.bilibili.com/xlive/web-room/v1/index/getRoomBaseInfo?room_ids={room_id}&req_biz=video'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://live.bilibili.com/{room_id}",
        }
        try:
            response = requests.get(API, headers=headers)
            response.raise_for_status()  # 如果请求返回错误状态码，会引发异常
            data = response.json()
            room_id_real = next(iter(data["data"]["by_room_ids"]))  # 真实房间号
            room_cover = data["data"]["by_room_ids"][room_id_real]["cover"]   # 封面
            room_title = data["data"]["by_room_ids"][room_id_real]["title"]   # 直播间标题
            up_name = data["data"]["by_room_ids"][room_id_real]["uname"]      # UP主
            room_url = data["data"]["by_room_ids"][room_id_real]["live_url"]  # 直播间地址
            atperson = MessageChain()
            for person_id in self.subscription[group_id][room_id][1:]:  # 排除状态码
                atperson.append(At(int(person_id)))
            await ctx.send_message("group",int(group_id),atperson + MessageChain([
                f"\n您订阅的直播间开播啦！",
                Image(url=room_cover),
                f"直播间标题：{room_title}",
                f"\nUP主：{up_name}",
                f"\n直播间地址：{room_url}"
            ]))
            if NOTIFY_ADMIN:
                await ctx.send_message("person", int(ADMIN_ID),[f"朝{group_id}的{atperson}发送了订阅信息"])
            self.ap.logger.info(f"朝{group_id}的{atperson}发送了订阅信息")
        except Exception as e:
            self.ap.logger.error(f"在调用notify_person函数时，发生错误：{e}")

    # 查询直播间状态
    def check_room_live(self,room_id):
        API = f'https://api.live.bilibili.com/xlive/web-room/v1/index/getRoomBaseInfo?room_ids={room_id}&req_biz=video'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://live.bilibili.com/{room_id}",
        }
        try:
            response = requests.get(API, headers=headers)
            response.raise_for_status()  # 如果请求返回错误状态码，会引发异常
            data = response.json()
            room_id_real = next(iter(data["data"]["by_room_ids"]))  # 真实房间号
            live_status = int(data["data"]["by_room_ids"][room_id_real]["live_status"])
            return live_status
        except Exception as e:
            self.ap.logger.error(f"在调用check_room_live函数时，访问URL失败，发生错误：{e}")
            return -400  # 400：Bad Request

    # 检查B站直播间是否存在
    def check_if_exit(self, room_id):
        API = f'https://api.live.bilibili.com/xlive/web-room/v1/index/getRoomBaseInfo?room_ids={room_id}&req_biz=video'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://live.bilibili.com/{room_id}",
        }
        try:
            response = requests.get(API, headers=headers)
            response.raise_for_status()  # 如果请求返回错误状态码，会引发异常
            data = response.json()
            code = data['code']
        except Exception as e:
            self.ap.logger.error(f"在调用check_if_exit函数时，访问URL失败，发生错误：{e}")
            return e
        return code

    # 获取UP主名称
    def get_up_name(self,room_id):
        API = f'https://api.live.bilibili.com/xlive/web-room/v1/index/getRoomBaseInfo?room_ids={room_id}&req_biz=video'
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"https://live.bilibili.com/{room_id}",
        }
        try:
            response = requests.get(API, headers=headers)
            response.raise_for_status()  # 如果请求返回错误状态码，会引发异常
            data = response.json()
            code = data['code']
            room_id_real = next(iter(data["data"]["by_room_ids"]))  # 真实房间号
            up_name = data["data"]["by_room_ids"][room_id_real]["uname"]      # UP主
            return up_name
        except Exception as e:
            self.ap.logger.error(f"在调用get_up_name函数时，访问URL失败，发生错误：{e}")
            return code
    
    # 检查是否已经注册提醒
    def check_if_apply(self,group_id,person_id,room_id):
        # 检查群组是否存在
        if group_id not in self.subscription["group_ids"]:
            return False
        
        # 检查person_id是否在person_ids列表中
        if "person_ids" not in self.subscription[group_id] or person_id not in self.subscription[group_id]["person_ids"]:
            return False
        
        # 检查person_id的字典中是否有任何up_name对应这个room_id
        if person_id in self.subscription[group_id] and isinstance(self.subscription[group_id][person_id], dict):
            for up_name, stored_room_id in self.subscription[group_id][person_id].items():
                if stored_room_id == room_id:
                    return True
        return False

    # 写入注册信息
    def apply_sub(self,group_id,person_id,room_id):
        up_name = self.get_up_name(room_id)
        
        # 初始化群组结构
        if group_id not in self.subscription["group_ids"]:
            self.subscription["group_ids"].append(group_id)
            self.subscription[group_id] = {
                "room_ids": [],
                "person_ids": []
            }
        
        # 确保基础结构存在
        if "room_ids" not in self.subscription[group_id]:
            self.subscription[group_id]["room_ids"] = []
        if "person_ids" not in self.subscription[group_id]:
            self.subscription[group_id]["person_ids"] = []
        
        # 添加person_id到person_ids列表（如果不存在）
        if person_id not in self.subscription[group_id]["person_ids"]:
            self.subscription[group_id]["person_ids"].append(person_id)
        
        # 确保person_id的字典存在
        if person_id not in self.subscription[group_id]:
            self.subscription[group_id][person_id] = {}
        
        # 添加up_name到person_id的字典中，格式为 {"up_name": "room_id"}
        self.subscription[group_id][person_id][up_name] = room_id
        
        # 处理room_id相关逻辑
        if room_id not in self.subscription[group_id]["room_ids"]:
            self.subscription[group_id]["room_ids"].append(room_id)
        
        # 初始化或更新room_id的订阅者列表
        if room_id not in self.subscription[group_id]:
            self.subscription[group_id][room_id] = ["0"]  # 第一个元素是状态码
        
        # 添加person_id到room_id的订阅者列表（如果不存在）
        if person_id not in self.subscription[group_id][room_id]:
            self.subscription[group_id][room_id].append(person_id)
        
        self.write_json()

    # 开始监控信息
    @handler(GroupCommandSent)
    async def cmd_run(self, ctx: EventContext):
        command = ctx.event.command
        if command == "startrem":
            ctx.prevent_default()
            ctx.prevent_postorder()
            if hasattr(self, 'run_task') and not self.run_task.done():
                await ctx.reply(["订阅任务已经开始执行了哦~"])
                return
            try:
                self.run_task = asyncio.create_task(self.run(ctx))
                await ctx.reply(["订阅任务开始执行"])
            except Exception as e:
                self.ap.logger.error(f"Error starting task: {e}")
        elif command == "rooms":
            self.ap.logger.info(f"执行rooms命令")
            group_id = str(ctx.event.launcher_id)
            person_id = str(ctx.event.sender_id)
            ctx.prevent_default()
            ctx.prevent_postorder()
            
            # 检查群组是否存在
            if group_id not in self.subscription["group_ids"]:
                await ctx.reply([At(int(ctx.event.sender_id)), "你订阅了个蛋？没订阅你瞎发什么？"])
                return
            
            # 检查person_id是否在person_ids列表中
            if "person_ids" not in self.subscription[group_id] or person_id not in self.subscription[group_id]["person_ids"]:
                await ctx.reply([At(int(ctx.event.sender_id)), "你订阅了个蛋？没订阅你瞎发什么？"])
                return
            
            # 从person_id的字典中获取订阅的UP主和房间信息
            up_room_list = []
            if person_id in self.subscription[group_id] and isinstance(self.subscription[group_id][person_id], dict):
                for up_name, room_id in self.subscription[group_id][person_id].items():
                    up_room_list.append(f"{up_name}({room_id})")
            
            if up_room_list:
                await ctx.reply([At(int(ctx.event.sender_id)), f"傻呗吗你？这你都能忘？给大伙看看你的爹爹们：<{', '.join(up_room_list)}>"]) 
            else:
                await ctx.reply([At(int(ctx.event.sender_id)), "你订阅了个蛋？没订阅你瞎发什么？"])
        elif command == "apply":
            self.ap.logger.info(f"执行apply命令")
            group_id = str(ctx.event.launcher_id)
            person_id = str(ctx.event.sender_id)
            room_id = ctx.event.text_message.split()[1]
            ctx.prevent_default()
            ctx.prevent_postorder()
            code = self.check_if_exit(room_id)
            if code == -400:
                await ctx.reply([At(int(ctx.event.sender_id)),"你没长眼睛吗？房间号对错不知道吗？"])
            elif code == 0:
                if self.check_if_apply(group_id,person_id,room_id):
                    await ctx.reply([At(int(ctx.event.sender_id)), f"你已经注册过B站直播间号[{room_id}],你再注册试试？"])
                else:
                    await ctx.reply([At(int(ctx.event.sender_id)), f"成功订阅B站直播间号[{room_id}],在开播时我会哈你"])
                    self.apply_sub(group_id,person_id,room_id)
            else:
                await ctx.reply([At(int(ctx.event.sender_id)), f"抱歉,订阅直播间发生了一个错误：{code}，请联系管理员"])
        elif command == "cancel":
            self.ap.logger.info(f"执行cancel命令")
            group_id = str(ctx.event.launcher_id)
            person_id = str(ctx.event.sender_id)
            room_id = ctx.event.text_message.split()[1]
            ctx.prevent_default()
            ctx.prevent_postorder()
            
            if self.check_if_apply(group_id, person_id, room_id):  # 如果订阅了就开始逐层删除
                # 获取要取消订阅的UP主名称
                up_name = self.get_up_name(room_id)
                
                # 从room_id的订阅者列表中删除person_id
                if room_id in self.subscription[group_id] and person_id in self.subscription[group_id][room_id]:
                    self.subscription[group_id][room_id].remove(person_id)
                
                # 从person_id的字典中删除对应的up_name
                if person_id in self.subscription[group_id] and isinstance(self.subscription[group_id][person_id], dict):
                    if up_name in self.subscription[group_id][person_id]:
                        del self.subscription[group_id][person_id][up_name]
                
                # 如果person_id的字典为空，从person_ids列表中删除该person_id
                if person_id in self.subscription[group_id] and len(self.subscription[group_id][person_id]) == 0:
                    if "person_ids" in self.subscription[group_id] and person_id in self.subscription[group_id]["person_ids"]:
                        self.subscription[group_id]["person_ids"].remove(person_id)
                    del self.subscription[group_id][person_id]
                
                # 房间清理逻辑：如果只剩状态码，删除房间
                if room_id in self.subscription[group_id] and len(self.subscription[group_id][room_id]) == 1:  # 如果只剩状态码
                    del self.subscription[group_id][room_id]
                    if "room_ids" in self.subscription[group_id] and room_id in self.subscription[group_id]["room_ids"]:
                        self.subscription[group_id]["room_ids"].remove(room_id)
                
                # 群组清理逻辑：如果该群号没有订阅房间，删除群组
                if "room_ids" in self.subscription[group_id] and len(self.subscription[group_id]["room_ids"]) == 0:
                    del self.subscription[group_id]
                    if group_id in self.subscription["group_ids"]:
                        self.subscription["group_ids"].remove(group_id)
                
                await ctx.reply([At(int(ctx.event.sender_id)), f"不看你爹<{up_name}>就滚"])
                self.write_json()
            else:
                up_name = self.get_up_name(room_id)
                await ctx.reply([At(int(ctx.event.sender_id)), f"你™订阅你爹<{up_name}>了吗？你就取消，再发给你卤煮扬了！"])

    # 插件卸载时触发
    def __del__(self):
        pass
